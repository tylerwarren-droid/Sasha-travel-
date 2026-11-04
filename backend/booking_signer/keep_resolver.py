"""Sasha 334 · THE KEEP RESOLVER (CR 163's ask): AgAPI, server to server, opens a keep:<id> reference AT BOOKING TIME ONLY — inside its one
supplier call (the airline's order, the stay). docs/sasha/S-334-group-v1.md.

  grant(member, refs, ttl)   Sasha itself, the moment it sends group.book / group.swap for ONE worker: those refs may be opened for the next
                             few minutes (the booking in flight) — and only those, only for that worker
  resolve(body, signature)   POST /api/booking/keep/resolve, HMAC-SHA256 of the body (SASHA_KEEP_RESOLVE_SECRET, shared with AgAPI). Refused:
                             unsigned · a bad signature · stale (`at` more than 60 s from now) · a reference with no live grant (a person not
                             in the booking Sasha is making). → {values}: opened by the Keep's own code (keep.py open_, the member's own key)

The values pass THROUGH: never logged (counts and rules only), never kept, never in a model's context.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import time
from typing import Any, Dict, List, Optional

log = logging.getLogger("booking_signer.keep_resolver")
SKEW_S = 60
GRANT_S = 600
_GRANTS: Dict[str, Dict[str, Any]] = {}   # ref → {member, until} — this process (one worker, R3); a restart drops them (a booking re-grants)


def secret() -> Optional[str]:
    s = os.getenv("SASHA_KEEP_RESOLVE_SECRET", "").strip()
    return s or None


def grant(member_id: str, refs: List[str], ttl: int = GRANT_S) -> None:
    until = time.time() + ttl
    for r in refs:
        if r:
            _GRANTS[r] = {"member": member_id, "until": until}


def revoke(refs: List[str]) -> None:
    for r in refs:
        _GRANTS.pop(r, None)


class Refused(Exception):
    def __init__(self, status: int, rule: str):
        super().__init__(rule)
        self.status, self.rule = status, rule


def sign(body: bytes, key: Optional[str] = None) -> str:
    return hmac.new((key or secret() or "").encode(), body, hashlib.sha256).hexdigest()


async def resolve(body: bytes, signature: Optional[str], now: Optional[float] = None) -> Dict[str, Any]:
    key = secret()
    if not key:
        raise Refused(503, "resolver_not_configured")
    if not signature or not hmac.compare_digest(signature, sign(body, key)):
        raise Refused(401, "bad_signature")
    try:
        d = json.loads(body)
        ref, at = str(d["ref"]), int(d["at"])
    except Exception:
        raise Refused(400, "bad_body") from None
    now = now or time.time()
    if abs(now - at) > SKEW_S:
        raise Refused(401, "stale")
    g = _GRANTS.get(ref)
    if not g or g["until"] < now:
        raise Refused(403, "not_in_this_booking")
    from agapi import keep as K, s2_keep as KEEP
    member = g["member"]
    st = KEEP._store()
    it = await st.item(member, ref[5:])
    if not it:
        raise Refused(404, "not_found")
    dek = await KEEP._dek(member, create=False)
    values = K.open_(dek, K.item_aad(member, member, str(it["id"]), it["type"]), bytes(it["nonce"]), bytes(it["ciphertext"]))
    await st.touch(it["id"])
    log.info("[keep_resolver] one %s opened for a booking", it["type"])   # the TYPE only — never a value, a mask or a reference
    return {"values": values, "type": it["type"]}


__all__ = ["grant", "revoke", "resolve", "sign", "secret", "Refused", "SKEW_S", "GRANT_S"]
