"""Where the ladder remembers (schema: sql/004_ladder.sql) — venue reads, emails, replies, quarantine.

Email status, and the only moves:
  awaiting_approval ──yes──▶ sending ──Resend accepted──▶ sent
                                     └─Resend refused───▶ not_sent
⚠ `sending` is claimed BEFORE Resend is asked, so one yes sends at most one email. Left in `sending` (the process died
before Resend's answer was recorded), it is shown as exactly that and never re-sent.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from .call_store import PostgresCallStore
from .store import BOOKINGS_TRIP_TITLE, StorageUnavailable, UnknownTrip, _row, _uuid_or_none

SENT_OR_TRYING = ("sending", "sent")


class MemoryLadderStore:
    def __init__(self) -> None:
        self.reads: Dict[str, dict] = {}
        self.emails: Dict[str, dict] = {}
        self.replies: List[dict] = []
        self.quarantined: List[dict] = []
        self.trips: Dict[str, dict] = {}
        self.trip_items: Dict[str, dict] = {}
        self.attempts: List[dict] = []

    async def put_read(self, row: dict) -> None:
        self.reads[row["read_id"]] = dict(row)

    async def get_read(self, account_id: str, read_id: str) -> Optional[dict]:
        r = self.reads.get(read_id)
        return dict(r) if r and r["account_id"] == account_id else None

    async def put_email(self, row: dict, trip_id: Optional[str]) -> str:
        if trip_id is not None and self.trips.get(trip_id, {}).get("owner_id") != row["account_id"]:
            raise UnknownTrip(trip_id)
        trip_id = trip_id or next((k for k, t in self.trips.items() if t["owner_id"] == row["account_id"]), None) or str(uuid.uuid4())
        self.trips.setdefault(trip_id, {"owner_id": row["account_id"], "title": BOOKINGS_TRIP_TITLE})
        item = str(uuid.uuid4())
        self.trip_items[item] = {"id": item, "status": "pending", "provider_name": row["venue_name"]}
        self.emails[row["email_id"]] = {**{k: v for k, v in row.items() if k not in _TRIP}, "trip_item_id": item, "status": "awaiting_approval"}
        return item

    async def get_email(self, account_id: str, email_id: str) -> Optional[dict]:
        e = self.emails.get(email_id)
        return dict(e) if e and e["account_id"] == account_id else None

    async def claim_email(self, account_id, email_id, approval, now, fresh_after, cap, since) -> str:
        e = self.emails.get(email_id)
        if not e or e["account_id"] != account_id:
            return "unknown"
        if e["status"] != "awaiting_approval":
            return "taken"
        if e["created_at"] < fresh_after:
            return "stale"
        if sum(1 for x in self.emails.values() if x["status"] in SENT_OR_TRYING and x.get("approved_at") and x["approved_at"] >= since) >= cap:
            return "cap"
        e.update(status="sending", approval=approval, approved_at=now)
        return "claimed"

    async def mark_sent(self, email_id: str, sent, now: datetime) -> None:
        e = self.emails[email_id]
        if e["status"] != "sending":
            return
        e.update(status="sent" if sent.sent else "not_sent", provider_id=sent.provider_id, provider_http=sent.http_status,
                 provider_answer=sent.answer, not_sent_why=sent.why, sent_at=now if sent.sent else None)
        if sent.sent:
            self.attempts.append({"trip_item_id": e["trip_item_id"], "method": "email", "status": "sent"})
            self.trip_items[e["trip_item_id"]]["status"] = "attempting"

    async def email_exists(self, email_id: str) -> bool:
        return email_id in self.emails

    async def add_reply(self, row: dict) -> bool:
        if any(r["provider_id"] == row["provider_id"] for r in self.replies):
            return False
        self.replies.append(dict(row))
        return True

    async def quarantine(self, row: dict) -> bool:
        if any(r["provider_id"] == row["provider_id"] for r in self.quarantined):
            return False
        self.quarantined.append(dict(row))
        return True

    async def replies_for(self, email_id: str) -> List[dict]:
        return sorted([dict(r) for r in self.replies if r["email_id"] == email_id], key=lambda r: r["received_at"])


_TRIP = ("venue_name",)


class PostgresLadderStore:
    def __init__(self, base) -> None:
        self._base = base
        self._calls = PostgresCallStore(base)

    async def _run(self, fn):
        try:
            return await self._calls._run(fn)
        except StorageUnavailable as e:
            if e.rule == "storage_not_provisioned":
                raise StorageUnavailable("storage_not_provisioned", f"{e} — run backend/booking_signer/sql/004_ladder.sql") from None
            raise

    async def put_read(self, row):
        await self._run(lambda c: c.execute(
            "insert into venue_reads (read_id, account_id, query, venue_name, country, read, created_at) values ($1,$2,$3,$4,$5,$6,$7)",
            uuid.UUID(row["read_id"]), uuid.UUID(row["account_id"]), row["query"], row["venue_name"], row["country"], row["read"], row["created_at"]))

    async def get_read(self, account_id, read_id):
        rid = _uuid_or_none(read_id)
        if rid is None:
            return None
        return _row(await self._run(lambda c: c.fetchrow(
            "select * from venue_reads where read_id = $1 and account_id = $2", rid, uuid.UUID(account_id))))

    async def put_email(self, row, trip_id):
        acct = uuid.UUID(row["account_id"])

        async def fn(conn):
            async with conn.transaction():
                if trip_id is not None:
                    tid = await conn.fetchval("select id from trips where id = $1 and owner_id = $2", _uuid_or_none(trip_id), acct)
                    if tid is None:
                        raise UnknownTrip(trip_id)
                else:
                    tid = await conn.fetchval("select id from trips where owner_id = $1 and title = $2 and status in ('draft','active') "
                                              "order by created_at limit 1", acct, BOOKINGS_TRIP_TITLE)
                    if tid is None:
                        tid = await conn.fetchval("insert into trips (owner_id, title) values ($1, $2) returning id", acct, BOOKINGS_TRIP_TITLE)
                item = await conn.fetchval(
                    "insert into trip_items (trip_id, type, status, provider_name, date_time, local_timezone, party_size) "
                    "values ($1, 'restaurant', 'pending', $2, ($3::date + $4::time) at time zone $5, $5, $6) returning id",
                    tid, row["venue_name"], row["local_date"], row["local_time"], row["local_timezone"], row["party_size"])
                await conn.execute(
                    "insert into booking_emails (email_id, account_id, trip_item_id, read_id, email, email_sha256, read_back_lines, "
                    "read_back_sha256, status, created_at) values ($1,$2,$3,$4,$5,$6,$7,$8,'awaiting_approval',$9)",
                    uuid.UUID(row["email_id"]), acct, item, uuid.UUID(row["read_id"]), row["email"], row["email_sha256"],
                    row["read_back_lines"], row["read_back_sha256"], row["created_at"])
                return str(item)
        return await self._run(fn)

    async def get_email(self, account_id, email_id):
        eid = _uuid_or_none(email_id)
        if eid is None:
            return None
        return _row(await self._run(lambda c: c.fetchrow(
            "select * from booking_emails where email_id = $1 and account_id = $2", eid, uuid.UUID(account_id))))

    async def claim_email(self, account_id, email_id, approval, now, fresh_after, cap, since):
        eid = _uuid_or_none(email_id)
        if eid is None:
            return "unknown"

        async def fn(conn):
            async with conn.transaction():
                await conn.execute("lock table booking_emails in share row exclusive mode")
                r = await conn.fetchrow("select status, created_at from booking_emails where email_id = $1 and account_id = $2",
                                        eid, uuid.UUID(account_id))
                if r is None:
                    return "unknown"
                if r["status"] != "awaiting_approval":
                    return "taken"
                if r["created_at"] < fresh_after:
                    return "stale"
                n = await conn.fetchval("select count(*) from booking_emails where status = any($1::text[]) and approved_at >= $2",
                                        list(SENT_OR_TRYING), since)
                if n >= cap:
                    return "cap"
                await conn.execute("update booking_emails set status = 'sending', approval = $2, approved_at = $3 where email_id = $1",
                                   eid, approval, now)
                return "claimed"
        return await self._run(fn)

    async def mark_sent(self, email_id, sent, now):
        async def fn(conn):
            async with conn.transaction():
                item = await conn.fetchval(
                    "update booking_emails set status = $2, provider_id = $3, provider_http = $4, provider_answer = $5, "
                    "not_sent_why = $6, sent_at = $7 where email_id = $1 and status = 'sending' returning trip_item_id",
                    uuid.UUID(email_id), "sent" if sent.sent else "not_sent", sent.provider_id, sent.http_status, sent.answer,
                    sent.why, now if sent.sent else None)
                if item is not None and sent.sent:
                    await conn.execute("insert into booking_attempts (trip_item_id, method, attempted_at, status, observed_by) "
                                       "values ($1, 'email', $2, 'sent', 'the mail service accepted it (Resend)')", item, now)
                    await conn.execute("update trip_items set status = 'attempting', updated_at = now() where id = $1 and status = 'pending'", item)
        await self._run(fn)

    async def email_exists(self, email_id):
        eid = _uuid_or_none(email_id)
        return eid is not None and bool(await self._run(lambda c: c.fetchval("select 1 from booking_emails where email_id = $1", eid)))

    async def add_reply(self, row):
        r = await self._run(lambda c: c.fetchrow(
            "insert into booking_email_replies (provider_id, email_id, from_addr, subject, body_text, note, received_at) "
            "values ($1,$2,$3,$4,$5,$6,$7) on conflict (provider_id) do nothing returning provider_id",
            row["provider_id"], uuid.UUID(row["email_id"]), row["from_addr"], row["subject"], row["body_text"], row["note"], row["received_at"]))
        return r is not None

    async def quarantine(self, row):
        r = await self._run(lambda c: c.fetchrow(
            "insert into booking_email_quarantine (provider_id, to_addrs, from_addr, subject, reason, received_at) "
            "values ($1,$2,$3,$4,$5,$6) on conflict (provider_id) do nothing returning provider_id",
            row["provider_id"], row["to_addrs"], row["from_addr"], row["subject"], row["reason"], row["received_at"]))
        return r is not None

    async def replies_for(self, email_id):
        rows = await self._run(lambda c: c.fetch(
            "select * from booking_email_replies where email_id = $1 order by received_at", uuid.UUID(email_id)))
        return [_row(r) for r in rows]
