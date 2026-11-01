"""Sasha 247 · CR 87's gap closed: the OLDER WhatsApp-guest flow records each booking in the outcomes ledger at the moment it's sent —
the same rung/channel and key (the reservation's own id) as book_venue — and the reply sync is awaited (never a bare task)."""
from __future__ import annotations

import asyncio
import unittest
from datetime import datetime, timezone
from unittest import mock

from agapi import s2_outcomes as OC
from booking_signer import guest_whatsapp as GW

ACCOUNT = "00000000-0000-4000-8000-000000000247"


def run(c):
    return asyncio.run(c)


class _Out:
    def __init__(self):
        self.items = []

    def text(self, s):
        self.items.append(("text", s))

    def ask(self, s, b):
        self.items.append(("ask", s))


class OldFlowRecordsAtTheMomentItsSent(unittest.TestCase):
    def setUp(self):
        self.sent = []

        async def call(op, body):
            self.sent.append((op, dict(body)))
            return {"ok": True, "result": {"ref": body.get("ref")}}
        for p in (mock.patch.object(OC, "CALL", call), mock.patch.object(OC, "start", lambda: None),
                  mock.patch.object(OC, "_DONE", set()), mock.patch.dict(OC._OPEN, {}, clear=True)):
            p.start()
            self.addCleanup(p.stop)

    def approve(self, pend, answer):
        async def api(account, method, path, body=None, timeout=None):
            return answer
        ctx = {"out": _Out(), "account": ACCOUNT, "st": {}, "now": datetime.now(timezone.utc), "ch": {}, "frm": "+0"}
        with mock.patch.object(GW, "api", api), mock.patch.object(GW, "_receipt_note", lambda *a, **k: ""), \
                mock.patch.object(GW, "_spawn", lambda c: c.close()):
            run(GW._approve(ctx, pend, {"said": "yes"}))
        return [b for op, b in self.sent if op == "outcomes.record"]

    PEND = {"id": "f1", "sha": "x", "venue": "Casa Lucio", "summary": "Saturday at 21:00, 2 people", "trip_item_id": "ti-1",
            "draft": {"what": {"category": "restaurant"}}, "read": {"city": "Madrid"}}

    def test_the_old_flows_own_sends_are_gone_nothing_sent_nothing_recorded(self):
        """Sasha 319 · the form / email / call this recorded were Sasha's own sends to a venue — gone (AgAPI is the one sender): the yes
        reaches no venue, records no outcome, and the guest is told Tyler takes it."""
        for rung in ("form", "email", "call", "call_email", "handover"):
            calls = []

            async def api(account, method, path, body=None, timeout=None):
                calls.append(path)
                return 200, {"status": "sent"}
            out = _Out()
            ctx = {"out": out, "account": ACCOUNT, "st": {}, "now": datetime.now(timezone.utc), "ch": {}, "frm": "+0"}
            with mock.patch.object(GW, "api", api):
                run(GW._approve(ctx, {**self.PEND, "rung": rung}, {"said": "yes"}))
            self.assertEqual((calls, [b for op, b in self.sent if op == "outcomes.record"]), ([], []), rung)

    def test_their_page_sent(self):
        async def api(account, method, path, body=None, timeout=None):
            return 200, {"link_id": "l1", "url": "https://example.com/book", "platform": "their own booking page", "trip_item_id": "ti-2"}
        ctx = {"out": _Out(), "account": ACCOUNT, "st": {}, "now": datetime.now(timezone.utc)}
        rd = {"read_id": "r1", "venue": "Bar Gate", "city": "Madrid"}
        res = {"when": {"at": "2026-10-17T21:00"}, "how_many": {"count": 2}}
        with mock.patch.object(GW, "api", api):
            self.assertTrue(run(GW._send_link(ctx, rd, res, "Alex", None, {"draft": {"what": {"category": "restaurant"}}})))
        b = [b for op, b in self.sent if op == "outcomes.record"][0]
        self.assertEqual((b["ref"], b["rung"], b["channel"], b["state"]), ("sasha:ti-2", "human_tap", "page_handover", "sent"))

    def test_a_ledger_that_doesnt_answer_never_stops_the_booking(self):
        async def down(op, body):
            raise RuntimeError("ledger down")
        with mock.patch.object(OC, "CALL", down):
            got = self.approve({**self.PEND, "rung": "email"}, (200, {"status": "sent"}))
        self.assertEqual(got, [])   # nothing recorded — and _approve finished (it said DONE_ASKED)


class TheGateNeverRecordsLive(unittest.TestCase):
    def test_pinned_to_the_sandbox(self):
        import inspect
        from scripts import gate
        self.assertIn('os.environ["SASHA_OUTCOMES_VIA"] = "sandbox"', inspect.getsource(gate.main))


class TheReplySyncIsAwaited(unittest.TestCase):
    def test_no_bare_task(self):
        import inspect
        from agapi import venues as VN
        src = inspect.getsource(VN.venue_bookings)
        self.assertIn("await asyncio.wait_for(OC.sync(", src)
        self.assertNotIn("create_task(OC.sync", src)


if __name__ == "__main__":
    unittest.main()
