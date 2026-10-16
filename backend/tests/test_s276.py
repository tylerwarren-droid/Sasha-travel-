"""Sasha 276 · /s2 SHOWS AgAPI venue.discover's grouped options and its pick (v1.18, CR 106) — and keeps no rule of her own.
    · /s2's search_venues asks venue.discover — the ONE discovery path there (never venues/find, never her own Places search)
    · groups in AgAPI's order, its options (never their unconfirmed contacts), the ONE pick and its reason; refused → its line, no cards;
      checks → their question first; her line is AgAPI's say_text, said by code with its cards
    · old S1 (parity off) and WhatsApp's brain (its list cards, until Sasha 277) keep their search as it was
    · no ranking, category, platform or permission rule in her /s2 prompt or her /s2 tool descriptions
Offline: the three answers below are agapi-sandbox's own (16 Oct, v1.18.0 — dog walker / cocaine / wine delivery), trimmed.
    cd backend && python -m unittest tests.test_s276 -v
"""
from __future__ import annotations

import asyncio
import json
import pathlib
import unittest
from unittest import mock

from agapi import v0 as API, venue_submit as VS, venues as VN
from app.agent import s2 as S2, sasha as AG, voice as V

BACKEND = pathlib.Path(__file__).resolve().parents[1]
FRONT = BACKEND.parent / "frontend"
ACCT = "00000000-0000-4000-8000-000000002760"
run = asyncio.run

DOG = {"ok": True, "agapi": "1.2", "result": {
    "say_text": "There are lots of dog walkers around Madrid. I've found four platforms with lots of dog walkers, and five private options nearby — any preference? Or we can pick the right one together.",
    "pick": {"ref": "ven_A", "name": "Casa Marea (test)", "reason": "Sasha's pick: Casa Marea (test) — offers dog walking; 4.7★ from 2,209 reviews"},
    "groups": [{"id": "places", "label": "places", "refs": ["ven_A", "ven_B"], "more": 3}, {"id": "platforms", "label": "platforms", "refs": ["mkt_rover"], "more": 0},
               {"id": "private", "label": "private options", "refs": ["web_1"], "more": 1}],
    "options": [
        {"ref": "ven_A", "group": "places", "kind": "place", "name": "Casa Marea (test)", "type": "Dog walker", "rating": 4.7, "reviews": 2209, "price_level": 2,
         "place_id": "ChIJtestA", "link": "https://www.google.com/maps/search/?api=1&query_place_id=ChIJtestA", "next": {"operation": "venue.profile"}, "rank": 1,
         "photo": {"url": "https://agapi-sandbox.example.test/photo/x", "by": "A. Author"}},
        {"ref": "ven_B", "group": "places", "kind": "place", "name": "Mesón Encina (test)", "rating": 4.1, "reviews": 1360, "place_id": "ChIJtestB", "rank": 2},
        {"ref": "mkt_rover", "group": "platforms", "kind": "marketplace", "name": "Rover", "feel": "a large marketplace of vetted walkers", "link": "https://www.rover.com/es/x/",
         "hand_over": {"link": "https://www.rover.com/es/x/", "fields": [{"label": "Service", "value": "Dog walking"}, {"label": "Where", "value": "Madrid"}],
                       "say": "Choose your dog walker on Rover — your details are ready to copy."}, "rank": 9},
        {"ref": "web_1", "group": "private", "kind": "independent", "name": "The Walking Dog", "link": "https://the-walking-dog.example.test",
         "contacts": [{"kind": "email", "value": "walker@example.test", "confirmed": False}], "next": {"operation": "venue.profile", "input": {"url": "x"}}, "rank": 13}]}}
DRUGS = {"ok": True, "result": {"refused": True, "say_text": "That's not something I can arrange. I can help with a great bar or a night out.", "groups": [], "options": []}}
WINE = {"ok": True, "result": {"say_text": "I've found a few good options in Madrid — my pick is El Barril (test).", "pick": {"ref": "ven_W", "reason": "r"},
        "checks": {"category": "alcohol", "ask_text": "Just to check, are you 18 or over?", "say_text": "I can help with that — just to check, are you 18 or over?"},
        "groups": [{"id": "places", "label": "places", "refs": ["ven_W"]}], "options": [{"ref": "ven_W", "kind": "place", "name": "El Barril (test)", "place_id": "ChIJw"}]}}


def _ctx(surface="s2", via="page"):
    return API.Ctx(account=ACCT, mode="test", user_said="find me a dog walker", session="s276", surface=surface, via=via)


class Discover(unittest.TestCase):
    def setUp(self):
        VN._SHOWN.pop(ACCT, None)

    def _search(self, answer, args=None, ctx=None):
        sent = []

        async def call(account, op, body, approval=None):
            sent.append((op, body))
            return answer
        with mock.patch.object(VS, "_call", call), mock.patch("agapi.test_venues.search", mock.AsyncMock(return_value=None)), \
                mock.patch.object(VN, "named_on_screen", lambda *a: None):
            out = run(API._search_venues(ctx or _ctx(), args or {"what": "dog walker", "where": "Madrid", "country": "ES",
                                                                 "dates": {"from": "2026-10-19", "to": "2026-10-23"}, "when_words": "next week"}))
        return out, sent

    def test_one_question_to_agapi(self):
        out, sent = self._search(DOG)
        self.assertEqual([op for op, _ in sent], ["venue.discover"])
        self.assertEqual(sent[0][1], {"what": "dog walker", "where": {"query": "Madrid", "country": "ES"}, "dates": {"from": "2026-10-19", "to": "2026-10-23"},
                                      "when_words": "next week"})
        d = out["discover"]
        self.assertEqual([g["id"] for g in d["groups"]], ["places", "platforms", "private"])   # AgAPI's order, as it is
        self.assertEqual([o["ref"] for o in d["options"] if o["pick"]], ["ven_A"])           # the ONE pick
        self.assertEqual(d["pick"]["reason"], DOG["result"]["pick"]["reason"])
        self.assertEqual(out["say"], DOG["result"]["say_text"])
        self.assertNotIn("contacts", json.dumps(d))                                          # unconfirmed contacts never reach the screen
        self.assertEqual(next(o for o in d["options"] if o["kind"] == "marketplace")["hand_over"]["fields"][0], {"label": "Service", "value": "Dog walking"})
        shown = VN._SHOWN.get(ACCT) or {}
        self.assertIn("ChIJtestA", shown)                                                    # a place tap finds its card
        self.assertEqual((shown.get("web_1") or {}).get("website"), "https://the-walking-dog.example.test")   # an independent: its own site
        self.assertNotIn("place_id", shown["web_1"])                                         # its ref is AgAPI's option id, never a listing
        self.assertEqual(VN.card_of(ACCT, None, "The Walking Dog")["website"], "https://the-walking-dog.example.test")   # its tap: by name
        self.assertNotIn("mkt_rover", shown)                                                 # a marketplace is never a booking card

    def test_refused_is_its_line_and_nothing_else(self):
        out, _ = self._search(DRUGS, {"what": "cocaine", "where": "Madrid"})
        self.assertTrue(out["refused"])
        self.assertEqual(out["say"], DRUGS["result"]["say_text"])
        self.assertEqual((out["discover"]["groups"], out["discover"]["options"]), ([], []))
        ev = AG.render("search_venues", out, {})
        self.assertEqual(ev["kind"], "discover"); self.assertEqual(ev["options"], [])

    @unittest.skipUnless(FRONT.exists(), "the frontend isn't beside the backend here (Railway's image)")
    def test_the_screen(self):
        fe = (FRONT / "app" / "s2" / "S2App.tsx").read_text(encoding="utf-8")
        self.assertIn("ev.kind === 'discover' && Array.isArray(ev.groups) && Array.isArray(ev.options) && ev.options.length", fe)   # refused: no cards
        self.assertIn("onBook={o.kind === 'independent' ? (n: string) => choose(n, '') : choose}", fe)   # an independent's ref never sent as place_id
        self.assertIn("data-hand-over-link", fe); self.assertIn("data-copy", fe)                              # a marketplace: their link + copy, no send
        self.assertNotIn("contacts", fe.split("function DiscoverCards", 1)[1].split("\nfunction ", 1)[0])    # unconfirmed contacts never drawn

    def test_checks_ask_first(self):
        out, _ = self._search(WINE, {"what": "wine delivery", "where": "Madrid", "open_at": "2026-10-16T21:00"})
        self.assertEqual(out["say"], "I can help with that — just to check, are you 18 or over?")
        self.assertEqual(out["checks"], {"ask_text": "Just to check, are you 18 or over?"})
        self.assertIn("book nothing until they answer checks.ask_text", out["how"])

    def test_said_by_code_with_its_cards(self):
        out, _ = self._search(DOG)
        r = {"ok": True, "result": out}
        self.assertEqual(V.discover_line("search_venues", r), DOG["result"]["say_text"])
        self.assertEqual(V.discover_line("hold_venue", r), "")
        self.assertNotIn("discover", json.dumps(AG.model_result(r, "search_venues")))      # the model gets the names and the line only
        src = (BACKEND / "app" / "agent" / "sasha.py").read_text(encoding="utf-8")
        self.assertIn("or _V.discover_line(u.name, r)) if honest else", src)               # the turn ends on it (read_back_said)
        self.assertIn('if tool == "search_venues" and isinstance(res.get("discover"), dict):', src)

    def test_one_path_on_s2_whatsapp_and_old_s1_unchanged(self):
        for ctx in (_ctx("s2", "wa"), _ctx("s1")):
            with mock.patch.object(VS, "_call", mock.AsyncMock()) as call, mock.patch("agapi.test_venues.search", mock.AsyncMock(return_value=None)), \
                    mock.patch.object(VN, "named_on_screen", lambda *a: None), \
                    mock.patch("booking_signer.guest_whatsapp.api", mock.AsyncMock(return_value=(503, {"rule": "x"}))) as find:
                with self.assertRaises(API.ToolError):
                    run(API._search_venues(ctx, {"what": "dog walker", "where": "Madrid"}))
            call.assert_not_called()                                                         # never venue.discover there
            self.assertEqual(find.call_args[0][2], "/api/booking/venues/find")               # their search, as it was
        src = (BACKEND / "agapi" / "v0.py").read_text(encoding="utf-8")
        self.assertEqual(src.count('if ctx.surface == "s2" and getattr(ctx, "via", "page") == "page":'), 2)   # search_venues + _search_venues
        self.assertIn('via="wa" if wa else "page"', (BACKEND / "app" / "agent" / "sasha.py").read_text(encoding="utf-8"))


class NoRuleOfHerOwn(unittest.TestCase):
    """The whole class: what she shows on /s2 is AgAPI's decision — no ranking, category, platform or permission rule in her prompt
    or her tools' words. Fails the day one appears."""

    MARKERS = ("Rover", "OpenTable", "TheFork", "CoverManager", "PetBacker", "Gudog", "Animalin", "TuriTop", "Fresha", "Treatwell",
               "cocaine", "drug", "escort", "weapon", "alcohol", "tobacco", "gambling", "18 or over", "21 or over", "not_permitted",
               "prefill_link", "fill_browser", "rating + reviews", "ranking", "score_parts", "rank them", "rank by", "marketplace")

    def test_her_s2_prompt_and_tools(self):
        tools = json.dumps([{**t, "description": S2.S2_SEARCH, "input_schema": S2.search_schema(t["input_schema"])} if t["name"] == "search_venues" else t
                            for t in API.TOOLS if t["name"] in S2.S2_TOOLS], default=str)
        for where, text in (("her /s2 prompt", S2.s2_system()), ("her /s2 tools", tools)):
            for m in self.MARKERS:
                self.assertNotIn(m.lower(), text.lower(), f"{m!r} in {where} — AgAPI decides that, not Sasha")

    def test_the_discover_path_has_no_rule(self):
        src = (BACKEND / "agapi" / "v0.py").read_text(encoding="utf-8")
        body = src.split("async def _discover(ctx: Ctx, a: dict) -> dict:", 1)[1].split("\nasync def ", 1)[0].split("\n# ──", 1)[0]
        for m in ("sorted(", ".sort(", "score", "rating >", "reviews >", "PLATFORM", "CATEGOR", "REFUS", "not_permitted"):   # `refused` is AgAPI's own flag, passed on
            self.assertNotIn(m, body, m)

    def test_in_the_gate(self):
        self.assertIn('["tests.test_s276"]', (BACKEND / "scripts" / "one_truth_suite.py").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
