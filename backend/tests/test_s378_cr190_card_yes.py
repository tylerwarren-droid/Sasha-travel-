"""Sasha 378 · CR 190's Sasha half — ONE WhatsApp "yes" approves ONE CARD. NO PATCHES.

Found (Sasha 376, row 1906): on WhatsApp a card of several people booked only its first — each item asked approvals.in_app_tap with the
SAME message id, and AgAPI keeps a message id once. ONE source now: AgAPI's approvals.in_app_tap {read_backs, session} (kanoe_contract
1.84.0), the session signed over the card's sha256 (vendored vector kanoe_contract/vectors/whatsapp_card.json); one approval per
read-back comes back, each checked by AgAPI on its own (refused ones with AgAPI's why; one already done is a state, never "failed").
S2's in-app tap and a one-person card keep the single tap.

    cd backend && python -m unittest tests.test_s378_cr190_card_yes -v
"""
from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import os
import pathlib
import time
import unittest
from unittest import mock

import kanoe_contract as KC
from agapi import venue_submit as VS
from booking_signer import group_book as GB

run = asyncio.run
BACKEND = pathlib.Path(__file__).resolve().parents[1]
VECTOR = json.loads((BACKEND / "kanoe_contract" / "vectors" / "whatsapp_card.json").read_text())["vectors"][0]
ACCT = "00000000-0000-4000-8000-000000000190"
WA = {"wa_id": "15005550375", "message_id": "SM190card"}   # the fictional +1 500 555 0375


class TheVector(unittest.TestCase):
    def test_vendored_byte_identical(self):
        v = json.loads((BACKEND / "kanoe_contract" / "VENDORED.json").read_text())
        self.assertEqual((KC.CONTRACT_VERSION, v["version"]), ("1.84.0", "1.84.0"))
        for name, sha in v["vectors"].items():
            self.assertEqual(hashlib.sha256((BACKEND / "kanoe_contract" / name).read_bytes()).hexdigest(), sha, name)

    def test_the_card_signs_as_agapi_checks(self):
        self.assertEqual(VS.card_canonical(VECTOR["read_backs"]), VECTOR["canonical"])
        self.assertEqual(VS.card_sha256(list(reversed(VECTOR["read_backs"]))), VECTOR["card_sha256"])   # the card's order: no matter
        with mock.patch.dict(os.environ, {"SASHA_AGAPI_TAP_SECRET": VECTOR["secret"]}):
            s = VS.whatsapp_card_session(VECTOR["read_backs"], wa={"wa_id": VECTOR["wa_id"], "message_id": VECTOR["message_id"]},
                                         t=VECTOR["t"], nonce=VECTOR["nonce"])
        self.assertEqual(s["signature"], VECTOR["signature"])
        self.assertEqual((s["kind"], s["wa_id"], s["message_id"]), ("whatsapp", VECTOR["wa_id"], VECTOR["message_id"]))


class FakeAgAPI:
    """approvals.in_app_tap as AgAPI answers it (CR 190): a card's read-backs, each on its own; a message id used ONCE."""

    def __init__(self, refuse=None):
        self.calls, self.used, self.refuse = [], set(), dict(refuse or {})

    async def __call__(self, op, body, approval=None, account=None):
        self.calls.append((op, json.loads(json.dumps(body))))
        if op == KC.OP.USERS_REGISTER:
            return {"ok": True, "result": {"end_user_id": "eu_190"}}
        if op == KC.OP.APPROVALS_IN_APP_TAP:
            mid = body["session"]["message_id"]
            if mid in self.used:
                return {"ok": False, "error": {"code": KC.ERR.APPROVAL_CONSUMED, "message": "that message was already used for a yes"}}
            self.used.add(mid)
            rbs = body.get("read_backs") or [{"read_back_id": body["read_back_id"], "read_back_sha256": body["read_back_sha256"]}]
            ok = [x for x in rbs if x["read_back_id"] not in self.refuse]
            return {"ok": True, "result": {"method": "whatsapp", "say": f"Approved {len(ok)} of {len(rbs)} on this card.",
                                           "approvals": [{"read_back_id": x["read_back_id"], "approval_id": "apv_" + x["read_back_id"][-4:],
                                                          "operation": "group.book", "say": "ok"} for x in ok],
                                           "refused": [{"read_back_id": k, "code": c, "why": w} for k, (c, w) in self.refuse.items()
                                                       if any(x["read_back_id"] == k for x in rbs)]}}
        return {"ok": False, "error": {"code": KC.ERR.UNKNOWN_OPERATION, "message": op}}

    def taps(self):
        return [b for op, b in self.calls if op == KC.OP.APPROVALS_IN_APP_TAP]


def items(n):
    return [{"name": f"Person {i}", "read_back_id": f"rbk_190_{i:04d}", "sha": f"{i:x}" * 64, "member": f"m{i}", "op": KC.OP.GROUP_BOOK,
             "body": {"end_user": "eu_190"}, "idem": f"k{i}", "lines": [f"Person {i}"]} for i in range(n)]


class World:
    def __init__(self, test, fake):
        self.acted = []
        test.addCleanup(lambda: [p.stop() for p in self.p])

        async def act_one(account, it, said, mv, members, done, failed, reasked=None, apv=None):
            self.acted.append((it["name"], apv))
            done.append({"name": it["name"], "state": "booked", "parts": []})

        class Store:
            async def movement(self, account, mid=None):
                return {"id": "mv190", "rules": {}}

            async def members(self, mid):
                return [{"id": f"m{i}", "name": f"Person {i}"} for i in range(9)]
        self.p = [mock.patch.object(VS, "CALL", fake), mock.patch.object(GB, "_act_one", act_one),
                  mock.patch.object(GB, "reconcile", mock.AsyncMock()), mock.patch("booking_signer.groups.store", lambda: Store()),
                  mock.patch.object(GB, "finish", mock.AsyncMock(side_effect=lambda a, m, done, failed, **k: {"say": f"{len(done)} booked"})),
                  mock.patch.dict(os.environ, {"SASHA_AGAPI_TAP_SECRET": "test-secret-190"})]
        for p in self.p:
            p.start()

    def confirm(self, its, wa=WA):
        cid = "grp_" + "c" * 20
        GB._CARDS[cid] = {"account": ACCT, "action": "book", "items": its, "at": time.time(), "movement_id": "mv190"}
        tok = VS.WA.set(dict(wa)) if wa is not None else None
        try:
            return run(GB.confirm(ACCT, cid, "group_yes", "sí"))
        finally:
            if tok is not None:
                VS.WA.reset(tok)


class OneYesOneCard(unittest.TestCase):
    def test_a_four_person_card_is_one_tap_with_every_read_back(self):
        fake = FakeAgAPI()
        w = World(self, fake)
        out = w.confirm(items(4))
        self.assertEqual(len(fake.taps()), 1)                                                 # ONE approvals.in_app_tap …
        tap = fake.taps()[0]
        self.assertEqual(sorted(x["read_back_id"] for x in tap["read_backs"]), [f"rbk_190_{i:04d}" for i in range(4)])
        self.assertNotIn("read_back_id", tap)                                                 # … for the card, never one per item
        self.assertEqual(tap["session"]["message_id"], "SM190card")
        self.assertEqual(sorted(w.acted), [(f"Person {i}", "apv_" + f"rbk_190_{i:04d}"[-4:]) for i in range(4)])   # each its OWN approval
        self.assertEqual(out["say"], "4 booked")

    def test_a_refused_read_back_is_said_with_agapis_why_and_one_done_is_a_state(self):
        fake = FakeAgAPI(refuse={"rbk_190_0001": ("approval_expired", "That read-back expired; it was read back again."),
                                 "rbk_190_0002": (KC.ERR.ALREADY_COMPLETED, "already done")})
        w = World(self, fake)
        out = w.confirm(items(3))
        self.assertEqual([n for n, _ in w.acted], ["Person 0"])                               # only the approved one is acted
        self.assertEqual([(f["name"], f["why"]) for f in out["failed"]], [("Person 1", "That read-back expired; it was read back again.")])
        self.assertIn({"name": "Person 2", "state": "booked", "parts": []}, out["done"])       # already done: a STATE, never "failed"

    def test_the_same_message_again_is_refused_nothing_acted(self):
        fake = FakeAgAPI()
        w = World(self, fake)
        w.confirm(items(2))
        w.acted.clear()
        out = w.confirm(items(2))
        self.assertEqual(w.acted, [])
        self.assertEqual({f["code"] for f in out["failed"]}, {"approval_refused"})

    def test_s2_and_a_one_person_card_keep_the_single_tap(self):
        self.assertIsNone(run(GB._card_approvals(ACCT, items(3), [], [])))                    # not on WhatsApp
        tok = VS.WA.set(dict(WA))
        try:
            self.assertIsNone(run(GB._card_approvals(ACCT, items(1), [], [])))                # one read-back: the single tap
            t2 = VS.TAP.set({"kind": "supabase", "token": "x"})
            try:
                self.assertIsNone(run(GB._card_approvals(ACCT, items(3), [], [])))            # in the app: in_app_tap, per read-back
            finally:
                VS.TAP.reset(t2)
        finally:
            VS.WA.reset(tok)


class TheRatchet(unittest.TestCase):
    def test_the_card_is_approved_before_any_act_and_never_per_item_on_whatsapp(self):
        src = inspect.getsource(GB.confirm)
        self.assertLess(src.index("_card_approvals("), src.index("_act_one("))
        self.assertIn("apv=card_apv.get(", src)
        self.assertIn("apv = apv or await _approval(", inspect.getsource(GB._act_one))
        self.assertIn('{"read_backs": rbs, "session": sess}', inspect.getsource(VS.whatsapp_card_tap))


if __name__ == "__main__":
    unittest.main()
