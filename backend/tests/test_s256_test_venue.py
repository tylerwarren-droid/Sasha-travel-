"""Sasha 256 item 1 · T33 — THE TEST VENUE, ONE PLACE (agapi/test_venues): what a TEST person can book is decided in the venue search,
by the person's mode. Found on production (13 Oct): "Book a table for two at the Sasha Test Venue in Madrid …" → Google Places gave
"Sacha Restaurant"; Kanoe's test venue was never found. Now a test person who names it gets its card (no Places call), holds it
through the same engine path (the ONE question), and a live person never sees it — a hold naming it is refused.

    cd backend && python -m unittest tests.test_s256_test_venue -v
"""
from __future__ import annotations

import asyncio
import unittest
from datetime import date, timedelta
from unittest import mock

from agapi import test_venues as TV, v0 as API, venues as VN
from app.agent import voice as V
from booking_signer import guest_accounts as GA, guest_receipt as GR, guest_whatsapp as GW
from tests.test_venue_pick_230 import FormApi, reader

ACCT = "00000000-0000-4000-8000-000000000256"
LATER = (date.today() + timedelta(days=9)).isoformat()


def run(c):
    return asyncio.run(c)


def ctx(said="Book a table for two at the Sasha Test Venue in Madrid.", surface="s2"):
    return API.Ctx(account=ACCT, mode="test", user_said=said, session="s256", surface=surface)


class Base(unittest.TestCase):
    MODE = "test"

    def setUp(self):
        VN._HELD.pop(ACCT, None)
        self.api = FormApi()
        self.places = mock.AsyncMock(return_value=(200, {"cards": []}))
        for p in (mock.patch.object(TV, "mode_of", mock.AsyncMock(return_value=self.MODE)),
                  mock.patch.object(GW, "api", self.api), mock.patch.object(GA, "founder", lambda a: False),
                  mock.patch.object(GR, "address_of", mock.AsyncMock(return_value="alex@example.test"))):
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(VN._HELD.pop, ACCT, None)
        API._LAST_FIND.pop(ACCT, None)
        self.addCleanup(API._LAST_FIND.pop, ACCT, None)


class ATestPerson(Base):
    def test_names_it_and_gets_only_its_card_without_places(self):
        r = run(TV.search(ctx(), {"what": "Sasha Test Venue", "where": "Madrid"}))
        self.assertEqual([c["name"] for c in r["preset"]["cards"]], ["Sasha Test Venue"])
        self.assertTrue(r["preset"]["cards"][0]["test"])
        self.assertIn("not a real restaurant", r["venues"][0]["about"])
        self.assertEqual(self.api.calls, [])   # no Places / venues/find call

    def test_the_words_that_reach_it(self):
        for said in ("Sasha Test Venue", "the sasha test venue please", "Kanoe test venue", "a table at the TEST VENUE"):
            self.assertTrue(TV.names_test_venue(said), said)
        for said in ("Sacha Restaurant", "dinner in Madrid", "test the venue"):
            self.assertFalse(TV.names_test_venue(said), said)

    def test_a_generic_search_is_unchanged(self):
        self.assertIsNone(run(TV.search(ctx("dinner in Madrid tonight"), {"what": "dinner", "where": "Madrid"})))

    def test_its_hold_asks_the_one_question(self):
        from tests.test_s254_one_decider import engine_from   # Sasha 270 · MOVED: its own form is the engine's read (CR 101)
        rungs = {"link": {"value": "https://x.test/api/booking/test-venue/plain"}}
        with mock.patch.object(VN, "_read", reader(rungs)), mock.patch.object(VN, "engine_channel", engine_from(rungs)):
            out = run(VN.hold_venue(ctx(), {"name": "Sasha Test Venue", "place_id": "kanoe-test-venue", "city": "Madrid", "country": "ES",
                                            "what": "dinner", "party": 2, "day": LATER, "time": "20:00"}))
        self.assertEqual(out["status"], "choose_route", out)
        self.assertEqual(out["ask"], V.ASK_BOOK)

    def test_vet_gives_the_test_cards_own_form(self):
        a = run(TV.vet(ctx(), {"name": "Sasha Test Venue"}))
        self.assertEqual(a["place_id"], "kanoe-test-venue")
        self.assertIn("/api/booking/test-venue/plain", a["website"])


class ALivePerson(Base):
    MODE = "live"

    def test_never_gets_the_test_card(self):
        self.assertIsNone(run(TV.search(ctx(), {"what": "Sasha Test Venue", "where": "Madrid"})))

    def test_a_hold_naming_it_is_refused(self):
        with self.assertRaises(API.ToolError):
            run(TV.vet(ctx(), {"name": "Sasha Test Venue"}))
        with self.assertRaises(API.ToolError):
            run(TV.vet(ctx(), {"place_id": "kanoe-test-venue", "name": "anything"}))

    def test_other_holds_pass_untouched(self):
        a = {"name": "Casa Gate", "place_id": "ChIJ-real"}
        self.assertEqual(run(TV.vet(ctx(), dict(a))), a)


class TheirWordsPickTheOption(Base):
    """Found live on production (/s2, the test venue): "Prefilled form" was sent by the model as route "form" and became Sasha sending
    it (a read-back of a send). Their words naming ONE option decide the route in hold_venue (venues.chosen_route)."""

    def test_the_words_map_to_the_rules_options(self):
        self.assertEqual(VN.chosen_route("Prefilled form"), "page")
        self.assertEqual(VN.chosen_route("prefilled form please"), "page")
        self.assertEqual(VN.chosen_route("Handle it"), "form")
        self.assertEqual(VN.chosen_route("handle it and let me know"), "form")
        for said in ("Yes, send it.", "book it", "the prefilled one, or handle it?", ""):
            self.assertIsNone(VN.chosen_route(said), said)

    def test_prefilled_form_is_the_page_whatever_the_model_sent(self):
        seen = []
        real = VN._read

        async def rd(c, a):
            seen.append(a.get("route"))
            return await reader({"link": {"value": "https://x.test/api/booking/test-venue/plain"}})(c, a)
        with mock.patch.object(VN, "_read", rd):
            try:
                run(VN.hold_venue(ctx("Prefilled form"), {"name": "Sasha Test Venue", "place_id": "kanoe-test-venue", "city": "Madrid",
                                                          "country": "ES", "what": "dinner", "party": 2, "day": LATER, "time": "20:00",
                                                          "route": "form"}))
            except Exception:
                pass   # the page's preparation is AgAPI's (not faked here) — what matters is the route it was held with
        self.assertIn("page", seen)
        self.assertNotIn("form", seen)


class ShortConfirmations(Base):
    """Demo path item 10 (≤ 2 sentences + the card): found live — after "Handle it" she recited the read-back in five sentences. On a
    screen the venue read-back is its card and she says one line (venues.READ_BACK_ASK); WhatsApp keeps the words (no card there)."""

    def handle_it(self, surface):
        # Sasha 270 · MOVED (CR 101: one form engine): its form is the engine's read, and "Handle it" is AgAPI's send (faked)
        from tests.test_s254_handle_it_live import use_fake_agapi
        from tests.test_s254_one_decider import engine_from
        use_fake_agapi(self)
        rungs = {"link": {"value": "https://x.test/api/booking/test-venue/plain"}, "form": {}}
        with mock.patch.object(VN, "_read", reader(rungs)), mock.patch.object(VN, "engine_channel", engine_from(rungs)):
            return run(VN.hold_venue(ctx("Handle it", surface), {"name": "Sasha Test Venue", "place_id": "kanoe-test-venue", "city": "Madrid",
                                                                  "country": "ES", "what": "dinner", "party": 2, "day": LATER, "time": "20:00",
                                                                  "route": "form"}))

    def test_on_a_screen_one_line_over_the_card(self):
        from app.agent import sasha as S
        out = self.handle_it("s2")
        self.assertEqual(out["status"], "awaiting_yes", out)
        self.assertEqual(out["ask"], VN.READ_BACK_ASK.format(venue=out["venue"]))
        self.assertLessEqual(len([x for x in out["ask"].replace("?", ".").split(".") if x.strip()]), 2)
        r = S.render("hold_venue", out, {})
        self.assertEqual((r or {}).get("kind"), "read_back")
        self.assertTrue(r["read_back"])

    def test_whatsapp_keeps_the_read_back_in_words(self):
        out = self.handle_it("wa")
        self.assertEqual(out["status"], "awaiting_yes", out)
        self.assertNotIn("ask", out)


class EverySurfaceSearchesHere(unittest.TestCase):
    def test_the_one_search_asks_the_test_venues_first(self):
        import inspect
        self.assertIn("TV.search(", inspect.getsource(API._search_venues))
        self.assertIn("TV.vet(", inspect.getsource(VN.hold_venue))
        self.assertIn("TV.vet(", inspect.getsource(VN.read_booking_route))


if __name__ == "__main__":
    unittest.main()
