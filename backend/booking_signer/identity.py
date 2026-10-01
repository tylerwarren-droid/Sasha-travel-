"""S-62 step 1 · WHO a booking request acts for — a VERIFIED account, never one a header merely names.

The booking key (gate.py) proves a call came through the frontend's proxy. On its own it names nobody: one leaked key
must never equal every account. So, after the key, each request carries exactly one of:
  · `Authorization: Bearer <a Supabase access token>` — a signed-in guest. Its signature is checked against Sasha's
    Supabase project's PUBLIC keys (JWKS, ES256), with the issuer, audience and expiry; the account is its `sub`;
  · `x-sasha-session: founder` — the founder's own session, checked by the proxy. It maps to FOUNDER_ACCOUNT_ID once he
    has an auth user of his own; until that is set, to the demo account his bookings have always been under;
  · `x-sasha-session: demo` — the demo account, only when the founder's session asks for it explicitly.
None of them → no account, and every route that needs one refuses (account.account_for: 401 account_required).
⛔ Fails closed: keys unreachable, a forged, expired or wrongly-issued token, an unknown session word → refused.
"""
from __future__ import annotations

import os
import re
import time
from typing import Any, Awaitable, Callable, Dict, List, Optional

from fastapi import HTTPException, Request

AUDIENCE = "authenticated"
_PROJECT = re.compile(r"https://[a-z0-9-]+\.supabase\.co")


def project_url() -> Optional[str]:
    """S-69 · SASHA_SUPABASE_URL, read at call time — no project ref in code, so a move is an env change. None if unset."""
    u = os.getenv("SASHA_SUPABASE_URL", "").strip().rstrip("/")
    return u if _PROJECT.fullmatch(u) else None


def issuer() -> str:
    return f"{project_url()}/auth/v1"
ALGORITHMS = ["ES256"]
JWKS_TTL_S = 600
SESSION_HEADER = "x-sasha-session"
_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")

#: () → the JWKS document. Tests replace it; None = an HTTPS GET of the project's JWKS (issuer()/.well-known/jwks.json).
FetchJwks = Callable[[], Awaitable[Dict[str, Any]]]
FETCH: Optional[FetchJwks] = None
_cache: Dict[str, Any] = {"keys": None, "at": 0.0}


def _refuse(rule: str, message: str) -> HTTPException:
    return HTTPException(401, {"ok": False, "rule": rule, "message": message})


async def _fetch() -> Dict[str, Any]:
    if FETCH is not None:
        return await FETCH()
    import httpx
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.get(f"{issuer()}/.well-known/jwks.json")
        r.raise_for_status()
        return r.json()


async def _keys(force: bool = False) -> List[dict]:
    """The project's public signing keys — public, so held in memory for ten minutes; refetched on an unknown kid."""
    if force or _cache["keys"] is None or time.time() - _cache["at"] > JWKS_TTL_S:
        doc = await _fetch()
        _cache["keys"], _cache["at"] = list(doc.get("keys") or []), time.time()
    return _cache["keys"]


def reset_cache() -> None:
    _cache["keys"], _cache["at"] = None, 0.0


async def verify_token(token: str) -> str:
    """A Supabase access token → its account id (`sub`), or a 401 saying why. Nothing in it is trusted unverified."""
    from jose import jwt
    from jose.exceptions import ExpiredSignatureError, JWTClaimsError, JWTError
    if project_url() is None:   # ⛔ fail closed: with no project configured, no token can be verified — and it says so
        raise HTTPException(503, {"ok": False, "rule": "sign_in_not_configured",
                                  "message": "SASHA_SUPABASE_URL is not set on this server, so no sign-in can be checked; nothing was done"})
    try:
        kid = jwt.get_unverified_header(token).get("kid")
    except JWTError:
        raise _refuse("account_token_invalid", "the sign-in token is not a token") from None
    try:
        keys = await _keys()
        key = next((k for k in keys if k.get("kid") == kid), None)
        if key is None:
            key = next((k for k in await _keys(force=True) if k.get("kid") == kid), None)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(503, {"ok": False, "rule": "account_keys_unavailable",
                                  "message": f"the sign-in keys could not be read ({type(e).__name__}); nothing was done"}) from None
    if key is None:
        raise _refuse("account_token_invalid", "the sign-in token was not signed by Sasha's sign-in keys")
    try:
        claims = jwt.decode(token, key, algorithms=ALGORITHMS, audience=AUDIENCE, issuer=issuer())
    except ExpiredSignatureError:
        raise _refuse("account_token_expired", "the sign-in has expired — sign in again") from None
    except (JWTClaimsError, JWTError):
        raise _refuse("account_token_invalid", "the sign-in token did not verify") from None
    sub = str(claims.get("sub") or "")
    if not _UUID.fullmatch(sub) or claims.get("role") != "authenticated":
        raise _refuse("account_token_invalid", "the sign-in token names no signed-in account")
    return sub


def founder_account() -> str:
    """FOUNDER_ACCOUNT_ID (his own auth user) when set and well-formed; until then, the demo account."""
    from .account import DEMO_ACCOUNT_ID
    v = os.getenv("FOUNDER_ACCOUNT_ID", "").strip().lower()
    return v if _UUID.fullmatch(v) else DEMO_ACCOUNT_ID


async def resolve(request: Request) -> Optional[str]:
    """The verified account for this request, or None. Called by the gate after the booking key."""
    from .account import DEMO_ACCOUNT_ID
    auth = request.headers.get("authorization", "")
    if auth:
        scheme, _, token = auth.partition(" ")
        if scheme.lower() != "bearer" or not token.strip():
            raise _refuse("account_token_invalid", "the Authorization header is not a bearer token")
        return await verify_token(token.strip())
    session = request.headers.get(SESSION_HEADER, "").strip().lower()
    if not session:
        return None
    if session == "founder":
        return founder_account()
    if session == "demo":
        return DEMO_ACCOUNT_ID
    raise _refuse("account_session_unknown", f"{SESSION_HEADER} is founder or demo")


__all__ = ["resolve", "verify_token", "founder_account", "reset_cache", "project_url", "issuer", "SESSION_HEADER", "AUDIENCE"]
