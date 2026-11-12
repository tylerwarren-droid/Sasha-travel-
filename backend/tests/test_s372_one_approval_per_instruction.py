"""Sasha 372 · ONE approval per instruction — every mandate's proof is keyed by the INSTRUCTION (the S2 turn / the page's tap / the WhatsApp
message id), never the conversation. NO PATCHES.

Found (row 1891): the in-app proof's id was the session id, and AgAPI takes a proof once (mandates._verify "mandate_in_app:<sha(session)>") —
a SECOND instruction in the same conversation was refused (approval_untrusted_origin), live 3× on 12 Nov.

ONE source: the instruction's own id (agapi.v0.Ctx.turn — every turn and tap builds its own Ctx; WhatsApp: the message_id), signed into the
proof. AgAPI's half (CR 187, written in mailbox row 1892): approvals.mandate proof.instruction_id, signed as the in_app id, once.
ONE proof form (Tyler, 12 Nov): no today's-form fallback and no contract detection — Sasha 372 deploys TOGETHER with CR 187, never before.

    cd backend && python -m unittest tests.test_s372_one_approval_per_instruction -v
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import os
import pathlib
import unittest
from unittest import mock

from agapi import v0 as API
from booking_signer import agapi_mandate as AM, groups as G, mandate as M
from tests import test_s365_mandate as T365, test_s367_mandate_at_agapi as T367

run = asyncio.run
ROOT = pathlib.Path(__file__).resolve().parents[2]
OWNER = T367.OWNER
SECRET = T367.SECRET


def _say(w, words, session, dest="London", start="2026-12-15", end="2026-12-17", roles=("executives",)):
    async def go():
        ctx = API.Ctx(account=OWNER, user_said=words, surface="s2", session=session)
        r = await API.call(ctx, "group_select", {"change": "new", "destination": dest, "starts_on": start, "ends_on": end, "roles": list(roles)})
        await M.finished(OWNER)
        return ctx, r
    return run(go())


class TheInstructionIsTheId(unittest.TestCase):
    def test_every_turn_has_its_own_id_and_the_proof_carries_it(self):
        a, b = API.Ctx(account=OWNER, session="conv-1"), API.Ctx(account=OWNER, session="conv-1")
        self.assertNotEqual(a.turn, b.turn)                                                   # two instructions, one conversation: two ids
        pa, pb = AM.proof_from(a), AM.proof_from(b)
        self.assertEqual((pa["session_id"], pb["session_id"]), ("conv-1", "conv-1"))
        self.assertEqual((pa["instruction_id"], pb["instruction_id"]), (a.turn, b.turn))
        wa = mock.Mock(via="wa")
        from agapi import venue_submit as VS
        tok = VS.WA.set({"wa_id": "34611000000", "message_id": "SM9"})
        try:
            self.assertEqual(AM.proof_from(wa), {"kind": "whatsapp", "wa_id": "34611000000", "message_id": "SM9"})   # WhatsApp: the message
        finally:
            VS.WA.reset(tok)

    def test_the_instruction_is_what_is_signed(self):
        proof = {"kind": "in_app", "session_id": "conv-1", "instruction_id": "turn_abc"}
        with mock.patch.dict(os.environ, {"SASHA_AGAPI_TAP_SECRET": SECRET}):
            p = AM.sign(proof, OWNER, "ab" * 32, t=1700000000, nonce="n" * 16)
            none = AM.sign({"kind": "in_app", "session_id": "conv-1"}, OWNER, "ab" * 32, t=1700000000, nonce="n" * 16)
        want = hmac.new(SECRET.encode(), f"1700000000.{'n' * 16}.mandate.in_app.turn_abc.{OWNER}.{'ab' * 32}".encode(), hashlib.sha256).hexdigest()
        self.assertEqual(p["signature"], want)
        self.assertEqual((p["session_id"], p["instruction_id"]), ("conv-1", "turn_abc"))
        self.assertIsNone(none)                                                               # no instruction → nothing signed, never the session


class TwoInstructionsOneConversation(unittest.TestCase):
    def test_both_run_with_two_distinct_proofs(self):
        with T367.World() as w:
            _, r1 = _say(w, "Book all executives to London 15–17 December", "conv-372")
            _, r2 = _say(w, "Also book everyone to Lisbon 9–12 January", "conv-372", dest="Lisbon", start="2027-01-09", end="2027-01-12",
                         roles=("executives",))
        mand = [b for op, b in w.agapi.calls if op == "approvals.mandate"]
        self.assertEqual(len(mand), 2)                                                        # BOTH accepted
        self.assertEqual(len(w.agapi.mandates), 2)
        ids = [m["proof"]["instruction_id"] for m in mand]
        self.assertEqual(len(set(ids)), 2)                                                    # two distinct proofs …
        self.assertEqual({m["proof"]["session_id"] for m in mand}, {"conv-372"})              # … in ONE conversation

    def test_the_same_instruction_replayed_is_the_same_proof_accepted_once(self):
        with T367.World() as w:
            ctx = API.Ctx(account=OWNER, user_said="Book all executives", surface="s2", session="conv-r")
            proof = AM.proof_from(ctx)
            mv = run(G.store().movement(OWNER))
            members = run(G.store().members(mv["id"]))
            first = run(AM.register(OWNER, "Book all executives", mv, members, proof))
            again = run(AM.register(OWNER, "Book all executives", mv, members, dict(proof)))
        self.assertTrue(first.get("mandate_id"), first)
        self.assertEqual(again.get("code"), "approval_untrusted_origin")                     # the SAME instruction: accepted once
        self.assertEqual(len(w.agapi.mandates), 1)


class OneProofForm(unittest.TestCase):
    def test_no_fallback_and_no_detection(self):
        src = (ROOT / "backend" / "booking_signer" / "agapi_mandate.py").read_text()
        for gone in ("per_instruction", "takes_instruction", "openapi.json", "CONTRACT", 'ident, who = proof["session_id"]'):
            self.assertNotIn(gone, src, gone)

    def test_no_door_invents_a_session(self):
        routes = (ROOT / "backend" / "booking_signer" / "group_routes.py").read_text()
        self.assertNotIn('"session_id": "group-page-"', routes)
        self.assertIn('return {"kind": "in_app", "session_id": tap, "instruction_id": tap}', routes)


if __name__ == "__main__":
    unittest.main()
