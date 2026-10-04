"""Sasha 144 · THE CALL AND BOOKING LOG — the founder's one place to answer a venue's dispute (founder only).

  · every call: the venue, when, its outcome, the venue's own words, Bland's call id — and Bland's own record of it
    (transcript; a recording only where one was made: Sasha's calls are placed with record: false, and the log says so);
  · every booking: its status, the venue's reference, Sasha's K-reference, whether the guest's receipt went, its
    calendar event;
  · TEST calls (the test line) are in it like every call, marked as tests (sql/032).

Read from records that already exist; a fact the records don't hold is said ("not recorded"), never filled in.
Also here: placing a test-line call that is LOGGED (the only way a test call is placed — a script that called Bland
directly left the 4 Oct call out of every log), and importing test-line calls that Bland has and our log doesn't.
"""
from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

log = logging.getLogger("booking_signer.ops_log")
router = APIRouter(prefix="/ops", tags=["booking-ops"])
NOW = lambda: datetime.now(timezone.utc)   # noqa: E731
NOT_RECORDED = "not recorded"
NO_RECORDING = "no recording — Sasha's calls are placed with record: false"


def _refuse(status: int, rule: str, message: str) -> JSONResponse:
    return JSONResponse({"ok": False, "rule": rule, "message": message}, status_code=status)


# ── the log ─────────────────────────────────────────────────────────────────────────────────────────────────────────

CALLS_SQL = (
    # to_jsonb(c): the row as it is, whichever of 032's columns exist yet
    "select to_jsonb(c) - 'brief' - 'read_back_lines' - 'bland_answer' as c, "
    "c.brief->>'venue_name' as brief_venue, c.brief->>'own_reference' as k_ref, coalesce(c.brief->>'purpose', 'book') as purpose, "
    "c.bland_details->>'concatenated_transcript' as transcript, c.bland_details->>'recording_url' as recording_url, "
    "c.bland_details->>'price' as price, c.bland_details->>'call_length' as minutes, "
    "t.provider_name, t.status as booking_status "
    "from booking_calls c left join trip_items t on t.id = c.trip_item_id "
    "where c.created_at >= $1 order by c.created_at desc limit 500")

BOOKINGS_SQL = (
    "select t.id, p.owner_id as account_id, t.type, t.status, t.provider_name, t.booking_reference, t.date_time, t.local_timezone, "
    "t.party_size, t.created_at, "
    "(select z.brief->>'own_reference' from booking_calls z where z.trip_item_id = t.id and z.brief ? 'own_reference' "
    " order by z.created_at desc limit 1) as k_call, "
    "(select substring(z.email::text from 'K-[A-Z0-9]{4}') from booking_emails z where z.trip_item_id = t.id and z.sent_at is not null "
    " order by z.created_at desc limit 1) as k_email, "
    "(select count(*) from booking_calls z where z.trip_item_id = t.id) as calls, "
    "(select count(*) from booking_emails z where z.trip_item_id = t.id and z.sent_at is not null) as emails, "
    "(select count(*) from booking_forms z where z.trip_item_id = t.id and z.sent_at is not null) as forms, "
    "(select count(*) from booking_links z where z.trip_item_id = t.id) as links, "
    "(select jsonb_build_object('event_id', g.google_event_id, 'status', g.synced_status, 'at', g.synced_at) "
    " from booking_calendar_events g where g.trip_item_id = t.id limit 1) as calendar, "
    "(select jsonb_build_object('syncs', count(*), 'last', max(o.done_at)) from calendar_outbox o where o.trip_item_id = t.id) as cal_history "
    "from trip_items t join trips p on p.id = t.trip_id "
    "where t.created_at >= $1 and t.status <> 'pending' order by t.created_at desc limit 500")

RECEIPTS_SQL = ("select to_regclass('public.booking_receipts_sent') is not null as there")
RECEIPTS_ROWS = ("select trip_item_id, call_id, kind, venue, route, outcome, provider_id, sent_at from booking_receipts_sent "
                 "where sent_at >= $1 order by sent_at")


def call_view(r: dict) -> dict:
    """One call row as the log shows it — every field from the record, or said to be missing."""
    c = r["c"] if isinstance(r.get("c"), dict) else {}
    is_test = bool(c.get("is_test")) or c.get("venue_key") == "test-line"
    venue = "the Sasha test line" if is_test and not r.get("brief_venue") else (r.get("brief_venue") or r.get("provider_name") or c.get("venue_key"))
    return {"call_id": c.get("call_id"), "account_id": c.get("account_id"), "trip_item_id": c.get("trip_item_id"), "test": is_test,
            "venue": venue, "purpose": r.get("purpose"), "language": c.get("language"), "created_at": c.get("created_at"),
            "placed_at": c.get("placed_at"), "status": c.get("status"), "outcome": c.get("outcome"),
            "venue_words": c.get("venue_words"), "not_placed_why": c.get("not_placed_why"), "k_ref": r.get("k_ref"),
            "booking_status": r.get("booking_status"), "bland_call_id": c.get("bland_call_id"),
            "minutes": _num(r.get("minutes")), "price_usd": _num(r.get("price")),
            "transcript": r.get("transcript"),
            "recording": r.get("recording_url") or (NO_RECORDING if c.get("bland_call_id") else None)}


def _num(v: Any) -> Optional[float]:
    try:
        return round(float(v), 4) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def booking_view(r: dict, receipts: Optional[List[dict]]) -> dict:
    mine = [x for x in receipts or [] if str(x.get("trip_item_id") or "") == str(r["id"])]
    routes = [k for k in ("calls", "emails", "forms", "links") if r.get(k)]
    local = None
    if r.get("date_time") is not None:
        try:
            from zoneinfo import ZoneInfo
            local = r["date_time"].astimezone(ZoneInfo(r.get("local_timezone") or "UTC")).strftime("%Y-%m-%d %H:%M")
        except Exception:
            local = r["date_time"].isoformat()
    cal = r.get("calendar") if isinstance(r.get("calendar"), dict) else None
    return {"id": str(r["id"]), "account_id": str(r.get("account_id") or ""), "type": r.get("type"), "status": r.get("status"),
            "venue": r.get("provider_name"), "when_local": local, "timezone": r.get("local_timezone"), "party": r.get("party_size"),
            "venue_reference": r.get("booking_reference"), "k_ref": r.get("k_call") or r.get("k_email"),
            "routes": {k: r[k] for k in routes}, "created_at": r.get("created_at"),
            "receipt": (NOT_RECORDED + " (receipts are recorded from 4 Oct 2026, sql/032)") if receipts is None else
                       ([{"outcome": x["outcome"], "route": x["route"], "kind": x["kind"], "at": x["sent_at"]} for x in mine] or "none sent"),
            "calendar": ({"event_id": cal.get("event_id"), "status": cal.get("status"), "at": cal.get("at")} if cal else _no_event(r))}


def _no_event(r: dict) -> str:
    """No event now — and whether there ever was one: a cancelled booking's event is removed from the calendar."""
    h = r.get("cal_history") if isinstance(r.get("cal_history"), dict) else {}
    n = int(h.get("syncs") or 0)
    if not n:
        return "no calendar event"
    last = str(h.get("last") or "")[:16].replace("T", " ")
    gone = " — removed when it was cancelled" if r.get("status") in ("cancelled", "declined") else ""
    return f"no event now{gone}; synced {n}× (last {last or 'not done'} UTC)"


def matches(row: dict, q: str) -> bool:
    q = (q or "").strip().lower()
    return not q or any(q in str(v).lower() for v in row.values() if v is not None)


def assemble(calls: List[dict], bookings: List[dict], receipts: Optional[List[dict]], *, q: str = "", kind: str = "all",
             tests: str = "include", status: str = "") -> dict:
    cv = [call_view(r) for r in calls] if kind in ("all", "calls") else []
    if tests == "exclude":
        cv = [c for c in cv if not c["test"]]
    elif tests == "only":
        cv = [c for c in cv if c["test"]]
    bv = [booking_view(r, receipts) for r in bookings] if kind in ("all", "bookings") and tests != "only" else []
    if status:
        cv = [c for c in cv if status in (c.get("status"), c.get("outcome"), c.get("booking_status"))]
        bv = [b for b in bv if b.get("status") == status]
    return {"calls": [c for c in cv if matches(c, q)], "bookings": [b for b in bv if matches(b, q)],
            "receipts_recorded": receipts is not None}


async def _fetch(since: datetime) -> tuple:
    from . import ladder_routes as LR

    async def fn(conn):
        calls = [dict(r) for r in await conn.fetch(CALLS_SQL, since)]
        bookings = [dict(r) for r in await conn.fetch(BOOKINGS_SQL, since)]
        there = await conn.fetchval(RECEIPTS_SQL)
        receipts = [dict(r) for r in await conn.fetch(RECEIPTS_ROWS, since)] if there else None
        return calls, bookings, receipts
    calls, bookings, receipts = await LR.LADDER_STORE._run(fn)
    import json
    for r in calls:   # asyncpg hands jsonb back as text
        if isinstance(r.get("c"), str):
            r["c"] = json.loads(r["c"])
    for r in bookings:
        for k in ("calendar", "cal_history"):
            if isinstance(r.get(k), str):
                r[k] = json.loads(r[k])
    return calls, bookings, receipts


@router.get("/log")
async def ops_log(request: Request, q: str = "", kind: str = "all", tests: str = "include", status: str = "", days: int = 60):
    from .ops import founder_only
    from .store import StorageUnavailable
    no = founder_only(request)
    if no:
        return no
    since = NOW() - timedelta(days=max(1, min(int(days or 60), 730)))
    try:
        calls, bookings, receipts = await _fetch(since)
    except StorageUnavailable as e:
        return _refuse(503, e.rule, e.detail)
    out = assemble(calls, bookings, receipts, q=q, kind=kind if kind in ("all", "calls", "bookings") else "all",
                   tests=tests if tests in ("include", "exclude", "only") else "include", status=status)
    return {"ok": True, "since": since.isoformat(), **out}


@router.get("/log/bland/{bland_call_id}")
async def bland_record(bland_call_id: str, request: Request):
    """Bland's OWN record of one call, read now: its transcript and, where one exists, its recording."""
    from . import calls as C, call_routes as CRT
    from .ops import founder_only
    no = founder_only(request)
    if no:
        return no
    key = C.bland_key()
    if not key:
        return _refuse(503, "bland_not_configured", "BLAND_API_KEY is not set on this server")
    try:
        d = await C.fetch_call(CRT.HTTP, key, bland_call_id)
    except Exception as e:
        return _refuse(502, "bland_unavailable", f"Bland's record could not be read: {e}")
    d = d if isinstance(d, dict) else {}
    turns = [{"who": "Sasha" if t.get("user") == "assistant" else ("the line" if t.get("user") == "user" else t.get("user")),
              "text": t.get("text")} for t in d.get("transcripts") or [] if isinstance(t, dict)]
    return {"ok": True, "bland_call_id": bland_call_id, "status": d.get("status"), "answered_by": d.get("answered_by"),
            "minutes": d.get("call_length"), "created_at": d.get("created_at"), "price_usd": d.get("price"),
            "recording": d.get("recording_url") or NO_RECORDING, "transcript": turns}


# ── a TEST-LINE call, logged ─────────────────────────────────────────────────────────────────────────────────────

async def place_test_call(account: str, language: str = "en", minutes: int = 1) -> dict:
    """The one way to place a test-line call: written to booking_calls (is_test) FIRST, then placed, then Bland's answer
    recorded — the sweeper reads its outcome like any call. Never a venue, never a booking, nothing sent to a guest."""
    from . import calls as C, call_routes as CRT, places_terms as PT
    venue = C.test_line()
    venue = C.CallVenue(**{**venue.__dict__, "language": language or venue.language})
    p = C.parse_call_particulars({"date": (NOW() + timedelta(days=1)).date().isoformat(), "time": "21:00", "party": 2,
                                  "name": "Tyler Warren"})
    built = C.build_call(venue, p, NOW().astimezone())
    number = built["brief"]["number"]
    lines = [ln.replace(number, "⟨the test line's number⟩") for ln in built["read_back_lines"]]   # the founder's mobile: no digits stored
    row = {"call_id": str(uuid.uuid4()), "account_id": account, "venue_key": "test-line",
           "dialled_number": PT.number_key(number),   # the founder's own mobile: kept as its hash, never its digits
           "language": built["brief"]["language"], "guest_name": "Tyler Warren", "guest_phone": None,
           "brief": {**built["brief"], "number": None, "test": True}, "brief_sha256": built["brief_sha256"],
           "read_back_lines": lines, "read_back_sha256": C._sha256hex("\n".join(lines))}
    approval = {"by": account, "how": "ops_test_call", "at": NOW().isoformat(), "max_minutes": minutes}
    await CRT.CALL_STORE.put_test_call(row, approval, NOW())
    payload = {**C.bland_payload(built["brief"], row["call_id"]), "max_duration": max(1, min(int(minutes or 1), 3))}
    placed = await C.place_call(CRT.HTTP, C.bland_key(), payload)
    await CRT.CALL_STORE.mark_placed(row["call_id"], placed, NOW())
    return {"call_id": row["call_id"], "placed": placed.placed, "bland_call_id": placed.bland_call_id, "why": placed.why,
            "opening": built["brief"].get("first_sentence")}


@router.post("/calls/test")
async def test_call(request: Request):
    from .account import account_for
    from .ops import founder_only
    from .store import StorageUnavailable
    no = founder_only(request)
    if no:
        return no
    try:
        body = await request.json()
    except Exception:
        body = {}
    try:
        out = await place_test_call(account_for(request), str((body or {}).get("language") or "en"), int((body or {}).get("minutes") or 1))
    except StorageUnavailable as e:
        return _refuse(503, e.rule, f"{e.detail}. No call was placed.")
    except Exception as e:
        return _refuse(422, "test_call_refused", f"{type(e).__name__}: {e}. No call was placed.")
    return {"ok": True, **out}


# ── test-line calls Bland has and our log doesn't ────────────────────────────────────────────────────────────────

def missing(bland_calls: List[dict], logged_ids: set, test_number: Optional[str]) -> Dict[str, List[dict]]:
    """→ {test: Bland calls to the test line not in our log, other: Bland calls to any other number not in our log}."""
    norm = lambda n: "".join(ch for ch in str(n or "") if ch.isdigit())   # noqa: E731
    out: Dict[str, List[dict]] = {"test": [], "other": []}
    for b in bland_calls:
        cid = b.get("call_id") or b.get("c_id")
        if not cid or cid in logged_ids:
            continue
        (out["test"] if test_number and norm(b.get("to")) == norm(test_number) else out["other"]).append(b)
    return out


@router.post("/calls/import-bland")
async def import_bland(request: Request):
    """Every test-line call Bland placed that our log lacks, written to booking_calls as a test (status 'placed': the
    sweeper then reads Bland's outcome into it like any call). A call to any other number is LISTED, never invented."""
    from . import calls as C, call_routes as CRT, places_terms as PT
    from .account import account_for
    from .ops import founder_only
    from .store import StorageUnavailable
    no = founder_only(request)
    if no:
        return no
    key = C.bland_key()
    if not key:
        return _refuse(503, "bland_not_configured", "BLAND_API_KEY is not set on this server")
    r = await CRT.HTTP("GET", f"{C.BLAND_CALLS_URL}?limit=200", headers={"authorization": key})
    if r.status_code != 200:
        return _refuse(502, "bland_unavailable", f"Bland answered HTTP {r.status_code}")
    body = r.json()
    bland = body.get("calls") if isinstance(body, dict) else body
    bland = [b for b in bland or [] if isinstance(b, dict)]
    from . import ladder_routes as LR
    rows = await LR.LADDER_STORE._run(lambda c: c.fetch("select bland_call_id from booking_calls where bland_call_id is not null"))
    logged = {str(x["bland_call_id"]) for x in rows}
    test_number = os.getenv("SASHA_TEST_CALL_NUMBER", "").strip() or None
    found = missing(bland, logged, test_number)
    account, imported = account_for(request), []
    for b in found["test"]:
        cid = b.get("call_id") or b.get("c_id")
        made = b.get("created_at") or NOW().isoformat()
        try:
            at = datetime.fromisoformat(str(made).replace("Z", "+00:00"))
        except ValueError:
            at = NOW()
        brief = {"test": True, "imported_from_bland": True, "venue_name": "the Sasha test line", "purpose": "test",
                 "first_sentence": None, "note": "placed outside the app (a script); imported from Bland's own log on " + NOW().date().isoformat()}
        row = {"call_id": str(uuid.uuid4()), "account_id": account, "venue_key": "test-line", "dialled_number": PT.number_key(test_number),
               "language": str(b.get("language") or "en")[:8], "guest_name": "Tyler Warren", "guest_phone": None, "brief": brief,
               "brief_sha256": C._sha256hex(C._canonical(brief)), "read_back_lines": [], "read_back_sha256": C._sha256hex("")}
        try:
            await CRT.CALL_STORE.put_test_call(row, {"by": account, "how": "imported_from_bland", "at": NOW().isoformat()}, at)
            await CRT.CALL_STORE.mark_placed(row["call_id"], C.Placed(True, cid, 200, {"imported": True}, None), at)
        except StorageUnavailable as e:
            return _refuse(503, e.rule, f"{e.detail}. Nothing was imported.")
        imported.append({"bland_call_id": cid, "at": at.isoformat()})
    return {"ok": True, "imported_test_calls": imported,
            "not_in_our_log_other_numbers": [{"bland_call_id": b.get("call_id") or b.get("c_id"), "at": b.get("created_at")} for b in found["other"]],
            "bland_calls_seen": len(bland)}


__all__ = ["router", "assemble", "call_view", "booking_view", "missing", "place_test_call"]
