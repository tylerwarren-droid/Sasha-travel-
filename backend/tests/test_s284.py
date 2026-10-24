"""Sasha 284 · T64 — S2 FOLLOWS AGAPI'S DECISION (Tyler's real use, 23 Oct 13:44 UTC: "Spa & Massage, Chiswick High Road" — a clear
BOOK MASSAGE button — then Boys Don't Cry Tattoo and Opulence Thai Spa: venue.discover, venue.profile, and NO venue.prepare_booking;
S2 told him it could not book).

ROOT TEST (written before the code):
  (1) ONE truth: AgAPI's decision on venue.profile (handoff.decide: route · say_text · button {label, link, sends}). S2 reads it in ONE
      place — agapi/venue_truth.decision(place), kept whole by _from_profile (and prepare_booking's own copy by venue_truth.prepare).
  (2) No per-route or per-venue branch in Sasha, no second decision: read_booking_route says its say_text; hold_venue hands over every
      route the PERSON finishes (its button sends nothing, not a call) through venues.follow → the ONE hand-over path from 283 (the
      prepared rung: venue.prepare_booking, the page on screen and phone, the way back, the row "Did it go through?" reads).
  (3) The class: S2 never says "can't" while AgAPI's decision names a route other than none — the ratchet below runs every route
      (own form, platform page, Google, WhatsApp, email, phone, no reservations, open_slot), with and without a slot, and every refusal
      of the booking rules (access off, today's calls made, too soon, no channel of its own).
  A call stays the rules' act (Kanoe calls on his yes); AgAPI's call lines ("only takes bookings by phone") limit the channel (rule 15),
  so read_booking_route keeps her own line for a call — handed to CR, not re-worded here.
Offline: fakes only (no model, no AgAPI, no Places, no WhatsApp, nothing leaves the process).
    cd backend && python -m unittest tests.test_s284 -v
"""
from __future__ import annotations

import asyncio
import inspect
import re
import unittest
from datetime import datetime, timezone
from unittest import mock

from agapi import venue_truth as VT, venues as VN
from agapi.booking_rules import booking_rules as BR
from app.agent import voice as V

run = asyncio.run
ACCT = "00000000-0000-4000-8000-000000000284"
PREP = "https://agapi.example/prepared/tok284"

# AgAPI v1.27.0's ONE decision, one per route (handoff/1.8 · handoff.ROUTES, their words as decide() writes them)
DECISIONS = {
    "send_form": {"how_far": "zero_touch", "say_text": "I can fill in Spa & Massage's own booking form and send it for you — just say yes.",
                  "button": {"label": "Send my request", "link": "https://spaandmassage.co.uk/book", "sends": True}},
    "ask_then_send": {"how_far": "zero_touch", "say_text": "I can fill in Spa & Massage's own booking form and send it — first, which massage?",
                      "button": {"label": "Answer and send", "link": "https://spaandmassage.co.uk/book", "sends": True}},
    "prefilled_page": {"how_far": "prefilled_hand_over", "say_text": "Spa & Massage's form asks you to prove you're human, so I've filled it "
                                                                    "in for you to confirm there.",
                       "button": {"label": "Open their form", "link": "https://spaandmassage.co.uk/book", "sends": False}},
    "platform": {"how_far": "hand_over", "say_text": "Opulence Thai Spa books on Fresha — your details are on the card to copy. You press Book "
                                                     "there; I never book on a platform.",
                 "button": {"label": "Book on Fresha", "link": "https://www.fresha.com/a/opulence-thai-spa", "sends": False}},
    "reserve_with_google": {"how_far": "hand_over", "say_text": "They take bookings through Google — open their listing and tap “Reserve a "
                                                                "table”; your details are on the card to copy.",
                            "button": {"label": "Reserve on Google", "link": "https://maps.google.com/?cid=284", "sends": False}},
    "message": {"how_far": "request", "sender": "person", "say_text": "Boys Don't Cry Tattoo takes booking requests by WhatsApp — I've written "
                                                                      "it for you: tap “Send on WhatsApp” and it goes from your phone; they'll reply to you.",
                "button": {"label": "Send on WhatsApp", "link": "https://wa.me/447700900284", "sends": False}},
    "message_kanoe": {"route": "message", "how_far": "request", "sender": "kanoe",
                      "say_text": "They take booking requests by email — I can send it for you and tell you when they answer.",
                      "button": {"label": "Send the request", "link": None, "sends": True}},
    "call": {"how_far": "call", "say_text": "They only take bookings by phone — I can call them for you.",
             "button": {"label": "Ask Sasha to call", "link": "https://spaandmassage.co.uk/", "sends": False}},
    "no_reservations": {"how_far": "link", "say_text": "Their listing says they don't take reservations.",
                        "button": {"label": "Open their listing", "link": "https://maps.google.com/?cid=285", "sends": False}},
    "none": {"how_far": "link", "say_text": "I couldn't find a way to book them online or by message. You can take it over — here's what I found.",
             "button": {"label": "See what I found", "link": "https://maps.google.com/?cid=286", "sends": False}},
}


def dec_of(name: str) -> dict:
    d = dict(DECISIONS[name])
    d.setdefault("route", name)
    return d


# What S2 must never say while AgAPI found a route (the class): "can't" in any of its forms, and the rules' refusal words
CANT = re.compile(r"\b(can'?t|cannot|can not|unable|not able)\b", re.I)


class Ctx:
    def __init__(self, surface="s2", said=""):
        self.account, self.surface, self.user_said = ACCT, surface, said
        self.started = datetime.now(timezone.utc)


class TheDecisionIsKeptWhole(unittest.TestCase):
    def test_venue_profile_keeps_it(self):
        dec = dec_of("platform")
        got = VT._from_profile({"facts": {}, "booking": {"rung": 1}, "decision": dec})
        self.assertEqual(got["decision"], dec)
        self.assertNotIn("decision", VT._from_profile({"facts": {}, "booking": {}}))

    def test_prepare_booking_keeps_its_own(self):
        dec = {**dec_of("platform"), "button": {**DECISIONS["platform"]["button"], "link": PREP}}

        async def call(op, body):
            self.assertEqual(op, "venue.prepare_booking")
            return {"ok": True, "result": {"link": PREP, "say": "Ready for you to confirm.", "submitted": False, "decision": dec}}
        with mock.patch.object(VT, "CALL", call):
            got = run(VT.prepare({"name": "Opulence"}, {"name": "T", "phone": "+447700900000"}, "2099-11-01", "18:00", 1))
        self.assertEqual(got["decision"], dec)

    def test_it_is_read_in_one_place(self):
        place = {"website": "https://opulence.example"}
        with mock.patch.object(VT, "cached", lambda p: {"decision": dec_of("platform")}):
            self.assertEqual(VT.decision(place)["route"], "platform")
        with mock.patch.object(VT, "cached", lambda p: {"decision": {"say_text": "x"}}):
            self.assertIsNone(VT.decision(place))   # no route: no decision
        for src in (inspect.getsource(VN.read_booking_route), inspect.getsource(VN.hold_venue)):
            self.assertIn("VT.decision(card or listing_card(rd))", src)


class SheSaysAgAPIsWords(unittest.TestCase):
    def _route(self, dec, eng=None):
        rd = {"venue": "Spa & Massage", "say": "", "rungs": {}, "place_id": "ChIJ284"}
        with mock.patch("agapi.test_venues.vet", mock.AsyncMock(side_effect=lambda c, a: a)), \
                mock.patch.object(VN, "_read", mock.AsyncMock(return_value=rd)), mock.patch.object(VN, "card_of", lambda *a: None), \
                mock.patch.object(VN, "engine_channel", mock.AsyncMock(return_value=eng)), mock.patch.object(VN, "read_channel", lambda r, c, **k: eng), \
                mock.patch.object(VT, "decision", lambda p: dec), mock.patch.object(VT, "reservable_say", lambda c: None):
            return run(VN.read_booking_route(Ctx(), {"name": "Spa & Massage", "city": "London"}))

    def test_every_route_is_said_and_never_no_link(self):
        for name in DECISIONS:
            dec = dec_of(name)
            got = self._route(dec)
            if dec["route"] == "none":
                self.assertEqual(got["how"], dec["say_text"])   # Sasha 286 · nothing found: AgAPI's own floor, its button
            elif dec["how_far"] == "call":   # rule 15: AgAPI's call line limits the channel — her offer (284b: it was NO_LINK on live)
                self.assertEqual(got["how"], V.CALL_IT)
                self.assertFalse(V.limits_channel(got["how"]))
                self.assertFalse(CANT.search(got["how"]))
            else:
                self.assertEqual(got["how"], dec["say_text"], name)
                self.assertEqual(got["decision"]["button"], dec["button"])
                self.assertFalse(V.asks_for_link(got["how"]))

    def test_the_chiswick_spa_is_no_longer_no_link(self):
        # row 1259: no OWN_FORM channel (a platform page) → voice.NO_LINK, AgAPI's route ignored; 286: no decision → THE FLOOR
        self.assertTrue(self._route(None)["how"].startswith("Here's their "))
        self.assertEqual(self._route(dec_of("platform"))["how"], DECISIONS["platform"]["say_text"])

    def test_old_s1_unchanged(self):
        self.assertIn('return {**({"card": card} if card else {}), "venue": rd["venue"], "routes": _routes_of(rd), "how": rd.get("say"),',
                      inspect.getsource(VN.read_booking_route))


class Memory:
    def __init__(self):
        self.kinds = {}

    async def kind(self, _acct, name):
        return self.kinds.get(name)

    async def put_kind(self, _acct, name, value):
        self.kinds[name] = [dict(r) for r in value]
        return True


class TheHoldFollows(unittest.TestCase):
    """hold_venue → follows(decision) → follow() → the prepared rung (283's one hand-over path) → venue.prepare_booking → AgAPI's words."""

    def setUp(self):
        VN._HELD.pop(ACCT, None)
        VN._PREPARED.pop(ACCT, None)
        self.mem, self.calls, self.told = Memory(), [], []
        from agapi import s2_memory as M, s2_outcomes as OC
        from booking_signer import guest_receipt as GR, wa_brain as WB
        test = self

        async def call(op, body):
            test.calls.append(op)
            d = {**test.dec, "button": {**test.dec["button"], "link": PREP}}
            return {"ok": True, "result": {"link": PREP, "say": "Ready for you to confirm: Opulence. Nothing has been sent yet.",
                                           "human_step": "confirm", "submitted": False, "decision": d}}

        class Store:
            async def channel_of_account(self, _a):
                return {"wa_id_sha256": "x" * 64}

        async def tell(ch, text, template=None):
            test.told.append(text)
            return "sent (captured)"
        GW = VN._API()
        self.p = [mock.patch.object(M, "kind", self.mem.kind), mock.patch.object(M, "put_kind", self.mem.put_kind),
                  mock.patch.object(VT, "CALL", call), mock.patch.object(GR, "address_of", mock.AsyncMock(return_value="t@example.com")),
                  mock.patch.object(WB, "trip_day_words", mock.AsyncMock(return_value="")), mock.patch.object(OC, "booked", mock.AsyncMock()),
                  mock.patch.object(VN, "_loyalty", mock.AsyncMock(return_value=None)), mock.patch.object(GW, "STORE", Store()),
                  mock.patch.object(GW, "_tell", tell)]
        for p in self.p:
            p.start()

    def tearDown(self):
        for p in self.p:
            p.stop()
        VN._HELD.pop(ACCT, None)

    RES = {"who": {"name": "Tyler", "contact": {"mobile_e164": "+447700900000"}}, "how_many": {"count": 1},
           "when": {"at": "2099-11-01T18:00"}, "what": {"category": "spa"}}
    RD = {"venue": "Opulence Thai Spa", "rungs": {}, "place_id": "ChIJ284", "read_id": "r284"}

    def _follow(self, name, at="2099-11-01T18:00", refused=False, a=None):
        self.dec = dec_of(name)
        return run(VN.follow(Ctx(), a or {"name": "Opulence Thai Spa"}, self.RD, self.RES, at, datetime.now(timezone.utc),
                             {"website": "https://opulence.example", "place_id": "ChIJ284"}, self.dec, refused=refused))

    def test_a_platform_is_prepared_by_agapi_and_handed_over_in_its_words(self):
        out = self._follow("platform")
        self.assertEqual(self.calls, ["users.register", "venue.prepare_booking"])   # the call S2 never made (row 1259); 285: the person first
        self.assertEqual(out["say"], DECISIONS["platform"]["say_text"])
        self.assertEqual(out["prepared"]["button"], "Book on Fresha")
        self.assertEqual(out["prepared"]["url"], PREP)
        self.assertFalse(out["booked"])
        self.assertTrue(self.told and self.told[-1].endswith(V.way_back(__import__("booking_signer.wa_agent", fromlist=["x"]).s2_link())))
        self.assertEqual(self.mem.kinds[VN.PREPARED_KIND][-1]["venue"], "Opulence Thai Spa")   # the row "Did it go through?" reads

    def test_a_whatsapp_they_send_is_written_by_agapi(self):
        out = self._follow("message")
        self.assertEqual(out["say"], DECISIONS["message"]["say_text"])
        self.assertEqual(out["prepared"]["button"], "Send on WhatsApp")

    def test_no_slot_hands_over_venue_profiles_button(self):
        out = self._follow("platform", at="", a={"name": "Opulence Thai Spa", "open_slot": "whenever", "day": "2099-11-01"})
        self.assertEqual(self.calls, [])   # no day and time to prepare: venue.profile's button as given
        self.assertEqual(out["button"], {"label": "Book on Fresha", "link": DECISIONS["platform"]["button"]["link"]})
        self.assertEqual(out["open"], DECISIONS["platform"]["button"]["link"])
        self.assertTrue(out["say"].startswith(V.REACH_THEM))   # 284b: nothing prepared → never AgAPI's "on the card" / "I've written it"
        self.assertEqual(len(self.mem.kinds[VN.PREPARED_KIND]), 1)

    def test_nothing_prepared_never_claims_a_ready_booking(self):   # 284b · live: Boys Don't Cry, a quote, a guest's access
        out = self._follow("message_kanoe", at="", refused=True, a={"name": "Boys Don't Cry", "open_slot": "quote", "day": "2099-11-01"})
        self.assertEqual(self.calls, [])
        self.assertTrue(out["say"].startswith(V.REACH_THEM))   # the card's site: their way in
        self.assertNotIn("ready", out["say"])
        self.assertNotIn("written", out["say"])

    def test_a_refused_act_is_their_prepared_page_never_cant(self):
        out = self._follow("send_form", refused=True)
        self.assertEqual(out["say"], "Ready for you to confirm: Opulence. Nothing has been sent yet.")   # prepare_booking's own words
        self.assertEqual(out["prepared"]["button"], V.OPEN_THEIR_PAGE)
        self.assertFalse(CANT.search(out["say"]))


class NeverCantWhileAgAPIFoundARoute(unittest.TestCase):
    """THE RATCHET (3): every route × with/without a slot × every refusal of the booking rules → what S2 does with it."""

    def test_who_finishes_it_is_agapis_button(self):
        for name in DECISIONS:
            dec = dec_of(name)
            for at in ("2099-11-01T18:00", ""):
                expect = dec["route"] != "none" and dec["how_far"] != "call" and not dec["button"]["sends"] \
                    and (bool(at) or dec["how_far"] != "request")
                self.assertEqual(VN.follows(dec, at), expect, (name, at))
        self.assertFalse(VN.follows(None, "2099-11-01T18:00"))

    def test_the_hold_asks_agapi_first_and_never_ends_on_a_refusal(self):
        src = inspect.getsource(VN.hold_venue)
        i_dec, i_follow, i_rules, i_refused = (src.index(x) for x in (
            "dec = VT.decision(card or listing_card(rd)) if path else None", "if follows(dec, at):",
            "d = await rules_for(", 'if dec and dec["route"] != "none" and d.get("say") in REFUSED:'))
        self.assertLess(i_dec, i_follow)
        self.assertLess(i_follow, i_rules)
        self.assertLess(i_rules, i_refused)
        self.assertIn("refused=True", src[i_refused:i_refused + 400])

    def test_every_refusal_of_the_rules_is_caught(self):
        # every "Kanoe may not act" key the rules can return (booking_rules._call_allowed and the access gate)
        src = inspect.getsource(BR)
        for key in ("no_real_sends", "calls_cap", "too_soon"):
            self.assertIn(f'"{key}"', src)
            self.assertIn(key, VN.REFUSED)
        self.assertIn("no_channel", VN.REFUSED)
        for key in VN.REFUSED:   # each of these, said as the rules say it, is a "can't" (or nothing to hand over) — never on /s2 with a route
            self.assertTrue(key == "no_channel" or CANT.search(BR.PHRASES.get(key, "can't")) or "won't" in BR.PHRASES.get(key, ""), key)

    def test_her_follow_lines_never_say_cant(self):
        for line in (V.FINISH_IT, V.OPEN_THEIR_PAGE, V.CALL_IT, V.REACH_THEM, V.FLOOR):
            self.assertFalse(CANT.search(line), line)
            self.assertFalse(V.limits_channel(line), line)
        for name in DECISIONS:
            if dec_of(name)["route"] != "none" and DECISIONS[name]["how_far"] != "call":
                self.assertFalse(CANT.search(DECISIONS[name]["say_text"]), name)   # AgAPI's own words for a route: none says "can't"

    def test_the_page_card_draws_agapis_button(self):
        from app.agent import sasha as SA
        ev = SA.render("hold_venue", {"prepared": {"venue": "Opulence", "url": PREP, "fields": [], "button": "Book on Fresha"}}, {})
        self.assertEqual((ev["kind"], ev["button"]), ("prepared", "Book on Fresha"))


if __name__ == "__main__":
    unittest.main()
