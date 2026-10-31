"""Sasha 317 · cancel — and change, and running late — by ONE instruction on EVERY route.

Found live (31 Oct 07:41–07:44, Tyler's account): "Book Taberna Las Sobrinas for 2 … Fri 13 Nov at 21:30" went at once; then "Cancel my
Las Sobrinas booking" got "I'll message Taberna Las Sobrinas asking them to cancel… Shall I send it?". Read-only first: agapi-live shows
the booking's read-back (venue.submit_booking 409) and its tap (approvals.in_app_tap) at 07:41:59–07:42:01, then the cancel's read-back
(venue.cancel_booking 409) at 07:43:44 — and NO cancel after it: nothing was sent to the venue.
WHY: not the route. Sasha 314's rule asked for the venue's WHOLE name in his words ("taberna las sobrinas" in "cancel my las sobrinas
booking" → no), so only one-word names like DiverXO ever matched; and change / running late never had the rule at all (always "OK?").
Root test: (1) ONE truth — `venues.one_instruction`: his own words, the action's verb and a name naming exactly ONE active booking of his,
from the app or his verified WhatsApp, ARE the approval; (2) no per-route copy — the act (every AgAPI route: email, Kanoe's WhatsApp, his
WhatsApp, a call) and the reservation route take the same rule, and a handed-over booking (a platform) is his, there; (3) the whole class:
cancel, change and late, each route. Offline.

    cd backend && python -m unittest tests.test_s317 -v
"""
from __future__ import annotations

import asyncio
import inspect
import unittest
from datetime import datetime, timezone
from unittest import mock

from agapi import s2_manage as M, venue_submit as VS, venues as VN

ACCT = "acct-317"
LS = {"act_id": "act_LS", "venue": "Taberna Las Sobrinas", "date": "2026-11-13", "time": "21:30", "party": 2, "status": "requested"}
DX = {"act_id": "act_DX", "venue": "DiverXO", "date": "2026-11-20", "time": "21:00", "party": 2, "status": "requested"}
RB = {"ok": True, "end_user": "eu", "read_back_id": "rb_1", "lines": ["Cancel: Taberna Las Sobrinas · Fri 13 Nov 21:30 · 2"],
      "act_id": "act_LS", "read_back_sha256": "f" * 64}
ROUTES = ("email", "kanoe_whatsapp", "his_whatsapp", "phone")


def run(c):
    return asyncio.run(c)


def ctx(said):
    from agapi import v0 as API
    c = API.Ctx(account=ACCT, surface="s2", user_said=said, mode="test")
    c.started = datetime.now(timezone.utc)
    return c


class Base(unittest.TestCase):
    channel = "wa"

    def setUp(self):
        from agapi import v0 as API
        from booking_signer import basket as BK
        VN._CANCEL.pop(ACCT, None)
        M._HELD.pop(ACCT, None)
        API._CLAIMED.clear()
        for p in (mock.patch.object(BK, "_run", lambda: None), mock.patch.object(M, "_record", mock.AsyncMock())):
            p.start()
            self.addCleanup(p.stop)
        if self.channel == "wa":   # his verified WhatsApp: the approval channel (Sasha 314)
            tok = VS.WA.set({"wa_id": "+34600000317", "message_id": "SM317"})
            self.addCleanup(VS.WA.reset, tok)

    def cancel(self, said, rows, result=None):
        submit = mock.AsyncMock(return_value=result or {"ok": True, "status": "sent", "cancel_act_id": "act_CX"})
        with mock.patch.object(VS, "bookings", mock.AsyncMock(return_value=rows)), \
                mock.patch.object(VS, "cancel_read_back", mock.AsyncMock(return_value=dict(RB))), \
                mock.patch.object(VS, "cancel_submit", submit):
            out = run(VN._cancel_act(ctx(said), {"act_id": "act_LS"}, None, said, lambda s: True))
        return out, submit

    def notice(self, said, kind, route, rows, ask):
        b = {"source": "act", "act_id": "act_LS", "venue": "Taberna Las Sobrinas", "route": route, "route_words": route,
             "date": "2026-11-13", "time": "21:30", "party": 2}
        submit = mock.AsyncMock(return_value={"ok": True, "status": "sent", "change_act_id": "act_CH", "say": "I've asked them."})
        with mock.patch.object(VS, "bookings", mock.AsyncMock(return_value=rows)), \
                mock.patch.object(VS, "change_read_back", mock.AsyncMock(return_value={**RB, "lines": ["Change: …"]})), \
                mock.patch.object(VS, "change_submit", submit):
            out = run(M._act_notice(ctx(said), ask, b, kind, "running_late" if kind == "late" else "change_booking"))
        return out, submit


class ATylersCancel(Base):
    def test_cancel_my_las_sobrinas_booking_goes_at_once_and_once(self):
        out, submit = self.cancel("Cancel my Las Sobrinas booking", [dict(LS), dict(DX)])
        submit.assert_called_once()
        self.assertEqual(out["status"], "requested")
        self.assertIn("I've asked Taberna Las Sobrinas to cancel", out["line"])
        again, submit2 = self.cancel("Cancel my Las Sobrinas booking", [dict(LS), dict(DX)])   # the same words again: never twice
        submit2.assert_not_called()
        self.assertEqual(again["status"], "already_sent")

    def test_the_whole_name_and_its_short_name_both_name_it(self):
        for said in ("Cancel my Taberna Las Sobrinas booking", "cancel las sobrinas please", "Cancel Sobrinas", "Cancela Las Sobrinas"):
            self.setUp()
            out, submit = self.cancel(said, [dict(LS)])
            self.assertEqual(out["status"], "requested", said)

    def test_anything_less_is_a_read_back_never_a_guess(self):
        for said, rows in (("Cancel my booking", [dict(LS)]),                                       # no name
                           ("Cancel my Sobrinass booking", [dict(LS)]),                             # misspelt: no fuzzy match
                           ("Cancel my Las Sobrinas booking", [dict(LS), {**LS, "act_id": "act_LS2", "date": "2026-11-20"}]),   # two
                           ("Cancel my DiverXO booking", [dict(LS), dict(DX)]),                     # names another booking
                           ("What time is Las Sobrinas?", [dict(LS)])):                             # no verb
            self.setUp()
            out, submit = self.cancel(said, rows)
            submit.assert_not_called()
            self.assertEqual(out["status"], "awaiting_yes", said)

    def test_names_venue(self):
        self.assertTrue(VN.names_venue("cancel my las sobrinas booking", "Taberna Las Sobrinas"))
        self.assertTrue(VN.names_venue("cancel DiverXO", "DiverXO"))
        self.assertFalse(VN.names_venue("cancel the taberna", "Taberna Las Sobrinas"))          # its kind alone names no place
        self.assertFalse(VN.names_venue("cancel sobrinasx", "Taberna Las Sobrinas"))
        self.assertTrue(VN.names_venue("cancel my correo booking", "Taverna Correo (sandbox)"))   # the proof's find: "taverna" is a kind too
        self.assertFalse(VN.names_venue("cancel my taverna booking", "Taverna Correo (sandbox)"))


class BEveryRouteOneRule(Base):
    """The whole class: cancel, change and late on each of AgAPI's routes go on his instruction; the route only says how it goes."""

    def test_cancel_every_route(self):
        for route in ROUTES:
            self.setUp()
            result = ({"ok": True, "status": "person_sends", "message": {"link": "https://wa.me/34600"}, "say": "Send this on WhatsApp."}
                      if route == "his_whatsapp" else {"ok": True, "status": "sent", "route": route})
            out, submit = self.cancel("Cancel my Las Sobrinas booking", [{**LS, "route": route}], result)
            submit.assert_called_once()
            self.assertNotEqual(out["status"], "awaiting_yes", route)

    def test_change_every_route(self):
        for route in ROUTES:
            self.setUp()
            out, submit = self.notice("Move my Las Sobrinas booking to 22:00", "change", route, [{**LS, "route": route}], {"new_time": "22:00"})
            submit.assert_called_once()
            self.assertEqual(submit.call_args.args[1]["ask"], {"at": "2026-11-13T22:00"})
            self.assertNotEqual(out["status"], "awaiting_yes", route)

    def test_late_every_route(self):
        for route in ROUTES:
            self.setUp()
            out, submit = self.notice("I'm running 20 minutes late to Las Sobrinas", "late", route, [{**LS, "route": route}], {"minutes": 20})
            submit.assert_called_once()
            self.assertEqual(submit.call_args.args[1]["ask"], {"arrive": "21:50"})
            self.assertNotEqual(out["status"], "awaiting_yes", route)

    def test_a_change_that_names_nothing_is_still_asked(self):
        out, submit = self.notice("Move it to 22:00", "change", "email", [dict(LS)], {"new_time": "22:00"})
        submit.assert_not_called()
        self.assertEqual(out["status"], "awaiting_yes")

    def test_the_reservation_route_takes_the_same_rule(self):
        calls = []

        async def api(account, method, path, body=None, timeout=90.0):
            calls.append((method, path))
            if method == "GET" and path.endswith("/cancel"):
                return 200, {"venue": "Taberna Las Sobrinas", "route": "email", "read_back": {"sha256": "a" * 64, "lines": ["Cancel: …"]}}
            if method == "POST" and path.endswith("/cancel"):
                return 200, {"status": "requested", "say": "I've asked them to cancel."}
            return 200, {}
        rows = [{"trip_item_id": "ti_1", "venue": "Taberna Las Sobrinas", "status": "requested"}]
        GW = VN._API()
        with mock.patch.object(GW, "api", api), mock.patch.object(VN, "venue_bookings", mock.AsyncMock(return_value=rows)), \
                mock.patch.object(VN, "_push_later", mock.AsyncMock()), mock.patch.object(VS, "bookings", mock.AsyncMock(return_value=[])):
            out = run(VN.cancel_venue(ctx("Cancel my Las Sobrinas booking"), {"trip_item_id": "ti_1"}))
        self.assertEqual(out["status"], "requested")
        self.assertIn(("POST", "/api/booking/reservations/ti_1/cancel"), calls)

    def test_one_rule_no_route_copy(self):
        src = inspect.getsource(VN) + inspect.getsource(M)
        self.assertNotIn("_cancel_named", src)                                                    # 314's per-cancel copy is gone
        self.assertEqual(src.count("await one_instruction(") + src.count("await VN.one_instruction("), 4)   # act + reservation, cancel + notice


class DAskedAgain(Base):
    def test_a_cancel_already_sent_is_said_never_an_error(self):   # found by the sandbox proof (31 Oct): it raised "didn't ask for their yes"
        async def call(op, body, approval=None, account=None):
            return {"ok": True, "result": {"status": "already_cancelled", "say": "I already asked Taverna Correo to cancel it."}}
        with mock.patch.object(VS, "CALL", call), mock.patch.object(VS, "end_user", mock.AsyncMock(return_value="eu")), \
                mock.patch.object(VS, "bookings", mock.AsyncMock(return_value=[dict(LS)])):
            out = run(VN._cancel_act(ctx("Cancel my Las Sobrinas booking"), {"act_id": "act_LS"}, None, "x", lambda s: True))
        self.assertEqual((out["status"], out["line"]), ("already_sent", "I already asked Taverna Correo to cancel it."))


class COtherChannelsStillAsk(Base):
    channel = None   # the web chat or the voice line: no tap and no verified WhatsApp — Sasha 314's channels only

    def test_no_approval_channel_is_a_read_back(self):
        out, submit = self.cancel("Cancel my Las Sobrinas booking", [dict(LS)])
        submit.assert_not_called()
        self.assertEqual(out["status"], "awaiting_yes")


if __name__ == "__main__":
    unittest.main()
