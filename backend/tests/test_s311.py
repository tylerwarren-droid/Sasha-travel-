"""Sasha 311 · the number confirmation never loops: the bare code works (any case, any wrapping), "confirmed" only when AgAPI's record
READ BACK says verified, the exchange is in her conversation, and his very next yes sends the held request by code.

    cd backend && python -m unittest tests.test_s311 -v
"""
from __future__ import annotations

import asyncio
import pathlib
import unittest
from datetime import datetime, timezone
from unittest import mock

from agapi import venue_submit as VS, venues as VN
from app.agent import voice as V
from booking_signer import guest_whatsapp as GW

ROOT = pathlib.Path(__file__).resolve().parents[1]
ACCT = "11111111-1111-4111-8111-311311311311"
NUM = "+34600000311"


def run(c):
    return asyncio.run(c)


class Store(GW.MemoryGuestStore):
    pass


class TheCode(unittest.TestCase):
    def setUp(self):
        self.store = Store()
        now = GW.NOW()
        run(self.store.put_code({"code": "119218", "account_id": ACCT, "consent_at": now, "consent_wording_version": "v2",
                                 "consent_text_sha256": "x", "created_at": now}))
        self.ch = {"account_id": ACCT, "wa_id_sha256": GW.wa_key(NUM), "number_e164": NUM}
        VN._HELD[ACCT] = {"venue": "DiverXO", "summary": "Fri 13 Nov 21:00, 2 people", "at": datetime.now(timezone.utc)}
        self.p = [mock.patch.object(GW, "STORE", self.store)]
        for p in self.p:
            p.start()

    def tearDown(self):
        for p in self.p:
            p.stop()
        VN._HELD.pop(ACCT, None)

    def confirm(self, body, verified=True, read_back=True):
        with mock.patch.object(VS, "confirm_whatsapp", mock.AsyncMock(return_value={"ok": True, "state": "verified"} if verified else
                                                                       {"ok": False, "error": {"code": "destination_code_invalid"}})) as c, \
                mock.patch.object(VS, "whatsapp_verified", mock.AsyncMock(return_value=read_back)):
            said = run(GW.confirmed_by_code(self.ch, NUM, {"Body": body, "MessageSid": "SM311"}))
        return said, c

    def test_the_bare_code_any_case_any_wrapping(self):   # found live: "119218" refused ("send the whole message")
        for body in ("119218", "Kanoe Link 119218", "kanoe link 119218", "code: 119218.", " 119218 "):
            self.setUp()
            said, c = self.confirm(body)
            self.assertEqual(said, V.number_confirmed_line("DiverXO"), body)
            c.assert_called_once()
            self.tearDown()

    def test_confirmed_only_when_agapis_record_reads_verified(self):
        said, _ = self.confirm("119218", verified=True, read_back=False)
        self.assertEqual(said, V.NUMBER_NOT_CONFIRMED)
        self.assertNotIn("number_confirmed_at", VN._HELD[ACCT])

    def test_the_exchange_is_in_her_conversation_and_the_request_is_marked(self):   # found live: said OUTSIDE her history
        said, _ = self.confirm("119218")
        h = run(self.store.get_state(self.ch["wa_id_sha256"]))["history"]
        self.assertEqual(h[-2:], [{"role": "user", "content": "119218"}, {"role": "assistant", "content": said}])
        self.assertIn("number_confirmed_at", VN._HELD[ACCT])

    def test_another_accounts_code_is_never_consumed(self):
        said = run(GW.confirmed_by_code({**self.ch, "account_id": "someone-else"}, NUM, {"Body": "119218", "MessageSid": "SM2"}))
        self.assertIsNone(said)
        self.assertIsNotNone(run(self.store.peek_code("119218", GW.NOW())))   # still waiting for its own account

    def test_not_a_code_is_just_a_message(self):
        self.assertIsNone(run(GW.confirmed_by_code(self.ch, NUM, {"Body": "Yes", "MessageSid": "SM3"})))
        self.assertIsNone(run(GW.confirmed_by_code(self.ch, NUM, {"Body": "Book DiverXO for 2 on Friday 13 November at 21:00 — ref 123456 "
                                                                         "please keep it, thanks a lot", "MessageSid": "SM4"})))


class AnUnverifiedWhatsAppNumberIsAskedForItsCode(unittest.TestCase):
    def test_on_any_target_never_an_sms_link(self):
        async def call(account, op, body, approval=None):
            if op == "approvals.in_app_tap":
                return {"ok": False, "error": {"code": "approval_untrusted_origin", "message": "not verified"}}
            if op == "users.register":   # the WhatsApp tap registers the number (unverified) before it asks
                return {"ok": True, "result": {}}
            raise AssertionError(f"no {op} — an SMS link never verifies this WhatsApp number")
        wa = VS.WA.set({"wa_id": NUM, "message_id": "SM311"})
        try:
            for tgt in ("sandbox", "live"):
                with mock.patch.object(VS, "_call", call), mock.patch.object(VS, "target", mock.AsyncMock(return_value=tgt)), \
                        mock.patch.object(VS, "whatsapp_verified", mock.AsyncMock(return_value=False)), \
                        mock.patch.dict("os.environ", {"SASHA_AGAPI_TAP_SECRET": "s"}):
                    r = run(VS.submit(ACCT, {"read_back_id": "rbk", "prepared_id": "p", "end_user": "eu", "sha": "f" * 64}, "Yes"))
                self.assertEqual(r, {"ok": True, "status": "confirm_number"}, tgt)
        finally:
            VS.WA.reset(wa)


class TheNextYesSends(unittest.TestCase):
    def test_the_turn_runs_book_venue_by_code(self):
        src = (ROOT / "app" / "agent" / "sasha.py").read_text()
        self.assertIn('if _hy and _hy.get("number_confirmed_at") and _yes_y(message):', src)
        self.assertIn('tap_uses = [_TapUse(f"toolu_yes_{turn_key}", "book_venue", {"name": _hy.get("venue"), "approval": {"said": message}})]', src)

    def test_the_read_back_stands_again_when_nothing_went(self):   # found by the proof: his first yes was consumed, nothing went → no_read_back
        src = (ROOT / "agapi" / "venues.py").read_text()
        body = src[src.index("async def confirm_number"):src.index("async def _agapi_call")]
        self.assertIn('YG.shown(ctx, act, {"read_back": [held.get("summary") or venue]})', body)   # Sasha 314 MOVED: a booking's or a cancel's
        self.assertLess(body.index("store[ctx.account] = held"), body.index("YG.shown("))   # shown again only once it's held again

    def test_refused_again_after_confirming_is_said_and_never_a_loop(self):
        held = {"venue": "DiverXO", "summary": "Fri 13 Nov 21:00, 2 people", "number_confirmed_at": "2026-10-29T10:50:52Z"}
        VN._HELD["acct-311"] = held

        class C:
            account = "acct-311"
        out = run(VN.confirm_number(C(), held, "DiverXO"))
        self.assertEqual(out["status"], "not_sent")
        self.assertNotIn("acct-311", VN._HELD)
        self.assertNotRegex(out["line"].lower(), r"send me this message|kanoe link|say yes")
        self.assertEqual(V.yes_line("book_venue", {"ok": True, "result": out}), out["line"])


if __name__ == "__main__":
    unittest.main()
