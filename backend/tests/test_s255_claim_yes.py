"""Sasha 255 · S2 item 16 — "Yes, send it." to a money-back read-back was answered "that wasn't a clear yes" in every EU scoreboard run
(found live: agapi-sandbox logged money.flight_check → sandbox.simulate_approval 409 with no new read-back). The read-back waiting for
the yes (_PEND, durable) was cleared only on success and belonged to no case: once AgAPI had it answered (AgAPI hands back the SAME
read-back for the same act — "approval_same_turn") or it had expired, it caught every later yes, forever. Now: a new case drops it;
any refusal but the words uses the approval AgAPI already holds while it's valid, else holds the act again — a fresh read-back, never a
refusal of a clear yes. "maybe later" is still not a yes.

    cd backend && python -m unittest tests.test_s255_claim_yes -v
"""
from __future__ import annotations

import asyncio
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

from agapi import agapi_route as AR, s2_fine_print as FP

ACCOUNT = "00000000-0000-4000-8000-000000000255"
KEY = f"{ACCOUNT}|file_flight_claim"


def run(c):
    return asyncio.run(c)


class Ctx:
    def __init__(self, said="", ago=5):
        self.account, self.user_said = ACCOUNT, said
        self.started = datetime.now(timezone.utc) + timedelta(seconds=ago)   # ago > 0: a LATER turn than any read-back made now


class SandboxClaims:
    """AgAPI's sandbox as observed on 13 Oct: one read-back per act (held again → the same id); answered once; its approval valid 15 min."""

    def __init__(self, approval_valid=True):
        self.calls, self.answered, self.filed, self.approval_valid = [], set(), [], approval_valid

    def rb(self, body):
        return "rb_" + body["case_id"]

    async def __call__(self, op, body, approval=None):
        self.calls.append(op)
        if op == "users.register":
            return {"ok": True, "result": {"end_user_id": "usr_1"}}
        if op == "money.flight_check":   # every check is a NEW case on AgAPI
            self.cases = getattr(self, "cases", 0) + 1
            return {"ok": True, "result": {"case_id": f"mny_{self.cases}", "say": "You may be owed EUR 250. Want me to claim it?", "verdict": "yes",
                                           "amount": None, "rules": []}}
        if op == "money.flight_claim":
            if not approval:
                return {"ok": False, "error": {"code": "approval_required", "details": {"read_back_id": self.rb(body), "read_back": {"lines": [
                    f"File a compensation claim with Example Air ({body['case_id']})."]}}}}
            self.filed.append(body["case_id"])
            return {"ok": True, "result": {"state": "filed", "say": "Filed with Example Air."}}
        if op == "sandbox.simulate_approval":
            if "yes" not in body["said"].lower():
                return {"ok": False, "error": {"code": "no_explicit_yes", "message": "The words given are not an explicit yes."}}
            if body["read_back_id"] in self.answered:
                return {"ok": False, "error": {"code": "approval_same_turn", "message": "That read-back has already been answered; hold again for a fresh one."}}
            self.answered.add(body["read_back_id"])
            return {"ok": True, "result": {"approval_id": "apv_" + body["read_back_id"]}}
        if op == "approvals.status":
            ok = body["read_back_id"] in self.answered and self.approval_valid
            return {"ok": True, "result": {"read_back_id": body["read_back_id"], "approval": {"approval_id": "apv_" + body["read_back_id"],
                                                                                             "state": "valid" if ok else "expired"} if body["read_back_id"] in self.answered else None}}
        raise AssertionError(op)


class Base(unittest.TestCase):
    def setUp(self):
        self.api = SandboxClaims()
        for p in (mock.patch.object(FP, "CALL", self.api), mock.patch.dict(FP._PEND, {}, clear=True)):
            p.start()
            self.addCleanup(p.stop)

    def claim(self, said, case="mny_1", ago=5):
        with AR.using("sandbox"):
            return run(FP._with_yes(Ctx(said, ago), KEY, "money.flight_claim", {"end_user": "usr_1", "case_id": case}))


class TheYesIsNeverRefusedForAStaleReadBack(Base):
    def test_a_clean_claim_read_back_then_yes(self):
        r = self.claim("Can I get money back?", ago=-1)
        self.assertEqual(r["result"]["status"], "awaiting_yes")
        self.assertEqual(self.claim("Yes, send it.")["result"]["state"], "filed")

    def test_an_answered_read_back_uses_the_approval_already_given(self):
        # EU's runs: an earlier conversation answered this read-back but never filed — the waiting read-back was stuck on it
        self.api.answered.add("rb_mny_1")
        FP._PEND[KEY] = {"read_back_id": "rb_mny_1", "at": 0, "case": "mny_1"}
        r = self.claim("Yes, send it.")
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["result"]["state"], "filed")
        self.assertNotIn(KEY, FP._PEND)

    def test_an_answered_read_back_whose_approval_expired_is_held_again_never_refused(self):
        self.api.answered.add("rb_mny_1")
        self.api.approval_valid = False
        FP._PEND[KEY] = {"read_back_id": "rb_mny_1", "at": 0, "case": "mny_1"}
        r = self.claim("Yes, send it.")
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["result"]["status"], "awaiting_yes")
        self.assertIn("can't take a yes any more", r["result"]["ask"])
        self.assertNotIn("clear yes", str(r))
        self.assertEqual(self.api.filed, [])   # nothing sent without a yes to a read-back they heard

    def test_a_read_back_from_an_earlier_case_never_catches_this_cases_yes(self):
        FP._PEND[KEY] = {"read_back_id": "rb_mny_old", "at": 0, "case": "mny_old"}
        r = self.claim("Yes, send it.", case="mny_new")
        self.assertEqual(r["result"]["status"], "awaiting_yes")      # this case's read-back first
        self.assertEqual(FP._PEND[KEY]["case"], "mny_new")
        self.assertNotIn("sandbox.simulate_approval", self.api.calls)
        self.assertEqual(self.claim("Yes, send it.", case="mny_new")["result"]["state"], "filed")
        self.assertEqual(self.api.filed, ["mny_new"])

    def test_words_that_arent_a_yes_are_still_not_a_yes(self):
        self.claim("Can I get money back?", ago=-1)
        r = self.claim("maybe later")
        self.assertEqual(r["error"]["code"], "no_explicit_yes")
        self.assertEqual(self.api.filed, [])


class TheModelChecksAgainInTheTurnOfTheYes(Base):
    """Found live (agapi-sandbox log of EU's run and of this proof): in the yes turn the model runs flight_money_back again, then
    file_flight_claim. Same facts → the same case, so their yes answers the read-back they heard; new facts → a new read-back."""

    FLIGHT = {"airline": "EX", "number": "456", "date": "2026-10-12", "from": "MAD", "to": "LIS", "what": "delayed", "arrival_delay_minutes": 240,
              "booking_reference": "EXTEST", "passengers": ["Erika Mustermann"]}

    def setUp(self):
        super().setUp()
        for p in (mock.patch.dict(FP._MONEY, {}, clear=True), mock.patch.dict(FP._MONEY_FACTS, {}, clear=True), mock.patch.dict(FP._USERS, {}, clear=True),
                  mock.patch.object(FP, "_hydrate", mock.AsyncMock()), mock.patch.object(FP, "_persist", mock.AsyncMock()),
                  mock.patch.object(FP, "target", mock.AsyncMock(return_value="sandbox"))):
            p.start()
            self.addCleanup(p.stop)

    def tool(self, said, name, args, ago=5):
        return run(FP.run_tool(Ctx(said, ago), name, args))

    def test_the_same_facts_checked_again_keep_the_case_and_the_yes_files(self):
        self.tool("Can I get money back?", "flight_money_back", self.FLIGHT, ago=-1)
        self.assertEqual(self.tool("Can I get money back?", "file_flight_claim", {}, ago=-1)["result"]["status"], "awaiting_yes")
        self.tool("Yes, send it.", "flight_money_back", self.FLIGHT)                 # the model checks again in the yes turn
        r = self.tool("Yes, send it.", "file_flight_claim", {})
        self.assertEqual(r["result"]["status"], "filed", r)
        self.assertEqual(self.api.filed, ["mny_1"])

    def test_new_facts_are_a_new_case_with_its_own_read_back(self):
        self.tool("Can I get money back?", "flight_money_back", self.FLIGHT, ago=-1)
        self.tool("Can I get money back?", "file_flight_claim", {}, ago=-1)
        self.tool("It was EX 457.", "flight_money_back", {**self.FLIGHT, "number": "457"})
        r = self.tool("Yes, send it.", "file_flight_claim", {})
        self.assertEqual(r["result"]["status"], "awaiting_yes")                      # never filed on a read-back they didn't hear
        self.assertEqual(self.api.filed, [])


class TheCaseIsKept(Base):
    def test_the_waiting_read_backs_case_survives_a_restart(self):
        self.claim("Can I get money back?", ago=-1)
        snap = FP._snap(ACCOUNT)["fp_pending"]
        self.assertEqual(snap["file_flight_claim"]["case"], "mny_1")
        FP._PEND.clear()   # a restart: this process lost it; s2_memory kept it
        from agapi import s2_memory as M
        with mock.patch.object(M, "kinds", mock.AsyncMock(return_value={"fp_pending": snap})):
            run(FP._hydrate(ACCOUNT))
        self.assertEqual(FP._PEND[KEY]["case"], "mny_1")


if __name__ == "__main__":
    unittest.main()
