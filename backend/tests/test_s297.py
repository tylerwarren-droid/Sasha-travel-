"""Sasha 297 · T75 — "WHAT KIND OF PLACE?" ONE QUICK QUESTION WHEN THE ASK IS VAGUE (Tyler, 27 Oct: "can she ask us what type of
restaurant are you looking for? budget, fine dining (michelin) or take away?").

ROOT TEST (written before the code): (1) the ONE place S2 decides what to ask before a search is agapi/place_kind.py, asked from ONE
site (v0._discover); each answer maps onto AgAPI's OWN behaviour — special: nothing added (recognition first is AgAPI's default) ·
good value: notes "good value" (AgAPI's value ranking) · takeaway / delivery: AgAPI's intent. (2) A second question flow, S2 ranking
places, or a list of S2's = PATCH. (3) She never asks when they already said it, and never twice in a session.
Offline: venue.discover's answers are its v1.39 shape; nothing reaches AgAPI.
    cd backend && python -m unittest tests.test_s297 -v
"""
from __future__ import annotations

import asyncio
import inspect
import pathlib
import unittest
from unittest import mock

from agapi import place_kind as PK, v0 as API, venue_submit as VS, venues as VN
from app.agent import sasha as S, voice as V

BACKEND = pathlib.Path(__file__).resolve().parents[1]
ACCT = "00000000-0000-4000-8000-000000002970"
run = asyncio.run
#: AgAPI v1.39 spec/ext/kanoe-sandbox.schema.json venue_discover_in — additionalProperties: false (Sasha 297: `notes` was refused live)
ALLOWED = {"what", "where", "open_at", "dates", "when_words", "party", "near", "all", "intent"}
FOUND = {"ok": True, "result": {"say_text": "I've found a few good options in Madrid — my pick is Casa Uno (test).",
                                "pick": {"ref": "v1", "name": "Casa Uno (test)", "reason": "r"},
                                "groups": [{"id": "places", "label": "places", "refs": ["v1", "v2"]}],
                                "options": [{"ref": "v2", "group": "places", "kind": "place", "name": "Casa Dos (test)", "place_id": "P2", "rank": 1},
                                            {"ref": "v1", "group": "places", "kind": "place", "name": "Casa Uno (test)", "place_id": "P1", "rank": 2,
                                             "label": "takeaway"}]}}


def search(said, what="restaurant", session="s297-a", where="Madrid"):
    sent = []

    async def call(account, op, body, approval=None):
        sent.append((op, body))
        return FOUND
    ctx = API.Ctx(account=ACCT, mode="test", user_said=said, session=session, surface="s2", via="page")
    with mock.patch.object(VS, "_call", call), mock.patch("agapi.test_venues.search", mock.AsyncMock(return_value=None)), \
            mock.patch.object(VN, "named_on_screen", lambda *a: None), mock.patch("agapi.s2_memory._run", lambda: None):
        out = run(API._search_venues(ctx, {"what": what, "where": where, "country": "ES"}))
    return out, sent


class TheOnePlace(unittest.TestCase):
    def setUp(self):
        PK._HELD.clear()
        VN._SHOWN.pop(ACCT, None)

    def test_a_vague_ask_hears_one_question_and_nothing_is_searched(self):
        out, sent = search("Find me somewhere for dinner in Madrid tonight", what="somewhere for dinner")
        self.assertEqual(sent, [])                                   # no search before the answer
        self.assertEqual(out["kind_ask"], {"ask": V.KIND_ASK, "choices": list(V.KIND_CHOICES)})
        self.assertEqual(V.KIND_ASK, "Something special, good value, or takeaway?")
        self.assertEqual(V.discover_line("search_venues", {"ok": True, "result": out}), V.KIND_ASK)   # said by code, spoken and shown
        self.assertEqual(S.render("search_venues", out, {}), {"type": "render", "kind": "kind_ask", "ask": V.KIND_ASK, "choices": list(V.KIND_CHOICES)})

    def test_each_answer_is_agapis_own_input(self):
        for answer, want in (("Something special", {"intent": "browse", "what": "restaurant"}), ("Good value", {"intent": "browse", "what": "good value restaurant"}),
                             ("Takeaway / delivery", {"intent": "takeaway", "what": "restaurant"}), ("just delivery please", {"intent": "delivery", "what": "restaurant"})):
            PK._HELD.clear()
            search("find me a restaurant", session="s297-b")                          # asked
            out, sent = search(answer, session="s297-b")                              # the model searches again on the answer
            self.assertEqual(len(sent), 1, answer)
            body = sent[0][1]
            self.assertEqual({k: body[k] for k in ("intent", "what") if k in body}, want, answer)
            self.assertLessEqual(set(body), ALLOWED, answer)   # AgAPI's venue_discover_in only (additionalProperties: false)
            self.assertEqual([o["name"] for o in out["discover"]["options"]], ["Casa Dos (test)", "Casa Uno (test)"])   # as AgAPI gave them

    def test_never_when_they_already_said_it(self):
        for said, what in (("Michelin tonight in Madrid", "restaurant"), ("cheap Indian takeaway", "Indian takeaway"),
                           ("somewhere good value for dinner", "restaurant"), ("a fine dining place for our anniversary", "restaurant"),
                           ("pizza delivery to the hotel", "pizza"), ("somewhere to eat right now", "restaurant"),
                           ("book Botín for two at nine", "Botín"), ("an Indian restaurant in Madrid", "Indian restaurant"),
                           ("tapas tonight", "tapas")):
            PK._HELD.clear()
            out, sent = search(said, what=what, session="s297-c")
            self.assertNotIn("kind_ask", out, said)
            self.assertEqual(len(sent), 1, said)

    def test_never_twice_in_a_session_and_the_answer_holds(self):
        search("find me a restaurant", session="s297-d")
        out, sent = search("hmm, not sure", session="s297-d")             # no kind in the answer: the search goes ahead, browse
        self.assertNotIn("kind_ask", out)
        out, sent = search("somewhere for lunch then", what="somewhere for lunch", session="s297-d")   # vague again: never asked again
        self.assertNotIn("kind_ask", out)
        PK._HELD.clear()
        search("find me a restaurant", session="s297-e")
        search("Good value", session="s297-e")
        out, sent = search("and somewhere for lunch tomorrow", what="lunch", session="s297-e")   # the answer holds
        self.assertEqual(sent[0][1]["what"], "good value lunch")
        out, sent = search("find me a restaurant", session="s297-new")    # New chat = a new session: asked once there
        self.assertIn("kind_ask", out)

    def test_a_held_takeaway_never_overrides_book_said_now(self):
        search("find me a restaurant", session="s297-f")
        search("takeaway", session="s297-f")
        out, sent = search("book a table for two", what="restaurant", session="s297-f")
        self.assertEqual(sent[0][1]["intent"], "book")

    def test_the_decision_alone(self):
        self.assertTrue(PK.decide("find a restaurant", "restaurant", "browse", None)["ask"])
        self.assertTrue(PK.decide("a table for two tonight", "dinner", "book", None)["ask"])          # vague on the kind
        self.assertFalse(PK.decide("x", "restaurant", "eat_now", None)["ask"])
        self.assertFalse(PK.decide("x", "restaurant", "browse", {"asked": True, "kind": None})["ask"])
        for w in ("restaurant", "somewhere for dinner", "a nice place to eat", "dinner tonight"):
            self.assertTrue(PK.vague(w), w)
        for w in ("Indian restaurant", "sushi", "tapas bar", "Botín", "steakhouse", "", None):
            self.assertFalse(PK.vague(w), w)


class NoPatch(unittest.TestCase):
    def test_one_call_site_and_no_list_of_s2s(self):
        callers = [p.name for p in (BACKEND / "agapi").glob("*.py") if "PK.decide(" in p.read_text()]
        callers += [p.name for p in (BACKEND / "app" / "agent").glob("*.py") if "PK.decide(" in p.read_text()]
        self.assertEqual(callers, ["v0.py"])
        src = inspect.getsource(PK)
        self.assertNotIn("place_id", src)
        self.assertNotRegex(src, r"(?i)sort|rank\(|options\[")     # it never touches AgAPI's options

    def test_the_words_name_no_guide(self):   # Sasha 292's rule holds for her words: the cards credit a guide, she never names one
        for w in (V.KIND_ASK, *V.KIND_CHOICES):
            self.assertNotRegex(w, r"(?i)michelin|bib|repsol|50 best")


if __name__ == "__main__":
    unittest.main()
