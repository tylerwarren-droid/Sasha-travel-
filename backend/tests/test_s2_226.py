"""Sasha 226 · /s2 manages what's booked: my plans; change / cancel; "I'm running late" — read back, yes in a LATER turn, act,
recorded. Offline: fakes only (no call, no email, no Duffel, no database).

    cd backend && python -m unittest tests.test_s2_226 -v
"""
from __future__ import annotations
import tests.founder_fixture  # noqa: F401,E402  (Sasha 249 · the fixtures name the founder; no fallback any more)

import asyncio
import os
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
    """Sasha 319 · "I'm running late" for a booking on the old reservation route (no AgAPI act): AgAPI is the one sender to venues, so
    nothing is read back or sent from here — Tyler takes it. (An AgAPI act's late: tests.test_s300 / test_s317.)"""

    def setUp(self):
        M._HELD.clear()
        self.calls = []
        from agapi import venues as VN
        GW = VN._API()

        async def api(account, method, path, body=None, timeout=None):
            self.calls.append((method, path, body))
            return 404, {}
        for p in (mock.patch.object(VN, "venue_bookings", mock.AsyncMock(return_value=VENUES)), mock.patch.object(GW, "api", api)):
            p.start()
            self.addCleanup(p.stop)

    def test_it_is_handed_to_tyler_and_nothing_is_sent(self):
        from agapi import venues as VN
        r = run(M.running_late(ctx(), {"minutes": 20, "approval": {"said": "I'm running 20 minutes late"}}))
        self.assertEqual((r["status"], r["sent"], r["line"]), ("to_tyler", False, VN.TO_TYLER))
        self.assertFalse([c for c in self.calls if "/notice" in c[1] or "/place" in c[1]])
        later = datetime.now(timezone.utc) + timedelta(seconds=5)
        again = run(M.running_late(ctx(started=later), {"approval": {"said": "OK"}}))   # a yes after it: still nothing sent
        self.assertEqual(again["status"], "to_tyler")
        self.assertFalse([c for c in self.calls if c[0] == "POST"])


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

    def test_after_a_late_call_nothing_goes_to_the_venue(self):   # Sasha 319 · its "nobody answered → the email" follow-up is gone
        from booking_signer import call_routes as CRT, emailing as E
        with mock.patch.object(E, "send", mock.AsyncMock(side_effect=AssertionError("never an email to the venue"))):
            run(CRT._follow_up({"account_id": ACCOUNT, "brief": {"purpose": "late"}}, mock.Mock(state="not_reached", outcome=None)))


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
        self.assertIn("€76.41", done["say"])   # Sasha 305 · MOVED: the refund said in the money's own words (FM.money), then the order re-read


class NextIsUnchanged(unittest.TestCase):
    @mock.patch.dict(os.environ, {"SASHA_S1_PARITY": "off"})   # Sasha 241 · the old S1, exactly, behind its way-back switch
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

# Sasha 353 · these tests compare SURFACES (what each can offer): the per-turn need selection is set aside (tests/whole_surface.py)
def setUpModule():
    from tests import whole_surface as _WS
    _WS.start()


def tearDownModule():
    from tests import whole_surface as _WS
    _WS.stop()


if __name__ == "__main__":
    unittest.main()
