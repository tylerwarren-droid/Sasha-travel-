"""Where the booking routes keep what they must remember (schema: sql/001_booking_storage.sql).

⚠ A RESERVATION IS A TRIP ITEM. It lives in the repo's own trip model (migrations/001_initial_schema.sql):
  trips ──< trip_items ──< booking_attempts
The trip item is created with the intent (status `pending`: nothing asked of the venue yet). Only when the device
reports that something WAS sent does a booking_attempts row record what came back, and the trip item take the
same status. The five booking_* tables beside it are the signer's own ledger, which nothing in the trip model has
columns for (docs/sasha/S-17-existing-tables.md §3).

Two implementations of one interface:
  * PostgresStore — production. Reads DATABASE_URL and nothing else. ⚠ Nothing here creates a table; until the
    SQL has been run, every call raises StorageUnavailable("storage_not_provisioned") and the route answers 503.
  * MemoryStore   — the test double. The route suite runs against BOTH (tests/test_booking_routes.py).

⚠ Not SQLite, and not backend/app/services/chat_store.py: that file lives inside the container (S-18: it does
not survive a redeploy without a volume) and inside backend/app/, which every CTO drop replaces.
"""
from __future__ import annotations

import json
import os
import uuid
from typing import Any, Dict, List, Optional

from .verify import PairedDevice

#: The booking signer's own tables, and the model-A tables it writes. `status()` reports any that are missing.
TABLES = ("booking_pairing_challenges", "booking_devices", "booking_intents", "booking_tasks", "booking_reports",
          "trips", "trip_items", "booking_attempts")
#: The one trip each account's bookings gather under until trips are chosen by the page (§ docs, S-17).
BOOKINGS_TRIP_TITLE = "Sasha bookings"
#: Who read the venue's page — always the user's device, never this server (contract §6).
OBSERVED_BY = "the user's device"


class StorageUnavailable(Exception):
    """`rule` is storage_not_configured (no DATABASE_URL) or storage_not_provisioned (tables missing)."""

    def __init__(self, rule: str, message: str) -> None:
        super().__init__(f"{rule}: {message}")
        self.rule = rule
        #: the message without the rule — so a wrapper can re-hint it without stacking "rule: rule: rule: …"
        self.detail = message

    def rehint(self, sql_file: str) -> "StorageUnavailable":
        """The same failure, pointing at the SQL block that creates the missing table (once, not nested)."""
        if self.rule != "storage_not_provisioned":
            return self
        return StorageUnavailable(self.rule, f"{self.detail.split(' — run ')[0]} — run backend/booking_signer/sql/{sql_file}")


class AlreadyRecorded(Exception):
    """A second task for one intent, or a second verified report for one task."""


class UnknownTrip(Exception):
    """A trip id that is not one of this account's trips."""


# ── the test double ──────────────────────────────────────────────────────────────────────────

class MemoryStore:
    def __init__(self) -> None:
        self.challenges: Dict[str, dict] = {}
        self.devices_: Dict[str, dict] = {}
        self.trips: Dict[str, dict] = {}
        self.trip_items: Dict[str, dict] = {}
        self.intents: Dict[str, dict] = {}
        self.tasks: Dict[str, dict] = {}          # by intent_id
        self.reports: List[dict] = []
        self.attempts: List[dict] = []

    async def status(self) -> dict:
        return {"configured": True, "provisioned": True, "missing": []}

    async def put_challenge(self, account_id, challenge, issued_at, expires_at) -> None:
        self.challenges[challenge] = {"account_id": account_id, "expires_at": expires_at, "used_at": None}

    async def take_challenge(self, account_id, challenge, now) -> bool:
        c = self.challenges.get(challenge)
        if not c or c["account_id"] != account_id or c["used_at"] is not None or c["expires_at"] <= now:
            return False
        c["used_at"] = now
        return True

    async def add_device(self, account_id, device: PairedDevice, origin, now) -> str:
        d = self.devices_.get(device.device_id)
        if d:
            return "already" if d["account_id"] == account_id else "other_account"
        self.devices_[device.device_id] = {"account_id": account_id, "device_public_spki": device.device_public_spki, "revoked_at": None}
        return "added"

    async def devices(self, account_id) -> List[PairedDevice]:
        return [PairedDevice(k, v["device_public_spki"]) for k, v in self.devices_.items()
                if v["account_id"] == account_id and v["revoked_at"] is None]

    async def put_intent(self, row: dict, trip_id: Optional[str]) -> str:
        if trip_id is not None:
            if self.trips.get(trip_id, {}).get("owner_id") != row["account_id"]:
                raise UnknownTrip(trip_id)
        else:
            trip_id = next((k for k, t in self.trips.items() if t["owner_id"] == row["account_id"]
                            and t["title"] == BOOKINGS_TRIP_TITLE and t["status"] in ("draft", "active")), None)
            if trip_id is None:
                trip_id = str(uuid.uuid4())
                self.trips[trip_id] = {"owner_id": row["account_id"], "title": BOOKINGS_TRIP_TITLE, "status": "draft"}
        item_id = str(uuid.uuid4())
        self.trip_items[item_id] = {
            "id": item_id, "trip_id": trip_id, "type": "restaurant", "status": "pending", "booking_reference": None,
            "provider_name": row["venue_name"], "local_date": row["local_date"], "local_time": row["local_time"],
            "local_timezone": row["local_timezone"], "party_size": row["party_size"],
        }
        self.intents[row["intent_id"]] = {**{k: v for k, v in row.items() if k not in _TRIP_FIELDS and k != "request"}, "trip_item_id": item_id}
        remember_request(self.trip_items[item_id], self.intents[row["intent_id"]], row.get("request"))
        return item_id

    async def get_intent(self, account_id, intent_id) -> Optional[dict]:
        r = self.intents.get(intent_id)
        if not r or r["account_id"] != account_id:
            return None
        item = self.trip_items[r["trip_item_id"]]
        return {**r, "local_date": item["local_date"], "local_time": item["local_time"],
                "local_timezone": item["local_timezone"], "party_size": item["party_size"]}

    async def put_task(self, row: dict) -> None:
        if row["intent_id"] in self.tasks or any(t["task_digest"] == row["task_digest"] for t in self.tasks.values()):
            raise AlreadyRecorded("a task was already signed for this intent")
        self.tasks[row["intent_id"]] = dict(row)
        self.intents[row["intent_id"]]["status"] = "issued"

    async def get_task_by_digest(self, task_digest) -> Optional[dict]:
        return next((dict(t) for t in self.tasks.values() if t["task_digest"] == task_digest), None)

    async def get_report_for_task(self, task_digest) -> Optional[dict]:
        return next((dict(r) for r in self.reports if r["task_digest"] == task_digest), None)

    async def record_report(self, report_row: dict, attempt_row: Optional[dict], prepared_item_id: Optional[str] = None) -> Optional[str]:
        if report_row["task_digest"] is not None and any(r["task_digest"] == report_row["task_digest"] for r in self.reports):
            raise AlreadyRecorded("a verified report was already recorded for this task")
        self.reports.append(dict(report_row))
        if report_row["task_verified"] and report_row["intent_id"] in self.intents:
            self.intents[report_row["intent_id"]]["status"] = "reported"
        if prepared_item_id is not None and self.trip_items[prepared_item_id]["status"] == "pending":
            self.trip_items[prepared_item_id]["status"] = "prepared"   # ⚠ only ever from pending: never over an outcome
            return prepared_item_id
        if attempt_row is None:
            return None
        self.attempts.append(dict(attempt_row))
        item = self.trip_items[attempt_row["trip_item_id"]]
        item["status"] = attempt_row["status"]
        if attempt_row.get("venue_reference"):
            item["booking_reference"] = attempt_row["venue_reference"]
        return attempt_row["trip_item_id"]

    async def attempt_for_task(self, task_digest) -> Optional[dict]:
        return next((dict(a) for a in self.attempts if a["task_digest"] == task_digest), None)

    async def reservations(self, account_id) -> List[dict]:
        out = []
        for item in self.trip_items.values():
            if self.trips[item["trip_id"]]["owner_id"] != account_id or item["status"] == "pending":
                continue
            atts = [a for a in self.attempts if a["trip_item_id"] == item["id"]]
            att = atts[-1] if atts else {}   # a PREPARED item has no attempt: nothing was sent
            intent = [i for i in self.intents.values() if i["trip_item_id"] == item["id"]][-1]
            out.append({"id": item["id"], "trip_id": item["trip_id"], "intent_id": intent["intent_id"], "channel": "form",
                        "venue": item["provider_name"], "local_date": item["local_date"], "local_time": item["local_time"],
                        "local_timezone": item["local_timezone"], "party_size": item["party_size"], "status": item["status"],
                        "booking_reference": item["booking_reference"], "venue_words": att.get("venue_words"),
                        "observed_by": att.get("observed_by"), "request": item.get("request"),
                        "task_digest": self.tasks.get(intent["intent_id"], {}).get("task_digest")})
        return sorted(out, key=lambda r: (r["local_date"], r["local_time"]))


_TRIP_FIELDS = ("venue_name", "local_date", "local_time", "local_timezone", "party_size")


# ── production ───────────────────────────────────────────────────────────────────────────────

class PostgresStore:
    """asyncpg against DATABASE_URL. The pool is created on first use, never at import, so a missing or wrong
    DATABASE_URL cannot stop Sasha's backend from starting — it makes the booking routes answer 503."""

    def __init__(self, dsn: Optional[str] = None) -> None:
        self._dsn = dsn
        self._pool = None

    def _url(self) -> str:
        raw = self._dsn if self._dsn is not None else os.getenv("DATABASE_URL", "")
        if not raw.strip():
            raise StorageUnavailable("storage_not_configured", "DATABASE_URL is not set, so no booking can be stored")
        return raw.strip().replace("postgresql+asyncpg://", "postgresql://", 1)

    async def _p(self):
        if self._pool is None:
            import asyncpg

            async def _init(conn):
                await conn.set_type_codec("jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog")
            # ⚠ statement_cache_size=0: Supabase's pooler (transaction mode) cannot hold prepared statements
            self._pool = await asyncpg.create_pool(self._url(), min_size=0, max_size=4,
                                                   statement_cache_size=0, init=_init)
        return self._pool

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    async def _run(self, fn):
        import asyncpg
        try:
            pool = await self._p()
            async with pool.acquire() as conn:
                return await fn(conn)
        except (asyncpg.exceptions.UndefinedTableError, asyncpg.exceptions.UndefinedColumnError) as e:
            raise StorageUnavailable("storage_not_provisioned", f"{e} — run backend/booking_signer/sql/001_booking_storage.sql") from None
        except asyncpg.exceptions.UniqueViolationError as e:
            raise AlreadyRecorded(str(e)) from None

    async def status(self) -> dict:
        try:
            self._url()
        except StorageUnavailable:
            return {"configured": False, "provisioned": False, "missing": list(TABLES)}

        async def q(conn):
            rows = await conn.fetch("select c from unnest($1::text[]) as c where to_regclass('public.' || c) is null", list(TABLES))
            missing = [r["c"] for r in rows]
            # the S-17 additions to model A, which a pre-S-17 database has the tables but not the columns for
            if not missing and await conn.fetchval(
                    "select count(*) from information_schema.columns where table_schema = 'public' and "
                    "((table_name = 'trip_items' and column_name in ('party_size','local_timezone')) or "
                    "(table_name = 'booking_attempts' and column_name in ('task_digest','observed_by')))") != 4:
                missing.append("trip_items/booking_attempts S-17 columns")
            # S-26: a dry run marks its trip item 'prepared' — without sql/002 that would be a CHECK violation mid-demo
            if not missing and "prepared" not in (await conn.fetchval(
                    "select pg_get_constraintdef(oid) from pg_constraint where conname = 'trip_items_status_check'") or ""):
                missing.append("trip_items 'prepared' status (sql/002_prepared_status.sql)")
            return missing
        try:
            missing = await self._run(q)
        except Exception as e:  # health must report, never raise
            return {"configured": True, "provisioned": False, "missing": list(TABLES), "error": type(e).__name__}
        return {"configured": True, "provisioned": not missing, "missing": missing}

    async def put_challenge(self, account_id, challenge, issued_at, expires_at):
        await self._run(lambda c: c.execute(
            "insert into booking_pairing_challenges (challenge, account_id, issued_at, expires_at) values ($1,$2,$3,$4)",
            challenge, uuid.UUID(account_id), issued_at, expires_at))

    async def take_challenge(self, account_id, challenge, now) -> bool:
        # ⚠ one statement: a challenge is used at most once even under two concurrent pairings
        row = await self._run(lambda c: c.fetchrow(
            "update booking_pairing_challenges set used_at = $3 where challenge = $1 and account_id = $2 "
            "and used_at is null and expires_at > $3 returning challenge", challenge, uuid.UUID(account_id), now))
        return row is not None

    async def add_device(self, account_id, device, origin, now) -> str:
        async def fn(conn):
            row = await conn.fetchrow(
                "insert into booking_devices (device_id, account_id, device_public_spki, paired_origin, paired_at) "
                "values ($1,$2,$3,$4,$5) on conflict (device_id) do nothing returning device_id",
                device.device_id, uuid.UUID(account_id), device.device_public_spki, origin, now)
            if row:
                return "added"
            owner = await conn.fetchval("select account_id from booking_devices where device_id = $1", device.device_id)
            return "already" if str(owner) == account_id else "other_account"
        return await self._run(fn)

    async def devices(self, account_id):
        rows = await self._run(lambda c: c.fetch(
            "select device_id, device_public_spki from booking_devices where account_id = $1 and revoked_at is null "
            "order by paired_at", uuid.UUID(account_id)))
        return [PairedDevice(r["device_id"], r["device_public_spki"]) for r in rows]

    async def put_intent(self, row, trip_id):
        """The trip (found or created), its trip item — the reservation, status `pending` — and the intent, in ONE
        transaction. ⚠ date_time is computed BY POSTGRES from the local date, time and IANA zone, so the absolute
        instant never depends on the server's own timezone data."""
        acct = uuid.UUID(row["account_id"])

        async def fn(conn):
            async with conn.transaction():
                if trip_id is not None:
                    tid = await conn.fetchval("select id from trips where id = $1 and owner_id = $2", _uuid_or_none(trip_id), acct)
                    if tid is None:
                        raise UnknownTrip(trip_id)
                else:
                    tid = await conn.fetchval(
                        "select id from trips where owner_id = $1 and title = $2 and status in ('draft','active') "
                        "order by created_at limit 1", acct, BOOKINGS_TRIP_TITLE)
                    if tid is None:
                        tid = await conn.fetchval("insert into trips (owner_id, title) values ($1, $2) returning id", acct, BOOKINGS_TRIP_TITLE)
                item_id = await conn.fetchval(
                    "insert into trip_items (trip_id, type, status, provider_name, date_time, local_timezone, party_size) "
                    "values ($1, 'restaurant', 'pending', $2, ($3::date + $4::time) at time zone $5, $5, $6) returning id",
                    tid, row["venue_name"], row["local_date"], row["local_time"], row["local_timezone"], row["party_size"])
                await conn.execute(
                    "insert into booking_intents (intent_id, account_id, trip_item_id, venue_key, mode, guest_name, "
                    "guest_email, guest_phone, task, standing, read_back_lines, read_back_sha256, filled_values_sha256, "
                    "status, created_at) values ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15)",
                    uuid.UUID(row["intent_id"]), acct, item_id, row["venue_key"], row["mode"], row["guest_name"],
                    row["guest_email"], row["guest_phone"], row["task"], row["standing"], row["read_back_lines"],
                    row["read_back_sha256"], row["filled_values_sha256"], row["status"], row["created_at"])
                await write_request(conn, item_id, "booking_intents", "intent_id", uuid.UUID(row["intent_id"]), row.get("request"))
                return str(item_id)
        return await self._run(fn)

    async def get_intent(self, account_id, intent_id):
        iid = _uuid_or_none(intent_id)
        if iid is None:
            return None
        r = await self._run(lambda c: c.fetchrow(
            "select i.*, (t.date_time at time zone t.local_timezone)::date as local_date, "
            "(t.date_time at time zone t.local_timezone)::time as local_time, t.local_timezone, t.party_size "
            "from booking_intents i join trip_items t on t.id = i.trip_item_id "
            "where i.intent_id = $1 and i.account_id = $2", iid, uuid.UUID(account_id)))
        return _row(r)

    async def put_task(self, row):
        async def fn(conn):
            async with conn.transaction():
                await conn.execute(
                    "insert into booking_tasks (intent_id, task_digest, account_id, device_id, mode, payload, signature, "
                    "issued_at, expires_at) values ($1,$2,$3,$4,$5,$6,$7,$8,$9)",
                    uuid.UUID(row["intent_id"]), row["task_digest"], uuid.UUID(row["account_id"]), row["device_id"],
                    row["mode"], row["payload"], row["signature"], row["issued_at"], row["expires_at"])
                await conn.execute("update booking_intents set status = 'issued' where intent_id = $1", uuid.UUID(row["intent_id"]))
        await self._run(fn)

    async def get_task_by_digest(self, task_digest):
        return _row(await self._run(lambda c: c.fetchrow("select * from booking_tasks where task_digest = $1", task_digest)))

    async def get_report_for_task(self, task_digest):
        return _row(await self._run(lambda c: c.fetchrow("select * from booking_reports where task_digest = $1", task_digest)))

    async def record_report(self, report_row, attempt_row, prepared_item_id=None):
        """The report, and — only if something was sent — the attempt and the trip item's status, in ONE transaction.
        A verified DRY RUN that captured its form marks the trip item 'prepared' instead: no attempt, nothing sent."""
        async def fn(conn):
            async with conn.transaction():
                await conn.execute(
                    "insert into booking_reports (received_at, account_id, device_id, task_digest, intent_id, task_verified, "
                    "report, device_signature, outcome) values ($1,$2,$3,$4,$5,$6,$7,$8,$9)",
                    report_row["received_at"], uuid.UUID(report_row["account_id"]), report_row["device_id"],
                    report_row["task_digest"], _uuid_or_none(report_row["intent_id"]), report_row["task_verified"],
                    report_row["report"], report_row["device_signature"], report_row["outcome"])
                if report_row["task_verified"]:
                    await conn.execute("update booking_intents set status = 'reported' where intent_id = $1",
                                       uuid.UUID(report_row["intent_id"]))
                if prepared_item_id is not None:
                    # ⚠ only ever from 'pending' — a prepared dry run never overwrites an outcome
                    await conn.execute("update trip_items set status = 'prepared', updated_at = now() "
                                       "where id = $1 and status = 'pending'", uuid.UUID(prepared_item_id))
                    return prepared_item_id
                if attempt_row is None:
                    return None
                a = attempt_row
                # ⚠ status is ALWAYS given: booking_attempts has no default any more (S-17)
                await conn.execute(
                    "insert into booking_attempts (trip_item_id, method, attempted_at, status, response_received, "
                    "response_at, task_digest, observed_by) values ($1, 'web_form', $2, $3, $4, $5, $6, $7)",
                    uuid.UUID(a["trip_item_id"]), a["attempted_at"], a["status"], a["venue_words"], a["observed_at"],
                    a["task_digest"], a["observed_by"])
                await conn.execute(
                    "update trip_items set status = $2, booking_reference = coalesce($3, booking_reference), "
                    "updated_at = now() where id = $1", uuid.UUID(a["trip_item_id"]), a["status"], a["venue_reference"])
                return a["trip_item_id"]
        return await self._run(fn)

    async def attempt_for_task(self, task_digest):
        return _row(await self._run(lambda c: c.fetchrow("select * from booking_attempts where task_digest = $1", task_digest)))

    async def reservations(self, account_id):
        rows = await self._run(lambda c: c.fetch(
            # S-41 G5 · EVERY channel's reservation, not only the form's: a phone call, an email, a slot link. Which one it
            # was is said (`channel`), and the venue's own words come from the attempt, or from the call when it was one.
            "select t.id, t.trip_id, coalesce(i.intent_id, c.call_id, e.email_id, l.link_id) as intent_id, "
            "case when i.intent_id is not null then 'form' when c.call_id is not null then 'phone' "
            "     when e.email_id is not null then 'email' when l.link_id is not null then 'link' end as channel, "
            "t.provider_name as venue, "
            "(t.date_time at time zone t.local_timezone)::date as local_date, "
            "(t.date_time at time zone t.local_timezone)::time as local_time, t.local_timezone, t.party_size, t.status, "
            "t.booking_reference, coalesce(a.response_received, c.venue_words) as venue_words, a.observed_by, k.task_digest, "
            "c.own_reference, "   # Sasha 88 · her K-XXXX, said to the venue
            "t.request "   # S-64 step 14 · the activity, its length and its unit, for the screen
            "from trip_items t join trips p on p.id = t.trip_id "
            "left join lateral (select * from booking_intents y where y.trip_item_id = t.id order by y.created_at desc limit 1) i on true "
            "left join booking_tasks k on k.intent_id = i.intent_id "
            "left join lateral (select call_id, venue_words, brief->>'own_reference' as own_reference from booking_calls z "
            "where z.trip_item_id = t.id order by z.created_at desc limit 1) c on true "
            "left join lateral (select email_id from booking_emails z where z.trip_item_id = t.id limit 1) e on true "
            "left join lateral (select link_id from booking_links z where z.trip_item_id = t.id limit 1) l on true "
            # a PREPARED item has no attempt — nothing was sent — so the attempt is optional
            "left join lateral (select * from booking_attempts x where x.trip_item_id = t.id order by x.attempted_at desc limit 1) a on true "
            "where p.owner_id = $1 and t.status <> 'pending' order by local_date nulls last, local_time nulls last", uuid.UUID(account_id)))
        return [_row(r) for r in rows]


def _uuid_or_none(v: Any) -> Optional[uuid.UUID]:
    try:
        return uuid.UUID(str(v)) if v is not None else None
    except (ValueError, TypeError, AttributeError):
        return None


async def write_request(conn, item_id, table: str, key_col: str, key, request) -> None:
    """S-64 step 3 · the reservation/1 object alongside the old columns, IN the caller's transaction: the object and
    its hash on the trip item (when this row created it), the hash on the channel row. No object, nothing written."""
    if not request:
        return
    from . import reservation as RS
    sha = RS.sha256(request)
    if item_id is not None:
        await conn.execute("update trip_items set request = $2, request_sha256 = $3, request_schema = $4 where id = $1",
                           item_id, RS.validate(request), sha, RS.SCHEMA)
    await conn.execute(f"update {table} set request_sha256 = $2 where {key_col} = $1", key, sha)


def remember_request(item: Optional[dict], channel: dict, request) -> None:
    """The same, for the memory stores (tests)."""
    if not request:
        return
    from . import reservation as RS
    sha = RS.sha256(request)
    if item is not None:
        item.update(request=RS.validate(request), request_sha256=sha, request_schema=RS.SCHEMA)
    channel["request_sha256"] = sha


def _row(r) -> Optional[dict]:
    """asyncpg Record → dict, with uuids as strings so both stores hand back the same shapes."""
    if r is None:
        return None
    return {k: (str(v) if isinstance(v, uuid.UUID) else v) for k, v in dict(r).items()}
