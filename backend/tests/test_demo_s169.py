"""Sasha 169 · the Vietnam demo: the whole trip booked in one (TEST), pick by voice, the stand-in, "the 16th", spoken times,
flights on the days around the trip, the voice page. Offline.

    cd backend && python -m unittest tests.test_demo_s169 -v
"""
import asyncio
import unittest
from datetime import date, datetime
from zoneinfo import ZoneInfo

from booking_signer import guest_whatsapp as GW, plan_store as PS, trip_book as TB, voice_turn as VT, wa_brain as WB

NOW = datetime(2026, 10, 6, 12, 0, tzinfo=ZoneInfo("Europe/Madrid"))
DAYS = [{"day": 1, "city": "Hanoi", "hotel": {"name": "Metropole"}}, {"day": 2, "city": "Hanoi", "hotel": {"name": "Metropole"}},
        {"day": 3, "city": "Ha Long Bay", "hotel": {"name": "Cruise"}}, {"day": 4, "city": "Hoi An", "hotel": "Nam Hai"},
        {"day": 5, "city": "Hoi An", "hotel": "Nam Hai"}]


class BookTheTrip(unittest.TestCase):
    def test_the_words(self):
        for m, o in (("book it", ""), ("Book the whole trip from Madrid", "Madrid"), ("ok, book it all please", ""),
                     ("book the hotels and flights, flying from London", "London")):
            self.assertEqual(TB.asked(m), o, m)
        for m in ("book a table at Botín", "book dinner in Hoi An", "book it at 8"):
            self.assertIsNone(TB.asked(m), m)

    def test_consecutive_nights_are_one_stay(self):
        s = TB.stays(DAYS, date(2026, 11, 12))
        self.assertEqual([(x["hotel"], x["checkin"], x["nights"]) for x in s],
                         [("Metropole", "2026-11-12", 2), ("Cruise", "2026-11-14", 1), ("Nam Hai", "2026-11-15", 2)])

    def test_the_bundle_reads_back_test_and_one_total(self):
        async def lat(a, hint=None):
            return {"trip_id": "t", "title": "Vietnam", "start": date(2026, 11, 12), "end": date(2026, 11, 16), "plan": {"days": DAYS}}

        async def search(o, d, day, adults=1, limit=3):
            return {"cards": [{"id": f"off_{o}", "owner": "Duffel Airways", "flights": "ZZ 1", "from": o[:3].upper(), "to": d[:3].upper(),
                               "from_city": o, "to_city": d, "departs": f"{day}T10:00:00", "arrives": f"{day}T22:00:00", "stops": 0,
                               "minutes": 720, "amount": "500.00", "currency": "EUR"}]}
        old = PS.latest
        PS.latest, TB.SEARCH = lat, search
        try:
            b = asyncio.run(TB.bundle("11111111-1111-4111-8111-111111111111", "Madrid"))
        finally:
            PS.latest, TB.SEARCH = old, None
        self.assertIn("TEST", b["lines"][0])
        self.assertEqual(b["eur"], 5 * 120 + 1000)
        self.assertIn("Wed 11 Nov", b["lines"][4])     # the flight there leaves the day before day 1
        self.assertIn("ONE tap to pay", b["lines"][-2])


class FlightsAroundTheTrip(unittest.TestCase):
    def test_on_day_one_and_the_last_day(self):
        p = {"trip_id": "t", "start": date(2026, 11, 12), "end": date(2026, 11, 16), "plan": {"days": [dict(d) for d in DAYS]}}
        m = PS.merge(p, [{"venue": "Flight ZZ 1 Madrid → Hanoi (TEST booking)", "date": "2026-11-11", "time": "07:44", "type": "flight",
                          "status": "confirmed"},
                         {"venue": "Flight ZZ 2 Hoi An → Madrid (TEST booking)", "date": "2026-11-17", "time": "02:10", "type": "flight",
                          "status": "confirmed"}])
        self.assertEqual(m["days"][0]["bookings"][0]["edge"], "leaves Wed 11 Nov")
        self.assertEqual(m["days"][-1]["bookings"][0]["edge"], "leaves Tue 17 Nov")
        self.assertIn("07:44 (leaves Wed 11 Nov) TEST · Flight", "\n".join(PS.text(m)))


class PickByVoice(unittest.TestCase):
    CARDS = [{"name": "Red Bean Hoi An Restaurant", "address": "23 Nguyễn Thái Học, Minh An, Hội An"},
             {"name": "Mango Rooms", "address": "111 Bạch Đằng, Minh An, Hội An"},
             {"name": "Sasha Test Venue"}]

    def test_number_name_or_what_its_like(self):
        pend = {"nonce": "n", "cards": self.CARDS}
        self.assertEqual(GW._picked(pend, "the second one", ""), 1)
        self.assertEqual(GW._picked(pend, "Mango Rooms please", ""), 1)
        self.assertEqual(GW._picked(pend, "the one by the river", ""), 1)
        self.assertIsNone(GW._picked(pend, "the one in the old town", ""))   # two match: asked again, never a guess
        self.assertIsNone(GW._picked(pend, "something nice", ""))


class SaidAloud(unittest.TestCase):
    def test_spoken_times(self):
        for m, t in (("10 in the morning", "10:00"), ("eight at night", "20:00"), ("3 in the afternoon for 2", "15:00"), ("9pm", "21:00")):
            self.assertEqual(WB.spoken_time(m), t, m)
        self.assertIsNone(WB.spoken_time("at 10"))

    def test_the_16th_is_the_trips_16th(self):
        async def lat(a, hint=None):
            return {"trip_id": "t", "start": date(2026, 11, 12), "end": date(2026, 11, 19), "plan": {"days": DAYS}}
        f, parts = {"open_at": "2026-10-06T20:00"}, {}
        old = PS.latest
        PS.latest = lat
        try:
            asyncio.run(WB._ordinal_day({"account": "a", "now": NOW}, f, parts, "a romantic dinner in Hoi An on the 16th at 8 at night"))
            f2, parts2 = {}, {}
            asyncio.run(WB._ordinal_day({"account": "a", "now": NOW}, f2, parts2, "a cooking class in Hoi An on the 17th"))
        finally:
            PS.latest = old
        self.assertEqual(f["open_at"], "2026-11-16T20:00")
        self.assertEqual(parts2["day"], "2026-11-17")

    def test_classes_and_shows_are_bookable(self):
        from booking_signer.chat_request import draft
        self.assertEqual(draft("a cooking class", NOW)["parts"]["what"]["category"], "experience")
        self.assertEqual(draft("the water puppet show", NOW)["parts"]["what"]["activity"], "seats for the show")


class StandIn(unittest.TestCase):
    def test_the_name_says_so_and_fits(self):
        from booking_signer import ladder_routes as LR
        n = LR.standin_name("Cooking Class in Hoi An by Cam Thanh Tours Plus and a very long name indeed")
        self.assertTrue(n.endswith("(TEST stand-in)"))
        self.assertLessEqual(len(n), 80)
        self.assertTrue(WB.is_test({"venue": n}))

    def test_only_the_founder_and_only_when_on(self):
        import os
        from booking_signer import ladder_routes as LR
        os.environ.pop("SASHA_DEMO_STANDIN", None)
        self.assertFalse(LR.standin("11111111-1111-4111-8111-111111111111"))
        os.environ["SASHA_DEMO_STANDIN"] = "1"
        try:
            self.assertTrue(LR.standin("11111111-1111-4111-8111-111111111111"))
            self.assertFalse(LR.standin("22222222-2222-4222-8222-222222222222"))
        finally:
            os.environ.pop("SASHA_DEMO_STANDIN", None)


class VoicePage(unittest.TestCase):
    def test_cards_are_said_and_shown(self):
        out = GW.Out().text("Here are the best-rated places.").media("Sasha's pick · Red Bean · ★ 5.0", "https://x/a.jpg") \
            .media("Mango Rooms · ★ 4.9", "https://x/b.jpg").ask("Which one?", [("Red Bean", "p0"), ("Mango Rooms", "p1")])
        words, photos = VT._spoken(out.items)
        self.assertIn("1. Red Bean", words)
        self.assertIn("Which one? (Red Bean or Mango Rooms)", words)
        self.assertEqual([p["url"] for p in photos], ["https://x/a.jpg", "https://x/b.jpg"])

    def test_not_a_booking_is_the_conductors(self):
        class Store:
            async def get_state(self, k):
                return {}
        old = GW.STORE
        GW.STORE = Store()
        try:
            self.assertIsNone(asyncio.run(VT.turn("11111111-1111-4111-8111-111111111111", "tell me about Hue", [])))
        finally:
            GW.STORE = old


if __name__ == "__main__":
    unittest.main()
