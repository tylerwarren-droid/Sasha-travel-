"""CR 130 · a record of what happened never holds up the person's answer (Sasha 299 (4): outcomes.record took 8.9 s on La Mi Venta's tap,
and her answer waited for it). venues._finish hands the ledger write to s2_outcomes.booked_later; the timeline keeps AgAPI's own time."""
import asyncio
import inspect
import time
import unittest

from agapi import measure as MS, s2_outcomes as OC, venues as VN


class TheLedgerIsWrittenAfter(unittest.TestCase):
    def test_a_the_answer_does_not_wait_for_a_slow_ledger(self):
        sent = []

        async def slow(op, body):
            await asyncio.sleep(0.5)
            sent.append(op)
            return {"ok": True, "result": {"outcome_id": "bko_x"}}

        async def run():
            was, OC.CALL = OC.CALL, slow
            try:
                t = time.perf_counter()
                OC.booked_later("acct_cr130", {"rung": "page", "id": "h1"}, "La Mi Venta", "Madrid", result={"status": "page_link"})
                back = time.perf_counter() - t
                await OC.settle()
                return back
            finally:
                OC.CALL = was
        back = asyncio.run(run())
        self.assertLess(back, 0.05)              # her answer goes on at once
        self.assertEqual(sent, ["outcomes.record"])   # and the attempt is still recorded, once

    def test_b_the_taps_path_never_awaits_the_ledger(self):
        src = inspect.getsource(VN._finish)
        self.assertNotIn("await OC.booked(", src)
        self.assertEqual(src.count("OC.booked_later("), 2)

    def test_c_never_raises_without_a_loop(self):
        OC.booked_later("acct_cr130", {"rung": "page"}, "X", None)

    def test_d_the_timeline_keeps_agapis_own_time(self):
        tok = MS._TURN.set({"agapi_ops": 0, "t0": time.perf_counter()})
        try:
            MS.agapi_op("outcomes.record", {}, {"ok": True, "result": {}, "trace": {"ms": 41}}, 8900, "https://agapi-live", None)
            MS.agapi_op("venue.profile", {}, {"ok": False}, 300, "https://agapi-live", None)
            ops = MS._TURN.get()["ops"]
        finally:
            MS._TURN.reset(tok)
        self.assertEqual((ops[0]["ms"], ops[0]["server_ms"]), (8900, 41))
        self.assertNotIn("server_ms", ops[1])


if __name__ == "__main__":
    unittest.main()
