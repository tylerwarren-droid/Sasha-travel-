"""Sasha 246 item 4 (EU 241's walk) · six small fixes, offline: fakes only (no Google Places, no Duffel, no Stripe, no database).

    1 a hotel's NAME, never its page title ("Tings Lisbon - better rates…")
    2 the Trip tab's travellers: the plan's party (a plan without one takes its basket rows')
    3 cancel can drop a HELD trip (waiting for payment, nothing booked) — read back, then their yes in a later turn
    4 the spoken read-back names BOTH flights, the outbound first
    6 the Subscriptions text on WhatsApp when none are found

    cd backend && python -m unittest tests.test_s2_246_six -v
"""
from __future__ import annotations

import asyncio
import unittest
from datetime import date, datetime, timedelta, timezone
from unittest import mock

from agapi import s2_manage as M, v0 as API

ACCOUNT = "00000000-0000-4000-8000-000000000246"
TRIP = "11111111-1111-4111-8111-111111111246"
run = asyncio.run
D3 = (date.today() + timedelta(days=3)).isoformat()
D9 = (date.today() + timedelta(days=9)).isoformat()


def ctx(started=None):
    c = API.Ctx(account=ACCOUNT, surface="s2")
    if started:
        c.started = started
    return c


# ── 1 · the hotel's name ─────────────────────────────────────────────────────────────────────────────────────────────────────

class HotelName(unittest.TestCase):
    def test_a_page_titles_marketing_tail_is_dropped(self):
        from app.services.world_itinerary import hotel_name
        self.assertEqual(hotel_name("Tings Lisbon - better rates…"), "Tings Lisbon")
        self.assertEqual(hotel_name("Tings Lisbon - better rates on our official site"), "Tings Lisbon")
        self.assertEqual(hotel_name("Hotel Patio | Official Site | Best Price Guaranteed"), "Hotel Patio")
        self.assertEqual(hotel_name("Casa Azul – Book Direct & Save"), "Casa Azul")

    def test_a_real_name_is_kept_as_it_is(self):
        from app.services.world_itinerary import hotel_name
        for n in ("Pestana Palace Lisboa - Hotel & National Monument", "Memmo Alfama", "Hotel Mar-Sol", "The Lumiares Hotel & Spa"):
            self.assertEqual(hotel_name(n), n)
        self.assertEqual(hotel_name("  Memmo   Alfama "), "Memmo Alfama")
        self.assertEqual(hotel_name(None), "")

    def test_search_stays_and_its_card_carry_the_name(self):
        from app.services import world_itinerary as W
        from booking_signer import guest_whatsapp as GW
        cand = {"place_id": "ChIJtings", "name": "Tings Lisbon - better rates…", "types": ["lodging"], "rating": 4.6, "rating_count": 900,
                "address": "Rua X, Lisboa"}
        with mock.patch.object(GW, "api", mock.AsyncMock(return_value=(200, {"candidates": [cand]}))):
            hs = run(W.hotels_in(ACCOUNT, "Lisbon", "Portugal", "PT"))
        self.assertEqual(hs[0]["name"], "Tings Lisbon")
        from app.agent import sasha as AG
        card = AG.stays_card({"city": "Lisbon", "stays": [{"name": "Tings Lisbon - better rates…", "estimate_eur_per_night": 140}]})
        self.assertEqual(card["options"][0]["name"], "Tings Lisbon")


# ── 2 · travellers ───────────────────────────────────────────────────────────────────────────────────────────────────────────

class TravellersFromTheBasket(unittest.TestCase):
    def test_a_plan_without_its_party_takes_the_baskets(self):
        from booking_signer import basket as BK
        rows = [{"id": "f1", "kind": "flight", "state": "chosen", "party": 2, "slice_key": "out:MAD→LIS", "snapshot": {}, "day": D3}]
        self.assertEqual(BK.overlay({"days": []}, rows)["party"], 2)

    def test_the_plans_own_party_wins(self):
        from booking_signer import basket as BK
        rows = [{"id": "f1", "kind": "flight", "state": "chosen", "party": 2, "slice_key": "out:MAD→LIS", "snapshot": {}, "day": D3}]
        self.assertEqual(BK.overlay({"days": [], "party": 3}, rows)["party"], 3)
        self.assertNotIn("party", BK.overlay({"days": []}, []))


# ── 3 · cancel drops a HELD trip ─────────────────────────────────────────────────────────────────────────────────────────────

HELD_ROWS = [{"id": "h-flight", "kind": "flight", "state": "pending_payment", "day": D3, "order_id": None, "paid_session": "cs_test_246",
              "snapshot": {"owner": "Iberia", "flights": "IB3116", "from": "MAD", "to": "LIS", "departs": f"{D3}T08:30"}},
             {"id": "h-stay", "kind": "stay", "state": "pending_payment", "day": D3, "paid_session": "cs_test_246",
              "snapshot": {"name": "Memmo Alfama", "city": "Lisbon", "nights": 6}}]
PEND = {"sid": "cs_test_246", "trip_id": TRIP, "rows": HELD_ROWS}


class CancelDropsAHeldTrip(unittest.TestCase):
    def setUp(self):
        from agapi import venues as VN
        from booking_signer import basket as BK, basket_book as BB, plan_store as PS
        M._HELD.clear()

        async def items(account, trip_id, states=BK.LIVE):
            return [r for r in HELD_ROWS if r["state"] in states]
        self.supersede = mock.AsyncMock(return_value=None)
        self.trips = []

        async def runner(fn):
            class C:
                async def execute(_s, sql, *args):
                    self.trips.append((sql, args))
            return await fn(C())
        for p in (mock.patch.object(VN, "venue_bookings", mock.AsyncMock(return_value=[])),
                  mock.patch.object(PS, "plans", mock.AsyncMock(return_value=[{"trip_id": TRIP, "title": "Lisbon"}])),
                  mock.patch.object(PS, "_run", lambda: runner),
                  mock.patch.object(BK, "items", items),
                  mock.patch.object(BB, "in_progress", mock.AsyncMock(return_value=PEND)),
                  mock.patch.object(BB, "_supersede", self.supersede),
                  mock.patch.object(API, "claim", mock.AsyncMock())):
            p.start()
            self.addCleanup(p.stop)

    def test_plan_read_back_then_yes_drops_it(self):
        r = run(M.cancel_booking(ctx(), {"what": "plan", "approval": {"said": "cancel the trip"}}))
        self.assertEqual(r["status"], "awaiting_yes")
        self.assertIn("held trip “Lisbon”", r["read_back"][0])
        self.assertIn("Iberia IB3116 MAD→LIS", r["read_back"][0])
        self.assertIn("Memmo Alfama, Lisbon", r["read_back"][0])
        self.supersede.assert_not_awaited()   # nothing touched before their yes
        later = datetime.now(timezone.utc) + timedelta(seconds=5)
        done = run(M.cancel_booking(ctx(started=later), {"what": "plan", "approval": {"said": "Yes, cancel it."}}))
        self.assertEqual(done["status"], "cancelled")
        self.supersede.assert_awaited_once()
        self.assertTrue(any("update trips set status = 'cancelled'" in sql for sql, _ in self.trips))

    def test_a_held_flight_is_no_longer_refused(self):   # before: "that flight isn't ticketed yet — nothing to cancel"
        r = run(M.cancel_booking(ctx(), {"what": "flight", "approval": {"said": "cancel my flight"}}))
        self.assertEqual(r["status"], "awaiting_yes")
        self.assertTrue(r["read_back"][0].startswith("I'll drop your held trip"))

    def test_a_yes_in_the_same_turn_drops_nothing(self):
        r = run(M.cancel_booking(ctx(), {"what": "plan", "approval": {"said": "cancel the trip"}}))
        same = run(M.cancel_booking(ctx(started=datetime.now(timezone.utc) - timedelta(seconds=60)), {"what": "plan", "approval": {"said": "yes"}}))
        self.assertEqual(same["status"], "awaiting_yes")
        self.supersede.assert_not_awaited()
        self.assertEqual(r["read_back"], same["read_back"])

    def test_paid_already_is_refused_never_dropped(self):
        self.supersede.return_value = {"why": "your earlier payment for this trip has already gone through"}
        run(M.cancel_booking(ctx(), {"what": "plan", "approval": {"said": "cancel the trip"}}))
        later = datetime.now(timezone.utc) + timedelta(seconds=5)
        done = run(M.cancel_booking(ctx(started=later), {"what": "plan", "approval": {"said": "Yes, cancel it."}}))
        self.assertEqual(done["status"], "not_cancelled")
        self.assertFalse(self.trips)

    def test_nothing_held_is_said(self):
        from booking_signer import basket_book as BB
        with mock.patch.object(BB, "in_progress", mock.AsyncMock(return_value=None)), mock.patch.object(BB, "current", mock.AsyncMock(return_value=None)):
            with self.assertRaises(API.ToolError) as e:
                run(M.cancel_booking(ctx(), {"what": "plan"}))
        self.assertEqual(e.exception.code, "nothing_held")

    def test_a_planned_trip_read_back_but_never_paid_is_dropped_on_their_yes(self):
        """Found live (scratch F): after the read-back, "cancel the whole plan" → nothing_held → "I can't delete it myself"."""
        from booking_signer import basket as BK, basket_book as BB
        planned = [dict(r, state="chosen", paid_session=None) for r in HELD_ROWS]
        dropped = mock.AsyncMock(return_value=2)

        async def items(account, trip_id, states=BK.LIVE):
            return [r for r in planned if r["state"] in states]
        with mock.patch.object(BB, "in_progress", mock.AsyncMock(return_value=None)), \
                mock.patch.object(BB, "current", mock.AsyncMock(return_value={"rows": planned, "trip_id": TRIP, "title": "Lisbon"})), \
                mock.patch.object(BK, "items", items), mock.patch.object(BK, "drop_planned", dropped):
            r = run(M.cancel_booking(ctx(), {"what": "plan", "approval": {"said": "cancel the whole plan"}}))
            self.assertEqual(r["status"], "awaiting_yes")
            self.assertIn("planned trip “Lisbon”", r["read_back"][0])
            dropped.assert_not_awaited()                                        # nothing touched before their yes
            later = datetime.now(timezone.utc) + timedelta(seconds=5)
            done = run(M.cancel_booking(ctx(started=later), {"what": "plan", "approval": {"said": "Yes, cancel it."}}))
        self.assertEqual(done["status"], "cancelled")
        dropped.assert_awaited_once_with(ctx().account, TRIP)
        self.assertTrue(any("update trips set status = 'cancelled'" in sql for sql, _ in self.trips))

    def test_the_tool_offers_plan(self):
        t = next(t for t in M.tools() if t["name"] == "cancel_booking")
        self.assertIn("plan", str(t))


# ── 4 · both flights in the spoken read-back, the outbound first ─────────────────────────────────────────────────────────────

def _fl(i, leg, day, owner, num, frm, to, hhmm):
    return {"id": i, "kind": "flight", "state": "chosen", "day": day, "slice_key": f"{leg}:{frm}→{to} {day}" if leg else f"{frm}→{to} {day}",
            "price_amount": 100.0, "price_currency": "EUR", "price_source": "quoted",
            "snapshot": {"owner": owner, "flights": num, "from": frm, "to": to, "departs": f"{day}T{hhmm}:00"}}


class BothFlightsSpoken(unittest.TestCase):
    def test_outbound_first_even_when_the_rows_come_home_first(self):
        from booking_signer import basket_book as BB
        rows = [_fl("b", "back", D9, "TAP", "TP1026", "LIS", "MAD", "19:05"), _fl("a", "out", D3, "Iberia", "IB3116", "MAD", "LIS", "08:30")]
        said = BB.flights_spoken(rows)
        self.assertTrue(said.startswith("Flying out on Iberia IB3116"), said)
        self.assertIn("; home on TAP TP1026", said)
        self.assertLess(said.index("Iberia"), said.index("TAP"))

    def test_the_read_back_lines_put_the_outbound_first(self):
        from booking_signer import basket_book as BB
        rows = [_fl("b", "back", D9, "TAP", "TP1026", "LIS", "MAD", "19:05"), _fl("a", "out", D3, "Iberia", "IB3116", "MAD", "LIS", "08:30")]
        lines = [l for l in BB.lines_of(rows, 2) if l.startswith("✈️")]
        self.assertEqual(len(lines), 2)
        self.assertIn("Iberia", lines[0])
        self.assertIn("TAP", lines[1])

    def test_the_cheapest_fare_picks_with_no_leg_are_ordered_by_day(self):
        from booking_signer import basket_book as BB
        rows = [_fl("b", "", D9, "TAP", "TP1026", "LIS", "MAD", "19:05"), _fl("a", "", D3, "Iberia", "IB3116", "MAD", "LIS", "08:30")]
        self.assertTrue(BB.flights_spoken(rows).startswith("Flying out on Iberia"))

    def test_only_a_flight_home_says_no_flight_out(self):
        from booking_signer import basket_book as BB
        said = BB.flights_spoken([_fl("b", "back", D9, "TAP", "TP1026", "LIS", "MAD", "19:05")])
        self.assertTrue(said.startswith("Home on TAP"), said)
        self.assertIn("No flight out is chosen yet.", said)

    def test_hold_booking_hands_her_the_line(self):
        from booking_signer import basket as BK, basket_book as BB, passengers as PX
        q = {"lines": ["⚠ TEST", "✈️ Iberia", "✈️ TAP", "Total €200.00 (TEST)"], "sha256": "x" * 64, "eur": 200.0,
             "spoken_flights": "Flying out on Iberia IB3116, …; home on TAP TP1026, …."}
        API._HELD.pop(ACCOUNT, None)
        with mock.patch.object(API, "_plan", mock.AsyncMock(return_value={"trip_id": TRIP, "plan": {"party": 2}})), \
                mock.patch.object(PX, "saved", mock.AsyncMock(return_value=[{}, {}])), \
                mock.patch.object(API, "_s1_passport", mock.AsyncMock(return_value=None)), \
                mock.patch.object(BB, "quote", mock.AsyncMock(return_value=q)), \
                mock.patch.object(BK, "items", mock.AsyncMock(return_value=[])), \
                mock.patch("agapi.keep_gate.keep_on", lambda *a: False):
            res = run(API.hold_booking(ctx(), {}))
        API._HELD.pop(ACCOUNT, None)
        self.assertEqual(res["say_flights"], q["spoken_flights"])


# ── 6 · the Subscriptions text when none are found ───────────────────────────────────────────────────────────────────────────

class _Out:
    def __init__(self):
        self.texts = []

    def text(self, t):
        self.texts.append(t)
        return self


class NoSubscriptions(unittest.TestCase):
    def test_none_found_has_its_own_heading(self):
        from booking_signer import wa_agent as WA
        out = _Out()
        WA.render({"kind": "subscriptions", "items": [], "total": "", "source": "your Gmail"}, out, {}, datetime.now(timezone.utc))
        self.assertTrue(out.texts[0].startswith("*No subscriptions found*\nNo subscription receipts found — read from your Gmail."), out.texts)
        self.assertNotIn("say which", out.texts[0])

    def test_a_list_is_as_before(self):
        from booking_signer import wa_agent as WA
        out = _Out()
        WA.render({"kind": "subscriptions", "items": [{"service": "Netflix", "price": "€12.99", "how_often": "monthly"}],
                   "total": "EUR 12.99"}, out, {}, datetime.now(timezone.utc))
        self.assertTrue(out.texts[0].startswith("*Your subscriptions*\nNetflix · €12.99 a month"), out.texts)
        self.assertIn("About EUR 12.99 a month. To cancel one, say which.", out.texts[0])


if __name__ == "__main__":
    unittest.main()
