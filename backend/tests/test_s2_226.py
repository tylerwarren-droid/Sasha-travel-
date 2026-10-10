"""Sasha 226 · /s2 manages what's booked: my plans; change / cancel; "I'm running late" — read back, yes in a LATER turn, act,
recorded. Offline: fakes only (no call, no email, no Duffel, no database).

    cd backend && python -m unittest tests.test_s2_226 -v
"""
from __future__ import annotations

import asyncio
import unittest
from datetime import date, datetime, time, timedelta, timezone
from unittest import mock

from agapi import s2_manage as M, v0 as API

ACCOUNT = "00000000-0000-4000-8000-000000000226"
run = asyncio.run
D1 = (date.today() + timedelta(days=1)).isoformat()
D3 = (date.today() + timedelta(days=3)).isoformat()


def ctx(started=None):
    c = API.Ctx(account=ACCOUNT, surface="s2")
    if started:
        c.started = started
    return c


VENUES = [{"trip_item_id": "t-dinner", "venue": "Casa Gate", "date": D1, "time": "21:00", "party": 2, "status": "Confirmed",
           "type": "Restaurant", "reference": "TV-1"}]
ROWS = [{"id": "b-flight", "kind": "flight", "state": "booked", "day": D3, "order_id": "ord_1", "booking_reference": "ABC123",
         "snapshot": {"owner": "easyJet", "flights": "U2 7640", "from": "MAD", "to": "LIS", "departs": f"{D3}T09:00"}},
        {"id": "b-hotel", "kind": "stay", "state": "booked", "day": D3, "booking_reference": "H-9", "trip_item_id": None,
         "snapshot": {"name": "Hotel Patio", "city": "Lisbon", "nights": 2}}]


def plans_patches():
    from agapi import venues as VN
    from booking_signer import basket as BK, plan_store as PS
    return [mock.patch.object(VN, "venue_bookings", mock.AsyncMock(return_value=VENUES)),
            mock.patch.object(PS, "plans", mock.AsyncMock(return_value=[{"trip_id": "trip-1", "title": "Lisbon"}])),
            mock.patch.object(BK, "items", mock.AsyncMock(return_value=ROWS))]


class MyPlans(unittest.TestCase):
    def setUp(self):
        for p in plans_patches():
            p.start()
            self.addCleanup(p.stop)

    def test_everything_upcoming_first(self):
        r = run(M.my_plans(ctx(), {}))
        self.assertEqual([i["kind"] for i in r["items"]], ["dinner", "flight", "hotel"])
        self.assertEqual(r["items"][1]["reference"], "ABC123")

    def test_where_am_i_on_a_day_includes_the_nights_hotel(self):
        r = run(M.my_plans(ctx(), {"on": (date.today() + timedelta(days=4)).isoformat()}))   # the 2nd night of the stay
        self.assertEqual([i["title"] for i in r["items"]], ["Hotel Patio"])

    def test_the_card(self):
        from app.agent import sasha as AG
        ev = AG.render("my_plans", run(M.my_plans(ctx(), {})), {})
        self.assertEqual(ev["kind"], "plans")


class RunningLate(unittest.TestCase):
    def setUp(self):
        M._HELD.clear()
        self.calls = []
        from agapi import venues as VN
        GW = VN._API()

        async def api(account, method, path, body=None, timeout=None):
            self.calls.append((method, path, body))
            if method == "GET" and "/notice" in path:
                return 200, {"route": "call", "read_back": {"lines": ["I'll call Casa Gate and say the Gate table for 2 at 21:00 will arrive about 21:20.",
                                                                     "If nobody answers, I'll email them at r@casa.test instead.", "OK?"], "sha256": "n" * 64}}
            if method == "POST" and path.endswith("/notice"):
                return 200, {"status": "call_prepared", "call_id": "call-1", "call_read_back_sha256": "c" * 64}
            if method == "POST" and path.endswith("/place"):
                return 200, {"status": "placed"}
            return 404, {}
        for p in (mock.patch.object(VN, "venue_bookings", mock.AsyncMock(return_value=VENUES)), mock.patch.object(GW, "api", api),
                  mock.patch.object(API, "claim", mock.AsyncMock()), mock.patch.object(M, "_record", mock.AsyncMock())):
            p.start()
            self.addCleanup(p.stop)

    def test_read_back_then_ok_next_turn_calls(self):
        first = run(M.running_late(ctx(), {"minutes": 20, "approval": {"said": "I'm running 20 minutes late"}}))
        self.assertEqual(first["status"], "awaiting_yes")
        self.assertTrue(first["read_back"][0].startswith("I'll call Casa Gate and say the Gate table for 2 at 21:00 will arrive about 21:20"))
        self.assertIn("arrive=21:20", self.calls[0][1])
        later = datetime.now(timezone.utc) + timedelta(seconds=5)
        done = run(M.running_late(ctx(started=later), {"approval": {"said": "OK"}}))
        self.assertEqual(done["status"], "calling")
        self.assertEqual([c[1].rsplit("/", 1)[-1] for c in self.calls[1:]], ["notice", "place"])

    def test_a_yes_in_the_same_turn_does_nothing(self):
        run(M.running_late(ctx(), {"minutes": 20, "approval": {"said": "I'm late"}}))
        same = run(M.running_late(ctx(started=datetime.now(timezone.utc) - timedelta(seconds=60)), {"minutes": 20, "approval": {"said": "yes"}}))
        self.assertEqual(same["status"], "awaiting_yes")       # read back again — nothing sent
        self.assertFalse(any(c[0] == "POST" for c in self.calls))

    def test_a_question_is_not_a_yes(self):
        run(M.running_late(ctx(), {"minutes": 20, "approval": {"said": "I'm late"}}))
        later = datetime.now(timezone.utc) + timedelta(seconds=5)
        r = run(M.running_late(ctx(started=later), {"minutes": 20, "approval": {"said": "Yes — what will you say to them?"}}))
        self.assertEqual(r["status"], "awaiting_yes")
        self.assertFalse(any(c[0] == "POST" for c in self.calls))


class NoticeCall(unittest.TestCase):
    def test_late_in_the_venues_language(self):
        from booking_signer import calls as C
        v = C.CallVenue(key="read:x", name="Casa Test", number_env="", language="es", timezone="Europe/Madrid", number="+34910000000",
                        source="their website")
        p = C.parse_call_particulars({"date": "2026-10-10", "time": "21:00", "party": 2, "name": "Alex Gate", "phone": ""})
        b = C.build_notice_call(v, p, datetime(2026, 10, 10, 15, tzinfo=timezone.utc), "late", arrive=time(21, 25))
        self.assertIn("sobre las 21:25", b["brief"]["first_sentence"])
        self.assertIn("Never agree to anything other than what you asked", b["brief"]["task"])
        with self.assertRaises(C.CallRefused):
            C.build_notice_call(v, p, datetime.now(timezone.utc), "late")
        with self.assertRaises(C.CallRefused):
            C.build_notice_call(v, p, datetime.now(timezone.utc), "book", arrive=time(21, 25))

    def test_nobody_answers_then_the_email_goes(self):
        from booking_signer import venue_notice as VNT, emailing as E, live_events as LE
        sent, pub = [], []

        async def send(http, email):
            sent.append(email)
            return E.Sent(True, "em_1", 200, {}, None)
        reading = mock.Mock(state="not_reached", outcome=None, why="nobody answered. Nothing was agreed.")
        call = {"brief": {"purpose": "late", "venue_name": "Casa Gate", "fallback_email": {"to": "r@casa.test", "subject": "s", "text": "t"}}}
        with mock.patch.object(E, "send", send), mock.patch.object(LE, "publish", lambda a, ev: pub.append(ev)):
            run(VNT.after_call(ACCOUNT, call, reading))
        self.assertEqual(sent[0]["to"], "r@casa.test")
        self.assertIn("So I emailed them at r@casa.test instead.", pub[0]["say"])

    def test_the_call_follow_up_routes_a_late_call(self):
        from booking_signer import call_routes as CRT, venue_notice as VNT
        with mock.patch.object(VNT, "after_call", mock.AsyncMock()) as ac:
            run(CRT._follow_up({"account_id": ACCOUNT, "brief": {"purpose": "late"}}, mock.Mock(state="answered", outcome="yes")))
        ac.assert_awaited_once()


class TestVenue(unittest.TestCase):
    def test_a_stand_in_booking_is_recognised(self):   # its phone is the test line — never a real venue
        from booking_signer import venue_notice as VNT
        self.assertTrue(VNT._our_test_venue({"read": {"name": "Casa Gate (TEST stand-in)"}}))
        self.assertTrue(VNT._our_test_venue({"read": {"sources": ["https://x/api/booking/test-venue/plain"]}}))
        self.assertFalse(VNT._our_test_venue({"read": {"name": "Casa Gate", "sources": ["https://casagate.es"]}}))


class ANewHoldSupersedes(unittest.TestCase):
    def test_a_yes_never_falls_back_to_an_older_venue(self):
        from agapi import venues as VN
        VN._HELD[ACCOUNT] = {"rung": "form", "id": "f1", "sha": "x" * 64, "at": datetime.now(timezone.utc) - timedelta(minutes=2),
                             "venue": "El Mirador de Sol", "when": f"{D1}T21:00", "party": 2, "out": {"status": "awaiting_yes"}}
        with mock.patch.object(VN, "_read", mock.AsyncMock(side_effect=RuntimeError("the new venue's read failed"))):
            with self.assertRaises(RuntimeError):
                run(VN.hold_venue(ctx(), {"name": "D-Sunset Madrid", "city": "Madrid", "day": D1, "time": "21:00", "party": 2}))
        self.assertNotIn(ACCOUNT, VN._HELD)   # nothing left for a yes to book


class CancelledIsOnTheRecord(unittest.TestCase):
    def test_get_status_lists_a_cancelled_table(self):   # found live: she retracted a TRUE "cancelled" because the record didn't show it
        from agapi import venues as VN
        rows = VENUES + [{**VENUES[0], "trip_item_id": "t-2", "venue": "Casa Vieja", "status": "cancelled"}]
        async def vb(account, include_cancelled=False):
            return [r for r in rows if include_cancelled or r["status"] != "cancelled"]
        with mock.patch.object(VN, "venue_bookings", vb), mock.patch.object(API, "_latest", mock.AsyncMock(return_value=None)):
            r = run(API.get_status(ctx(), {}))
        self.assertEqual([v["venue"] for v in r["venues"]], ["Casa Gate"])
        self.assertTrue(r["cancelled"][0].startswith("Casa Vieja"))


class CancelHotelAndFlight(unittest.TestCase):
    def setUp(self):
        M._HELD.clear()
        for p in plans_patches() + [mock.patch.object(API, "claim", mock.AsyncMock())]:
            p.start()
            self.addCleanup(p.stop)

    def test_hotel_read_back_then_yes(self):
        from booking_signer import basket as BK
        r = run(M.cancel_booking(ctx(), {"what": "hotel", "approval": {"said": "cancel the hotel"}}))
        self.assertIn("test hotel booking", r["read_back"][1])
        later = datetime.now(timezone.utc) + timedelta(seconds=5)
        with mock.patch.object(BK, "cancelled", mock.AsyncMock()) as c:
            done = run(M.cancel_booking(ctx(started=later), {"what": "hotel", "approval": {"said": "Yes, cancel it."}}))
        self.assertEqual(done["status"], "cancelled")
        c.assert_awaited_once()

    def test_flight_uses_duffels_quote_then_confirms(self):
        from booking_signer import basket as BK, flight_manage as FM
        q = {"possible": True, "quote_id": "ore_1", "lines": ["I'll cancel your easyJet flight U2 7640.", "Refund €76.41 (Duffel's quote)."]}
        with mock.patch.object(FM, "cancel_quote", mock.AsyncMock(return_value=q)):
            r = run(M.cancel_booking(ctx(), {"what": "flight", "approval": {"said": "cancel my flight"}}))
        self.assertEqual(r["read_back"], q["lines"])
        later = datetime.now(timezone.utc) + timedelta(seconds=5)
        with mock.patch.object(FM, "cancel_confirm", mock.AsyncMock(return_value={"status": "cancelled", "cancellation_id": "ore_1",
                                                                                  "refund_amount": "76.41", "refund_currency": "EUR"})), \
                mock.patch.object(BK, "cancelled", mock.AsyncMock()), mock.patch.object(BK, "event", mock.AsyncMock()):
            done = run(M.cancel_booking(ctx(started=later), {"what": "flight", "approval": {"said": "Yes, cancel it."}}))
        self.assertEqual(done["status"], "cancelled")
        self.assertIn("EUR 76.41", done["say"])


class NextIsUnchanged(unittest.TestCase):
    def test_s1_has_none_of_them(self):
        import app.services.llm as LLM
        from app.agent import sasha as AG
        from app.agent.fakes import Block, client
        seen = []

        async def go():
            async for _ in AG.turn(ACCOUNT, "what's coming up?", [], "s226-s1", None, "s1"):
                pass
        with mock.patch.object(LLM, "client", client([[Block(type="text", text="ok")]], seen=seen)):
            run(go())
        names = [t["name"] for t in seen[0]["tools"]]
        self.assertFalse({"my_plans", "running_late", "change_booking", "cancel_booking"} & set(names))
        self.assertEqual(names, [t["name"] for t in API.TOOLS])


if __name__ == "__main__":
    unittest.main()
