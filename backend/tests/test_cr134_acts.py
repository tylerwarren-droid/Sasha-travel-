"""CR 134 · cancel_venue's first booking_unknown (Sasha 302, row 1474): the AgAPI acts behind get_status / cancel_venue were read one
status at a time under ONE 5-second budget, and a timeout dropped EVERY act — so a booking with a change, a late and a cancel waiting to be
read came back "unknown" once, then (its reads having updated the kept acts in place) found on the retry. Root test: the reads go out
together (bounded by the slowest), and a read that is still slow gives the acts as last known — never "no bookings".

    cd backend && python -m unittest tests.test_cr134_acts -v
"""
from __future__ import annotations

import asyncio
import time
import unittest
from unittest import mock

from agapi import venue_submit as VS, venues as VN
from booking_signer import guest_whatsapp as GW

ACCOUNT = "cr134-acts"
SOON = "2999-01-01T21:30"
BOOKING = {"act_id": "act_booking", "venue": "Taverna Correo (sandbox)", "when": SOON, "party": 4, "channel": "email",
           "state": "confirmed", "words": "Confirmed: a table for 4 at 21:00."}
ASKS = [{"act_id": f"act_{k}", "venue": "Taverna Correo (sandbox)", "when": SOON, "party": 4, "channel": "email", "state": "sent",
         "words": None, ("cancels" if k == "cancel" else "changes"): "act_booking", "kind": k} for k in ("change", "late", "cancel")]


def run(c):
    return asyncio.get_event_loop().run_until_complete(c)


class SlowReads(unittest.TestCase):
    def setUp(self):
        VS._ACTS[ACCOUNT] = [dict(BOOKING)] + [dict(a) for a in ASKS]
        self.addCleanup(VS._ACTS.pop, ACCOUNT, None)

        async def api(account, method, path, body=None, timeout=90.0):
            return 200, {"reservations": []}
        for p in (mock.patch.object(GW, "api", api), mock.patch("agapi.s2_outcomes.sync", mock.AsyncMock()),
                  mock.patch("agapi.s2_memory.put_kind", mock.AsyncMock())):
            p.start()
            self.addCleanup(p.stop)

    def reads_take(self, secs):
        async def status(account, act_id):
            await asyncio.sleep(secs)
            return {"state": "sent", "venue_words": {"untrusted_text": "Sent by email"}}
        p = mock.patch.object(VS, "status", status)
        p.start()
        self.addCleanup(p.stop)

    def test_a_three_slow_reads_together_fit_where_one_after_another_did_not(self):
        self.reads_take(2.0)                                                    # 3 × 2 s one after another = 6 s > the 5 s budget
        t0 = time.monotonic()
        got = run(VN.venue_bookings(ACCOUNT))
        self.assertLess(time.monotonic() - t0, 4.5)                             # together: about the slowest one
        self.assertEqual([(b["act_id"], b["status"]) for b in got], [("act_booking", "confirmed")])   # cancel_venue's filter finds it

    def test_b_slower_than_the_budget_the_booking_is_still_there_as_last_known(self):
        self.reads_take(30.0)
        t0 = time.monotonic()
        got = run(VN.venue_bookings(ACCOUNT))
        self.assertLess(time.monotonic() - t0, 6.5)
        self.assertEqual([(b["act_id"], b["status"]) for b in got], [("act_booking", "confirmed")])   # never "no bookings"

    def test_c_one_failing_read_leaves_the_others(self):
        async def status(account, act_id):
            if act_id == "act_late":
                raise RuntimeError("AgAPI hiccup")
            return {"state": "confirmed", "venue_words": {"untrusted_text": "Sí."}}
        with mock.patch.object(VS, "status", status):
            run(VN.venue_bookings(ACCOUNT))
        kept = {a["act_id"]: a for a in VS._ACTS[ACCOUNT]}
        self.assertEqual((kept["act_change"]["state"], kept["act_late"]["state"]), ("confirmed", "sent"))


if __name__ == "__main__":
    unittest.main()
