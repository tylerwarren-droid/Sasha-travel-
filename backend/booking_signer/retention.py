"""S-53 · THE RETENTION JOB — S-51's periods, enforced. Runs daily; every deletion is logged in `retention_log`.

The periods are CONFIG, read from the environment each run, so counsel can change a number without a rebuild:
    RETENTION_BOOKINGS_MONTHS                   24   a Sasha booking and everything recorded for it, counted from its DATE
    RETENTION_BODIES_MONTHS                     12   transcripts and message bodies: call transcripts, the venue's words,
                                                     email reply and confirmation bodies, the text of emails Sasha sent
    RETENTION_CONSENT_YEARS_AFTER_WITHDRAWAL     3   a venue's opt-in records, counted from its WITHDRAWAL
    RETENTION_UNCONFIRMED_REQUEST_DAYS          30   a Work-with-Sasha request whose link was never confirmed (S-55),
                                                     counted from the link's expiry — it was never consent
    RETENTION_ENABLED                            1   anything else turns the job off (it then deletes nothing)

What it never does:
  · ⛔ touch an ACTIVE opt-in: only an opt-in whose latest record is a withdrawal older than the period goes, and then
    the whole chain for that venue, channel and scope (its evidence goes with it — nothing half-kept);
  · delete a trip item that is not Sasha's: only trip items a Sasha booking record points at (a form intent, a call,
    an email, a slot link) — the CTO's own trips are not this job's;
  · delete anything without logging it: if `retention_log` does not exist, the run stops before deleting.

SQL: sql/007_retention_log.sql (the log) and sql/008_venue_optins.sql (the opt-in table the consent rule reads; until it
exists, that rule is skipped and says so).
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, List, Optional

log = logging.getLogger("sasha.retention")

RUN_EVERY_S = 24 * 3600
FIRST_RUN_AFTER_S = 120
_task: Optional[asyncio.Task] = None


@dataclass(frozen=True)
class Periods:
    bookings_months: int
    bodies_months: int
    consent_years_after_withdrawal: int
    unconfirmed_request_days: int = 30


def _int(name: str, default: int) -> int:
    try:
        v = int(os.getenv(name, str(default)).strip())
        return v if v > 0 else default
    except ValueError:
        return default


def periods() -> Periods:
    return Periods(_int("RETENTION_BOOKINGS_MONTHS", 24), _int("RETENTION_BODIES_MONTHS", 12),
                   _int("RETENTION_CONSENT_YEARS_AFTER_WITHDRAWAL", 3), _int("RETENTION_UNCONFIRMED_REQUEST_DAYS", 30))


def enabled() -> bool:
    return os.getenv("RETENTION_ENABLED", "1").strip() == "1"


def months_before(now: datetime, months: int) -> datetime:
    return now - timedelta(days=round(months * 30.4375))


# The trip items this job may touch: those a Sasha booking record points at, whose booking date is past the cutoff.
_SASHA_ITEMS = """
    select t.id from trip_items t
     where t.date_time < $1
       and (exists (select 1 from booking_intents x where x.trip_item_id = t.id)
         or exists (select 1 from booking_calls x where x.trip_item_id = t.id)
         or exists (select 1 from booking_emails x where x.trip_item_id = t.id)
         or exists (select 1 from booking_links x where x.trip_item_id = t.id))
"""

# (rule, table, SQL) — each a statement over `old` (the ids above) or a cutoff, run in ONE transaction per rule.
_BOOKING_STEPS = [
    ("booking_link_confirmations", "delete from booking_link_confirmations where link_id in (select link_id from booking_links where trip_item_id = any($1::uuid[]))"),
    ("booking_links", "delete from booking_links where trip_item_id = any($1::uuid[])"),
    ("booking_email_replies", "delete from booking_email_replies where email_id in (select email_id from booking_emails where trip_item_id = any($1::uuid[]))"),
    ("booking_emails", "delete from booking_emails where trip_item_id = any($1::uuid[])"),
    ("booking_calls", "delete from booking_calls where trip_item_id = any($1::uuid[])"),
    ("booking_attempts", "delete from booking_attempts where trip_item_id = any($1::uuid[])"),
    ("booking_reports", "delete from booking_reports where intent_id in (select intent_id from booking_intents where trip_item_id = any($1::uuid[])) "
                        "or task_digest in (select k.task_digest from booking_tasks k join booking_intents i using (intent_id) where i.trip_item_id = any($1::uuid[]))"),
    ("booking_tasks", "delete from booking_tasks where intent_id in (select intent_id from booking_intents where trip_item_id = any($1::uuid[]))"),
    ("booking_intents", "delete from booking_intents where trip_item_id = any($1::uuid[])"),
    ("trip_items", "delete from trip_items where id = any($1::uuid[])"),
]

_BODY_STEPS = [
    ("booking_calls", "update booking_calls set bland_details = null, venue_words = null, reading = reading - 'quote' - 'raised' "
                      "where coalesce(read_at, created_at) < $1 and (bland_details is not null or venue_words is not null)"),
    ("booking_attempts", "update booking_attempts set response_received = null where attempted_at < $1 and response_received is not null"),
    ("booking_email_replies", "update booking_email_replies set body_text = null where received_at < $1 and body_text is not null"),
    ("booking_email_quarantine", "delete from booking_email_quarantine where received_at < $1"),
    ("booking_link_confirmations", "update booking_link_confirmations set body_text = null where received_at < $1 and body_text is not null"),
    ("booking_emails", "update booking_emails set email = email - 'text' where coalesce(sent_at, created_at) < $1 and email ? 'text'"),
]

# ⛔ Only chains whose LATEST record is a withdrawal older than the cutoff. An active opt-in is never in this set.
_CONSENT_CHAINS = """
    select venue_id, channel, scope from (
        select distinct on (venue_id, channel, scope) venue_id, channel, scope, status, withdrawn_at
          from venue_optins order by venue_id, channel, scope, recorded_at desc, id desc) latest
     where latest.status = 'withdrawn' and latest.withdrawn_at < $1
"""


async def run_once(conn, now: Optional[datetime] = None) -> List[dict]:
    """One pass. Returns what it did (also written to retention_log). `conn` is an asyncpg connection."""
    now = now or datetime.now(timezone.utc)
    if not await conn.fetchval("select to_regclass('public.retention_log') is not null"):
        log.error("[retention] retention_log does not exist — nothing deleted (run sql/007_retention_log.sql)")
        return [{"rule": "all", "table": "retention_log", "rows": 0, "note": "not run: retention_log missing"}]
    p = periods()
    run_id = uuid.uuid4()
    done: List[dict] = []

    async def logged(rule: str, table: str, rows: int, cutoff: datetime, note: Optional[str] = None) -> None:
        done.append({"rule": rule, "table": table, "rows": rows, "cutoff": cutoff.isoformat(), "note": note})
        await conn.execute("insert into retention_log (run_id, ran_at, rule, table_name, rows_affected, cutoff, note) "
                           "values ($1,$2,$3,$4,$5,$6,$7)", run_id, now, rule, table, rows, cutoff, note)
        if rows:
            log.info("[retention] %s: %s %d row(s) older than %s", rule, table, rows, cutoff.date())

    # 1 · bodies (12 months): the text is emptied, the record of what happened stays
    cut = months_before(now, p.bodies_months)
    async with conn.transaction():
        for table, sql in _BODY_STEPS:
            r = await conn.execute(sql, cut)
            await logged("bodies", table, int(r.split()[-1]), cut)

    # 2 · bookings (24 months after the booking's date): the booking and everything recorded for it
    cut = months_before(now, p.bookings_months)
    async with conn.transaction():
        ids = [r["id"] for r in await conn.fetch(_SASHA_ITEMS, cut)]
        for table, sql in _BOOKING_STEPS:
            r = await conn.execute(sql, ids) if ids else "DELETE 0"
            await logged("bookings", table, int(r.split()[-1]), cut)

    # 3 · consent (3 years after withdrawal) — never an active opt-in
    cut = now - timedelta(days=round(p.consent_years_after_withdrawal * 365.25))
    if not await conn.fetchval("select to_regclass('public.venue_optins') is not null"):
        await logged("consent", "venue_optins", 0, cut, "skipped: venue_optins does not exist yet")
    else:
        async with conn.transaction():
            await conn.execute("set local booking.retention = 'on'")   # the append-only trigger lets ONLY this job delete
            chains = await conn.fetch(_CONSENT_CHAINS, cut)
            n = 0
            for c in chains:
                r = await conn.execute("delete from venue_optins where venue_id = $1 and channel = $2 and scope = $3",
                                       c["venue_id"], c["channel"], c["scope"])
                n += int(r.split()[-1])
            await logged("consent", "venue_optins", n, cut, f"{len(chains)} withdrawn chain(s)" if chains else None)

    # 4 · S-55 · page requests never confirmed (never consent): gone 30 days after their link expired. A CONFIRMED
    # request is kept — its link is the venue's way to withdraw — and its fields are already in the opt-in's evidence.
    cut = now - timedelta(days=p.unconfirmed_request_days)
    if not await conn.fetchval("select to_regclass('public.venue_optin_requests') is not null"):
        await logged("consent", "venue_optin_requests", 0, cut, "skipped: venue_optin_requests does not exist yet")
    else:
        async with conn.transaction():
            r = await conn.execute("delete from venue_optin_requests where confirmed_at is null and expires_at < $1", cut)
            # logged under 'consent' (007's rule check allows four rules), told apart by its table and note
            await logged("consent", "venue_optin_requests", int(r.split()[-1]), cut, "page requests never confirmed")
    return done


async def _forever(get_conn) -> None:
    await asyncio.sleep(FIRST_RUN_AFTER_S)
    while True:
        if enabled():
            try:
                conn = await get_conn()
                try:
                    done = await run_once(conn)
                    log.info("[retention] run finished: %s", json.dumps([d for d in done if d.get("rows") or d.get("note")]))
                finally:
                    await conn.close()
            except Exception as e:   # a failed run deletes nothing more and is retried tomorrow
                log.error("[retention] run failed: %s: %s", type(e).__name__, e)
        await asyncio.sleep(RUN_EVERY_S)


async def _connect():
    import asyncpg
    url = os.getenv("DATABASE_URL", "").strip().replace("postgresql+asyncpg://", "postgresql://", 1)
    return await asyncpg.connect(url, statement_cache_size=0)


def start() -> None:
    """Called at app startup (routes.py). Off in tests (SASHA_RETENTION_LOOP=0) and without a database."""
    global _task
    if _task is None and os.getenv("SASHA_RETENTION_LOOP", "1") == "1" and os.getenv("DATABASE_URL", "").strip():
        _task = asyncio.create_task(_forever(_connect))
