"""Sasha 320 · the demo, effortless: a hand-over is drawn as AgAPI gives it (every kind), and the mic says nothing before a tap.

Root test (written first): (1) one truth — for a hand-over, AgAPI's kind + hand-over (CR 150, kinds/1: venue.discover's kind, handover,
trip); for the mic, the browser's answer AFTER his tap. (2) A train-only branch or a banner flag = PATCH: none here — every kind AgAPI
hands over takes the same card (its line + one button per page), every kind it can't is said in AgAPI's own words; the mic's ONE gate is
"has he tapped" in VoiceButton.reportMicError, for every mic line. (3) Whole class: transport, official_ticketing, unknown / no seller,
flight; and no mic line of any kind before a tap. Offline.

    cd backend && python -m unittest tests.test_s320 -v
"""
from __future__ import annotations

import asyncio
import pathlib
import unittest
from unittest import mock

from agapi import v0 as API
from app.agent import sasha as AG, voice as V

FRONT = pathlib.Path(__file__).resolve().parents[2] / "frontend"
RAIL = [{"operator": "Renfe", "page": "https://www.renfe.com/es/es", "filled": "never"},
        {"operator": "Iryo", "page": "https://iryo.eu/es", "filled": "never"},
        {"operator": "OUIGO España", "page": "https://www.ouigo.com/es/", "filled": "never"}]
AGAPI_TRAIN = {"kind": {"kind": "train", "family": "transport", "route": "operator", "version": "kinds/1"}, "options": [], "groups": [],
               "handover": RAIL, "trip": {"from": "Madrid", "to": "Barcelona", "passengers": 1},
               "say": "Here are the train operators' own booking pages — you choose the train there. Nothing is filled in for you; "
                      "the trip is below to copy.",
               "say_text": "Here are the train operators' own booking pages — you choose the train there. Nothing is filled in for you; "
                           "the trip is below to copy."}


def discover(result, args):
    async def call(account, op, body):
        return {"ok": True, "result": result}
    ctx = API.Ctx(account="acct-320", surface="s2", user_said="train from Madrid to Barcelona on Monday around 1pm, 1 adult")
    with mock.patch("agapi.venue_submit._call", call), mock.patch("agapi.place_kind.held_for", mock.AsyncMock(return_value={"asked": True})), \
            mock.patch("agapi.place_kind.hold", mock.AsyncMock()):
        return asyncio.run(API._discover(ctx, {"what": "train Madrid to Barcelona", "where": "Madrid", **args}))


class EveryKindAgAPIHandsOver(unittest.TestCase):
    def test_a_train_is_one_line_and_a_button_per_operator(self):
        r = discover(AGAPI_TRAIN, {"open_at": "2026-11-02T13:00", "party": 1})
        self.assertEqual(r["say"], "Madrid → Barcelona · Mon 2 Nov · 13:00 · 1 passenger")
        ev = AG.render("search_venues", r, {})
        self.assertEqual((ev["kind"], ev["line"]), ("operators", r["say"]))
        self.assertEqual([(b["label"], b["url"]) for b in ev["buttons"]], [(h["operator"], h["page"]) for h in RAIL])
        said = V.discover_line("search_venues", {"ok": True, "result": r})
        self.assertEqual(said, r["say"])                                                   # said once, by code
        self.assertNotIn("Nothing is filled in", said + str(ev))                           # cut: the line and the buttons only
        self.assertIn("never repeat the line or the buttons", r["how"])                    # "are you there?" → one short line

    def test_the_prado_is_its_official_page_button(self):
        res = {"kind": {"kind": "tickets", "family": "tickets", "route": "official_ticketing"}, "options": [],
               "handover": [{"operator": "Museo del Prado", "page": "https://entradas.museodelprado.es/", "filled": "never"}],
               "say": "Tickets for Museo del Prado are sold on its official page — you pick the time slot there. Nothing is filled in for you."}
        r = discover(res, {"open_at": "2026-11-03T10:00", "party": 2})
        ev = AG.render("search_venues", r, {})
        self.assertEqual(ev["buttons"], [{"label": "Museo del Prado", "url": "https://entradas.museodelprado.es/"}])
        self.assertEqual(r["say"], "Museo del Prado · Tue 3 Nov · 10:00 · 2 people")

    def test_a_kind_it_cannot_hand_over_is_said_in_agapis_words_no_card(self):
        for res in ({"kind": {"kind": "unknown", "family": "unknown"}, "handover": [], "unhandled": True,
                     "say": "I can't do this one yet — it isn't something I know how to book. I've noted it so I can learn it."},
                    {"kind": {"kind": "bus", "family": "transport"}, "handover": [], "unhandled": True,
                     "say": "I can't book buss here yet: I don't have their official booking page. I've noted it so I can learn it."}):
            r = discover(res, {})
            self.assertEqual(r["say"], res["say"])
            self.assertIsNone(AG.render("search_venues", r, {}))                           # nothing to tap: no empty card
            self.assertEqual(V.discover_line("search_venues", {"ok": True, "result": r}), res["say"])

    def test_a_flight_goes_to_the_flight_search(self):
        r = discover({"kind": {"kind": "flight", "family": "flight"}, "handover": [], "next": "travel.find_flights",
                      "say": "That's a flight — I'll search the flights for it."}, {})
        self.assertIn("call search_flights", r["how"])

    def test_a_venue_is_still_the_places_answer(self):
        r = discover({"kind": {"kind": "venue", "family": "venue"}, "options": [], "groups": [], "say_text": "x"}, {})
        self.assertNotIn("operators", r)
        self.assertIn("discover", r)

    def test_the_card_is_drawn_and_the_screen_keeps_it(self):
        src = (FRONT / "app/s2/S2App.tsx").read_text()
        self.assertIn("ev.kind === 'operators'", src)
        self.assertIn("c.k === 'operators'", src)
        self.assertIn("operators", AG.KINDS_S2_PAGE)
        self.assertIn("operators", AG._MODEL_DROP_KEYS)                                      # the buttons are the screen's, never her words


class NoMicLineBeforeATap(unittest.TestCase):
    def test_the_one_gate_is_his_tap(self):
        vb = (FRONT / "app/components/VoiceButton.tsx").read_text()
        gate = vb[vb.index("const reportMicError = useCallback"):vb.index("}, [])", vb.index("const reportMicError = useCallback"))]
        self.assertIn("if (m && !tappedRef.current)", gate)                               # every mic line, held until a tap
        toggle = vb[vb.index("const toggleListening = () => {"):][:200]
        self.assertIn("tappedRef.current = true", toggle)
        self.assertNotIn("stepsFor", vb)
        ms = (FRONT / "lib/mic-state.ts").read_text()
        self.assertIn("Microphone is off — type instead, or allow it in ${browserName()} settings", ms)
        self.assertNotIn("stepsFor()", (FRONT / "app/s2/S2App.tsx").read_text())             # one short line on S2, never the long steps


if __name__ == "__main__":
    unittest.main()
