"""Sasha 381k · TWO GATE RUNS NEVER SHARE A TEST IDENTITY (scripts/gate_identity). Found by 6da7a18b's two builds (55068c85 + ccb3af9a,
row 1998): both voice loops linked the same fixed WhatsApp numbers at the same minute; a link removes the channel already on that
number, so each run took the other's mobile (hold_booking → mobile_needed).

    cd backend && python -m unittest tests.test_s381k_gate_runs_apart -v
"""
from __future__ import annotations

import asyncio
import inspect
import pathlib
import unittest
from datetime import datetime, timezone

import phonenumbers

from booking_signer import guest_whatsapp as GW
from scripts import gate_identity as GI

run = asyncio.run
BACKEND = pathlib.Path(__file__).resolve().parents[1]


class Store(GW.MemoryGuestStore):
    """The real store's rule (PostgresGuestStore.link): one channel per number, across accounts — a link removes it from anyone else."""

    async def link(self, row: dict) -> None:
        for k in [k for k, c in self.channels.items() if c["account_id"] == row["account_id"] or k == row["wa_id_sha256"]]:
            del self.channels[k]
        self.channels[row["wa_id_sha256"]] = dict(row)


async def a_run(store: Store, run_id: str, checks: int, fixed: bool = False) -> list:
    """One voice-loop run's linking, as the suite does it: its own guest per check, the number from THIS run."""
    guests = []
    for n in range(1, checks + 1):
        if fixed:
            number = f"+3461{n:07d}"   # the old way
        else:
            async def taken(num: str) -> bool:
                return await store.channel_for(GW.wa_key(num)) is not None
            number = await _run_mobile(run_id, n, taken)
        a = f"{run_id}-guest-{n}"
        await store.link({"account_id": a, "wa_id_sha256": GW.wa_key(number), "number_e164": number,
                          "linked_at": datetime.now(timezone.utc)})
        guests.append(a)
        await asyncio.sleep(0)   # the other run's link can land between any two
    return guests


async def _run_mobile(run_id: str, n: int, taken) -> str:
    for attempt in range(20):
        number = GI.mobile_for(run_id, n, attempt)
        if not await taken(number):
            return number
    raise RuntimeError("none free")


class TwoRunsInTheSameMinute(unittest.TestCase):
    def test_each_keeps_its_own_mobiles(self):
        store = Store()

        async def both():
            return await asyncio.gather(a_run(store, "dep_record", 15), a_run(store, "dep_push", 15))
        ga, gb = run(both())
        for g in ga + gb:
            self.assertIsNotNone(run(store.channel_of_account(g)), g)                # every guest still has its mobile

    def test_the_old_fixed_numbers_collided(self):
        store = Store()

        async def both():
            return await asyncio.gather(a_run(store, "dep_record", 15, fixed=True), a_run(store, "dep_push", 15, fixed=True))
        ga, gb = run(both())
        lost = [g for g in ga + gb if run(store.channel_of_account(g)) is None]
        self.assertTrue(lost)                                                          # what 55068c85 + ccb3af9a hit

    def test_a_number_linked_to_anyone_is_never_taken(self):
        store = Store()
        first = GI.mobile_for("dep_x", 1)
        run(store.link({"account_id": "a-real-person", "wa_id_sha256": GW.wa_key(first), "number_e164": first}))

        async def taken(num):
            return await store.channel_for(GW.wa_key(num)) is not None
        got = run(_run_mobile("dep_x", 1, taken))
        self.assertNotEqual(got, first)
        self.assertIsNotNone(run(store.channel_of_account("a-real-person")))

    def test_numbers_are_a_suppliers_and_per_run(self):
        a = [GI.mobile_for("dep_a", n) for n in range(1, 16)]
        b = [GI.mobile_for("dep_b", n) for n in range(1, 16)]
        self.assertEqual(len(set(a + b)), 30)
        self.assertTrue(all(phonenumbers.is_valid_number(phonenumbers.parse(x)) for x in a + b))

    def test_the_suite_uses_it(self):
        from scripts import voice_loop_suite as VL
        src = inspect.getsource(VL.one)
        self.assertIn("GI.run_mobile(n, _taken)", src)
        self.assertNotIn('f"+3461{n:07d}"', src)
        self.assertIn("RAILWAY_DEPLOYMENT_ID", inspect.getsource(GI))


if __name__ == "__main__":
    unittest.main()
