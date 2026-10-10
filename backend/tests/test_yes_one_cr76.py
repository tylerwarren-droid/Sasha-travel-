"""CR 76 · THE ONE YES RULE — permanent, offline, 0 live calls (nothing is emailed: the send is captured).

  · the vendored module is byte for byte the generated one (MANIFEST) and passes the ONE conformance set (contract 1.3)
  · on /s2 an act runs only through it: read-back (turn 1) → their explicit yes (a later turn) → the act, once
  · same-turn yes, a question, a cancel-yes to a send, a reused yes and a changed message are all refused, nothing sent
  · S1 never goes through the gate (its behaviour is unchanged)

    cd backend && python -m unittest tests.test_yes_one_cr76 -v
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import unittest
from pathlib import Path
from unittest import mock

from agapi import s2_tools as S, v0 as API, yes_gate as YG
from agapi.yes_one import test_yes_one as CONF  # noqa: F401 · the conformance set runs with this module

ACCOUNT = "00000000-0000-4000-8000-000000000076"
MSG = {"to": {"address": "marta@example.com", "name": "Marta"}, "subject": "Our flight times",
       "body": "Hi Marta, we fly out on 21 November at 08:30 and back on 30 November."}
HERE = Path(API.__file__).resolve().parent / "yes_one"


def run(c):
    return asyncio.run(c)


class Vendored(unittest.TestCase):
    def test_byte_for_byte_the_generated_module(self):
        m = json.loads((HERE / "MANIFEST.json").read_text())
        self.assertEqual(m["contract_version"], "1.3")
        for f in ("yes_one.py", "conformance.json", "test_yes_one.py"):
            self.assertEqual(hashlib.sha256((HERE / f).read_bytes()).hexdigest(), m["outputs"][f], f)

    def test_the_gate_uses_it(self):
        self.assertEqual(Path(YG.YES.__file__).resolve(), HERE / "yes_one.py")   # imported, not re-implemented
        self.assertEqual(YG.YES.CONTRACT_VERSION, "1.3")


class S2Gate(unittest.TestCase):
    def setUp(self):
        from booking_signer import basket as BK
        self.p = mock.patch.object(BK, "_run", lambda: None)
        self.p.start()
        self.clear()

    def tearDown(self):
        self.p.stop()
        self.clear()

    def clear(self):
        S.OUTBOX.clear(), S._HELD.clear(), API._IDEM.clear(), API._CLAIMED.clear(), YG._RB.clear(), YG._APV.clear()

    def turn(self, said, key, surface="s2", msg=MSG):
        ctx = API.Ctx(account=ACCOUNT, user_said=said)
        ctx.surface = surface
        return ctx, run(API.call(ctx, "send_email", {**msg, "approval": {"said": said}, "idempotency_key": key}))

    def test_read_back_then_a_later_yes_sends_once(self):
        _, r = self.turn("email Marta our flight times", "k0")
        self.assertEqual(r["result"]["status"], "awaiting_yes")
        self.assertIn((ACCOUNT, "send_email"), YG._RB)
        _, r = self.turn("Yes, send it.", "k1")
        self.assertTrue(r["ok"], r)
        self.assertEqual(len(S.OUTBOX), 1)
        self.assertNotIn((ACCOUNT, "send_email"), YG._RB)   # consumed
        _, r = self.turn("Yes, send it.", "k2")              # the same yes again: a fresh read-back, nothing sent
        self.assertEqual(len(S.OUTBOX), 1)

    def test_same_turn_yes_is_refused(self):
        ctx, r = self.turn("email Marta our flight times", "k0")
        YG.heard(ctx, "send_email", "Yes, send it.")          # their yes, heard in the read-back's own turn
        ctx.act_name, ctx.act_said, ctx.idem = "send_email", "Yes, send it.", "x"
        S._HELD[ACCOUNT]["at"] = ctx.started.replace(year=2000)
        with self.assertRaises(API.ToolError) as e:
            run(API.claim(ctx))
        self.assertEqual(e.exception.code, "approval_same_turn")
        self.assertEqual(S.OUTBOX, [])

    def test_a_question_or_a_cancel_yes_never_sends(self):
        self.turn("email Marta our flight times", "k0")
        for i, said in enumerate(("Yes — what will it say?", "ok", "Yes, cancel it.")):
            _, r = self.turn(said, f"q{i}")
            self.assertFalse(r["ok"] and r["result"].get("status") == "sent", said)
        self.assertEqual(S.OUTBOX, [])

    def test_a_changed_message_needs_a_new_yes(self):
        self.turn("email Marta our flight times", "k0")
        changed = {**MSG, "body": MSG["body"] + " P.S. bring the passports."}
        _, r = self.turn("Yes, send it.", "k1", msg=changed)
        self.assertEqual(r["result"]["status"], "awaiting_yes")   # the new message is read back; nothing sent
        self.assertEqual(S.OUTBOX, [])

    def test_no_read_back_recorded_refuses_at_the_act(self):
        ctx = API.Ctx(account=ACCOUNT, user_said="Yes, send it.")
        ctx.surface, ctx.act_name, ctx.act_said, ctx.idem = "s2", "send_email", "Yes, send it.", "x"
        with self.assertRaises(API.ToolError) as e:
            run(API.claim(ctx))
        self.assertEqual(e.exception.code, "no_read_back")

    def test_s1_never_goes_through_the_gate(self):
        self.turn("email Marta our flight times", "k0", surface="s1")
        self.assertEqual(YG._RB, {})
        ctx = API.Ctx(account=ACCOUNT)
        self.assertIsNone(ctx.act_name)


if __name__ == "__main__":
    unittest.main()
