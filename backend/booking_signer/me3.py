"""Sasha 155 · ME3 EVERYWHERE: "tell me about RelocateMe / CampusMe / EspañaMe" in the web chat, the voice avatar or WhatsApp
→ Sasha explains the product in two sentences (from EU's approved copy, docs/business/product-tabs-copy.md and
agapi-hub-pitches.md — every limit said) and switches into that product's mode, exactly as its WhatsApp keyword would.
The products are CR's (backend/products/); this only recognises the ask and opens the same mode.
"""
from __future__ import annotations

import re
from typing import Optional

_NAME = r"(relocate\s*me|relocateme|campus\s*me|campusme|espa[nñ]a\s*me|espa[nñ]ame)"
ASK = re.compile(r"\b(?:tell me (?:more )?about|what(?:'s| is)|explain|show me|try|open|start|switch(?: me)? to|go to|use)\s+"
                 rf"(?:the\s+)?{_NAME}\b", re.I)
BARE = re.compile(rf"^\s*{_NAME}\s*[?.!]?\s*$", re.I)

#: the product → its mode on the web (products.web.OPEN) and its keyword on WhatsApp (products.whatsapp)
MODE = {"relocateme": "relocation", "campusme": "campus", "españame": "espana"}
KEYWORD = {"relocation": "relocate", "campus": "campus", "espana": "españa"}
NAME = {"relocation": "RelocateMe", "campus": "CampusMe", "espana": "EspañaMe"}

INTRO = {
    "relocation": "RelocateMe gets your first Spanish residence application ready: I read your passport, prepare Spain's "
                  "official EX-01 from your own words and check it field by field — you sign and lodge it, I never do. "
                  "Then I plan the move itself: flights, your first nights and one itinerary with every deadline (test "
                  "bookings for now).",
    "campus": "CampusMe plans university visits: I read each university's own visit calendar live and prepare its "
              "registration from your details — you press Register, I never do. Then I plan the trip around the visits: "
              "flights, a hotel near each campus and the drive between them (test bookings for now).",
    "espana": "EspañaMe helps with Spain's public services, each step from its official page — I prepare everything, and you "
              "sign in and press; I never do that part for you. It's a concept today: the health part works in our test "
              "setup, and the padrón, utilities and phone line are still being studied.",
}


def asked(message: str) -> Optional[str]:
    """The product mode the guest asked about ("relocation" | "campus" | "espana"), or None."""
    m = ASK.search(message or "") or BARE.match(message or "")
    if not m:
        return None
    key = re.sub(r"\s+", "", m.group(1).lower()).replace("espana", "españa")
    return MODE.get(key)


__all__ = ["asked", "INTRO", "KEYWORD", "MODE", "NAME"]
