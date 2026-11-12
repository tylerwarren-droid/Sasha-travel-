"""Sasha 378 · CR 188 · THE TEST DOUBLE for AgAPI's ONE booking decision — venue.profile's `decision` (AgAPI's handoff.decide), in the
shapes AgAPI answers (each template below is handoff.decide's own output, agapi cr/190 e590043 — which carries CR 188 — run over a
profile of that kind, the venue's name substituted). Sasha decides nothing from it: the code under test reads VT.decision only.

CR 188's ONE order: their own form → send_form (Kanoe submits) · their own email → message (Kanoe sends) · their own WhatsApp → message
(the person sends, unless AgAPI's gate says Kanoe) · their own phone → call · a platform the policy permits → platform_book (Sasha books
it on the yes) · a step only they may do, or a closed platform → platform (the hand-over) · nothing → none (the floor).

    decision("send_form", venue="Casa Gate", link="https://casagate.example/reservas")
    for_rungs(rungs, facts)               # the decision AgAPI answers for a venue publishing these (CR 188's order)
    engine_for(rungs, facts)              # venue.profile faked for VN.engine_channel: caches that decision for the place asked about
    profile_says(test, decision)          # the same, patched for a unit test's duration

Used by the deploy gate's suites (scripts/venue_suite, her_voice_suite) and the unit tests alike.
"""
from __future__ import annotations

import copy
import time
from typing import Optional
from unittest import mock

VERSION = "handoff/2.4 · 2026-11-12"
CM = "https://www.covermanager.com/reserve/module_restaurant/restaurante-casa-gate/spanish"
OT = "https://www.opentable.com/r/casa-gate-madrid"

_T = {
    "send_form": {"route": "send_form", "channel": "their own booking form", "how_far": "zero_touch",
                  "say_text": "I can fill in {v}'s own booking form and send it for you — just say yes.",
                  "button": {"label": "Send my request", "link": "{link}", "sends": True}},
    "email": {"route": "message", "channel": "email", "how_far": "request", "say_text": "{v}: I can send it for you and tell you when they answer.",
              "button": {"label": "Send the request", "link": "{link}", "sends": True}, "sender": "kanoe", "options": []},
    "whatsapp": {"route": "message", "channel": "WhatsApp", "how_far": "request",
                 "say_text": "{v}: I'll write it for you, and you send it from your phone; they'll reply to you.",
                 "button": {"label": "Send on WhatsApp", "link": "https://wa.me/34600000001", "sends": False}, "sender": "person",
                 "options": [{"kind": "whatsapp", "label": "Send on WhatsApp", "link": "https://wa.me/34600000001", "sends": False}]},
    "call": {"route": "call", "channel": "phone", "how_far": "call", "say_text": "{v}: I can call them for you.",
             "button": {"label": "Ask Sasha to call", "link": "{link}", "sends": False}},
    "platform_book": {"route": "platform_book", "channel": "CoverManager", "how_far": "zero_touch",
                      "say_text": "{v} books on CoverManager — I'll book it there for you; just say yes.",
                      "button": {"label": "Yes, book it", "link": CM, "sends": True}},
    "platform": {"route": "platform", "channel": "OpenTable", "how_far": "hand_over",
                 "say_text": "{v} books on OpenTable, which doesn't let me book for you — your details are on the card to copy. You press Book there.",
                 "button": {"label": "Book on OpenTable", "link": OT, "sends": False}, "hand_over": {"link": OT, "carried": [], "copy": []},
                 "policy": {"prefill_link": "permitted", "fill_browser": "not_permitted", "submit": "not_permitted"}},
    "none": {"route": "none", "channel": None, "how_far": "link", "say_text": "Here's their website — book there, and I'll check how it went when you're back.",
             "button": {"label": "Open their website", "link": "{link}", "sends": False}, "options": [], "floor": True},
}


def decision(kind: str, venue: str = "Casa Gate", link: Optional[str] = "https://casagate.example/", **over) -> dict:
    """AgAPI's decision of this kind (send_form | email | whatsapp | call | platform_book | platform | none), as handoff.decide answers it."""
    d = copy.deepcopy(_T[kind])
    d["say_text"] = d["say_text"].replace("{v}", venue)
    if d["button"].get("link") == "{link}":
        d["button"]["link"] = link
    d["version"] = VERSION
    d.update(over)
    return d


#: platforms the channel policy permits a submit on, for everyone (channel-policy/7): AgAPI books them (platform_book); every other
#: platform's page is handed over (route platform) — as counsel set it, per platform, never per person
PERMITTED = ("covermanager", "dish")


def for_rungs(rungs: dict, facts: Optional[list] = None, url: Optional[str] = None, venue: str = "Casa Gate") -> dict:
    """AgAPI's decision for a venue publishing `rungs` (venue.profile → handoff.decide, CR 188's ONE order) — the fake AgAPI's answer:
    their own form / booking page → send_form (a CAPTCHA on it: the step only they may do → platform, handed over); their own email →
    message (Kanoe sends); their own WhatsApp → message (they send it); their own phone → call; a platform the policy permits →
    platform_book, any other platform → its page handed over (platform); nothing → none (the floor)."""
    rungs = rungs or {}
    link = str((rungs.get("link") or {}).get("value") or "")
    own = next((r for r in ("form", "own_page") if r in rungs), None)
    page = url or (link if link.startswith("http") else None) or "https://casagate.es/reservas"
    if own:
        if any(f.get("kind") == "challenge" for f in facts or []):
            return decision("platform", venue, channel="their own booking page",
                            say_text=f"{venue}'s booking page asks you to prove you're not a robot — I've filled in your booking; that last step is yours.",
                            button={"label": "Open their booking page", "link": page, "sends": False},
                            hand_over={"link": page, "carried": [], "copy": []})
        return decision("send_form", venue, link=page)
    if "email" in rungs:
        return decision("email", venue, link=url or "https://casagate.es/")
    if "whatsapp" in rungs:
        return decision("whatsapp", venue)
    if "phone" in rungs:
        return decision("call", venue, link=url or "https://casagate.es/")
    if "link" in rungs:
        name = link if not link.startswith("http") else link.split("//")[-1].split("/")[0].replace("www.", "").split(".")[0]
        if name.lower().replace(" ", "") not in PERMITTED:
            here = link if link.startswith("http") else f"https://www.{name.lower()}.example/{venue.lower().replace(' ', '-')}"
            return decision("platform", venue, channel=name,
                            say_text=f"{venue} books on {name}, which doesn't let me book for you — your details are on the card to copy. You press Book there.",
                            button={"label": f"Book on {name}", "link": here, "sends": False}, hand_over={"link": here, "carried": [], "copy": []})
        return decision("platform_book", venue, channel=name, say_text=f"{venue} books on {name} — I'll book it there for you; just say yes.")
    return decision("none", venue, link=url or "https://casagate.es/")


def engine_for(rungs: dict, facts: Optional[list] = None, url: Optional[str] = None):
    """venue.profile, faked for VN.engine_channel: AgAPI's decision for this venue (for_rungs), cached as venue_truth keeps it."""
    from agapi import venue_truth as VT

    async def eng(card, budget_s=30.0, listing=False):
        if not card:
            return None
        dec = for_rungs(rungs, facts, url, venue=card.get("name") or "Casa Gate")
        seed(card, dec)
        return VT.channel({"decision": dec})
    return eng


def seed(place: dict, dec: Optional[dict]) -> None:
    """AgAPI's venue.profile for this place, cached as agapi.venue_truth keeps it — its `decision` is what VT.decision reads."""
    from agapi import venue_truth as VT
    key = VT._key_of(place)
    if key:
        VT._CACHE[key] = {"at": time.time(), "profile": {"decision": dec} if dec else {}}


def profile_says(test, dec: Optional[dict] = None, by_place: Optional[dict] = None):
    """For the test's duration: AgAPI's venue.profile answers `dec` (or by_place[place_id]) for the place asked about — the ONE
    decision hold_venue follows. Nothing is fetched."""
    from agapi import venue_truth as VT, venues as VN

    async def engine_channel(card, budget_s=30.0, listing=False):
        if not card:
            return None
        d = (by_place or {}).get(card.get("place_id"), dec) if by_place is not None else dec
        seed(card, d)
        return VT.channel({"decision": d}) if d else None
    p = mock.patch.object(VN, "engine_channel", engine_channel)
    p.start()
    test.addCleanup(p.stop)
    snap = dict(VT._CACHE)
    test.addCleanup(lambda: (VT._CACHE.clear(), VT._CACHE.update(snap)))
    return engine_channel


__all__ = ["decision", "for_rungs", "engine_for", "seed", "profile_says", "CM", "OT", "PERMITTED"]
