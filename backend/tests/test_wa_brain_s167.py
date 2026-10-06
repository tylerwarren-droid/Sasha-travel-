"""Sasha 167 · WhatsApp does everything the web does: no "open Sasha at …", a placeless request uses the trip, a pick lands on
its day, TEST bookings are labelled, "reset the demo". Offline.

    cd backend && python -m unittest tests.test_wa_brain_s167 -v
"""
import asyncio
import unittest
from datetime import date, datetime
from zoneinfo import ZoneInfo

from booking_signer import guest_whatsapp as GW, plan_store as PS, wa_brain as WB

NOW = datetime(2026, 10, 6, 12, 0, tzinfo=ZoneInfo("Europe/Madrid"))
PLAN = {"title": "7 Days in Vietnam", "days": [
    {"day": 1, "city": "Hanoi", "activities": [{"time": "Evening", "name": "Street food dinner"}]},
    {"day": 2, "city": "Hanoi", "activities": []},
    {"day": 3, "city": "Hoi An", "activities": []},
    {"day": 4, "city": "Hoi An", "activities": []},
    {"day": 5, "city": "Ho Chi Minh City", "activities": []}]}
LATEST = {"trip_id": "7a011103-0000-4000-8000-000000000000", "title": "7 Days in Vietnam", "start": date(2026, 11, 12),
          "end": date(2026, 11, 18), "plan": PLAN, "cities": ["Hanoi", "Hoi An", "Ho Chi Minh City"]}


def ctx(pending=None):
    return {"account": "11111111-1111-4111-8111-111111111111", "ch": {"wa_id_sha256": "k"}, "frm": None, "now": NOW, "out": GW.Out(),
            "st": {"pending": pending, "history": []}, "wa_number": "+447700900123", "button_text": ""}


class Patch:
    def __init__(self, **kw):
        self.kw, self.old = kw, {}

    def __enter__(self):
        for k, v in self.kw.items():
            mod, name = k.split("__")
            m = {"PS": PS, "GW": GW, "WB": WB}[mod]
            self.old[k] = getattr(m, name)
            setattr(m, name, v)

    def __exit__(self, *a):
        for k, v in self.old.items():
            mod, name = k.split("__")
            setattr({"PS": PS, "GW": GW, "WB": WB}[mod], name, v)


class Placeless(unittest.TestCase):
    def test_the_founders_words_are_a_search(self):
        w = WB.placeless("I want a romantic location that has great Vietnamese food")
        self.assertEqual(w, {"what": "romantic Vietnamese restaurant", "kind": "restaurant"})
        self.assertEqual(WB.placeless("find me a cocktail bar")["what"], "cocktail bar")
        self.assertEqual(WB.placeless("I'd love a spa somewhere quiet")["kind"], "spa")

    def test_not_placeless(self):
        for m in ("I want a romantic restaurant in Hoi An", "plan a trip to Vietnam", "I want a hotel", "what's the weather",
                  "show me my itinerary", "I need a flight"):
            self.assertIsNone(WB.placeless(m), m)


class Context(unittest.TestCase):
    def run_ctx(self, body, latest=LATEST):
        async def lat(a):
            return latest
        with Patch(PS__latest=lat):
            return asyncio.run(WB.context("a", body, "restaurant", NOW))

    def test_several_cities_ask_one_question(self):
        c = self.run_ctx("a romantic Vietnamese dinner")
        self.assertEqual(c["ask"], ["Hanoi", "Hoi An", "Ho Chi Minh City"])
        self.assertEqual(c["country"], "VN")

    def test_a_city_or_a_date_said_picks_the_day(self):
        c = self.run_ctx("romantic dinner, Hoi An please")
        self.assertEqual((c["where"], c["trip"]["day"], c["trip"]["date"]), ("Hoi An", 3, "2026-11-14"))
        c = self.run_ctx("romantic dinner on 15 Nov")
        self.assertEqual((c["where"], c["trip"]["day"]), ("Hoi An", 4))

    def test_no_trip_is_home(self):
        c = self.run_ctx("a romantic dinner", latest=None)
        self.assertEqual((c["where"], c.get("home")), ("Madrid", True))
        over = {**LATEST, "end": date(2026, 9, 1)}
        self.assertTrue(self.run_ctx("a romantic dinner", latest=over).get("home"))


class Flow(unittest.TestCase):
    def test_question_then_cards_then_added_to_its_day(self):
        found, added = [], []

        async def lat(a):
            return LATEST

        async def find(c, f, draft):
            found.append(f)
            c["st"]["pending"] = {"kind": "cards", "find": f, "draft": {}, "nonce": "n", "cards": [{"place_id": "p1", "name": "Mango Rooms"}]}

        async def add(account, trip_id, day, activity):
            added.append((day, activity["name"]))
            return True
        c = ctx()
        with Patch(PS__latest=lat, GW___find=find, PS__add_place=add):
            asyncio.run(GW._new_request(c, "I want a romantic location that has great Vietnamese food"))
            self.assertEqual(c["out"].items[-1][0], "ask")
            self.assertEqual(c["out"].items[-1][1], "In Hanoi, Hoi An or Ho Chi Minh City?")
            nonce = c["st"]["pending"]["nonce"]
            self.assertTrue(asyncio.run(GW._answer_pending(c, "Hoi An", f"where:{nonce}:1")))
            self.assertEqual((found[0]["what"], found[0]["where"], found[0]["country"], found[0]["trip"]["day"]),
                             ("romantic Vietnamese restaurant", "Hoi An", "VN", 3))
            asyncio.run(GW._picked_card(c, c["st"]["pending"], {"place_id": "p1", "name": "Mango Rooms"}))
        self.assertEqual(added, [(3, "Mango Rooms")])
        self.assertIn("Added Mango Rooms to Day 3", c["out"].items[-1][1])
        self.assertIn("Nothing is booked yet", c["out"].items[-1][1])
        self.assertEqual(c["st"]["pending"]["kind"], "trip_added")

    def test_book_it_at_8_runs_the_ladder_on_the_trip_day(self):
        got = []

        async def picked(c, pend, card):
            got.append((pend["find"].get("open_at"), "trip" in pend["find"], card["name"]))
        pend = {"kind": "trip_added", "at": NOW.isoformat(), "card": {"place_id": "p1", "name": "Mango Rooms"},
                "find": {"what": "romantic Vietnamese restaurant", "where": "Hoi An", "trip": {"date": "2026-11-14", "day": 3}}, "draft": {}}
        c = ctx(pend)
        with Patch(GW___picked_card=picked):
            self.assertTrue(asyncio.run(GW._answer_pending(c, "book it at 8 for 2", "")))
        self.assertEqual(got, [("2026-11-14T20:00", False, "Mango Rooms")])


class NoDeadEnd(unittest.TestCase):
    def test_anything_else_is_the_web_chats_turn(self):
        async def conduct(msg, hist, **kw):
            return {"response": "**Hoi An** is lovely in November. [Map](https://maps.example/x)", "photos": [], "links": []}
        WB.CONDUCT = conduct
        try:
            c = ctx()
            asyncio.run(GW._new_request(c, "what's Hoi An like in November?"))
        finally:
            WB.CONDUCT = None
        said = c["out"].said()
        self.assertIn("*Hoi An* is lovely", said)
        self.assertNotIn("open Sasha at", said)
        self.assertNotIn("you#whatsapp", said)

    def test_a_brain_failure_is_said_plainly(self):
        async def conduct(msg, hist, **kw):
            raise RuntimeError("x")
        WB.CONDUCT = conduct
        try:
            c = ctx()
            asyncio.run(GW._new_request(c, "tell me a joke"))
        finally:
            WB.CONDUCT = None
        self.assertNotIn("open Sasha at", c["out"].said())

    def test_long_answers_are_chunked(self):
        parts = WB.chunks(["x" * 1000, "y" * 1000, "z" * 3000])
        self.assertTrue(all(len(p) <= 1400 for p in parts))
        self.assertEqual("".join(parts).replace("\n", ""), "x" * 1000 + "y" * 1000 + "z" * 3000)


class Contact(unittest.TestCase):
    def test_the_name_is_asked_here_and_the_booking_carries_on(self):
        calls, resumed = [], []

        async def api(account, method, path, body=None, timeout=90.0):
            calls.append((method, path, body))
            return 200, {"ok": True}

        async def prep(c, pend):
            resumed.append(pend["kind"])
        c = ctx()
        with Patch(GW__api=api, GW___prepare_or_ask=prep):
            asyncio.run(WB.ask_contact(c, {"kind": "need", "draft": {}, "read": {}}))
            self.assertIn("this WhatsApp number", c["out"].items[-1][1])
            self.assertIn("to nobody else", c["out"].items[-1][1])   # the consent sentence, shown as saved
            self.assertTrue(asyncio.run(GW._answer_pending(c, "Tyler Warren", "")))
        self.assertEqual(calls[0][1], "/api/booking/contact")
        self.assertEqual((calls[0][2]["name"], calls[0][2]["mobile"]), ("Tyler Warren", "+447700900123"))
        self.assertEqual(resumed, ["need"])


class TestLabel(unittest.TestCase):
    def test_test_bookings_say_test(self):
        p = {**LATEST}
        rows = [{"venue": "Sasha Test Venue", "date": "2026-11-12", "time": "20:00", "status": "confirmed",
                 "status_words": "Confirmed — their ref TV-D521E5-A9", "type": "restaurant", "category": "restaurant"},
                {"venue": "Real Place", "date": "2026-11-13", "time": "20:00", "status": "requested", "type": "restaurant"}]
        t = "\n".join(PS.text(PS.merge(p, rows)))
        self.assertIn("TEST · Sasha Test Venue", t)
        self.assertNotIn("TEST · Real Place", t)
        self.assertTrue(WB.is_test({"venue": "Flight BA 0105 Madrid → Hanoi (TEST booking)"}))

    def test_added_places_show_not_booked(self):
        plan = {**PLAN, "days": [{**PLAN["days"][0], "activities": [{"time": "Evening", "name": "Mango Rooms", "added": True}]}]}
        t = "\n".join(PS.text(PS.merge({**LATEST, "plan": plan}, [])))
        self.assertIn("📍 Evening: Mango Rooms (not booked yet)", t)

    def test_reset_words(self):
        for m in ("reset the demo", "Reset demo", "clear the demo."):
            self.assertTrue(WB.RESET.match(m), m)
        self.assertFalse(WB.RESET.match("reset the demo bookings at Hanakura and book"))

    def test_reset_is_the_founders(self):
        c = ctx()
        c["account"] = "22222222-2222-4222-8222-222222222222"
        asyncio.run(WB.start_reset(c))
        self.assertIn("founder's", c["out"].said())


if __name__ == "__main__":
    unittest.main()
