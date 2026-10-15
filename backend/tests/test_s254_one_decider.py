"""Sasha 254 · item 2 — ONE DECIDER. Every venue booking chooser (/s2, WhatsApp's brain, /next under parity — and old S1) asks the
vendored booking rules (agapi/booking_rules: decide) through ONE adapter (agapi/booking_decide), and the executors run exactly the
action it returned, saying its phrase + the take-over. One end-to-end hold per rule (R1–R14 + access), through the one path
(hold_venue → book_venue), against a recorder for the booking API; the hotel's 24 h no-reply call from the sweep; a deposit asked on a
call (the call ends, the person is told, no payment question); the 3 a day and 30 minute limits; a source scan that the retired
deciders and env vars are read nowhere.

Offline: the booking API is a recorder (nothing leaves the process); no model, no Places, no Twilio/Bland, no database.

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


def live_access(test: unittest.TestCase, access: dict = None):
    """For tests of the EXECUTORS behind the rules: this person may reach real venues (the founder's / Jon's access)."""
    p = mock.patch.object(BD, "access_of", mock.AsyncMock(return_value=dict(access or LIVE)))
    p.start()
    test.addCleanup(p.stop)


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
                "opens_at": None, "say": "", "place_id": a.get("place_id")}
    return rd


def engine_from(rungs, facts=None, url=None):
    """Sasha 270 · MOVED (CR 101: one classifier): on the one path a FORM is the venue engine's to find (venue.profile), never Sasha's
    own read. The same venue as `rungs`: its own form / booking page (a form, their own page, a link that isn't a platform's) — and
    its CAPTCHA, on the engine's evidence — read by the engine, its messages as the engine's other ways. engine_channel is asked with
    listing=True only on the one path: old S1 (parity off) is unchanged."""
    from agapi import venues as _VN
    own = next((r for r in ("form", "own_page", "link") if r in rungs and not _VN._read_rung_kept(r, rungs[r])), None)

    async def eng(card, budget_s=30.0, listing=False):
        if not listing or not own:
            return None
        v = str((rungs[own] or {}).get("value") or "")
        also = [{"kind": k, "value": (rungs[k] or {}).get("value")} for k in ("whatsapp", "email") if k in rungs]
        return {"kind": {"form": "form", "own_page": "own_engine", "link": "widget"}[own], "url": v if v.startswith("http") else url,
                "engine_captcha": any(f.get("kind") == "challenge" for f in facts or []), "all": also,
                **({"alternative": also[0]} if also else {})}   # (venue_truth.channel: their request way, for the one question)
    return eng


# Sasha 265 · item 4: the phone is the venue's OWN published number (a call act may carry it; a Google listing's never is — Sasha 64)
ALL4 = {"form": {}, "whatsapp": {"value": "+34600000001"}, "email": {"value": "reservas@casagate.es"}, "phone": {"fact_index": 0, "value": "+34910000000"}}


def fake_act(test: unittest.TestCase, answer: dict = None):
    """Sasha 265 · item 4 (CR 99): AgAPI's call act, faked — venue.prepare_booking with call, the call's read-back, and the tap's result
    (status calling + call_plan, simulate: nothing dialled), or `submit` when a test gives another answer."""
    from agapi import venue_submit as VS
    lines = ["2 people at Casa Gate.", "I'll call them now and let you know.", "Sasha calls Casa Gate from Kanoe's number …"]
    test.vs_calls = []

    real_prepare, real_read_back, real_submit = VS.prepare, VS.read_back, VS.submit   # only the CALL act is faked; the rest is real

    async def prepare(account, place, person, date_, time_, party, notes=None, call=None):
        test.vs_calls.append(("prepare", call))
        if not call:
            return await real_prepare(account, place, person, date_, time_, party, notes=notes)
        return {"ok": True, "prepared_id": "vpr_" + "a" * 32, "link": "https://agapi.test/p/x", "routes": ["page", "call"]}

    async def read_back(account, pid, route=None, call=None):   # Sasha 269 · + the call (a listing number passed again)
        test.vs_calls.append(("read_back", route))
        if route != "call":
            return await real_read_back(account, pid)
        return {"ok": True, "end_user": "usr_1", "read_back_id": "rbk_1", "lines": lines, "sha256": "f" * 64}

    async def submit(account, held, said):
        if held.get("rung") != "agapi_call":
            return await real_submit(account, held, said)
        test.vs_calls.append(("submit", held.get("read_back_id")))
        return dict(answer or {"ok": True, "status": "calling", "route": "call", "act_id": "act_1",
                               "call_plan": {"phone": "+34910000000", "when": "now", "simulate": True, "next_call": {"allowed": True}},
                               "say": BR.on_it("I'll call them now and let you know")})
    for p in (mock.patch.object(VS, "prepare", prepare), mock.patch.object(VS, "read_back", read_back), mock.patch.object(VS, "submit", submit)):
        p.start()
        test.addCleanup(p.stop)


class Base(unittest.TestCase):
    surface = "s2"
    access = LIVE

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

        class _Store:
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
                  mock.patch.object(VN, "_push_later", mock.AsyncMock(return_value="watching")),
                  mock.patch.object(CR, "CALL_STORE", self.calls_store)):
            p.start()
            self.addCleanup(p.stop)
        live_access(self, self.access)
        fake_act(self)   # Sasha 265 · item 4: a call is an AgAPI act
        self.addCleanup(VN._HELD.pop, ACCT, None)

    def ctx(self, said="", later=False):
        c = API.Ctx(account=ACCT, mode="test", user_said=said, session="s254d", surface=self.surface)
        if later:
            c.started = VN._HELD[ACCT]["at"] + timedelta(minutes=1)
        return c

    def hold(self, rungs, hours=72.0, venue="Casa Gate", what="dinner", facts=None, **a):
        day, hhmm = local(hours)
        args = {"name": venue, "city": "Madrid", "country": "ES", "what": what, "party": 2, "day": day, "time": hhmm, **a}
        with mock.patch.object(VN, "_read", reader(rungs, venue, facts=facts)), mock.patch.object(VN, "engine_channel", engine_from(rungs, facts)):
            return run(VN.hold_venue(self.ctx("book it"), args))

    def yes(self):
        return run(VN.book_venue(self.ctx("yes, go ahead", later=True), {"approval": {"said": "yes, go ahead"}}))

    def expect(self, out, action, say_key, say_now=True, **fmt):
        self.assertEqual(out["rules"]["action"], action, out)
        self.assertEqual(out["rules"]["say_key"], say_key, out)
        self.assertEqual(out["takeover"]["say"], BR.PHRASES["takeover"])          # R11 · on EVERY answer
        if not say_now:   # the read-back first; the rules' words follow the send
            self.assertTrue(VN._HELD[ACCT]["rules_say"].startswith(BR.PHRASES[say_key].format(**fmt)))
        elif out.get("say"):
            self.assertTrue(out["say"].startswith(BR.PHRASES[say_key].format(**fmt)), out["say"])
            self.assertIn("take it over", out["say"].lower())


# ── R1 · own channels in this order: form → WhatsApp → email → phone ───────────────────────────────────────────────────────────

class R1ChannelOrder(Base):
    def test_form_first_the_one_question(self):
        out = self.hold(ALL4)
        self.assertEqual(out["status"], "choose_route")
        self.expect(out, "ask_one_question", "ask_book")

    def test_whatsapp_before_email_and_phone(self):
        out = self.hold({k: v for k, v in ALL4.items() if k != "form"})
        self.expect(out, "request_whatsapp", "request_wait")
        self.assertEqual(out["status"], "draft_message")                         # (until item 3: the message they send)
        self.assertNotIn("/api/booking/emails", self.api.paths())

    def test_email_before_phone(self):
        out = self.hold({"email": ALL4["email"], "phone": ALL4["phone"]})
        self.expect(out, "request_email", "request_wait")
        self.assertEqual((out["status"], out["route"]), ("awaiting_yes", "email"))
        self.assertNotIn("/api/booking/calls", self.api.paths())

    def test_phone_only_far_away_waits_to_call(self):
        # Sasha 269 · MOVED (CR 100): R3's call is the ACT's — its card (venue.submit_booking route "call"), never Sasha's own
        # /api/booking/calls (a call no act opened is never placed)
        out = self.hold({"phone": ALL4["phone"]})
        self.assertEqual(out["rules"]["action"], "wait")
        self.assertEqual(out["route"], "agapi_call")
        got = self.yes()
        self.assertEqual(self.api.bodies("/api/booking/calls"), [])
        self.assertEqual(got["status"], "calling")


# ── R2 · a form → the ONE question; its two answers ──────────────────────────────────────────────────────────────────────────

class R2TheOneQuestion(Base):
    def test_the_question_is_the_rules_phrase_and_her_voice(self):
        self.assertEqual(V.ASK_BOOK, BR.PHRASES["ask_book"])
        self.assertEqual(V.SENT, BR.PHRASES["sent"])
        self.assertEqual(V.DONE_FORM, BR.PHRASES["done_form"])
        out = self.hold({"form": {}, "email": ALL4["email"]})
        self.assertEqual(out["ask"], V.ASK_BOOK)
        self.assertEqual([o["title"] for o in out["options"]], ["Prefilled form", "Handle it"])
        self.assertNotIn(ACCT, VN._HELD)                                           # nothing prepared before the answer

    def test_handle_it_fills_and_sends_the_form_on_the_yes(self):
        # Sasha 270 · MOVED (CR 101: one form engine): on the one path "Handle it" is AgAPI's send (test_s254_handle_it_live.TheSend:
        # the read-back, the yes, venue.submit_booking). Sasha's own form sender (/api/booking/forms) is old S1's only — with no AgAPI
        # here, their page, prepared; never a send of Sasha's own
        decided = []

        async def via(ctx, a, rd, res, at, now, d, card, r6=False, link=None):
            decided.append(d["action"])
            return None
        with mock.patch.object(VN, "_via_agapi", via):
            out = self.hold({"form": {}, "email": ALL4["email"]}, route="form")
        self.assertEqual(decided, ["fill_form_zero_touch"])                         # the rules: handle it
        self.expect(out, "prepared_link", "prepared_link")
        self.assertNotIn("/api/booking/forms", self.api.paths())

    def test_a_prefilled_form_is_their_page_never_sent(self):
        out = self.hold({"form": {}, "email": ALL4["email"]}, route="page", website="https://casagate.es")
        self.expect(out, "prepared_link", "prepared_link")
        self.assertNotIn("/api/booking/forms", self.api.paths())                  # nothing reaches the venue


# ── R3 / R4 · 48 h: a request and wait; within it a call, or their page ─────────────────────────────────────────────────────

class R3R4FortyEightHours(Base):
    def test_49_hours_is_still_a_request_never_a_call(self):
        out = self.hold({"email": ALL4["email"], "phone": ALL4["phone"]}, hours=49)
        self.expect(out, "request_email", "request_wait")
        self.assertNotIn("/api/booking/calls", self.api.paths())

    def test_20_hours_calls_on_is_a_call_on_the_yes(self):
        # Sasha 265 · item 4 (booking-rules/2, CR 99): the call is the ONE question — its read-back on a card with one "OK" — and the yes
        # (the tap) is its approval: the act, then ONLY "On it — …". Sasha's own /api/booking/calls is never used (no act, no call).
        out = self.hold({"email": ALL4["email"], "phone": ALL4["phone"]}, hours=20)
        self.expect(out, "ask_call", "ask_call_now")
        self.assertEqual((out["status"], out["route"], out["choices"]), ("awaiting_yes", "agapi_call", list(BD.OK_CHOICES)))
        self.assertEqual(out["ask"], BR.PHRASES["ask_call_now"].format(head=out["ask"].split(" — ")[0]))
        got = self.yes()
        self.assertEqual(got["status"], "calling")
        self.assertEqual(got["line"], "On it — I'll call them now and let you know.")
        self.assertNotIn("/api/booking/calls", self.api.paths())


class R4CallsOff(Base):
    access = {**LIVE, "calls": "off"}

    def test_20_hours_calls_off_is_their_page_and_no_call(self):
        out = self.hold({"email": ALL4["email"], "phone": ALL4["phone"]}, hours=20)
        self.expect(out, "prepared_link", "no_real_sends")
        self.assertNotIn("/api/booking/calls", self.api.paths())


# ── R5 / R6 · hotels ────────────────────────────────────────────────────────────────────────────────────────────────────────

class R6Hotel(Base):
    def test_arriving_in_18_hours_call_and_email_at_once_one_yes(self):
        # Sasha 269 · MOVED (CR 100): a hotel STAY (nights) has no AgAPI act, so R6 is its email alone — never a call of Sasha's own
        # (the call half was /api/booking/calls, which no act opened). A table or a spa: the email act + venue.call_again R6.
        out = self.hold({"email": ALL4["email"], "phone": ALL4["phone"]}, hours=18, what="a room", venue="Hotel Gate", nights=2)
        self.assertEqual(out["rules"]["action"], "call_and_email")
        self.assertEqual((out["status"], out["route"]), ("awaiting_yes", "email"))
        self.assertEqual(self.api.bodies("/api/booking/calls"), [])
        self.assertEqual(len(self.api.bodies("/api/booking/emails")), 1)
        self.yes()
        self.assertIn("/api/booking/emails/e-1/send", self.api.paths())
        self.assertFalse(any(p.startswith("/api/booking/calls") for p in self.api.paths()))

    def test_a_hotel_request_carries_the_24_hour_call_in_its_read_back(self):
        out = self.hold({"email": ALL4["email"], "phone": ALL4["phone"]}, hours=30, what="a room", venue="Hotel Gate", nights=2)
        self.expect(out, "request_email", "request_wait", say_now=False)
        plan = self.api.bodies("/api/booking/emails")[0]["plan_line"]
        self.assertIn(f"within {BR.HOTEL_NO_REPLY_HOURS} hours, I'll call them", plan)
        self.assertIn("Your yes covers these steps", plan)

    def test_a_restaurant_request_carries_no_call(self):
        self.hold({"email": ALL4["email"], "phone": ALL4["phone"]}, hours=72)
        self.assertNotIn("plan_line", self.api.bodies("/api/booking/emails")[0])


class R5HotelNoReplySweep(unittest.TestCase):
    """The follow-up runs in proactive's sweep; its TIMING is decide()'s (state.request_sent_at / venue_replied)."""

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
        self.acts = [{"act_id": "act_h", "venue": "Hotel Gate", "when": f"{day}T{hhmm}", "party": 2, "state": "sent", "category": "hotel",
                      "country": "ES", "venue_phone": "+34910000000", "sent_at": (self.now - timedelta(hours=25)).isoformat()}]
        self.again_says = {"status": "calling", "say": "On it — I'll call them now and let you know."}

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
                  mock.patch.object(VC, "tell", tell), mock.patch.object(GW, "STORE", Chans()),
                  mock.patch.dict(os.environ, {"SASHA_NO_REPLY_CALL": "1"})):
            p.start()
            self.addCleanup(p.stop)
        BD._STOPPED.pop(ACCT, None)

    def test_25_hours_without_a_reply_a_hotel_is_called_under_the_yes(self):
        from booking_signer import proactive as PR
        live_access(self)
        done = run(PR.no_reply_offers(self.now))
        self.assertEqual(self.calls, [("act_h", "R5")])                           # the act's own follow-up call (venue.call_again R5)
        self.assertEqual(done[0]["rules"], "call")
        self.assertEqual(self.told, [self.again_says["say"]])                      # the act's words
        self.assertEqual(run(PR.no_reply_offers(self.now)), [])                   # once

    def test_23_hours_still_waits(self):
        from booking_signer import proactive as PR
        live_access(self)
        self.acts[0]["sent_at"] = (self.now - timedelta(hours=23)).isoformat()
        self.assertEqual(run(PR.no_reply_offers(self.now)), [])
        self.assertEqual(self.calls, [])

    def test_calls_off_the_stop_is_told(self):
        from booking_signer import proactive as PR
        live_access(self, {**LIVE, "calls": "off"})
        self.again_says = {"status": "not_allowed", "say": BR.PHRASES["no_real_sends"]}   # the ACT refuses it, in its words
        done = run(PR.no_reply_offers(self.now))
        self.assertEqual(done[0]["outcome"], "not_allowed")
        self.assertEqual(self.told, [BR.PHRASES["no_real_sends"]])

    def test_no_env_timing(self):
        src = (BACKEND / "booking_signer" / "proactive.py").read_text()
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

        class _Store:
            async def channel_of_account(self, acct):
                return {"wa_id_sha256": "x" * 64}
        for p in (mock.patch.object(GW, "_tell", tell), mock.patch.object(GW, "STORE", _Store()),
                  mock.patch.object(GW, "venue_display", mock.AsyncMock(return_value="Casa Lucio")),
                  mock.patch.object(GW, "push_payment_question", mock.AsyncMock(side_effect=AssertionError("asked to pay"))),
                  mock.patch.object(CR.C, "place_call", mock.AsyncMock(side_effect=AssertionError("a confirmation call"))),   # Sasha 269 · moved
                  mock.patch("booking_signer.followup.after_call", mock.AsyncMock(return_value=None)),
                  mock.patch("booking_signer.followup.sms_ask", mock.AsyncMock(return_value="no")),
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
    def dialled(self, n, minutes_ago=120, account=ACCT, venue_key="read:other"):
        now = datetime.now(timezone.utc)
        for i in range(n):
            cid = str(uuid.uuid4())
            self.calls_store.calls[cid] = {"call_id": cid, "account_id": account, "status": "answered", "venue_key": venue_key,
                                           "dialled_number": f"+3491000000{i}", "approved_at": now - timedelta(minutes=minutes_ago + i)}

    def test_a_4th_call_today_is_refused_calls_cap(self):
        self.dialled(3)
        out = self.hold({"email": ALL4["email"], "phone": ALL4["phone"]}, hours=20)
        self.expect(out, "prepared_link", "calls_cap")
        self.assertNotIn("/api/booking/calls", self.api.paths())

    def test_2_other_peoples_calls_dont_count(self):
        self.dialled(2, account="00000000-0000-4000-8000-0000000000aa")
        out = self.hold({"email": ALL4["email"], "phone": ALL4["phone"]}, hours=20)
        self.expect(out, "ask_call", "ask_call_now")   # Sasha 265 · booking-rules/2: the call, asked as the ONE question

    def test_the_server_net_still_holds(self):
        self.dialled(BD.SERVER_CALLS_PER_DAY, account="00000000-0000-4000-8000-0000000000aa")
        out = self.hold({"email": ALL4["email"], "phone": ALL4["phone"]}, hours=20)
        self.expect(out, "prepared_link", "calls_cap")

    def test_the_same_venue_within_30_minutes_is_too_soon(self):
        self.dialled(1, minutes_ago=10, venue_key="read:r-1")
        out = self.hold({"email": ALL4["email"], "phone": ALL4["phone"]}, hours=20)
        self.expect(out, "prepared_link", "too_soon")

    def test_31_minutes_later_a_call_again(self):
        self.dialled(1, minutes_ago=31, venue_key="read:r-1")
        self.expect(self.hold({"email": ALL4["email"], "phone": ALL4["phone"]}, hours=20), "ask_call", "ask_call_now")   # Sasha 265

    def test_refused_at_the_dial_the_stop_is_said_in_the_turn(self):
        # Sasha 265 · item 4: R10 is the ACT's (CR 99): a call it won't open (today's calls made) is said in the turn, nothing dialled
        self.hold({"email": ALL4["email"], "phone": ALL4["phone"]}, hours=20)
        fake_act(self, answer={"ok": True, "status": "not_allowed", "route": "call", "say": BR.PHRASES["calls_cap"]})
        got = self.yes()
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
        for rungs, hours in ((ALL4, 72), ({"email": ALL4["email"]}, 72), ({"phone": ALL4["phone"]}, 20), ({"link": {"value": "TheFork"}}, 72), ({}, 72)):
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


# ── R13 / R14 · a CAPTCHA is theirs; a platform is handed over, never booked ────────────────────────────────────────────────

class R13R14(Base):
    def test_a_captcha_is_never_zero_touch_even_when_asked_to_handle_it(self):
        out = self.hold({"form": {}}, route="form", facts=[{"kind": "challenge", "value": "captcha"}], website="https://casagate.es")
        self.expect(out, "prepared_link", "prepared_link_captcha")
        self.assertNotIn("/api/booking/forms/f-9/send", self.api.paths())

    def test_a_platform_is_handed_over_never_named_never_booked(self):
        out = self.hold({"link": {"value": "TheFork"}})
        self.expect(out, "hand_over_platform_link", "platform", platform="a booking platform")
        self.assertEqual(V.channel_words(out["say"]), [])                           # her voice never names it
        self.yes()
        self.assertEqual(self.taps, ["https://www.thefork.es/restaurante/x-r1"])    # their page, to the person
        self.assertFalse(any(p.endswith("/send") or p.endswith("/place") for p in self.api.paths()))

    def test_own_channels_come_before_a_platform(self):
        out = self.hold({"link": {"value": "TheFork"}, "email": ALL4["email"]})
        self.expect(out, "request_email", "request_wait")


# ── access (§B) — booking_decide.access_of, the ONE function: the record (item 5) ──────────────────────────────────────────────────

class AccessTest(Base):
    access = {"mode": "test", "calls": "on", "real_venue_sends": "on"}

    def setUp(self):   # Sasha 256 · Kanoe's test venue is held by a TEST person only (agapi/test_venues)
        super().setUp()
        from agapi import test_venues as TV
        p = mock.patch.object(TV, "mode_of", mock.AsyncMock(return_value="test"))
        p.start()
        self.addCleanup(p.stop)

    def test_a_test_person_never_reaches_a_real_venue(self):
        out = self.hold(ALL4, hours=20)
        self.expect(out, "prepared_link", "not_live")
        self.assertFalse([p for p in self.api.paths() if p in ("/api/booking/forms", "/api/booking/emails", "/api/booking/calls")])

    def test_a_test_venue_is_fine_in_test_mode(self):
        # Sasha 270 · MOVED: the decision is the same (handle it — never "not_live"); the send is AgAPI's (none here → their page)
        decided = []

        async def via(ctx, a, rd, res, at, now, d, card, r6=False, link=None):
            decided.append((d["action"], d["say"]))
            return None
        with mock.patch.object(VN, "_via_agapi", via):
            out = self.hold({"form": {}}, venue="Sasha Test Venue", route="form")
        self.assertEqual(decided, [("fill_form_zero_touch", "sent")])
        self.assertNotEqual(out["rules"]["say_key"], "not_live")


class AccessSendsOff(Base):
    access = {"mode": "live", "calls": "off", "real_venue_sends": "off"}

    def test_real_sends_off_is_their_page_said_kindly(self):
        out = self.hold({"email": ALL4["email"]})
        self.expect(out, "prepared_link", "no_real_sends")


class AccessOf(unittest.TestCase):
    def test_the_record_in_one_function(self):
        """Sasha 254 item 5 · access_of IS the person's record (agapi.person_access): mode, calls, real-venue sends — nothing added."""
        from agapi import person_access as PA
        other = "00000000-0000-4000-8000-0000000000bb"
        with mock.patch.object(PA, "RESOLVER", None), PA.records({ACCT: PA.LIVE_PERSON, other: {"mode": "live"}}):
            self.assertEqual(run(BD.access_of(ACCT)), LIVE)
            self.assertEqual(BD.access_cached(ACCT), LIVE)
            self.assertEqual(run(BD.access_of(other)), {"mode": "live", "calls": "off", "real_venue_sends": "off"})
        with mock.patch.object(PA, "RESOLVER", None), PA.records({ACCT: {**PA.LIVE_PERSON, "mode": "test"}}):
            self.assertEqual(run(BD.access_of(ACCT))["mode"], "test")
        with mock.patch.object(PA, "RESOLVER", None), mock.patch.dict(os.environ, {"SASHA_AGAPI_KEY": ""}):
            PA.clear()
            self.assertEqual(run(BD.access_of(other)), {"mode": "test", "calls": "off", "real_venue_sends": "off"})   # no row: closed

    def test_utc_from_the_venues_local_time(self):
        self.assertEqual(BD.utc_of("2026-07-01T21:00", "ES"), "2026-07-01T19:00:00+00:00")   # Madrid in summer: UTC+2
        self.assertEqual(BD.utc_of("2026-12-01T21:00", "PT"), "2026-12-01T21:00:00+00:00")   # Lisbon in winter: UTC


# ── every surface, the one path ─────────────────────────────────────────────────────────────────────────────────────────────

class EverySurface(Base):
    def test_s2_whatsapp_next_and_old_s1_all_ask_the_rules(self):
        for surface, parity in (("s2", "on"), ("wa", "on"), ("s1", "on"), ("s1", "off")):
            VN._HELD.pop(ACCT, None)
            self.surface = surface
            with mock.patch.dict(os.environ, {"SASHA_S1_PARITY": parity}), \
                    mock.patch.object(BD, "decide_for", wraps=BD.decide_for) as spy:
                out = self.hold({"email": ALL4["email"], "phone": ALL4["phone"]}, hours=20)
            self.assertEqual(spy.call_count, 1, (surface, parity))
            if parity == "off":   # old S1: booking-rules/1's answer, byte-identical (booking_decide.as_v1)
                self.expect(out, "call", "calling")
            else:                 # Sasha 265 · the one path: booking-rules/2 — the call IS the ONE question (its card)
                self.expect(out, "ask_call", "ask_call_now")

    def test_the_old_flow_and_the_web_card_ask_the_same_rules(self):
        rd = {"venue": "Casa Gate", "country": "ES", "rungs": {"email": {"value": "x@casagate.es"}, "phone": {"value": "+34910000000"}}}
        day, hhmm = local(20)
        with mock.patch.object(BD, "access_cached", lambda a: dict(LIVE)):
            dv = GW.decision_of(rd, None, f"{day}T{hhmm}", datetime.now(timezone.utc), ACCT)
            self.assertEqual((dv.route, dv.then, dv.alternatives), ("call", None, []))
            self.assertTrue(dv.reason.startswith(BR.PHRASES["calling"]))
            lad = GW.ladder_of({**rd, "rungs": {"form": {}, **rd["rungs"]}}, {"when": {"at": f"{day}T{hhmm}"}}, datetime.now(timezone.utc), ACCT)
            self.assertEqual(lad["line"], BR.PHRASES["ask_book"])


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
        from booking_signer import decide as D
        for gone in ("decide", "ladder", "line", "urgent_hours", "reply_hours", "tap_window_min", "available", "urgent", "Venue", "Decision"):
            self.assertFalse(hasattr(D, gone), gone)
        vn = (BACKEND / "agapi" / "venues.py").read_text()
        for gone in ("_hold_inner", "_engine_route", "ladder_of", "decision_of", "wa_first", "ROUTE_TO_PREFER"):
            self.assertNotIn(gone, vn)
        for rel, src in self.sources():
            self.assertNotRegex(src, r"\bD\.(decide|ladder|urgent_hours|reply_hours|tap_window_min)\(", rel)

    def test_one_decider_call_site(self):
        hits = [rel for rel, src in self.sources() if re.search(r"\bBR\.decide\(|booking_rules\.decide\(", src) and not rel.startswith("scripts/")]
        self.assertEqual(sorted(set(hits)), ["agapi/booking_decide.py"], hits)


if __name__ == "__main__":
    unittest.main()
