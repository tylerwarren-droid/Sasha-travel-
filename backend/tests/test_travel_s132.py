"""Sasha 132 · the travel demo: flights in Duffel TEST mode (a live token refused), the one-touch test payment before the
test order, a hotel requested from the hotel itself, and the itinerary answered from the guest's own bookings.

    cd backend && python -m unittest tests.test_travel_s132 -v
"""
from __future__ import annotations

import asyncio
import os
import unittest
from datetime import date, datetime, time, timezone
from unittest import mock

from booking_signer import emailing as E, guest_whatsapp as GW, itinerary_q as IQ, test_deposit as TD, travel as TR
from tests import test_guest_whatsapp_s75 as TG

OFFER = {"id": "off_1", "owner": {"name": "Duffel Airways"}, "total_amount": "391.52", "total_currency": "EUR", "expires_at": "2026-11-01T00:00:00Z",
         "passengers": [{"id": "pas_1"}],
         "slices": [{"duration": "PT21H45M", "segments": [
             {"origin": {"iata_code": "MAD", "city_name": "Madrid", "name": "Barajas", "time_zone": "Europe/Madrid"}, "destination": {"iata_code": "DOH", "name": "Doha"},
              "departing_at": "2026-11-12T08:30:00", "arriving_at": "2026-11-12T16:30:00", "marketing_carrier": {"iata_code": "ZZ"}, "marketing_carrier_flight_number": "123"},
             {"origin": {"iata_code": "DOH", "name": "Doha"}, "destination": {"iata_code": "HAN", "city_name": "Hanoi", "name": "Noi Bai"},
              "departing_at": "2026-11-12T19:00:00", "arriving_at": "2026-11-13T07:15:00", "marketing_carrier": {"iata_code": "ZZ"}, "marketing_carrier_flight_number": "456"}]}]}


class FakeDuffel:
    def __init__(self, price="391.52"):
        self.calls, self.price = [], price

    async def __call__(self, method, path, body=None, params=None):
        self.calls.append((method, path, body))
        if path == "/places/suggestions":
            q = (params or {}).get("query", "")
            code = {"Madrid": "MAD", "Hanoi": "HAN"}.get(q, q.upper()[:3])
            return 200, {"data": [{"type": "city", "iata_city_code": code, "city_name": q, "time_zone": "Europe/Madrid"}]}
        if path.startswith("/air/offer_requests"):
            return 201, {"data": {"live_mode": False, "offers": [OFFER]}}
        if path == "/air/offers/off_1":
            return 200, {"data": {**OFFER, "total_amount": self.price}}
        if path == "/air/orders":
            return 201, {"data": {"id": "ord_1", "booking_reference": "RZPNX8", "live_mode": False}}
        return 404, {"errors": [{"message": "no fake"}]}


class Duffel(unittest.TestCase):
    def setUp(self):
        self.saved = TR.HTTP
        TR.HTTP = self.fake = FakeDuffel()

    def tearDown(self):
        TR.HTTP = self.saved

    def test_a_live_token_is_refused(self):
        for t in ("", "duffel_live_abc"):
            with mock.patch.dict(os.environ, {"DUFFEL_ACCESS_TOKEN": t}):
                self.assertIn("TEST token", asyncio.run(TR.search("Madrid", "Hanoi", "2026-11-12"))["why"])
        self.assertEqual(self.fake.calls, [])

    def test_cards_say_test_and_the_read_back_says_the_placeholders(self):
        with mock.patch.dict(os.environ, {"DUFFEL_ACCESS_TOKEN": "duffel_test_x"}):
            got = asyncio.run(TR.search("Madrid", "Hanoi", "2026-11-12", 2))
        c = got["cards"][0]
        self.assertEqual(TR.card_line(c), "Duffel Airways ZZ 123 + ZZ 456 · Thu 12 Nov 08:30 MAD → 07:15+1 HAN · 1 stop · 21h 45m · EUR 391.52 (TEST)")
        lines = TR.read_back(c, "Tyler Warren", "guest@example.com")
        self.assertIn("⚠ TEST booking — Duffel test mode: no real ticket, nothing charged.", lines)
        self.assertTrue(any("placeholders (1 Jan 1980, Mr, M) — test only" in ln for ln in lines))

    def test_the_order_is_refused_when_the_price_moved(self):
        with mock.patch.dict(os.environ, {"DUFFEL_ACCESS_TOKEN": "duffel_test_x"}):
            c = TR.card_of(OFFER)
            TR.HTTP = FakeDuffel(price="420.00")
            self.assertIn("price changed", asyncio.run(TR.order(c, "Tyler Warren", "g@example.com", None))["why"])
            TR.HTTP = FakeDuffel()
            o = asyncio.run(TR.order(c, "Tyler Warren", "g@example.com", None))
        self.assertEqual(o["booking_reference"], "RZPNX8")


class FlightsOnWhatsApp(TG.Base):
    def setUp(self):
        super().setUp()
        self.link()
        self.saved = (TR.HTTP, TD.HTTP, TR.RECORD)
        TR.HTTP = FakeDuffel()
        self.sessions = {"cs_1": {"status": "open"}}

        async def stripe(method, path, data=None):
            if path == "/checkout/sessions" and method == "POST":
                self.paid_for = data
                return 200, {"id": "cs_1", "url": "https://checkout.stripe.com/c/pay/cs_test_1", "livemode": False}
            if path == "/checkout/sessions/cs_1":
                return 200, {**self.sessions["cs_1"], "livemode": False}
            return 404, {}
        TD.HTTP = stripe
        self.recorded = []

        async def record(account, c, ref):
            self.recorded.append((c["flights"], ref))
        TR.RECORD = record
        p = mock.patch.dict(os.environ, {"DUFFEL_ACCESS_TOKEN": "duffel_test_x", "STRIPE_TEST_SECRET_KEY": "sk_test_x"})
        p.start()
        self.addCleanup(p.stop)

    def tearDown(self):
        TR.HTTP, TD.HTTP, TR.RECORD = self.saved
        super().tearDown()

    def test_cards_yes_one_touch_paid_then_the_test_order(self):
        self.say("flights from Madrid to Hanoi on 12 November for 2")
        said = "\n".join(self.bodies())
        self.assertIn("from Duffel in TEST mode", said)
        self.assertIn("1. Duffel Airways ZZ 123 + ZZ 456", said)
        _, picks = GW.SENDER.contents[-1]
        self.say("1", payload=picks[0][1])
        body, yes = GW.SENDER.contents[-1]
        self.assertTrue(body.startswith("Book it? Duffel Airways ZZ 123 + ZZ 456, EUR 391.52 — TEST booking."))
        self.say("Yes, book it", payload=yes[0][1])
        self.assertIn("https://checkout.stripe.com/c/pay/cs_test_1", self.bodies()[-1])
        self.assertEqual(self.paid_for["line_items[0][price_data][unit_amount]"], 39152)
        self.assertEqual(self.recorded, [])                                             # nothing booked before it's paid
        self.sessions["cs_1"] = {"status": "complete", "payment_status": "paid", "amount_total": 39152, "currency": "eur", "payment_intent": "pi_1"}
        GW.WATCH_PAY = (0, 2)
        ch = TG.run(GW.STORE.channel_for(GW.wa_key(TG.GUEST)))
        TG.run(GW.watch_flight_payment(ch, TG.SANDBOX, TG.ACCOUNT, TR.card_of(OFFER), "cs_1", "Tyler Warren", "g@example.com", None))
        self.assertEqual(self.recorded, [("ZZ 123 + ZZ 456", "RZPNX8")])
        self.assertIn("✅ Booked (TEST)", self.bodies()[-1])
        self.assertIn("Reference RZPNX8", self.bodies()[-1])

    def test_without_a_stripe_key_nothing_is_booked(self):
        with mock.patch.dict(os.environ, {"STRIPE_TEST_SECRET_KEY": ""}):
            self.say("flights from Madrid to Hanoi on 12 November")
            _, picks = GW.SENDER.contents[-1]
            self.say("1", payload=picks[0][1])
            _, yes = GW.SENDER.contents[-1]
            self.say("yes", payload=yes[0][1])
        self.assertIn("I can't take the test payment yet", self.bodies()[-1])
        self.assertIn("Nothing was booked", self.bodies()[-1])


class Hotels(TG.Base):
    def test_a_hotel_is_requested_from_the_hotel_and_says_so(self):
        self.link()
        self.say("a hotel in Hoi An from 14 to 16 November for 2")
        said = "\n".join(self.bodies())
        self.assertIn("Hotels for 2 nights from Saturday 14 November, 2 people. For the one you pick: a TEST booking (no hotel contacted), "
                      "or a real request to the hotel.", said)
        find = next(c for c in GW.api.calls if c[2] == "/api/booking/venues/find")[3]
        self.assertEqual(find["what"], "hotel")

    def test_the_room_email(self):
        p = E.EmailParticulars(on=date(2026, 11, 14), at=time(15, 0), party=2, name="Tyler Warren", guest_email="g@example.com", nights=2)
        m = E.compose("vi", "Anantara", "res@x.com", p, "id1")
        self.assertEqual(m["subject"], "Room request — 2, 2026-11-14 for 2 nights")
        self.assertIn("(check-in 2026-11-14, check-out 2026-11-16)", m["text"])
        self.assertIn("We can't agree to a price, a deposit or different dates by email", m["text"])


class Itinerary(unittest.TestCase):
    ROWS = [{"date": "2026-11-12", "time": "08:30", "type": "flight", "venue": "Flight ZZ 123 + ZZ 456 Madrid → Hanoi (TEST booking)",
             "location": "MAD → HAN", "timezone": "Europe/Madrid", "duration_minutes": 1305, "status": "confirmed"},
            {"date": "2026-11-14", "time": "19:00", "type": "restaurant", "venue": "Mate", "party": 2, "timezone": "Asia/Ho_Chi_Minh", "status": "requested"}]

    def test_where_am_i(self):
        self.assertEqual(IQ.where_on(self.ROWS, date(2026, 11, 14)),
                         ["Saturday 14 November:", "• 19:00 Mate, 2 people",
                          "Your last flight before then goes to Hanoi — that's where your bookings put you."])
        self.assertIn("Your bookings don't say where you'll be", IQ.where_on(self.ROWS, date(2026, 11, 1))[-1])

    def test_the_5th_said_on_the_20th_is_next_month(self):
        self.assertEqual(IQ.day_of("where am I on the 5th?", datetime(2026, 10, 20, 9, tzinfo=timezone.utc)), date(2026, 11, 5))

    def test_time_to_drive_uses_the_routes_api_and_says_so(self):
        from booking_signer import proactive as PR

        async def travel(o, d, depart, mode):
            return 75 * 60

        class Store:
            async def default_place(self, a):
                return {"address": "Calle de Velázquez 8, Madrid"}
        with mock.patch.object(PR, "travel", travel), mock.patch.object(PR, "STORE", Store()):
            got = asyncio.run(IQ.time_for("a", "do I have time to drive to Toledo between 13:00 and 18:00 on 5 November?", [],
                                          datetime(2026, 10, 3, tzinfo=timezone.utc)))
        self.assertEqual(got, ["Yes: 1h 15m each way by car (Routes API, leaving 13:00), so 150 min there after the round trip."])

    def test_the_web_turn_answers_only_its_question(self):
        self.assertIsNone(asyncio.run(IQ.web_turn("dinner for 2 in Chamberí", "a", [])))
        t = asyncio.run(IQ.web_turn("where am I on the 5th?", None, []))
        self.assertEqual(t["response"], "Sign in, and I'll answer from your own bookings.")


class Rehearsal2Fixes(unittest.TestCase):
    """Rehearsal 1 (3 Oct): 'fly from Madrid to Lisbon' lost Lisbon; 'drive from X' was ignored."""

    def test_from_and_to_are_both_read(self):
        t = "do I have time to fly from Madrid to Lisbon between 9 and 14 on 12 November?"
        self.assertEqual((IQ._TO.search(t)["x"], IQ._FROM.search(t)["x"]), ("Lisbon", "Madrid"))
        self.assertEqual(IQ._TO.search("do I have time to drive to Toledo between 13:00 and 18:00 on the 5th?")["x"], "Toledo")

    def test_drive_from_said_is_the_origin(self):
        from booking_signer import proactive as PR
        seen = []

        async def travel(o, d, depart, mode):
            seen.append(o)
            return 60 * 60
        with mock.patch.object(PR, "travel", travel), mock.patch.object(PR, "STORE", None):
            asyncio.run(IQ.time_for("a", "do I have time to drive from Madrid to Toledo between 13:00 and 18:00 on 5 November?", [],
                                    datetime(2026, 10, 3, tzinfo=timezone.utc)))
        self.assertEqual(seen, ["Madrid, Spain"])                                      # never a bare name Google reads as Ohio


class FindRoute(unittest.TestCase):
    """The /venues/find ROUTE itself (a missing import once hid here): our test restaurant is never a hotel card."""

    def test_rehearsal_card_for_dinner_not_for_a_hotel(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from booking_signer import ladder_routes as LR, venue_read as V
        founder = "11111111-1111-4111-8111-111111111111"

        async def find(http, **kw):
            return {"candidates": [{"place_id": "a", "name": "A"}], "ranking": {"orders": {"rated": ["a"]}, "picks": {"rated": "a"}}}
        app = FastAPI()
        app.include_router(LR.router, prefix="/api/booking")
        with mock.patch.object(V, "find_venues", find), mock.patch.object(LR, "account_for", lambda r: founder), \
                mock.patch.dict(os.environ, {"SASHA_REHEARSAL": "1", "FOUNDER_ACCOUNT_ID": ""}):
            c = TestClient(app)
            dinner = c.post("/api/booking/venues/find", json={"what": "dinner", "where": "Madrid"}).json()
            hotel = c.post("/api/booking/venues/find", json={"what": "hotel", "where": "Hoi An"}).json()
        self.assertIn("sasha-test-venue", [x["place_id"] for x in dinner["candidates"]])
        self.assertNotIn("sasha-test-venue", [x["place_id"] for x in hotel["candidates"]])


class Rehearsal2(TG.Base):
    """Rehearsal 2 (3 Oct): 'do I have time to fly…' was taken as a flight search; driving sent a departure time that Routes
    refuses unless routing is traffic-aware."""

    def test_a_time_question_is_a_question(self):
        self.link()
        called = []

        async def answer(account, text, now):
            called.append(text)
            return ["answered"]
        with mock.patch.object(IQ, "answer", answer):
            self.say("do I have time to fly from Madrid to Lisbon between 9 and 14 on 12 November?")
        self.assertEqual(self.bodies()[-1], "answered")

    def test_driving_asks_routes_for_traffic_aware_routing(self):
        from booking_signer import proactive as PR
        seen = []

        async def http(url, headers, body):
            seen.append(body)
            return 200, {"routes": [{"duration": "3600s"}]}
        with mock.patch.object(PR, "ROUTES_HTTP", http), mock.patch.dict(os.environ, {"GOOGLE_PLACES_API_KEY": "k"}):
            self.assertEqual(asyncio.run(PR.travel("Madrid", "Toledo", datetime(2026, 11, 5, 12, tzinfo=timezone.utc), "DRIVE")), 3600)
        self.assertEqual(seen[0]["routingPreference"], "TRAFFIC_AWARE")


class Qualified(unittest.TestCase):
    def test_a_bare_name_gets_its_country(self):
        self.assertEqual(IQ.qualified("Toledo", "ES"), "Toledo, Spain")
        self.assertEqual(IQ.qualified("Madrid"), "Madrid, Spain")
        self.assertEqual(IQ.qualified("Chamberí"), "Chamberí, Madrid, Spain")
        self.assertEqual(IQ.qualified("Calle de Velázquez 8, Madrid"), "Calle de Velázquez 8, Madrid")


class ProductHandOff(TG.Base):
    """CR 13 · a product hands Sasha a sentence: her flow answers it as if typed; a button is never rewritten."""

    def test_a_handed_sentence_runs_sasha_s_flow(self):
        self.link()
        from products import whatsapp as PW
        seen = []

        async def product_turn(ch, frm, p, st, out, now, early=None):
            if p.get("Body") == "book my flights":
                p["KanoeSaid"], p["Body"] = p["Body"], "flights from London to Madrid on 1 March 2027 for 1"
            return False

        async def flights(ctx, body):
            seen.append(body)
        with mock.patch.object(PW, "product_turn", product_turn), mock.patch.object(GW, "_flights", flights):
            self.say("book my flights")
        self.assertEqual(seen, ["flights from London to Madrid on 1 March 2027 for 1"])
