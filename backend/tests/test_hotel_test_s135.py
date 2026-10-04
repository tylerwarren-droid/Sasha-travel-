"""Sasha 135 · hotel "Reserve" as a TEST booking (no hotel contacted), next to the real "request from the hotel".

    cd backend && python -m unittest tests.test_hotel_test_s135 -v
"""
from __future__ import annotations

import os
import unittest
from datetime import datetime, timezone
from unittest import mock

from booking_signer import calendar_sync as CS, guest_whatsapp as GW, hotel_test as HT, proactive as PR, test_deposit as TD
from tests import test_guest_whatsapp_s75 as TG


class Words(unittest.TestCase):
    def test_the_read_back_never_says_confirmed_and_says_test_first(self):
        q = HT.quote("Tohe Riverside Lodge", "Hoi An", "2026-11-14", 2, 2)
        self.assertTrue(q["lines"][0].startswith("⚠ Test booking: no hotel contacted"))
        self.assertIn("a placeholder, not the hotel's rate", "\n".join(q["lines"]))
        self.assertNotIn("confirm", "\n".join(q["lines"]).lower())
        self.assertEqual(q["eur"], 240.0)

    def test_the_calendar_and_the_brief_say_test(self):
        body = CS.event_body({"date_time": datetime(2026, 11, 14, 15, tzinfo=timezone.utc), "provider_name": f"Tohe {HT.MARK}",
                              "booking_reference": "TEST-ABC123", "duration_minutes": 2640, "local_timezone": "Asia/Ho_Chi_Minh"}, "event")
        self.assertTrue(body["description"].startswith("TEST booking — no hotel or provider was contacted"))
        brief = PR.render("morning_brief", {}, {"items": [{"time": "15:00", "venue": f"Tohe {HT.MARK}", "status": "confirmed",
                                                          "booking_reference": "TEST-ABC123"}]})
        self.assertIn("(TEST booking)", brief)
        self.assertNotIn("(confirmed)", brief)


class OnWhatsApp(TG.Base):
    def setUp(self):
        super().setUp()
        self.link()
        self.saved = (TD.HTTP, HT.RECORD)
        self.session = {"status": "open"}

        async def stripe(method, path, data=None):
            if path == "/checkout/sessions" and method == "POST":
                self.paid_for = data
                return 200, {"id": "cs_h", "url": "https://checkout.stripe.com/c/pay/cs_test_h", "livemode": False}
            if path == "/checkout/sessions/cs_h":
                return 200, {**self.session, "livemode": False}
            return 404, {}
        TD.HTTP = stripe
        self.recorded = []

        async def record(account, hotel, city, tz, checkin, nights, party, ref):
            self.recorded.append((hotel, city, tz, checkin, nights, party, ref))
        HT.RECORD = record
        p = mock.patch.dict(os.environ, {"STRIPE_TEST_SECRET_KEY": "sk_test_x"})
        p.start()
        self.addCleanup(p.stop)

    def tearDown(self):
        TD.HTTP, HT.RECORD = self.saved
        super().tearDown()

    def pick_hotel(self):
        self.say("a hotel in Hoi An, Vietnam from 14 to 16 November for 2")
        _, cards = GW.SENDER.contents[-1]
        self.say("x", payload=cards[0][1])
        return GW.SENDER.contents[-1]

    def test_test_booking_paid_then_a_test_reference(self):
        body, choice = self.pick_hotel()
        self.assertIn("make a TEST booking", body)
        self.assertEqual([t for t, _ in choice], ["Test booking", "Book with hotel"])
        self.say("Test booking", payload=choice[0][1])
        said = "\n".join(self.bodies())
        self.assertIn("• ⚠ Test booking: no hotel contacted", said)
        body, yes = GW.SENDER.contents[-1]
        self.assertTrue(body.startswith("Make the TEST booking at"))
        self.say("Yes", payload=yes[0][1])
        self.assertIn("https://checkout.stripe.com/c/pay/cs_test_h", self.bodies()[-1])
        self.assertEqual(self.paid_for["line_items[0][price_data][unit_amount]"], 24000)
        self.assertEqual(self.recorded, [])                                   # nothing recorded before Stripe says paid
        self.session = {"status": "complete", "payment_status": "paid", "amount_total": 24000, "currency": "eur", "payment_intent": "pi_h"}
        GW.WATCH_PAY = (0, 2)
        ch = TG.run(GW.STORE.channel_for(GW.wa_key(TG.GUEST)))
        p = {"hotel": "A Very Long Restaurant Name In Madrid", "city": "Hoi An", "country": "VN", "checkin": "2026-11-14", "nights": 2, "party": 2}
        TG.run(GW.watch_hotel_payment(ch, TG.SANDBOX, TG.ACCOUNT, p, "cs_h"))
        self.assertEqual(self.recorded[0][2], "Asia/Ho_Chi_Minh")
        self.assertRegex(self.recorded[0][6], r"^TEST-[0-9A-F]{6}$")
        last = self.bodies()[-1]
        self.assertIn("Test booking: no hotel contacted", last)
        self.assertNotIn("confirmed", last.lower())

    def test_request_from_the_hotel_is_the_real_path(self):
        _, choice = self.pick_hotel()
        n = len([c for c in GW.api.calls if c[2] == "/api/booking/venues/read"])
        self.say("Request from hotel", payload=choice[1][1])
        self.assertEqual(len([c for c in GW.api.calls if c[2] == "/api/booking/venues/read"]), n + 1)   # read, as any real booking


class EmailOnlyVenue(TG.Base):
    """Rehearsal (3 Oct): 'Request from hotel' at a hotel that publishes only an email stopped dead — a guard from before the
    email route (Sasha 130) skipped it."""

    def test_an_email_only_hotel_gets_the_email_route(self):
        self.link()
        api = GW.api

        async def fake(account, method, path, body=None, timeout=90.0):
            if path == "/api/booking/venues/read":
                return 200, {"read_id": "r-h", "venue": "ARTIEM", "country": "ES", "listing": {"name": "ARTIEM Madrid"}, "say": "x", "facts": [],
                             "rungs": [{"rung": "email", "available": True, "fact_index": 1, "value": "res@artiem.es"}]}
            if path == "/api/booking/emails":
                fake.email = body
                return 200, {"email_id": "e-h", "read_back": {"lines": ["I'll email ARTIEM Madrid"], "sha256": "e" * 64}}
            return await api(account, method, path, body, timeout)
        fake.calls, fake.email = api.calls, None
        GW.api = fake
        from booking_signer import ladder_routes as LR, ladder_store as LS
        saved = LR.LADDER_STORE
        LR.LADDER_STORE = LS.MemoryLadderStore()
        LR.LADDER_STORE.account_emails = {TG.ACCOUNT: "guest@example.com"}
        try:
            self.say("a hotel in Madrid from 20 to 22 October for 2")
            _, cards = GW.SENDER.contents[-1]
            self.say("x", payload=cards[0][1])
            _, choice = GW.SENDER.contents[-1]
            self.say("Request from hotel", payload=choice[1][1])
        finally:
            GW.api, LR.LADDER_STORE = api, saved
        self.assertEqual(fake.email["nights"], 2)                               # the ROOM request, for its nights
        self.assertIn("I'll email them", "\n".join(self.bodies()))
        self.assertEqual(GW.SENDER.contents[-1][0], "Email ARTIEM Madrid to ask for a room for 2, Tuesday 20 October for 2 nights? "
                                                    "It's a request — nothing is booked until they reply.")
