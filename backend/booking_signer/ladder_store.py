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
from .store import BOOKINGS_TRIP_TITLE, StorageUnavailable, UnknownTrip, _row, _uuid_or_none, remember_request, write_request

SENT_OR_TRYING = ("sending", "sent")



# ── S-37 · slot links ─────────────────────────────────────────────────────────────────────────
#
# offered ──guest opens──▶ link_sent ──"I booked it"──▶ guest_booked
#                              └──────────────┴──forwarded confirmation naming the venue or platform──▶ confirmed
# ⚠ Only a FORWARDED CONFIRMATION that names the venue or the platform reaches `confirmed`; the guest's word alone is
# `guest_booked`, recorded as theirs. Nothing ever moves back, and silence moves nothing.

LINK_TRIP = {"link_sent": "link_sent", "guest_booked": "guest_booked", "confirmed": "confirmed"}
OBSERVED_BY_LINK = "the platform's confirmation, forwarded by the guest — shown word for word"


class MemoryLinks:
    """Mixed into MemoryLadderStore."""

    async def put_link(self, row, trip_id=None):
        item = str(uuid.uuid4())
        self.trip_items[item] = {"id": item, "status": "pending", "provider_name": row["venue_name"]}
        self.links[row["link_id"]] = {**{k: v for k, v in row.items() if k not in ("venue_name", "request")}, "trip_item_id": item,
                                      "status": "offered", "venue_name": row["venue_name"]}
        remember_request(self.trip_items[item], self.links[row["link_id"]], row.get("request"))
        return item

    async def get_link(self, account_id, link_id):
        l = self.links.get(link_id)
        return dict(l) if l and l["account_id"] == account_id else None

    async def link_exists(self, link_id):
        return link_id in self.links

    async def open_link(self, account_id, link_id, now):
        l = self.links.get(link_id)
        if not l or l["account_id"] != account_id:
            return "unknown"
        if l["status"] == "offered":
            l.update(status="link_sent", opened_at=now)
            self.trip_items[l["trip_item_id"]]["status"] = "link_sent"
        return "ok"

    async def stale_links(self, before):
        """Sasha 131 · one-tap pages the guest hasn't pressed on (offered / opened) since before `before`."""
        return [{"link_id": k, "account_id": l["account_id"], "trip_item_id": l["trip_item_id"], "read_id": str(l["read_id"]),
                 "created_at": l["created_at"], "venue": l["venue_name"], "local_date": l.get("local_date"), "local_time": l.get("local_time"),
                 "local_timezone": l.get("local_timezone"), "party_size": l.get("party_size"), "read_back_lines": l.get("read_back_lines")}
                for k, l in self.links.items() if l["status"] in ("offered", "link_sent") and l["created_at"] < before
                and self.trip_items.get(l["trip_item_id"], {}).get("status") != "cancelled"
                # Sasha 132 · already followed by an email for the same venue: the escalation happened once
                and not any(e.get("account_id") == l["account_id"] and str(e.get("read_id")) == str(l["read_id"])
                            and e.get("created_at") and e["created_at"] > l["created_at"] for e in self.emails.values())]

    async def guest_booked(self, account_id, link_id, said, now):
        l = self.links.get(link_id)
        if not l or l["account_id"] != account_id:
            return "unknown"
        if l["status"] in ("offered", "link_sent"):
            l.update(status="guest_booked", guest_said=said, guest_said_at=now)
            self.trip_items[l["trip_item_id"]]["status"] = "guest_booked"
        return "ok"

    async def add_link_confirmation(self, row):
        if any(c["provider_id"] == row["provider_id"] for c in self.link_confirmations):
            return False
        self.link_confirmations.append(dict(row))
        l = self.links[row["link_id"]]
        if row["counted"] and l["status"] != "confirmed":
            l.update(status="confirmed", confirmed_at=row["received_at"])
            self.trip_items[l["trip_item_id"]]["status"] = "confirmed"
            self.attempts.append({"trip_item_id": l["trip_item_id"], "method": "web_form", "status": "confirmed",
                                  "observed_by": OBSERVED_BY_LINK})
        return True

    async def link_venue(self, link_id):
        l = self.links.get(link_id)
        return (l["venue_name"], l["platform"]) if l else None

    async def confirmations_for(self, link_id):
        return sorted([dict(c) for c in self.link_confirmations if c["link_id"] == link_id], key=lambda c: c["received_at"])


class PostgresLinks:
    """Mixed into PostgresLadderStore."""

    async def _run_links(self, fn):
        try:
            return await self._calls._run(fn)
        except StorageUnavailable as e:
            raise e.rehint("005_slot_links.sql") from None

    async def put_link(self, row, trip_id=None):
        acct = uuid.UUID(row["account_id"])

        async def fn(conn):
            async with conn.transaction():
                tid = await conn.fetchval("select id from trips where owner_id = $1 and title = $2 and status in ('draft','active') "
                                          "order by created_at limit 1", acct, BOOKINGS_TRIP_TITLE)
                if tid is None:
                    tid = await conn.fetchval("insert into trips (owner_id, title) values ($1, $2) returning id", acct, BOOKINGS_TRIP_TITLE)
                item = await conn.fetchval(
                    "insert into trip_items (trip_id, type, status, provider_name, date_time, local_timezone, party_size) "
                    "values ($1, 'restaurant', 'pending', $2, ($3::date + $4::time) at time zone $5, $5, $6) returning id",
                    tid, row["venue_name"], row["local_date"], row["local_time"], row["local_timezone"], row["party_size"])
                await conn.execute(
                    "insert into booking_links (link_id, account_id, trip_item_id, read_id, platform, url, slot_filled, "
                    "read_back_lines, read_back_sha256, status, created_at) values ($1,$2,$3,$4,$5,$6,$7,$8,$9,'offered',$10)",
                    uuid.UUID(row["link_id"]), acct, item, uuid.UUID(row["read_id"]), row["platform"], row["url"],
                    row["slot_filled"], row["read_back_lines"], row["read_back_sha256"], row["created_at"])
                await write_request(conn, item, "booking_links", "link_id", uuid.UUID(row["link_id"]), row.get("request"))
                return str(item)
        return await self._run_links(fn)

    async def get_link(self, account_id, link_id):
        lid = _uuid_or_none(link_id)
        if lid is None:
            return None
        return _row(await self._run_links(lambda c: c.fetchrow(
            "select l.*, t.provider_name as venue_name from booking_links l join trip_items t on t.id = l.trip_item_id "
            "where l.link_id = $1 and l.account_id = $2", lid, uuid.UUID(account_id))))

    async def link_exists(self, link_id):
        lid = _uuid_or_none(link_id)
        return lid is not None and bool(await self._run_links(lambda c: c.fetchval("select 1 from booking_links where link_id = $1", lid)))

    async def _move(self, account_id, link_id, frm, to, extra_sql, *extra):
        lid = _uuid_or_none(link_id)
        if lid is None:
            return "unknown"

        async def fn(conn):
            async with conn.transaction():
                owner = await conn.fetchval("select account_id from booking_links where link_id = $1", lid)
                if owner is None or str(owner) != account_id:
                    return "unknown"
                item = await conn.fetchval(f"update booking_links set status = $2{extra_sql} where link_id = $1 "
                                           f"and status = any($3::text[]) returning trip_item_id", lid, to, list(frm), *extra)
                if item is not None:
                    await conn.execute("update trip_items set status = $2, updated_at = now() where id = $1", item, LINK_TRIP[to])
                return "ok"
        return await self._run_links(fn)

    async def open_link(self, account_id, link_id, now):
        return await self._move(account_id, link_id, ("offered",), "link_sent", ", opened_at = $4", now)

    async def stale_links(self, before):
        rows = await self._run_links(lambda c: c.fetch(
            "select l.link_id, l.account_id, l.trip_item_id, l.read_id, l.created_at, t.provider_name as venue, "
            "(t.date_time at time zone t.local_timezone)::date as local_date, (t.date_time at time zone t.local_timezone)::time as local_time, "
            "t.local_timezone, t.party_size, l.read_back_lines from booking_links l join trip_items t on t.id = l.trip_item_id "
            "where l.status in ('offered','link_sent') and l.created_at < $1 and t.status <> 'cancelled' and t.date_time > now() "
            # Sasha 132 · already followed by an email for the same venue: the escalation happened once
            "and not exists (select 1 from booking_emails e where e.account_id = l.account_id and e.read_id = l.read_id "
            "and e.created_at > l.created_at)", before))
        return [{k: (str(v) if isinstance(v, uuid.UUID) else v) for k, v in dict(r).items()} for r in rows]

    async def guest_booked(self, account_id, link_id, said, now):
        return await self._move(account_id, link_id, ("offered", "link_sent"), "guest_booked",
                                ", guest_said = $4, guest_said_at = $5", said, now)

    async def add_link_confirmation(self, row):
        async def fn(conn):
            async with conn.transaction():
                ok = await conn.fetchval(
                    "insert into booking_link_confirmations (provider_id, link_id, from_addr, subject, body_text, counted, note, received_at) "
                    "values ($1,$2,$3,$4,$5,$6,$7,$8) on conflict (provider_id) do nothing returning provider_id",
                    row["provider_id"], uuid.UUID(row["link_id"]), row["from_addr"], row["subject"], row["body_text"],
                    row["counted"], row["note"], row["received_at"])
                if ok is None:
                    return False
                if row["counted"]:
                    item = await conn.fetchval("update booking_links set status = 'confirmed', confirmed_at = $2 where link_id = $1 "
                                               "and status <> 'confirmed' returning trip_item_id", uuid.UUID(row["link_id"]), row["received_at"])
                    if item is not None:
                        await conn.execute("update trip_items set status = 'confirmed', updated_at = now() where id = $1", item)
                        await conn.execute("insert into booking_attempts (trip_item_id, method, attempted_at, status, response_received, "
                                           "response_at, observed_by) values ($1, 'web_form', $2, 'confirmed', $3, $2, $4)",
                                           item, row["received_at"], row["body_text"], OBSERVED_BY_LINK)
                return True
        return await self._run_links(fn)

    async def link_venue(self, link_id):
        lid = _uuid_or_none(link_id)
        r = await self._run_links(lambda c: c.fetchrow(
            "select t.provider_name, l.platform from booking_links l join trip_items t on t.id = l.trip_item_id where l.link_id = $1", lid))
        return (r["provider_name"], r["platform"]) if r else None

    async def confirmations_for(self, link_id):
        rows = await self._run_links(lambda c: c.fetch(
            "select * from booking_link_confirmations where link_id = $1 order by received_at", uuid.UUID(link_id)))
        return [_row(r) for r in rows]


class MemoryLadderStore(MemoryLinks):
    def __init__(self) -> None:
        self.reads: Dict[str, dict] = {}
        self.emails: Dict[str, dict] = {}
        self.replies: List[dict] = []
        self.quarantined: List[dict] = []
        self.trips: Dict[str, dict] = {}
        self.trip_items: Dict[str, dict] = {}
        self.attempts: List[dict] = []
        self.links: Dict[str, dict] = {}
        self.link_confirmations: List[dict] = []

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
        self.emails[row["email_id"]] = {**{k: v for k, v in row.items() if k not in _TRIP and k != "request"}, "trip_item_id": item, "status": "awaiting_approval"}
        remember_request(self.trip_items[item], self.emails[row["email_id"]], row.get("request"))
        return item

    async def get_email(self, account_id: str, email_id: str) -> Optional[dict]:
        e = self.emails.get(email_id)
        return dict(e) if e and e["account_id"] == account_id else None

    async def claim_email(self, account_id, email_id, approval, now, fresh_after, cap, since, account_cap=None) -> str:
        e = self.emails.get(email_id)
        if not e or e["account_id"] != account_id:
            return "unknown"
        if e["status"] != "awaiting_approval":
            return "taken"
        if e["created_at"] < fresh_after:
            return "stale"
        if sum(1 for x in self.emails.values() if x["status"] in SENT_OR_TRYING and x.get("approved_at") and x["approved_at"] >= since) >= cap:
            return "cap"
        if account_cap is not None and sum(1 for x in self.emails.values() if x["account_id"] == account_id and x["status"] in SENT_OR_TRYING
                                           and x.get("approved_at") and x["approved_at"] >= since) >= account_cap:
            return "account_cap"   # S-62 step 2
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
            item = self.trip_items.get(e["trip_item_id"], {})
            if item.get("status") == "pending":   # as Postgres does: a confirmed reservation is never set back by an email
                item["status"] = "attempting"

    async def email_exists(self, email_id: str) -> bool:
        return email_id in self.emails

    account_emails: Dict[str, str] = {}

    async def account_email(self, account_id: str) -> Optional[str]:
        return self.account_emails.get(account_id)

    async def account_by_email(self, email: str) -> Optional[str]:
        return next((a for a, e in self.account_emails.items() if e.lower() == (email or "").lower()), None)

    # ── Sasha 74 · the follow-up after a call, and the replies that move a reservation ──
    async def put_followup_email(self, row: dict, trip_item_id: str) -> None:
        if row["email_id"] in self.emails:
            raise ValueError("a follow-up with this id already exists")
        self.emails[row["email_id"]] = {**dict(row), "trip_item_id": trip_item_id, "status": "awaiting_approval"}

    async def email_any(self, email_id: str) -> Optional[dict]:
        e = self.emails.get(email_id)
        return dict(e) if e else None

    async def email_for_sender(self, addr: str) -> Optional[str]:
        sent = [(e.get("sent_at") or e["created_at"], k) for k, e in self.emails.items()
                if e["status"] == "sent" and str(e["email"].get("to", "")).lower() == addr.lower()]
        return max(sent)[1] if sent else None

    async def request_of_email(self, email_id: str) -> Optional[dict]:
        e = self.emails.get(email_id)
        return (self.trip_items.get(e["trip_item_id"]) or {}).get("request") if e else None

    async def reply_outcome(self, email_id: str, trip_status: str, attempt_status: str, text: str, now: datetime) -> None:
        e = self.emails[email_id]
        self.trip_items[e["trip_item_id"]]["status"] = trip_status
        self.attempts.append({"trip_item_id": e["trip_item_id"], "method": "email", "status": attempt_status, "response_received": text})

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

    # ── Sasha 76 · a reply whose words could not be fetched is fetched again, never left unread ──
    async def unread_replies(self) -> List[dict]:
        return [dict(r) for r in self.replies if r.get("body_text") is None and "could not be fetched" in str(r.get("note") or "")]

    async def set_reply_text(self, provider_id: str, text: Optional[str], note: Optional[str]) -> None:
        for r in self.replies:
            if r["provider_id"] == provider_id:
                r.update(body_text=text, note=note)


_TRIP = ("venue_name",)


class PostgresLadderStore(PostgresLinks):
    def __init__(self, base) -> None:
        self._base = base
        self._calls = PostgresCallStore(base)

    async def _run(self, fn):
        try:
            return await self._calls._run(fn)
        except StorageUnavailable as e:
            raise e.rehint("004_ladder.sql") from None

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
                await write_request(conn, item, "booking_emails", "email_id", uuid.UUID(row["email_id"]), row.get("request"))
                return str(item)
        return await self._run(fn)

    async def get_email(self, account_id, email_id):
        eid = _uuid_or_none(email_id)
        if eid is None:
            return None
        return _row(await self._run(lambda c: c.fetchrow(
            "select * from booking_emails where email_id = $1 and account_id = $2", eid, uuid.UUID(account_id))))

    async def claim_email(self, account_id, email_id, approval, now, fresh_after, cap, since, account_cap=None):
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
                if account_cap is not None and await conn.fetchval(
                        "select count(*) from booking_emails where account_id = $3 and status = any($1::text[]) and approved_at >= $2",
                        list(SENT_OR_TRYING), since, uuid.UUID(account_id)) >= account_cap:
                    return "account_cap"   # S-62 step 2
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

    # ── Sasha 74 · the follow-up after a call, and the replies that move a reservation ──
    async def put_followup_email(self, row, trip_item_id):
        """On the call's OWN reservation (no new trip item). A second insert of the same id fails: never twice."""
        await self._run(lambda c: c.execute(
            "insert into booking_emails (email_id, account_id, trip_item_id, read_id, email, email_sha256, read_back_lines, "
            "read_back_sha256, status, created_at) values ($1,$2,$3,$4,$5,$6,$7,$8,'awaiting_approval',$9)",
            uuid.UUID(row["email_id"]), uuid.UUID(row["account_id"]), uuid.UUID(trip_item_id), uuid.UUID(row["read_id"]), row["email"],
            row["email_sha256"], row["read_back_lines"], row["read_back_sha256"], row["created_at"]))

    async def account_by_email(self, email):
        """Sasha 118 · the account whose verified sign-in address this is (a guest forwarding a confirmation)."""
        r = await self._run(lambda c: c.fetchval("select id from auth.users where lower(email) = lower($1) and email_confirmed_at is not null", email))
        return str(r) if r else None

    async def account_email(self, account_id):
        """The account's own address in Supabase Auth — verified by its magic link. None for the demo account."""
        aid = _uuid_or_none(account_id)
        return None if aid is None else await self._run(lambda c: c.fetchval("select email from auth.users where id = $1", aid))

    async def email_any(self, email_id):
        eid = _uuid_or_none(email_id)
        return None if eid is None else _row(await self._run(lambda c: c.fetchrow("select * from booking_emails where email_id = $1", eid)))

    async def email_for_sender(self, addr):
        v = await self._run(lambda c: c.fetchval(
            "select email_id from booking_emails where status = 'sent' and lower(email->>'to') = lower($1) "
            "order by coalesce(sent_at, created_at) desc limit 1", addr))
        return str(v) if v else None

    async def request_of_email(self, email_id):
        eid = _uuid_or_none(email_id)
        return None if eid is None else await self._run(lambda c: c.fetchval(
            "select t.request from trip_items t join booking_emails e on e.trip_item_id = t.id where e.email_id = $1", eid))

    async def reply_outcome(self, email_id, trip_status, attempt_status, text, now):
        async def fn(conn):
            async with conn.transaction():
                item = await conn.fetchval("select trip_item_id from booking_emails where email_id = $1", uuid.UUID(email_id))
                if item is None:
                    return
                await conn.execute("update trip_items set status = $2, updated_at = now() where id = $1", item, trip_status)
                await conn.execute("insert into booking_attempts (trip_item_id, method, attempted_at, status, response_received, response_at, observed_by) "
                                   "values ($1, 'email', $2, $3, $4, $2, 'their email reply, read with the field checks (Sasha 74)')",
                                   item, now, attempt_status, text[:4000])
        await self._run(fn)

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

    async def unread_replies(self):
        rows = await self._run(lambda c: c.fetch(
            "select * from booking_email_replies where body_text is null and note like '%could not be fetched%' "
            "and received_at > now() - interval '7 days' order by received_at limit 20"))
        return [_row(r) for r in rows]

    async def set_reply_text(self, provider_id, text, note):
        await self._run(lambda c: c.execute("update booking_email_replies set body_text = $2, note = $3 where provider_id = $1",
                                            provider_id, text, note))

