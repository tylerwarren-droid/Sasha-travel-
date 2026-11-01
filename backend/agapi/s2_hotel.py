"""Sasha 235 · UPGRADE MY ROOM (/s2 only): a request to the hotel they're booked at.

Sasha 319 · it was drafted to the address the hotel publishes on its own site and sent by Sasha's own email (send_email) — Sasha's own
send to a venue, gone: AgAPI's acts are the one sender to venues, and AgAPI has no "ask the hotel about my stay" act yet. The request
is handed to Tyler; nothing is sent. (Its test hotel and scripted reply went with it.)
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Dict, List

log = logging.getLogger("agapi.s2_hotel")
TEST_HOTEL = "Kanoe Test Hotel"
REPLIES: Dict[str, dict] = {}   # account → the hotel's latest reply (their words), for "did they answer?"


def plain_hotel(title: str) -> str:
    from booking_signer import hotel_test as HT
    return str(title or "").replace(HT.MARK, "").strip() or "your hotel"


async def hotel_request(ctx, a: dict) -> dict:
    from agapi.v0 import ToolError
    from agapi import s2_manage as M
    if a.get("check_reply"):
        r = REPLIES.get(ctx.account)
        if not r:
            return {"status": "no_reply_yet", "say": "Say plainly there's no reply from the hotel yet."}
        return {"status": "replied", "their_reply": r, "how": "Say who replied and quote their words exactly; then, if it's not English, a short translation."}
    stays = [p for p in await M.plans_of(ctx.account) if p.get("kind") == "hotel" and p.get("status") == "booked"]
    if a.get("hotel"):
        want = str(a["hotel"]).lower()
        stays = [s for s in stays if want in plain_hotel(s.get("title")).lower()] or stays
    stays.sort(key=lambda s: str(s.get("when") or ""))
    today = datetime.now(timezone.utc).date().isoformat()
    stay = next((s for s in stays if str(s.get("when") or "") >= today), stays[-1] if stays else None)
    if not stay:
        raise ToolError("no_stay", "there's no booked hotel stay on their account to ask about")
    # Sasha 319 · an email to the hotel's front desk was Sasha's own send to a venue (its address read off their site) — gone: AgAPI's acts
    # are the one sender, and AgAPI has no "ask the hotel about my stay" act yet. Nothing is sent: Tyler takes it.
    from agapi import venues as VN
    return {"status": "to_tyler", "venue": plain_hotel(stay.get("title")), "sent": False, "line": VN.TO_TYLER,
            "how": "Say `line` word for word — nothing else."}


def tools() -> List[dict]:
    from agapi.v0 import _t
    appr = {"approval": {"type": "object", "properties": {"said": {"type": "string"}}}}
    return [
        _t("hotel_request", "Austen", hotel_request, "A request to the hotel they're booked at — 'Upgrade my room' → ask='upgrade' (or "
           "their words: a late check-out, a quiet room…). Sasha 319: nothing is written to the hotel from here (AgAPI is the one "
           "sender to venues and has no such act yet) — it answers status to_tyler: say its `line` word for word. "
           "check_reply=true: has the hotel answered?",
           {"ask": {"type": "string"}, "hotel": {"type": "string"}, "check_reply": {"type": "boolean"}, **appr}, [],
           {"type": "object", "properties": {"status": {"type": "string"}}},
           ["no_stay", "no_contact", "no_explicit_yes", "invalid_input"], austen=True),
    ]
