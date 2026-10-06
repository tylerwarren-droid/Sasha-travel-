"""Sasha 165 (4) · HAND-OFF: "send this to my phone" / "Continue on my phone" on the web → ONE WhatsApp to the account's phone,
"Picking up: <trip> — <the open item and its next step>. Reply to carry on." On either device, "carry on" or "what was I
doing?" answers with the trip, day by day (itinerary_q.TRIP)."""
from __future__ import annotations

import re
from typing import Optional

ASK = re.compile(r"\b(?:send (?:this|it|that|my (?:trip|itinerary|plan)) to my phone|continue on my phone|pick (?:this|it) up on my phone)\b", re.I)


def asked(message: str) -> bool:
    return bool(ASK.search(message or ""))


async def summary(account: str) -> Optional[str]:
    """"<trip> — <open item and next step>", from the account's plan and bookings; None with neither."""
    from . import guest_whatsapp as GW, plan_store as PS
    p = await PS.latest(account)
    s, j = await GW.api(account, "GET", "/api/booking/reservations")
    rows = (j or {}).get("reservations") or [] if s == 200 else []
    if p:
        from . import journeys as JN   # Sasha 177 · its own bookings only
        merged = PS.merge(p, JN.for_journey(rows, p.get("trip_id")))
        open_items = [(d, b) for d in merged.get("days") or [] for b in d.get("bookings") or []
                      if b.get("status") in ("requested", "attempting", "pending", "link_sent", "proposed", "quoted", "unclear")]
        if open_items:
            d, b = open_items[0]
            nxt = "they've not answered yet — I'll tell you when they do" if b.get("status") in ("requested", "attempting") else "it's waiting on you"
            return f"{merged.get('title')} — {b.get('venue')} on Day {d.get('day')} ({b.get('status_words')}); {nxt}"
        return f"{merged.get('title')} — {len(merged.get('days') or [])} days planned; next, book what's still a placeholder"
    open_rows = [r for r in rows if r.get("status") in ("requested", "attempting", "pending", "proposed", "quoted")]
    if open_rows:
        r = open_rows[0]
        return f"{r.get('venue')} on {r.get('date')} — {r.get('status_words')}"
    return None


async def send(account: Optional[str]) -> str:
    """The sentence to say on the web. Never raises."""
    from . import guest_whatsapp as GW
    if not account or GW.STORE is None:
        return "Sign in, and I'll send it to your phone."
    ch = await GW.STORE.channel_of_account(account)
    if not ch:
        return "Your phone isn't linked to Sasha on WhatsApp yet — message Sasha there once, and I can send things to it."
    s = await summary(account)
    if not s:
        return "There's nothing open to pick up yet — plan a trip or ask me to book something first."
    out = await GW._tell(ch, f"Picking up: {s}. Reply to carry on — or ask “show me my itinerary”.")
    if out.startswith("not"):
        return "I couldn't reach your WhatsApp just now (it needs a message from you in the last 24 hours) — say hi to Sasha there first."
    return "Sent to your phone — reply there to carry on."


__all__ = ["asked", "send", "summary"]
