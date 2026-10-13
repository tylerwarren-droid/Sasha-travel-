"""Sasha 254 · item 3 — "I'LL HANDLE IT", LIVE. When the booking rules say Sasha sends it ("Handle it" → fill_form_zero_touch, or a
request), the send is AgAPI's venue.submit_booking (agapi-live v1.8.0, CR 90) through the ONE route: venue.prepare_booking → the read-back
(submit_booking without an approval → approval_required + read_back_id) → on their yes in a LATER turn, the approval (sandbox:
sandbox.simulate_approval with their words; live: their tap, approvals.status) → submit_booking with AgAPI-Approval-Id → said in her
voice. "not_allowed" → kindly, with their prepared page. venue.booking_status → get_status (the one status).

Offline: AgAPI is a recorder (every op and body kept; nothing leaves the process); the booking API is the venue suite's recorder.

    cd backend && python -m unittest tests.test_s254_handle_it_live -v
"""
from __future__ import annotations

import asyncio
import unittest
from datetime import timedelta
from unittest import mock

from agapi import booking_decide as BD, s2_outcomes as OC, s2_status as SS, v0 as API, venue_submit as VS, venues as VN
from agapi.booking_rules import booking_rules as BR
from app.agent import voice as V
from tests.test_s254_one_decider import ALL4, Base

run = asyncio.run
PREP = "vpr_" + "a" * 32
RB = "rb_01JABCDEFGHJKMNPQRSTVWXYZ0"
APV = "apv_01JABCDEFGHJKMNPQRSTVWXYZ0"


class FakeAgapi:
    """AgAPI as CR 90 answers it — every call recorded (op, body, approval)."""

    def __init__(self):
        self.calls = []
        self.submit = {"prepared_id": PREP, "status": "sent", "submitted": True, "act_id": "act_1", "venue": "Casa Gate",
                       "say": "Sent to Casa Gate."}
        self.approval_state = "valid"
        self.state = "sent"

    async def __call__(self, op, body, approval=None, account=None):
        self.calls.append((op, body, approval))
        if op == "users.register":
            return {"ok": True, "result": {"end_user_id": "eu_254"}}
        if op == "venue.prepare_booking":
            return {"ok": True, "result": {"venue_id": "v_1", "venue": "Casa Gate", "submitted": False, "prepared_id": PREP,
                                           "zero_touch_allowed": True, "link": "https://agapi.test/prepared/casagate", "say": "ready"}}
        if op == "venue.submit_booking" and not approval:
            return {"ok": False, "error": {"code": "approval_required", "message": "the person's yes first", "retryable": False,
                                           "details": {"read_back_id": RB, "read_back": {"lines": [
                                               "I'll send Casa Gate's own booking form: 2 people, under Alex Gate.",
                                               "Nothing is booked until they confirm."]}}}}
        if op == "sandbox.simulate_approval":
            return {"ok": True, "result": {"approval_id": APV}}
        if op == "approvals.request":
            return {"ok": True, "result": {"read_back_id": RB, "presentation": {"channel": body["channel"]}}}
        if op == "approvals.status":
            return {"ok": True, "result": {"read_back_id": RB, "approval": {"approval_id": APV, "state": self.approval_state}}}
        if op == "venue.submit_booking":
            return {"ok": True, "result": dict(self.submit)}
        if op == "venue.booking_status":
            return {"ok": True, "result": {"act_id": body["act_id"], "state": self.state, "venue": "Casa Gate",
                                           "venue_words": {"text": "Confirmado, os esperamos."}, "say": "x"}}
        return {"ok": False, "error": {"code": "unknown_op", "message": op}}

    def ops(self):
        return [c[0] for c in self.calls]

    def body(self, op):
        return next(b for o, b, _a in self.calls if o == op)


class HandleIt(Base):
    target = "sandbox"

    def setUp(self):
        super().setUp()
        VS._USERS.clear()
        VS._ACTS.pop("00000000-0000-4000-8000-000000000254", None)
        self.agapi = FakeAgapi()
        for p in (mock.patch.object(VS, "CALL", self.agapi), mock.patch.object(VS, "target", mock.AsyncMock(return_value=self.target)),
                  mock.patch("agapi.s2_memory.put_kind", mock.AsyncMock(return_value=True)),
                  mock.patch("agapi.s2_memory.kind", mock.AsyncMock(return_value=None))):
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(VS._ACTS.clear)

    def handle_it(self, rungs=None, **a):
        return self.hold(rungs or {"form": {}, "email": ALL4["email"]}, route="form", website="https://casagate.es", **a)


class TheSend(HandleIt):
    def test_handle_it_read_back_then_yes_then_submit_booking(self):
        out = self.handle_it()
        self.assertEqual((out["status"], out["route"], out["rules"]["action"]), ("awaiting_yes", "agapi", "fill_form_zero_touch"))
        self.assertEqual(out["read_back"][0], "I'll send Casa Gate's own booking form: 2 people, under Alex Gate.")   # AgAPI's read-back
        self.assertEqual(self.agapi.ops(), ["venue.prepare_booking", "users.register", "venue.submit_booking"])   # nothing sent yet
        prep = self.agapi.body("venue.prepare_booking")
        self.assertEqual((prep["person"]["name"], prep["person"]["phone"], prep["party"]), ("Alex Gate", "+447700900211", 2))
        self.assertEqual(prep["place"]["website"], "https://casagate.es")
        self.assertEqual(self.agapi.calls[-1][2], None)                                         # the read-back call carries no approval
        self.assertFalse(any(p in ("/api/booking/forms", "/api/booking/emails") for p in self.api.paths()))   # Sasha's own senders: unused
        got = self.yes()
        self.assertEqual(self.agapi.ops()[-2:], ["sandbox.simulate_approval", "venue.submit_booking"])
        self.assertEqual(self.agapi.calls[-2][1], {"read_back_id": RB, "said": "yes, go ahead"})          # their own words
        op, body, approval = self.agapi.calls[-1]
        self.assertEqual((body, approval), ({"end_user": "eu_254", "prepared_id": PREP}, APV))
        self.assertEqual(got["status"], "requested")
        self.assertEqual(got["line"], f"{V.SENT} {BR.PHRASES['takeover']}")                     # "Sent. I'll tell you when they reply."
        self.assertNotIn(ACCT := "00000000-0000-4000-8000-000000000254", VN._HELD)
        rec = OC.booked.await_args
        self.assertEqual((rec.args[1]["rung"], rec.args[1]["agapi_action"]), ("agapi", "fill_form_zero_touch"))

    def test_a_yes_in_the_same_turn_sends_nothing(self):
        self.handle_it()
        same = self.ctx("yes")
        same.started = VN._HELD["00000000-0000-4000-8000-000000000254"]["at"]                    # the turn the read-back was said in
        with self.assertRaises(API.ToolError) as e:
            run(VN.book_venue(same, {"approval": {"said": "yes"}}))
        self.assertEqual(e.exception.code, "read_back_first")
        self.assertNotIn("sandbox.simulate_approval", self.agapi.ops())

    def test_a_request_by_email_goes_the_same_way(self):
        out = self.hold({"email": ALL4["email"], "phone": ALL4["phone"]}, hours=72)
        self.assertEqual((out["route"], out["rules"]["action"]), ("agapi", "request_email"))
        got = self.yes()
        self.assertEqual(got["line"], f"{BR.PHRASES['request_wait']} {BR.PHRASES['takeover']}")
        self.assertNotIn("/api/booking/emails", self.api.paths())

    def test_confirmed_at_once_is_booked_with_their_reference(self):
        self.agapi.submit.update(status="confirmed", reference="CG-77")
        self.handle_it()
        got = self.yes()
        self.assertEqual((got["status"], got["reference"]), ("confirmed", "CG-77"))
        self.assertTrue(got["line"].startswith("✅ Booked: Casa Gate"))

    def test_not_allowed_is_said_kindly_with_their_prepared_page(self):
        self.agapi.submit.update(status="not_allowed", submitted=False, act_id=None)
        self.handle_it()
        got = self.yes()
        self.assertEqual(got["status"], "not_allowed")
        self.assertEqual(got["say"], f"{BR.PHRASES['no_real_sends']} {BR.PHRASES['takeover']}")
        self.assertEqual(got["page_url"], "https://agapi.test/prepared/casagate")
        from app.agent import sasha as AG
        self.assertEqual(AG.render("book_venue", got, {})["kind"], "handover")                   # their page, drawn

    def test_not_allowed_at_the_read_back_is_said_kindly_not_an_error(self):   # found by the gate on agapi-live (deploy c59733b0)
        real = self.agapi.__call__

        async def refuse_early(op, body, approval=None, account=None):
            if op == "venue.submit_booking" and not approval:
                self.agapi.calls.append((op, body, approval))
                return {"ok": True, "result": {"status": "not_allowed", "submitted": False, "say": "not granted",
                                               "link": "https://agapi.test/prepared/casagate"}}
            return await real(op, body, approval, account)
        with mock.patch.object(VS, "CALL", refuse_early):
            out = self.handle_it()
        self.assertEqual(out["status"], "not_contacted")
        self.assertTrue(out["not_allowed"])
        self.assertTrue(out["say"].startswith(BR.PHRASES["no_real_sends"]))
        self.assertEqual(out["page_url"], "https://agapi.test/prepared/casagate")

    def test_no_key_here_is_sashas_own_sender(self):
        self.agapi.prepare_off = True

        async def off(op, body, approval=None, account=None):
            return {"ok": False, "error": {"code": "not_configured", "message": "off"}}
        with mock.patch.object(VS, "CALL", off):
            out = self.handle_it()
        self.assertEqual(out["route"], "form")
        self.assertIn("/api/booking/forms", self.api.paths())


class Live(HandleIt):
    target = "live"

    def test_live_their_tap_is_the_approval(self):
        self.handle_it()
        self.assertEqual(self.agapi.body("approvals.request"), {"read_back_id": RB, "channel": "link_sms"})
        self.agapi.approval_state = "presented"
        got = self.yes()
        self.assertEqual(got["status"], "waiting_for_their_tap")
        self.assertNotIn("venue.submit_booking", [o for o, _b, a in self.agapi.calls if a])        # nothing sent before the tap
        self.assertIn("00000000-0000-4000-8000-000000000254", VN._HELD)                             # still held for it
        self.agapi.approval_state = "valid"
        VN._HELD["00000000-0000-4000-8000-000000000254"]["at"] -= timedelta(minutes=1)
        got = self.yes()
        self.assertEqual(got["status"], "requested")
        self.assertEqual(self.agapi.calls[-1][2], APV)


class TheStatus(HandleIt):
    def test_booking_status_confirmed_get_status_says_booked(self):
        self.handle_it()
        self.yes()
        self.agapi.state = "confirmed"
        with mock.patch.object(API, "_latest", mock.AsyncMock(return_value=None)):
            st = run(SS.status_of("00000000-0000-4000-8000-000000000254"))
        self.assertEqual(st["state"], "booked")
        self.assertTrue(st["line"].startswith("Booked: Casa Gate"), st["line"])
        self.assertIn("venue.booking_status", self.agapi.ops())
        row = next(v for v in st["venues"] if v.get("act_id") == "act_1")
        self.assertEqual(row["venue_said"], {"untrusted_text": "Confirmado, os esperamos."})   # their words, as data

    def test_still_waiting_is_requested(self):
        self.handle_it()
        self.yes()
        with mock.patch.object(API, "_latest", mock.AsyncMock(return_value=None)):
            st = run(SS.status_of("00000000-0000-4000-8000-000000000254"))
        self.assertEqual(st["state"], "requested")


class TheRoute(unittest.TestCase):
    def test_a_test_person_goes_to_the_sandbox_through_the_one_route(self):
        from agapi import agapi_route as AR
        with mock.patch.object(AR, "person_mode", mock.AsyncMock(return_value="test")):
            self.assertEqual(run(VS.target("00000000-0000-4000-8000-000000000254")), "sandbox")
        seen = []

        async def client_for(family, account=None, *a, **k):
            seen.append((family, account))
            return "https://agapi.test", ""
        with mock.patch.object(AR, "client_for", client_for):
            r = run(VS._agapi("venue.prepare_booking", {}, account="acct-1"))
        self.assertEqual((seen, r["error"]["code"]), ([("venues", "acct-1")], "not_configured"))


if __name__ == "__main__":
    unittest.main()
