"""Sasha 271 · S2 — HOTEL CALLS THROUGH THE ENGINE (CR 102, AgAPI v1.17.0) + the new arrival + the green ring + the disappearing bug.
    A  a hotel stay is a booking act like a table: venue.prepare_booking stay {nights, room?} with the hotel's number; the read-back is
       the engine's; after the ONE yes, submit_booking's call_plan (R6, arriving within 24 h) is dialled exactly as a table's call; the
       R5 call opens (venue.call_again) only when venue.booking_status.follow_up.due — Sasha keeps no clock and decides no call
    B  her arrival: "Hey there" (a return: "Hey <name>"), then at once voice.CAMERA_OFF — then the corner (frontend; lines from voice.py)
    C  she never vanishes: one element, measured to the corner, never portalled into a slot that may be gone (frontend test too)
    D  the corner's ring: green awake and listening, a calm paused look with "Wake" (lib/presence-rule.mjs)
Offline: AgAPI is a recorder (CR 102's answers); nothing leaves the process; no Places, no model.
    cd backend && python -m unittest tests.test_s271 -v
"""
from __future__ import annotations

import asyncio
import inspect
import pathlib
import unittest
from unittest import mock

from agapi import venue_calls as VC, venue_submit as VS, venues as VN
from app.agent import voice as V
from booking_signer import proactive as PR
from tests.test_s254_handle_it_live import use_fake_agapi
from tests.test_s254_one_decider import ALL4, Base

BACKEND = pathlib.Path(__file__).resolve().parents[1]
FRONT = BACKEND.parent / "frontend"
run = asyncio.run


def _front(case, rel):
    f = FRONT / rel
    if not f.exists():
        case.skipTest("frontend/ is not in this checkout (a backend-only build)")
    return f.read_text()
R6_SAY = "On it — I've emailed Hotel Gate, and I'll call them now too and let you know."
PLAN = {"call_id": "vcp_r6", "reason": "R6", "phone": "+34910000000", "source": "venue", "when": "now", "simulate": True}


class TheStayIsTheEnginesAct(Base):
    def test_a_stay_is_prepared_with_its_stay_and_the_hotels_number(self):
        fake = use_fake_agapi(self)
        out = self.hold({"email": ALL4["email"], "phone": ALL4["phone"]}, hours=96, what="a room", venue="Hotel Gate", nights=3, room="a double")
        self.assertEqual((out["status"], out["route"]), ("awaiting_yes", "agapi"))
        body = fake.body("venue.prepare_booking")
        self.assertEqual((body["stay"], body["party"], body["call"]), ({"nights": 3, "room": "a double"}, 2, {"phone": "+34910000000", "source": "venue"}))
        self.assertNotIn("notes", body)                                                     # the stay says it — never free text
        self.assertEqual(out["read_back"][0], "I'll send Casa Gate's own booking form: 2 people, under Alex Gate.")   # the ENGINE's read-back
        self.assertEqual(self.api.bodies("/api/booking/emails"), [])                        # never Sasha's own room email
        got = self.yes()
        self.assertEqual(got["status"], "requested")
        self.assertNotIn("call", got)                                                       # far out: a request, no call yet

    def test_a_table_carries_no_stay_and_no_number(self):
        fake = use_fake_agapi(self)
        self.hold({"email": ALL4["email"], "phone": ALL4["phone"]}, hours=72)
        body = fake.body("venue.prepare_booking")
        self.assertNotIn("stay", body)
        self.assertNotIn("call", body)

    def test_r6_the_engines_call_plan_dialled_under_the_one_yes(self):
        fake = use_fake_agapi(self, {"call_plan": PLAN, "say": R6_SAY, "approval": {"inherited": True, "approval_id": "apv_1", "asked_again": False}})
        dialled = []

        async def dial(account, res, held):
            dialled.append((res["act_id"], res["call_plan"]["call_id"]))
            return {"status": "simulated"}
        with mock.patch.object(VC, "dial", dial), mock.patch.object(VC, "again", mock.AsyncMock(side_effect=AssertionError("Sasha's own R6"))):
            self.hold({"email": ALL4["email"], "phone": ALL4["phone"]}, hours=10, what="a room", venue="Hotel Gate", nights=1)
            got = self.yes()
        self.assertEqual((got["line"], got["call"]["status"], got["call"]["reason"]), (R6_SAY, "calling", "R6"))
        self.assertEqual(dialled, [("act_1", "vcp_r6")])
        self.assertEqual(fake.ops().count("venue.submit_booking"), 2)                      # the read-back, then the ONE send

    def test_no_booking_service_a_stay_is_said_never_sasha_s_own_email(self):
        async def none(*a, **k):
            return {"ok": False, "error": {"code": "not_configured", "message": "no key"}}
        with mock.patch.object(VS, "prepare", none):
            with self.assertRaises(Exception) as e:
                self.hold({"email": ALL4["email"], "phone": ALL4["phone"]}, hours=96, what="a room", venue="Hotel Gate", nights=2)
        self.assertIn("take it over", str(getattr(e.exception, "message", e.exception)))
        self.assertEqual(self.api.bodies("/api/booking/emails"), [])


class TheStatusIsTheEngines(unittest.TestCase):
    def test_booking_and_follow_up_are_kept_as_the_engine_says_them(self):
        self.assertIn("booking", VS.STATUS_KEYS)
        self.assertIn("follow_up", VS.STATUS_KEYS)
        stay = {"kind": "stay", "check_in": "2026-10-20", "check_out": "2026-10-23", "nights": 3, "guests": 2, "room": "double", "arrival": "15:00",
                "name": "Alex"}
        self.assertEqual(VS.stay_of(stay), {k: stay[k] for k in ("check_in", "check_out", "nights", "guests", "room", "arrival")})

    def test_an_act_keeps_no_time_or_flag_to_decide_a_call_from(self):
        kept = VS._follow_up_of({"call_source": "venue", "venue_phone": "+34910000000", "r6": True, "category": "hotel", "stay": {"nights": 2}})
        self.assertEqual(kept, {"call_source": "venue", "stay": {"nights": 2}})   # Sasha 272: its source only — the number is the record's


class NoSecondCopy(unittest.TestCase):
    def test_no_clock_of_sasha_s_own_for_r5(self):
        src = inspect.getsource(PR.no_reply_offers)
        for gone in ("decide_for", "request_sent_at", "venue_replied", "sent_at", "venue_type"):
            self.assertNotIn(gone, src)
        self.assertIn('fu.get("due")', src)                                                # only when booking_status says due
        self.assertIn("VS.status(account", src)

    def test_no_r6_call_of_sasha_s_own(self):
        src = (BACKEND / "agapi" / "venues.py").read_text()
        self.assertNotIn('"R6")', src)
        self.assertNotIn("r6=True", src)
        self.assertNotIn('held.get("r6")', src)
        self.assertIn('if r.get("call_plan") and r.get("act_id"):', src)
        # the one path: a stay never takes Sasha's own room email, call or "no act" refusal
        ex = src[src.index("async def _execute("):src.index("async def _call_question(")]
        self.assertNotIn("not at or open_slot or nights", ex)
        self.assertNotIn("if at and not open_slot and not nights:", ex)


class HerArrivalsWords(unittest.TestCase):
    def test_hey_there_then_the_camera_off_line(self):
        self.assertEqual(V.CAMERA_OFF, "I'm turning my camera off — just talk, or tap to see me.")   # Sasha 281 · MOVED: one short line
        # Sasha 295 · MOVED: her hello says what she does ("Hey there" left him guessing), and is said only after his tap
        self.assertEqual(V.arrival_line(), f"Hi — what shall I book for you? {V.CAMERA_OFF}")
        self.assertEqual(V.arrival_line("Tyler Warren", back=True), f"Hi Tyler — what shall I book for you? {V.CAMERA_OFF}")
        self.assertEqual(V.arrival_line("Tyler", back=False), f"Hi — what shall I book for you? {V.CAMERA_OFF}")   # a first visit: no name
        self.assertEqual(V.arrival_line(None, back=True), f"Hi — what shall I book for you? {V.CAMERA_OFF}")

    def test_the_page_reads_them_from_voice_py(self):
        from app.agent import sasha as S
        got = run(S.first_line_rule())
        self.assertEqual((got["hello"], got["hello_back"], got["camera_off"]), (V.HELLO, V.HELLO_BACK, V.CAMERA_OFF))
        fl = _front(self, "lib/first-line.ts")
        # Sasha 281 · MOVED: the camera words join the hello only when her live face says it (presence-rule withCamera)
        self.assertIn("return withCamera(back && first ? rule.helloBack.replace('{name}', first) : rule.hello, rule.cameraOff, live)", fl)
        hello = _front(self, "app/s2/S2Hello.tsx")
        self.assertIn("arrivalLine(nameRef.current ?? null, !!back.current, live)", hello)
        self.assertNotIn("helloLine", hello)


class OnScreenIsOneRule(unittest.TestCase):
    def test_presence_rule_is_tested_and_drawn_from(self):
        self.assertIn("scripts/presence-rule.test.mjs", _front(self, "package.json"))
        hello = _front(self, "app/s2/S2Hello.tsx")
        self.assertIn("const p = presence({", hello)
        self.assertNotIn("createPortal", hello)                                             # C: never into a slot that may be gone
        self.assertIn("c.dataset.drawn = '0'", hello)                                       # C: a released live face shows her still


if __name__ == "__main__":
    unittest.main()
