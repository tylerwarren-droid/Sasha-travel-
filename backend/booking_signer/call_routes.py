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
import dataclasses
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from . import calls as C
from . import hours as H
from . import places_terms as PT
from . import render as R
from . import reservation as RS
from . import ladder_routes
from . import stop as S
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
    async with httpx.AsyncClient(timeout=httpx.Timeout(60.0)) as client:   # S-57 · Bland took over 20 s on 30 Sept
        return await client.request(method, url, headers=headers, json=json)


def NOW() -> datetime:
    return datetime.now(timezone.utc)


def cap() -> int:
    try:
        return max(0, int(os.getenv("SASHA_CALLS_PER_DAY", "3")))
    except ValueError:
        return 3


def account_cap() -> int:
    """S-62 step 2 · calls per ACCOUNT per 24 h, as well as the server's cap (SASHA_CALLS_PER_ACCOUNT_PER_DAY, default 10)."""
    try:
        return max(0, int(os.getenv("SASHA_CALLS_PER_ACCOUNT_PER_DAY", "10")))
    except ValueError:
        return 10


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
    return {"enabled": C.calls_enabled(), "bland_configured": bool(C.bland_key()), "per_day": cap(), "per_account_per_day": account_cap(), "venues": venues}


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


RESOLVE_AFTER = timedelta(seconds=90)    # S-57 · longer than the 60 s the request itself may take
GIVE_UP_AFTER = timedelta(minutes=10)    # no call in Bland's log by then: it was not placed


async def sweep_once() -> int:
    """Read every placed call once. Returns how many were recorded."""
    key = C.bland_key()
    if not key or CALL_STORE is None:
        return 0
    recorded = 0
    try:
        await place_due()   # S-66 · scheduled calls whose venue has now opened
    except Exception as e:
        log.warning("[booking_calls] could not place a scheduled call: %s: %s", type(e).__name__, e)
    # S-57 · first, every call whose placing went unanswered: Bland's own log says whether it dialled
    now = NOW()
    for call in await CALL_STORE.unresolved(now - RESOLVE_AFTER):
        try:
            found = await C.calls_in_log(HTTP, key, call["dialled_number"], call["approved_at"])
            if found:
                b = found[0]
                await CALL_STORE.resolve(call["call_id"], b["call_id"], b["_created"], f"found in Bland's call log as {b['call_id']}")
                log.warning("[booking_calls] call %s: its placing went unanswered, but Bland's log has it as %s", call["call_id"], b["call_id"])
            elif call["approved_at"] < now - GIVE_UP_AFTER:
                await CALL_STORE.resolve(call["call_id"], None, None,
                                         "Bland's call log has no call to this venue's number in the "
                                         f"{int(GIVE_UP_AFTER.total_seconds() // 60)} minutes after the request went unanswered")
        except Exception as e:
            log.warning("[booking_calls] could not check Bland's log for call %s: %s: %s", call.get("call_id"), type(e).__name__, e)
    for call in await CALL_STORE.placed_calls():
        try:
            details = await C.fetch_call(HTTP, key, call["bland_call_id"])
            r = await C.read_call(details if isinstance(details, dict) else {}, READER, (call.get("brief") or {}).get("purpose", "book"),
                                  call.get("brief"))
            if r.state != "in_progress" and isinstance(details, dict):
                # S-56 · a venue that said stop on the call: recorded BEFORE the reading, so a failure retries both
                await S.on_venue_words((call.get("brief") or {}).get("venue_ids"), "phone", call["dialled_number"],
                                       "\n".join(C.venue_turns(details)),
                                       {"call_id": str(call["call_id"]), "bland_call_id": call.get("bland_call_id")}, NOW(), spoken=True)
            if r.state != "in_progress" and await CALL_STORE.record_reading(call["call_id"], r, PT.scrub_bland(details, call.get("brief")), NOW()):
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
    refused = await ladder_routes._optin_refusal(venue.venue_ids, "phone")
    if refused:
        return refused
    now = NOW()
    if body.get("reservation") is not None:
        return await _prepare_from_object(account, venue, body, now)
    try:
        p = C.parse_call_particulars(body)
        built = C.build_call(venue, p, now)
    except C.CallRefused as e:
        return _refuse(422, e.rule, str(e))
    if len(built["brief"]["task"]) > 2000:   # Bland's limit; a truncated brief would drop a rule
        return _refuse(422, "brief_too_long", "the call's instructions exceed Bland's 2,000 characters")
    try:
        built = _with_hours(built, await _read_of(account, built["brief"]), venue.timezone, now)
        built = PT.seal_call(built, venue)   # Sasha 64 · a listing number: dialled, never stored or shown
    except StorageUnavailable as e:
        return _refuse(503, e.rule, e.detail)
    except PT.ListingUnavailable as e:
        return _refuse(422, e.rule, str(e))
    row = {
        # S-64 step 3 · the reservation/1 object, written alongside the old columns
        "request": RS.try_from_particulars(p, account_id=account, venue_name=venue.name, timezone=venue.timezone,
                                           lang=built["brief"]["language"], venue_ids=venue.venue_ids or (),
                                           read_id=str(body["read_id"]) if body.get("read_id") else None),
        "call_id": str(uuid.uuid4()), "account_id": account, "venue_key": venue.key,
        "dialled_number": built["dialled_number"], "language": built["brief"]["language"],
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


async def _read_of(account: str, brief: Mapping[str, Any]) -> Optional[dict]:
    """The venue read a call's number came from ("read:<id>"), or None (the test line)."""
    key = str((brief or {}).get("venue_key") or "")
    if not key.startswith("read:"):
        return None
    row = await ladder_routes.LADDER_STORE.get_read(account, key[5:])
    return await PT.hydrate_read(HTTP, row["read"], NOW()) if row else None   # Sasha 64 · the listing's hours, re-read


def _with_hours(built: dict, read: Optional[dict], timezone: str, now) -> dict:
    """S-66 · the read-back says what happens if they are closed when the guest says yes — the yes covers that call."""
    if not read:
        return built
    line = H.read_back_line(H.status(read, now, timezone), email_now=False)
    if not line:
        return built
    lines = list(built["read_back_lines"])
    lines.insert(len(lines) - 1, line)
    return {**built, "read_back_lines": lines, "read_back_sha256": C._sha256hex("\n".join(lines))}


async def _cancel_from_object(account: str, booking: dict, b: dict, venue: C.CallVenue):
    refused = await ladder_routes._optin_refusal(venue.venue_ids, "phone")
    if refused:
        return refused
    now = NOW()
    try:
        built = R.cancel_for(b, venue, now, (booking.get("reading") or {}).get("reference"))
    except (RS.ReservationRefused, C.CallRefused) as e:
        return _refuse(422, getattr(e, "rule", "cancel_invalid"), str(e))
    built["brief"]["cancels_call_id"] = booking["call_id"]
    built = PT.seal_call(built, venue)
    row = {"call_id": str(uuid.uuid4()), "account_id": account, "venue_key": venue.key, "dialled_number": built["dialled_number"],
           "language": b["language"], "guest_name": b["name"], "guest_phone": b.get("phone"), "brief": built["brief"],
           "brief_sha256": built["brief_sha256"], "read_back_lines": built["read_back_lines"],
           "read_back_sha256": built["read_back_sha256"], "created_at": now}
    try:
        item = await CALL_STORE.put_cancel_call(row, booking["trip_item_id"])
    except StorageUnavailable as e:
        return _refuse(503, e.rule, e.detail)
    return {"call_id": row["call_id"], "trip_item_id": item, "purpose": "cancel",
            "read_back": {"lines": row["read_back_lines"], "sha256": row["read_back_sha256"]}}


async def _prepare_from_object(account: str, venue: C.CallVenue, body: dict, now):
    """S-64 step 9 · a call from a reservation/1 object: a booking at a set time, or an ASKING call (quote-first,
    "when do you have space"). The venue and its number are still the ones READ (read_id), never the object's; the
    account is the caller's own, never the object's."""
    if not body.get("read_id"):
        return _refuse(422, "read_required", "a call from a reservation needs the venue read (read_id) its number comes from")
    extra = set(body) - {"reservation", "read_id", "fact_index", "trip_id"}
    if extra:
        return _refuse(422, "call_malformed", f"a call from a reservation takes only the object and the read; not {sorted(extra)}")
    obj = body["reservation"] if isinstance(body["reservation"], dict) else {}
    obj = {**obj, "who": {**(obj.get("who") or {}), "account_id": account},
           "where": {**(obj.get("where") or {}), "read_id": str(body["read_id"]), "venue_ids": list(venue.venue_ids or ()),
                     "venue_name": venue.name, "timezone": venue.timezone}}
    try:
        o = RS.validate(obj)
        built = R.call_for(o, venue, now, C.number_of(venue))
    except RS.ReservationRefused as e:
        return _refuse(422, e.rule, str(e).split(": ", 1)[-1])
    except C.CallRefused as e:
        return _refuse(422, e.rule, str(e))
    if built["brief"]["purpose"] == "book":
        try:
            built = _with_hours(built, await _read_of(account, built["brief"]), venue.timezone, now)
        except StorageUnavailable as e:
            return _refuse(503, e.rule, e.detail)
    try:
        built = PT.seal_call(built, venue)   # Sasha 64 · a listing number: dialled, never stored or shown
    except PT.ListingUnavailable as e:
        return _refuse(422, e.rule, str(e))
    cols = RS.columns(o)
    row = {
        "request": o,
        "call_id": str(uuid.uuid4()), "account_id": account, "venue_key": venue.key,
        "dialled_number": built["dialled_number"], "language": built["brief"]["language"],
        "guest_name": o["who"]["name"], "guest_phone": (o["who"].get("contact") or {}).get("mobile_e164"),
        "brief": built["brief"], "brief_sha256": built["brief_sha256"],
        "read_back_lines": built["read_back_lines"], "read_back_sha256": built["read_back_sha256"],
        "created_at": now, "type": o["what"]["category"],
        "venue_name": venue.name, "local_date": cols.get("local_date"), "local_time": cols.get("local_time"),
        "local_timezone": venue.timezone, "party_size": cols.get("party_size"),
    }
    trip_id = body.get("trip_id")
    try:
        item = await CALL_STORE.put_call(row, trip_id if isinstance(trip_id, str) and trip_id else None)
    except UnknownTrip:
        return _refuse(404, "trip_unknown", "no trip with that id belongs to this account; nothing was recorded")
    except StorageUnavailable as e:
        return _refuse(503, e.rule, e.detail)
    return {"call_id": row["call_id"], "trip_item_id": item, "purpose": built["brief"]["purpose"],
            "read_back": {"lines": row["read_back_lines"], "sha256": row["read_back_sha256"]}}


_LANG_BY_CODE = {lang.code: key for key, lang in C.LANGUAGES.items()}


async def _prepare_cancel(account: str, booking_call_id: str, body: dict):
    """S-47 · the call that cancels a booking Sasha made. EVERYTHING — venue, number, language, day, time, party, name,
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
    # a yes, OR an unclear answer: the venue may be holding it (Calma, 1 Oct: a yes the check missed) — a cancellation
    # is the safe call either way. A plain "no" holds nothing, so there is nothing to cancel.
    if b.get("purpose", "book") != "book" or booking["status"] != "answered" or booking.get("outcome") not in ("yes", "unclear"):
        return _refuse(422, "nothing_to_cancel", "only a booking the venue said yes to — or may be holding — can be cancelled by phone")
    lang_key = _LANG_BY_CODE.get(b.get("language"))
    if not b.get("timezone") or lang_key is None:
        return _refuse(422, "booking_brief_incomplete", "that booking's call does not record its language and timezone")
    ref = b.get("number_ref") or {}
    # a booking made before Sasha 64 (and before 013's purge) still holds a listing number's digits: it is a listing
    # number all the same, and its cancellation is stored the new way
    listed = bool(ref) or str(b.get("number_source") or "").startswith("their Google")
    try:
        number = b["number"] or await PT.listing_number(HTTP, ref, NOW())   # Sasha 64 · re-read, checked, not stored
        place_id = ref.get("place_id") or (PT.place_id_of(await _read_of(account, b) or {}) if listed else None)
    except PT.ListingUnavailable as e:
        return _refuse(422, e.rule, str(e).replace("nothing was dialled", "the cancellation could not be prepared"))
    except StorageUnavailable as e:
        return _refuse(503, e.rule, e.detail)
    venue = C.CallVenue(key=b["venue_key"], name=b.get("venue_name") or b["venue_key"], number_env="", language=lang_key,
                        timezone=b["timezone"], number=number, source=PT.LISTING_LABEL if listed else b.get("number_source"),
                        venue_ids=tuple(b.get("venue_ids") or ()) or None,
                        number_kind="places" if listed else b.get("number_source_kind") or "site", place_id=place_id)
    if b.get("activity_venue_lang"):   # S-64 · a booking made from the object: cancel THAT activity, never "a table"
        return await _cancel_from_object(account, booking, b, venue)
    # S-54 · "any stop ends every channel" — a cancellation too; the guest can still cancel themselves
    refused = await ladder_routes._optin_refusal(venue.venue_ids, "phone")
    if refused:
        return refused
    now = NOW()
    try:
        p = C.parse_call_particulars({"date": b["date"], "time": b["time"], "party": b["party"], "name": b["name"], "phone": b.get("phone") or ""})
        built = C.build_call(venue, p, now, purpose="cancel", reference=((booking.get("reading") or {}).get("reference")))
    except C.CallRefused as e:
        return _refuse(422, e.rule, str(e))
    if len(built["brief"]["task"]) > 2000:
        return _refuse(422, "brief_too_long", "the call's instructions exceed Bland's 2,000 characters")
    built["brief"]["cancels_call_id"] = booking_call_id
    built = PT.seal_call(built, venue)
    row = {"request": RS.try_from_particulars(p, account_id=account, venue_name=venue.name, timezone=venue.timezone,
                                              lang=b["language"], venue_ids=venue.venue_ids or (), flow="cancel"),
           "call_id": str(uuid.uuid4()), "account_id": account, "venue_key": venue.key, "dialled_number": built["dialled_number"],
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
    # S-66 (EU) step 6 · a yes TYPED in the chat counts too — with the guest's exact words, kept with the approval
    if a.get("how") not in ("button", "voice", "chat") or (a.get("how") in ("voice", "chat") and not str(a.get("said") or "").strip()):
        return _refuse(422, "approval_void", "an approval is by button, or by voice or typed in the chat with the words said")
    brief = call["brief"]
    if C._sha256hex(C._canonical(brief)) != call["brief_sha256"]:
        return _refuse(409, "brief_changed", "the stored brief no longer matches what was read back; nothing was dialled")
    # S-54 · checked again at the dial, before the claim: a venue can withdraw between the read-back and the yes
    refused = await ladder_routes._optin_refusal(brief.get("venue_ids"), "phone")
    if refused:
        return refused
    # S-66 · CLOSED NOW by its listed hours → no call now: scheduled for opening + 10 minutes, covered by this yes
    if brief.get("purpose") == "book":
        try:
            read = await _read_of(account, brief)
        except StorageUnavailable as e:
            return _refuse(503, e.rule, e.detail)
        st = H.status(read, NOW(), brief["timezone"]) if read else {"known": False}
        if st.get("known") and st.get("open_now") is False and st.get("call_at"):
            return await _schedule(account, call_id, call, body, a, st)
    # Sasha 64 · a listing number is re-read now and must be the one approved — before the claim, so a refusal costs nothing
    try:
        dial = await PT.dialable(HTTP, brief, NOW())
    except PT.ListingUnavailable as e:
        return _refuse(422, e.rule, str(e))
    # S-57 · never a second call while an earlier one to this number may have been placed
    try:
        if await CALL_STORE.unresolved_to(call["dialled_number"]):
            return _refuse(409, "previous_call_unresolved", "an earlier call to this number may have been placed and Bland's "
                                                            "log has not said yet; nothing was dialled — try again in a minute")
    except StorageUnavailable as e:
        return _refuse(503, e.rule, e.detail)
    now = NOW()
    approval = {"by": account, "how": a["how"], "said": a.get("said"), "at": now.isoformat(),
                "read_back_sha256": call["read_back_sha256"], "brief_sha256": call["brief_sha256"]}
    try:
        claimed = await CALL_STORE.claim(account, call_id, approval, now, now - APPROVAL_WINDOW, cap(), cap_window(now), account_cap())
    except StorageUnavailable as e:
        return _refuse(503, e.rule, e.detail)
    if claimed == "taken":
        return _refuse(409, "call_already_placed", "this call was already approved; a second call is a new read-back and a new yes")
    if claimed == "stale":
        return _refuse(422, "read_back_expired", "that read-back is more than 15 minutes old; prepare the call again")
    if claimed == "cap":
        return _refuse(429, "daily_call_limit", f"{cap()} calls have been placed in the last 24 hours, the most this server allows")
    if claimed == "account_cap":
        return _refuse(429, "account_daily_call_limit", f"this account has placed {account_cap()} calls in the last 24 hours, the most one account may")
    if claimed != "claimed":
        return _refuse(404, "call_unknown", "no call with that id was prepared for this account")

    placed = await C.place_call(HTTP, C.bland_key(), C.bland_payload(dial, call_id))
    placed = dataclasses.replace(placed, answer=PT.scrub_bland(placed.answer, brief))
    if placed.uncertain:
        try:
            await CALL_STORE.mark_placed(call_id, placed, NOW())
        except StorageUnavailable as e:
            log.error("[booking_calls] call %s: %s — and it could not be recorded: %s", call_id, placed.why, e)
        return {"ok": True, "status": "uncertain", "why": placed.why,
                "say": "Bland didn't answer in time, so the call may have been placed. I'm checking Bland's own call log "
                       "and will show what happened here — don't call them again until it does."}
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


async def _schedule(account: str, call_id: str, call: dict, body: dict, a: dict, st: dict):
    now = NOW()
    approval = {"by": account, "how": a["how"], "said": a.get("said"), "at": now.isoformat(),
                "read_back_sha256": call["read_back_sha256"], "brief_sha256": call["brief_sha256"],
                "scheduled_for": st["call_at"], "opens_at": st["opens_at"], "hours_basis": st["basis"], "hours_notes": st["notes"]}
    try:
        r = await CALL_STORE.schedule(account, call_id, approval, now, now - APPROVAL_WINDOW)
    except StorageUnavailable as e:
        return _refuse(503, e.rule, e.detail)
    if r == "taken":
        return _refuse(409, "call_already_placed", "this call was already approved; a second call is a new read-back and a new yes")
    if r == "stale":
        return _refuse(422, "read_back_expired", "that read-back is more than 15 minutes old; prepare the call again")
    if r != "scheduled":
        return _refuse(404, "call_unknown", "no call with that id was prepared for this account")
    opens = st["opens_at"][11:]
    call_hhmm = (datetime.fromisoformat(st["opens_at"]) + H.AFTER_OPENING).strftime("%H:%M")
    # the email rung is not live: when it is, the request is emailed here and a reply cancels the call (inbound)
    return {"ok": True, "status": "scheduled", "scheduled_for": st["call_at"],
            "say": f"{_name(call)} is closed now by its listed hours — they open at {opens} — so I'll call at {call_hhmm}, as your yes covered."}


async def place_due() -> int:
    """S-66 · the sweeper places every scheduled call whose time has come (opening + 10 minutes)."""
    now = NOW()
    placed_n = 0
    for call in await CALL_STORE.due(now):
        cid = str(call["call_id"])
        if C.calls_enabled() is False or not C.bland_key():
            await CALL_STORE.cancel_scheduled(cid, "calls were switched off when it was due, so nothing was dialled")
            continue
        try:
            dial = await PT.dialable(HTTP, call["brief"], now)   # Sasha 64 · re-read and checked, before the claim
        except PT.ListingUnavailable as e:
            await CALL_STORE.cancel_scheduled(cid, str(e))
            continue
        r = await CALL_STORE.start_scheduled(cid, cap(), cap_window(now), account_cap())
        if r == "cap":
            await CALL_STORE.cancel_scheduled(cid, f"{cap()} calls had already been placed in the last 24 hours; nothing was dialled")
            continue
        if r == "account_cap":
            await CALL_STORE.cancel_scheduled(cid, f"this account had already placed {account_cap()} calls in the last 24 hours; nothing was dialled")
            continue
        if r != "claimed":
            continue
        placed = await C.place_call(HTTP, C.bland_key(), C.bland_payload(dial, cid))
        await CALL_STORE.mark_placed(cid, dataclasses.replace(placed, answer=PT.scrub_bland(placed.answer, call["brief"])), NOW())
        placed_n += 1
    return placed_n


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
        r = await C.read_call(details if isinstance(details, dict) else {}, READER, (call.get("brief") or {}).get("purpose", "book"),
                                  call.get("brief"))
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
           "read_by": reading.get("read_by"), "offer": reading.get("offer")}
    if call["status"] == "not_placed":
        out["why"] = call.get("not_placed_why")
        out["say"] = f"I couldn't place the call: {call.get('not_placed_why')}"
    elif call["status"] == "placing":
        out["say"] = ("Bland hasn't told me yet whether the call was placed. I'm checking its own call log; I won't call "
                      "them again until it says.")
    elif call["status"] == "awaiting_approval" and (call.get("approval") or {}).get("scheduled_for"):
        ap = call["approval"]
        out["status"] = "scheduled"
        out["say"] = (f"Scheduled: they were closed when you said yes (they open at {ap['opens_at'][11:]}), so I'll call "
                      f"ten minutes after they open. Nothing has been dialled yet.")
    elif call["status"] == "awaiting_approval":
        out["say"] = None
    elif call["status"] in ("answered", "not_reached"):
        r = C.CallReading(state=call["status"], outcome=call.get("outcome"), venue_words=call.get("venue_words") or "",
                          quote=reading.get("quote"), why=reading.get("why") or "", offer=reading.get("offer"))
        out["say"] = C.say_for(name, r, (call.get("brief") or {}).get("purpose", "book"))
    return out
