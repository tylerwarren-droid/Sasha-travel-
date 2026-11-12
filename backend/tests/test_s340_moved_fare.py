"""Sasha 340 · on CR 166: a moved fare after the ONE yes is re-asked for THAT worker alone (the rest stay booked); limits are checked
against approval_required details.priced. Offline: 339's world and an AgAPI double that answers CR 166's contract.
    cd backend && python -m unittest tests.test_s340_moved_fare -v
"""
from __future__ import annotations

import asyncio
import inspect
import json
import unittest
from unittest import mock

from booking_signer import basket as BK, group_book as GB, groups as G
from tests import test_s339_book_all as T

run = asyncio.run
OWNER = T.OWNER


class CR166(T.PricedAgAPI):
    """approval_required carries `priced`; at the act a moved fare → approval_void · payload_changed with a FRESH read-back (once);
    an offer gone at the act → approval_void · payload_changed · reason offer_gone, no read-back."""

    def __init__(self, priced_per_night=None, moved=(), gone_at_act=(), **kw):
        super().__init__(**kw)
        self.priced_per_night, self.moved, self.gone_at_act, self.voided = priced_per_night, set(moved), set(gone_at_act), []

    def _key(self, op, body):
        return json.dumps({"op": op, **{k: v for k, v in body.items() if k != "end_user"}}, sort_keys=True)

    async def _do(self, op, body, approval):
        r = await super()._do(op, body, approval) if not (op == "group.book" and approval) else None
        if op == "group.book" and not approval:
            e = r.get("error") or {}
            if e.get("code") == "approval_required":
                pn = self.priced_per_night or self.per_night
                e["details"]["priced"] = [{"kind": i["kind"], "offer_id": i["ref"], "currency": "EUR",
                                           "amount_minor": 12000 if i["kind"] == "flight" else pn * i.get("nights", 1),
                                           **({"per_night_minor": pn} if i["kind"] == "stay" else {})} for i in body["items"]]
            return r
        if op == "group.book" and approval:
            name = f"{body['worker']['given_name']} {body['worker']['family_name']}"
            if name in self.gone_at_act and name not in self.voided:
                self.voided.append(name)
                return {"ok": False, "error": {"code": "approval_void", "message": "The fare changed after the yes, so nothing was booked.",
                                               "details": {"void_reason": "payload_changed", "reason": "offer_gone"}}}
            if name in self.moved and name not in self.voided:
                self.voided.append(name)
                new = self._id("rb")
                self.rbs[self._key(op, body)] = new   # the FRESH read-back: the next approval answers THIS one
                return {"ok": False, "error": {"code": "approval_void", "message": "The fare changed after the yes, so nothing was booked.",
                                               "details": {"void_reason": "payload_changed", "read_back_id": new, "read_back_sha256": "sha_" + new,
                                                           "read_back": {"lines": ["The fare moved since your yes: now EUR 125.00, was EUR 120.00 when you said yes.",
                                                                                   f"For {name}:", "Total EUR 545.00 — TEST."]},
                                                           "priced": [], "changed": [{"why": "price_rose"}]}}}
            return await super()._do(op, body, approval)
        return r


class World(T.World):
    pass


class MovedFareReaskedAlone(unittest.TestCase):
    def test_one_yes_books_the_rest_and_the_moved_one_gets_its_own_card(self):
        with World(CR166(moved={"Bruno Example"})) as w:
            card = run(GB.prepare(OWNER, "book"))
            out = run(GB.confirm(OWNER, card["read_back_id"], "group_yes", "Yes, go ahead."))
            self.assertEqual((len(out["done"]), out["failed"]), (18, []))                     # the rest stay booked
            self.assertEqual([x["name"] for x in out["reasked"]], ["Bruno Example"])          # THAT worker only
            re = out["reasked"][0]
            self.assertEqual(re["read_back"][0], "The fare moved since your yes: now EUR 125.00, was EUR 120.00 when you said yes.")
            self.assertIn("The fare moved for Bruno Example", out["say"])
            from app.agent.sasha import yes_buttons
            self.assertEqual([c["route"] for c in yes_buttons("group_book", re)["choices"]], ["group_yes", "group_no"])   # its own Yes
            waiting_before = [x["name"] for x in GB.waiting_cards(OWNER)]
            again = run(GB.confirm(OWNER, re["read_back_id"], "group_yes", "Yes, go ahead."))
            waiting_after = [x["name"] for x in GB.waiting_cards(OWNER)]
            rows = run(G.view(OWNER))["rows"]
            listed = {r["name"]: r["status"] for r in rows}
            inv = run(GB.invoice(OWNER, run(G.store().movement(OWNER))["id"]))
        self.assertEqual((len(again["done"]), again["failed"], again["reasked"]), (1, [], []))
        self.assertEqual(waiting_before, ["Bruno Example"])                                    # a reload finds THAT card
        self.assertEqual(waiting_after, [])
        self.assertEqual(sum(1 for s in listed.values() if s == "booked"), 19)               # the master list = AgAPI's record
        self.assertEqual(round(sum(r["price_eur"] for r in rows if r["status"] == "booked"), 2), float(inv["total"].strip("€").replace(",", "")))
        self.assertEqual(len(inv["lines"]), 19)

    def test_an_offer_gone_at_the_act_is_prepared_again_for_that_worker(self):
        with World(CR166(gone_at_act={"Amara Sample"})) as w:
            card = run(GB.prepare(OWNER, "book", ["Amara Sample", "Bruno Example"]))
            out = run(GB.confirm(OWNER, card["read_back_id"], "group_yes"))
        self.assertEqual([d["name"] for d in out["done"]], ["Bruno Example"])
        self.assertEqual([x["name"] for x in out["reasked"]], ["Amara Sample"])               # found again, its own card


class LimitsFromPriced(unittest.TestCase):
    def test_the_read_backs_own_price_decides_not_the_offer_or_a_sentence(self):
        agapi = CR166(per_night=9000, priced_per_night=19000)    # the offer says €90, the READ-BACK says €190
        with World(agapi), mock.patch.object(G, "limit_for", lambda rules, m: {"hotel_night_eur": 150.0, "flight_return_eur": 1400.0}):
            out = run(GB.prepare(OWNER, "book", ["Amara Sample"]))
        self.assertEqual(out["skipped"][0]["kind"], "over_at_booking")
        self.assertEqual(out["skipped"][0]["why"], "Hotel Alba (test): hotel €190/night > €150 limit")
        self.assertIsNone(GB.over_priced([{"kind": "stay", "offer_id": "s", "per_night_minor": 19000, "currency": "USD"}], {"hotel_night_eur": 1.0}))


class ThePatchIsGone(unittest.TestCase):
    def test_readers_take_objects_only(self):
        src = inspect.getsource(BK.snapshot_of)
        self.assertNotIn("isinstance(v, list)", src)                                          # 051 applied: no array reading
        self.assertFalse(hasattr(BK, "SNAP_OBJECT"))
        self.assertEqual(BK.snapshot_of(["x"]), {})


if __name__ == "__main__":
    unittest.main()
