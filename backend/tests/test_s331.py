"""Sasha 331 · how she'll book and why, in one line, from AgAPI's decision (docs/sasha/S-331-route-line.md). Offline.

    cd backend && python -m unittest tests.test_s331 -v
"""
from __future__ import annotations

import asyncio
import inspect
import unittest
from unittest import mock

from agapi import venues as VN
from app.agent import spoken as SP, voice as V

#: every route AgAPI's handoff.decide can return (agapi_service/handoff.py ROUTES, origin/main), with the fields that pick its row
AGAPI_ROUTES = {
    "send_form": {"route": "send_form"}, "ask_then_send": {"route": "ask_then_send"}, "prefilled_page": {"route": "prefilled_page"},
    "platform": {"route": "platform", "channel": "CoverManager booking"}, "reserve_with_google": {"route": "reserve_with_google"},
    "message_email": {"route": "message", "channel": "email", "sender": "kanoe"},
    "message_whatsapp_kanoe": {"route": "message", "channel": "WhatsApp", "sender": "kanoe"},
    "message_whatsapp_person": {"route": "message", "channel": "WhatsApp", "sender": "person"},
    "message_instagram": {"route": "message", "channel": "Instagram", "sender": "person"},
    "call": {"route": "call"}, "call_at_opening": {"route": "call", "row": "call_at_opening", "hours": {"opens_at": "2026-11-04T13:00:00+01:00"}},
    "call_no_voice": {"route": "call", "row": "call_no_voice"}, "no_reservations": {"route": "no_reservations"},
    "none": {"route": "none"}, "none_listing": {"route": "none"},
}

#: Tyler's four (fixtures, no real venue)
FOUR = {
    "an email-only hotel": ({"route": "message", "channel": "email", "sender": "kanoe"},
                            "They don't take bookings online, so I'll email them your request — I'll tell you when they reply."),
    "a WhatsApp venue": ({"route": "message", "channel": "WhatsApp", "sender": "kanoe"}, "They book on WhatsApp — I'll message them for you."),
    "a CoverManager venue": ({"route": "platform_book", "channel": "CoverManager booking"},
                             "They use CoverManager — I can book it directly once you confirm."),
    "a phone-only venue": ({"route": "call", "row": "call_at_opening", "hours": {"opens_at": "2026-11-04T13:00:00+01:00"}},
                           "They take bookings by phone and they're closed now — I'll call when they open at 13:00."),
}


class EveryRouteHasItsLine(unittest.TestCase):
    def test_every_route_agapi_can_return(self):
        for name, dec in AGAPI_ROUTES.items():
            line = V.route_line(dec)
            if dec["route"] == "none":   # the floor: its own words (FLOOR), nothing in front
                self.assertIsNone(line, name)
                continue
            self.assertTrue(line, name)
            self.assertTrue(V.is_route_line(line), name)
            self.assertEqual(V.faults([("assistant", line + " Shall I send this?")]), [], name)   # rule 15's checks let THIS line through
            spoken = SP.speakable(line)
            self.assertIsNone(SP.NEVER_SPOKEN.search(spoken), (name, spoken))                 # the voice line passes the speakable check
            self.assertNotIn("only", line.lower(), name)                                      # positive: never "only by…"
            self.assertNotIn("no online booking form", line.lower(), name)                    # the rest of 15 Oct's rule stands

    def test_never_without_agapis_decision(self):
        for dec in (None, {}, {"route": None}, {"route": "message"}, {"route": "platform"}, {"route": "something_new"}):
            self.assertIsNone(V.route_line(dec), dec)                                          # no decision, no route said
        self.assertEqual(V.faults([("assistant", "They use CoverManager, so easy.")]), ["turn 0: names the channel 'CoverManager'"])
        self.assertFalse(V.is_route_line("They book on WhatsApp — and Instagram too."))        # only the table's own sentences

    def test_one_table_one_place(self):
        src = inspect.getsource(VN)
        self.assertEqual(src.count("V.route_line("), 1)
        self.assertIn("@_says_route", inspect.getsource(VN.hold_venue))   # every answer of hold_venue passes with_route_line
        sasha = inspect.getsource(__import__("app.agent.sasha", fromlist=["x"]))
        self.assertEqual(sasha.count("_V.route_told(r[\"result\"])"), 2)                      # said by code, in front — the one entry


class TheFourOnEveryChannel(unittest.TestCase):
    def test_s2_whatsapp_and_voice(self):
        for name, (dec, want) in FOUR.items():
            line = V.route_line(dec)
            self.assertEqual(line, want, name)
            question = "Shall I send this to Casa Prueba? Every detail is on the card."
            said = f"{V.told_prefix(question, [line])} {question}"                             # sasha.turn: the told line in front, once
            self.assertTrue(said.startswith(want), name)                                      # S2 and WhatsApp: the same text (one turn)
            voice = SP.speakable(V.told_prefix(question, [line]))                             # voice: the same line, spoken
            self.assertIsNone(SP.NEVER_SPOKEN.search(voice), name)
            self.assertEqual(V.told_prefix(f"{line} {question}", [line]), "", name)           # never said twice
            print(f"\n[s331 proof] {name}: S2/WhatsApp «{said}» · voice «{voice}»")


class OncePerBooking(unittest.TestCase):
    def test_hold_keeps_it_for_the_same_booking(self):
        src = inspect.getsource(VN._hold)
        self.assertIn('"route_said": prev["route_said"]', src)

    def test_said_on_the_question_once(self):
        acct = "acct-331"
        out = {"status": "awaiting_yes", "venue": "Casa Prueba", "route": "agapi", "ask": "Shall I send this to Casa Prueba?"}

        async def inner(ctx, a):
            ctx.route_dec = {"route": "message", "channel": "email", "sender": "kanoe"}
            VN._HELD.setdefault(acct, {"venue": "Casa Prueba"})   # the same booking held again (venues._hold keeps route_said)
            return dict(out)
        ctx = type("C", (), {"account": acct})()
        held = VN._says_route(inner)   # hold_venue's own decorator, round a fake hold
        first = asyncio.run(held(ctx, {}))
        again = asyncio.run(held(ctx, {}))
        self.assertEqual(first["route_line"], FOUR["an email-only hotel"][1])
        self.assertNotIn("route_line", again)
        self.assertEqual(V.route_told(first), first["route_line"])
        VN._HELD.pop(acct, None)

    def test_nothing_on_a_handover_or_an_outcome(self):
        ctx = type("C", (), {"account": "acct-331b", "route_dec": {"route": "call"}})()
        for st in ("page_link", "requested", "confirmed", "not_contacted"):
            self.assertNotIn("route_line", VN.with_route_line(ctx, {"status": st}), st)
        ctx.route_dec = None
        self.assertNotIn("route_line", VN.with_route_line(ctx, {"status": "choose_route"}))


if __name__ == "__main__":
    unittest.main()
