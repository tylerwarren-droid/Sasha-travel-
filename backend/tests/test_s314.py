"""Sasha 314 · one instruction, one action: his complete instruction (a booking naming venue, day, time and party; "cancel my <venue>
booking" naming exactly one) IS the approval, from his verified WhatsApp / the app; a short read-back only when Sasha filled a term;
never "I've sent you a link" — the SMS link fallback that sent nothing is gone. Offline.

    cd backend && python -m unittest tests.test_s314 -v
"""
from __future__ import annotations

import asyncio
import inspect
import pathlib
import unittest
from datetime import datetime, timezone
from unittest import mock

from agapi import venue_submit as VS, venues as VN
from app.agent import voice as V

ROOT = pathlib.Path(__file__).resolve().parents[1]
ACCT = "acct-314"
DX = {"act_id": "act_DX", "venue": "DiverXO", "date": "2026-11-13", "time": "21:00", "party": 2, "status": "requested"}
RB = {"ok": True, "end_user": "eu", "read_back_id": "rb_c", "lines": ["Cancel: DiverXO · Fri 13 Nov 21:00 · 2"], "act_id": "act_DX",
      "read_back_sha256": "f" * 64}


def run(c):
    return asyncio.run(c)


class Ctx:
    def __init__(self, said):
        from agapi import v0 as API
        self.c = API.Ctx(account=ACCT, surface="s2", user_said=said, mode="test")
        self.c.started = datetime.now(timezone.utc)


class ACancelNamingOneBookingIsTheYes(unittest.TestCase):
    def setUp(self):
        VN._CANCEL.pop(ACCT, None)
        from agapi import v0 as API
        API._CLAIMED.clear()

    def go(self, said, rows, submit):
        from booking_signer import basket as BK
        wa = VS.WA.set({"wa_id": "+34600000314", "message_id": "SM314"})   # his verified WhatsApp: the approval channel
        self.addCleanup(VS.WA.reset, wa)
        with mock.patch.object(VS, "bookings", mock.AsyncMock(return_value=rows)), \
                mock.patch.object(VS, "cancel_read_back", mock.AsyncMock(return_value=dict(RB))), \
                mock.patch.object(VS, "cancel_submit", submit), mock.patch.object(BK, "_run", lambda: None):
            return run(VN._cancel_act(Ctx(said).c, {"act_id": "act_DX"}, None, said, lambda s: True))

    def test_cancel_my_diverxo_booking_goes_at_once(self):
        submit = mock.AsyncMock(return_value={"ok": True, "status": "sent", "cancel_act_id": "act_CX"})
        out = self.go("Cancel my DiverXO booking", [dict(DX)], submit)
        submit.assert_called_once()
        self.assertEqual(out["status"], "requested")
        self.assertEqual(out["line"], "Cancelled — I've asked DiverXO to cancel Fri 13 Nov 21:00 for 2. I'll tell you when they confirm.")

    def test_two_bookings_there_is_a_read_back_never_a_guess(self):
        submit = mock.AsyncMock()
        out = self.go("Cancel my DiverXO booking", [dict(DX), {**DX, "act_id": "act_DX2", "date": "2026-11-20"}], submit)
        submit.assert_not_called()
        self.assertEqual(out["status"], "awaiting_yes")

    def test_words_that_dont_name_it_are_a_read_back(self):
        submit = mock.AsyncMock()
        out = self.go("cancel it", [dict(DX)], submit)
        submit.assert_not_called()
        self.assertEqual(out["status"], "awaiting_yes")


class TheCancelYesOnWhatsApp(unittest.TestCase):   # found live: cancel_submit had no WhatsApp branch → the link fallback → nothing
    def test_a_whatsapp_yes_is_the_approval(self):
        wa = VS.WA.set({"wa_id": "+34600000314", "message_id": "SM314"})
        try:
            with mock.patch.object(VS, "whatsapp_tap", mock.AsyncMock(return_value={"ok": True, "result": {"status": "sent", "cancel_act_id": "act_CX"}})) as tap, \
                    mock.patch.object(VS, "acts_of", mock.AsyncMock(return_value=[])), mock.patch.object(VS, "_remember", mock.AsyncMock()):
                r = run(VS.cancel_submit(ACCT, {"read_back_id": "rb_c", "act_id": "act_DX", "end_user": "eu", "read_back_sha256": "f" * 64}, "yes"))
        finally:
            VS.WA.reset(wa)
        tap.assert_called_once_with(ACCT, "rb_c", "f" * 64)
        self.assertEqual(r["status"], "sent")


class NeverALinkThatWasntSent(unittest.TestCase):
    def test_no_sms_link_fallback_in_the_venue_path(self):
        src = (ROOT / "agapi" / "venue_submit.py").read_text()
        code = "\n".join(x.split("#")[0] for x in src.splitlines())
        self.assertNotIn('"approvals.request"', code)
        self.assertNotIn('"status": "waiting_for_their_tap"', code)

    def test_no_words_about_a_link_nobody_got(self):
        for f in ("agapi/venues.py", "agapi/s2_manage.py", "agapi/venue_submit.py"):
            code = "\n".join(x.split("#")[0] for x in (ROOT / f).read_text().splitlines())
            self.assertNotIn("sent you the link", code, f)
            self.assertNotIn("sent you a link", code, f)

    def test_the_other_link_users_say_it_only_when_it_went(self):
        for f in ("agapi/s2_subscriptions.py", "agapi/s2_fine_print.py"):
            self.assertIn('["link_sent"] = bool(q.get("ok"))', (ROOT / f).read_text(), f)


class TheShortReadBack(unittest.TestCase):
    def test_tylers_words(self):
        self.assertEqual(V.kanoe_ask("DiverXO", "Fri 13 Nov", "21:00", 2, "email"), "DiverXO, Fri 13 Nov 21:00 for 2. Send?")   # HER VOICE: no channel

    def test_the_complete_request_is_sent_and_a_filled_term_is_asked(self):
        src = inspect.getsource(VN.kanoe_card)
        self.assertLess(src.index("if all(got.values()):"), src.index("_kanoe_now("))
        self.assertIn('"read_back": []', src)   # the short line is the card: never the whole template


if __name__ == "__main__":
    unittest.main()
