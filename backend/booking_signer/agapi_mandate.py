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
    turn = str(getattr(ctx, "turn", "") or "")
    # Sasha 372 · the INSTRUCTION's own id (this turn), with the conversation it was said in — two instructions, two proofs
    return {"kind": "in_app", "session_id": sid, "instruction_id": turn} if sid and turn else None


def _minor(eur: Optional[float]) -> Optional[Dict[str, Any]]:
    return {"amount_minor": int(round(float(eur) * 100)), "currency": "EUR"} if eur is not None else None


def limits_for(mv: dict, members: List[dict]) -> Optional[Dict[str, Any]]:
    """Sasha 371b · CR 184: EACH worker's OWN limits, from the ONE rules record (groups.limit_for — their own, else their grade's), as AgAPI's
    per_worker list [{worker, flight_return_max?, stay_night_max?}] (money in minor units). One meaning on both sides: the worker's flights
    together (out + back) against flight_return_max, each night against stay_night_max. A worker with none is LEFT OUT — AgAPI asks for
    theirs (limits_missing); another worker's limit is never used. None: nobody on the trip has a limit (asked before anything is sent)."""
    from . import groups as G
    out = []
    for m in members:
        lim = G.limit_for(mv.get("rules") or {}, m)
        row = {k: _minor(lim[src]) for k, src in (("flight_return_max", "flight_return_eur"), ("stay_night_max", "hotel_night_eur"))
               if lim.get(src) is not None}
        if row:
            out.append({"worker": str(m["id"]), **row})
    return {"per_worker": out} if out else None


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
    return {"movement_id": str(mv["id"]), "workers": [m["id"] for m in members], "destination": codes,   # Sasha 371b · CR 184: the movement
            "from": str(mv.get("starts_on") or "")[:10], "to": str(mv.get("ends_on") or "")[:10]}


def mandate_sha256(end_user: str, words: str, scope: dict, limits: dict, expires_in_minutes: int) -> str:
    body = {"end_user": end_user, "words": words, "scope": scope, "limits": limits, "expires_in_minutes": expires_in_minutes}
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()


def sign(proof: Dict[str, str], account: str, sha: str, t: Optional[int] = None, nonce: Optional[str] = None,
         per_instruction: bool = True) -> Optional[Dict[str, Any]]:
    """The proof as AgAPI checks it (1866): kind whatsapp — id the message id, who the wa_id digits; in_app — id the INSTRUCTION's id
    (Sasha 372: the turn / tap it was given in), who the person (<person> of their end user "sasha:<person>", AgAPI access.person_of).
    per_instruction False: AgAPI's published contract has no instruction_id yet (CR's half not live) → today's form, id = the session id
    (DEBT, Sasha 372: deleted the day CR's half is live). None: no secret here (nothing is sent unsigned)."""
    secret = os.getenv("SASHA_AGAPI_TAP_SECRET", "")
    if not secret or not proof:
        return None
    t = int(t if t is not None else time.time())
    nonce = nonce or secrets.token_hex(16)
    if proof["kind"] == "whatsapp":
        ident, who = proof["message_id"], proof["wa_id"]
        extra = {"wa_id": who, "message_id": ident}
    elif per_instruction and proof.get("instruction_id"):
        ident, who = proof["instruction_id"], account   # Sasha 372 · the instruction signs it; cr/182 access.person_of → <person>
        extra = {"session_id": proof.get("session_id") or "", "instruction_id": ident}
    else:
        ident, who = proof["session_id"], account   # today's contract (CR's half not live): the session id
        extra = {"session_id": ident}
    sig = hmac.new(secret.encode(), f"{t}.{nonce}.mandate.{proof['kind']}.{ident}.{who}.{sha}".encode(), hashlib.sha256).hexdigest()
    return {"kind": proof["kind"], "t": t, "nonce": nonce, **extra, "signature": sig}


CONTRACT = None   # tests replace it: (account) → bool — does AgAPI's published approvals.mandate take proof.instruction_id?
_CONTRACT_SEEN: Dict[str, Any] = {}   # AgAPI's url → (takes it, when read)
CONTRACT_S = 600


async def takes_instruction(account: str) -> bool:
    """Sasha 372 · AgAPI's OWN published contract (its /openapi.json: approvals.mandate's proof) decides the proof's form — never a flag of
    Sasha's. Read once per 10 minutes per AgAPI; unreadable → today's form (which today's AgAPI accepts)."""
    if CONTRACT is not None:
        return bool(await CONTRACT(account))
    from . import group_book as GB
    from agapi import agapi_route as AR
    url, _ = await AR.client_for(GB.FAMILY, account)
    seen = _CONTRACT_SEEN.get(url)
    if seen and time.time() - seen[1] < CONTRACT_S:
        return seen[0]
    takes = False
    try:
        import httpx
        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as c:
            r = await c.get(f"{url}/openapi.json")
        sch = r.json()["paths"]["/v1/approvals.mandate"]["post"]["requestBody"]["content"]["application/json"]["schema"]
        takes = "instruction_id" in ((sch.get("properties") or {}).get("proof") or {}).get("properties", {})
    except Exception as e:
        log.warning("[mandate] AgAPI's contract wasn't read: %s", type(e).__name__)
        return False
    _CONTRACT_SEEN[url] = (takes, time.time())
    return takes


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
    signed = sign(proof, account, sha, per_instruction=await takes_instruction(account))
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


__all__ = ["proof_from", "limits_for", "scope_for", "mandate_sha256", "sign", "register", "takes_instruction", "EXPIRES_MIN"]
