"""Sasha 291 · T70 — THE PERSON'S INTENT GOES TO AgAPI, SO "BOOK" NEVER SUGGESTS A PLACE THAT CAN'T BE BOOKED (Tyler, 25 Oct 22:09:
an Indian restaurant in London → Hungama, walk-in/takeaway, no bookings. "If the user wants takeaway, Sasha can suggest places like
Hungama. We have to be smart.")

ROOT TEST (written before the code):
  (1) ONE place S2 reads the intent — agapi/v0.py intent_of(the person's OWN words this turn, never the model's `what`); ONE call sends
      it — v0._discover → venue.discover `intent` (AgAPI v1.34.0). Unclear → browse, never book.
  (2) S2 dropping or re-ranking AgAPI's options itself, its own walk-in rule, or a cuisine/city/venue case = PATCH. S2 shows AgAPI's
      options as given, with AgAPI's own label ("walk-in, no bookings"); a left-out line only in AgAPI's words (its say_text).
  (3) "book me a table" → intent book → AgAPI's fits_intent keeps only places that take bookings; S2 never adds an option back.
Offline: AgAPI's answers below are its v1.34.0 shape; nothing reaches AgAPI.
    cd backend && python -m unittest tests.test_s291 -v
"""
from __future__ import annotations

import asyncio
import inspect
import pathlib
import re
import unittest
from unittest import mock

from agapi import v0 as API, venue_submit as VS, venues as VN

BACKEND = pathlib.Path(__file__).resolve().parents[1]
ACCT = "00000000-0000-4000-8000-000000002910"
run = asyncio.run

BOOK = {"ok": True, "result": {
    "say_text": "I've found a few good options in Soho — my pick is Dishoom (test).", "pick": {"ref": "ven_D", "name": "Dishoom (test)", "reason": "r"},
    "groups": [{"id": "places", "label": "places", "refs": ["ven_D"]}],
    "options": [{"ref": "ven_D", "group": "places", "kind": "place", "name": "Dishoom (test)", "place_id": "ChIJd", "rank": 1}],
    "intent": {"intent": "book", "from": "asked", "kept": 1,
               "left_out": [{"name": "Hungama (test)", "place_id": "ChIJh", "why": "their listing says they don't take bookings"}]}}}
TAKEAWAY = {"ok": True, "result": {
    "say_text": "I've found a few good options near Charing Cross — my pick is Hungama (test).", "pick": {"ref": "ven_H", "name": "Hungama (test)", "reason": "r"},
    "groups": [{"id": "places", "label": "places", "refs": ["ven_H"]}],
    "options": [{"ref": "ven_H", "group": "places", "kind": "place", "name": "Hungama (test)", "place_id": "ChIJh", "rank": 1, "label": "walk-in, no bookings"}],
    "intent": {"intent": "takeaway", "from": "asked", "kept": 1, "left_out": []}}}
NONE_BOOK = {"ok": True, "result": {"say_text": "I found places in Soho, but none that take bookings — want walk-in spots, or shall I widen the search?",
                                    "groups": [], "options": [], "pick": None,
                                    "intent": {"intent": "book", "kept": 0, "left_out": [{"name": "Hungama (test)", "why": "x"}]}}}


class TheirWords(unittest.TestCase):
    def test_each_intent_from_their_own_words(self):
        for said, want in (("book an Indian restaurant in Soho for 2 at 8", "book"), ("Reserve somewhere for Friday", "book"),
                           ("a table for four tonight", "book"), ("quiero reservar una mesa para dos", "book"),
                           ("Indian takeaway near Charing Cross", "takeaway"), ("something to go", "takeaway"),
                           ("comida para llevar", "takeaway"), ("I'll pick up a curry", "takeaway"),
                           ("pizza delivery to the hotel", "delivery"), ("sushi a domicilio", "delivery"),
                           ("somewhere to eat now", "eat_now"), ("algo para comer ahora", "eat_now"), ("a walk-in place", "eat_now"),
                           ("an Indian restaurant in London", "browse"), ("what's good around here?", "browse"), ("", "browse"), (None, "browse")):
            self.assertEqual(API.intent_of(said), want, said)

    def test_unclear_is_never_book(self):
        for said in ("an Indian restaurant in London", "nice places for dinner", "somewhere good in Soho"):
            self.assertNotEqual(API.intent_of(said), "book", said)


class Discover(unittest.TestCase):
    def setUp(self):
        VN._SHOWN.pop(ACCT, None)

    def _search(self, answer, said, what="Indian restaurant", where="Soho"):
        sent = []

        async def call(account, op, body, approval=None):
            sent.append((op, body))
            return answer
        ctx = API.Ctx(account=ACCT, mode="test", user_said=said, session="s291", surface="s2", via="page")
        with mock.patch.object(VS, "_call", call), mock.patch("agapi.test_venues.search", mock.AsyncMock(return_value=None)), \
                mock.patch.object(VN, "named_on_screen", lambda *a: None):
            out = run(API._search_venues(ctx, {"what": what, "where": where, "country": "GB"}))
        return out, sent

    def test_book_is_sent_and_agapis_options_shown_as_given(self):
        out, sent = self._search(BOOK, "book an Indian restaurant in Soho for 2 at 8")
        self.assertEqual([(op, b["intent"]) for op, b in sent], [("venue.discover", "book")])
        self.assertEqual([o["name"] for o in out["discover"]["options"]], ["Dishoom (test)"])   # never a left-out place added back
        self.assertNotIn("Hungama", str(out["discover"]["options"]))
        self.assertEqual(out["say"], BOOK["result"]["say_text"])   # no list of reasons; only AgAPI's words

    def test_takeaway_keeps_a_walk_in_place_with_agapis_label(self):
        out, sent = self._search(TAKEAWAY, "Indian takeaway near Charing Cross", what="Indian takeaway", where="Charing Cross, London")
        self.assertEqual(sent[0][1]["intent"], "takeaway")
        o = out["discover"]["options"][0]
        self.assertEqual((o["name"], o["label"]), ("Hungama (test)", "walk-in, no bookings"))

    def test_none_bookable_is_agapis_line(self):
        out, _ = self._search(NONE_BOOK, "book an Indian in Soho")
        self.assertEqual(out["say"], NONE_BOOK["result"]["say_text"])
        self.assertEqual(out["discover"]["options"], [])

    def test_their_words_decide_not_the_models_what(self):
        _, sent = self._search(BOOK, "an Indian restaurant in London", what="Indian restaurant to book")   # the model's paraphrase
        self.assertEqual(sent[0][1]["intent"], "browse")


class TheRatchet(unittest.TestCase):
    def test_one_reader_one_call_no_filter_of_s2s_own(self):
        src = inspect.getsource(API._discover)
        self.assertIn('intent = intent_of(ctx.user_said)', src)   # Sasha 297 · MOVED: read once, then place_kind's answer (a tap) may set it
        self.assertIn('"intent": kind["body"].get("intent") or intent', src)
        self.assertNotRegex(src, r"left_out|reservable|walk.?in|fits_intent")   # S2 never filters on intent itself
        users = [p for p in BACKEND.rglob("*.py") if "tests" not in p.parts and "intent_of(" in p.read_text(errors="ignore")
                 and "agapi/v0.py" not in str(p) and "def intent_of" not in p.read_text(errors="ignore")]
        self.assertEqual(users, [])

    def test_the_card_carries_agapis_label(self):   # the card's own rendering is pinned in frontend/scripts/intent-label-291.test.mjs
        self.assertIn("label", API.DISCOVER_CARD)


if __name__ == "__main__":
    unittest.main()
