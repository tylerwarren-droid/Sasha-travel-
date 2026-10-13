"""Sasha 121 · OPS — the founder's tools, refused to every other account.

  POST /api/booking/ops/invite  {email}  → an invitation to Sasha, emailed from Sasha's own address.

Sign-up is INVITE-ONLY until counsel approves the privacy notice and the terms: Supabase keeps public sign-up DISABLED,
so only an address the founder invites here can ever sign in. The link is Supabase's own (admin generate_link — an
"invite" for a new address, a "magiclink" for one already invited); it lands on the app's /auth/confirm, which verifies
it with Supabase and opens "You". The token is never stored or logged here.
"""
from __future__ import annotations

import logging
import os
import re
from typing import Any, Dict, Optional, Tuple
from urllib.parse import quote

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

log = logging.getLogger("booking_signer.ops")
router = APIRouter(prefix="/ops", tags=["booking-ops"])
_EMAIL = re.compile(r"[^@\s]{1,64}@[A-Za-z0-9.-]{1,190}\.[A-Za-z]{2,24}")


def _refuse(status: int, rule: str, message: str) -> JSONResponse:
    return JSONResponse({"ok": False, "rule": rule, "message": message}, status_code=status)


def founder_only(request: Request) -> Optional[JSONResponse]:
    from .account import account_for
    from app.services.accounts import is_founder   # Sasha 249 · the one founder decision
    return None if is_founder(account_for(request)) else _refuse(403, "founder_only", "this is the founder's ops tool")


async def _admin(method: str, path: str, body: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
    """Supabase's admin API, with the service-role key — server side only, never sent anywhere else."""
    import httpx
    url = os.getenv("SASHA_SUPABASE_URL", "").strip().rstrip("/")
    key = os.getenv("SUPABASE_SERVICE_KEY", "").strip()
    if not url or not key:
        return 503, {"msg": "Supabase admin is not configured on this server"}
    async with httpx.AsyncClient(timeout=httpx.Timeout(20.0)) as c:
        r = await c.request(method, f"{url}/auth/v1{path}", json=body, headers={"apikey": key, "authorization": f"Bearer {key}"})
    try:
        return r.status_code, r.json()
    except ValueError:
        return r.status_code, {}


ADMIN = _admin   # tests replace it


def web() -> str:
    return os.getenv("SASHA_WEB_URL", "https://project.kanoe.ai").rstrip("/")


def invitation(link: str) -> str:
    return ("Hello,\n\nYou're invited to Sasha by Kanoe — an AI concierge that books restaurants and other venues for you, by "
            "phone, email and messaging, and always tells them she is an AI.\n\n"
            f"Open this link to sign in (it works once, for 24 hours):\n{link}\n\n"
            "There is no password: each time, Sasha emails you a link like this one.\n"
            f"How we handle your details: {web()}/sasha-privacy\n\n"
            "— Sasha (AI concierge, Kanoe Technologies SL)")


@router.post("/invite")
async def invite(request: Request):
    no = founder_only(request)
    if no:
        return no
    try:
        body = await request.json()
    except Exception:
        body = {}
    return await _invite(str((body or {}).get("email") or "").strip())


_NONCES: Dict[str, float] = {}


@router.post("/invite-from-agapi")
async def invite_from_agapi(request: Request):
    """CR 91 · AgAPI's founder page (EU 250 §B3) — the SAME invitation, asked server to server. X-Kanoe-Invite-Signature:
    t=<unix>,n=<nonce>,v1=<hex HMAC-SHA256(SASHA_AGAPI_INVITE_SECRET, "<t>.<n>.<raw body>")>; stale after 5 minutes; a nonce is used once.
    → {account_id}: the person's Sasha account (AgAPI's person_access row is keyed by it)."""
    import hashlib
    import hmac
    import time
    secret = os.getenv("SASHA_AGAPI_INVITE_SECRET", "").strip()
    raw = (await request.body()).decode()
    m = re.fullmatch(r"t=(\d+),n=([A-Za-z0-9_-]{16,64}),v1=([0-9a-f]{64})", (request.headers.get("x-kanoe-invite-signature") or "").strip())
    if not secret or not m or abs(int(time.time()) - int(m.group(1))) > 300:
        return _refuse(401, "unsigned", "this route takes only AgAPI's signed request")
    want = hmac.new(secret.encode(), f"{m.group(1)}.{m.group(2)}.{raw}".encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(want, m.group(3)) or m.group(2) in _NONCES:
        return _refuse(401, "unsigned", "this route takes only AgAPI's signed request")
    now = time.time()
    for k, at in list(_NONCES.items()):
        if now - at > 600:
            _NONCES.pop(k, None)
    _NONCES[m.group(2)] = now
    try:
        email = str((__import__("json").loads(raw or "{}") or {}).get("email") or "").strip()
    except ValueError:
        email = ""
    return await _invite(email)


async def _invite(email: str):
    from . import emailing as E, ladder_routes as LR
    if not _EMAIL.fullmatch(email):
        return _refuse(422, "email_invalid", "that isn't an email address")
    redirect = f"{web()}/you"
    kind = "invite"
    s, j = await ADMIN("POST", "/admin/generate_link", {"type": "invite", "email": email, "redirect_to": redirect})
    if s == 422 and re.search(r"already|registered|exists", str(j), re.I):   # invited before: a fresh sign-in link
        kind = "magiclink"
        s, j = await ADMIN("POST", "/admin/generate_link", {"type": "magiclink", "email": email, "redirect_to": redirect})
    th = j.get("hashed_token") or (j.get("properties") or {}).get("hashed_token")
    if s != 200 or not th:
        log.error("[ops] invitation not created: HTTP %s %s", s, str(j.get("msg") or j.get("error_description") or "")[:200])
        return _refuse(502, "invite_not_created", f"Supabase did not create the invitation (HTTP {s})")
    link = f"{web()}/auth/confirm?token_hash={quote(th)}&type={kind}&next=/you"
    sent = await E.send(LR.HTTP, {"from": os.getenv("SASHA_EMAIL_FROM", "").strip(), "to": email,
                                  "subject": "You're invited to Sasha by Kanoe", "text": invitation(link)})
    if not sent.sent:
        return _refuse(502, "invite_not_sent", f"the invitation was created but not emailed: {sent.why}")
    log.info("[ops] invitation (%s) emailed", kind)
    account_id = j.get("id") or (j.get("user") or {}).get("id")   # CR 91 · the person's account (Supabase user id) — AgAPI keys their access record by it
    return {"ok": True, "to": email, "kind": kind, **({"account_id": account_id} if account_id else {}),
            "say": f"Invitation sent to {email}. The link works once, for 24 hours."}


__all__ = ["router", "invite", "invite_from_agapi", "invitation", "founder_only"]
