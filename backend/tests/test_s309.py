"""Sasha 309 · one read-back, one yes, it goes (WhatsApp). The read-back is the complete request; ONE yes (tap or typed) sends it; a yes
that can't go yet is said as it is — never "tap Yes" with nothing to tap; a number linked before CR 100 is confirmed once, from itself.

    cd backend && python -m unittest tests.test_s309 -v
"""
from __future__ import annotations

import asyncio
import inspect
import os
import unittest
from unittest import mock

from agapi import venue_submit as VS, venues as VN
from app.agent import voice as V
from tests import test_s287 as T

ACCT = T.ACCT


def run(c):
    return asyncio.run(c)


class TheRefusedLinkIsNeverTapYes(unittest.TestCase):   # found live: 403 on his WhatsApp yes, 422 on the link, then "tap Yes"
    def test_submit_says_confirm_number(self):
        async def call(account, op, body, approval=None):
            if op == "approvals.in_app_tap":
                return {"ok": False, "error": {"code": "approval_untrusted_origin", "message": "not this person's verified number"}}
            if op == "approvals.request":
                return {"ok": False, "error": {"code": "invalid_input", "message": "That WhatsApp number isn't verified yet"}}
            return {"ok": True, "result": {}}
        wa = VS.WA.set({"wa_id": "+34600000309", "message_id": "SM309"})
        try:
            with mock.patch.object(VS, "_call", call), mock.patch.object(VS, "target", mock.AsyncMock(return_value="live")), \
                    mock.patch.object(VS, "whatsapp_verified", mock.AsyncMock(return_value=False)), \
                    mock.patch.dict(os.environ, {"SASHA_AGAPI_TAP_SECRET": "s"}):
                r = run(VS.submit(ACCT, {"read_back_id": "rbk", "prepared_id": "p", "end_user": "eu", "sha": "f" * 64}, "Yes"))
        finally:
            VS.WA.reset(wa)
        self.assertEqual(r, {"ok": True, "status": "confirm_number"})

    def test_confirm_number_asks_for_the_code_once_and_never_tap(self):
        put = mock.AsyncMock(return_value=True)
        store = mock.Mock(channel_of_account=mock.AsyncMock(return_value={"number_e164": "+34600000309", "consent_at": None}), put_code=put)
        from booking_signer import guest_whatsapp as GW
        with mock.patch.object(GW, "STORE", store), \
                mock.patch.object(VS, "link_whatsapp", mock.AsyncMock(return_value={"ok": True, "code": "123456", "text": "Kanoe link 123456"})):
            out = run(VN.confirm_number(T.ctx("Yes"), {"summary": "Fri 13 Nov 21:00, 2 people", "venue": "DiverXO"}, "DiverXO"))
        VN._HELD.pop(ACCT, None)
        self.assertEqual(out["status"], "confirm_number")
        self.assertIn("send me this message: Kanoe link 123456", out["line"])
        self.assertNotRegex(out["line"].lower(), r"\btap\b|\bcall\b|\bring\b")
        self.assertEqual(put.call_args.args[0]["account_id"], ACCT)
        self.assertEqual(V.yes_line("book_venue", {"ok": True, "result": out}), out["line"])   # said by code; the turn ends on it

    def test_the_line_is_said_on_every_surface(self):
        self.assertEqual(V.yes_line("hold_venue", {"ok": True, "result": {"status": "waiting_for_their_tap", "line": "x"}}), "x")
        self.assertEqual(V.yes_line("hold_venue", {"ok": True, "result": {"status": "awaiting_yes", "line": "x"}}), "")


class ALinkedNumberConfirmsItselfOnce(unittest.TestCase):
    def _dispatch(self, code_row, confirm):
        from booking_signer import guest_whatsapp as GW
        ch = {"account_id": ACCT, "wa_id_sha256": "k", "number_e164": "+34600000309"}
        store = mock.Mock(channel_for=mock.AsyncMock(return_value=ch), take_code=mock.AsyncMock(return_value=code_row),
                          peek_code=mock.AsyncMock(return_value=code_row), get_state=mock.AsyncMock(return_value={}),
                          put_state=mock.AsyncMock())   # Sasha 311 MOVED: the code is peeked first; the exchange goes in her history
        p = {"From": "whatsapp:+34600000309", "To": "whatsapp:+447000000000", "Body": "Kanoe link 123456", "MessageSid": "SM1"}
        with mock.patch.object(GW, "STORE", store), mock.patch.object(GW, "guest_numbers", lambda: ["+447000000000"]), \
                mock.patch.object(GW, "first_time", mock.AsyncMock(return_value=True)), \
                mock.patch.object(GW, "_spawn", side_effect=lambda c: c.close()) as turn, mock.patch.object(VS, "confirm_whatsapp", confirm), \
                mock.patch.object(VS, "whatsapp_verified", mock.AsyncMock(return_value=True)):   # Sasha 311 · AgAPI's record read back
            out = run(GW.dispatch(p, mock.AsyncMock(return_value=None)))
        return out, turn

    def test_its_own_code_confirms_it(self):
        confirm = mock.AsyncMock(return_value={"ok": True, "state": "verified"})
        out, turn = self._dispatch({"account_id": ACCT}, confirm)
        self.assertIn(V.NUMBER_CONFIRMED, out)
        turn.assert_not_called()
        self.assertEqual(confirm.call_args.args[:2], (ACCT, "+34600000309"))

    def test_another_accounts_code_is_just_a_message(self):
        confirm = mock.AsyncMock()
        out, turn = self._dispatch({"account_id": "someone-else"}, confirm)
        confirm.assert_not_called()
        turn.assert_called_once()


class OneMessageOneYes(unittest.TestCase):
    def test_the_whatsapp_read_back_is_one_message_with_its_buttons_and_no_place_cards(self):
        from booking_signer import wa_agent as WA, guest_whatsapp as GW
        out = GW.Out()
        WA._read_back({"kind": "read_back", "read_back": T.LINES, "ask": "Casa Gate, Friday 21:00 for 2. Shall I send?"}, out)
        self.assertEqual(len(out.items), 1)
        kind, body, buttons = out.items[0]
        self.assertEqual(kind, "ask")
        self.assertTrue(body.startswith(T.LINES[0]) and body.endswith("Shall I send?"))
        self.assertEqual(buttons[0], ("Yes", "yn:yes"))
        src = inspect.getsource(WA)
        self.assertIn('renders = [ev for ev in renders if ev.get("kind") != "venues"]', src)

    def test_a_full_request_is_one_send_and_no_confirmation_at_all(self):   # Sasha 314 MOVED: his complete instruction IS the yes
        class B(T.Base):
            def runTest(self):
                pass
        b = B()
        b.setUp()
        try:
            out = b.hold(T.FULL)
            self.assertEqual(b.agapi.sends, ["rbk_287"])
            self.assertEqual(out["status"], "requested")
            self.assertNotIn("ask", out)
        finally:
            b.tearDown()


if __name__ == "__main__":
    unittest.main()
