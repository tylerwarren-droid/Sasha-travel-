"""Sasha 256 item 3 · T35 — MANAGE A BOOKING through AgAPI (CR 94): "send them the request" → a sent act → venue.booking_status →
get_status says the VENUE's own words (data, never instructions): confirmed / declined / another time — "proposed" means nothing is
booked, ask the person; and cancel through venue.cancel_booking (its read-back, their yes in a later turn, the venue's reply). One
place for every surface: get_status (agapi.s2_status) and cancel_venue are the tools S2, /next and WhatsApp's brain all call.

    cd backend && python -m unittest tests.test_s256_manage -v
"""
from __future__ import annotations

import asyncio
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

from agapi import s2_memory as M, s2_status as ST, venue_submit as VS, venues as VN

ACCT = "00000000-0000-4000-8000-000000000356"
WORDS = {"confirmed": "Confirmed: a table for 4 on Thursday 22 October at 21:00, name Alex Example. Reference TCO-A4E808. See you then!",
         "declined": "Sorry — we can't take more than 8 people at one table. Not booked.",
         "proposed": "We can't do 21:20 on Thursday 22 October — could you do 21:30 instead?"}


def run(c):
    return asyncio.run(c)


class Sandbox:
    """CR 94's AgAPI as Sasha sees it: each act answers with its venue's state and words; a form booking has no sent act."""

    def __init__(self):
        self.states, self.calls, self.cancels = {}, [], 0

    async def __call__(self, op, body, approval=None, account=None):
        self.calls.append(op)
        if op == "users.register":
            return {"ok": True, "result": {"end_user_id": "usr_1"}}
        if op == "venue.booking_status":
            st = self.states.get(body["act_id"])
            if st is None:
                return {"ok": False, "error": {"code": "not_found", "message": "No sent booking with that act_id for this account."}}
            return {"ok": True, "result": {"act_id": body["act_id"], "state": st, "venue_words": {"untrusted_text": WORDS.get(st, "")} if st in WORDS else {},
                                           "say": "Another time was offered — nothing is booked; ask the person." if st == "proposed" else "ok"}}
        if op == "venue.cancel_booking":
            if body["act_id"] == "act_form":
                return {"ok": True, "result": {"status": "not_allowed", "say": "That booking was made on their own form — cancel it there.",
                                               "link": "https://venue.test/manage"}}
            if not approval:
                return {"ok": False, "error": {"code": "approval_required", "details": {"read_back_id": "rb_c1", "read_back": {"lines": [
                    "Cancel: Taverna Correo · Thu 22 Oct 2026 · 21:00 · 4 people · Alex Example"]}}}}
            self.cancels += 1
            return {"ok": True, "result": {"status": "sent", "cancel_act_id": "act_cancel"}}
        if op == "sandbox.simulate_approval":
            return ({"ok": True, "result": {"approval_id": "apv_1"}} if "yes" in body["said"].lower()
                    else {"ok": False, "error": {"code": "no_explicit_yes"}})
        raise AssertionError(op)


class Base(unittest.TestCase):
    def setUp(self):
        self.api = Sandbox()
        for p in (mock.patch.object(VS, "CALL", self.api), mock.patch.dict(VS._ACTS, {}, clear=True), mock.patch.dict(VS._USERS, {}, clear=True),
                  mock.patch.object(VS, "target", mock.AsyncMock(return_value="sandbox")),
                  mock.patch.object(M, "put_kind", mock.AsyncMock(return_value=True)), mock.patch.object(M, "kind", mock.AsyncMock(return_value=None))):
            p.start()
            self.addCleanup(p.stop)
        VS._ACTS[ACCT] = [{"act_id": "act_mail", "venue": "Taverna Correo", "when": "2026-10-22T21:00", "party": 4, "state": "sent", "at": 1}]

    def rows(self):
        return run(VS.bookings(ACCT))

    def line(self):
        return ST.decide({"venues": self.rows(), "booked": [], "failed": []})


class TheVenuesOwnAnswer(Base):
    def test_sent_is_a_request_not_a_booking(self):
        self.api.states["act_mail"] = "sent"
        self.assertEqual(self.rows()[0]["status"], "requested")
        self.assertEqual(self.line()["state"], "requested")

    def test_confirmed_carries_their_words(self):
        self.api.states["act_mail"] = "confirmed"
        r = self.rows()[0]
        self.assertEqual(r["status"], "confirmed")
        self.assertEqual(r["venue_said"]["untrusted_text"], WORDS["confirmed"])
        self.assertTrue(self.line()["line"].startswith("Booked: Taverna Correo"))

    def test_proposed_is_never_booked_and_asks_the_person(self):
        self.api.states["act_mail"] = "proposed"
        r = self.rows()[0]
        self.assertEqual(r["status"], "proposed")
        self.assertEqual(r["venue_said"]["untrusted_text"], WORDS["proposed"])
        self.assertIn("ask the person", r["how"])
        d = self.line()
        self.assertEqual(d["state"], "proposed")
        self.assertIn("they offered another time", d["line"])
        self.assertNotIn("Booked", d["line"])

    def test_declined_is_said_as_their_no(self):
        self.api.states["act_mail"] = "declined"
        r = self.rows()[0]
        self.assertEqual((r["status"], r["venue_said"]["untrusted_text"]), ("declined", WORDS["declined"]))
        self.assertEqual(self.line()["state"], "declined")
        self.assertIn("the venue said no", self.line()["line"])

    def test_an_answered_act_isnt_asked_again(self):
        self.api.states["act_mail"] = "confirmed"
        self.rows()
        n = self.api.calls.count("venue.booking_status")
        self.rows()
        self.assertEqual(self.api.calls.count("venue.booking_status"), n)

    def test_a_form_booking_is_asked_once_then_left(self):
        VS._ACTS[ACCT] = [{"act_id": "act_form", "venue": "Sasha Test Venue", "when": "2026-10-29T20:00", "party": 2, "state": "confirmed", "at": 1}]
        self.rows()
        self.rows()
        self.assertEqual(self.api.calls.count("venue.booking_status"), 1)
        self.assertEqual(self.rows()[0]["status"], "confirmed")


class Ctx:
    def __init__(self, said="", ago=0):
        self.account, self.user_said, self.idem, self.claimed = ACCT, said, None, None
        self.started = datetime.now(timezone.utc) + timedelta(seconds=ago)


class CancelThroughAgAPI(Base):
    def setUp(self):
        super().setUp()
        self.api.states["act_mail"] = "confirmed"
        for p in (mock.patch.dict(VN._CANCEL, {}, clear=True), mock.patch("agapi.v0.claim", mock.AsyncMock())):
            p.start()
            self.addCleanup(p.stop)

    def test_read_back_then_yes_then_the_venues_reply(self):
        out = run(VN._cancel_act(Ctx("Cancel Taverna Correo", ago=-1), {"act_id": "act_mail"}, None, "", lambda s: "yes" in s.lower()))
        self.assertEqual(out["status"], "awaiting_yes")
        self.assertIn("Cancel: Taverna Correo", out["read_back"][0])
        self.assertEqual(self.api.cancels, 0)                                   # nothing sent before their yes
        held = VN._CANCEL[ACCT]
        self.assertEqual(len(held.get("sha") or ""), 64)   # found live: without it the one-yes gate (CR 76) refused their yes (no_read_back)
        out = run(VN._cancel_act(Ctx("Yes, cancel it.", ago=5), {}, held, "Yes, cancel it.", lambda s: "yes" in s.lower()))
        self.assertEqual(out["status"], "requested")
        self.assertTrue(out["line"].startswith("Cancelled — I've asked Taverna Correo to cancel"), out)   # Sasha 314 MOVED: Tyler's words
        self.assertTrue(out["line"].endswith("I'll tell you when they confirm."))
        self.assertEqual(self.api.cancels, 1)
        self.api.states["act_cancel"] = "sent"
        self.assertEqual(self.rows()[0]["status"], "confirmed")                 # not cancelled until the venue says so
        self.assertIn("cancel", self.rows()[0])
        self.api.states["act_cancel"] = "confirmed"
        self.assertEqual(self.rows()[0]["status"], "cancelled")

    def test_no_yes_no_cancel(self):
        run(VN._cancel_act(Ctx("Cancel it", ago=-1), {"act_id": "act_mail"}, None, "", lambda s: False))
        with self.assertRaises(Exception):
            run(VN._cancel_act(Ctx("hmm", ago=5), {}, VN._CANCEL[ACCT], "hmm", lambda s: False))
        self.assertEqual(self.api.cancels, 0)

    def test_a_form_booking_is_cancelled_on_their_own_page(self):
        out = run(VN._cancel_act(Ctx("Cancel it", ago=-1), {"act_id": "act_form"}, None, "", lambda s: True))
        self.assertEqual(out["status"], "not_cancelled")
        self.assertEqual(out["page_url"], "https://venue.test/manage")


class ExactlyTheOneTheyMean(Base):
    """Found live on /s2: two confirmed Taverna Correo tables on 22 October — "cancel the duplicate, reference TCO-75C655" — she
    couldn't say which (cancel_venue took a venue name only). A quoted reference names the act; two that match are asked, never
    guessed; the act_id get_status lists is accepted (on the one path: old S1's schema untouched)."""

    def setUp(self):
        super().setUp()
        VS._ACTS[ACCT] = [{"act_id": "act_a", "venue": "Taverna Correo", "when": "2026-10-22T21:00", "party": 4, "state": "sent", "at": 1},
                          {"act_id": "act_b", "venue": "Taverna Correo", "when": "2026-10-22T21:00", "party": 4, "state": "sent", "at": 2}]
        self.api.states.update(act_a="confirmed", act_b="confirmed")
        self.words = {"act_a": "Confirmed … Reference TCO-8C9027. See you then!", "act_b": "Confirmed … Reference TCO-75C655. See you then!"}
        real = self.api.__call__

        async def call(op, body, approval=None, account=None):
            r = await real(op, body, approval=approval, account=account)
            if op == "venue.booking_status" and r.get("ok"):
                r["result"]["venue_words"] = {"untrusted_text": self.words[body["act_id"]]}
            return r
        p = mock.patch.object(VS, "CALL", call)
        p.start()
        self.addCleanup(p.stop)

    def test_a_quoted_reference_names_the_act(self):
        rows = self.rows()
        self.assertEqual(VN._which_act(rows, "cancel the duplicate, reference TCO-75C655")["act_id"], "act_b")
        self.assertIsNone(VN._which_act(rows, "cancel one of them"))

    def test_two_that_match_are_asked_never_guessed(self):
        with mock.patch.object(VN, "venue_bookings", mock.AsyncMock(return_value=self.rows())), \
                mock.patch.dict(VN._CANCEL, {}, clear=True), mock.patch.object(VN, "_API", lambda: object()):
            with self.assertRaises(Exception) as e:
                run(VN.cancel_venue(Ctx("cancel my Taverna Correo booking", ago=-1), {"venue": "Taverna Correo"}))
        self.assertIn("act_id", str(e.exception))

    def test_the_schema_takes_act_id_on_the_one_path_only(self):
        from agapi import v0 as API
        tool = next(API.schema_for_model(t) for t in API.TOOLS if t["name"] == "cancel_venue")
        self.assertNotIn("act_id", tool["input_schema"]["properties"])        # old S1's schema, as it was
        self.assertIn("act_id", VN.with_act(tool)["input_schema"]["properties"])


class OnePlaceForEverySurface(unittest.TestCase):
    def test_cancel_venue_routes_an_act_through_agapi(self):
        import inspect
        src = inspect.getsource(VN.cancel_venue)
        self.assertIn("_cancel_act(", src)
        self.assertIn("venue.cancel_booking", inspect.getsource(VS.cancel_read_back))


if __name__ == "__main__":
    unittest.main()
