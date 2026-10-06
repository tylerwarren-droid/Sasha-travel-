"""Sasha 132 · ONE yes covers the escalation: the plan is said in the first read-back; a later email or call is sent
under that yes ONLY when the server finds, in its own records, that the cited yes covered it.

    cd backend && python -m unittest tests.test_escalation_s132 -v
"""
from __future__ import annotations

import asyncio
import os
import unittest
from datetime import date, datetime, time, timezone
from unittest import mock

from booking_signer import escalation as ESC, guest_whatsapp as GW, ladder_routes as LR, ladder_store as LS, proactive as PR
from tests import test_guest_whatsapp_s75 as TG

A = TG.ACCOUNT
PLAN = ESC.plan_line("If you haven't booked on their page within 30 minutes, I'll email them", "if they don't reply within 24 hours, I'll call them")


def link(store, lid, read_id, lines, made=None, run=asyncio.run):
    return run(store.put_link({"link_id": lid, "account_id": A, "read_id": read_id, "platform": "CoverManager", "url": "https://x/y",
                                       "slot_filled": False, "read_back_lines": lines, "read_back_sha256": "0" * 64,
                                       "created_at": made or datetime.now(timezone.utc), "venue_name": "Akiro", "local_date": date(2026, 10, 6),
                                       "local_time": time(21, 0), "local_timezone": "Europe/Madrid", "party_size": 2}))


class Verify(unittest.TestCase):
    def setUp(self):
        self.saved = LR.LADDER_STORE
        LR.LADDER_STORE = LS.MemoryLadderStore()

    def tearDown(self):
        LR.LADDER_STORE = self.saved

    def ok(self, approval, read_id):
        return asyncio.run(ESC.verify(A, approval, read_id))

    def test_a_plan_yes_covers_the_same_venue_only(self):
        link(LR.LADDER_STORE, "l-1", "r-1", ["page", PLAN])
        self.assertIsNone(self.ok({"how": "escalation_plan", "from": {"kind": "link", "id": "l-1"}}, "r-1"))
        self.assertIn("different venue", self.ok({"how": "escalation_plan", "from": {"kind": "link", "id": "l-1"}}, "r-2"))

    def test_without_the_plan_line_it_must_be_asked(self):
        link(LR.LADDER_STORE, "l-2", "r-1", ["page only"])
        self.assertIn("didn't cover further steps", self.ok({"how": "escalation_plan", "from": {"kind": "link", "id": "l-2"}}, "r-1"))

    def test_a_made_up_or_missing_source_is_refused(self):
        self.assertIn("isn't yours", self.ok({"how": "escalation_plan", "from": {"kind": "link", "id": "nope"}}, "r-1"))
        self.assertIn("must name the earlier step", self.ok({"how": "escalation_plan"}, "r-1"))


class Auto(TG.Base):
    def setUp(self):
        super().setUp()
        self.link()
        self.addCleanup(setattr, LR, "LADDER_STORE", LR.LADDER_STORE)
        self.addCleanup(setattr, PR, "STORE", PR.STORE)
        LR.LADDER_STORE, PR.STORE = LS.MemoryLadderStore(), PR.MemoryProactiveStore()
        LR.LADDER_STORE.account_emails = {A: "guest@example.com"}
        TG.run(LR.LADDER_STORE.put_read({"read_id": "r-5", "account_id": A, "created_at": TG.NOW,
                                         "read": {"name": "Akiro", "country": "ES", "facts": [
                                             {"kind": "phone", "value": "+34910000000"}, {"kind": "email", "value": "hola@akiro.es"}]}}))
        self.sent, api = [], GW.api

        async def fake(account, method, path, body=None, timeout=90.0):
            if path == "/api/booking/emails":
                self.prepared = body
                return 200, {"email_id": "e-1", "read_back": {"lines": ["I'll email Akiro"], "sha256": "e" * 64}}
            if path == "/api/booking/emails/e-1/send":
                self.sent.append(body)
                return 200, {"ok": True, "status": "sent"}
            return await api(account, method, path, body, timeout)
        fake.calls = api.calls
        GW.api = fake
        self.addCleanup(setattr, GW, "api", api)
        p = mock.patch.dict(os.environ, {"SASHA_TAP_ESCALATION": "1"})
        p.start()
        self.addCleanup(p.stop)

    def test_the_planned_email_is_sent_without_a_new_question_and_the_guest_is_told(self):
        link(LR.LADDER_STORE, "l-77", "r-5", ["page", PLAN], made=datetime(2026, 10, 3, 10, 0, tzinfo=timezone.utc), run=TG.run)
        self.now = datetime(2026, 10, 3, 10, 40, tzinfo=timezone.utc)
        TG.run(GW.STORE.put_state(GW.wa_key(TG.GUEST), {"history": [], "pending": None, "last_inbound_at": self.now, "link_tries": []}))
        done = TG.run(PR.tap_offers(self.now))
        self.assertEqual([d["outcome"] for d in done], ["auto: sent"])
        self.assertEqual(self.sent[0]["approval"], {"how": "escalation_plan", "from": {"kind": "link", "id": "l-77"}})
        self.assertIn("Your yes covers these steps", self.prepared["plan_line"])          # the email carries the rest: the call
        self.assertIn("so — as you agreed — I've emailed them", self.bodies()[-1])
        self.assertEqual(GW.SENDER.contents, [])                                            # no question asked

    def test_without_a_plan_it_is_still_asked(self):
        link(LR.LADDER_STORE, "l-78", "r-5", ["page"], made=datetime(2026, 10, 3, 10, 0, tzinfo=timezone.utc), run=TG.run)
        self.now = datetime(2026, 10, 3, 10, 40, tzinfo=timezone.utc)
        TG.run(GW.STORE.put_state(GW.wa_key(TG.GUEST), {"history": [], "pending": None, "last_inbound_at": self.now, "link_tries": []}))
        TG.run(PR.tap_offers(self.now))
        self.assertEqual(self.sent, [])
        self.assertTrue(GW.SENDER.contents[-1][0].startswith("Not booked on Akiro's page yet"))


class OneYesOnWhatsApp(TG.Base):
    """The one-tap with a plan: asked ONCE ("Send me their page?" with the plan in the read-back), then the page — made with
    the plan in its stored read-back, which is what later steps cite."""

    def setUp(self):
        super().setUp()
        self.link()
        self.links, api = [], GW.api

        async def fake(account, method, path, body=None, timeout=90.0):
            if path == "/api/booking/venues/read":
                return 200, {"read_id": "r-1", "venue": "Botavara", "country": "ES", "listing": {"name": "Botavara Chamberí"}, "say": "x", "facts": [],
                             "rungs": [{"rung": "link", "available": True, "fact_index": 1, "value": "CoverManager"},
                                       {"rung": "email", "available": True, "fact_index": 2, "value": "hola@botavara.es"}]}
            if path == "/api/booking/links":
                self.links.append(body)
                return 200, {"link_id": "l-1", "url": "https://www.covermanager.com/x", "platform": "CoverManager", "slot_filled": False}
            return await api(account, method, path, body, timeout)
        fake.calls = api.calls
        GW.api = fake
        self.addCleanup(setattr, GW, "api", api)
        p = mock.patch.dict(os.environ, {"SASHA_TAP_ESCALATION": "1"})
        p.start()
        self.addCleanup(p.stop)

    def test_one_yes_then_the_page(self):
        self.say("dinner for 2 in Chamberí on Saturday at 9")
        _, cards = GW.SENDER.contents[-1]
        self.say("x", payload=cards[0][1])
        said = "\n".join(self.bodies())
        self.assertIn("• If you haven't booked on their page within 30 minutes, I'll email them. Your yes covers these steps", said)
        body, buttons = GW.SENDER.contents[-1]
        self.assertTrue(body.startswith("Send me their page?"))
        self.assertEqual(self.links, [])                                                   # nothing made before the yes
        self.say("Yes, send it", payload=buttons[0][1])
        self.assertIn("Your yes covers these steps", self.links[0]["plan_line"])
        self.assertTrue(self.bodies()[-1].startswith("Here's Botavara Chamberí on CoverManager"))   # Sasha 163
