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
        async def held(c):
            return 200, {}
        old = PS.latest
        PS.latest, TB.SEARCH, TB.ORDERABLE = lat, search, held
        try:
            b = asyncio.run(TB.bundle("11111111-1111-4111-8111-111111111111", "Madrid"))
        finally:
            PS.latest, TB.SEARCH, TB.ORDERABLE = old, None, None
        self.assertIn("TEST", b["lines"][0])
        self.assertEqual(b["eur"], 5 * 120 + 1000)
        self.assertIn("Wed 11 Nov", b["lines"][4])     # the flight there leaves the day before day 1
        self.assertIn("ONE tap to pay", b["lines"][-2])


class OnlyFaresTheAirlineWillBook(unittest.TestCase):
    def test_a_gone_fare_is_skipped(self):
        async def check(c):
            return (404 if c["id"] == "gone" else 200), {}
        TB.ORDERABLE = check
        try:
            got = asyncio.run(TB._orderable([{"id": "gone"}, {"id": "held"}]))
        finally:
            TB.ORDERABLE = None
        self.assertEqual(got["id"], "held")


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
        self.assertEqual(GW._picked(pend, "Please book the first one.", ""), 0)        # Sasha 173 live
        self.assertEqual(GW._picked(pend, "ok let's go with the second one please", ""), 1)
        self.assertEqual(GW._picked(pend, "book Mango Rooms please", ""), 1)
        self.assertIsNone(GW._picked(pend, "book the first restaurant you find in Hanoi for tomorrow at nine", ""))
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


class StartOver(unittest.TestCase):
    """Sasha 170 · "reset" in RelocateMe got its checklist question again; "start over" restarts any of the four."""

    def test_the_words(self):
        from products import whatsapp as PW
        for m, w in (("start over", ""), ("Start over relocate", "relocation"), ("restart campus", "campus"), ("reset CampusMe", "campus"),
                     ("empezar de nuevo españa", "health"), ("start over with Sasha", "sasha"), ("reset", ""), ("volver a empezar", "")):
            self.assertEqual(PW.start_over(m), w, m)
        for m in ("reset the demo", "start over the itinerary for Hoi An tomorrow please", "restart my phone"):
            self.assertIsNone(PW.start_over(m), m)

    def test_in_a_product_it_restarts_that_product(self):
        from products import whatsapp as PW
        dropped = []

        class Store:
            async def drop_conversation(self, key, prod):
                dropped.append(prod)

            async def put_conversation(self, *a):
                return None
        from products import store as ST
        old_store, old_resume, old_turn = ST.STORE, PW._resume, PW._module
        ST.STORE = Store()

        saved = {"kind": "product", "product": "relocation", "step": "pack", "touched": NOW.isoformat()}

        async def resume(ch, prod):   # the shared row, until it is dropped
            return dict(saved) if prod == "relocation" and prod not in dropped else None
        PW._resume = resume
        seen = []

        class Mod:
            @staticmethod
            async def turn(ctx, rest, payload, entering=False):
                seen.append((rest, entering))
                ctx["out"].text("Welcome to RelocateMe")
                ctx["st"]["pending"]["step"] = "ask"
                return True

            @staticmethod
            def claims(*a):
                return False
        PW._module = lambda prod: Mod
        st = {"pending": {"kind": "product", "product": "relocation", "step": "pack", "touched": NOW.isoformat()}, "history": []}

        async def put(ch, prod, pend):
            return None
        old_put = PW._store_put
        PW._store_put = put
        try:
            out = GW.Out()
            asyncio.run(PW.product_turn({"account_id": "a", "wa_id_sha256": "k"}, "f", {"Body": "reset"}, st, out, NOW))
            # CR 39 · asked once first: "Start RelocateMe from the beginning? Your old file is kept, not deleted."
            self.assertEqual(dropped, [])
            q = next(i for i in out.items if i[0] == "ask")
            self.assertIn("Start RelocateMe from the beginning? Your old file is kept, not deleted.", q[1])
            out = GW.Out()
            asyncio.run(PW.product_turn({"account_id": "a", "wa_id_sha256": "k"}, "f", {"Body": "", "ButtonPayload": "so:yes:relocation"},
                                        st, out, NOW))
        finally:
            ST.STORE, PW._resume, PW._module, PW._store_put = old_store, old_resume, old_turn, old_put
        self.assertEqual(dropped, ["relocation"])
        self.assertTrue(seen and seen[0][1])   # entered afresh, not answered as a reply to "the numbers, please"

    def test_reset_the_demo_leaves_a_product(self):
        self.assertTrue(WB.RESET.match("reset the demo"))


class SpokenDates(unittest.TestCase):
    """Sasha 171 live: "on the sixteenth at eight at night" (Deepgram's words) lost the date, and 'outside your trip?' asked
    about today — 'Add to my trip' then added 6 October to the plan."""

    def test_words_become_the_trips_day(self):
        async def lat(a, hint=None):
            return {"trip_id": "t", "start": date(2026, 11, 12), "end": date(2026, 11, 19), "plan": {"days": DAYS}}
        f, parts = {"open_at": "2026-10-06T20:00"}, {}
        old = PS.latest
        PS.latest = lat
        try:
            asyncio.run(WB._ordinal_day({"account": "a", "now": NOW}, f, parts,
                                        "Please book a romantic dinner in Hoi An on the sixteenth at eight at night for two."))
        finally:
            PS.latest = old
        self.assertEqual(f["open_at"], "2026-11-16T20:00")

    def test_no_date_said_no_trip_question(self):
        self.assertIsNone(WB._DATE_SAID.search(WB.ordinals_as_digits("a romantic dinner in Hoi An at eight at night")))
        self.assertTrue(WB._DATE_SAID.search(WB.ordinals_as_digits("dinner on the sixteenth")))
        self.assertEqual(WB.ordinals_as_digits("the first one"), "the first one")   # a pick stays a pick


class StandInQuestion(unittest.TestCase):
    """Sasha 173 · the demo line's "spa/restaurant" overwrote the question's kind: "Yes, cancel" and a yes that booked nothing."""

    def test_the_yes_stays_a_booking_yes(self):
        c = {"out": GW.Out(), "st": {}, "now": NOW}
        asyncio.run(GW._ask_yes(c, "handover", "f1", {"sha256": "a" * 64, "lines": []}, "Shall I?", "Hanoi Spa - Massage (TEST stand-in)"))
        self.assertEqual(c["st"]["pending"]["kind"], "confirm")
        self.assertEqual(c["out"].items[-1][2][0][0], "Yes, book it")
        self.assertIn("the spa isn't contacted", c["out"].items[-1][1])
