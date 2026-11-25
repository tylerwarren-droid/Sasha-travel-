"""Sasha 404 · WHAT A SUPPLIER IS — the ONE source (root test: mailbox row 2145; KANOE "THE DMC SPACE" 20 Nov, "DEMO CONTACTS" 25 Nov).

A card's supplier is one of three kinds:
  real        a real business, live;
  real_test   a real business in TEST mode (Duffel's test fares, a test booking of a real hotel, AgAPI's sandbox for a test person) —
              today's behaviour: the page's "No real money moves" line, NO word on the card (no-test-label.mjs strips "TEST" there);
  demo        a supplier that is not a business at all (Kanoe's test venues and hotel, the founder demo's stand-in, the test carriers) —
              it ALWAYS shows it is a demo, ON THE CARD, in every door: its display name carries DEMO_MARK, from here.

Measured before (404): "what is this" was decided by name in booking_decide, venues, test_venues, wa_brain, journeys, hotel_test and the
stand-in's own mark; and the stand-in ("(TEST stand-in)" — a real venue's booking sent to Kanoe's demo venue) was STRIPPED per screen
(itinerary_q ×3, guest_whatsapp ×2, plan_store, TripPanel, ChatBooking, no-test-label), so a demo booking showed as the real venue.

  kind_of(x)   a card / row / name → "real" | "real_test" | "demo" — the ONE decision.
  shown(name)  THE display name: a demo supplier's with its mark (idempotent; an old stand-in mark becomes the new one).
  demo_name()  how a demo supplier is NAMED where it is defined (test_venues, s2_hotel, the stand-in) — so records, AgAPI and every door
               carry the mark with no per-screen code.
"""
from __future__ import annotations

import os
import re
from typing import Any, Mapping, Optional

DEMO_MARK = "Demo"
SUFFIX = f" · {DEMO_MARK}"
STANDIN = f" · {DEMO_MARK} stand-in"   # a real venue's booking sent to Kanoe's demo venue (the founder demo, Sasha 169)
LEGACY_STANDIN = ("(TEST stand-in)", "(our test venue stood in)")   # older rows' marks: read as demo, shown with the new one

#: the demo suppliers Sasha defines — their BASE names (the display name adds the mark) and ids
DEMO_VENUES = {"kanoe-test-venue": "Sasha Test Venue", "kanoe-taverna-correo": "Taverna Correo",
               "kanoe-taverna-sandbox": "Taverna Sandbox"}
DEMO_HOTEL = "Kanoe Test Hotel"
#: test carriers — fake airlines (Duffel's, AgAPI's fixture)
DEMO_CARRIERS = {"ZZ": "Duffel Airways", "EX": "Example Air"}
_DEMO_NAME = re.compile(r"^\s*(?:the\s+)?(?:sasha test venue|taverna correo|taverna sandbox|kanoe test hotel|duffel airways|example air)\b", re.I)


def _has_standin(name: str) -> bool:
    return STANDIN.strip() in name or any(m in name for m in LEGACY_STANDIN)


def kind_of(x: Any) -> str:
    """real | real_test | demo — a card, a booking row, an option, or a bare name."""
    if isinstance(x, Mapping):
        if x.get("place_id") in DEMO_VENUES or str(x.get("carrier") or x.get("owner_code") or "").upper() in DEMO_CARRIERS:
            return "demo"
        for k in ("name", "venue", "provider_name", "airline", "owner"):
            if x.get(k) and kind_of(str(x[k])) == "demo":
                return "demo"
        if x.get("test") or x.get("is_test") or str(x.get("booking_reference") or x.get("reference") or "").startswith("TEST-"):
            return "real_test"
        return "real"
    name = str(x or "")
    if DEMO_MARK and (name.endswith(SUFFIX) or _has_standin(name) or _DEMO_NAME.search(name)):
        return "demo"
    return "real"


def is_standin(name: Any) -> bool:
    """The founder demo's stand-in: a real venue's booking sent to Kanoe's demo venue (its mark, new or old)."""
    return _has_standin(str(name or ""))


def is_demo(x: Any) -> bool:
    return kind_of(x) == "demo"


def _base(name: str) -> str:
    n = name
    for m in LEGACY_STANDIN:
        n = n.replace(m, "")
    return n.replace(STANDIN, "").replace(SUFFIX, "").strip()


def shown(name: Optional[str]) -> Optional[str]:
    """THE display name. A demo supplier's carries its mark — exactly once; anything else is returned as it is."""
    if not name or not is_demo(str(name)):
        return name
    s = str(name)
    return _base(s) + (STANDIN if _has_standin(s) else SUFFIX)


def demo_name(base: str) -> str:
    """How a demo supplier is NAMED where it is defined."""
    return _base(base) + SUFFIX


def standin_name(real: Optional[str]) -> str:
    """The founder demo: the place he picked, its booking sent to Kanoe's demo venue — said, on its name (≤ 80 characters)."""
    return f"{(real or 'the place you picked').strip()[:62]}{STANDIN}"


def demo_venue_phone() -> Optional[str]:
    """The demo VENUE's number — CONFIGURATION (CR 181: contacts are configuration, never a literal): Kanoe's own, settled 25 Nov (KANOE
    "DEMO CONTACTS"). Never shown on a shared screen or in a recording. Unset → no number (the call route simply isn't offered)."""
    v = os.getenv("SASHA_DEMO_VENUE_PHONE", "").strip()
    return v if v.startswith("+") else None


__all__ = ["is_standin", "kind_of", "is_demo", "shown", "demo_name", "standin_name", "demo_venue_phone", "DEMO_MARK", "SUFFIX", "STANDIN",
           "LEGACY_STANDIN", "DEMO_VENUES", "DEMO_HOTEL", "DEMO_CARRIERS"]
