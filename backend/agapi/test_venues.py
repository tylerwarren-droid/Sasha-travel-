"""Sasha 256 item 1 · THE TEST VENUE, ONE PLACE — what a TEST person can book is decided in the venue search, by the person's mode.

Found on production (13 Oct, /s2): "Book a table for two at the Sasha Test Venue in Madrid …" → search_venues (Google Places) gave
"Sasha- Beauty Salon", "Sacha Restaurant" and "SASHA"; Kanoe's test venue was never found. The booking engine already books it (a
card with our own form as its website: hold_venue → the ONE question → the read-back → venue.submit_booking, sandbox for a test
person); only FINDING it was missing.

  · TEST_VENUES — Kanoe's test venues, built here and nowhere else: a card in the same shape a search returns (PlaceCard data), with
    test=True and its line "Kanoe test venue — not a real restaurant". Its website is OUR form (form_rung.test_venue_url), so its read
    never looks it up on Google (venue_read: "our own test venue is never looked up on Google") and nothing real is contacted.
  · search(ctx, a) — called by the ONE venue search (agapi.v0._search_venues: /s2, WhatsApp's brain and /next under parity). A
    test-mode person whose request names the test venue gets its card, and ONLY its card: no Places call, so never "Sacha
    Restaurant". A generic search ("dinner in Madrid") is unchanged for everyone — the test venue is found by name, never as filler.
  · vet(ctx, a) — read_booking_route and hold_venue: a hold naming a test venue (its place_id, or by name with no place_id) is the
    test card for a test person, and REFUSED for a live person (never read, never held, never booked).

Kanoe Test Hotel (s2_hotel.TEST_HOTEL) is not here: its path is a TEST stay (search_stays / hold_booking) and the upgrade request,
not hold_venue's form — a hotel card here would book nothing that works.
Old S1 (SASHA_S1_PARITY=off) is untouched: nothing here runs off the one path (venues.one_path).
"""
from __future__ import annotations

import logging
import re
import unicodedata
from typing import Dict, List, Optional

log = logging.getLogger("agapi.test_venues")

TEST_LINE = "Kanoe test venue — not a real restaurant"
#: the words that name each test venue (case- and accent-insensitive, as whole words)
_NAMES = {"kanoe-test-venue": re.compile(r"\b(?:(?:sasha|kanoe)\s+)?test\s+venue\b"),
          "kanoe-taverna-correo": re.compile(r"\btaverna\s+correo\b"),
          "kanoe-taverna-sandbox": re.compile(r"\btaverna\s+sandbox\b")}
#: Sasha 256 item 3 · CR 94's sandbox email test venue: it books by EMAIL only (captured, never sent) and answers by itself ~20 s
#: after the request — 21:00 for up to 8 confirms, more than 8 people or a Monday declines, a time it doesn't offer gets the nearest
TAVERNA_CORREO = "https://agapi-sandbox-production.up.railway.app/fixtures/taverna-correo"
#: Sasha 265 · item 4 · CR 99's sandbox CALL test venue: AgAPI's own fixture (its booking page; "lunch 13:00–15:00, dinner 20:00–22:30,
#: closed Mondays"), with the AgAPI sandbox's FICTIONAL number (+1 500 555 0193 — a test range; nothing is dialled for a test person:
#: the act's call_plan says simulate). Its page AND a phone, soon → the ONE question "fill in their page now, or shall I call them?"
TAVERNA_SANDBOX = "https://agapi-sandbox-production.up.railway.app/fixtures/taverna"
SANDBOX_PHONE = "+15005550193"
_WEEK = {d: [("13:00", "15:00"), ("20:00", "22:30")] for d in range(1, 7)}   # Tuesday–Sunday (0 = Monday: closed)


def _venues() -> List[dict]:
    from booking_signer import form_rung as FR
    return [{"place_id": "kanoe-test-venue", "name": "Sasha Test Venue", "test": True, "kind": "restaurant",
             "website": FR.test_venue_url("plain"), "city": "Madrid", "country": "ES",
             "address": f"{TEST_LINE}, Madrid, Spain", "type": TEST_LINE, "type_source": "site", "google_type": None,
             "phone": None, "status": None, "listing_url": "", "rating": None, "rating_count": None, "price_level": None,
             "distance_m": None, "books": {"how": "site", "words": "Its own booking form"}},
            {"place_id": "kanoe-taverna-correo", "name": "Taverna Correo", "test": True, "kind": "restaurant",
             "website": TAVERNA_CORREO, "city": "Madrid", "country": "ES",
             "address": f"{TEST_LINE} (books by email), Madrid, Spain", "type": TEST_LINE, "type_source": "site", "google_type": None,
             "phone": None, "status": None, "listing_url": "", "rating": None, "rating_count": None, "price_level": None,
             "distance_m": None, "books": {"how": "email", "words": "By email"}},
            {"place_id": "kanoe-taverna-sandbox", "name": "Taverna Sandbox", "test": True, "kind": "restaurant",
             "website": TAVERNA_SANDBOX, "city": "Madrid", "country": "ES",
             "address": f"{TEST_LINE} (its page, or a call), Madrid, Spain", "type": TEST_LINE, "type_source": "site", "google_type": None,
             "phone": SANDBOX_PHONE, "week": {str(k): v for k, v in _WEEK.items()}, "status": None, "listing_url": "", "rating": None,
             "rating_count": None, "price_level": None, "distance_m": None, "books": {"how": "site", "words": "Its own page, or by phone"}}]


def TEST_VENUES() -> List[dict]:   # noqa: N802 · a function: test_venue_url reads the server's public base when called
    return [dict(v) for v in _venues()]


TEST_IDS = ("kanoe-test-venue", "kanoe-taverna-correo", "kanoe-taverna-sandbox")


def _plain(text: Optional[str]) -> str:
    t = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode().casefold()
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", t)).strip()


def named(*texts: Optional[str]) -> List[dict]:
    """The test venues these words name: "Sasha Test Venue" / "kanoe test venue" / "the test venue"; "Taverna Correo" (any case,
    any accents)."""
    said = [_plain(t) for t in texts if t]
    return [v for v in TEST_VENUES() if any(_NAMES[v["place_id"]].search(t) for t in said)]


def names_test_venue(*texts: Optional[str]) -> bool:
    return bool(named(*texts))


def is_test_card(card: Optional[dict]) -> bool:
    return bool(card) and (bool(card.get("test")) or card.get("place_id") in TEST_IDS)


async def mode_of(account: Optional[str]) -> str:
    """The person's mode FOR WHAT THEY MAY BOOK — their access record: "live" only when the record says live; no record (or an
    unreadable one) → "test" (fails closed, as person_access does). Sasha 259 · EU 255 (row 890): a fresh account with no record got
    Google's "Sacha Restaurant" instead of the test card, because this read the routing mode (no record → the guest marker → "live").
    A person who can't reach a real venue must reach Kanoe's test venue; only a live record hides it."""
    from agapi import person_access as PA
    return "live" if (await PA.get(account)).get("mode") == "live" else "test"


def _on_path(ctx) -> bool:
    from agapi import venues as VN
    return VN.one_path(ctx)


async def search(ctx, a: dict) -> Optional[dict]:
    """The search's answer when a TEST person names the test venue: its card first (alone — the fuzzy Places matches are never
    shown for it), in the search's own shape. None: the search goes on as before (a live person, or the test venue not named)."""
    cards = named(a.get("what"), a.get("name"), a.get("query"), getattr(ctx, "user_said", None)) if _on_path(ctx) else []
    if not cards:
        return None
    if await mode_of(ctx.account) != "test":
        log.info("[test_venues] a live person named the test venue: the normal search")
        return None
    from agapi import venues as VN
    VN.remember_cards(ctx.account, cards)
    what, where = (a.get("what") or cards[0]["name"]).strip(), (a.get("where") or "Madrid").strip()
    find = {k: v for k, v in {"what": what, "where": where, "country": a.get("country"), "open_at": a.get("open_at"),
                              "party": a.get("party")}.items() if v}
    ids = [c["place_id"] for c in cards]
    return {"venues": [{**VN.card_for_model(c), "about": TEST_LINE} for c in cards],
            "ribbon": f"{len(cards)} for “{what}” in {where}",
            "on_screen": "these are EXACTLY the cards on their screen — name only these; nothing contacted",
            "find": find,
            "preset": {"all": cards, "ranking": {"default": "rated", "chips": {}, "orders": {"rated": ids}}, "show": len(cards),
                       "near": None, "cards": cards}}


async def vet(ctx, a: dict) -> dict:
    """read_booking_route / hold_venue: a hold naming a test venue. A test person → the args of the test card (its own form as the
    website, so no Places call and no real site); a live person → refused. Anything else → the args as they came."""
    if not _on_path(ctx):
        return a
    from agapi import venues as VN
    pid = a.get("place_id")
    if pid:   # a place_id decides by itself (the founder's rehearsal card, "sasha-test-venue", is the server's own — not this)
        card = next((c for c in TEST_VENUES() if c["place_id"] == pid), None)
        if card is None and is_test_card(VN.card_of(ctx.account, pid)):
            card = (named(a.get("name")) or TEST_VENUES())[0]
    else:
        card = (named(a.get("name")) or [None])[0]
    if card is None:
        return a
    if await mode_of(ctx.account) != "test":
        from agapi.v0 import ToolError
        log.info("[test_venues] a live person's hold named the test venue: refused")
        raise ToolError("no_such_venue", "There's no place by that name I can book for them — search for the place they mean "
                                         "(search_venues) and use a card on their screen. Nothing was read or booked.")
    VN.remember_cards(ctx.account, [card])
    return {**a, "place_id": card["place_id"], "name": card["name"], "website": card["website"], "city": card["city"],
            "country": card["country"]}
