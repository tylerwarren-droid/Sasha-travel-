"""S-33 · the phone rung's routes — included into /api/booking by routes.py (so main.py is not touched).

    POST /api/booking/calls                 particulars → the read-back (nothing is dialled)
    POST /api/booking/calls/{call_id}/place the user said yes → claim → ask Bland → record EXACTLY what Bland answered
    GET  /api/booking/calls/{call_id}       the call as it stands; once Bland says it has finished, read it ONCE

⛔ FOUR THINGS STAND BETWEEN A REQUEST AND A RINGING PHONE, each refusing by name:
  1. SASHA_CALLS_ENABLED=1 on the server (off unless the founder sets it) and BLAND_API_KEY present;
  2. the venue is in calls.call_venues() — server-side — and its number comes from the environment, never the request;
  3. the approval is for THIS call's read-back, within 15 minutes of it being read, and a call row is dialled once;
  4. no more than SASHA_CALLS_PER_DAY calls (default 3) have been dialled in the last 24 hours, across everyone.
⚠ Why 4 exists: nobody signs in (account.py), so these routes are as public as the page that calls them.

⚠ NOTHING HERE RUNS AFTER THE RESPONSE. Placing waits for Bland's answer before replying; reading happens when the
page asks (GET), so there is no background task to be lost on a redeploy.
"""
from __future__ import annotations

import asyncio
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from . import calls as C
from . import ladder_routes
from .account import account_for
from .call_store import PostgresCallStore, cap_window
from .store import AlreadyRecorded, StorageUnavailable, UnknownTrip

log = logging.getLogger("sasha.booking_calls")

router = APIRouter(prefix="/calls", tags=["booking-calls"])

#: How long a read-back stays good for a yes. "Thursday" is only true for a while.
APPROVAL_WINDOW = timedelta(minutes=15)

# ── injectable for tests ──────────────────────────────────────────────────────────────────────
CALL_STORE: Any = None     # set by routes.py to a PostgresCallStore sharing its pool
READER: C.Reader = C.anthropic_reader


async def HTTP(method: str, url: str, headers: dict, json: Optional[dict] = None):
    import httpx
    async with httpx.AsyncClient(timeout=httpx.Timeout(20.0)) as client:
        return await client.request(method, url, headers=headers, json=json)


def NOW() -> datetime:
    return datetime.now(timezone.utc)


def cap() -> int:
    try:
        return max(0, int(os.getenv("SASHA_CALLS_PER_DAY", "3")))
    except ValueError:
        return 3


def _refuse(status: int, rule: str, message: str) -> JSONResponse:
    return JSONResponse({"ok": False, "rule": rule, "message": message}, status_code=status)


async def _json(request: Request) -> Optional[dict]:
    try:
        body = await request.json()
    except Exception:
        return None
    return body if isinstance(body, dict) else None


def status() -> dict:
    """For /api/booking/health: can a call be placed, and to where — never the number itself."""
    venues = {}
    for k, v in C.call_venues().items():
        try:
            C.number_of(v)
            venues[k] = {"number_set": True, "language": v.language}
        except C.CallRefused as e:
            venues[k] = {"number_set": False, "why": e.rule}
    return {"enabled": C.calls_enabled(), "bland_configured": bool(C.bland_key()), "per_day": cap(), "venues": venues}


def _off() -> Optional[JSONResponse]:
    if not C.calls_enabled():
        return _refuse(422, "calls_disabled", "phone calls are off on this server (SASHA_CALLS_ENABLED is not 1); nothing was dialled")
    if not C.bland_key():
        return _refuse(503, "calls_not_configured", "BLAND_API_KEY is not set, so no call can be placed")
    return None


# ── S-41 G3 · the result is read on the SERVER — closing the tab never leaves a call unread ─────────────────
#
# Every minute the sweeper reads each `placed` call from Bland and, once Bland says it has finished, records the reading
# (record_reading refuses a second time, so the page's own GET and the sweeper can never both record it). The state
# lives in the database, so a redeploy loses nothing: the next process's sweeper picks up where this one stopped.
SWEEP_EVERY_S = 60
_sweeper: Optional[asyncio.Task] = None


async def sweep_once() -> int:
    """Read every placed call once. Returns how many were recorded."""
    key = C.bland_key()
    if not key or CALL_STORE is None:
        return 0
    recorded = 0
    for call in await CALL_STORE.placed_calls():
        try:
            details = await C.fetch_call(HTTP, key, call["bland_call_id"])
            r = await C.read_call(details if isinstance(details, dict) else {}, READER, (call.get("brief") or {}).get("purpose", "book"))
            if r.state != "in_progress" and await CALL_STORE.record_reading(call["call_id"], r, details, NOW()):
                recorded += 1
        except Exception as e:  # one call's trouble never stops the others; it is retried next sweep
            log.warning("[booking_calls] sweep could not read call %s: %s: %s", call.get("call_id"), type(e).__name__, e)
    return recorded


async def _sweep_forever() -> None:
    while True:
        try:
            n = await sweep_once()
            if n:
                log.info("[booking_calls] sweep recorded %d finished call(s)", n)
        except Exception as e:
            log.error("[booking_calls] sweep failed: %s: %s", type(e).__name__, e)
        await asyncio.sleep(SWEEP_EVERY_S)


@router.on_event("startup")
async def _start_sweeper() -> None:
    global _sweeper
    if os.getenv("SASHA_CALL_SWEEP", "1") == "1" and _sweeper is None:
        _sweeper = asyncio.create_task(_sweep_forever())


@router.post("")
async def prepare(request: Request):
    """The read-back for a call. ⚠ Refused outright while calls are off: a yes button that cannot dial is a lie."""
    off = _off()
    if off:
        return off
    body = await _json(request)
    if body is None:
        return _refuse(400, "call_malformed", "send the booking as a JSON object")
    account = account_for(request)
    if body.get("cancels_call_id"):
        return await _prepare_cancel(account, str(body["cancels_call_id"]), body)
    if body.get("read_id"):
        # S-36 · the number Magellan READ at the venue — never one in the request
        try:
            venue = await ladder_routes.call_venue_from_read(account, body["read_id"], body.get("fact_index"))
        except C.CallRefused as e:
            return _refuse(422, e.rule, str(e))
        except StorageUnavailable as e:
            return _refuse(503, e.rule, e.detail)
    else:
        venue = C.call_venues().get(body.get("venue"))
        if venue is None:
            return _refuse(422, "venue_not_callable", f"{body.get('venue')!r} is not a venue Sasha may phone")
    now = NOW()
    try:
        p = C.parse_call_particulars(body)
        built = C.build_call(venue, p, now)
    except C.CallRefused as e:
        return _refuse(422, e.rule, str(e))
    if len(built["brief"]["task"]) > 2000:   # Bland's limit; a truncated brief would drop a rule
        return _refuse(422, "brief_too_long", "the call's instructions exceed Bland's 2,000 characters")
    row = {
        "call_id": str(uuid.uuid4()), "account_id": account, "venue_key": venue.key,
        "dialled_number": built["brief"]["number"], "language": built["brief"]["language"],
        "guest_name": p.name, "guest_phone": p.phone,
        "brief": built["brief"], "brief_sha256": built["brief_sha256"],
        "read_back_lines": built["read_back_lines"], "read_back_sha256": built["read_back_sha256"],
        "created_at": now,
        "venue_name": venue.name, "local_date": p.on, "local_time": p.at, "local_timezone": venue.timezone, "party_size": p.party,
    }
    trip_id = body.get("trip_id")
    try:
        item = await CALL_STORE.put_call(row, trip_id if isinstance(trip_id, str) and trip_id else None)
    except UnknownTrip:
        return _refuse(404, "trip_unknown", "no trip with that id belongs to this account; nothing was recorded")
    except StorageUnavailable as e:
        return _refuse(503, e.rule, e.detail)
    return {"call_id": row["call_id"], "trip_item_id": item,
            "read_back": {"lines": row["read_back_lines"], "sha256": row["read_back_sha256"]}}


_LANG_BY_CODE = {lang.code: key for key, lang in C.LANGUAGES.items()}


async def _prepare_cancel(account: str, booking_call_id: str, body: dict):
    """S-45 · the call that cancels a booking Sasha made. EVERYTHING — venue, number, language, day, time, party, name,
    the reference they gave — is read from the booking call itself; the request may name nothing else, so a
    cancellation can never drift onto another venue or another night."""
    extra = set(body) - {"cancels_call_id"}
    if extra:
        return _refuse(422, "cancel_takes_nothing_else", f"a cancellation is prepared from the booking call alone; not {sorted(extra)}")
    try:
        booking = await CALL_STORE.get_call(account, booking_call_id)
    except StorageUnavailable as e:
        return _refuse(503, e.rule, e.detail)
    if booking is None:
        return _refuse(404, "call_unknown", "no call with that id was placed for this account")
    b = booking["brief"] or {}
    if b.get("purpose", "book") != "book" or booking["status"] != "answered" or booking.get("outcome") != "yes":
        return _refuse(422, "nothing_to_cancel", "only a booking call the venue said yes to can be cancelled by phone")
    lang_key = _LANG_BY_CODE.get(b.get("language"))
    if not b.get("timezone") or lang_key is None:
        return _refuse(422, "booking_brief_incomplete", "that booking's call does not record its language and timezone")
    venue = C.CallVenue(key=b["venue_key"], name=b.get("venue_name") or b["venue_key"], number_env="", language=lang_key,
                        timezone=b["timezone"], number=b["number"], source=b.get("number_source"))
    now = NOW()
    try:
        p = C.parse_call_particulars({"date": b["date"], "time": b["time"], "party": b["party"], "name": b["name"], "phone": b.get("phone") or ""})
        built = C.build_call(venue, p, now, purpose="cancel", reference=((booking.get("reading") or {}).get("reference")))
    except C.CallRefused as e:
        return _refuse(422, e.rule, str(e))
    if len(built["brief"]["task"]) > 2000:
        return _refuse(422, "brief_too_long", "the call's instructions exceed Bland's 2,000 characters")
    built["brief"]["cancels_call_id"] = booking_call_id
    built["brief_sha256"] = C._sha256hex(C._canonical(built["brief"]))
    row = {"call_id": str(uuid.uuid4()), "account_id": account, "venue_key": venue.key, "dialled_number": b["number"],
           "language": b["language"], "guest_name": p.name, "guest_phone": p.phone, "brief": built["brief"],
           "brief_sha256": built["brief_sha256"], "read_back_lines": built["read_back_lines"],
           "read_back_sha256": built["read_back_sha256"], "created_at": now}
    try:
        item = await CALL_STORE.put_cancel_call(row, booking["trip_item_id"])
    except StorageUnavailable as e:
        return _refuse(503, e.rule, e.detail)
    return {"call_id": row["call_id"], "trip_item_id": item, "purpose": "cancel",
            "read_back": {"lines": row["read_back_lines"], "sha256": row["read_back_sha256"]}}


@router.post("/{call_id}/place")
async def place(call_id: str, request: Request):
    off = _off()
    if off:
        return off
    body = await _json(request)
    if body is None:
        return _refuse(400, "approval_void", "send {read_back_sha256, approval: {how, said}} as a JSON object")
    account = account_for(request)
    try:
        call = await CALL_STORE.get_call(account, call_id)
    except StorageUnavailable as e:
        return _refuse(503, e.rule, e.detail)
    if call is None:
        return _refuse(404, "call_unknown", "no call with that id was prepared for this account")
    # ⚠ The page must name the read-back it showed; the server holds the lines and their hash.
    if body.get("read_back_sha256") != call["read_back_sha256"]:
        return _refuse(422, "approval_void", "the approval was given to different words from this call's read-back")
    a = body.get("approval") if isinstance(body.get("approval"), dict) else {}
    if a.get("how") not in ("button", "voice") or (a.get("how") == "voice" and not str(a.get("said") or "").strip()):
        return _refuse(422, "approval_void", "an approval is by button, or by voice with the words said")
    brief = call["brief"]
    if C._sha256hex(C._canonical(brief)) != call["brief_sha256"]:
        return _refuse(409, "brief_changed", "the stored brief no longer matches what was read back; nothing was dialled")
    now = NOW()
    approval = {"by": account, "how": a["how"], "said": a.get("said"), "at": now.isoformat(),
                "read_back_sha256": call["read_back_sha256"], "brief_sha256": call["brief_sha256"]}
    try:
        claimed = await CALL_STORE.claim(account, call_id, approval, now, now - APPROVAL_WINDOW, cap(), cap_window(now))
    except StorageUnavailable as e:
        return _refuse(503, e.rule, e.detail)
    if claimed == "taken":
        return _refuse(409, "call_already_placed", "this call was already approved; a second call is a new read-back and a new yes")
    if claimed == "stale":
        return _refuse(422, "read_back_expired", "that read-back is more than 15 minutes old; prepare the call again")
    if claimed == "cap":
        return _refuse(429, "daily_call_limit", f"{cap()} calls have been placed in the last 24 hours, the most this server allows")
    if claimed != "claimed":
        return _refuse(404, "call_unknown", "no call with that id was prepared for this account")

    placed = await C.place_call(HTTP, C.bland_key(), C.bland_payload(brief, call_id))
    try:
        await CALL_STORE.mark_placed(call_id, placed, NOW())
    except (StorageUnavailable, AlreadyRecorded) as e:
        # ⚠ Bland may have queued it and we could not record that. Say so; never pretend either way.
        log.error("[booking_calls] call %s: Bland answered placed=%s (%s) but it could not be recorded: %s",
                  call_id, placed.placed, placed.bland_call_id, e)
        return _refuse(503, getattr(e, "rule", "not_recorded"), f"Bland answered {'placed' if placed.placed else 'not placed'}, but it could not be recorded: {e}")
    if not placed.placed:
        return {"ok": False, "status": "not_placed", "rule": "call_not_placed", "why": placed.why,
                "say": f"I couldn't place the call: {placed.why}"}
    return {"ok": True, "status": "placed", "say": f"Calling {_name(call)} now."}


@router.get("/{call_id}")
async def get_call(call_id: str, request: Request):
    account = account_for(request)
    try:
        call = await CALL_STORE.get_call(account, call_id)
    except StorageUnavailable as e:
        return _refuse(503, e.rule, e.detail)
    if call is None:
        return _refuse(404, "call_unknown", "no call with that id was prepared for this account")
    name = _name(call)
    if call["status"] == "placed":
        # ⚠ Read ONLY when Bland says it has finished; read once (record_reading refuses a second time).
        key = C.bland_key()
        if not key:
            return _refuse(503, "calls_not_configured", "BLAND_API_KEY is not set, so the call cannot be read")
        try:
            details = await C.fetch_call(HTTP, key, call["bland_call_id"])
        except Exception as e:
            return {"call_id": call_id, "status": "placed", "say": f"I'm on the phone to {name} now.",
                    "note": f"Bland's details could not be fetched just now: {type(e).__name__}: {e}"}
        r = await C.read_call(details if isinstance(details, dict) else {}, READER, (call.get("brief") or {}).get("purpose", "book"))
        if r.state == "in_progress":
            return {"call_id": call_id, "status": "placed", "say": C.say_for(name, r), "why": r.why}
        try:
            await CALL_STORE.record_reading(call_id, r, details, NOW())
            call = await CALL_STORE.get_call(account, call_id)
        except StorageUnavailable as e:
            return _refuse(503, e.rule, e.detail)
    return _view(call, name)


def _name(call: dict) -> str:
    v = C.call_venues().get(call["venue_key"])
    return (call.get("brief") or {}).get("venue_name") or (v.name if v else call["venue_key"])


def _view(call: dict, name: str) -> dict:
    reading = call.get("reading") or {}
    out = {"call_id": call["call_id"], "status": call["status"], "read_back": call["read_back_lines"],
           "outcome": call.get("outcome"), "venue_words": call.get("venue_words"),
           "quote": reading.get("quote"), "raised": reading.get("raised") or [], "why": reading.get("why"),
           # ⚠ labelled wherever it is shown: the outcome is a model's reading; their words are verbatim
           "read_by": reading.get("read_by")}
    if call["status"] == "not_placed":
        out["why"] = call.get("not_placed_why")
        out["say"] = f"I couldn't place the call: {call.get('not_placed_why')}"
    elif call["status"] == "placing":
        out["say"] = ("I asked Bland to place the call but never recorded its answer, so I can't tell you whether the "
                      "phone rang. I won't call again on my own.")
    elif call["status"] == "awaiting_approval":
        out["say"] = None
    elif call["status"] in ("answered", "not_reached"):
        r = C.CallReading(state=call["status"], outcome=call.get("outcome"), venue_words=call.get("venue_words") or "",
                          quote=reading.get("quote"), why=reading.get("why") or "")
        out["say"] = C.say_for(name, r, (call.get("brief") or {}).get("purpose", "book"))
    return out
