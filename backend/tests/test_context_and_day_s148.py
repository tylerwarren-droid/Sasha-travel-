"""Sasha 148 · two of CR 20's proposals, approved by the founder (additive):
  (a) on the web, an in-product booking carries the product's context: products.web.in_context runs before Sasha's own
      booking hand-off (signed-in accounts only), its sentence is what Sasha books, its line goes on top;
  (b) a day given without a time is kept, and only the time is asked — on the web and on WhatsApp. Offline.

    cd backend && python -m unittest tests.test_context_and_day_s148 -v
"""
from __future__ import annotations

import asyncio
import unittest
from datetime import datetime, timezone
from unittest import mock

from booking_signer import chat_request as CQ, guest_whatsapp as GW

A = "11111111-1111-4111-8111-111111111111"
NOW = datetime(2026, 10, 5, 9, 0, tzinfo=timezone.utc)
ASKED = "book me a 60-minute massage in Madrid near Calle de Ejemplo 12 on 2027-03-01"


def run(c):
    return asyncio.new_event_loop().run_until_complete(c)


class ADayWithoutATime(unittest.TestCase):
    def test_the_day_is_kept_and_only_the_time_is_asked(self):
        d = CQ.draft(ASKED, NOW)
        self.assertEqual(d["parts"]["day"], "2027-03-01")
        self.assertIn("when", d["missing"])
        self.assertEqual(d["question"], "What time on Monday 1 March — or shall I ask them when they have space?")
        self.assertNotIn("when", d["parts"])                     # nothing invented: no time, so no "at"

    def test_the_answer_joins_the_thread_on_the_web(self):
        first = CQ.booking_turn(ASKED, [], NOW)
        history = first["messages"]
        out = CQ.booking_turn("at 10am, 1 person", history, NOW)
        d = out["reservation_draft"]
        self.assertEqual(d["missing"], [])
        self.assertEqual(d["parts"]["when"], {"mode": "at", "at": "2027-03-01T10:00"})

    def test_a_day_and_time_together_is_unchanged(self):
        self.assertEqual(CQ.draft("book a massage on 2027-03-01 at 10am for 1 person", NOW)["parts"]["when"],
                         {"mode": "at", "at": "2027-03-01T10:00"})

    def test_whatsapp_asks_only_the_time_and_keeps_the_day(self):
        out = GW.Out()
        ctx = {"out": out, "st": {}, "now": NOW, "account": A}
        pend = {"draft": {"what": {"activity": "a 60-minute massage", "category": "spa"}, "day": "2027-03-01",
                          "how_many": {"count": 1, "unit": "people"}}, "read": {}}
        run(GW._prepare_or_ask(ctx, pend))
        self.assertEqual(out.items[-1], ("text", "What time on Monday 1 March?"))
        seen = {}

        async def capture(c, p):
            seen.update(p["draft"])
        with mock.patch.object(GW, "_prepare_or_ask", capture):
            run(GW._answer_need({**ctx, "out": GW.Out()}, ctx["st"]["pending"], "10am"))
        self.assertEqual(seen["when"], {"mode": "at", "at": "2027-03-01T10:00"})


class TheProductsContextOnTheWeb(unittest.TestCase):
    def test_the_products_sentence_is_booked_and_its_line_said_first(self):
        from app.services import conductor as CD
        seen = []

        async def ctx(user_id, message, signed_in=None, now=None):
            return {"sentence": ASKED, "line": "For your move: near your new address, on arrival.", "product": "relocation"} \
                if "near my hotel" in message else None

        def handoff(message, history):
            seen.append(message)
            return {"response": "Here are places for a massage.", "intents": ["booking"], "messages": []}
        with mock.patch("products.web.in_context", ctx), mock.patch("booking_signer.handoff.booking_handoff", handoff):
            out = run(CD.conduct("book me a 60-minute massage near my hotel on arrival", [], user_id=A, signed_in=True))
        self.assertEqual(seen, [ASKED])                                    # Sasha booked the product's sentence
        self.assertTrue(out["response"].startswith("For your move: near your new address, on arrival."))
        self.assertIn("Here are places for a massage.", out["response"])
        self.assertEqual(out["messages"][-2]["content"], "book me a 60-minute massage near my hotel on arrival")   # the guest's own words kept

    def test_never_for_the_public_demo(self):
        from app.services import conductor as CD
        called = []

        async def ctx(*a, **k):
            called.append(a)
            return None
        with mock.patch("products.web.in_context", ctx), \
             mock.patch("booking_signer.handoff.booking_handoff", lambda m, h: {"response": "ok", "intents": [], "messages": []}):
            run(CD.conduct("book me a massage near my hotel", [], user_id="00000000-0000-4000-8000-0000000d3e00", signed_in=False))
        self.assertEqual(called, [])


if __name__ == "__main__":
    unittest.main()
