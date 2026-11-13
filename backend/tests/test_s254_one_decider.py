"""Sasha 254 → Sasha 378 (CR 188's Sasha half) · ONE DECISION, AND IT IS AgAPI's. Every venue booking (/s2, WhatsApp's brain, /next
under parity — and old S1) follows venue.profile's `decision` (AgAPI's handoff.decide) through ONE path (venues.one_decision): its act
(Kanoe's form / email, or the call) → venue.prepare_booking → its read-back → the ONE yes; the platform → Sasha books it on the yes
(platform_book) or hands over the step only they may do (platform); nothing → the floor. Sasha decides no route, asks no question of her
own and reads no person's switch (access, real-venue sends, the platform beta). The rules' call conduct (R7–R9), the 30-minute / 3-a-day
limits at the dial (R10) and the take-over line (R11/R12) stay as words and constants.

Offline: the booking API is a recorder (nothing leaves the process); AgAPI's decision is scripts/agapi_decides (its own shapes); no model,
no Places, no Twilio/Bland, no database.

    cd backend && python -m unittest tests.test_s254_one_decider -v
"""
from __future__ import annotations

import asyncio
import os
import pathlib
import re
import unittest
import uuid
from datetime import date, datetime, timedelta, timezone
from unittest import mock

from agapi import booking_decide as BD, s2_outcomes as OC, v0 as API, venues as VN
from agapi.booking_rules import booking_rules as BR
from app.agent import voice as V
from booking_signer import call_routes as CR, call_store as CS, calls as C, guest_accounts as GA, guest_receipt as GR
from booking_signer import guest_whatsapp as GW, loyalty as LY, wa_brain as WB
from scripts.venue_suite import FakeApi

ACCT = "00000000-0000-4000-8000-000000000254"
run = asyncio.run
LIVE = {"mode": "live", "calls": "on", "real_venue_sends": "on"}
BACKEND = pathlib.Path(__file__).resolve().parents[1]


def local(hours: float) -> tuple:
    """A booking `hours` from now, in Madrid's local day and time (the venue's own clock)."""
    from zoneinfo import ZoneInfo
    t = (datetime.now(timezone.utc) + timedelta(hours=hours)).astimezone(ZoneInfo("Europe/Madrid"))
    return t.date().isoformat(), t.strftime("%H:%M")


class Api(FakeApi):
    """The venue suite's booking API recorder + a form that is sent, and a call route that can refuse at the dial."""

    def __init__(self):
        super().__init__()
        self.place = (200, {"status": "placed"})

    async def __call__(self, account, method, path, body=None, timeout=90.0):
        if path == "/api/booking/forms" and not (body or {}).get("handover"):
            self.calls.append((method, path, body))
            return 200, {"form_id": "f-9", "trip_item_id": "t-9", "read_back": {"lines": ["Casa Gate · 2 people"], "sha256": "f" * 64}}
        if path == "/api/booking/forms/f-9/send":
            self.calls.append((method, path, body))
            return 200, {"status": "sent", "reading": {"result": None}}
        if path == "/api/booking/calls/k-1/place":
            self.calls.append((method, path, body))
            return self.place
        return await super().__call__(account, method, path, body, timeout)

    def bodies(self, path):
        return [b for _m, p, b in self.calls if p == path]

    def paths(self):
        return [p for _m, p, _b in self.calls]


def reader(rungs, venue="Casa Gate", country="ES", facts=None):
    async def rd(ctx, a):
        return {"read_id": "r-1", "country": country, "venue": venue, "facts": facts or [], "rungs": rungs, "open_now": True,
                "opens_at": None, "say": "", "place_id": a.get("place_id") or "ChIJcasagate254"}
    return rd


def engine_from(rungs, facts=None, url=None):
    """Sasha 378 · venue.profile, faked: AgAPI's decision for this venue (scripts/agapi_decides.for_rungs — CR 188's order), cached as
    venue_truth keeps it — the ONE route hold_venue follows (VT.decision). Nothing is fetched."""
    from scripts import agapi_decides as AD
    return AD.engine_for(rungs, facts, url)


# Sasha 265 · item 4: the phone is the venue's OWN published number (a call act may carry it; a Google listing's never is — Sasha 64)
ALL4 = {"form": {}, "whatsapp": {"value": "+34600000001"}, "email": {"value": "reservas@casagate.es"}, "phone": {"fact_index": 0, "value": "+34910000000"}}


def signed_in(test: unittest.TestCase) -> None:
    """Sasha 381 · CR 196 · the door's proof of this turn's instruction, as production sets it: in the app the person's verified session
    (sasha.agent_turn) with the turn's id; on WhatsApp the signed inbound message (inbound_phone, after Twilio's signature). The
    instruction is the approval (agapi_mandate.proof_from reads whichever this turn came by)."""
    from agapi import venue_submit as VS
    # Sasha 381e · ONE door per turn, as its entry point records it (none records both): asked on WhatsApp (via "wa", the harness's
    # default) → the signed inbound message; else the app → the verified session
    if getattr(test, "via", "wa") == "wa":
        tok = VS.WA.set({"wa_id": "447700900254", "message_id": "SM" + "4" * 32})
        test.addCleanup(VS.WA.reset, tok)
    else:
        tok = VS.TAP.set({"kind": "supabase", "token": "test-token"})
        test.addCleanup(VS.TAP.reset, tok)
    API._CLAIMED.clear()   # each test its own conversation: a booking claimed by another test is not this one
    for p in (mock.patch("booking_signer.basket._run", lambda: None),   # claims in-process (no database in a unit test), as s287 / s328 do
              mock.patch.dict("os.environ", {"SASHA_AGAPI_TAP_SECRET": "test-tap-secret"})):
        p.start()
        test.addCleanup(p.stop)


async def agapi_door(op, body, approval=None, account=None):
    """Sasha 381 · AgAPI's person and instruction ops as it answers them (a test's own fake replaces this one): users.register, and
    approvals.mandate (CR 196: a missing term → term_not_given). Anything else is a test reaching AgAPI it didn't fake — refused."""
    if op == "users.register":
        return {"ok": True, "result": {"end_user_id": "eu_254"}}
    if op == "approvals.mandate":
        missing = [k for k in ("prepared_id", "party", "date", "time") if (body["scope"].get("booking") or {}).get(k) in (None, "")]
        if missing:
            return {"ok": False, "error": {"code": "invalid_input", "message": "asked, never guessed",
                                           "details": {"rule": "term_not_given", "missing": missing}}}
        return {"ok": True, "result": {"mandate_id": "mdt_" + "c" * 26, "expires_at": "2099-01-01T00:00:00Z", "proof": {"kind": body["proof"]["kind"]}}}
    return {"ok": False, "error": {"code": "not_configured", "message": op}}   # nothing else here: as a server with no venues key


def fake_act(test: unittest.TestCase, answer: dict = None):
    """Sasha 265 · item 4 (CR 99): AgAPI's call act, faked — venue.prepare_booking with call, the call's read-back, and the tap's result
    (status calling + call_plan, simulate: nothing dialled), or `submit` when a test gives another answer."""
    from agapi import venue_submit as VS
    lines = ["2 people at Casa Gate.", "I'll call them now and let you know.", "Sasha calls Casa Gate from Kanoe's number …"]
    test.vs_calls = []

    real_prepare, real_read_back = VS.prepare, VS.read_back   # only the CALL act is faked; the rest is real

    async def prepare(account, place, person, date_, time_, party, notes=None, call=None, **kw):
        test.vs_calls.append(("prepare", call))
        if not call or kw.get("stay"):   # Sasha 271 · a stay's request act (its number rides with it): the real prepare
            return await real_prepare(account, place, person, date_, time_, party, notes=notes, call=call, **kw)
        return {"ok": True, "prepared_id": "vpr_" + "a" * 32, "link": "https://agapi.test/p/x", "routes": ["page", "call"]}

    async def read_back(account, pid, route=None, call=None):   # Sasha 269 · + the call (a listing number passed again)
        test.vs_calls.append(("read_back", route))
        if route != "call":
            return await real_read_back(account, pid)
        return {"ok": True, "end_user": "usr_1", "read_back_id": "rbk_1", "lines": lines, "sha256": "f" * 64}

    real_instructed = VS.submit_instructed

    async def submit_instructed(account, held, said):   # Sasha 381 · CR 196 · the call act, approved by the instruction (its mandate)
        if held.get("rung") != "agapi_call":
            return await real_instructed(account, held, said)
        test.vs_calls.append(("submit", held.get("mandate_id")))
        say = f"Booking now: Casa Gate, {held['party']} people, {held['when'][:10]} at {held['when'][11:16]}."
        return dict(answer or {"ok": True, "status": "calling", "route": "call", "act_id": "act_1",
                               "call_plan": {"phone": "+34910000000", "when": "now", "simulate": True, "next_call": {"allowed": True}},
                               "say": BR.on_it("I'll call them now and let you know"), "instructed": {"mandate_id": held.get("mandate_id"), "say": say}})
    signed_in(test)
    for p in (mock.patch.object(VS, "prepare", prepare), mock.patch.object(VS, "read_back", read_back),
              mock.patch.object(VS, "submit_instructed", submit_instructed), mock.patch.object(VS, "CALL", agapi_door)):
        p.start()
        test.addCleanup(p.stop)


def said(args: dict) -> str:
    """Sasha 381 · the person's instruction in their own words — every term of the booking given (a term not given is asked, never
    guessed): the venue, the day, the time (none for a quote), the people."""
    when = (f" on {args['day']}" if args.get("day") else "") + (f" at {str(args['time'])[:5]}" if args.get("time") else "")
    return f"book {args.get('name')}{when} for {args.get('party')}"


class Base(unittest.TestCase):
    surface = "s2"

    def setUp(self):
        VN._HELD.pop(ACCT, None)
        BD._STOPPED.pop(ACCT, None)
        self.api = Api()
        self.told, self.taps = [], []

        async def tell(ch, text, template=None):
            self.told.append(text)
            return "sent (captured)"

        async def tap(account, text, url, link_id=None, venue=None, when=None):
            self.taps.append(url)
            return "sent (captured)"

        class _Store(GW.MemoryGuestStore):   # Sasha 288 · the real store's shape: get_state too (the gate logged its absence)
            async def channel_of_account(self, acct):
                return {"wa_id_sha256": "x" * 64, "account_id": acct}
        self.calls_store = CS.MemoryCallStore()
        for p in (mock.patch.object(GW, "api", self.api), mock.patch.object(GA, "founder", lambda a: False),
                  mock.patch.object(GR, "address_of", mock.AsyncMock(return_value="alex@example.test")),
                  mock.patch.object(VN, "engine_channel", mock.AsyncMock(return_value=None)),
                  mock.patch.object(GW, "_tell", tell), mock.patch.object(GW, "tap_platform", tap), mock.patch.object(GW, "STORE", _Store()),
                  mock.patch.object(WB, "trip_day_words", mock.AsyncMock(return_value="It's in your bookings")),
                  mock.patch.object(OC, "booked", mock.AsyncMock()), mock.patch("agapi.v0.claim", mock.AsyncMock()),
                  mock.patch.object(LY, "find_for", mock.AsyncMock(return_value=None)),
                  mock.patch.object(CR, "CALL_STORE", self.calls_store)):
            p.start()
            self.addCleanup(p.stop)
        fake_act(self)   # Sasha 265 · item 4: a call is an AgAPI act
        self.addCleanup(VN._HELD.pop, ACCT, None)

    def ctx(self, said="", later=False):
        c = API.Ctx(account=ACCT, mode="test", user_said=said, session="s254d", surface=self.surface, via=getattr(self, "via", "wa"))   # 326: the phone only when asked there
        if later:
            c.started = VN._HELD[ACCT]["at"] + timedelta(minutes=1)
        return c

    def hold(self, rungs, hours=72.0, venue="Casa Gate", what="dinner", facts=None, **a):
        day, hhmm = local(hours)
        args = {"name": venue, "city": "Madrid", "country": "ES", "what": what, "party": 2, "day": day, "time": hhmm,
                "place_id": "ChIJcasagate254", **a}   # Sasha 378 · its listing: venue.profile (AgAPI's decision) is asked by it
        with mock.patch.object(VN, "_read", reader(rungs, venue, facts=facts)), mock.patch.object(VN, "engine_channel", engine_from(rungs, facts)):
            return run(VN.hold_venue(self.ctx(said(args)), args))

    def yes(self):
        return run(VN.book_venue(self.ctx("yes, go ahead", later=True), {"approval": {"said": "yes, go ahead"}}))

    def expect(self, out, action, say_key, say_now=True, **fmt):
        """The executors' words (agapi_d over AgAPI's decision): its action, its say key, the take-over on EVERY answer (R11)."""
        self.assertEqual(out["rules"]["action"], action, out)
        self.assertEqual(out["rules"]["say_key"], say_key, out)
        self.assertEqual(out["takeover"]["say"], BR.PHRASES["takeover"])


# ── Sasha 378 · CR 188 · each of AgAPI's routes, followed — never re-decided ──────────────────────────────────────────────────

class FollowsAgapi(Base):
    """hold_venue follows AgAPI's decision exactly: an act it sends → its read-back for the ONE yes (no booking service here → Tyler's,
    never Sasha's own send); a call → the call's card; their WhatsApp (they send it) / a closed platform / a step only they may do →
    AgAPI's hand-over; nothing → the floor. No question of Sasha's own, whatever the venue publishes."""

    def setUp(self):
        super().setUp()
        from tests.test_s254_handle_it_live import use_fake_agapi
        self.agapi = use_fake_agapi(self)

    def test_their_own_form_is_kanoes_send_on_the_instruction(self):
        out = self.hold(ALL4)                                                           # a form AND every other way: still ONE decision
        self.assertEqual((out["status"], out["route"]), ("requested", "agapi"))       # Sasha 381 · sent on the instruction, no card
        self.assertNotIn("options", out)                                                # no "prefilled form or handle it?"
        self.assertEqual(out["rules"]["action"], "fill_form_zero_touch")
        self.assertIn("venue.prepare_booking", self.agapi.ops())
        self.assertFalse(any(p in ("/api/booking/forms", "/api/booking/emails") for p in self.api.paths()))

    def test_their_own_email_is_kanoes_request(self):
        out = self.hold({"email": ALL4["email"], "phone": ALL4["phone"]}, hours=20)    # within 48 h: still AgAPI's email, never a call of Sasha's
        self.assertEqual((out["status"], out["route"], out["rules"]["action"]), ("requested", "agapi", "request_email"))
        self.assertNotIn("/api/booking/calls", self.api.paths())

    def test_their_phone_is_the_call_on_the_instruction(self):
        got = self.hold({"phone": ALL4["phone"]}, hours=20)
        self.assertEqual((got["status"], got["route"]), ("calling", "agapi_call"))   # Sasha 381 · no OK card: the instruction is it
        self.assertNotIn("choices", got)
        self.assertEqual(self.api.bodies("/api/booking/calls"), [])                    # the act's call, never Sasha's own

    def test_their_whatsapp_they_send_is_agapis_hand_over(self):
        out = self.hold({"whatsapp": ALL4["whatsapp"]})
        self.assertNotEqual(out.get("route"), "agapi")                                  # nothing Kanoe sends: AgAPI said the person does
        self.assertFalse(any(p.startswith("/api/booking/") and p.endswith("/send") for p in self.api.paths()))

    def test_a_platform_is_booked_by_sasha_on_the_yes(self):
        out = self.hold({"link": {"value": "CoverManager"}})
        self.assertIn(out["status"], ("awaiting_yes", "page_link", "page_on_phone"), out)
        self.assertIn("venue.prepare_booking", self.agapi.ops())                        # AgAPI's prepare decides platform_book or the hand-over

    def test_nothing_is_agapis_floor_their_page_never_a_send(self):
        out = self.hold({})                                                             # AgAPI: none — their website, the floor
        self.assertIn(out["status"], ("page_on_phone", "page_link"), out)
        self.assertFalse(out.get("booked"))
        self.assertNotIn(ACCT, VN._HELD if out["status"] == "page_link" else {})
        self.assertFalse(any(p.endswith("/send") for p in self.api.paths()))

    def test_the_decision_is_read_never_made(self):
        src = (BACKEND / "agapi" / "venues.py").read_text()
        hv = src[src.index("async def hold_venue(ctx, a: dict)"):src.index("#: Sasha 377 · CR 188 · the routes AgAPI ACTS on")]
        self.assertIn("dec = VT.decision(place)", hv)
        for gone in ("rules_for", "_execute", "read_channel", "chosen_route", "decide_for", "BR.decide", "redecide"):
            self.assertNotIn(gone, src, gone)


class R5HotelNoReplySweep(unittest.TestCase):
    """The follow-up runs in proactive's sweep. Sasha 271 · MOVED (CR 102): its TIMING is the engine's — venue.booking_status.follow_up
    {reason, due, due_at} — never decide() over a time Sasha kept (state.request_sent_at / venue_replied assumed)."""

    def setUp(self):
        from booking_signer import escalation as ESC, ladder_routes as LR, proactive as PR
        self.calls, self.told = [], []
        now = datetime.now(timezone.utc)
        self.now = now.replace(hour=12, minute=0)   # 14:00 Madrid: daytime
        day, hhmm = (self.now + timedelta(days=5)).date().isoformat(), "15:00"
        self.row = {"id": "t-h", "venue": "Hotel Gate", "date": day, "time": hhmm, "timezone": "Europe/Madrid", "status": "requested",
                    "channel": "email", "read_id": "r-h", "intent_id": "e-h", "type": "restaurant",
                    "requested_at": (self.now - timedelta(hours=25)).isoformat()}
        plan = ESC.plan_line(f"If they haven't replied within {BR.HOTEL_NO_REPLY_HOURS} hours, I'll call them", None)

        # Sasha 269 · MOVED (CR 100): R5's call is the ACT's — an AgAPI email request act, venue.call_again "R5" (venue_calls.again);
        # Sasha's own auto_call_from_email is deleted. The act's words are what the person is told.
        from agapi import venue_calls as VC, venue_submit as VS
        self.acts = [{"act_id": "act_h", "venue": "Hotel Gate", "when": f"{day}T{hhmm}", "party": 2, "state": "sent", "country": "ES",
                      "call_source": "venue"}]   # Sasha 272 · CR 103: the act keeps the call's source only — the number is the record's
        self.again_says = {"status": "calling", "say": "On it — I'll call them now and let you know."}
        self.follow_up = {"reason": "R5", "due": True, "due_at": None, "call": "venue.call_again"}   # the engine: no reply in 24 h
        self.status_asked = []

        async def status(account, act_id):
            self.status_asked.append(act_id)
            return {"act_id": act_id, "state": "sent", **({"follow_up": dict(self.follow_up)} if self.follow_up else {})}

        async def acts_of(account):
            return [dict(x) for x in self.acts]

        async def remember(account, act):
            self.acts = [x for x in self.acts if x["act_id"] != act["act_id"]] + [dict(act)]

        async def again(account, act_id, reason="person_asked"):
            self.calls.append((act_id, reason))
            return dict(self.again_says)

        async def tell(account, text, card=None, wa_text=None):
            self.told.append(text)
            return "sent (captured)"

        class Chans:
            async def all_channels(self):
                return [{"account_id": ACCT, "wa_id_sha256": "x" * 64}]

        for p in (mock.patch.object(VS, "acts_of", acts_of), mock.patch.object(VS, "_remember", remember), mock.patch.object(VC, "again", again),
                  mock.patch.object(VS, "status", status),
                  mock.patch.object(VC, "tell", tell), mock.patch.object(GW, "STORE", Chans()),
                  mock.patch.dict(os.environ, {"SASHA_NO_REPLY_CALL": "1"})):
            p.start()
            self.addCleanup(p.stop)
        BD._STOPPED.pop(ACCT, None)

    def test_25_hours_without_a_reply_a_hotel_is_called_under_the_yes(self):
        from booking_signer import proactive as PR
        done = run(PR.no_reply_offers(self.now))
        self.assertEqual(self.calls, [("act_h", "R5")])                           # the act's own follow-up call (venue.call_again R5)
        self.assertEqual(done[0]["follow_up"], "R5")                              # because booking_status said it's due
        self.assertEqual(self.told, [self.again_says["say"]])                      # the act's words
        self.assertEqual(run(PR.no_reply_offers(self.now)), [])                   # once

    def test_23_hours_still_waits(self):
        from booking_signer import proactive as PR
        due_at = (self.now + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.follow_up = {"reason": "R5", "due": False, "due_at": due_at, "call": "venue.call_again"}   # the engine: not yet
        self.assertEqual(run(PR.no_reply_offers(self.now)), [])
        self.assertEqual(self.calls, [])
        self.assertEqual(run(PR.no_reply_offers(self.now + timedelta(minutes=30))), [])   # asked again — still not due
        self.assertEqual(self.status_asked, ["act_h", "act_h"])                    # every sweep asks: no kept due_at of the engine's
        self.follow_up = {"reason": "R5", "due": True, "due_at": None, "call": "venue.call_again"}   # (the engine's clock moved it)
        run(PR.no_reply_offers(self.now + timedelta(minutes=31)))                  # due now → the act's call
        self.assertEqual(self.calls, [("act_h", "R5")])

    def test_no_follow_up_no_call(self):
        from booking_signer import proactive as PR
        self.follow_up = None   # the venue replied, a call is open, or the rules attach none
        self.assertEqual(run(PR.no_reply_offers(self.now)), [])
        self.assertEqual(self.calls, [])

    def test_calls_off_the_stop_is_told(self):
        from booking_signer import proactive as PR
        self.again_says = {"status": "not_allowed", "say": BR.PHRASES["no_real_sends"]}   # the ACT refuses it, in its words
        done = run(PR.no_reply_offers(self.now))
        self.assertEqual(done[0]["outcome"], "not_allowed")
        self.assertEqual(self.told, [BR.PHRASES["no_real_sends"]])

    def test_no_env_timing(self):
        src = (BACKEND / "booking_signer" / "proactive.py").read_text()
        block = src[src.index("async def no_reply_offers"):src.index("async def tap_offers")]
        for gone in ("decide_for", "request_sent_at", "sent_at", "venue_replied", "timedelta"):   # Sasha 271 · no clock of Sasha's
            self.assertNotIn(gone, block)
        self.assertNotRegex(src, r"\bD\.(reply_hours|urgent_hours|tap_window_min)\(")
        self.assertNotRegex(src, r"from \. import decide")


# ── R7 / R8 / R9 · the call ─────────────────────────────────────────────────────────────────────────────────────────────────

class R7R8R9TheCall(unittest.TestCase):
    def brief(self):
        v = C.CallVenue(key="test", name="Casa Gate", number_env="", language="en", timezone="Europe/Madrid", number="+34910000000",
                        source="test")
        p = C.parse_call_particulars({"date": (date.today() + timedelta(days=3)).isoformat(), "time": "21:00", "party": 4, "name": "Anna Johnson"})
        return C.build_call(v, p, datetime.now(timezone.utc))["brief"]

    def test_r7_the_opening_starts_with_the_disclosure_exactly(self):
        b = self.brief()
        self.assertTrue(b["first_sentence"].startswith(BR.CALL_DISCLOSURE + ", "), b["first_sentence"])
        self.assertEqual(C.LANGUAGES["en"].opening, BR.call_opening("calling {party} to book a table {what} {when} {at}. Is that possible?"))

    def test_r8_no_deposit_no_fee_no_other_time_the_call_ends(self):
        self.assertEqual(C.DEPOSIT_RULE, BR.CALL_RULES[1] + " ")
        task = self.brief()["task"]
        self.assertIn(BR.CALL_RULES[1], task)
        for never in ("payment link", "get the amount", "ask how they take it"):
            self.assertNotIn(never, task)
        self.assertLessEqual(len(task), 2000)

    def test_r9_no_voicemail_no_recording_the_limit(self):
        pl = C.bland_payload({**self.brief(), "venue_key": "test"}, "c-1")
        self.assertEqual((pl["voicemail"], pl["record"], pl["max_duration"]),
                         (BR.CALL_PAYLOAD["voicemail"], BR.CALL_PAYLOAD["record"], BR.CALL_PAYLOAD["max_minutes"]))


class R8DepositAsked(unittest.TestCase):
    """A deposit asked on a call → the call ends (its rule), the outcome is unclear, the PERSON IS TOLD; never a payment question."""

    def setUp(self):
        self.told = []

        async def tell(ch, text, template=None):
            self.told.append(text)
            return "sent (captured)"

        class _Store(GW.MemoryGuestStore):   # Sasha 288 · the real store's shape: get_state too (the gate logged its absence)
            async def channel_of_account(self, acct):
                return {"wa_id_sha256": "x" * 64}
        for p in (mock.patch.object(GW, "_tell", tell), mock.patch.object(GW, "STORE", _Store()),
                  mock.patch.object(GW, "venue_display", mock.AsyncMock(return_value="Casa Lucio")),
                  mock.patch.object(GW, "push_payment_question", mock.AsyncMock(side_effect=AssertionError("asked to pay"))),
                  mock.patch.object(CR.C, "place_call", mock.AsyncMock(side_effect=AssertionError("a confirmation call"))),   # Sasha 269 · moved
                  mock.patch("booking_signer.guest_receipt.send_after_call", mock.AsyncMock(return_value="sent"))):
            p.start()
            self.addCleanup(p.stop)
        BD._STOPPED.pop(ACCT, None)

    def test_the_person_is_told_and_never_asked_to_pay(self):
        from booking_signer import payments_t0 as PT0
        with mock.patch.object(PT0, "after_call", mock.AsyncMock(side_effect=AssertionError("a payment request"))):
            reading = C.CallReading(state="answered", outcome="unclear", venue_words="Sí, pero hace falta una señal de 20 euros.",
                                    raised=[{"what": "deposit", "quote": "hace falta una señal de 20 euros"}])
            run(CR._follow_up({"call_id": "c-1", "account_id": ACCT, "trip_item_id": "t-1", "brief": {"purpose": "book"}}, reading))
        self.assertEqual(len(self.told), 1)
        self.assertTrue(self.told[0].startswith("I stopped the booking call to Casa Lucio (they asked for a deposit"))
        self.assertNotIn("€", self.told[0])
        self.assertIn("Nothing else was cancelled", BD.stops_of(ACCT)[0])

    def test_the_rules_own_reader_ends_it(self):
        self.assertTrue(BR.call_answer("Necesitamos una fianza")["end_call"])
        self.assertIsNone(BR.call_answer("Necesitamos una fianza")["amount_agreed"])


# ── R10 · 3 calls a person a day; 30 minutes between calls to one venue ─────────────────────────────────────────────────────

class R10Limits(Base):
    """R10 is the ACT's (CR 99), and the dial's (R10CallRoutes): Sasha keeps no count of her own to decide a route by."""

    def test_refused_at_the_dial_the_stop_is_said_in_the_turn(self):
        fake_act(self, answer={"ok": True, "status": "not_allowed", "route": "call", "say": BR.PHRASES["calls_cap"]})
        got = self.hold({"phone": ALL4["phone"]}, hours=20)
        self.assertEqual(got["status"], "not_allowed")
        self.assertEqual(got["say"], BR.PHRASES["calls_cap"])
        self.assertNotIn("/api/booking/calls", self.api.paths())


class R10CallRoutes(unittest.TestCase):
    """The server enforces R10 at the dial for every surface: 30 minutes per venue, 3 per person, the net — constants, no env var."""

    def test_the_caps_are_the_rules_constants(self):
        with mock.patch.dict(os.environ, {"SASHA_CALLS_PER_DAY": "99", "SASHA_CALLS_PER_ACCOUNT_PER_DAY": "99"}):
            self.assertEqual(CR.cap(), BD.SERVER_CALLS_PER_DAY)
            self.assertEqual(CR.account_cap(), BR.CALLS_PER_PERSON_PER_DAY)

    def test_too_soon_at_the_dial(self):
        store = CS.MemoryCallStore()
        now = datetime.now(timezone.utc)
        store.calls["a"] = {"call_id": "a", "account_id": ACCT, "status": "answered", "venue_key": "read:r-1", "dialled_number": "+349",
                            "approved_at": now - timedelta(minutes=12)}
        with mock.patch.object(CR, "CALL_STORE", store):
            self.assertIn("less than 30 minutes", run(CR.too_soon(ACCT, {"venue_key": "read:r-9", "dialled_number": "+349"}, now)))
            self.assertIsNone(run(CR.too_soon(ACCT, {"venue_key": "read:r-9", "dialled_number": "+341"}, now)))
            self.assertIsNone(run(CR.too_soon(ACCT, {"venue_key": "read:r-1", "dialled_number": "+349"}, now + timedelta(minutes=19))))

    def test_the_rules_wait_is_a_call_scheduled_closer_to_the_day(self):
        with mock.patch.object(CR, "NOW", lambda: datetime(2026, 10, 13, 10, 0, tzinfo=timezone.utc)):
            self.assertEqual(CR._later("2026-10-14T19:00:00+00:00"), datetime(2026, 10, 14, 19, 0, tzinfo=timezone.utc))
            self.assertIsNone(CR._later("2026-10-13T09:00:00+00:00"))                  # never in the past
            self.assertIsNone(CR._later("not a time"))

    def test_a_scheduled_call_the_rules_now_refuse_is_told(self):
        store = CS.MemoryCallStore()
        now = datetime.now(timezone.utc)
        store.calls["s"] = {"call_id": "s", "account_id": ACCT, "status": "awaiting_approval", "venue_key": "read:r-1", "dialled_number": "+349",
                            "brief": {"venue_name": "Casa Gate", "act_id": "act_s"},   # Sasha 265 · an act's call (no act: never placed)
                            "approval": {"scheduled_for": (now - timedelta(minutes=1)).isoformat()}}
        told = []

        async def tell(account, what, why, link=None, push=True):
            told.append((what, why))
            return {}
        with mock.patch.object(CR, "CALL_STORE", store), mock.patch.object(C, "calls_enabled", lambda: False), \
                mock.patch.object(BD, "tell_stopped", tell):
            run(CR.place_due())
        self.assertEqual(store.calls["s"]["status"], "not_placed")
        self.assertEqual(told, [("the call to Casa Gate", "calls are off")])


# ── R11 / R12 · the take-over on every answer; an automatic stop is told ────────────────────────────────────────────────────

class R11R12(Base):
    def test_every_answer_carries_the_takeover(self):
        from tests.test_s254_handle_it_live import use_fake_agapi
        use_fake_agapi(self)
        for rungs, hours in ((ALL4, 72), ({"email": ALL4["email"]}, 72), ({"phone": ALL4["phone"]}, 20)):
            VN._HELD.pop(ACCT, None)
            out = self.hold(rungs, hours=hours)
            self.assertEqual(out["takeover"]["say"], BR.PHRASES["takeover"], rungs)
            self.assertIn("link", out["takeover"])

    def test_a_stop_reaches_their_whatsapp_and_get_status(self):
        d = run(BD.tell_stopped(ACCT, "the call to Casa Gate", "today's calls are made"))
        self.assertEqual(self.told, [d["say_text"]])
        self.assertEqual(BD.stops_of(ACCT), [d["say_text"]])
        from agapi import s2_status as SS
        with mock.patch.object(VN, "venue_bookings", mock.AsyncMock(return_value=[])), \
                mock.patch.object(API, "_latest", mock.AsyncMock(return_value=None)):
            st = run(SS.status_of(ACCT))
        self.assertEqual(st["stopped"], [d["say_text"]])


# ── a CAPTCHA is theirs; every surface follows the same decision ──────────────────────────────────────────────────────────────

class StepsOnlyTheyMayDo(Base):
    def test_a_captcha_is_agapis_hand_over_never_a_send(self):
        out = self.hold({"form": {}}, facts=[{"kind": "challenge", "value": "captcha"}], website="https://casagate.es")
        self.assertNotEqual(out.get("route"), "agapi")
        self.assertFalse(any(p.endswith("/send") for p in self.api.paths()))


class EverySurface(Base):
    def test_s2_whatsapp_next_and_old_s1_all_follow_agapis_decision(self):
        for surface, parity in (("s2", "on"), ("wa", "on"), ("s1", "on"), ("s1", "off")):
            VN._HELD.pop(ACCT, None)
            self.surface = surface
            with mock.patch.dict(os.environ, {"SASHA_S1_PARITY": parity}):
                out = self.hold({"phone": ALL4["phone"]}, hours=20)
            self.assertEqual((out["status"], out["route"]), ("calling", "agapi_call"), (surface, parity))


class UtcOf(unittest.TestCase):
    def test_utc_from_the_venues_local_time(self):
        self.assertEqual(BD.utc_of("2026-07-01T21:00", "ES"), "2026-07-01T19:00:00+00:00")   # Madrid in summer: UTC+2
        self.assertEqual(BD.utc_of("2026-12-01T21:00", "PT"), "2026-12-01T21:00:00+00:00")   # Lisbon in winter: UTC


# ── the source scan: the retired deciders and env vars are read nowhere ─────────────────────────────────────────────────────

class Retired(unittest.TestCase):
    def sources(self):
        for p in BACKEND.rglob("*.py"):
            rel = p.relative_to(BACKEND).as_posix()
            if rel.startswith(("tests/", "agapi/booking_rules/")) or "/." in rel or rel.startswith(("venv", ".venv")):
                continue
            yield rel, p.read_text(encoding="utf-8", errors="ignore")

    def test_the_env_vars_are_read_nowhere(self):
        for rel, src in self.sources():
            for name in ("SASHA_URGENT_HOURS", "SASHA_EMAIL_REPLY_HOURS", "SASHA_CALLS_PER_DAY", "SASHA_CALLS_PER_ACCOUNT_PER_DAY",
                         "SASHA_TAP_WINDOW_MIN"):
                self.assertIsNone(re.search(rf"getenv\(\s*[\"']{name}[\"']|environ(?:\.get)?\(?\[?\s*[\"']{name}[\"']", src), f"{rel} reads {name}")

    def test_the_old_deciders_are_gone(self):
        with self.assertRaises(ImportError):
            __import__("booking_signer.decide")
        vn = (BACKEND / "agapi" / "venues.py").read_text()
        for gone in ("_hold_inner", "_engine_route", "ladder_of", "decision_of", "wa_first", "ROUTE_TO_PREFER", "rules_for", "_execute",
                     "read_channel", "chosen_route"):
            self.assertNotIn(gone, vn)
        for gone in ("decide_for", "redecide", "ctx_for", "channels_of", "legacy_decision", "legacy_ladder", "access_of", "CHOICES"):
            self.assertFalse(hasattr(BD, gone), gone)

    def test_no_booking_decide_call_site(self):
        """Sasha 378 · CR 188: booking_rules.decide is AgAPI's — called nowhere in Sasha (its vendored vectors run in its own test)."""
        hits = [rel for rel, src in self.sources() if re.search(r"\bBR\.decide\(|booking_rules\.decide\(", src)]
        self.assertEqual(hits, [])


if __name__ == "__main__":
    unittest.main()
