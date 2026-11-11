"""Sasha 367 · THE MANAGER'S INSTRUCTION, REGISTERED ONCE AT AgAPI AS A SIGNED MANDATE (CR 182, mailbox 1866) — the ONE source of the yes for
every worker booked under it. Never the instruction's text sent as a yes, never a contact made up.

  proof_from(ctx)                      the door's proof, as IDS only (kept on the trip record, never a token): WhatsApp → the instruction's
                                       message id + the organiser's wa_id; in the app → the session id the instruction was typed/spoken in
  limits_for(mv, members)              the company's limits on the record → AgAPI's {flight_max, stay_night_max} (None: none on the record)
  scope_for(mv, members)               {workers (member ids, in order), destination (the city's IATA codes), from, to}
  register(account, words, mv, members, proof) → {mandate_id, expires_at} | {code, why}
                                       ONE POST approvals.mandate, signed with SASHA_AGAPI_TAP_SECRET:
                                       hex HMAC-SHA256 of "<t>.<nonce>.mandate.<kind>.<id>.<who>.<mandate_sha256>"
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import time
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)

EXPIRES_MIN = 360
PLACE = None   # tests replace it: (city) → [IATA codes]


def proof_from(ctx: Any) -> Optional[Dict[str, str]]:
    """The door's proof that the instruction came from the organiser — ids only. WhatsApp: the signed inbound (agapi.venue_submit.WA, set by
    the webhook once Twilio's signature checked); in the app: the conversation's session id. None: neither (nothing can be signed)."""
    from agapi import venue_submit as VS
    if getattr(ctx, "via", "page") == "wa":
        w = VS.WA.get() or {}
        wa_id, mid = re.sub(r"\D", "", str(w.get("wa_id") or "")), str(w.get("message_id") or "")
        return {"kind": "whatsapp", "wa_id": wa_id, "message_id": mid} if wa_id and mid else None
    sid = str(getattr(ctx, "session", "") or "")
    return {"kind": "in_app", "session_id": sid} if sid else None


def _minor(eur: Optional[float]) -> Optional[Dict[str, Any]]:
    return {"amount_minor": int(round(float(eur) * 100)), "currency": "EUR"} if eur is not None else None


def limits_for(mv: dict, members: List[dict]) -> Optional[Dict[str, Any]]:
    """The company's limits, from the record (each person's own: their grade's, or theirs by name) → AgAPI's outer bounds: the highest any
    worker on THIS trip may spend (each worker's own limit is still held by the plan — over it, they're asked, never booked)."""
    from . import groups as G
    lims = [G.limit_for(mv.get("rules") or {}, m) for m in members]
    fl = [float(x["flight_return_eur"]) for x in lims if x.get("flight_return_eur") is not None]
    st = [float(x["hotel_night_eur"]) for x in lims if x.get("hotel_night_eur") is not None]
    out = {k: v for k, v in (("flight_max", _minor(max(fl)) if fl else None), ("stay_night_max", _minor(max(st)) if st else None)) if v}
    return out or None


async def _codes(city: str) -> List[str]:
    """The destination as IATA codes: the city's own code and its airports' (Duffel's places) — AgAPI matches the flights against them."""
    if PLACE is not None:
        return list(await PLACE(city))
    from . import travel as T
    out: List[str] = []
    try:
        s, j = await T.HTTP("GET", "/places/suggestions", params={"query": city})
        rows = (j or {}).get("data") or [] if s == 200 else []
        best = next((p for p in rows if p.get("type") == "city"), None) or next((p for p in rows if p.get("type") == "airport"), None)
        if best:
            out += [best.get("iata_city_code") or best.get("iata_code")] + [a.get("iata_code") for a in best.get("airports") or []]
    except Exception as e:
        log.warning("[mandate] the destination's codes weren't read: %s", type(e).__name__)
    return [c for c in out if c]


async def scope_for(mv: dict, members: List[dict]) -> Dict[str, Any]:
    codes = sorted({c.upper() for c in await _codes(mv.get("destination") or "")})
    return {"workers": [m["id"] for m in members], "destination": codes, "from": str(mv.get("starts_on") or "")[:10],
            "to": str(mv.get("ends_on") or "")[:10]}


def mandate_sha256(end_user: str, words: str, scope: dict, limits: dict, expires_in_minutes: int) -> str:
    body = {"end_user": end_user, "words": words, "scope": scope, "limits": limits, "expires_in_minutes": expires_in_minutes}
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()


def sign(proof: Dict[str, str], account: str, sha: str, t: Optional[int] = None, nonce: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """The proof as AgAPI checks it (1866): kind whatsapp — id the message id, who the wa_id digits; in_app — id the session id, who
    "sasha:<person>". None: no secret here (nothing is sent unsigned)."""
    secret = os.getenv("SASHA_AGAPI_TAP_SECRET", "")
    if not secret or not proof:
        return None
    t = int(t if t is not None else time.time())
    nonce = nonce or secrets.token_hex(16)
    if proof["kind"] == "whatsapp":
        ident, who = proof["message_id"], proof["wa_id"]
        extra = {"wa_id": who, "message_id": ident}
    else:
        ident, who = proof["session_id"], f"sasha:{account}"
        extra = {"session_id": ident}
    sig = hmac.new(secret.encode(), f"{t}.{nonce}.mandate.{proof['kind']}.{ident}.{who}.{sha}".encode(), hashlib.sha256).hexdigest()
    return {"kind": proof["kind"], "t": t, "nonce": nonce, **extra, "signature": sig}


async def register(account: str, words: str, mv: dict, members: List[dict], proof: Optional[Dict[str, str]]) -> Dict[str, Any]:
    """ONE approvals.mandate for the instruction → {mandate_id, expires_at} or {code, why} (said by the caller, never guessed around)."""
    from . import group_book as GB
    limits = limits_for(mv, members)
    if not limits:
        return {"code": "limits_needed", "why": "To book on your word I need the company's limits — the most for a return flight and for a hotel "
                                                "night (per grade if they differ). What are they?"}
    if not proof:
        return {"code": "no_proof", "why": "I couldn't confirm this came from you, so I haven't booked anything — send the instruction again."}
    end_user = await GB._organiser(account)
    if not end_user:
        return {"code": "upstream_unreachable", "why": "The booking system didn't answer — nothing was booked. Say it again in a minute."}
    if proof["kind"] == "whatsapp":   # the number as THEIR end user's destination (AgAPI counts only a verified one)
        await GB._call(account, "users.register", {"external_ref": f"sasha:{account}", "destinations": [{"channel": "whatsapp", "value": "+" + proof["wa_id"]}]})
    scope = await scope_for(mv, members)
    words = (words or "")[:500]
    sha = mandate_sha256(end_user, words, scope, limits, EXPIRES_MIN)
    signed = sign(proof, account, sha)
    if not signed:
        return {"code": "not_configured", "why": "Booking on your word isn't switched on here — nothing was booked."}
    r = await GB._call(account, "approvals.mandate", {"end_user": end_user, "words": words, "scope": scope, "limits": limits,
                                                      "expires_in_minutes": EXPIRES_MIN, "proof": signed})
    if r.get("ok"):
        res = r.get("result") or {}
        return {"mandate_id": res.get("mandate_id"), "expires_at": res.get("expires_at")}
    code = (r.get("error") or {}).get("code") or "refused"
    log.warning("[mandate] AgAPI refused the mandate: %s", code)   # the code only — never the proof
    return {"code": code, "why": "The booking system didn't accept your instruction as the yes — nothing was booked."}


__all__ = ["proof_from", "limits_for", "scope_for", "mandate_sha256", "sign", "register", "EXPIRES_MIN"]
