"""Sasha 289 · T69 — THE FIRST REAL BOOKING REACHED THE FLOOR (Barbería Mano Santa Lavapies, Tyler's iPhone, 26 Oct 05:53 UTC).

ROOT TEST (written before the code):
  (1) The ONE truth that decided "floor": AgAPI's decision. Replayed on live (AgAPI-Lane: background, a scratch end user) because S2
      kept no copy: venue.profile and venue.prepare_booking both answered route message · channel WhatsApp · sender person, with the
      button's link, every option's link and prepare's person_send ALL empty — AgAPI decided WhatsApp from its KEPT listing record and
      its prepare (which reads the number fresh) had no number. S2: kanoe_whatsapp → sender person → own_whatsapp(no wa.me) → the floor.
  (2) A Mano Santa special case, a retry, or S2 re-deciding the route (its own number, a call, AgAPI's "book on none found" page as the
      WhatsApp) = PATCH. S2's path is unchanged; the decision is the CR's.
  (3) The ratchet: a message route AgAPI decided reaches the floor ONLY when AgAPI's own answer carries no way to send it — any wa.me
      link (decision.options, decision.button, prepare.person_send) → their own WhatsApp; sender kanoe → Kanoe's card. The link-less
      decision is never silent again: one warning line, and the decision (no link, no number) kept on the booking's measure row.
Offline: a fake AgAPI only — nothing reaches AgAPI, Twilio or a phone.
    cd backend && python -m unittest tests.test_s289 -v
"""
from __future__ import annotations

import json
import unittest

from agapi import measure as MS, venues as VN
from app.agent import voice as V
from tests import test_s287 as T

WA = T.WA
# the decision AgAPI returned for Mano Santa on live (replay of 26 Oct): a WhatsApp route with no link anywhere
MANO = {"route": "message", "channel": "WhatsApp", "how_far": "request", "sender": "person",
        "say_text": "Barbería Mano Santa Lavapies: I'll write it for you, and you send it from your phone; they'll reply to you.",
        "button": {"label": "Send on WhatsApp", "link": None, "sends": False}, "version": "handoff/2.3 · 2026-10-25",
        "options": [{"kind": "whatsapp", "label": "Send on WhatsApp", "link": None, "sends": False}],
        "pending": {"what": "a Google-listing number, used for this one WhatsApp"}}


class Prepared(T.FakeAgAPI):
    """venue.prepare_booking answering with `dec` and `person_send` as given (the rest of AgAPI as 287's fake)."""

    def __init__(self, dec, person_send):
        super().__init__(gate=dec.get("sender") == "kanoe")
        self.dec, self.person_send = dec, person_send

    async def __call__(self, op, body, approval=None, account=None):
        if op == "venue.prepare_booking":
            self.ops.append(op)
            return {"ok": True, "result": {"prepared_id": T.PID, "submitted": False, "link": "https://agapi.test/prepared/x",
                                           "decision": self.dec, "person_send": self.person_send, "channel": "none found"}}
        return await super().__call__(op, body, approval, account)


class Case(T.Base):
    dec, person_send = MANO, None

    def setUp(self):
        super().setUp()
        self.agapi = Prepared(self.dec, self.person_send)
        from unittest import mock
        from agapi import venue_submit as VS
        p = mock.patch.object(VS, "CALL", self.agapi)
        p.start()
        self.p.append(p)

    def tearDown(self):
        for p in reversed(self.p):
            p.stop()


class TheManoSantaDecisionIsTheFloorAndSaysSo(Case):
    """Today's answer (no link anywhere): the floor — S2 doesn't invent a way — and one warning names the contract break."""

    def test_floor_with_a_warning(self):
        with self.assertLogs("agapi.venues", level="WARNING") as lg:
            out = self.hold(T.FULL)
        self.assertEqual(out["status"], "page_link")
        self.assertIn("floor", out)
        self.assertNotIn("venue.submit_booking", self.agapi.ops)
        self.assertEqual(self.agapi.sends, [])
        self.assertTrue(any("AgAPI decided message/WhatsApp (sender person) with no link to send it" in m for m in lg.output), lg.output)
        self.assertNotEqual(out.get("page_url"), "https://agapi.test/prepared/x")   # never AgAPI's "book on none found" page as the WhatsApp


class _OwnWhatsApp:
    def test_their_own_whatsapp_never_the_floor(self):
        out = self.hold(T.FULL)
        self.assertNotIn("floor", out)
        self.assertEqual((out["status"], out["page_url"]), ("page_link", WA))
        self.assertTrue(out["say"].startswith(V.OWN_WHATSAPP))
        self.assertEqual(self.agapi.sends, [])


class ALinkOnTheOptionIsTheirWhatsApp(_OwnWhatsApp, Case):
    dec = {**MANO, "options": [{"kind": "whatsapp", "label": "Send on WhatsApp", "link": WA, "sends": False}]}


class ALinkOnTheButtonIsTheirWhatsApp(_OwnWhatsApp, Case):
    dec = {**MANO, "button": {"label": "Send on WhatsApp", "link": WA, "sends": False}}


class PrepareSPersonSendIsTheirWhatsApp(_OwnWhatsApp, Case):
    person_send = {"whatsapp": WA, "kanoe_sends": False}


class KanoeSendsIsKanoesCard(Case):
    dec = {**MANO, "sender": "kanoe", "button": {"label": "Send the request", "link": None, "sends": True}}

    def test_kanoes_card_never_the_floor(self):
        out = self.hold(T.FULL)
        self.assertNotIn("floor", out)
        self.assertIn("venue.submit_booking", self.agapi.ops)


class TheDecisionIsKeptOnTheBooking(unittest.TestCase):
    """The next trace is read from S2's own row: route, channel, sender, how far and whether each way carried a link — no link, no number."""

    def setUp(self):
        self.rows = {}

        async def w(row):
            self.rows[row["id"]] = row
        MS.WRITE = w
        MS._BOOKINGS.clear(); MS._OF.clear(); MS._LAST.clear(); MS._Q = None; MS._WRITER = None

    def tearDown(self):
        MS.WRITE = None
        MS._Q = None; MS._WRITER = None

    def test_kept(self):
        import asyncio
        import types
        ctx = types.SimpleNamespace(account=T.ACCT, surface="s2", session="s289")

        async def go():
            MS.turn_start(T.ACCT, "s289", "s2")
            MS.tool(ctx, "read_booking_route", {"place_id": "ChIJmano"}, {"ok": True, "result": {"routes": ["message"]}}, 40)
            MS.agapi_op("venue.prepare_booking", {}, {"ok": True, "result": {"decision": MANO, "person_send": None,
                                                                             "link": "https://agapi.test/prepared/x"}}, 90, "https://agapi.test")
            await MS.flush()
        asyncio.run(go())
        row = next(r for r in self.rows.values() if r["kind"] == "booking")
        d = row["data"]["_src"]["decisions"][-1]
        self.assertEqual(d, {"op": "venue.prepare_booking", "route": "message", "channel": "WhatsApp", "sender": "person",
                             "how_far": "request", "button_link": False, "button_sends": False, "option_links": 0, "person_send": False})
        self.assertNotIn("https://", json.dumps(d))

    def test_a_link_is_counted_never_kept(self):
        d = MS.decision_of("venue.prepare_booking", {"decision": {**MANO, "button": {"link": WA}}, "person_send": {"whatsapp": WA}})
        self.assertEqual((d["button_link"], d["person_send"]), (True, True))
        self.assertNotIn("wa.me", json.dumps(d))


if __name__ == "__main__":
    unittest.main()
