"""Sasha 339 · Book all as ONE background job; offer gone → re-plan once; limits at booking; a swap flies the newcomer's own flights
(docs/sasha/S-339-book-all.md). Offline: 334's world (20 fictional workers) and an AgAPI double that quotes prices as CR 164 does.
    cd backend && python -m unittest tests.test_s339_book_all -v
"""
from __future__ import annotations

import asyncio
import json
import pathlib
import unittest
from unittest import mock

from booking_signer import group_book as GB, groups as G
from tests import test_s334 as W334

run = asyncio.run
OWNER = W334.OWNER
ROOT = pathlib.Path(__file__).resolve().parents[2]


class PricedAgAPI(W334.FakeAgAPI):
    """CR 164's prices: flights quoted per offer, the stay by its price per night (Hotel Alba (test))."""

    def __init__(self, per_night=9000, gone=(), gone_twice=(), busy=(), slow=0.0):
        super().__init__()
        self.per_night, self.gone, self.gone_twice, self.busy, self.slow = per_night, set(gone), set(gone_twice), set(busy), slow
        self.seen, self.inflight, self.peak, self.bodies = {}, 0, 0, []

    async def _do(self, op, body, approval):
        if op == "travel.find_flights":
            return {"ok": True, "result": {"offers": [{"offer_ref": f"off_{body['origin']['query']}_{body['destination']['query']}_{body['date']}_{self._id('o')}",
                                                       "price": {"amount_minor": 12000, "currency": "EUR"}}]}}
        if op == "travel.find_stays":
            return {"ok": True, "result": {"stays": [{"stay_ref": "stay_alba", "name": {"text": "Hotel Alba (test)"},
                                                      "price_per_night": {"amount_minor": self.per_night, "currency": "EUR"}}]}}
        if op in ("group.book", "group.swap") and not approval:
            self.bodies.append((op, json.loads(json.dumps(body))))
            name = f"{body['worker']['given_name']} {body['worker']['family_name']}"
            n = self.seen[name] = self.seen.get(name, 0) + 1
            self.inflight += 1
            self.peak = max(self.peak, self.inflight)
            try:
                await asyncio.sleep(self.slow or 0.005)
            finally:
                self.inflight -= 1
            if name in self.busy and n == 1:
                return {"ok": False, "error": {"code": "upstream_rate_limited", "message": "busy", "retry_after_s": 10}}
            if (name in self.gone and n == 1) or name in self.gone_twice:
                return {"ok": False, "error": {"code": "upstream_refused", "message": "The airline no longer offers that fare; search again.",
                                               "details": {"service": "duffel", "reason": "offer_gone", "duffel_code": "offer_no_longer_available"}}}
        return await super()._do(op, body, approval)


class World(W334.World):
    def __init__(self, agapi=None):
        super().__init__()
        self._agapi = agapi or PricedAgAPI()

    def __enter__(self):
        super().__enter__()
        self.agapi = self._agapi
        for p in (mock.patch.object(GB, "CALL", self.agapi), mock.patch.object(GB, "SLEEP", lambda s: asyncio.sleep(0)),
                  mock.patch.dict(GB._JOBS, {}, clear=True)):
            p.start()
            self.p.append(p)
        return self


class OneJobOneCard(unittest.TestCase):
    def test_parallel_bounded_progress_one_card(self):
        with World() as w:
            seen = []
            card = run(GB.prepare(OWNER, "book", progress=lambda d, t: seen.append((d, t))))
        self.assertEqual(card["status"], "awaiting_yes")
        self.assertEqual(card["read_back"].count(""), 19)                                   # 19 read-backs on ONE card …
        self.assertTrue(card["read_back_id"].startswith("grp_"))                             # … with ONE id → ONE Yes
        self.assertEqual((seen[0], seen[-1]), ((0, 20), (20, 20)))                           # progress, counted
        self.assertTrue(1 < w.agapi.peak <= GB.BOOK_PARALLEL, w.agapi.peak)                 # in parallel, never more than 4

    def test_the_job_answers_at_once_and_never_reads_nothing_to_do(self):
        with World(PricedAgAPI(slow=0.05)):
            async def go():
                first = await GB.start(OWNER)
                mid = GB.job_view(OWNER)
                await GB.wait(OWNER, 30)
                return first, mid, GB.job_view(OWNER)
            first, mid, done = run(go())
        self.assertEqual(first["state"], "preparing")                                        # answered at once (no 120 s request)
        self.assertRegex(mid["say"], r"^Preparing 20… \d+ ready\.$")
        self.assertEqual((done["state"], done["result"]["status"]), ("ready", "awaiting_yes"))
        page = (ROOT / "frontend/app/group/page.tsx").read_text()
        self.assertIn("bookingReq('/api/booking/group/job')", page)
        self.assertIn("Sasha didn’t answer in time — nothing was booked or changed.", page)
        self.assertNotIn("'Nothing to do.'", page)                                           # a lost request never reads as nothing to do

    def test_agapi_busy_is_waited_out_once(self):
        with World(PricedAgAPI(busy={"Amara Sample"})) as w:
            card = run(GB.prepare(OWNER, "book", ["Amara Sample"]))
        self.assertEqual((card["status"], w.agapi.seen["Amara Sample"]), ("awaiting_yes", 2))


class OfferGone(unittest.TestCase):
    def test_replanned_once_then_held_per_worker(self):
        with World(PricedAgAPI(gone={"Amara Sample"}, gone_twice={"Bruno Example"})) as w:
            plans = []
            real = G.plan

            async def spy(account, movement_id=None, only=None):
                plans.append(only)
                return await real(account, movement_id, only)
            with mock.patch.object(G, "plan", spy):
                card = run(GB.prepare(OWNER, "book", ["Amara Sample", "Bruno Example"]))
            amara = next(m for m in w.members() if m["name"] == "Amara Sample")
        self.assertIn([amara["id"]], plans)                                                   # THIS worker re-planned (the planner, same limits)
        self.assertIn("(Re-planned: the first fare was gone.)", card["read_back"])           # the new fare on the card
        self.assertEqual(w.agapi.seen["Amara Sample"], 2)
        held = {s["name"]: s for s in card["skipped"]}
        self.assertEqual(held["Bruno Example"]["kind"], "no_fare")                            # still none: said per worker
        self.assertIn("no fare left", held["Bruno Example"]["why"])


class LimitsAtBooking(unittest.TestCase):
    def test_a_stay_over_the_limit_is_held_then_booked_only_when_asked(self):
        with World(PricedAgAPI(per_night=19000)) as w, \
                mock.patch.object(G, "limit_for", lambda rules, m: {"hotel_night_eur": 150.0, "flight_return_eur": 1400.0}):
            out = run(GB.prepare(OWNER, "book", ["Amara Sample"]))
            self.assertEqual(out["status"], "nothing")
            self.assertEqual(out["skipped"][0]["kind"], "over_at_booking")
            self.assertEqual(out["taps"][0]["label"], "Amara Sample — Hotel Alba (test): hotel €190/night > €150 limit — book anyway?")
            self.assertEqual([b for op, b in w.agapi.bodies], [])                             # never even asked for a read-back
            tap = out["taps"][0]["act"]
            card = run(GB.prepare(OWNER, tap["action"], tap["who"], over_ok=tap["over_ok"]))
        self.assertEqual(card["status"], "awaiting_yes")
        self.assertTrue(any("hotel €190/night > €150 limit" in l and l.startswith("⚠") for l in card["read_back"]))

    def test_flights_over_the_limit_too(self):
        self.assertEqual(GB.over_at_booking([{"kind": "flight", "_price": {"amount_minor": 90000, "currency": "EUR"}},
                                             {"kind": "flight", "_price": {"amount_minor": 70000, "currency": "EUR"}}],
                                            {"flight_return_eur": 1400.0}), "flights €1,600 > €1,400 limit")
        self.assertIsNone(GB.over_at_booking([{"kind": "flight", "_price": {"amount_minor": 90000, "currency": "USD"}}],
                                             {"flight_return_eur": 1.0}))                       # never a guess across currencies


class SwapFliesTheNewcomersOwnFlights(unittest.TestCase):
    def test_the_body_carries_his_flights(self):
        with World() as w:
            card = run(GB.prepare(OWNER, "book"))
            run(w.tap(card["read_back_id"]))
            out = run(GB.prepare(OWNER, "swap", ["Bruno Example"], "Zoe Newhire", newcomer={"city": "London", "grade": "worker"}))
            self.assertEqual(out["status"], "needs_vault")
            w.fill(next(m for m in w.members() if m["name"] == "Zoe Newhire"), 19)
            w.agapi.bodies.clear()
            sw = run(GB.prepare(OWNER, "swap", ["Bruno Example"], "Zoe Newhire"))
        self.assertEqual(sw["status"], "awaiting_yes")
        body = next(b for op, b in w.agapi.bodies if op == "group.swap")
        fl = body["flights"]
        self.assertEqual([f["kind"] for f in fl], ["flight", "flight"])
        self.assertTrue(fl[0]["ref"].startswith("off_London_Madrid_") and fl[1]["ref"].startswith("off_Madrid_London_"))   # from HIS home city, out and back
        self.assertTrue(all("planned_price" in f for f in fl))                                # as planned (CR 164)
        self.assertFalse(any(k.startswith("_") for f in fl for k in f))                      # Sasha's notes never sent


if __name__ == "__main__":
    unittest.main()
