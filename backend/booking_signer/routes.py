"""The booking routes — mounted at /api/booking by ONE line in backend/app/main.py (re-applied in Stage B).

    GET  /api/booking/health                     signer key + storage, for Stage E
    POST /api/booking/pairing/challenge          contract §4 step 1
    POST /api/booking/pairing                    contract §4 step 4 — store the device against the account
    GET  /api/booking/devices                    the account's paired devices
    POST /api/booking/intents                    RECORD the intent: particulars → task, read-back, hashes
    POST /api/booking/intents/{intent_id}/issue  the user said yes → sign the task (once per intent, ever)
    POST /api/booking/reports                    a relayed REPORT → verify → outcome → the trip item's status
    GET  /api/booking/reservations               the account's reservations: trip items something was sent for
    POST /api/booking/calls …                    S-33, the phone rung — call_routes.py

⚠ A RESERVATION IS A TRIP ITEM (store.py): created with the intent as `pending`, and given an outcome only when
the device reports that something was sent to the venue.

⛔ LIVE SUBMISSION IS OFF HERE AS WELL AS IN THE HELPER. A `mode: "live"` intent is refused before anything
is recorded (`live_submit_disabled_in_this_build`, the helper's own name for the same switch). Only dry runs
can be recorded, issued and reported, and a dry run stops before the venue's submit — so nothing in this
module can cause a real booking.

⚠ Every refusal answers with its rule by name. Storage that is missing answers 503, never a silent drop.
"""
from __future__ import annotations

import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from . import call_routes, ladder_routes, optin_page, optins, retention, stop
from .account import account_for
from .gate import require_booking_key
from .call_store import PostgresCallStore
from .ladder_store import PostgresLadderStore
from .optins import PostgresOptinStore
from .issue import IssueRefused, _iso_ms, issue_booking_task
from .keys import InvalidSigningKey, LoadedSigningKey, SigningKeyNotConfigured, load_signing_key
from .outcome import outcome_of
from .store import OBSERVED_BY, AlreadyRecorded, PostgresStore, StorageUnavailable, UnknownTrip
from .venues import VENUES, ParticularsRefused, build_for_venue, parse_particulars
from .verify import VerifyRefused, verify_device_report, verify_pairing

log = logging.getLogger("sasha.booking_signer")

#: The only origin the helper lets connect, and so the only one a pairing may name (contract §4, §5.1).
SASHA_ORIGIN = "https://project.kanoe.ai"
#: The signing key the helper PINS (extension-sasha/lib/config.js, S-19). A task signed by any other key is
#: refused by every installed helper, so this server refuses to sign with one.
PINNED_FINGERPRINT = "525f7027ed4f62b2"
#: ⛔ Off. Turning it on is a founder decision AND a new helper build (contract §0, switch 2).
LIVE_ISSUE_ENABLED = False
#: How long a task lives. The contract's ceiling is 15 minutes; the §12 vector uses 10.
TASK_LIFETIME = timedelta(minutes=10)
CHALLENGE_LIFETIME = timedelta(minutes=10)

# S-41 · every route below, and every router included into this one, needs the booking key (gate.py) — except the
# health report and the svix-signed email webhook
router = APIRouter(prefix="/api/booking", tags=["booking"], dependencies=[Depends(require_booking_key)])


# ── the key: loaded ONCE, at import — loud in the log, never fatal to the rest of Sasha ────────────

def _load_key() -> tuple:
    try:
        key = load_signing_key()
    except (SigningKeyNotConfigured, InvalidSigningKey) as e:
        # ⚠ The contract says refuse at startup, loudly. Loud: this line, and every issue answering 503 with
        # the reason. NOT fatal: a bad signing key must not take Sasha's chat and voice down with it.
        log.error("[booking_signer] signing key unusable — no booking task can be issued: %s", e)
        return None, f"{type(e).__name__}: {e}"
    if key.fingerprint != PINNED_FINGERPRINT:
        log.error("[booking_signer] signing key fingerprint %s is not the one the helper pins (%s) — "
                  "every task it signed would be refused", key.fingerprint, PINNED_FINGERPRINT)
    else:
        log.info("[booking_signer] signing key loaded, fingerprint %s (pinned)", key.fingerprint)
    return key, None


KEY, KEY_ERROR = _load_key()
STORE: Any = PostgresStore()
call_routes.CALL_STORE = PostgresCallStore(STORE)
ladder_routes.LADDER_STORE = PostgresLadderStore(STORE)
optins.OPTIN_STORE = PostgresOptinStore(STORE)   # S-54 · the refusal check reads venue_optins (sql/008)
optin_page.PAGE_STORE = optin_page.PostgresPageStore(STORE)   # S-55 · the Work-with-Sasha page (sql/009)
stop.STOP_STORE = stop.PostgresStopStore(STORE)   # S-56 · a venue's stop, on any channel (sql/010)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _refuse(status: int, rule: str, message: str) -> JSONResponse:
    return JSONResponse({"ok": False, "rule": rule, "message": message}, status_code=status)


def _unavailable(e: StorageUnavailable) -> JSONResponse:
    return _refuse(503, e.rule, e.detail)   # the rule is its own field: never repeated in the message


async def _json(request: Request) -> Optional[dict]:
    try:
        body = await request.json()
    except Exception:
        return None
    return body if isinstance(body, dict) else None


def _signing_key() -> tuple:
    """(key, None) or (None, refusal response)."""
    if KEY is None:
        return None, _refuse(503, "signer_not_configured", KEY_ERROR or "no signing key")
    if KEY.fingerprint != PINNED_FINGERPRINT:
        return None, _refuse(503, "signing_key_not_pinned_in_helper",
                             f"this server's key {KEY.fingerprint} is not the helper's pinned {PINNED_FINGERPRINT}")
    return KEY, None


# ── health — what Stage E probes ──────────────────────────────────────────────────────────────

@router.get("/health")
async def health():
    """Always 200: it REPORTS. Stage E checks `signer.matches_pinned` and `storage.provisioned`."""
    storage = await STORE.status()
    return {
        "mounted": True,
        "signer": {
            "configured": KEY is not None,
            "fingerprint": KEY.fingerprint if KEY else None,
            "matches_pinned": bool(KEY and KEY.fingerprint == PINNED_FINGERPRINT),
            "error": KEY_ERROR,
        },
        "storage": storage,
        "live_issue_enabled": LIVE_ISSUE_ENABLED,
        "calls": call_routes.status(),
        "ladder": ladder_routes.status(),
    }


# ── pairing (contract §4) ─────────────────────────────────────────────────────────────────────

@router.post("/pairing/challenge")
async def pairing_challenge(request: Request):
    account = account_for(request)
    challenge = secrets.token_urlsafe(32)  # 43 characters; the contract asks for at least 32
    now = _now()
    try:
        await STORE.put_challenge(account, challenge, now, now + CHALLENGE_LIFETIME)
    except StorageUnavailable as e:
        return _unavailable(e)
    return {"challenge": challenge, "expires_at": _iso_ms(now + CHALLENGE_LIFETIME)}


@router.post("/pairing")
async def pair(request: Request):
    account = account_for(request)
    body = await _json(request)
    if body is None:
        return _refuse(400, "pairing_invalid", "send the helper's PAIR answer as a JSON object")
    try:
        # ⚠ the challenge is spent BEFORE the signature is checked: a challenge is good for one attempt only
        if not await STORE.take_challenge(account, str(body.get("challenge") or ""), _now()):
            return _refuse(422, "pairing_invalid", "that challenge was not issued to this account, was already used, or has expired")
        device = verify_pairing(
            challenge=body.get("challenge"), expected_origin=SASHA_ORIGIN,
            device_public_spki=body.get("device_public_spki"), device_id=body.get("device_id"),
            origin=body.get("origin"), signature=body.get("signature"),
        )
        added = await STORE.add_device(account, device, SASHA_ORIGIN, _now())
    except VerifyRefused as e:
        return _refuse(422, e.rule, str(e))
    except StorageUnavailable as e:
        return _unavailable(e)
    if added == "other_account":
        return _refuse(409, "device_paired_to_another_account", "this browser is already paired to another account")
    return {"ok": True, "device_id": device.device_id, "already_paired": added == "already"}


@router.get("/devices")
async def devices(request: Request):
    try:
        found = await STORE.devices(account_for(request))
    except StorageUnavailable as e:
        return _unavailable(e)
    return {"devices": [d.device_id for d in found]}


# ── the intent: RECORDED before anything is signed (contract §3.5) ─────────────────────────────

@router.post("/intents")
async def record_intent(request: Request):
    account = account_for(request)
    body = await _json(request)
    if body is None:
        return _refuse(400, "intent_malformed", "send the booking as a JSON object")
    mode = body.get("mode", "dry_run")
    if mode == "live" and not LIVE_ISSUE_ENABLED:
        return _refuse(422, "live_submit_disabled_in_this_build",
                       "this build can prepare a booking but cannot send one; nothing was recorded")
    if mode != "dry_run" and mode != "live":
        return _refuse(422, "task_malformed", f"mode is dry_run or live, not {mode!r}")
    venue = VENUES.get(body.get("venue"))
    if venue is None:
        return _refuse(422, "venue_not_specified", f"no booking task is specified for {body.get('venue')!r}")
    try:
        p = parse_particulars(body)
        built = build_for_venue(venue, p, mode)
    except ParticularsRefused as e:
        return _refuse(422, e.rule, str(e))
    trip_id = body.get("trip_id")  # optional: one of this account's trips; else its "Sasha bookings" trip
    row = {
        "intent_id": str(uuid.uuid4()), "account_id": account, "venue_key": venue.key, "mode": mode,
        # → the trip item (the reservation)
        "venue_name": venue.short_name, "local_date": p.on, "local_time": p.at, "local_timezone": venue.timezone,
        "party_size": p.party,
        # → the intent (what the user said yes to)
        "guest_name": p.name, "guest_email": p.email, "guest_phone": p.phone,
        "task": built["task"], "standing": built["standing"], "read_back_lines": built["read_back_lines"],
        "read_back_sha256": built["read_back_sha256"], "filled_values_sha256": built["filled_values_sha256"],
        "status": "awaiting_approval", "created_at": _now(),
    }
    try:
        trip_item_id = await STORE.put_intent(row, trip_id if isinstance(trip_id, str) and trip_id else None)
    except UnknownTrip:
        return _refuse(404, "trip_unknown", "no trip with that id belongs to this account; nothing was recorded")
    except StorageUnavailable as e:
        return _unavailable(e)
    # ⚠ The page reads these lines to the user, exactly — the yes is bound to their hash.
    return {"intent_id": row["intent_id"], "trip_item_id": trip_item_id, "mode": mode, "read_back": {"lines": row["read_back_lines"], "sha256": row["read_back_sha256"]}}


@router.post("/intents/{intent_id}/issue")
async def issue(intent_id: str, request: Request):
    account = account_for(request)
    body = await _json(request)
    if body is None:
        return _refuse(400, "approval_void", "send {device_id, approval: {how, said}} as a JSON object")
    key, refusal = _signing_key()
    if refusal:
        return refusal
    try:
        intent = await STORE.get_intent(account, intent_id)
        if intent is None:
            return _refuse(404, "intent_unknown", "no intent with that id was recorded for this account")
        if intent["status"] != "awaiting_approval":
            # ⚠ one task per intent, ever: a second attempt is a NEW intent, a new read-back and a new yes
            return _refuse(409, "intent_already_issued", "a task was already signed for this intent; a retry is a new intent")
        if intent["mode"] == "live" and not LIVE_ISSUE_ENABLED:
            return _refuse(422, "live_submit_disabled_in_this_build", "this build cannot send a booking")
        paired = await STORE.devices(account)
    except StorageUnavailable as e:
        return _unavailable(e)

    approval_in = body.get("approval") if isinstance(body.get("approval"), dict) else {}
    now = _now()
    task = {**intent["task"], "intent_id": intent_id, "issued_at": _iso_ms(now), "expires_at": _iso_ms(now + TASK_LIFETIME)}
    # ⚠ The approval is bound HERE, from what this server recorded — the page supplies only how and what was said.
    approval = {
        "by": account, "how": approval_in.get("how"), "at": _iso_ms(now), "said": approval_in.get("said"),
        "read_back_sha256": intent["read_back_sha256"], "filled_values_sha256": intent["filled_values_sha256"],
    }
    venue = VENUES[intent["venue_key"]]
    try:
        signed = issue_booking_task(
            task=task,
            read_back={"lines": intent["read_back_lines"], "read_back_sha256": intent["read_back_sha256"],
                       "filled_values_sha256": intent["filled_values_sha256"]},
            approval=approval, mode=intent["mode"], device_id=body.get("device_id"), standing=intent["standing"],
            confirmation_email_field=venue.confirmation_email_field, now=now, key=key,
            paired_device_ids=[d.device_id for d in paired],
        )
    except IssueRefused as e:
        return _refuse(422, e.rule, str(e))
    try:
        await STORE.put_task({
            "intent_id": intent_id, "task_digest": signed["digest"], "account_id": account,
            "device_id": body.get("device_id"), "mode": intent["mode"], "payload": signed["payload"],
            "signature": signed["signature"], "issued_at": now, "expires_at": now + TASK_LIFETIME,
        })
    except AlreadyRecorded:
        return _refuse(409, "intent_already_issued", "a task was already signed for this intent; a retry is a new intent")
    except StorageUnavailable as e:
        return _unavailable(e)
    # ⚠ Handed to the page to RELAY, exactly as returned: {"type":"RUN","payload":…,"signature":…}
    return {"payload": signed["payload"], "signature": signed["signature"]}


# ── the report: verify, then (only if something was sent) an attempt and the trip item's outcome ──

@router.post("/reports")
async def report(request: Request):
    account = account_for(request)
    signed = await _json(request)
    if signed is None:
        return _refuse(400, "report_malformed", "send the helper's REPORT message as a JSON object")
    body = signed.get("report")
    if not isinstance(body, dict):
        return _refuse(400, "report_malformed", "the REPORT carries a report object")
    try:
        paired = {d.device_id: d for d in await STORE.devices(account)}
        device = paired.get(signed.get("device_id"))
        if device is None:
            return _refuse(403, "report_from_another_device", "the report was signed by a device this account did not pair")
        digest = signed.get("task_digest")

        if digest is None:
            # §5.4 · refused before the helper verified the task: nothing ran, nothing was sent, no outcome
            verify_device_report(signed, device, expected_task_digest="")
            known = await STORE.get_intent(account, str(body.get("intent_id") or ""))
            await STORE.record_report({
                "received_at": _now(), "account_id": account, "device_id": device.device_id, "task_digest": None,
                "intent_id": known["intent_id"] if known else None, "task_verified": False, "report": body,
                "device_signature": signed.get("device_signature"), "outcome": None,
            }, None)
            return {"ok": True, "outcome": None, "reservation_id": None, "say": body.get("user_words"), "status_line": None}

        task = await STORE.get_task_by_digest(digest)
        if task is None or task["account_id"] != account:
            return _refuse(409, "report_of_another_task", "no task with that digest was issued to this account")
        if task["device_id"] != device.device_id:
            return _refuse(403, "report_from_another_device", "the report was signed by a device other than the one the task named")
        verify_device_report(signed, device, expected_task_digest=task["task_digest"])
        if body.get("intent_id") != task["intent_id"]:
            return _refuse(409, "report_of_another_task", "the report names a different intent from the task it quotes")

        previous = await STORE.get_report_for_task(digest)
        if previous is not None:
            return await _already(previous, task)

        intent = await STORE.get_intent(account, task["intent_id"])
        venue = VENUES[intent["venue_key"]]
        out = outcome_of(body, venue.short_name)
        attempt = None
        if out.status is not None:
            # ⚠ Only a SENT task is an attempt (models A's "audit trail for every method used to confirm a trip
            # item"). Its status is always given — booking_attempts has no default since S-17.
            attempt = {
                "trip_item_id": intent["trip_item_id"], "task_digest": digest, "attempted_at": _now(),
                "status": out.status, "venue_words": out.venue_words, "venue_reference": out.venue_reference,
                "observed_at": _parse_instant(out.observed_at), "observed_by": OBSERVED_BY,
            }
        # S-26: a DRY RUN that filled and checked the form on the device, and sent nothing, leaves the reservation
        # PREPARED — never requested, never confirmed. No attempt row: an attempt is something sent.
        prepared = (out.status is None and task["mode"] == "dry_run" and body.get("sent") is False
                    and body.get("phase") == "captured_not_sent")
        try:
            rid = await STORE.record_report({
                "received_at": _now(), "account_id": account, "device_id": device.device_id, "task_digest": digest,
                "intent_id": task["intent_id"], "task_verified": True, "report": body,
                "device_signature": signed.get("device_signature"), "outcome": out.status,
            }, attempt, intent["trip_item_id"] if prepared else None)
        except AlreadyRecorded:  # the same report, arriving twice at once
            return await _already(await STORE.get_report_for_task(digest), task)
    except VerifyRefused as e:
        # ⚠ contract §5.4: a report that fails any check is discarded, and the task is NOT treated as having
        # run or not run — the user is told to check their email before trying again
        return _refuse(422, e.rule, f"{e} — this report was not recorded. Check your email before trying again.")
    except StorageUnavailable as e:
        return _unavailable(e)
    # ⚠ Only now may the page send ACK to the helper.
    return {"ok": True, "outcome": out.status, "reservation_id": rid, "say": out.say, "status_line": out.status_line}


async def _already(previous: dict, task: dict) -> dict:
    """A report re-sent on PENDING (the ACK was lost): recognised, never recorded twice."""
    att = await STORE.attempt_for_task(task["task_digest"])
    return {"ok": True, "already_recorded": True, "outcome": previous["outcome"],
            "reservation_id": att["trip_item_id"] if att else None, "say": None, "status_line": None}


def _parse_instant(s: Any) -> Optional[datetime]:
    if not isinstance(s, str):
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else None


# ── reservations ──────────────────────────────────────────────────────────────────────────────

#: What each status means, in words a guest can read. ⚠ None of them says "booked": prepared is not sent,
#: requested is not confirmed, and confirmed is unreachable from this surface (contract §8).
STATUS_WORDS = {
    "prepared": "Prepared — not sent (demo)",
    "requested": "Requested — waiting for the restaurant to confirm",
    "declined": "Declined by the restaurant",
    "unreachable": "Sent — their reply could not be read",
    "failed": "Sent — the page after could not be read",
    "confirmed": "Confirmed by the restaurant",
    "unclear": "Unclear — read what they said",
    "attempting": "Sent — waiting for their reply",
    "link_sent": "Link sent — not booked yet",
    "guest_booked": "Booked by you — forward the confirmation to add the reference",
    # S-56 · the venue said stop while this was pending: never "declined", which would put words in their mouth
    "escalated": "Not confirmed — the venue asked Sasha to stop contacting them; you can still contact them yourself",
}

@router.get("/reservations")
async def reservations(request: Request):
    try:
        rows = await STORE.reservations(account_for(request))
    except StorageUnavailable as e:
        return _unavailable(e)
    return {"reservations": [{
        "id": r["id"], "trip_id": r["trip_id"], "intent_id": r["intent_id"], "channel": r.get("channel") or "form", "venue": r["venue"],
        "date": r["local_date"].isoformat(), "time": r["local_time"].strftime("%H:%M"), "timezone": r["local_timezone"],
        "party": r["party_size"], "status": r["status"], "status_words": STATUS_WORDS.get(r["status"], r["status"]),
        # the VENUE's own reservation number, only ever when its page or email gave one — never ours in its place
        "booking_reference": r["booking_reference"],
        # Sasha's OWN reference (P807mv §3): the first 8 of the intent id — labelled as hers, never as the restaurant's
        "sasha_reference": str(r["intent_id"])[:8],
        "venue_words": r["venue_words"], "observed_by": r["observed_by"], "task_digest": r["task_digest"],
    } for r in rows]}


# S-33 · the phone rung, under the same /api/booking prefix
router.include_router(call_routes.router)
# S-36 · the ladder: venue reads, the email rung, the inbound webhook
router.include_router(ladder_routes.router)
# S-55 · the Work-with-Sasha page's server half (reached through the frontend's own route, which adds the key)
router.include_router(optin_page.router)


# S-53 · the daily retention job (retention.py) starts with the app; off in tests and without a database
@router.on_event("startup")
async def _start_retention() -> None:
    retention.start()
