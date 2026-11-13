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
from tests.test_s254_one_decider import ALL4, Base, signed_in  # noqa: F401 · signed_in: other suites import it from here

run = asyncio.run
PREP = "vpr_" + "a" * 32
RB = "rb_01JABCDEFGHJKMNPQRSTVWXYZ0"
APV = "apv_01JABCDEFGHJKMNPQRSTVWXYZ0"
MDT = "mdt_01JABCDEFGHJKMNPQRSTVWXYZ0"


def booking_now(b: dict, venue: str = "Casa Gate") -> str:
    """AgAPI's instructed.say (CR 196, venue_submit.booking_now) for a fake's booking: "Booking now: <venue>, <N> people, <Fri 14 Nov> at <21:00>."."""
    from datetime import date
    d = date.fromisoformat(b["date"])
    n = int(b["party"])
    return f"Booking now: {venue}, {n} {'person' if n == 1 else 'people'}, {d:%a} {d.day:02d} {d:%b} at {b['time']}."


class FakeAgapi:
    """AgAPI as CR 90 answers it — every call recorded (op, body, approval)."""

    def __init__(self):
        self.calls = []
        self.submit = {"prepared_id": PREP, "status": "sent", "submitted": True, "act_id": "act_1", "venue": "Casa Gate",
                       "say": "Sent to Casa Gate."}
        self.approval_state = "valid"
        self.state = "sent"
        self.mandates = []

    async def __call__(self, op, body, approval=None, account=None):
        self.calls.append((op, body, approval))
        if op == "users.register":
            return {"ok": True, "result": {"end_user_id": "eu_254"}}
        if op == "venue.prepare_booking":
            return {"ok": True, "result": {"venue_id": "v_1", "venue": "Casa Gate", "submitted": False, "prepared_id": PREP,
                                           "zero_touch_allowed": True, "link": "https://agapi.test/prepared/casagate", "say": "ready"}}
        if op == "approvals.mandate":   # Sasha 381 · CR 196 · the instruction recorded as the approval (a missing term: asked)
            missing = [k for k in ("prepared_id", "party", "date", "time") if (body["scope"].get("booking") or {}).get(k) in (None, "")]
            if missing:
                return {"ok": False, "error": {"code": "invalid_input", "message": "asked, never guessed",
                                               "details": {"path": "/scope/booking", "rule": "term_not_given", "missing": missing}}}
            self.mandates.append(body)
            return {"ok": True, "result": {"mandate_id": MDT, "expires_at": "2099-01-01T00:00:00Z", "proof": {"kind": body["proof"]["kind"]}}}
        if op == "venue.submit_booking" and body.get("mandate_id"):   # CR 196 · approved BY the instruction, acted at once
            b = self.mandates[-1]["scope"]["booking"] if self.mandates else {}
            return {"ok": True, "result": {**dict(self.submit), "instructed": {"mandate_id": body["mandate_id"], "say": booking_now(b)}}}
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
        return {"ok": False, "error": {"code": "unknown_operation", "message": op}}   # AgAPI's own code (agapi_service/app.py)

    def ops(self):
        return [c[0] for c in self.calls]

    def body(self, op):
        return next(b for o, b, _a in self.calls if o == op)


def use_fake_agapi(test: unittest.TestCase, submit: dict = None) -> FakeAgapi:
    """Sasha 270 · for tests MOVED off Sasha's own form sender: on the one path "Handle it" is AgAPI's send — faked as CR 90 answers."""
    fake = FakeAgapi()
    if submit:
        fake.submit.update(submit)
    signed_in(test)
    VS._USERS.clear()
    for p in (mock.patch.object(VS, "CALL", fake), mock.patch.object(VS, "target", mock.AsyncMock(return_value="sandbox")),
              mock.patch("agapi.s2_memory.put_kind", mock.AsyncMock(return_value=True)),
              mock.patch("agapi.s2_memory.kind", mock.AsyncMock(return_value=None))):
        p.start()
        test.addCleanup(p.stop)
    return fake


class HandleIt(Base):
    target = "sandbox"

    def setUp(self):
        super().setUp()
        VS._USERS.clear()
        VS._ACTS.pop("00000000-0000-4000-8000-000000000254", None)
        self.agapi = FakeAgapi()
        signed_in(self)
        for p in (mock.patch.object(VS, "CALL", self.agapi), mock.patch.object(VS, "target", mock.AsyncMock(return_value=self.target)),
                  mock.patch("agapi.s2_memory.put_kind", mock.AsyncMock(return_value=True)),
                  mock.patch("agapi.s2_memory.kind", mock.AsyncMock(return_value=None))):
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(VS._ACTS.clear)

    def handle_it(self, rungs=None, **a):
        return self.hold(rungs or {"form": {}, "email": ALL4["email"]}, route="form", website="https://casagate.es", **a)


class TheSend(HandleIt):
    """Sasha 381 · CR 196 · the instruction IS the approval: venue.prepare_booking → approvals.mandate scope.booking (the person's terms + the
    door's proof of THIS turn) → ONE venue.submit_booking {prepared_id, mandate_id} → AgAPI acts — in the SAME turn, said in ONE line:
    AgAPI's instructed.say + Requested / Booked. No read-back card, no tap."""

    def test_handle_it_is_sent_on_the_instruction_in_the_same_turn(self):
        got = self.handle_it()
        self.assertEqual(self.agapi.ops(), ["users.register", "venue.prepare_booking", "users.register", "approvals.mandate",
                                            "venue.submit_booking"])                                # ONE submit, no approval request
        prep = self.agapi.body("venue.prepare_booking")
        self.assertEqual((prep["person"]["name"], prep["person"]["phone"], prep["party"]), ("Alex Gate", "+447700900211", 2))
        self.assertEqual(prep["place"]["website"], "https://casagate.es")
        m = self.agapi.body("approvals.mandate")
        self.assertEqual(m["scope"], {"booking": {"prepared_id": PREP, "party": 2, "date": prep["date"], "time": prep["time"]}})
        self.assertEqual((m["proof"]["kind"], m["proof"]["message_id"]), ("whatsapp", "SM" + "4" * 32))   # THIS turn's own message
        self.assertNotIn("limits", m)
        sub = self.agapi.body("venue.submit_booking")
        self.assertEqual((sub["prepared_id"], sub["mandate_id"], self.agapi.calls[-1][2]), (PREP, MDT, None))   # approved BY the instruction
        self.assertFalse(any(p in ("/api/booking/forms", "/api/booking/emails") for p in self.api.paths()))   # Sasha's own senders: unused
        self.assertEqual(got["status"], "requested")
        self.assertRegex(got["line"], r"^Booking now: Casa Gate, 2 people, \w{3} \d{2} \w{3} at \d\d:\d\d\. Requested — I'll tell you when they reply\.$")
        self.assertNotIn(ACCT := "00000000-0000-4000-8000-000000000254", VN._HELD)
        rec = OC.booked.await_args
        self.assertEqual((rec.args[1]["rung"], rec.args[1]["agapi_action"]), ("agapi", "fill_form_zero_touch"))

    def test_no_verified_person_sends_nothing(self):
        VS.TAP.set(None)   # no signed-in session and no signed WhatsApp message: the instruction can't be proved theirs
        VS.WA.set(None)
        got = self.handle_it()
        self.assertNotIn("approvals.mandate", self.agapi.ops())
        self.assertNotIn("venue.submit_booking", self.agapi.ops())
        self.assertNotIn("sandbox.simulate_approval", self.agapi.ops())                          # never a simulated yes in its place
        self.assertEqual(got["status"], "not_sent")

    def test_a_request_by_email_goes_the_same_way(self):
        got = self.hold({"email": ALL4["email"], "phone": ALL4["phone"]}, hours=72)
        self.assertEqual(got["status"], "requested")
        self.assertTrue(got["line"].startswith("Booking now: Casa Gate, 2 people, ") and got["line"].endswith(V.REQUESTED), got["line"])
        self.assertNotIn("/api/booking/emails", self.api.paths())

    def test_confirmed_at_once_is_booked_with_their_reference(self):
        self.agapi.submit.update(status="confirmed", reference="CG-77")
        got = self.handle_it()
        self.assertEqual((got["status"], got["reference"]), ("confirmed", "CG-77"))
        self.assertIn(". Booked — reference CG-77.", got["line"])

    def test_not_allowed_is_said_kindly_with_their_prepared_page(self):
        why = "I can't send this one for you (no form of their own to send, and no WhatsApp or email to write to). The link I prepared is yours to finish — open it and confirm."
        self.agapi.submit.update(status="not_allowed", submitted=False, act_id=None, say=why)
        got = self.handle_it()
        self.assertEqual(got["status"], "not_allowed")
        self.assertEqual(got["say"], f"{V.FINISH_IT} {BR.PHRASES['takeover']}")                 # Sasha 380 · their page handed over; AgAPI's reason logged
        self.assertNotIn("on this account", got["say"])
        self.assertEqual(got["page_url"], "https://agapi.test/prepared/casagate")
        from app.agent import sasha as AG
        self.assertEqual(AG.render("hold_venue", got, {})["kind"], "handover")                   # their page, drawn

    def test_not_allowed_at_the_submit_is_said_kindly_not_an_error(self):   # found by the gate on agapi-live (deploy c59733b0)
        real = self.agapi.__call__

        async def refuse(op, body, approval=None, account=None):
            if op == "venue.submit_booking":
                self.agapi.calls.append((op, body, approval))
                return {"ok": True, "result": {"prepared_id": PREP, "status": "not_allowed", "submitted": False, "say": "not granted"}}
            return await real(op, body, approval, account)
        with mock.patch.object(VS, "CALL", refuse):
            out = self.handle_it()
        self.assertEqual(out["status"], "not_allowed")
        self.assertTrue(out["say"].startswith(V.FINISH_IT))                                      # Sasha 380 · their prepared page, in her voice
        self.assertNotIn(BR.PHRASES["no_real_sends"], out["say"])
        self.assertEqual(out["page_url"], "https://agapi.test/prepared/casagate")

    def test_no_key_here_is_sashas_own_sender(self):
        self.agapi.prepare_off = True

        async def off(op, body, approval=None, account=None):
            return {"ok": False, "error": {"code": "not_configured", "message": "off"}}
        with mock.patch.object(VS, "CALL", off):
            out = self.handle_it()
        # Sasha 319 · Sasha 378 (CR 188): AgAPI's send_form with no booking service here → Tyler's, nothing sent — never Sasha's own
        # form sender, and never a page of Sasha's choosing in its place
        self.assertEqual((out["status"], out["sent"]), ("to_tyler", False))
        self.assertNotIn("/api/booking/forms", self.api.paths())


class Live(HandleIt):
    target = "live"

    def test_live_the_instruction_is_the_approval_too(self):
        got = self.handle_it()
        self.assertNotIn("approvals.request", self.agapi.ops())   # Sasha 314: no SMS link
        self.assertNotIn("approvals.status", self.agapi.ops())    # never waiting for a tap: the instruction is it (CR 196)
        self.assertEqual((got["status"], self.agapi.body("approvals.mandate")["proof"]["kind"]), ("requested", "whatsapp"))


class TheStatus(HandleIt):
    def test_booking_status_confirmed_get_status_says_booked(self):
        self.handle_it()
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
