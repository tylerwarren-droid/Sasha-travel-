"""Sasha 258 · T40 — "YES, SEND IT" SENDS THE BOOKING ITSELF (CR 97, mailbox row 880). On /s2 and /next the person's own yes on a
"Handle it" read-back IS the approval: ONE call, approvals.in_app_tap {read_back_id, read_back_sha256 (the card's own), session (their
live Supabase session, passed through — never stored or logged)}; no email or text link to the person; no simulate_approval. A stale
card → its new read-back; already tapped → "already sent" + the booking's status. WhatsApp (no in-app session): unchanged.
Offline: AgAPI is a stand-in.

    cd backend && python -m unittest tests.test_s258_in_app_yes -v
"""
from __future__ import annotations

import asyncio
import logging
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

from agapi import s2_memory as M, venue_submit as VS, venues as VN
from app.agent import voice as V

ACCT = "00000000-0000-4000-8000-000000000258"
TOKEN = "eyJ.this-persons-own-session.sig"
SHA = "f6a976c4e39f" + "0" * 52


def run(c):
    return asyncio.run(c)


class AgAPI:
    """CR 97's AgAPI as Sasha sees it: submit without approval → approval_required + the card's hash; in_app_tap → the act's result."""

    def __init__(self, tap_error=None):
        self.calls, self.tap_error, self.rb = [], tap_error, 0

    async def __call__(self, op, body, approval=None, account=None):
        self.calls.append((op, body))
        if op == "users.register":
            return {"ok": True, "result": {"end_user_id": "usr_1"}}
        if op == "venue.submit_booking":
            self.rb += 1
            return {"ok": False, "error": {"code": "approval_required", "details": {
                "read_back_id": f"rb_{self.rb}", "read_back_sha256": SHA if self.rb == 1 else "a" * 64,
                "read_back": {"lines": [f"Sasha sends your booking request on Taverna Sandbox's own form … (v{self.rb})"]}}}}
        if op == "approvals.in_app_tap":
            if self.tap_error:
                return {"ok": False, "error": {"code": self.tap_error, "message": self.tap_error}}
            return {"ok": True, "result": {"approval_id": "apv_1", "method": "in_app_tap", "operation": "venue.submit_booking",
                                           "result": {"status": "confirmed", "act_id": "act_1", "reference": "TAV-BF497B",
                                                      "say": "Booked — Taverna Sandbox confirmed it, reference TAV-BF497B."}}}
        if op == "approvals.request":   # the link to the person's phone (only ever off the app)
            return {"ok": True, "result": {"sent": True}}
        if op == "venue.booking_status":
            return {"ok": True, "result": {"act_id": body["act_id"], "state": "confirmed", "venue_words": {"untrusted_text": "Confirmed. Reference TAV-BF497B."}}}
        raise AssertionError(op)


class Base(unittest.TestCase):
    TAP_ERROR = None

    def setUp(self):
        self.api = AgAPI(self.TAP_ERROR)
        for p in (mock.patch.object(VS, "CALL", self.api), mock.patch.dict(VS._ACTS, {}, clear=True), mock.patch.dict(VS._USERS, {}, clear=True),
                  mock.patch.object(VS, "target", mock.AsyncMock(return_value="live")),
                  mock.patch.object(M, "put_kind", mock.AsyncMock(return_value=True)), mock.patch.object(M, "kind", mock.AsyncMock(return_value=None)),
                  mock.patch.dict(VN._HELD, {}, clear=True), mock.patch.dict(VN._SENT, {}, clear=True)):
            p.start()
            self.addCleanup(p.stop)
        self.tok = VS.TAP.set({"kind": "supabase", "token": TOKEN})
        self.addCleanup(VS.TAP.reset, self.tok)

    def hold(self):
        rb = run(VS.read_back(ACCT, "vpr_" + "1" * 32))
        return {"read_back_id": rb["read_back_id"], "prepared_id": "vpr_" + "1" * 32, "sha": rb["sha256"], "lines": rb["lines"],
                "end_user": "usr_1", "venue": "Taverna Sandbox", "when": "2026-10-22T21:00", "party": 2, "summary": "Thursday 22 October at 21:00, 2 people"}

    def ops(self):
        return [op for op, _ in self.api.calls]


class TheYesSendsItself(Base):
    def test_one_in_app_tap_with_the_cards_hash_and_their_session(self):
        held = self.hold()
        self.assertEqual(held["sha"], SHA)                                   # the card binds to AgAPI's own hash
        r = run(VS.submit(ACCT, held, "Yes, send it."))
        self.assertTrue(r["ok"])
        self.assertEqual((r["status"], r["reference"]), ("confirmed", "TAV-BF497B"))
        taps = [b for op, b in self.api.calls if op == "approvals.in_app_tap"]
        self.assertEqual(len(taps), 1)
        self.assertEqual(taps[0], {"read_back_id": "rb_1", "read_back_sha256": SHA, "session": {"kind": "supabase", "token": TOKEN}})

    def test_no_link_to_the_person_and_no_simulated_yes(self):
        run(VS.submit(ACCT, self.hold(), "Yes, send it."))
        self.assertNotIn("approvals.request", self.ops())                    # no email / text to the person
        self.assertNotIn("sandbox.simulate_approval", self.ops())
        self.assertNotIn("approvals.status", self.ops())

    def test_the_session_is_never_logged(self):
        with self.assertLogs(level=logging.DEBUG) as logs:
            logging.getLogger("x").debug("start")
            run(VS.submit(ACCT, self.hold(), "Yes, send it."))
        self.assertFalse(any(TOKEN in line for line in logs.output))

    def test_the_same_yes_again_is_already_sent_with_its_status(self):
        VN._SENT[ACCT] = {"venue": "Taverna Sandbox", "at": datetime.now(timezone.utc)}
        VS._ACTS[ACCT] = [{"act_id": "act_1", "venue": "Taverna Sandbox", "when": "2026-10-22T21:00", "party": 2, "state": "sent", "at": 1}]

        class Ctx:
            account, user_said, idem, claimed = ACCT, "Yes, send it.", None, None
            started = datetime.now(timezone.utc) + timedelta(seconds=5)
        out = run(VN.book_venue(Ctx(), {"approval": {"said": "Yes, send it."}}))
        self.assertEqual(out["status"], "already_sent")
        self.assertTrue(out["say"].startswith(V.TAP_SAYS["approval_consumed"]))
        self.assertIn("Booked", out["say"])
        self.assertNotIn("approvals.in_app_tap", self.ops())                 # never sent twice


class AStaleCard(Base):
    TAP_ERROR = "approval_void"

    def test_the_new_read_back_is_shown_and_asked(self):
        held = self.hold()
        r = run(VS.submit(ACCT, held, "Yes, send it."))
        self.assertEqual(r["error"]["code"], "approval_void")
        fresh = r["error"]["details"]["fresh"]
        self.assertIn("(v2)", fresh["lines"][0])

        class Ctx:
            account = ACCT
        out = run(VN._tap_refused(Ctx(), held, "approval_void", r["error"], "Taverna Sandbox"))
        self.assertEqual(out["status"], "awaiting_yes")
        self.assertEqual(out["ask"], V.TAP_SAYS["approval_void"])
        self.assertEqual(VN._HELD[ACCT]["sha"], "a" * 64)                    # their next yes binds to the NEW card


class NotTheirSession(Base):
    TAP_ERROR = "approval_untrusted_origin"

    def test_sign_in_again_and_the_card_stays(self):
        held = self.hold()
        r = run(VS.submit(ACCT, held, "Yes, send it."))

        class Ctx:
            account = ACCT
        out = run(VN._tap_refused(Ctx(), held, r["error"]["code"], r["error"], "Taverna Sandbox"))
        self.assertEqual(out["say"], V.TAP_SAYS["approval_untrusted_origin"])
        self.assertIn(ACCT, VN._HELD)


class TheFoundersProxySession(Base):
    def test_never_guessed_or_signed_told_to_sign_in(self):
        VS.TAP.set({"kind": "founder"})
        r = run(VS.submit(ACCT, self.hold(), "Yes, send it."))
        self.assertEqual(r["error"]["code"], "approval_untrusted_origin")
        self.assertNotIn("approvals.in_app_tap", self.ops())


class WhatsAppUnchanged(Base):
    def test_no_in_app_session_keeps_its_own_path(self):
        VS.TAP.set(None)
        run(VS.read_back(ACCT, "vpr_" + "1" * 32))
        self.assertNotIn("approvals.request", self.ops())   # Sasha 314 MOVED: no SMS link fallback (it sent nothing: Tyler's DiverXO cancel)
        self.assertNotIn("approvals.in_app_tap", self.ops())


if __name__ == "__main__":
    unittest.main()


class FoundByTheScoreboard(unittest.TestCase):
    def test_the_trip_banner_reads_the_trips_own_state(self):   # item 3: a table booked elsewhere never makes a trip "Trip total"
        from agapi import s2_status as ST
        self.assertEqual(ST.public({"state": "booked", "line": "Booked: a table", "refs": [], "trip_state": "nothing"})["trip_state"], "nothing")
        self.assertEqual(ST.public({"state": "booked", "line": "x", "refs": []})["trip_state"], "booked")

    def test_an_agapi_hold_is_the_same_booking_whatever_channel_word(self):   # item 15: re-held on the yes → the same read-back
        import inspect
        src = inspect.getsource(VN.hold_venue)
        self.assertIn('held.get("rung") == "agapi"', src)
        self.assertIn('"status": "yes_heard"', src)


class TheOnceOnlyKeyBelongsToItsCard(unittest.TestCase):
    """Found on the scoreboard's account (it books Taverna Correo every run): the once-only key was <account>:book_venue:<the model's
    key>, durable in Postgres — a model reusing its key for a NEW booking got "already done" and nothing was sent. Now the key belongs
    to the read-back being answered: a new card is a new act; the same card is still sent once."""

    def test_a_new_card_is_a_new_key_the_same_card_the_same(self):
        from agapi import v0 as API
        with mock.patch.dict(VN._HELD, {ACCT: {"sha": "a" * 64}}):
            first = API._act_bound_to(ACCT, "book_venue")
        with mock.patch.dict(VN._HELD, {ACCT: {"sha": "b" * 64}}):
            second = API._act_bound_to(ACCT, "book_venue")
        with mock.patch.dict(VN._HELD, {ACCT: {"sha": "a" * 64}}):
            again = API._act_bound_to(ACCT, "book_venue")
        self.assertNotEqual(first, second)
        self.assertEqual(first, again)
        self.assertIsNone(API._act_bound_to(ACCT, "get_status"))
