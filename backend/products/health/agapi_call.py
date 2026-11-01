"""Sasha 319 · a clinic is called through AgAPI's CALL ACT — the one sender to venues — never Sasha's own /api/booking/calls.

  prepare(...)  venue.prepare_booking with the clinic's number (call {phone, source "venue"}) → the CALL's read-back (venue.submit_booking
                route "call", no approval yet). Nothing is dialled.
  place(...)    their yes → venue.submit_booking (the WhatsApp reply / the app tap is the approval, as every act's) → AgAPI's call_plan →
                Sasha dials ONLY that plan (agapi.venue_calls.dial; simulated on the sandbox). AgAPI's rules decide when (R10, opening
                hours) and its words are what is said.
CR 149 · a clinic known only by its phone is a venue AgAPI records (proved on agapi-sandbox, 1 Nov). No venues key on this server, or a
clinic AgAPI still can't record → nothing is prepared or dialled: Tyler takes it (agapi.venues.TO_TYLER)."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, Optional

log = logging.getLogger("products.health.agapi_call")


async def prepare(account: str, clinic: str, phone: str, at: datetime, who: Dict[str, Any], what: str,
                  website: Optional[str] = None) -> Dict[str, Any]:
    """→ {ok, held: {read_back_id, prepared_id, sha, lines, …}} or {ok: False, say} (nothing prepared, nothing dialled)."""
    from agapi import venue_submit as VS, venues as VN
    from booking_signer import guest_receipt as GR
    person = {"name": who.get("name"), "phone": who.get("mobile_e164"), "email": await GR.address_of(account)}
    place = {"name": clinic, "category": "clinic", **({"website": website} if website else {})}
    p = await VS.prepare(account, place, person, at.strftime("%Y-%m-%d"), at.strftime("%H:%M"), 1, notes=what,
                         call={"phone": phone, "source": "venue"})
    if not p.get("ok"):
        if p["error"]["code"] in ("not_configured", "invalid_input"):   # no venues key here / no venue AgAPI can put on a record
            log.info("[health] %s: not prepared by AgAPI (%s) — Tyler's, nothing dialled", clinic, p["error"]["code"])
            return {"ok": False, "say": VN.TO_TYLER}
        return {"ok": False, "say": f"Not prepared — {p['error']['message']}. Nothing was dialled."}
    rb = await VS.read_back(account, p["prepared_id"], route="call")
    if not rb.get("ok"):
        return {"ok": False, "say": f"Not prepared — {rb['error']['message']}. Nothing was dialled."}
    return {"ok": True, "held": {"read_back_id": rb["read_back_id"], "prepared_id": p["prepared_id"], "sha": rb["sha256"],
                                 "end_user": rb.get("end_user"), "lines": rb["lines"], "venue": clinic, "rung": "agapi_call",
                                 "when": at.strftime("%Y-%m-%dT%H:%M"), "party": 1, "name": who.get("name")}}


async def place(account: str, held: Dict[str, Any], said: str, summary: str) -> Dict[str, Any]:
    """Their yes → {status calling | not_called, say, call_id?} — the call AgAPI's act allows, dialled only from its plan."""
    from agapi import venue_calls as VC, venue_submit as VS
    r = await VS.submit(account, held, said)
    if not r.get("ok"):
        return {"status": "not_called", "say": f"Not called — {r['error']['message']}. Nothing was dialled."}
    if r.get("status") == "confirm_number":
        return {"status": "not_called", "say": "Your WhatsApp number isn't confirmed yet, so I can't take that yes — nothing was dialled."}
    if r.get("status") != "calling":
        return {"status": "not_called", "say": f"⚠ {r.get('say') or 'The call did not go through'} — nothing is booked."}
    d = await VC.dial(account, r, {**held, "summary": summary, "timezone": "Europe/Madrid"})
    return {"status": "calling", "say": r.get("say") or "", "dial": d.get("status"), **({"call_id": d["call_id"]} if d.get("call_id") else {}),
            "act_id": r.get("act_id")}
