"""Sasha 292 · T71 — SHE SHOWS THE CURATED RECOGNITION AgAPI ALREADY GIVES HER (Tyler, 25 Oct: "an array of curated restaurants" —
offered when we have it, never promised).

ROOT TEST (written before the code):
  (1) ONE field: venue.discover's option.recognition (AgAPI recognition.view — list, level, year, source, attribution and its ONE
      sentence `words`, credited and dated; no year → never given). ONE place S2 keeps it: v0._discover → option.recognition
      {words, source_url} → the card (frontend/scripts/recognition-292.test.mjs pins its rendering); the model sees `words` only.
  (2) S2 keeping its own starred list, inventing wording, naming a guide in its own code, or re-ranking a value ask = PATCH.
  (3) She can't state a recognition AgAPI didn't give (only `words` reaches her), or drop one it did (every option keeps it).
Offline: AgAPI's answers below are its v1.34 shape; nothing reaches AgAPI.
    cd backend && python -m unittest tests.test_s292 -v
"""
from __future__ import annotations

import asyncio
import inspect
import pathlib
import unittest
from unittest import mock

from agapi import v0 as API, venue_submit as VS, venues as VN

BACKEND = pathlib.Path(__file__).resolve().parents[1]
ACCT = "00000000-0000-4000-8000-000000002920"
run = asyncio.run
STARS = "Two MICHELIN Stars in the MICHELIN Guide (2026) — per Wikipedia (en)"
BIB = "A Bib Gourmand in the MICHELIN Guide (2026) — per Wikipedia (en)"


def rec(words, url="https://en.wikipedia.org/wiki/List_of_Michelin-starred_restaurants"):
    return {"list": "michelin", "level": "x", "year": 2026, "source": "wikipedia", "source_url": url, "licence": "CC BY-SA 4.0",
            "attribution": "Wikipedia (en)", "fetched_at": "2026-10-24T00:00:00Z", "match": {"by": "place_id"}, "tier": 2, "words": words}


ANSWER = {"ok": True, "result": {
    "say_text": f"I've found a few good options in Madrid — my pick is Casa Uno (test): {STARS}; 4.6★ from 900 reviews.",
    "pick": {"ref": "a", "name": "Casa Uno (test)", "reason": f"Sasha's pick: Casa Uno (test) — {STARS}"},
    "groups": [{"id": "places", "label": "places", "refs": ["a", "b", "c"]}],
    "options": [{"ref": "a", "group": "places", "kind": "place", "name": "Casa Uno (test)", "place_id": "P1", "rank": 1, "recognition": rec(STARS)},
                {"ref": "b", "group": "places", "kind": "place", "name": "Casa Dos (test)", "place_id": "P2", "rank": 2, "recognition": rec(BIB, url="http://x")},
                {"ref": "c", "group": "places", "kind": "place", "name": "Casa Tres (test)", "place_id": "P3", "rank": 3},
                {"ref": "d", "group": "places", "kind": "place", "name": "Casa Cuatro (test)", "place_id": "P4", "rank": 4,
                 "recognition": {"list": "michelin", "words": ""}}]}}


def search(answer, said, what="Spanish restaurant", where="Madrid"):   # Sasha 297 · MOVED: a specific ask (a vague one hears her one question first)
    sent = []

    async def call(account, op, body, approval=None):
        sent.append((op, body))
        return answer
    ctx = API.Ctx(account=ACCT, mode="test", user_said=said, session="s292", surface="s2", via="page")
    with mock.patch.object(VS, "_call", call), mock.patch("agapi.test_venues.search", mock.AsyncMock(return_value=None)), \
            mock.patch.object(VN, "named_on_screen", lambda *a: None):
        return run(API._search_venues(ctx, {"what": what, "where": where, "country": "ES"})), sent


class TheCard(unittest.TestCase):
    def test_each_card_has_agapis_words_or_nothing(self):
        out, _ = search(ANSWER, "book a restaurant in Madrid for 2 tonight")
        got = {o["name"]: o.get("recognition") for o in out["discover"]["options"]}
        self.assertEqual(got["Casa Uno (test)"], {"words": STARS, "source_url": "https://en.wikipedia.org/wiki/List_of_Michelin-starred_restaurants"})
        self.assertEqual(got["Casa Dos (test)"], {"words": BIB})   # its words kept; a link that isn't https dropped
        self.assertIsNone(got["Casa Tres (test)"])                  # none → nothing
        self.assertIsNone(got["Casa Cuatro (test)"])                # empty words → nothing (never a guide name alone)
        self.assertNotIn("licence", str(out["discover"]["options"]))   # only the sentence and its source travel


class HerVoice(unittest.TestCase):
    def test_she_sees_only_agapis_words(self):
        out, _ = search(ANSWER, "book a restaurant in Madrid for 2 tonight")
        v = {x["name"]: x.get("recognition") for x in out["venues"]}
        self.assertEqual((v["Casa Uno (test)"], v["Casa Dos (test)"], v["Casa Tres (test)"]), (STARS, BIB, None))
        self.assertEqual(out["say"], ANSWER["result"]["say_text"])   # AgAPI's own line, said by code — its pick's recognition in it
        self.assertIn("said only as its `recognition` gives it", out["how"])
        self.assertIn("never as a recommendation or a promise", out["how"])


class AValueAskIsAgapisOrder(unittest.TestCase):
    def test_shown_in_agapis_order(self):
        val = {"ok": True, "result": {**ANSWER["result"], "options": [ANSWER["result"]["options"][1], ANSWER["result"]["options"][0],
                                                                    ANSWER["result"]["options"][2]]}}
        out, _ = search(val, "somewhere good value in Mexico City", where="Mexico City")
        self.assertEqual([o["name"] for o in out["discover"]["options"]], ["Casa Dos (test)", "Casa Uno (test)", "Casa Tres (test)"])


class TheRatchet(unittest.TestCase):
    def test_no_guide_named_by_s2_itself(self):
        import re
        for f in (BACKEND / "agapi" / "v0.py", BACKEND / "agapi" / "venues.py", BACKEND / "app" / "agent" / "voice.py",
                  BACKEND / "app" / "agent" / "s2.py"):
            self.assertNotRegex(f.read_text(), re.compile(r"michelin|bib gourmand|50 best|repsol", re.I), f.name)

    def test_one_place_keeps_it(self):
        self.assertIn("recognition", API.DISCOVER_CARD)
        self.assertIn('o.pop("recognition", None)', inspect.getsource(API._discover))


if __name__ == "__main__":
    unittest.main()
