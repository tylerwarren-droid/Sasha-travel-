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
    # Sasha 159 · EU 160 §4 row 13: the citizen wording (newcomer steps are RelocateMe's)
    "espana": "EspañaMe helps you get Spain's public services done — renewals, help, appointments, taxes — each step from its "
              "official page; I prepare, you sign in and press. It's a concept today: the doctor's appointment works in our "
              "test setup.",
}


#: Sasha 178 · "back to the campus tour", "resume my relocation", "continue with EspañaMe" — that product, where it was left
BACK = re.compile(r"^\s*(?:ok(?:ay)?[,.!]?\s+)?(?:(?:let'?s\s+)?(?:go\s+)?back\s+to|resume|continue(?:\s+with)?|carry\s+on\s+with|return\s+to)\s+"
                  r"(?:the\s+|my\s+)?(?P<p>campus(?:\s*(?:tour|visits?|me))?|relocat\w*(?:\s*me)?|move(?:\s+to\s+madrid)?|"
                  r"espa[nñ]a\s*me|espa[nñ]a|health)\b", re.I)


def back(message: str) -> Optional[str]:
    """The product mode to RESUME ("campus" | "relocation" | "espana"), or None."""
    m = BACK.match(message or "")
    if not m:
        return None
    w = m["p"].lower()
    return "campus" if w.startswith("campus") else "relocation" if w.startswith(("relocat", "move")) else "espana"


def asked(message: str) -> Optional[str]:
    """The product mode the guest asked about ("relocation" | "campus" | "espana"), or None."""
    m = ASK.search(message or "") or BARE.match(message or "")
    if not m:
        return None
    key = re.sub(r"\s+", "", m.group(1).lower()).replace("espana", "españa")
    return MODE.get(key)


__all__ = ["asked", "back", "BACK", "INTRO", "KEYWORD", "MODE", "NAME"]
