"""Sasha 334 · THE KEEP RESOLVER (CR 163's ask): AgAPI, server to server, opens a keep:<id> reference AT BOOKING TIME ONLY — inside its one
supplier call (the airline's order, the stay). docs/sasha/S-334-group-v1.md.

Sasha 378 · CR 189 (agapi docs/agapi/cr189-sasha-half.md): a reference opens ONLY for its own traveller, bound in the SIGNED call — checked
against Sasha's own records. The in-process allow-list (grant / revoke, lost on a restart, trusting the reference for its window) is gone.

  resolve(body, signature)   POST /api/booking/keep/resolve. The body is canonical JSON (keep-resolve/1, vendored vector:
                             booking_signer/vectors/keep_resolve.json) {account, at, booking_id, member, movement_id, person, purpose, ref, v};
                             x-agapi-signature = hex HMAC-SHA256(SASHA_KEEP_RESOLVE_SECRET, those exact bytes). In this order:
                               1 the signature over the bytes, `at` within 60 s, v == keep-resolve/1                 (401 / 400 bad_body)
                               2 `account` is Sasha's OWN AgAPI account (usage.get, asked of AgAPI itself)          403 not_this_account
                               3 the movement exists and is `person`'s                                              403 not_this_movement
                               4 `member` is on that movement                                                       403 not_this_member
                               5 the reference is in that member's own vault (owner_of: the PERSON's, Sasha 351)    403 not_this_member
                               6 purpose is group.book or group.swap                                                400 bad_body
                             each refusal: ONE log line with its rule and the booking_id — never the reference or a value; nothing opened.

The values pass THROUGH: never logged (counts and rules only), never kept, never in a model's context.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import time
from typing import Any, Dict, Optional, Set

log = logging.getLogger("booking_signer.keep_resolver")
SKEW_S = 60
VERSION = "keep-resolve/1"
from kanoe_contract import OP  # noqa: E402 · THE ONE generated contract (CR 186)
PURPOSES = (OP.GROUP_BOOK, OP.GROUP_SWAP)
ACCOUNTS = None   # tests replace it: async () → {Sasha's own AgAPI account ids}
_OWN: Dict[str, Any] = {}   # AgAPI's URL → Sasha's account id there (asked of AgAPI itself, usage.get) — this process


def secret() -> Optional[str]:
    s = os.getenv("SASHA_KEEP_RESOLVE_SECRET", "").strip()
    return s or None


class Refused(Exception):
    def __init__(self, status: int, rule: str):
        super().__init__(rule)
        self.status, self.rule = status, rule


def sign(body: bytes, key: Optional[str] = None) -> str:
    return hmac.new((key or secret() or "").encode(), body, hashlib.sha256).hexdigest()


def canonical(d: Dict[str, Any]) -> bytes:
    """keep-resolve/1's bytes: sorted keys, no spaces, UTF-8 (the vector's own)."""
    return json.dumps(d, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


async def own_accounts() -> Set[str]:
    """Sasha's OWN account on the AgAPI that calls this resolver — the one its group bookings go to (agapi_route.client_for, the ONE
    route) — read from AgAPI itself (usage.get answers `account`), once per process. Never a config value of Sasha's."""
    if ACCOUNTS is not None:
        return set(await ACCOUNTS())
    from agapi import agapi_route as AR
    from . import group_book as GB
    import httpx  # noqa: F401
    url, key = await AR.client_for(GB.FAMILY)
    if url in _OWN:
        return {_OWN[url]}
    if not key:
        return set()
    try:
        from datetime import datetime, timedelta, timezone
        day = datetime.now(timezone.utc).replace(microsecond=0)
        win = {"from": (day - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ"), "to": day.strftime("%Y-%m-%dT%H:%M:%SZ")}   # its required window
        env = await AR.post(url, key, OP.USAGE_GET, win, {"Authorization": f"Bearer {key}", "content-type": "application/json",
                                                       "Idempotency-Key": "s378_usage_" + os.urandom(12).hex()}, 20.0)
        acct = (env.get("result") or {}).get("account") if env.get("ok") else None
    except Exception as e:
        log.warning("[keep_resolver] AgAPI's account wasn't read: %s", type(e).__name__)
        acct = None
    if not acct:   # unread: asked again next time (never cached as "nobody"), and nothing opens meanwhile
        return set()
    _OWN[url] = str(acct)
    return {str(acct)}


def _refuse(status: int, rule: str, booking_id: Any) -> Refused:
    log.warning("[keep_resolver] refused %s (booking %s) — nothing opened", rule, str(booking_id or "?")[:40])
    return Refused(status, rule)


async def resolve(body: bytes, signature: Optional[str], now: Optional[float] = None) -> Dict[str, Any]:
    key = secret()
    if not key:
        raise Refused(503, "resolver_not_configured")
    if not signature or not hmac.compare_digest(signature, sign(body, key)):
        raise Refused(401, "bad_signature")
    try:
        d = json.loads(body)
        ref, at = str(d["ref"]), int(d["at"])
        account, person, member, movement, booking, purpose = (str(d[k]) for k in ("account", "person", "member", "movement_id", "booking_id", "purpose"))
    except Exception:
        raise Refused(400, "bad_body") from None
    if d.get("v") != VERSION:
        raise _refuse(400, "bad_body", d.get("booking_id"))
    now = now or time.time()
    if abs(now - at) > SKEW_S:
        raise Refused(401, "stale")
    if account not in await own_accounts():
        raise _refuse(403, "not_this_account", booking)
    from . import group_book as GB, groups as G
    try:
        mv = await G.store().movement(person, movement)   # the movement, AS this person's (its owner) — anyone else's answers None
    except Exception:
        mv = None
    if not mv:
        raise _refuse(403, "not_this_movement", booking)
    m = next((x for x in await G.store().members(mv["id"]) if str(x["id"]) == member), None)
    if not m:
        raise _refuse(403, "not_this_member", booking)
    if purpose not in PURPOSES:
        raise _refuse(400, "bad_body", booking)
    from agapi import keep as K, s2_keep as KEEP
    owner = GB.owner_of(m)   # Sasha 351 · the PERSON's vault
    st = KEEP._store()
    it = await st.item(owner, ref[5:]) if ref.startswith("keep:") else None
    if not it:   # not this member's reference
        raise _refuse(403, "not_this_member", booking)
    dek = await KEEP._dek(owner, create=False)
    values = K.open_(dek, K.item_aad(owner, owner, str(it["id"]), it["type"]), bytes(it["nonce"]), bytes(it["ciphertext"]))
    await st.touch(it["id"])
    log.info("[keep_resolver] one %s opened for booking %s", it["type"], booking[:40])   # the TYPE only — never a value, a mask or a reference
    return {"values": values, "type": it["type"]}


__all__ = ["resolve", "sign", "canonical", "secret", "own_accounts", "Refused", "SKEW_S", "VERSION"]
