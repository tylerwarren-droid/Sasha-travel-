"""Sasha 159 (1) · a PHOTO sent in the web chat (attach, drag-and-drop, paste, a phone's camera): handed, as bytes, to the
same reader WhatsApp photos go to (products.web.web_turn(..., media=[{bytes, content_type}]), CR's) — in whatever mode the
chat is in. Read once; nothing is stored here. Limits: 5 photos, JPEG or PNG, 8 MB each (the browser already made JPEGs).
"""
from __future__ import annotations

import base64
import binascii
import inspect
from typing import List, Optional

MAX, MAX_BYTES, TYPES = 5, 8 * 1024 * 1024, ("image/jpeg", "image/png")


def decode(items: Optional[list]) -> List[dict]:
    """[{content_type, data_b64}] → [{bytes, content_type}]; anything else is dropped (never an error to the guest)."""
    out = []
    for m in (items or [])[:MAX]:
        if not isinstance(m, dict) or m.get("content_type") not in TYPES:
            continue
        try:
            b = base64.b64decode(str(m.get("data_b64") or ""), validate=True)
        except (binascii.Error, ValueError):
            continue
        if 0 < len(b) <= MAX_BYTES:
            out.append({"bytes": b, "content_type": m["content_type"]})
    return out


def _answer(text: str, extra: Optional[dict] = None) -> dict:
    return {"response": text, "intents": ["products"], "quick_replies": (extra or {}).get("quick_replies") or [],
            "media": (extra or {}).get("media") or [], "photos": [], "tools_used": [], "links": [], "hotels": [], "bookings": [],
            "itinerary": None, "action": None, "booking_ref": None, "itinerary_id": None, "payment_item": None, "saved_card": None}


async def web(user_id: Optional[str], message: str, media: List[dict], product_mode: Optional[str], payload: Optional[str],
              signed_in: Optional[bool]) -> dict:
    if not media:
        return _answer("I couldn't open that photo — send a JPEG or PNG, up to 8 MB. Nothing was kept.")
    if not user_id or signed_in is not True:
        return _answer("Photos are read in your own private session — give me a moment and send it again. Nothing was kept.")
    from products.web import web_turn
    if "media" not in inspect.signature(web_turn).parameters:
        return _answer("I can't read photos here yet — it's coming. Nothing was kept.")
    text = "" if message.startswith("📷 (") else message
    try:
        t = await web_turn(user_id, text, mode=product_mode, payload=payload, signed_in=True, media=media)
    except Exception as e:   # the products' failure never stops the chat — and is never a silent one
        print(f"[photo_turn] the photo turn failed: {type(e).__name__}: {e}")
        return _answer("Something went wrong reading that photo on my side — nothing was kept. Try again?")
    if t is None:
        return _answer("Got it. What's the photo for — your DNI or passport (EspañaMe, RelocateMe), or something for a booking? "
                       "Nothing was kept.")
    return _answer(t.get("response") or "", t)


__all__ = ["decode", "web"]
