"""CR 16 · the products on the WEB chat — the product tabs on project.kanoe.ai (RelocateMe, CampusMe, EspañaMe) embed
Sasha's own web chat, opened in that product's mode. ONE router for both channels: this runs the very same
products.whatsapp.product_turn the WhatsApp line does, keyed "web:<account>", so the products, their state, the trip
plan's hand-off and the itinerary are the same — only the channel's words differ (buttons become quick replies).

  web_turn(user_id, message, mode=None, payload=None) → None (not the products': Sasha's own web flow answers) |
      {"agent": "products", "response": str, "quick_replies": [{"title", "payload"}], "media": [{"caption", "url"}],
       "handoff": str|None}   — with a hand-off, Sasha's conduct() answers that sentence with her own flow, as on WhatsApp.

Sasha's conduct() calls it (her wiring, marked "CR 16"); `mode` opens a product on the first turn of an embedded chat.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from . import store as ST

log = logging.getLogger("products.web")
# Sasha's first message when a tab opens its product FRESH (EU 150, docs/business/product-tabs-copy.md, verbatim). It
# replaces the product's own opening words on the web only (the WhatsApp line keeps its own); a product already under way
# answers as it always does ("Back to your EX-01. …"). The product's buttons are kept.
OPENING = {
    "relocation": "Let's get your Spanish residence file ready. You sign it and you lodge it — I never file anything for you. "
                  "Is this your first application, or a renewal?",
    "campus": "Tell me which universities and roughly when. I'll read their own visit calendars and show you what's really "
              "open — and I'll never press Register for you.",
    "health": "I can help you get things done with Spain's public services. One rule first: I prepare everything, and you "
              "sign in and press — I never do that part for you. What do you need?",
}
PRODUCT_OF = {"relocation": "relocation", "campus": "campus", "españa": "health"}
FIRST_STEP = {"relocation": (None, "route"), "campus": (None,), "health": (None, "es_menu")}   # the opener's own question
OPEN = {"relocation": "relocation", "relocate": "relocation", "campus": "campus", "campusme": "campus",
        "espana": "españa", "españa": "españa", "espaname": "españa"}


async def _state(key: str) -> dict:
    """The web line's equivalent of Sasha's WhatsApp state: which product asked last (its `pending`)."""
    for r in await ST.STORE.conversations(key):
        if r["product"] == "webstate":
            return {"history": [], "pending": (r["state"].get("pending") or {}).get("pending")}
    return {"history": [], "pending": None}


async def current_space(user_id: Optional[str]) -> Optional[str]:
    """Sasha 194 · the space the web chat is in: "relocation" | "campus" | "health" | "trip" | "diligence", or None (Sasha)."""
    if not user_id:
        return None
    try:
        pend = (await _state(f"web:{user_id}")).get("pending") or {}
    except Exception:
        return None
    return pend.get("product") if pend.get("kind") == "product" else None


async def _save(key: str, account: str, st: dict) -> None:
    if st.get("pending"):
        await ST.STORE.put_conversation(key, account, "webstate", {"pending": st["pending"], "for": st["pending"].get("product")})
    else:
        await ST.STORE.drop_conversation(key, "webstate")


SIGN_IN = {"relocation": "RelocateMe", "relocate": "RelocateMe", "campus": "CampusMe", "campusme": "CampusMe",
           "espana": "EspañaMe", "españa": "EspañaMe", "espaname": "EspañaMe"}


#: CR 30 · a photo uploaded in the web chat (laptop or phone): the same reader as WhatsApp's, its bytes passed in, never kept
WEB_MEDIA_TYPES = ("image/jpeg", "image/png")
WEB_MEDIA_MAX = 8 * 1024 * 1024
WEB_MEDIA_COUNT = 5


def web_media(media) -> list:
    """[{"bytes": b"…", "content_type": "image/jpeg"}] → the router's media items ({url: None, type, bytes}); anything else,
    too large or too many is dropped here (the reader then says what it can read)."""
    out = []
    for m in (media or [])[:WEB_MEDIA_COUNT]:
        b, ct = (m or {}).get("bytes"), str((m or {}).get("content_type") or "").split(";")[0].strip().lower()
        if isinstance(b, (bytes, bytearray)) and 0 < len(b) <= WEB_MEDIA_MAX:
            out.append({"url": None, "type": ct, "bytes": bytes(b)})
    return out


async def web_turn(user_id: Optional[str], message: str, mode: Optional[str] = None, payload: Optional[str] = None,
                   now: Optional[datetime] = None, signed_in: Optional[bool] = None, media=None) -> Optional[dict]:
    """⛔ Only for a SIGNED-IN visitor (`signed_in=True`, from the conductor's verified token). A visitor with no token is
    the public demo account — which, since CR 3, IS the founder's real account: the products must never act on it for a
    stranger (his files, his visits, his itinerary). Until the caller says signed_in, nothing here runs (4 Oct 2026)."""
    if not user_id:
        return None
    if signed_in is not True:
        if mode and not (message or "").strip() and not payload:
            name = SIGN_IN.get(mode.lower(), "This product")
            return {"agent": "products", "response": f"Sign in to use {name} — it works on your own account: your own file, "
                    "your own visits, your own itinerary.", "quick_replies": [], "media": [], "handoff": None}
        return None
    from booking_signer import guest_whatsapp as GW
    from . import whatsapp as PW
    now = now or datetime.now(timezone.utc)
    key = f"web:{user_id}"
    body = (message or "").strip()
    if mode and not body and not payload and not media:
        word = OPEN.get(mode.lower())
        if not word:
            return None
        body = word                                    # the tab opens its product exactly as its word would
    st = await _state(key)
    ch_ = {"wa_id_sha256": key, "account_id": user_id}
    opening = PRODUCT_OF.get(body) if (mode and not (message or "").strip() and not payload) else None
    if opening:
        saved = await PW._resume(ch_, opening)
        if saved and saved.get("step") in FIRST_STEP.get(opening, ()):   # CR 36 · nothing answered yet: the tab opens on its
            await ST.STORE.drop_conversation(PW._key(ch_), opening)        # opener, never the bare first question
            saved = None
        if saved:
            opening = None                             # under way already: the product says where it was
    p = {"Body": body, "ButtonPayload": (payload or "").strip()}
    out, early = GW.Out(), []

    async def _early(text: str) -> None:
        early.append(text)
    ch = {"wa_id_sha256": key, "account_id": user_id, "number_e164": None, "channel": "web"}
    try:
        handled = await PW.product_turn(ch, "web", p, st, out, now, early=_early, media=web_media(media))
    except Exception as e:
        log.error("[products.web] the product turn failed: %s: %s", type(e).__name__, e)
        return {"agent": "products", "response": "Something went wrong on my side with that — nothing was done. Try again?",
                "quick_replies": [], "media": [], "handoff": None}
    await _save(key, user_id, st)
    texts = list(early)
    replies, media = [], []
    for it in out.items:
        if it[0] == "text":
            texts.append(it[1])
        elif it[0] == "media":
            from .formcard import split
            caption, link = split(it[1])                 # CR 33 · a filled form's card: the picture opens the full PDF
            media.append({"caption": caption, "url": it[2], **({"link": link} if link else {})})
        elif it[0] == "ask":
            texts.append(it[1])
            replies = [{"title": t, "payload": pl} for t, pl in it[2]]   # the last question's buttons
    if opening and handled:
        texts = [OPENING[opening]]
    handoff = p["Body"] if not handled and p["Body"] != body else None
    if not handled and not handoff:
        return None                                    # not the products' message: Sasha's own web flow answers it
    return {"agent": "products", "response": "\n\n".join(texts), "quick_replies": replies, "media": media, "handoff": handoff}


async def in_context(user_id: Optional[str], message: str, signed_in: Optional[bool] = None,
                     now: Optional[datetime] = None) -> Optional[dict]:
    """CR 20 (5) · for Sasha's conduct(), BEFORE her own booking hand-off: a request that only means something with a
    product's context ("a 60-minute massage near my hotel on arrival") → {"sentence": the same request with the product's
    city, place and date, "line": what to say first, "product": …}, or None (her flow takes the guest's own words).
    Read-only: nothing is booked, sent or stored here. Signed-in accounts only (the public demo has no products)."""
    if not user_id or signed_in is not True:
        return None
    from . import whatsapp as PW
    now = now or datetime.now(timezone.utc)
    if not PW._REL.search(message or "") or not PW.for_sasha(message, [], now):
        return None
    ch = {"wa_id_sha256": f"web:{user_id}", "account_id": user_id}
    for prod, saved in await PW._waiting(ch, now):
        handed = await PW._in_context(ch, prod, saved, message, now)
        if handed:
            return {"sentence": handed[0], "line": handed[1], "product": prod}
    return None
