"""Where the booking routes keep what they must remember (tables: sql/001_booking_storage.sql).

Two implementations of one interface:
  * PostgresStore — production. Reads DATABASE_URL and nothing else. ⚠ Nothing here creates a table: the SQL
    is the founder's to run, and until he does, every call raises StorageUnavailable("storage_not_provisioned")
    and the route answers 503 — loud, never a silent loss.
  * MemoryStore   — the test double. The route suite runs against BOTH (tests/test_booking_routes.py), so
    the double cannot drift from the real thing without a test failing.

⚠ Not SQLite, and not backend/app/services/chat_store.py. That store is a file inside the container
(S-18: it does not survive a redeploy without a volume), and it lives in backend/app/, which every CTO drop
replaces. A booking must outlive both.
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from .verify import PairedDevice

TABLES = ("booking_pairing_challenges", "booking_devices", "booking_intents",
          "booking_tasks", "booking_reports", "reservations")


class StorageUnavailable(Exception):
    """`rule` is storage_not_configured (no DATABASE_URL) or storage_not_provisioned (tables missing)."""

    def __init__(self, rule: str, message: str) -> None:
        super().__init__(f"{rule}: {message}")
        self.rule = rule


class AlreadyRecorded(Exception):
    """A second task for one intent, or a second verified report for one task."""


# ── the test double ──────────────────────────────────────────────────────────────────────────

class MemoryStore:
    def __init__(self) -> None:
        self.challenges: Dict[str, dict] = {}
        self.devices_: Dict[str, dict] = {}
        self.intents: Dict[str, dict] = {}
        self.tasks: Dict[str, dict] = {}          # by intent_id
        self.reports: List[dict] = []
        self.reservations_: List[dict] = []

    async def status(self) -> dict:
        return {"configured": True, "provisioned": True, "missing": []}

    async def put_challenge(self, account_id: str, challenge: str, issued_at: datetime, expires_at: datetime) -> None:
        self.challenges[challenge] = {"account_id": account_id, "issued_at": issued_at, "expires_at": expires_at, "used_at": None}

    async def take_challenge(self, account_id: str, challenge: str, now: datetime) -> bool:
        c = self.challenges.get(challenge)
        if not c or c["account_id"] != account_id or c["used_at"] is not None or c["expires_at"] <= now:
            return False
        c["used_at"] = now
        return True

    async def add_device(self, account_id: str, device: PairedDevice, origin: str, now: datetime) -> str:
        d = self.devices_.get(device.device_id)
        if d:
            return "already" if d["account_id"] == account_id else "other_account"
        self.devices_[device.device_id] = {"account_id": account_id, "device_public_spki": device.device_public_spki,
                                           "paired_origin": origin, "paired_at": now, "revoked_at": None}
        return "added"

    async def devices(self, account_id: str) -> List[PairedDevice]:
        return [PairedDevice(k, v["device_public_spki"]) for k, v in self.devices_.items()
                if v["account_id"] == account_id and v["revoked_at"] is None]

    async def put_intent(self, row: dict) -> None:
        self.intents[row["intent_id"]] = dict(row)

    async def get_intent(self, account_id: str, intent_id: str) -> Optional[dict]:
        r = self.intents.get(intent_id)
        return dict(r) if r and r["account_id"] == account_id else None

    async def put_task(self, row: dict) -> None:
        if row["intent_id"] in self.tasks or any(t["task_digest"] == row["task_digest"] for t in self.tasks.values()):
            raise AlreadyRecorded("a task was already signed for this intent")
        self.tasks[row["intent_id"]] = dict(row)
        self.intents[row["intent_id"]]["status"] = "issued"

    async def get_task_by_digest(self, task_digest: str) -> Optional[dict]:
        return next((dict(t) for t in self.tasks.values() if t["task_digest"] == task_digest), None)

    async def get_report_for_task(self, task_digest: str) -> Optional[dict]:
        return next((dict(r) for r in self.reports if r["task_digest"] == task_digest), None)

    async def record_report(self, report_row: dict, reservation_row: Optional[dict]) -> Optional[str]:
        if report_row["task_digest"] is not None and any(r["task_digest"] == report_row["task_digest"] for r in self.reports):
            raise AlreadyRecorded("a verified report was already recorded for this task")
        self.reports.append(dict(report_row))
        if report_row["task_verified"] and report_row["intent_id"] in self.intents:
            self.intents[report_row["intent_id"]]["status"] = "reported"
        if reservation_row is None:
            return None
        rid = str(uuid.uuid4())
        self.reservations_.append({**reservation_row, "id": rid})
        return rid

    async def reservation_for_intent(self, intent_id: str) -> Optional[dict]:
        return next((dict(r) for r in self.reservations_ if r["intent_id"] == intent_id), None)

    async def reservations(self, account_id: str) -> List[dict]:
        rows = [dict(r) for r in self.reservations_ if r["account_id"] == account_id]
        return sorted(rows, key=lambda r: (r["local_date"], r["local_time"]))


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
        # app/db.py's SQLAlchemy form, if that is what is set; asyncpg wants the plain scheme
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
        except asyncpg.exceptions.UndefinedTableError as e:
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
            return [r["c"] for r in rows]
        try:
            missing = await self._run(q)
        except Exception as e:  # health must report, never raise
            return {"configured": True, "provisioned": False, "missing": list(TABLES), "error": type(e).__name__}
        return {"configured": True, "provisioned": not missing, "missing": missing}

    async def put_challenge(self, account_id, challenge, issued_at, expires_at):
        await self._run(lambda c: c.execute(
            "insert into booking_pairing_challenges (challenge, account_id, issued_at, expires_at) values ($1,$2,$3,$4)",
            challenge, account_id, issued_at, expires_at))

    async def take_challenge(self, account_id, challenge, now) -> bool:
        # ⚠ one statement: a challenge is used at most once even under two concurrent pairings
        row = await self._run(lambda c: c.fetchrow(
            "update booking_pairing_challenges set used_at = $3 where challenge = $1 and account_id = $2 "
            "and used_at is null and expires_at > $3 returning challenge", challenge, account_id, now))
        return row is not None

    async def add_device(self, account_id, device, origin, now) -> str:
        async def fn(conn):
            row = await conn.fetchrow(
                "insert into booking_devices (device_id, account_id, device_public_spki, paired_origin, paired_at) "
                "values ($1,$2,$3,$4,$5) on conflict (device_id) do nothing returning device_id",
                device.device_id, account_id, device.device_public_spki, origin, now)
            if row:
                return "added"
            owner = await conn.fetchval("select account_id from booking_devices where device_id = $1", device.device_id)
            return "already" if owner == account_id else "other_account"
        return await self._run(fn)

    async def devices(self, account_id):
        rows = await self._run(lambda c: c.fetch(
            "select device_id, device_public_spki from booking_devices where account_id = $1 and revoked_at is null "
            "order by paired_at", account_id))
        return [PairedDevice(r["device_id"], r["device_public_spki"]) for r in rows]

    async def put_intent(self, row):
        await self._run(lambda c: c.execute(
            "insert into booking_intents (intent_id, account_id, venue_key, mode, local_date, local_time, venue_timezone, "
            "party, guest_name, guest_email, guest_phone, task, standing, read_back_lines, read_back_sha256, "
            "filled_values_sha256, itinerary_id, status, created_at) "
            "values ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19)",
            uuid.UUID(row["intent_id"]), row["account_id"], row["venue_key"], row["mode"], row["local_date"],
            row["local_time"], row["venue_timezone"], row["party"], row["guest_name"], row["guest_email"],
            row["guest_phone"], row["task"], row["standing"], row["read_back_lines"], row["read_back_sha256"],
            row["filled_values_sha256"], row["itinerary_id"], row["status"], row["created_at"]))

    async def get_intent(self, account_id, intent_id):
        try:
            iid = uuid.UUID(intent_id)
        except (ValueError, TypeError, AttributeError):
            return None
        r = await self._run(lambda c: c.fetchrow(
            "select * from booking_intents where intent_id = $1 and account_id = $2", iid, account_id))
        return _row(r)

    async def put_task(self, row):
        async def fn(conn):
            async with conn.transaction():
                await conn.execute(
                    "insert into booking_tasks (intent_id, task_digest, account_id, device_id, mode, payload, signature, "
                    "issued_at, expires_at) values ($1,$2,$3,$4,$5,$6,$7,$8,$9)",
                    uuid.UUID(row["intent_id"]), row["task_digest"], row["account_id"], row["device_id"], row["mode"],
                    row["payload"], row["signature"], row["issued_at"], row["expires_at"])
                await conn.execute("update booking_intents set status = 'issued' where intent_id = $1", uuid.UUID(row["intent_id"]))
        await self._run(fn)

    async def get_task_by_digest(self, task_digest):
        return _row(await self._run(lambda c: c.fetchrow("select * from booking_tasks where task_digest = $1", task_digest)))

    async def get_report_for_task(self, task_digest):
        return _row(await self._run(lambda c: c.fetchrow("select * from booking_reports where task_digest = $1", task_digest)))

    async def record_report(self, report_row, reservation_row):
        async def fn(conn):
            async with conn.transaction():
                await conn.execute(
                    "insert into booking_reports (received_at, account_id, device_id, task_digest, intent_id, task_verified, "
                    "report, device_signature, outcome) values ($1,$2,$3,$4,$5,$6,$7,$8,$9)",
                    report_row["received_at"], report_row["account_id"], report_row["device_id"], report_row["task_digest"],
                    uuid.UUID(report_row["intent_id"]) if report_row["intent_id"] else None, report_row["task_verified"],
                    report_row["report"], report_row["device_signature"], report_row["outcome"])
                if report_row["task_verified"]:
                    await conn.execute("update booking_intents set status = 'reported' where intent_id = $1",
                                       uuid.UUID(report_row["intent_id"]))
                if reservation_row is None:
                    return None
                r = reservation_row
                rid = await conn.fetchval(
                    "insert into reservations (intent_id, task_digest, account_id, itinerary_id, venue_key, venue_name, "
                    "venue_origin, local_date, local_time, venue_timezone, party, status, status_basis, venue_reference, "
                    "venue_words, observed_at, created_at) values ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17) "
                    "returning id",
                    uuid.UUID(r["intent_id"]), r["task_digest"], r["account_id"], r["itinerary_id"], r["venue_key"],
                    r["venue_name"], r["venue_origin"], r["local_date"], r["local_time"], r["venue_timezone"], r["party"],
                    r["status"], r["status_basis"], r["venue_reference"], r["venue_words"], r["observed_at"], r["created_at"])
                return str(rid)
        return await self._run(fn)

    async def reservation_for_intent(self, intent_id):
        return _row(await self._run(lambda c: c.fetchrow(
            "select * from reservations where intent_id = $1", uuid.UUID(intent_id))))

    async def reservations(self, account_id):
        rows = await self._run(lambda c: c.fetch(
            "select * from reservations where account_id = $1 order by local_date, local_time", account_id))
        return [_row(r) for r in rows]


def _row(r) -> Optional[dict]:
    """asyncpg Record → dict, with uuids as strings so both stores hand back the same shapes."""
    if r is None:
        return None
    return {k: (str(v) if isinstance(v, uuid.UUID) else v) for k, v in dict(r).items()}
