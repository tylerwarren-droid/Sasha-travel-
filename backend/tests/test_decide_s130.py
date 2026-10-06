"""Sasha 130 (2) · the decision workflow: one function, every branch, the reason the guest sees.

    cd backend && python -m unittest tests.test_decide_s130 -v
"""
from __future__ import annotations

import unittest

from booking_signer.decide import Venue, decide, preference


class Decide(unittest.TestCase):
    """Sasha 131 · the founder's escalation policy."""

    def test_own_form_wins(self):
        d = decide(Venue(form=True, platform="CoverManager", phone=True, email=True, open_now=True, hours_until=2))
        self.assertEqual(d.route, "form")                                             # even urgent: their form first
        self.assertIn("their own website's form", d.reason)

    def test_one_tap_is_the_default_even_when_they_are_open_with_a_phone(self):
        d = decide(Venue(platform="CoverManager", phone=True, email=True, open_now=True, hours_until=72))
        self.assertEqual(d.route, "one_tap")
        self.assertIn("They book through CoverManager", d.reason)
        self.assertIn("you press confirm (I can't press it for you)", d.reason)
        self.assertEqual(d.then, "If you haven't booked on their page within 30 minutes, I'll email them; if they don't reply within 24 hours, "
                                 "I'll call them. Your yes covers these steps — I'll ask you again only if something changes (a new time, a deposit, a cost).")
        self.assertEqual(d.alternatives, ["call_email", "call", "email"])

    def test_calls_are_no_longer_the_default_for_an_open_venue(self):
        d = decide(Venue(phone=True, email=True, open_now=True, hours_until=72))
        self.assertEqual(d.route, "email")
        self.assertTrue(d.then.startswith("If they don't reply within 24 hours, I'll call them. Your yes covers these steps"))

    def test_urgent_is_call_and_email_at_once_on_one_yes(self):
        d = decide(Venue(platform="CoverManager", phone=True, email=True, open_now=True, hours_until=5))
        self.assertEqual(d.route, "call_email")
        self.assertIn("It's within 24 hours, so I'll call them and email them at once — one yes covers both.", d.reason)
        self.assertEqual(decide(Venue(platform="TheFork", phone=True, hours_until=5)).route, "call")
        self.assertEqual(decide(Venue(platform="TheFork", hours_until=5)).route, "one_tap")    # nothing else exists

    def test_every_threshold_is_a_setting(self):
        import os
        from unittest import mock
        with mock.patch.dict(os.environ, {"SASHA_URGENT_HOURS": "6", "SASHA_TAP_WINDOW_MIN": "10", "SASHA_EMAIL_REPLY_HOURS": "12"}):
            self.assertEqual(decide(Venue(phone=True, email=True, hours_until=8)).route, "email")
            self.assertIn("within 12 hours", decide(Venue(phone=True, email=True, hours_until=8)).then)
            self.assertIn("within 10 minutes", decide(Venue(platform="CoverManager", email=True)).then)

    def test_unscripted_language_email_then_an_english_call(self):
        d = decide(Venue(phone=True, email=True, scripted=False, language_label="Vietnamese", hours_until=48))
        self.assertEqual(d.route, "email")
        self.assertIn("I'll call them (in English). Your yes covers these steps", d.then)
        d = decide(Venue(phone=True, email=True, scripted=False, language_label="Vietnamese", hours_until=3))
        self.assertIn("I can't speak Vietnamese, so the call is in English.", d.reason)

    def test_phone_only_calls(self):
        d = decide(Venue(phone=True, open_now=False, opens_at="13:00"))
        self.assertEqual(d.route, "call")
        self.assertIn("when they open at 13:00", d.reason)

    def test_nothing_usable(self):
        self.assertEqual(decide(Venue(phone=True, calls_on=False)).route, None)
        self.assertEqual(decide(Venue()).reason, "I found no way to book them that I may use.")

    def test_the_guest_overrides_and_an_impossible_wish_is_said(self):
        v = Venue(form=True, phone=True, email=True, open_now=True)
        self.assertEqual(decide(v, prefer="call").route, "call")
        self.assertTrue(decide(v, prefer="call").reason.startswith("As you asked"))
        self.assertEqual(decide(v, prefer="call_email").route, "call_email")
        d = decide(Venue(form=True), prefer="call")
        self.assertEqual(d.route, "form")
        self.assertTrue(d.reason.startswith("I can't call them: they publish no number."))

    def test_preference_words(self):
        self.assertEqual(preference("call them instead"), "call")
        self.assertEqual(preference("llámales"), "call")
        self.assertEqual(preference("just email them"), "email")
        self.assertEqual(preference("call and email them"), "call_email")
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
        self.assertIn("They book through CoverManager. I'll fill it in and send the last step to your phone.", said)   # Sasha 161
        self.assertIn("One tap: Botavara Chamberí's booking page on CoverManager — the day, time and party are filled in. "
                      "Press their confirm button; I can't press it for you.", said)
        self.say("BOOKED")
        self.assertIn("I'm looking for their confirmation email in your Gmail now.", self.bodies()[-1])
        self.assertIn("watch_gmail_confirmation", self.spawned)

    def test_no_page_no_form_is_email_not_a_call_even_with_a_phone(self):
        self.rungs = [{"rung": "phone", "available": True, "fact_index": 2, "value": "+34 91 000"},
                      {"rung": "email", "available": True, "fact_index": 3, "value": "hola@botavara.es"}]
        self.pick_first()
        said = "\n".join(self.bodies())
        self.assertNotIn("I'll email them", said)   # Sasha 158 · the route is the ops console's, never explained
        _, buttons = GW.SENDER.contents[-1]
        self.say("Yes, book it", payload=buttons[0][1])
        self.assertEqual(len(self.sent), 1)
        self.assertEqual(self.bodies()[-1], GW.DONE_ASKED)   # Sasha 158 · one sentence after; no promise: 028 not applied, flag off

    def test_the_guest_says_call_them_instead(self):
        self.rungs = [{"rung": "phone", "available": True, "fact_index": 2, "value": "+34 91 000"},
                      {"rung": "email", "available": True, "fact_index": 3, "value": "hola@botavara.es"}]
        self.pick_first()
        self.say("call them instead")
        self.assertIn("I'll call them", GW.SENDER.contents[-1][0])   # Sasha 161 · their ask answered in the one line
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
                    "status": "requested", "channel": "email", "read_id": "r-9", "requested_at": "2026-10-02T12:00:00+00:00", "what": "a table", "category": "restaurant", "count": 2}
        self.p = [mock.patch.object(GW, "_upcoming", side_effect=lambda a, **kw: [self.row]), mock.patch.dict(os.environ, {"SASHA_NO_REPLY_CALL": "1"})]
        for x in self.p:
            x.start()
            self.addCleanup(x.stop)
        self.dt = datetime

    def test_no_reply_in_24_hours_and_open_offered_once_and_the_yes_prepares_the_call(self):
        from booking_signer import proactive as PR
        from datetime import datetime, timezone
        self.now = datetime(2026, 10, 3, 18, 10, tzinfo=timezone.utc)                  # 20:10 Madrid: just opened
        GW.NOW = lambda: self.now
        TG.run(GW.STORE.put_state(GW.wa_key(TG.GUEST), {"history": [], "pending": None, "last_inbound_at": self.now, "link_tries": []}))
        done = TG.run(PR.no_reply_offers(self.now))
        self.assertEqual([d["outcome"] for d in done], ["sent"])
        body, buttons = GW.SENDER.contents[-1]
        self.assertTrue(body.startswith("No reply yet from Botavara Chamberí to my email about Saturday 3 October at 21:30. Shall I call them?"))
        self.assertEqual(TG.run(PR.no_reply_offers(self.now)), [])                     # once
        self.say("Yes, prepare the call", payload=buttons[0][1])
        self.assertIn("/api/booking/calls", self.api_paths())                         # the call's own read-back follows
        self.assertNotIn("/place", " ".join(self.api_paths()))                        # nothing dialled

    def test_not_while_they_are_closed_nor_before_24_hours(self):
        from booking_signer import proactive as PR
        from datetime import datetime, timezone
        self.now = datetime(2026, 10, 3, 17, 0, tzinfo=timezone.utc)                  # 19:00 Madrid: closed
        TG.run(GW.STORE.put_state(GW.wa_key(TG.GUEST), {"history": [], "pending": None, "last_inbound_at": self.now, "link_tries": []}))
        self.assertEqual(TG.run(PR.no_reply_offers(self.now)), [])
        self.now = datetime(2026, 10, 3, 18, 10, tzinfo=timezone.utc)                  # open, but the email went 2 h ago
        self.row["requested_at"] = "2026-10-03T16:10:00+00:00"
        self.assertEqual(TG.run(PR.no_reply_offers(self.now)), [])


class OneTapFiling(unittest.TestCase):
    def test_a_one_tap_booking_the_guest_pressed_is_confirmed_by_the_venues_email(self):
        """Rehearsal, 3 Oct: matched by venue and time, but 'guest_booked' wasn't offered — the confirmation was never filed."""
        from booking_signer import mailbox as MB
        off = MB.offer("confirmation", {"venue": "Sasha Test Venue", "at": "2026-10-07T21:00", "party": 2, "reference": "TV-30D27C"},
                       {"venue": "Sasha Test Venue", "status": "guest_booked"})
        self.assertEqual(off[0], "confirm")
        self.assertIn("(ref TV-30D27C). Mark it confirmed?", off[1])

    def test_the_platform_is_named(self):
        d = GW.decision_of({"rungs": {"link": {"fact_index": 1, "value": "CoverManager"}}, "country": "ES"})
        self.assertIn("They book through CoverManager.", d.reason)


class Urgent(OnWhatsApp):
    """Sasha 131 · within 24 h: the call AND the email, both read back, on ONE yes."""

    def test_urgent_call_and_email_on_one_yes(self):
        import os
        from unittest import mock
        self.rungs = [{"rung": "phone", "available": True, "fact_index": 2, "value": "+34 91 000"},
                      {"rung": "email", "available": True, "fact_index": 3, "value": "hola@botavara.es"}]
        with mock.patch.dict(os.environ, {"SASHA_URGENT_HOURS": "48"}):                 # Saturday 21:00 is 33 h away
            self.pick_first()
        said = "\n".join(self.bodies())
        self.assertIn("I'll call them and email them at once", GW.SENDER.contents[-1][0])   # Sasha 161 · one line
        self.assertNotIn("The call:", said)   # Sasha 161 · the scripts stay in the call and the email's own record
        body, buttons = GW.SENDER.contents[-1]
        self.assertTrue(body.startswith("There's no online booking for"), body)
        self.assertEqual(self.sent, [])
        self.say("Yes, book it", payload=buttons[0][1])
        self.assertEqual(len(self.sent), 1)                                            # the email, with its OWN read-back's hash
        self.assertEqual(self.sent[0]["read_back_sha256"], "e" * 64)
        self.assertTrue(any(p.endswith("/place") for p in self.api_paths()))            # and the call


class TapExpired(TG.Base):
    """Sasha 131 · a one-tap page not pressed within the window → ONE question: email them instead."""

    def setUp(self):
        super().setUp()
        import os
        from datetime import date, datetime, time, timezone
        from unittest import mock
        from booking_signer import ladder_routes as LR, ladder_store as LS, proactive as PR
        self.link()
        self.addCleanup(setattr, LR, "LADDER_STORE", LR.LADDER_STORE)
        self.addCleanup(setattr, PR, "STORE", PR.STORE)
        LR.LADDER_STORE, PR.STORE = LS.MemoryLadderStore(), PR.MemoryProactiveStore()
        TG.run(LR.LADDER_STORE.put_read({"read_id": "r-5", "account_id": TG.ACCOUNT, "created_at": TG.NOW,
                                         "read": {"name": "Akiro", "country": "ES", "facts": [
                                             {"kind": "phone", "value": "+34910000000"}, {"kind": "email", "value": "hola@akiro.es"}]}}))
        self.when = date(2026, 10, 6)
        TG.run(LR.LADDER_STORE.put_link({"link_id": "l-77", "account_id": TG.ACCOUNT, "read_id": "r-5", "platform": "CoverManager",
                                         "url": "https://www.covermanager.com/x", "slot_filled": False, "read_back_lines": [], "read_back_sha256": "0" * 64,
                                         "created_at": datetime(2026, 10, 3, 10, 0, tzinfo=timezone.utc), "venue_name": "Akiro",
                                         "local_date": self.when, "local_time": time(21, 0), "local_timezone": "Europe/Madrid", "party_size": 2}))
        p = mock.patch.dict(os.environ, {"SASHA_TAP_ESCALATION": "1"})
        p.start()
        self.addCleanup(p.stop)

    def test_after_the_window_the_email_is_offered_once(self):
        from booking_signer import proactive as PR
        from datetime import datetime, timezone
        self.now = datetime(2026, 10, 3, 10, 20, tzinfo=timezone.utc)                  # 20 min: inside the 30-minute window
        TG.run(GW.STORE.put_state(GW.wa_key(TG.GUEST), {"history": [], "pending": None, "last_inbound_at": self.now, "link_tries": []}))
        self.assertEqual(TG.run(PR.tap_offers(self.now)), [])
        self.now = datetime(2026, 10, 3, 10, 40, tzinfo=timezone.utc)
        done = TG.run(PR.tap_offers(self.now))
        self.assertEqual([d["outcome"] for d in done], ["sent"])
        body, buttons = GW.SENDER.contents[-1]
        self.assertEqual(body, "Not booked on Akiro's page yet for Tuesday 6 October at 21:00. Shall I email them instead? "
                               "I'll show you exactly what I'll send first.")
        self.assertEqual(buttons[0][0], "Yes, prepare the email")
        self.assertEqual(TG.run(PR.tap_offers(self.now)), [])                           # once a day

    def test_off_without_the_flag(self):
        import os
        from unittest import mock
        from booking_signer import proactive as PR
        from datetime import datetime, timezone
        with mock.patch.dict(os.environ, {"SASHA_TAP_ESCALATION": ""}):
            self.assertEqual(TG.run(PR.tap_offers(datetime(2026, 10, 3, 12, 0, tzinfo=timezone.utc))), [])
