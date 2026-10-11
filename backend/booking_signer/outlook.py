"""CR 86 · OUTLOOK / MICROSOFT 365, READ-ONLY — for the subscription finder (receipts) only; beta, by invitation, like Gmail.

Microsoft Graph, DELEGATED Mail.Read (+ offline_access): Sasha reads the signed-in person's own mail and nothing else — it never
sends, moves or deletes mail (no Mail.ReadWrite, no Mail.Send). The access is sealed in the vault as its own item (provider
microsoft.com, label "Outlook (read-only)"), used only by the purpose outlook_read, every use logged — exactly as Gmail's is.

Reading narrowly is in agapi/s2_outlook_receipts.py: ONE search (receipt / renewal subjects, 13 months), only its messages fetched,
their text sent to AgAPI and dropped. The consent sentence below is ticked on /you before Microsoft's sign-in; the chat says its own
sentence (s2_outlook_receipts.CONSENT) and waits for a yes in a later turn before the first search.

Env: SASHA_MS_CLIENT_ID, SASHA_MS_CLIENT_SECRET, SASHA_MS_REDIRECT (…/api/booking/outlook/callback), SASHA_MS_TENANT (default
"organizations": any work or school account; the Kanoe tenant id narrows it), SASHA_OUTLOOK_ACCOUNTS (invited, besides the founder
and SASHA_GMAIL_ACCOUNTS)."""
from __future__ import annotations

import hashlib
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlencode

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, RedirectResponse

log = logging.getLogger(__name__)
NOW = lambda: datetime.now(timezone.utc)
PROVIDER, LABEL = "microsoft.com", "Outlook (read-only)"
MAIL_READ = "https://graph.microsoft.com/Mail.Read"
SCOPE = f"offline_access {MAIL_READ}"
CONSENT = {"v1": ("Sasha will read your Outlook mail only for receipt and renewal emails from the last 13 months, to list what you're "
                  "subscribed to — read-only: it never sends, moves or deletes mail, and never stores your emails.")}
CURRENT = "v1"
router = APIRouter(prefix="/outlook", tags=["booking-outlook"])


def consent(version: str = CURRENT) -> dict:
    return {"version": version, "text": CONSENT[version], "sha256": hashlib.sha256(CONSENT[version].encode()).hexdigest()}


def tenant() -> str:
    return os.getenv("SASHA_MS_TENANT", "").strip() or "organizations"


def configured() -> bool:
    return all(os.getenv(k, "").strip() for k in ("SASHA_MS_CLIENT_ID", "SASHA_MS_CLIENT_SECRET", "SASHA_MS_REDIRECT"))


def invited(account: str) -> bool:
    from .mailbox import invited as gmail_invited
    listed = {a.strip().lower() for a in os.getenv("SASHA_OUTLOOK_ACCOUNTS", "").split(",") if a.strip()}
    return gmail_invited(account) or account.lower() in listed


def web_url(q: str) -> str:
    return os.getenv("SASHA_WEB_URL", "https://project.kanoe.ai").rstrip("/") + f"/you?{q}#outlook"


async def link(account: str) -> Optional[dict]:
    """The account's live Outlook access (the newest, not revoked) — its vault item's metadata, never the token."""
    from .vault import crypto as VC
    items = [i for i in await VC.STORE.list(account) if i["provider"] == PROVIDER and i["label"] == LABEL and not i.get("revoked_at")]
    return items[-1] if items else None


async def _http(method: str, url: str, data: Optional[dict] = None):
    import httpx
    async with httpx.AsyncClient(timeout=httpx.Timeout(20.0)) as c:
        r = await c.request(method, url, data=data)
    return r.status_code, (r.json() if r.headers.get("content-type", "").startswith("application/json") else {})


MS_HTTP = _http   # tests replace it


def _refuse(status: int, rule: str, message: str) -> JSONResponse:
    return JSONResponse({"ok": False, "rule": rule, "message": message}, status_code=status)


@router.get("")
async def outlook_view(request: Request):
    from .account import account_for
    account = account_for(request)
    return {"configured": configured(), "invited": invited(account), "connected": bool(await link(account)), "consent": consent()}


@router.post("/connect")
async def outlook_connect(request: Request):
    from .account import account_for
    from .calendar_sync import make_state
    account = account_for(request)
    try:
        body = await request.json()
    except Exception:
        body = {}
    if not invited(account):
        return _refuse(403, "outlook_by_invitation", "Outlook is a beta by invitation, and it isn't open for your account yet")
    c = consent()
    if body.get("consent_version") != c["version"] or body.get("consent_sha256") != c["sha256"]:
        return _refuse(422, "consent_stale", "tick the sentence shown — it must be the current one")
    if not configured():
        return _refuse(503, "microsoft_not_configured", "Microsoft sign-in isn't set up on this server yet")
    q = {"client_id": os.getenv("SASHA_MS_CLIENT_ID", "").strip(), "redirect_uri": os.getenv("SASHA_MS_REDIRECT", "").strip(),
         "response_type": "code", "response_mode": "query", "scope": SCOPE, "prompt": "select_account",
         "state": make_state(account, c["version"], product="outlook")}
    return {"url": f"https://login.microsoftonline.com/{tenant()}/oauth2/v2.0/authorize?" + urlencode(q)}


@router.get("/callback")
async def outlook_callback(request: Request):
    """Microsoft's redirect. The account is the one the signed state names — never anything else in the request."""
    from .calendar_sync import read_state
    from .vault import crypto as VC, kms
    st = read_state(request.query_params.get("state", ""))
    if st is None or st.get("p") != "outlook":
        return _refuse(400, "state_invalid", "that sign-in link is not valid or has expired; start again from Sasha")
    if request.query_params.get("error"):
        return RedirectResponse(web_url("outlook=declined"), status_code=303)
    s, tok = await MS_HTTP("POST", f"https://login.microsoftonline.com/{tenant()}/oauth2/v2.0/token", data={
        "client_id": os.getenv("SASHA_MS_CLIENT_ID", "").strip(), "client_secret": os.getenv("SASHA_MS_CLIENT_SECRET", "").strip(),
        "code": request.query_params.get("code", ""), "redirect_uri": os.getenv("SASHA_MS_REDIRECT", "").strip(),
        "grant_type": "authorization_code", "scope": SCOPE})
    if s != 200 or not tok.get("refresh_token") or not tok.get("access_token"):
        log.error("[outlook] the code exchange failed: HTTP %s %s", s, tok.get("error"))
        return RedirectResponse(web_url("outlook=failed"), status_code=303)
    granted = {g.lower() for g in (tok.get("scope") or "").split()}
    if not ({"mail.read", MAIL_READ.lower()} & granted):
        return RedirectResponse(web_url("outlook=scopes_missing"), status_code=303)
    account, now, c = st["a"], NOW(), consent(st["v"])
    old = await link(account)
    item_id = str(uuid.uuid4())
    try:
        sealed = await VC.seal(account, item_id, "oauth", json.dumps({"refresh_token": tok["refresh_token"]}).encode())
    except kms.VaultClosed:
        return RedirectResponse(web_url("outlook=vault_closed"), status_code=303)
    await VC.STORE.create({"id": item_id, "account_id": account, "provider": PROVIDER, "label": LABEL, "kind": "oauth", **sealed,
                           "special_category": False, "consent_at": now, "consent_wording_version": c["version"],
                           "consent_text_sha256": c["sha256"], "created_at": now, "updated_at": now})
    await VC.STORE.event(account, item_id, "created", {"kind": "oauth", "provider": PROVIDER, "purpose": "outlook_read",
                                                       "consent_version": c["version"], "consent_sha256": c["sha256"]}, now)
    if old:
        await VC.STORE.revoke(account, old["id"], now)
    return RedirectResponse(web_url("outlook=connected"), status_code=303)


@router.delete("")
async def outlook_disconnect(request: Request):
    """The access is deleted here. Microsoft has no per-app token revoke a mail-only app may call: the person removes Sasha's
    permission at Microsoft themselves (the address is said)."""
    from .account import account_for
    from .vault import crypto as VC
    account = account_for(request)
    lk = await link(account)
    if not lk:
        return {"disconnected": False}
    await VC.STORE.revoke(account, lk["id"], NOW())
    return {"disconnected": True, "at_microsoft": "to remove Sasha's permission at Microsoft too: https://myapps.microsoft.com → Sasha → Revoke permissions"}


__all__ = ["router", "consent", "configured", "invited", "link", "PROVIDER", "LABEL", "SCOPE"]
