"""Sasha 337 · planned_price on every group.book item (CR 164's ask) — docs/sasha/S-337-planned-price.md.
    cd backend && python -m unittest tests.test_s337_planned_price -v
"""
from __future__ import annotations

import asyncio
import inspect
import unittest
from unittest import mock

from booking_signer import group_book as GB
from tests import test_s334 as W334

run = asyncio.run
OWNER = W334.OWNER


def _minor(x):
    return int(round(float(x) * 100))


class EveryItemCarriesIt(unittest.TestCase):
    def _sent(self, w):
        sent = []
        real = GB.CALL

        async def spy(op, body, approval=None):
            if op == "group.book" and not approval:
                sent.append(body)
            return await real(op, body, approval)
        return sent, mock.patch.object(GB, "CALL", spy)

    def test_from_the_workers_one_trip(self):
        with W334.World() as w:
            sent, p = self._sent(w)
            with p:
                run(GB.prepare(OWNER, "book"))
            self.assertEqual(len(sent), 19)                                                    # every bookable worker (Rania: over limit)
            by_key = {m["id"]: m for m in w.members()}
            for body in sent:
                m = by_key[body["worker"]["key"]]
                rows = [r for r in w.trips[m["trip_id"]] if r["state"] in ("suggested", "chosen")]
                flights = {str(r["day"])[:10]: r for r in rows if r["kind"] == "flight"}
                stay = next(r for r in rows if r["kind"] == "stay")
                fl = [i for i in body["items"] if i["kind"] == "flight"]
                self.assertEqual(len(fl), 2)
                for item, day in zip(fl, (m["out_date"], m["back_date"])):
                    row = flights[str(day)[:10]]
                    self.assertEqual(item["planned_price"], {"amount_minor": _minor(row["price_amount"]), "currency": "EUR"}, m["name"])
                st = next(i for i in body["items"] if i["kind"] == "stay")
                self.assertEqual(st["planned_price"], {"amount_minor": _minor(stay["price_amount"]), "currency": "EUR"}, m["name"])
                self.assertTrue(all("planned_price" in i for i in body["items"]), m["name"])   # EVERY item carries it

    def test_read_at_prepare_time_never_a_copy(self):
        with W334.World() as w:
            amara = next(m for m in w.members() if m["name"] == "Amara Sample")
            out = next(r for r in w.trips[amara["trip_id"]] if r["kind"] == "flight" and str(r["day"])[:10] == str(amara["out_date"])[:10])
            sent, p = self._sent(w)
            with p:
                run(GB.prepare(OWNER, "book", ["Amara Sample"]))
                out["price_amount"] = 333.33                                                   # the trip row changes …
                run(GB.prepare(OWNER, "book", ["Amara Sample"]))
            self.assertNotEqual(sent[0]["items"][0]["planned_price"], sent[1]["items"][0]["planned_price"])
            self.assertEqual(sent[1]["items"][0]["planned_price"], {"amount_minor": 33333, "currency": "EUR"})   # … the next prepare says so

    def test_nothing_invented(self):
        self.assertIsNone(GB._minor({"price_amount": None}))
        self.assertIsNone(GB._minor(None))
        self.assertEqual(GB._minor({"price_amount": 120.5, "price_currency": "eur"}), {"amount_minor": 12050, "currency": "EUR"})
        src = inspect.getsource(GB._planned)
        self.assertIn("G._items(", src)                                                        # the ONE trip …
        for copy in ("_CARDS", "cache", "store().", "members("):                               # … never a stored copy
            self.assertNotIn(copy, src)


if __name__ == "__main__":
    unittest.main()
