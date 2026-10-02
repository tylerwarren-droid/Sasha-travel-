"""S-78 §9 · DELETE EVERYTHING, AND SEE EVERYTHING — the guest's GDPR rights over what Sasha keeps for them.

  DELETE /api/booking/account/data    {confirm: "delete everything"} — and a sign-in within the last 10 minutes
      → the vault crypto-shredded (rows, keys, ciphertext and use history), the WhatsApp link, its codes and its
        conversation state, the saved name and mobile; one retention_log line per table (S-53). Bookings already made
        stay with the venue's own record and follow S-51's retention periods.
  GET    /api/booking/account/export  → JSON: reservations, consents, the vault's METADATA and use history.
      V-3 · never a secret in plaintext, and nothing here decrypts.

Re-auth: deleting needs a FRESH sign-in (the token's `amr` timestamp within ten minutes), not just a live session —
a borrowed open laptop must not be able to erase an account. The founder's session header is not a sign-in.
"""
from __future__ import annotations

import base64
import json
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..account import account_for
from ..store import StorageUnavailable
from . import crypto

log = logging.getLogger("booking_signer.vault.gdpr")
router = APIRouter(prefix="/account", tags=["booking-account"])
NOW = lambda: datetime.now(timezone.utc)
FRESH_SECONDS = 600
CONFIRM = "delete everything"


def _refuse(status: int, rule: str, message: str) -> JSONResponse:
    return JSONResponse({"ok": False, "rule": rule, "message": message}, status_code=status)


def signed_in_within(request: Request, seconds: int = FRESH_SECONDS) -> bool:
    """The bearer token (already verified by the gate) records a sign-in in its `amr` no older than `seconds`."""
    auth = request.headers.get("authorization", "")
    scheme, _, token = auth.partition(" ")
    if scheme.lower() != "bearer" or token.count(".") != 2:
        return False
    try:
        part = token.split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4)))
        stamps = [int(a.get("timestamp") or 0) for a in claims.get("amr") or [] if isinstance(a, dict)]
    except Exception:
        return False
    return bool(stamps) and time.time() - max(stamps) <= seconds


async def _log_deletion(account: str, counts: Dict[str, int], now: datetime) -> None:
    """S-53 · every deletion is logged — the table and how many rows, never whose."""
    from .. import routes
    run_id = uuid.uuid4()

    async def go(c):
        for table, n in counts.items():
            await c.execute("insert into retention_log (run_id, ran_at, rule, table_name, rows_affected, cutoff, note) "
                            "values ($1,$2,$3,$4,$5,$6,$7)", run_id, now, "guest_erasure", table, n, now,
                            "the guest asked for everything to be deleted (S-78 §9)")
    await routes.STORE._run(go)


LOG_DELETION: Callable = _log_deletion   # tests replace it


@router.delete("/data")
async def delete_everything(request: Request):
    from .. import contacts, guest_whatsapp as GW
    account = account_for(request)
    try:
        body = await request.json()
    except Exception:
        body = None
    if not isinstance(body, dict) or str(body.get("confirm") or "").strip().lower() != CONFIRM:
        return _refuse(400, "erasure_unconfirmed", f'type "{CONFIRM}" to confirm — this cannot be undone')
    if not signed_in_within(request):
        return _refuse(401, "erasure_needs_fresh_sign_in", "sign in again with your email link, then delete within ten minutes")
    now = NOW()
    counts: Dict[str, int] = {}
    try:
        counts.update(await crypto.STORE.delete_account(account))
        if GW.STORE is not None:
            counts.update(await GW.STORE.delete_account(account))
        counts["guest_contacts"] = 1 if (contacts.STORE is not None and await contacts.STORE.delete(account)) else 0
        from .. import proactive as PR
        if PR.STORE is not None:   # S-83 · the reminder ledger, the opt-outs and the saved starting point
            counts.update(await PR.STORE.delete_account(account))
        from .. import invitations as IV
        if IV.STORE is not None:   # S-80 · invitations they sent
            counts.update(await IV.STORE.delete_account(account))
        from .. import mailbox as MB
        if MB.STORE is not None:   # S-82 · what was found in their inbox (facts only; the token went with the vault)
            counts["mailbox_finds"] = await MB.STORE.delete_account_finds(account)
        await LOG_DELETION(account, counts, now)
    except StorageUnavailable as e:
        log.error("[gdpr] erasure incomplete: %s", e.detail)
        return _refuse(503, e.rule, f"not everything could be deleted yet — {e.detail}; nothing you can see was kept back on purpose, try again")
    log.info("[gdpr] an account's data was erased: %s", counts)
    return {"deleted": counts, "say": "Deleted. Your saved accesses, WhatsApp link and saved details are gone. Bookings already "
                                      "made stay with the venue's own record; Sasha's copies follow the retention periods in the privacy notice."}


def _iso(v):
    return v.isoformat() if isinstance(v, datetime) else (str(v) if isinstance(v, uuid.UUID) else v)


def _jsonable(x: Any) -> Any:
    if isinstance(x, dict):
        return {k: _jsonable(v) for k, v in x.items()}
    if isinstance(x, list):
        return [_jsonable(v) for v in x]
    return _iso(x)


@router.get("/export")
async def export(request: Request):
    from .. import contacts, guest_whatsapp as GW, routes
    account = account_for(request)
    try:
        items = await crypto.STORE.list(account)
        uses = await crypto.STORE.uses_of(account)
        events = await crypto.STORE.events_of(account)
        contact = await contacts.STORE.get(account) if contacts.STORE is not None else None
        ch = await GW.STORE.channel_of_account(account) if GW.STORE is not None else None
        rows: List[dict] = await routes.STORE.reservations(account) if routes.STORE is not None else []
    except StorageUnavailable as e:
        return _refuse(503, e.rule, e.detail)
    return _jsonable({
        "exported_at": NOW(),
        "reservations": [{k: r.get(k) for k in ("id", "venue", "local_date", "local_time", "party_size", "status", "channel",
                                               "booking_reference", "venue_words")} for r in rows],
        "consents": {
            "contact": ({"name": contact["name"], "mobile_e164": contact["mobile_e164"], "version": contact["consent_wording_version"],
                         "at": contact["consent_at"]} if contact else None),
            "whatsapp": ({"linked_at": ch["linked_at"], "version": ch["consent_wording_version"], "at": ch["consent_at"],
                          "opted_out_at": ch.get("opted_out_at")} if ch else None)},
        # V-3 · metadata and history only — a secret is never exported
        "vault": {"items": items, "uses": [{k: u[k] for k in ("item_id", "action_kind", "action_ref", "status", "started_at", "ended_at")}
                                            for u in uses],
                  "events": events},
    })


__all__ = ["router", "signed_in_within", "CONFIRM"]
