"""Sasha 272 · S2 — ONE BOOKING RECORD (CR 103, AgAPI v1.17.1): a Google listing's number is never Sasha's.
    1  venue.prepare_booking gets the call ONCE: a listing as {source "listing", place_id} with NO phone; the venue's own number (or the
       person's) as {phone, source "venue"|"person"}
    2  venue.submit_booking and venue.call_again carry NO call object — the booking record is the truth
    3  what to say and dial is AgAPI's: call_plan (submit_booking / call_again), call_attempt.next_step {their_listing, phone, link} at the
       take-over; no number at that moment → takeover {their_listing, link} + say → the no-channel line + their listing, never silent
    4  nothing of the number on Sasha's side: no digits, no hash on the act, the call row or a kept next_step; no Places read of Sasha's
       own for a booking's call (a scheduled dial asks the act again)
Offline: AgAPI is a recorder (CR 103's answers); nothing leaves the process; no Places, no model.
    cd backend && python -m unittest tests.test_s272 -v
"""
from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import pathlib
import unittest
from unittest import mock

from agapi import venue_calls as VC, venue_submit as VS, venues as VN
from agapi.booking_rules import booking_rules as BR
from app.agent import voice as V
from booking_signer import call_routes as CR, call_store as CS, calls as C, places_terms as PT, proactive as PR
from tests.test_s254_handle_it_live import use_fake_agapi
from tests.test_s254_one_decider import ACCT, ALL4, Base

BACKEND = pathlib.Path(__file__).resolve().parents[1]
run = asyncio.run
LISTED = "+15005550183"   # CR 103's fixture_place_hotel (fictional)
PID = "fixture_place_hotel"
LINK = "https://www.google.com/maps/search/?api=1&query=Hotel+Gate&query_place_id=fixture_place_hotel"
LISTING_FACTS = [{"kind": "phone", "source_kind": "places", "value": LISTED}]


def _holds_no_number(case, blob):
    s = json.dumps(blob, default=str)
    case.assertNotIn(LISTED[1:], s)
    case.assertNotIn(hashlib.sha256(LISTED.encode()).hexdigest(), s)


class TheCallIsGivenOnce(Base):
    def test_a_listing_stay_is_prepared_with_its_place_id_and_no_phone(self):
        fake = use_fake_agapi(self)
        self.hold({"email": ALL4["email"], "phone": {"value": LISTED}}, hours=96, what="a room", venue="Hotel Gate", nights=2,
                  facts=LISTING_FACTS, place_id=PID)
        self.assertEqual(fake.body("venue.prepare_booking")["call"], {"source": "listing", "place_id": PID})
        self.yes()
        for op, body, _a in fake.calls:
            if op != "venue.prepare_booking":
                self.assertNotIn("call", body, op)                                            # 2: never passed again
        _holds_no_number(self, [b for o, b, _a in fake.calls if o != "venue.prepare_booking"])
        act = next(a for a in run(VS.acts_of(ACCT)) if a["act_id"] == "act_1")
        self.assertEqual((act["call_source"], act["place_id"]), ("listing", PID))
        _holds_no_number(self, act)                                                           # 4: the act keeps its source only

    def test_the_venues_own_number_once_with_its_source(self):
        fake = use_fake_agapi(self)
        self.hold({"email": ALL4["email"], "phone": ALL4["phone"]}, hours=96, what="a room", venue="Hotel Gate", nights=2)
        self.assertEqual(fake.body("venue.prepare_booking")["call"], {"phone": "+34910000000", "source": "venue"})
        self.yes()
        self.assertNotIn("call", [b for o, b, _a in fake.calls if o == "venue.submit_booking"][-1])

    def test_call_of_never_reads_the_digits(self):
        rd = {"facts": LISTING_FACTS}
        self.assertEqual(VN.call_of(rd, None, PID), {"source": "listing", "place_id": PID})
        self.assertIsNone(VN.call_of(rd, None, None))
        self.assertIsNone(VN.call_of({"facts": []}, None, PID))
        self.assertFalse(hasattr(VN, "listing_number"))


class NothingPassedAgain(unittest.TestCase):
    def test_read_back_submit_and_call_again_take_no_call(self):
        for fn in (VS.read_back, VS.call_again):
            self.assertNotIn("call", inspect.signature(fn).parameters)
        src = inspect.getsource(VS.submit)
        self.assertNotIn('"call": call', src)
        self.assertNotIn("held.get(\"call\")", src)

    def test_again_sends_only_act_and_reason(self):
        ops = []

        async def call(op, body, approval=None, account=None):
            ops.append((op, body))
            if op == "users.register":
                return {"ok": True, "result": {"end_user_id": "eu_1"}}
            return {"ok": True, "result": {"act_id": "act_1", "status": "not_allowed", "say": f"{BR.PHRASES['no_channel']} {LINK}",
                                           "takeover": {"kind": "their_listing", "link": LINK}}}
        acts = [{"act_id": "act_1", "venue": "Hotel Gate", "state": "sent", "call_source": "listing", "place_id": PID}]
        with mock.patch.object(VS, "CALL", call), mock.patch.object(VS, "acts_of", mock.AsyncMock(return_value=acts)), \
                mock.patch.object(PT, "listing_number", mock.AsyncMock(side_effect=AssertionError("Sasha's own Places read"))):
            VS._USERS.clear()
            got = run(VC.again(ACCT, "act_1", "R5"))
        self.assertEqual([b for o, b in ops if o == "venue.call_again"], [{"act_id": "act_1", "reason": "R5", "end_user": "eu_1"}])
        # 3: no number now → the no-channel line + their listing, with it on the card — never a silent skip
        self.assertEqual(got["say"], f"{BR.PHRASES['no_channel']} {LINK}")
        self.assertEqual(got["card"]["page"], LINK)


class SaidFromTheRecord(Base):
    def test_r6_at_the_yes_with_no_number_now_is_said_with_their_listing(self):
        use_fake_agapi(self, {"call_plan": None, "takeover": {"kind": "their_listing", "link": LINK},
                              "say": f"On it — I've emailed Hotel Gate. {BR.PHRASES['no_channel']} {LINK}"})
        with mock.patch.object(VC, "dial", mock.AsyncMock(side_effect=AssertionError("dialled with no number"))):
            self.hold({"email": ALL4["email"], "phone": {"value": LISTED}}, hours=10, what="a room", venue="Hotel Gate", nights=1,
                      facts=LISTING_FACTS, place_id=PID)
            got = self.yes()
        self.assertEqual(got["call"]["status"], "no_number")
        self.assertIn(BR.PHRASES["no_channel"], got["line"])
        self.assertEqual(got["line"].count(LINK), 1)
        self.assertEqual(got["open"], LINK)

    def test_no_call_from_the_engine_no_call_promised(self):
        # gate D2: her own rules said call AND email; the engine's read-back named no call (their listing shows no number) → the sent line
        use_fake_agapi(self)   # submit_booking: sent, no call_plan, no takeover
        with mock.patch.object(VC, "dial", mock.AsyncMock(side_effect=AssertionError("dialled with no plan"))):
            self.hold({"email": ALL4["email"], "phone": {"value": LISTED}}, hours=10, what="a room", venue="Hotel Gate", nights=1,
                      facts=LISTING_FACTS, place_id=PID)
            self.assertIn("call", VN._HELD[ACCT]["rules_say"].lower())                       # what her own rules would have said
            got = self.yes()
        self.assertEqual(got["line"], BR.PHRASES["sent"] + " " + BR.PHRASES["takeover"])
        self.assertNotIn("call", got["line"].lower())

    def test_takeover_line_is_the_no_channel_line_and_the_link(self):
        self.assertEqual(V.takeover_line(None, LINK), f"{BR.PHRASES['no_channel']} {LINK}")
        self.assertEqual(V.takeover_line(f"x {LINK}", LINK), f"x {LINK}")

    def test_the_take_over_shows_the_number_and_keeps_none(self):
        res = {"say": "They didn't pick up again.", "state": "no_answer",
               "next_step": {"kind": "their_listing", "phone": LISTED, "link": LINK}}
        said = V.no_answer_words(res)
        self.assertIn(LISTED, said)                                                         # shown to the person at that moment
        self.assertIn(LINK, said)
        card = VC.card_of("act_1", res)
        self.assertEqual(card["page"], LINK)
        self.assertEqual(VS.unkept(res["next_step"]), {"kind": "their_listing", "link": LINK})
        kept = []

        async def call(op, body, approval=None, account=None):
            return {"ok": True, "result": dict(res)}
        acts = [{"act_id": "act_1", "venue": "Hotel Gate", "state": "calling"}]

        async def remember(account, act):
            kept.append(act)
        with mock.patch.object(VS, "CALL", call), mock.patch.object(VS, "acts_of", mock.AsyncMock(return_value=acts)), \
                mock.patch.object(VS, "_remember", remember):
            run(VS.call_attempt(ACCT, "act_1", "no_answer", None, "none"))
        self.assertEqual(kept[-1]["next_step"], {"kind": "their_listing", "link": LINK})
        _holds_no_number(self, kept)


class TheDialKeepsNothing(unittest.TestCase):
    PLAN = {"phone": LISTED, "source": "listing", "when": "when they open at 13:00", "opens_at": "13:00", "simulate": False,
            "call_id": "vcp_1", "reason": "R6", "next_call": {"allowed": False, "allowed_at": "2099-01-01T00:00:00Z"},
            "payload": dict(BR.CALL_PAYLOAD), "opening": BR.call_opening("calling about the booking."), "rules": list(BR.CALL_RULES)}

    def setUp(self):
        self.store = CS.MemoryCallStore()
        acts = [{"act_id": "act_1", "venue": "Hotel Gate", "state": "sent", "call_source": "listing", "place_id": PID}]
        self.acts = acts

        async def remember(account, act):
            acts[:] = [a for a in acts if a["act_id"] != act["act_id"]] + [act]
        for p in (mock.patch.object(CR, "CALL_STORE", self.store), mock.patch.object(C, "calls_enabled", lambda: True),
                  mock.patch.object(C, "bland_key", lambda: "k"), mock.patch.object(VS, "acts_of", mock.AsyncMock(side_effect=lambda a: list(acts))),
                  mock.patch.object(VS, "_remember", remember),
                  mock.patch.object(C, "place_call", mock.AsyncMock(side_effect=AssertionError("dialled before the act allows it")))):
            p.start()
            self.addCleanup(p.stop)

    def test_a_scheduled_listing_call_keeps_no_digits_and_no_hash(self):
        out = run(VC.dial(ACCT, {"act_id": "act_1", "call_plan": dict(self.PLAN)}, {"venue": "Hotel Gate", "place_id": PID}))
        self.assertEqual(out["status"], "scheduled")
        row = next(iter(self.store.calls.values()))
        self.assertEqual(row["dialled_number"], f"listing:{PID}")
        self.assertEqual(row["brief"]["number_ref"], {"source": "listing", "place_id": PID})
        _holds_no_number(self, row)
        _holds_no_number(self, self.acts)

    def test_at_its_time_the_number_is_the_acts_never_a_places_read(self):
        brief = VC.brief_of("act_1", dict(self.PLAN), {"place_id": PID})
        ops = []

        async def call(op, body, approval=None, account=None):
            ops.append((op, body))
            if op == "users.register":
                return {"ok": True, "result": {"end_user_id": "eu_1"}}
            return {"ok": True, "result": {"act_id": "act_1", "status": "calling", "call_plan": dict(self.PLAN), "say": "x"}}
        VS._USERS.clear()
        with mock.patch.object(VS, "CALL", call):
            self.assertEqual(run(VC.number_now(ACCT, brief)), LISTED)
        self.assertEqual([b for o, b in ops if o == "venue.call_again"], [{"act_id": "act_1", "reason": "R6", "end_user": "eu_1"}])
        with self.assertRaises(PT.ListingUnavailable):   # Sasha's own Places read refuses a booking's listing
            run(PT.listing_number(None, brief["number_ref"], None))
        src = inspect.getsource(CR.place_due)
        self.assertIn("VC.number_now(", src)


class TheSweepTellsTheTakeOver(unittest.TestCase):
    def test_the_sweep_keys_on_the_calls_source_and_tells_with_the_card(self):
        src = inspect.getsource(PR.no_reply_offers)
        self.assertIn('act.get("call_source")', src)
        self.assertNotIn("venue_phone", src)
        self.assertNotIn("listing_ref", src)
        self.assertIn('got.get("card")', src)


class NoSecondCopyLeft(unittest.TestCase):
    def test_no_listing_number_or_hash_kept_for_a_booking(self):
        for rel in ("agapi/venues.py", "agapi/venue_submit.py", "agapi/venue_calls.py", "booking_signer/proactive.py"):
            src = (BACKEND / rel).read_text()
            for gone in ('"listing_ref"', '"venue_phone"', "number_ref(", "listing_number(rd", "PT.listing_number"):
                self.assertFalse(gone in src, f"{rel}: {gone}")


if __name__ == "__main__":
    unittest.main()
