"""Where a phone call is remembered (schema: sql/003_phone_calls.sql).

One row per call in booking_calls, created with the read-back as `awaiting_approval`, beside a trip item (the
reservation, `pending`) in the account's "Sasha bookings" trip — the same trip a form booking lands in.

Status, and the only moves between them:
  awaiting_approval ──yes──▶ placing ──Bland accepted──▶ placed ──finished──▶ answered | not_reached
                                      └─Bland refused──▶ not_placed
⚠ `placing` is claimed BEFORE Bland is asked, in one statement, so two approvals cannot dial twice. A row left in
`placing` (the process died between the claim and Bland's answer) is shown as exactly that — it is never retried.

Only `answered` touches model A: a booking_attempts row (method 'phone') and the trip item's status —
yes → confirmed, no → declined, unclear → unclear. A call that reached nobody leaves the reservation `pending`.

Two implementations of one interface, as store.py: MemoryCallStore (tests) and PostgresCallStore (production).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Tuple

from .store import BOOKINGS_TRIP_TITLE, PostgresStore, StorageUnavailable, UnknownTrip, _row, _uuid_or_none, remember_request, write_request

#: The venue-facing status each outcome gives the reservation.
TRIP_STATUS = {"yes": "confirmed", "no": "declined", "unclear": "unclear"}
#: S-64 step 8 · an offer instead of a yes: the reservation says so; the attempt is `unclear` (never `confirmed`)
OFFER_STATUS = {"proposed": "proposed", "quoted": "quoted", "waitlisted": "waitlisted"}


def outcome_effect(purpose: str, outcome: str, offer: Optional[dict] = None) -> Tuple[str, Optional[str]]:
    """(the attempt's status, the trip item's NEW status or None to leave it). S-47 · a cancellation that the venue
    confirmed cancels the reservation; one they refused or left unclear leaves the booking as it stands — never a guess
    that it is gone."""
    if purpose == "cancel":
        return {"yes": ("confirmed", "cancelled"), "no": ("declined", None), "unclear": ("unclear", None)}[outcome]
    if offer and outcome != "yes" and offer.get("kind") in OFFER_STATUS:
        return "unclear", OFFER_STATUS[offer["kind"]]
    return TRIP_STATUS[outcome], TRIP_STATUS[outcome]
#: Who read the outcome, as recorded on the attempt.
OBSERVED_BY_CALL = "Sasha's phone call — an AI reading of the transcript, with the venue's own words"
#: A call row counts against the daily ceiling from the moment it is claimed.
DIALLED = ("placing", "placed", "not_reached", "answered")


class MemoryCallStore:
    def __init__(self) -> None:
        self.trips: Dict[str, dict] = {}
        self.trip_items: Dict[str, dict] = {}
        self.calls: Dict[str, dict] = {}
        self.attempts: list = []

    async def put_call(self, row: dict, trip_id: Optional[str]) -> str:
        if trip_id is not None:
            if self.trips.get(trip_id, {}).get("owner_id") != row["account_id"]:
                raise UnknownTrip(trip_id)
        else:
            trip_id = next((k for k, t in self.trips.items() if t["owner_id"] == row["account_id"]
                            and t["title"] == BOOKINGS_TRIP_TITLE), None) or str(uuid.uuid4())
            self.trips.setdefault(trip_id, {"owner_id": row["account_id"], "title": BOOKINGS_TRIP_TITLE})
        item_id = str(uuid.uuid4())
        self.trip_items[item_id] = {"id": item_id, "status": "pending", "provider_name": row["venue_name"],
                                    "local_date": row["local_date"], "local_time": row["local_time"], "party_size": row["party_size"]}
        self.calls[row["call_id"]] = {**{k: v for k, v in row.items() if k not in _TRIP and k != "request"}, "trip_item_id": item_id,
                                      "status": "awaiting_approval"}
        remember_request(self.trip_items[item_id], self.calls[row["call_id"]], row.get("request"))
        return item_id

    async def get_call(self, account_id: str, call_id: str) -> Optional[dict]:
        r = self.calls.get(call_id)
        return dict(r) if r and r["account_id"] == account_id else None

    async def confirming(self, call_id: str) -> Optional[str]:
        """Sasha 108 · the confirmation call placed after this unclear call, if any."""
        return next((k for k, c in self.calls.items() if (c.get("brief") or {}).get("confirms_call_id") == call_id), None)

    async def confirmations(self, call_id: str, field: str = "confirms_call_id") -> list:
        """Sasha 108 · every confirmation call of this booking call (or, field="cancels_call_id", every cancelling call),
        oldest first."""
        return sorted((dict(c) for c in self.calls.values() if (c.get("brief") or {}).get(field) == call_id),
                      key=lambda c: c.get("created_at") or datetime.min)

    async def receipt_rows(self, account_id: str, trip_item_id: str) -> Optional[dict]:
        """Sasha 88 · the booking call behind a reservation, the reservation, and what the venue WROTE about it."""
        calls = [c for c in self.calls.values() if c.get("trip_item_id") == trip_item_id and c["account_id"] == account_id
                 and (c.get("brief") or {}).get("purpose", "book") == "book"]
        if not calls:
            return None
        call = max(calls, key=lambda c: (c.get("status") == "answered", c.get("created_at") or datetime.min))   # Sasha 109
        return {"call": dict(call), "item": dict(self.trip_items.get(trip_item_id) or {}),
                "written": [dict(w) for w in getattr(self, "written", []) if w.get("trip_item_id") == trip_item_id]}

    async def claim(self, account_id: str, call_id: str, approval: dict, now: datetime, fresh_after: datetime,
                    cap: int, since: datetime, account_cap: Optional[int] = None) -> str:
        """'claimed' | 'stale' | 'cap' | 'account_cap' | 'taken' | 'unknown' — in ONE step."""
        r = self.calls.get(call_id)
        if not r or r["account_id"] != account_id:
            return "unknown"
        if r["status"] != "awaiting_approval" or r.get("approval"):   # S-66 · a scheduled call is already approved
            return "taken"
        if r["created_at"] < fresh_after:
            return "stale"
        if sum(1 for c in self.calls.values() if c["status"] in DIALLED and c.get("approved_at") and c["approved_at"] >= since) >= cap:
            return "cap"
        if account_cap is not None and sum(1 for c in self.calls.values() if c["account_id"] == account_id and c["status"] in DIALLED
                                           and c.get("approved_at") and c["approved_at"] >= since) >= account_cap:
            return "account_cap"   # S-62 step 2 · per account as well as global
        r.update(status="placing", approval=approval, approved_at=now)
        return "claimed"

    # ── S-66 · a call scheduled for the venue's opening (its yes given while it was closed) ──
    async def schedule(self, account_id, call_id, approval, now, fresh_after) -> str:
        r = self.calls.get(call_id)
        if not r or r["account_id"] != account_id:
            return "unknown"
        if r["status"] != "awaiting_approval" or r.get("approval"):
            return "taken"
        if r["created_at"] < fresh_after:
            return "stale"
        r.update(approval=dict(approval), approved_at=now)
        return "scheduled"

    async def link_email(self, call_id, email_id) -> None:
        self.calls[call_id]["approval"]["email_id"] = email_id

    async def due(self, now) -> list:
        return [dict(c) for c in self.calls.values() if c["status"] == "awaiting_approval" and (c.get("approval") or {}).get("scheduled_for")
                and datetime.fromisoformat(c["approval"]["scheduled_for"]) <= now]

    async def start_scheduled(self, call_id, cap, since, account_cap: Optional[int] = None) -> str:
        r = self.calls[call_id]
        if r["status"] != "awaiting_approval" or not (r.get("approval") or {}).get("scheduled_for"):
            return "taken"
        if sum(1 for c in self.calls.values() if c["status"] in DIALLED and c.get("approved_at") and c["approved_at"] >= since) >= cap:
            return "cap"
        if account_cap is not None and sum(1 for c in self.calls.values() if c["account_id"] == r["account_id"] and c["status"] in DIALLED
                                           and c.get("approved_at") and c["approved_at"] >= since and c is not r) >= account_cap:
            return "account_cap"
        r["status"] = "placing"
        return "claimed"

    async def cancel_scheduled(self, call_id, why) -> bool:
        r = self.calls[call_id]
        if r["status"] != "awaiting_approval" or not (r.get("approval") or {}).get("scheduled_for"):
            return False
        r.update(status="not_placed", not_placed_why=why)
        return True

    async def scheduled_for_email(self, email_id) -> list:
        return [cid for cid, c in self.calls.items() if c["status"] == "awaiting_approval" and (c.get("approval") or {}).get("email_id") == email_id]

    async def mark_placed(self, call_id: str, placed, now: datetime) -> None:
        r = self.calls[call_id]
        if getattr(placed, "uncertain", False):   # S-57 · stays 'placing' until Bland's log says
            r.update(bland_http_status=placed.http_status, bland_answer={"uncertain": placed.why, "at": now.isoformat()})
            return
        r.update(status="placed" if placed.placed else "not_placed", bland_call_id=placed.bland_call_id,
                 bland_http_status=placed.http_status, bland_answer=placed.answer, not_placed_why=placed.why,
                 placed_at=now if placed.placed else None)

    async def unresolved(self, older_than: datetime) -> list:
        return [dict(c) for c in self.calls.values() if c["status"] == "placing" and c.get("approved_at") and c["approved_at"] < older_than]

    async def unresolved_to(self, number: str) -> bool:
        return any(c["status"] == "placing" and c["dialled_number"] == number for c in self.calls.values())

    async def resolve(self, call_id: str, bland_call_id: Optional[str], placed_at: Optional[datetime], note: str) -> bool:
        r = self.calls[call_id]
        if r["status"] != "placing":
            return False
        ans = {**(r.get("bland_answer") or {}), "resolved": note}
        if bland_call_id:
            r.update(status="placed", bland_call_id=bland_call_id, placed_at=placed_at, bland_answer=ans)
        else:
            r.update(status="not_placed", not_placed_why=note, bland_answer=ans)
        return True

    async def record_reading(self, call_id: str, reading, details: Any, now: datetime) -> bool:
        r = self.calls[call_id]
        if r["status"] != "placed":
            return False
        r.update(status=reading.state, bland_details=details, outcome=reading.outcome, venue_words=reading.venue_words,
                 reading=reading_json(reading), read_at=now)
        if reading.state == "answered":
            purpose = (r.get("brief") or {}).get("purpose", "book")
            attempt, trip = outcome_effect(purpose, reading.outcome, getattr(reading, "offer", None))
            self.attempts.append({"trip_item_id": r["trip_item_id"], "method": "phone", "status": attempt,
                                  "response_received": reading.venue_words, "observed_by": OBSERVED_BY_CALL})
            if trip:
                self.trip_items[r["trip_item_id"]]["status"] = trip
            if purpose == "book" and reading.outcome == "yes" and getattr(reading, "reference", None):
                self.trip_items[r["trip_item_id"]]["booking_reference"] = reading.reference
        return True

    async def put_cancel_call(self, row: dict, trip_item_id: str) -> str:
        """S-47 · a cancelling call sits on the SAME reservation as the booking it cancels — no new trip item."""
        self.calls[row["call_id"]] = {**{k: v for k, v in row.items() if k not in _TRIP and k != "request"}, "trip_item_id": trip_item_id,
                                      "status": "awaiting_approval"}
        remember_request(None, self.calls[row["call_id"]], row.get("request"))
        return trip_item_id

    async def placed_calls(self) -> list:
        """S-41 G3 · every call Bland accepted and nobody has read yet — across accounts, for the sweeper."""
        return [dict(c) for c in self.calls.values() if c["status"] == "placed"]


_TRIP = ("venue_name", "local_date", "local_time", "local_timezone", "party_size")


def reading_json(r) -> dict:
    return {"state": r.state, "outcome": r.outcome, "quote": r.quote, "reference": getattr(r, "reference", None), "raised": r.raised, "why": r.why,
            "read_by": r.read_by, "bland_status": r.bland_status, "answered_by": r.answered_by, "offer": getattr(r, "offer", None)}


class PostgresCallStore:
    """Shares the booking store's pool, so DATABASE_URL is read in exactly one place."""

    def __init__(self, base: PostgresStore) -> None:
        self._base = base

    async def _run(self, fn):
        import asyncpg
        try:
            return await self._base._run(fn)
        except StorageUnavailable as e:
            raise e.rehint("003_phone_calls.sql") from None
        except asyncpg.exceptions.CheckViolationError as e:
            raise StorageUnavailable("storage_not_provisioned", f"{e} — run backend/booking_signer/sql/003_phone_calls.sql") from None

    async def put_call(self, row: dict, trip_id: Optional[str]) -> str:
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
                    "values ($1, $7, 'pending', $2, ($3::date + $4::time) at time zone $5, $5, $6) returning id",
                    tid, row["venue_name"], row["local_date"], row["local_time"], row["local_timezone"], row["party_size"],
                    row.get("type") or "restaurant")   # S-64 · the object's category; no time on an asking call
                await conn.execute(
                    "insert into booking_calls (call_id, account_id, trip_item_id, venue_key, dialled_number, language, "
                    "guest_name, guest_phone, brief, brief_sha256, read_back_lines, read_back_sha256, status, created_at) "
                    "values ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,'awaiting_approval',$13)",
                    uuid.UUID(row["call_id"]), acct, item_id, row["venue_key"], row["dialled_number"], row["language"],
                    row["guest_name"], row["guest_phone"], row["brief"], row["brief_sha256"], row["read_back_lines"],
                    row["read_back_sha256"], row["created_at"])
                await write_request(conn, item_id, "booking_calls", "call_id", uuid.UUID(row["call_id"]), row.get("request"))
                return str(item_id)
        return await self._run(fn)

    async def confirmations(self, call_id: str, field: str = "confirms_call_id") -> list:
        """Sasha 108 · every confirmation call of this booking call (or, field="cancels_call_id", every cancelling call),
        oldest first."""
        assert field in ("confirms_call_id", "cancels_call_id")
        rows = await self._run(lambda c: c.fetch(
            f"select * from booking_calls where brief->>'{field}' = $1 order by created_at", call_id))
        return [_row(r) for r in rows]

    async def confirming(self, call_id: str) -> Optional[str]:
        """Sasha 108 · the confirmation call placed after this unclear call, if any."""
        r = await self._run(lambda c: c.fetchval(
            "select call_id from booking_calls where brief->>'confirms_call_id' = $1 order by created_at limit 1", call_id))
        return str(r) if r else None

    async def get_call(self, account_id: str, call_id: str) -> Optional[dict]:
        cid = _uuid_or_none(call_id)
        if cid is None:
            return None
        return _row(await self._run(lambda c: c.fetchrow(
            "select * from booking_calls where call_id = $1 and account_id = $2", cid, uuid.UUID(account_id))))

    async def receipt_rows(self, account_id, trip_item_id):
        item_id = _uuid_or_none(trip_item_id)
        if item_id is None:
            return None

        async def fn(conn):
            call = await conn.fetchrow(
                "select * from booking_calls where trip_item_id = $1 and account_id = $2 "
                "and coalesce(brief->>'purpose', 'book') = 'book' "
                # Sasha 109 · the latest call a VENUE answered (a confirmation that reached no one, or never dialled, does
                # not replace the call that spoke to them); else the latest
                "order by (status = 'answered') desc, created_at desc limit 1", item_id, uuid.UUID(account_id))
            if call is None:
                return None
            item = await conn.fetchrow("select * from trip_items where id = $1", item_id)
            # what the venue WROTE: an SMS or WhatsApp to Sasha's number, a voicemail, a reply to her email — verbatim
            inbound = await conn.fetchval("select to_regclass('public.booking_inbound') is not null")   # 016, S-70
            written = await conn.fetch(
                ("select channel, null::text as from_addr, null::text as subject, body_text, recording_url, received_at "
                 "from booking_inbound where trip_item_id = $1 union all " if inbound else "")
                + "select 'email' as channel, r.from_addr, r.subject, r.body_text, null as recording_url, r.received_at "
                "from booking_email_replies r join booking_emails e on e.email_id = r.email_id where e.trip_item_id = $1 "
                "order by received_at", item_id)
            return {"call": _row(call), "item": _row(item) or {}, "written": [_row(w) for w in written]}
        return await self._run(fn)

    async def claim(self, account_id, call_id, approval, now, fresh_after, cap, since, account_cap=None) -> str:
        cid = _uuid_or_none(call_id)
        if cid is None:
            return "unknown"

        async def fn(conn):
            async with conn.transaction():
                # ⚠ serialised: two approvals racing for the last call of the day cannot both win
                await conn.execute("lock table booking_calls in share row exclusive mode")
                r = await conn.fetchrow("select status, created_at, approval from booking_calls where call_id = $1 and account_id = $2",
                                        cid, uuid.UUID(account_id))
                if r is None:
                    return "unknown"
                if r["status"] != "awaiting_approval" or r["approval"]:   # S-66 · a scheduled call is already approved
                    return "taken"
                if r["created_at"] < fresh_after:
                    return "stale"
                n = await conn.fetchval("select count(*) from booking_calls where status = any($1::text[]) and approved_at >= $2",
                                        list(DIALLED), since)
                if n >= cap:
                    return "cap"
                if account_cap is not None and await conn.fetchval(
                        "select count(*) from booking_calls where account_id = $3 and status = any($1::text[]) and approved_at >= $2",
                        list(DIALLED), since, uuid.UUID(account_id)) >= account_cap:
                    return "account_cap"   # S-62 step 2
                await conn.execute("update booking_calls set status = 'placing', approval = $2, approved_at = $3 where call_id = $1",
                                   cid, approval, now)
                return "claimed"
        return await self._run(fn)

    # ── S-66 · a call scheduled for the venue's opening ──
    async def schedule(self, account_id, call_id, approval, now, fresh_after) -> str:
        cid = _uuid_or_none(call_id)
        if cid is None:
            return "unknown"

        async def fn(conn):
            async with conn.transaction():
                r = await conn.fetchrow("select status, created_at, approval from booking_calls where call_id = $1 and account_id = $2 for update",
                                        cid, uuid.UUID(account_id))
                if r is None:
                    return "unknown"
                if r["status"] != "awaiting_approval" or r["approval"]:
                    return "taken"
                if r["created_at"] < fresh_after:
                    return "stale"
                await conn.execute("update booking_calls set approval = $2, approved_at = $3 where call_id = $1", cid, approval, now)
                return "scheduled"
        return await self._run(fn)

    async def link_email(self, call_id, email_id) -> None:
        await self._run(lambda c: c.execute(
            "update booking_calls set approval = approval || jsonb_build_object('email_id', $2::text) where call_id = $1",
            uuid.UUID(call_id), email_id))

    async def due(self, now) -> list:
        rows = await self._run(lambda c: c.fetch(
            "select * from booking_calls where status = 'awaiting_approval' and approval ? 'scheduled_for' "
            "and (approval->>'scheduled_for')::timestamptz <= $1 order by approved_at limit 20", now))
        return [_row(r) for r in rows]

    async def start_scheduled(self, call_id, cap, since, account_cap=None) -> str:
        async def fn(conn):
            async with conn.transaction():
                await conn.execute("lock table booking_calls in share row exclusive mode")
                r = await conn.fetchrow("select status, approval, account_id from booking_calls where call_id = $1", uuid.UUID(call_id))
                if r is None or r["status"] != "awaiting_approval" or not (r["approval"] or {}).get("scheduled_for"):
                    return "taken"
                n = await conn.fetchval("select count(*) from booking_calls where status = any($1::text[]) and approved_at >= $2",
                                        list(DIALLED), since)
                if n >= cap:
                    return "cap"
                if account_cap is not None and await conn.fetchval(
                        "select count(*) from booking_calls where account_id = $3 and status = any($1::text[]) and approved_at >= $2",
                        list(DIALLED), since, r["account_id"]) >= account_cap:
                    return "account_cap"
                await conn.execute("update booking_calls set status = 'placing' where call_id = $1", uuid.UUID(call_id))
                return "claimed"
        return await self._run(fn)

    async def cancel_scheduled(self, call_id, why) -> bool:
        r = await self._run(lambda c: c.fetchval(
            "update booking_calls set status = 'not_placed', not_placed_why = $2 where call_id = $1 and status = 'awaiting_approval' "
            "and approval ? 'scheduled_for' returning call_id", uuid.UUID(call_id), why))
        return r is not None

    async def scheduled_for_email(self, email_id) -> list:
        rows = await self._run(lambda c: c.fetch(
            "select call_id from booking_calls where status = 'awaiting_approval' and approval->>'email_id' = $1", str(email_id)))
        return [str(r["call_id"]) for r in rows]

    async def mark_placed(self, call_id, placed, now) -> None:
        if getattr(placed, "uncertain", False):   # S-57 · stays 'placing' until Bland's log says
            await self._run(lambda c: c.execute(
                "update booking_calls set bland_http_status = $2, bland_answer = $3 where call_id = $1 and status = 'placing'",
                uuid.UUID(call_id), placed.http_status, {"uncertain": placed.why, "at": now.isoformat()}))
            return
        await self._run(lambda c: c.execute(
            "update booking_calls set status = $2, bland_call_id = $3, bland_http_status = $4, bland_answer = $5, "
            "not_placed_why = $6, placed_at = $7 where call_id = $1 and status = 'placing'",
            uuid.UUID(call_id), "placed" if placed.placed else "not_placed", placed.bland_call_id, placed.http_status,
            placed.answer, placed.why, now if placed.placed else None))

    async def put_cancel_call(self, row: dict, trip_item_id: str) -> str:
        """S-47 · a cancelling call sits on the SAME reservation as the booking it cancels — no new trip item."""
        async def fn(conn):
            async with conn.transaction():
                await conn.execute(
                    "insert into booking_calls (call_id, account_id, trip_item_id, venue_key, dialled_number, language, "
                    "guest_name, guest_phone, brief, brief_sha256, read_back_lines, read_back_sha256, status, created_at) "
                    "values ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,'awaiting_approval',$13)",
                    uuid.UUID(row["call_id"]), uuid.UUID(row["account_id"]), uuid.UUID(trip_item_id), row["venue_key"], row["dialled_number"],
                    row["language"], row["guest_name"], row["guest_phone"], row["brief"], row["brief_sha256"], row["read_back_lines"],
                    row["read_back_sha256"], row["created_at"])
                # the reservation keeps its BOOKING request; the cancel call carries its own (flow: cancel)
                await write_request(conn, None, "booking_calls", "call_id", uuid.UUID(row["call_id"]), row.get("request"))
        await self._run(fn)
        return trip_item_id

    async def unresolved(self, older_than) -> list:
        rows = await self._run(lambda c: c.fetch(
            "select * from booking_calls where status = 'placing' and approved_at < $1 order by approved_at limit 20", older_than))
        return [_row(r) for r in rows]

    async def unresolved_to(self, number) -> bool:
        return bool(await self._run(lambda c: c.fetchval(
            "select exists (select 1 from booking_calls where status = 'placing' and dialled_number = $1)", number)))

    async def resolve(self, call_id, bland_call_id, placed_at, note) -> bool:
        r = await self._run(lambda c: c.fetchval(
            "update booking_calls set status = case when $2::text is null then 'not_placed' else 'placed' end, "
            "bland_call_id = $2, placed_at = $3, not_placed_why = case when $2::text is null then $4 else not_placed_why end, "
            "bland_answer = coalesce(bland_answer, '{}'::jsonb) || jsonb_build_object('resolved', $4::text) "
            "where call_id = $1 and status = 'placing' returning call_id",
            uuid.UUID(call_id), bland_call_id, placed_at, note))
        return r is not None

    async def placed_calls(self) -> list:
        """S-41 G3 · every placed, unread call, oldest first — for the sweeper."""
        rows = await self._run(lambda c: c.fetch("select * from booking_calls where status = 'placed' order by placed_at limit 50"))
        return [_row(r) for r in rows]

    async def record_reading(self, call_id, reading, details, now) -> bool:
        async def fn(conn):
            async with conn.transaction():
                row = await conn.fetchrow(
                    "update booking_calls set status = $2, bland_details = $3, outcome = $4, venue_words = $5, reading = $6, "
                    "read_at = $7 where call_id = $1 and status = 'placed' returning trip_item_id, brief",
                    uuid.UUID(call_id), reading.state, details, reading.outcome, reading.venue_words, reading_json(reading), now)
                if row is None:
                    return False   # already read by another poll: never recorded twice
                if reading.state == "answered":
                    purpose = (row["brief"] or {}).get("purpose", "book")
                    attempt, trip = outcome_effect(purpose, reading.outcome, getattr(reading, "offer", None))
                    await conn.execute(
                        "insert into booking_attempts (trip_item_id, method, attempted_at, status, response_received, "
                        "response_at, observed_by) values ($1, 'phone', $2, $3, $4, $2, $5)",
                        row["trip_item_id"], now, attempt, reading.venue_words, OBSERVED_BY_CALL)
                    if trip:
                        # the venue's own name/reference, verbatim — never ours in its place (G4); only a booking sets it
                        await conn.execute("update trip_items set status = $2, booking_reference = coalesce($3, booking_reference), "
                                           "updated_at = now() where id = $1", row["trip_item_id"], trip,
                                           getattr(reading, "reference", None) if purpose == "book" and reading.outcome == "yes" else None)
                return True
        return await self._run(fn)


def cap_window(now: datetime) -> datetime:
    return now - timedelta(hours=24)

