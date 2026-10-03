"""Sasha 130 (2) · the decision workflow: one function, every branch, the reason the guest sees.

    cd backend && python -m unittest tests.test_decide_s130 -v
"""
from __future__ import annotations

import unittest

from booking_signer.decide import Venue, decide, preference


class Decide(unittest.TestCase):
    def test_own_form_wins(self):
        d = decide(Venue(form=True, platform="CoverManager", phone=True, email=True, open_now=True))
        self.assertEqual(d.route, "form")
        self.assertIn("their own website's form", d.reason)
        self.assertEqual(d.alternatives, ["one_tap", "call", "email"])

    def test_platform_only_is_one_tap_with_the_call_offered(self):
        d = decide(Venue(platform="CoverManager", phone=True, open_now=True))
        self.assertEqual(d.route, "one_tap")
        self.assertIn("They book only through CoverManager", d.reason)
        self.assertIn("you press confirm (I can't press it for you)", d.reason)
        self.assertIn("file their confirmation email from your Gmail", d.reason)
        self.assertIn("Or I can call them", d.reason)
        self.assertEqual(decide(Venue(platform="CoverManager", phone=True, open_now=True), prefer="call").route, "call")
        self.assertNotIn("Or I can call", decide(Venue(platform="TheFork", phone=True, calls_on=False)).reason)

    def test_open_phone_scripted_is_a_call(self):
        d = decide(Venue(phone=True, email=True, open_now=True, scripted=True))
        self.assertEqual((d.route, d.then), ("call", None))
        self.assertIn("they're open now", d.reason)

    def test_closed_is_email_then_a_call_offered_at_opening(self):
        d = decide(Venue(phone=True, email=True, open_now=False, opens_at="13:00"))
        self.assertEqual(d.route, "email")
        self.assertIn("they're closed right now", d.reason)
        self.assertEqual(d.then, "If they haven't replied by their opening (13:00), I'll ask you here whether to call them.")

    def test_unscripted_language_is_email_then_an_english_call(self):
        d = decide(Venue(phone=True, email=True, open_now=True, scripted=False, language_label="Vietnamese"))
        self.assertEqual(d.route, "email")
        self.assertIn("I can't call in Vietnamese", d.reason)
        self.assertIn("whether to call them, in English", d.then)

    def test_email_only(self):
        d = decide(Venue(email=True))
        self.assertEqual((d.route, d.then), ("email", None))
        self.assertIn("email is the only way they publish", d.reason)

    def test_hours_unknown_with_email_never_rings_blind(self):
        self.assertIn("I don't know their hours", decide(Venue(phone=True, email=True)).reason)

    def test_closed_phone_only_calls_at_opening(self):
        d = decide(Venue(phone=True, open_now=False, opens_at="13:00"))
        self.assertEqual(d.route, "call")
        self.assertIn("when they open at 13:00", d.reason)

    def test_unscripted_phone_only_is_english_abroad_said_as_such(self):
        d = decide(Venue(phone=True, open_now=True, scripted=False, language_label="Vietnamese"))
        self.assertEqual(d.route, "call")
        self.assertIn("I'll call in English — they may not speak it", d.reason)

    def test_nothing_usable(self):
        self.assertEqual(decide(Venue(phone=True, calls_on=False)).route, None)
        self.assertEqual(decide(Venue()).reason, "I found no way to book them that I may use.")

    def test_the_guest_overrides_and_an_impossible_wish_is_said(self):
        v = Venue(form=True, phone=True, email=True, open_now=True)
        self.assertEqual(decide(v, prefer="email").route, "email")
        self.assertTrue(decide(v, prefer="email").reason.startswith("As you asked"))
        d = decide(Venue(form=True), prefer="call")
        self.assertEqual(d.route, "form")
        self.assertTrue(d.reason.startswith("I can't call them: they publish no number."))

    def test_preference_words(self):
        self.assertEqual(preference("call them instead"), "call")
        self.assertEqual(preference("llámales"), "call")
        self.assertEqual(preference("just email them"), "email")
        self.assertEqual(preference("send me the link, I'll book it myself"), "one_tap")
        self.assertIsNone(preference("yes"))


from booking_signer import guest_whatsapp as GW  # noqa: E402
from tests import test_guest_whatsapp_s75 as TG  # noqa: E402


class OnWhatsApp(TG.Base):
    """The decision on the phone: its reason first, then that route's own read-back or page; the guest's override."""

    def setUp(self):
        super().setUp()
        self.link()
        self.rungs = []
        self.sent = []
        api = GW.api

        async def fake(account, method, path, body=None, timeout=90.0):
            if path == "/api/booking/venues/read":
                return 200, {"read_id": "r-1", "venue": "Botavara", "country": "ES", "listing": {"name": "Botavara Chamberí"},
                             "rungs": self.rungs, "say": "x", "facts": []}
            if path == "/api/booking/links":
                return 200, {"link_id": "l-1", "url": "https://www.covermanager.com/reserve/botavara", "platform": "CoverManager", "slot_filled": True}
            if path == "/api/booking/links/l-1/booked":
                return 200, {"ok": True}
            if path == "/api/booking/emails":
                return 200, {"email_id": "e-12345678", "read_back": {"lines": ["I'll email Botavara Chamberí at hola@botavara.es"], "sha256": "e" * 64}}
            if path == "/api/booking/emails/e-12345678/send":
                self.sent.append(body)
                return 200, {"ok": True, "status": "sent", "say": "Sent"}
            return await api(account, method, path, body, timeout)
        fake.calls = api.calls
        GW.api = fake
        self.addCleanup(setattr, GW, "api", api)
        from booking_signer import ladder_routes as LR, ladder_store as LS
        self.addCleanup(setattr, LR, "LADDER_STORE", LR.LADDER_STORE)
        LR.LADDER_STORE = LS.MemoryLadderStore()
        LR.LADDER_STORE.account_emails = {TG.ACCOUNT: "guest@example.com"}

    def test_platform_only_is_one_tap_and_booked_starts_the_gmail_check(self):
        self.rungs = [{"rung": "link", "available": True, "fact_index": 1, "value": "https://www.covermanager.com/reserve/botavara"}]
        self.pick_first()
        said = "\n".join(self.bodies())
        self.assertIn("They book only through CoverManager.", said)
        self.assertIn("One tap: Botavara Chamberí's booking page on CoverManager — the day, time and party are filled in. "
                      "Press their confirm button; I can't press it for you.", said)
        self.say("BOOKED")
        self.assertIn("I'm looking for their confirmation email in your Gmail now.", self.bodies()[-1])
        self.assertIn("watch_gmail_confirmation", self.spawned)

    def test_hours_unknown_with_email_is_email_then_a_call_offered(self):
        self.rungs = [{"rung": "phone", "available": True, "fact_index": 2, "value": "+34 91 000"},
                      {"rung": "email", "available": True, "fact_index": 3, "value": "hola@botavara.es"}]
        self.pick_first()
        said = "\n".join(self.bodies())
        self.assertIn("I'll email them — I don't know their hours, so I won't ring them blind.", said)
        _, buttons = GW.SENDER.contents[-1]
        self.say("Yes, book it", payload=buttons[0][1])
        self.assertEqual(len(self.sent), 1)
        self.assertIn("✉️ Emailed Botavara Chamberí", "\n".join(self.bodies()))
        self.assertIn("Not booked yet", "\n".join(self.bodies()))
        self.assertTrue(self.bodies()[-1].startswith("✉️ Emailed Botavara Chamberí"))   # no promise: 028 not applied, flag off

    def test_the_guest_says_call_them_instead(self):
        self.rungs = [{"rung": "phone", "available": True, "fact_index": 2, "value": "+34 91 000"},
                      {"rung": "email", "available": True, "fact_index": 3, "value": "hola@botavara.es"}]
        self.pick_first()
        self.say("call them instead")
        self.assertIn("As you asked: I'll call them, after your yes.", self.bodies())
        self.assertIn("/api/booking/calls", self.api_paths())
        self.assertEqual(self.sent, [])

    def pick_first(self):
        self.say("dinner for 2 in Chamberí on Saturday at 9")
        _, buttons = GW.SENDER.contents[-1]
        self.say("A Very Long…", payload=buttons[0][1])


class NoReplyCall(TG.Base):
    """Email, then — no reply, and they've just opened — ONE question on WhatsApp; its yes leads to the call's own read-back."""

    def setUp(self):
        super().setUp()
        import os
        from datetime import datetime, timezone
        from unittest import mock
        from booking_signer import ladder_routes as LR, ladder_store as LS, proactive as PR
        self.link()
        self.addCleanup(setattr, LR, "LADDER_STORE", LR.LADDER_STORE)
        self.addCleanup(setattr, PR, "STORE", PR.STORE)
        LR.LADDER_STORE, PR.STORE = LS.MemoryLadderStore(), PR.MemoryProactiveStore()
        week = {str(d): [["13:00", "16:00"], ["20:00", "23:30"]] for d in range(7)}
        TG.run(LR.LADDER_STORE.put_read({"read_id": "r-9", "account_id": TG.ACCOUNT, "created_at": TG.NOW,
                                         "read": {"name": "Botavara Chamberí", "country": "ES", "facts": [
                                             {"kind": "phone", "value": "+34910000000", "source_label": "their website"},
                                             {"kind": "hours", "source_kind": "site", "source_label": "their website", "evidence": {"week": week}}]}}))
        self.row = {"id": "t-77777777", "venue": "Botavara Chamberí", "date": "2026-10-03", "time": "21:30", "timezone": "Europe/Madrid",
                    "status": "requested", "channel": "email", "read_id": "r-9", "what": "a table", "category": "restaurant", "count": 2}
        self.p = [mock.patch.object(GW, "_upcoming", side_effect=lambda a: [self.row]), mock.patch.dict(os.environ, {"SASHA_NO_REPLY_CALL": "1"})]
        for x in self.p:
            x.start()
            self.addCleanup(x.stop)
        self.dt = datetime

    def test_offered_once_at_opening_and_the_yes_prepares_the_call(self):
        from booking_signer import proactive as PR
        from datetime import datetime, timezone
        self.now = datetime(2026, 10, 3, 18, 10, tzinfo=timezone.utc)                  # 20:10 Madrid: just opened
        GW.NOW = lambda: self.now
        TG.run(GW.STORE.put_state(GW.wa_key(TG.GUEST), {"history": [], "pending": None, "last_inbound_at": self.now, "link_tries": []}))
        done = TG.run(PR.no_reply_offers(self.now))
        self.assertEqual([d["outcome"] for d in done], ["sent"])
        body, buttons = GW.SENDER.contents[-1]
        self.assertTrue(body.startswith("No reply yet from Botavara Chamberí to my email about Saturday 3 October at 21:30. They've just opened"))
        self.assertEqual(TG.run(PR.no_reply_offers(self.now)), [])                     # once
        self.say("Yes, prepare the call", payload=buttons[0][1])
        self.assertIn("/api/booking/calls", self.api_paths())                         # the call's own read-back follows
        self.assertNotIn("/place", " ".join(self.api_paths()))                        # nothing dialled

    def test_not_while_still_closed_nor_long_after_opening(self):
        from booking_signer import proactive as PR
        from datetime import datetime, timezone
        for hhmm in ((17, 0), (21, 0)):                                              # 19:00 closed; 23:00 open 3 h
            self.now = datetime(2026, 10, 3, *hhmm, tzinfo=timezone.utc)
            TG.run(GW.STORE.put_state(GW.wa_key(TG.GUEST), {"history": [], "pending": None, "last_inbound_at": self.now, "link_tries": []}))
            self.assertEqual(TG.run(PR.no_reply_offers(self.now)), [])
