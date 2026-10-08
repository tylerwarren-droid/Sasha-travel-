"""CR 56 · robustness facts about Sasha's agent, pinned (fixtures only, 0 live calls). docs/sasha/robustness-review.md.

Passing tests hold what is right today; @expectedFailure ones are the gaps the review ranks — each flips to a failure the day it's
fixed (remove the decorator then, and it guards from that day on).

    cd backend && python -m unittest tests.test_robustness_cr56 -v
"""
from __future__ import annotations

import unittest

from agapi import v0 as API


class Spending(unittest.TestCase):
    def test_a_turn_has_a_step_cap(self):
        from app.agent import sasha as AG
        self.assertLessEqual(AG.MAX_STEPS, 8)

    @unittest.expectedFailure   # CR 56 · the agent's own route is outside the rate limiter: "/api/agents" doesn't match "/api/agent/…"
    def test_the_agent_route_is_rate_limited(self):
        from app.middleware import ratelimit as RL
        self.assertTrue(any("/api/agent/turn".startswith(p) for p in RL._PROTECTED_PREFIXES))

    @unittest.expectedFailure   # CR 56 · no per-account daily budget for the agent (model steps / paid tool calls)
    def test_there_is_a_per_account_daily_budget(self):
        from app.agent import sasha as AG
        self.assertTrue(hasattr(AG, "DAILY_BUDGET") or hasattr(API, "DAILY_BUDGET"))


class Acting(unittest.TestCase):
    ACTS = {"book", "book_venue", "cancel_venue"}

    def test_every_acting_tool_needs_the_persons_yes(self):
        """Each tool that spends, sends or cancels declares no_explicit_yes among its errors — the loop fills its approval."""
        for name in self.ACTS:
            self.assertIn("no_explicit_yes", API.BY_NAME[name]["errors"], name)

    def test_the_model_never_sees_the_approval_field(self):
        for t in API.TOOLS:
            self.assertNotIn("approval", API.schema_for_model(t)["input_schema"]["properties"], t["name"])
            self.assertNotIn("idempotency_key", API.schema_for_model(t)["input_schema"]["properties"], t["name"])

    def test_the_loop_fills_the_approval_for_every_acting_tool(self):
        import inspect
        from app.agent import sasha as AG
        src = inspect.getsource(AG.turn)
        for name in self.ACTS:
            self.assertIn(f'"{name}"', src, f"{name}: the loop must fill its approval from the real message")


def run(c):
    import asyncio
    return asyncio.run(c)


class OutsideServicesDown(unittest.TestCase):
    """What she does when an outside service fails — never improvise, never act on an outage as if it were a fact."""

    ROW = {"id": "r1", "kind": "flight", "state": "chosen", "snapshot": {"id": "off_1", "amount": "120.00", "currency": "EUR",
                                                                        "owner": "Iberia", "flights": "IB 3166"}}

    @unittest.expectedFailure   # CR 56 · a Duffel 5xx on the offer check reads as "no longer offered" → _replace_gone_flights SWAPS it
    def test_duffel_down_is_never_read_as_the_flight_gone(self):
        from unittest import mock
        from booking_signer import basket_book as BB, travel as T
        with mock.patch.object(T, "HTTP", mock.AsyncMock(return_value=(503, {"errors": [{"message": "unavailable"}]}))), \
                mock.patch.object(BB, "_card", lambda r: r["snapshot"]), \
                mock.patch.object(BB, "_same_flight", mock.AsyncMock(return_value=None)):
            v = run(BB._validate_flight("acct", self.ROW, 1))
        self.assertNotIn("no longer offered", v.get("why", ""), v)

    @unittest.expectedFailure   # CR 56 · the payment is sent even when its restart-safe record wasn't written → paid, never booked
    def test_no_payment_link_without_its_record(self):
        from unittest import mock
        from booking_signer import basket_book as BB, basket as BK, guest_whatsapp as GW, paid_watch as PWT, test_deposit as TD
        cur = {"rows": [dict(self.ROW, price_amount=120.0, price_currency="EUR", day="2026-11-12")], "party": 1, "trip_id": "t1", "title": "Trip"}
        lines = BB.lines_of(cur["rows"], 1)
        import hashlib
        sha = hashlib.sha256("\n".join(lines).encode()).hexdigest()
        tap = mock.AsyncMock(return_value="sent")
        with mock.patch.object(BB, "current", mock.AsyncMock(return_value=cur)), \
                mock.patch.object(TD, "checkout", mock.AsyncMock(return_value={"id": "cs_test_1", "url": "https://checkout.stripe.test/x"})), \
                mock.patch.object(BK, "hold", mock.AsyncMock()), \
                mock.patch.object(PWT, "remember", mock.AsyncMock(return_value=None)), \
                mock.patch.object(GW, "tap_to_pay", tap):
            got = run(BB.pay("acct", sha))
        tap.assert_not_called()
        self.assertIn("why", got)

    @unittest.expectedFailure   # CR 56 · a database outage reads as "there is no trip on this account yet"
    def test_database_down_is_never_read_as_no_trip(self):
        from unittest import mock
        from booking_signer import plan_store as PS
        async def down(fn):                                                        # the database itself is unreachable
            raise ConnectionError("pool exhausted")
        with mock.patch.object(PS, "STORE_RUN", down):
            r = run(API.call(API.Ctx(account="00000000-0000-4000-8000-0000000000c6"), "get_trip", {}))
        self.assertNotEqual((r.get("error") or {}).get("code"), "no_trip", r)       # an outage is said as one, never "no trip"


class Injection(unittest.TestCase):
    @unittest.expectedFailure   # CR 56 · a venue's own words reach the model through get_status (status_words) unmarked
    def test_venue_words_reach_the_model_marked_as_untrusted(self):
        import inspect
        from agapi import venues as VN
        self.assertIn("untrusted", inspect.getsource(VN.venue_bookings))

    @unittest.expectedFailure   # CR 56 · the model gets every tool on every turn (skill scoping is on branch cr/campusme-skill)
    def test_the_tool_list_is_scoped(self):
        import inspect
        from app.agent import sasha as AG
        self.assertNotIn("for t in API.TOOLS]", inspect.getsource(AG.tools_for_model))


if __name__ == "__main__":
    unittest.main()
