"""Sasha 381e · THE INSTRUCTION'S PROOF FOLLOWS THE DOOR THE TURN CAME THROUGH — on EVERY door that books. NO PATCHES.

Found by 381d's recording (row 1969): the voice avatar / REST chat (booking_signer.voice_turn) runs the WhatsApp brain, so its ctx.via is
"wa", but its turn is a signed-in in-app request, not a signed WhatsApp message. proof_from decided the door by ctx.via, took its WhatsApp
branch, found no message, and refused every voice booking ("I couldn't confirm the request came from you"). The door was decided in THREE
places: proof_from (by ctx.via), the approvals (by TAP / WA, in venue_submit, s2_tools and group_book), and the /group page (its own
_tap_proof). Now ONE reader, venue_submit.door(), of what each door's entry point records:
  · S2 and /next  — sasha.agent_turn:   VS.TAP ← session_of(request)          → in_app, THIS turn's id
  · voice / REST  — voice_turn._agent:  VS.TAP ← tap (session_of(request))    → in_app, THIS turn's id
  · /group page   — group_routes.group_act: VS.TAP ← session_of(request)      → in_app, THIS tap's id
  · WhatsApp      — inbound_phone.sms:  VS.WA ← the signed message            → whatsapp, its message id
  · none of these                                                              → no proof (nothing acts)

    cd backend && python -m unittest tests.test_s381e_every_door -v
"""
from __future__ import annotations

import asyncio
import inspect
import os
import pathlib
import re
import unittest
from unittest import mock

from agapi import v0 as API, venue_submit as VS
from booking_signer import agapi_mandate as AM

BACKEND = pathlib.Path(__file__).resolve().parents[1]
ACCT = "00000000-0000-4000-8000-0000000381e0"
run = asyncio.run


class EveryDoor(unittest.TestCase):
    """Each door's REAL entry point records its door; inside it, an instruction's proof is that door's — whatever ctx.via says."""

    def setUp(self):
        p = mock.patch.dict(os.environ, {"SASHA_AGAPI_TAP_SECRET": "s381e-secret"})
        p.start()
        self.addCleanup(p.stop)

    def proof_inside(self, via: str, turn: str = "turn_381e", session: str = "conv_381e"):
        return AM.proof_from(API.Ctx(account=ACCT, surface="s2", via=via, turn=turn, session=session))

    def test_voice_and_rest_a_signed_in_request_is_the_in_app_proof(self):
        """voice_turn._agent (the avatar and the REST chat): the request's session → in_app, though the brain speaks as WhatsApp."""
        from booking_signer import voice_turn as VT, wa_agent as WA
        seen = {}

        async def brain(ch, body, payload, st, out, now, button_text="", voice_in=False):
            seen["door"], seen["proof"] = VS.door(), self.proof_inside(via="wa")   # the WhatsApp brain's own ctx.via
            return "x"
        with mock.patch.object(WA, "agent_turn", brain), mock.patch.object(WA, "set_agent_state", lambda *a, **k: None):
            run(VT._agent(ACCT, "k" * 64, "book Taverna Sandbox", {}, __import__("datetime").datetime.now(), {"kind": "supabase", "token": "t"}))
        self.assertEqual(seen["door"], {"kind": "in_app"})
        self.assertEqual((seen["proof"]["kind"], seen["proof"]["instruction_id"]), ("in_app", "turn_381e"))
        self.assertIsNone(VS.TAP.get())                                                     # recorded for that turn only

    def test_s2_and_next_a_signed_in_request_is_the_in_app_proof(self):
        """sasha.agent_turn (S2 and /next): the door it records is the request's session (one reader for both surfaces)."""
        from app.agent import sasha as S
        src = inspect.getsource(S.agent_turn)
        self.assertIn("tap_session = _VS.session_of(request)", src)
        self.assertIn("VS.TAP.set(tap_session)", src)
        tok = VS.TAP.set({"kind": "supabase", "token": "t"})
        try:
            for via in ("page", "wa"):
                p = self.proof_inside(via=via)
                self.assertEqual((p["kind"], p["instruction_id"], p["session_id"]), ("in_app", "turn_381e", "conv_381e"), via)
        finally:
            VS.TAP.reset(tok)

    def test_whatsapp_a_signed_message_is_the_whatsapp_proof(self):
        """inbound_phone.sms records THIS message once Twilio's signature passed: its message id — on any surface the brain speaks as."""
        from booking_signer import inbound_phone as IP
        self.assertIn('VS.WA.set({"wa_id": sender, "message_id": sid})', inspect.getsource(IP))
        tok = VS.WA.set({"wa_id": "+34611381381", "message_id": "SM" + "e" * 32})
        try:
            for via in ("wa", "page"):
                self.assertEqual(self.proof_inside(via=via), {"kind": "whatsapp", "wa_id": "34611381381", "message_id": "SM" + "e" * 32}, via)
        finally:
            VS.WA.reset(tok)

    def test_the_group_page_a_signed_in_tap_is_the_in_app_proof(self):
        """group_routes.group_act (Book all on /group): its request's session → in_app, THIS tap's own id."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from booking_signer import group_outcome as GO, group_routes as GR
        seen = {}

        async def go(account, action, args):
            seen.update(args)
            return {"status": "started"}
        app = FastAPI()
        app.include_router(GR.router)
        with mock.patch.object(GO, "run", go), mock.patch.object(GR, "account_for", lambda r: ACCT):
            TestClient(app).post("/group/act", json={"action": "book"}, headers={"Authorization": "Bearer t"})
        self.assertEqual(seen["proof"]["kind"], "in_app")
        self.assertTrue(seen["proof"]["instruction_id"].startswith("tap_"))
        with mock.patch.object(GO, "run", go), mock.patch.object(GR, "account_for", lambda r: ACCT):
            seen.clear()
            TestClient(app).post("/group/act", json={"action": "book"})   # no session on the request: nothing to prove it by
        self.assertIsNone(seen["proof"])

    def test_no_door_recorded_no_proof(self):
        for via in ("page", "wa"):
            self.assertIsNone(self.proof_inside(via=via), via)


class TheRatchet(unittest.TestCase):
    def test_one_reader_never_ctx_via(self):
        self.assertNotIn("via", inspect.getsource(AM.proof_from).split('"""')[-1])        # its body: never how she speaks
        self.assertIn("VS.door()", inspect.getsource(AM.proof_from))
        bad = []
        for rel in ("agapi/venue_submit.py", "agapi/s2_tools.py", "booking_signer/group_book.py", "booking_signer/agapi_mandate.py"):
            src = (BACKEND / rel).read_text()
            for pat in (r"TAP\.get\(\) is not None or (VS\.)?WA\.get\(\)", r"if (VS\.)?TAP\.get\(\) is not None else (VS\.)?whatsapp_tap",
                        r"getattr\(ctx, \"via\""):
                bad += [f"{rel}: {pat}" for _ in re.finditer(pat, src)]
        self.assertEqual(bad, [])
        from booking_signer import group_routes as GR
        self.assertFalse(hasattr(GR, "_tap_proof"))                                        # the /group page's own proof: gone

    def test_every_entry_point_records_its_door(self):
        for rel, rec in (("app/agent/sasha.py", "VS.TAP.set(tap_session)"), ("booking_signer/voice_turn.py", "VS.TAP.set(tap)"),
                         ("booking_signer/group_routes.py", "VS.TAP.set(VS.session_of(request))"),
                         ("booking_signer/inbound_phone.py", 'VS.WA.set({"wa_id": sender, "message_id": sid})')):
            self.assertIn(rec, (BACKEND / rel).read_text(), rel)


if __name__ == "__main__":
    unittest.main()
