"""Sasha 265 · T47 — S2 freeze bugs (Tyler, 14 Oct 16:40) + CR 99 wired. One gate per item; each fails on 264's code. Offline.

  1 MIC        — connect() waited on `await ctx.resume()` made AFTER the permission and the key: a phone (or a page with no tap yet) never
                 resumes audio there, so no socket ever reached Deepgram (his iPhone 14:21Z, his Mac 14:46Z: a key minted, no listen).
                 The audio is made and resumed before the first await and never waited on; a word spoken over her is kept (pre-roll).
  2 AVATAR     — every arrival plays the one sequence (her face full size → the hello → the circle); the circle's slot is watched.
  3 NEW CHAT   — the conversation cleared in its one place (s2_memory.clear_conversation, DELETE /api/agent/memory); bookings stay.
  4 CR 99      — booking-rules/2 vendored byte-identical; the ONE question is the call's card (the tap is the approval: in_app_tap);
                 only "On it — …" said; a booking call is placed only from its act (call_plan) and every attempt goes back to the act;
                 the WhatsApp yes is in_app_tap kind "whatsapp", signed; status says calling / no_answer.
  5 SILENCE    — a request for work hears voice.FIRST_LINE at once (the stream's first event; WhatsApp's first message), then a line about
                 every voice.PROGRESS_S (5 s); /next's standby face shows it (no call: she never just looks at you).

    cd backend && python -m unittest tests.test_s265 -v
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import inspect
import os
import pathlib
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

from agapi import booking_decide as BD, s2_memory as MEM, s2_status as SS, venue_calls as VC, venue_submit as VS, venues as VN
from agapi import yes_gate as YG
from agapi.booking_rules import booking_rules as BR
from app.agent import sasha as S, voice as V
from booking_signer import call_routes as CR, call_store as CS, calls as C, inbound_phone as IP
from tests import test_s254_one_decider as T254

ACCT = "00000000-0000-4000-8000-000000000265"
BACKEND = pathlib.Path(__file__).resolve().parents[1]


def run(c):
    return asyncio.run(c)


async def collect(agen):
    return [e async for e in agen]


def _tsx(case, rel):
    """A frontend file — skipped where the checkout is backend-only (Railway's deploy gate builds backend/ alone)."""
    f = BACKEND.parent / "frontend" / rel
    if not f.exists():
        case.skipTest("frontend/ is not in this checkout (a backend-only build)")
    return f.read_text()


# ── 1 · MIC ─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
class TheMicOpensItsSocketWhatever(unittest.TestCase):
    def test_gate_the_audio_is_made_before_the_first_await_and_never_waited_on(self):
        src = _tsx(self, "app/components/VoiceButton.tsx")
        import re
        body = src[src.index("const connect = useCallback(async () => {"):src.index("}, [])  // stable — all dynamic props are read via refs above")]
        body = re.sub(r"//[^\n]*", "", body)   # the code only, never its comments
        made = body.index("const ctx = new AudioContext()")
        self.assertLess(made, body.index("await "), "the AudioContext must be made (and resumed) before the first await")
        self.assertNotIn("await ctx.resume()", body)                       # 264: waited for good on a phone — no socket
        self.assertIn("Promise.race([resumed, new Promise(r => setTimeout(r, RESUME_WAIT_MS))])", body)
        self.assertLess(body.index("Promise.race([resumed"), body.index("new WebSocket("))   # the socket opens either way

    def test_gate_a_word_said_over_her_is_kept_and_her_own_voice_never(self):
        src = _tsx(self, "app/components/VoiceButton.tsx")
        self.assertIn("for (const f of preroll.splice(0)) send(f)", src)                      # on barge-in only
        self.assertIn("if (preroll.length) { preroll.length = 0; prerollLen = 0 }", src)      # opened by her stopping: dropped


# ── 2 · AVATAR ──────────────────────────────────────────────────────────────────────────────────────────────────────────────────
class EveryArrivalShowsHer(unittest.TestCase):
    def test_gate_one_arrival_sequence_no_return_skip(self):
        hello = _tsx(self, "app/s2/S2Hello.tsx")
        self.assertNotIn("getItem('s2_hello')", hello)                         # a return skipped her
        self.assertNotIn("opacity: phase === 'starting' ? 0", hello)           # never invisible while her face starts
        self.assertIn("const big = shown === 'face' || shown === 'card'", hello)
        self.assertIn("prefers-reduced-motion: reduce", hello)
        self.assertIn("new MutationObserver(look)", hello)                     # the circle's slot, watched
        app = _tsx(self, "app/s2/S2App.tsx")
        self.assertIn("started={arrivalStarted(msgs)}", app)


# ── 3 · NEW CHAT ────────────────────────────────────────────────────────────────────────────────────────────────────────────────
class NewChatClearsTheConversationOnly(unittest.TestCase):
    def setUp(self):
        self.addCleanup(setattr, MEM, "RUN", MEM.RUN)
        MEM.RUN = None
        MEM._MEM[ACCT] = {"recent": [{"role": "user", "content": "dinner"}], "summary": ["dinner in Sol"], "thing": "dinner in Sol",
                          "pending": {"kind": "question", "asked": "Which one?"}, "screen": {"cards": []}, "decided": {"what": "X"},
                          "session": "s2-a", "session_lines": 2, "name": "Eva",
                          "kinds": {"handover": {"n": 1}, "screen": {"s": 1}, "openers": {"o": 1}, "venue_acts": [{"act_id": "a"}],
                                    "prepared": [1], "outcomes_open": [2]}}
        self.addCleanup(MEM._MEM.pop, ACCT, None)
        YG._RB[(ACCT, "book_venue")] = {"x": 1}
        YG._APV[(ACCT, "book_venue")] = {"x": 1}
        YG._RB[("someone-else", "book_venue")] = {"x": 1}
        self.addCleanup(YG._RB.pop, ("someone-else", "book_venue"), None)
        VN._SHOWN[ACCT] = {"p": {}}

    def test_gate_the_conversation_goes_and_the_bookings_stay(self):
        out = run(MEM.clear_conversation(ACCT))
        m = MEM._MEM[ACCT]
        for k in MEM.CONVERSATION:
            self.assertNotIn(k, m)
        self.assertEqual(sorted(m["kinds"]), ["outcomes_open", "prepared", "venue_acts"])   # the acts, prepared pages, outcomes stay
        self.assertEqual(m["name"], "Eva")
        self.assertIn("kinds.handover", out["cleared"])
        self.assertNotIn((ACCT, "book_venue"), YG._RB)                         # a "yes" in the new chat lands on no old card
        self.assertNotIn((ACCT, "book_venue"), YG._APV)
        self.assertIn(("someone-else", "book_venue"), YG._RB)                  # nobody else's
        self.assertNotIn(ACCT, VN._SHOWN)
        self.assertIsNone(MEM.line_for(m, ACCT))                               # no "Welcome back — we were looking at …"

    def test_gate_one_route_both_surfaces(self):
        self.assertIn(("/memory", "DELETE"), {(r.path.replace("/api/agent", ""), m) for r in S.router.routes for m in getattr(r, "methods", [])})
        self.assertIn("method: 'DELETE'", _tsx(self, "app/s2/S2App.tsx"))
        self.assertIn("fetch('/api/sasha-agent/memory', { method: 'DELETE'", _tsx(self, "app/next/page.tsx"))
        for rel in ("app/api/s2-memory/route.ts", "app/api/sasha-agent/memory/route.ts"):
            self.assertIn("/api/agent/memory`, { method: 'DELETE'", _tsx(self, rel))


# ── 4 · CR 99 ───────────────────────────────────────────────────────────────────────────────────────────────────────────────────
ROW_934 = {"booking_rules.py": "1ee3c87abd347eaf87bd627a3887f5bd9d9e37c9d723d408dd6184409716dd0c",
           "vectors.json": "e326bbc7e268ad1d4032bccf56676346b3fc660819ac237e507c2dd9edc65b47",
           "test_booking_rules.py": "188aa758b1df7ef343496de15cb547cf464d1c000192cc2b021a92d6ffe8a8f2"}
PAGE_AND_PHONE = {"form": {}, "phone": {"fact_index": 0, "value": "+34910000000"}}


class BookingRules2(unittest.TestCase):
    def test_gate_vendored_byte_identical_to_row_934(self):
        d = BACKEND / "agapi" / "booking_rules"
        for name, want in ROW_934.items():
            self.assertEqual(hashlib.sha256((d / name).read_bytes()).hexdigest(), want, name)
        self.assertTrue(BR.VERSION.startswith("booking-rules/2"))

    def test_old_s1_keeps_booking_rules_1(self):
        call = {"action": "ask_call", "say": "ask_call_now", "say_text": "x"}
        self.assertEqual((BD.as_v1(call)["action"], BD.as_v1(call)["say_text"]), ("call", BR.PHRASES["calling"]))
        q = {"action": "ask_one_question", "say": "ask_page_or_call", "say_text": "x"}
        self.assertEqual(BD.as_v1(q)["say_text"], BR.PHRASES["ask_book"])

    def test_the_booking_words_are_local(self):
        now = datetime(2026, 10, 14, 10, 0, tzinfo=timezone.utc)
        b = BD.booking_words("Casa Gate", 2, "2026-10-14T21:00", "ES", now)
        self.assertEqual((b["day"], b["time"], b["party"]), ("today", "21:00", 2))
        self.assertEqual(BR.head({"booking": b, "venue": {"name": "Casa Gate"}}), "2 people at Casa Gate, today 21:00")


class TheCardIsTheQuestion(T254.Base):
    access = T254.LIVE

    def test_gate_soon_their_page_and_a_phone_two_buttons(self):
        out = self.hold(PAGE_AND_PHONE, hours=20)
        self.assertEqual(out["status"], "awaiting_yes")
        self.assertEqual(out["choices"], list(BD.CALL_CHOICES))                         # "Fill in their page" / "Call them"
        self.assertTrue(out["ask"].endswith("— fill in their page now, or shall I call them?"), out["ask"])
        self.assertIn(("prepare", {"phone": "+34910000000", "open_now": False}), self.vs_calls)   # the act carries the call
        self.assertIn(("read_back", "call"), self.vs_calls)                              # the CALL's read-back
        self.assertEqual(V.read_back_line("hold_venue", {"ok": True, "result": out}), out["ask"])   # said by code, word for word
        ev = S.render("hold_venue", out, {})
        self.assertEqual((ev["kind"], ev["read_back_id"], ev["choices"]), ("read_back", "rbk_1", list(BD.CALL_CHOICES)))
        self.assertNotIn("/api/booking/calls", self.api.paths())

    def test_gate_the_tap_is_the_approval_and_only_on_it_is_said(self):
        self.hold(PAGE_AND_PHONE, hours=20)
        VN._HELD[T254.ACCT]["at"] -= timedelta(minutes=1)
        tok = VS.TAP.set({"kind": "supabase", "token": "t"})
        try:
            evs = run(collect(S.card_tap(T254.ACCT, "s254d", "s2", {"read_back_id": "rbk_1", "choice": "call"}, "Call them")))
        finally:
            VS.TAP.reset(tok)
        text = next(e["delta"] for e in evs if e["type"] == "text")
        self.assertEqual(text, "On it — I'll call them now and let you know.")             # ONLY the act's say
        self.assertIn(("submit", "rbk_1"), self.vs_calls)
        self.assertNotIn("/api/booking/calls", self.api.paths())                            # never Sasha's own call

    def test_a_tap_on_a_card_no_longer_there_sends_nothing(self):
        self.hold(PAGE_AND_PHONE, hours=20)
        evs = run(collect(S.card_tap(T254.ACCT, "s254d", "s2", {"read_back_id": "rbk_other", "choice": "call"}, "Call them")))
        self.assertEqual(next(e["delta"] for e in evs if e["type"] == "text"), V.NOTHING_WAITING)
        self.assertNotIn(("submit", "rbk_other"), self.vs_calls)

    def test_no_number_of_their_own_is_never_a_call(self):
        out = self.hold({"form": {}, "phone": {"fact_index": 0}}, hours=20)                 # a listing's number: never handed on (Sasha 64)
        self.assertNotIn("choices", out)
        self.assertFalse([c for c in self.vs_calls if c[0] == "prepare" and c[1]])


class OnlyFromTheAct(unittest.TestCase):
    def held(self):
        return {"venue": "Casa Gate", "summary": "Thu 15 Oct at 21:00 for 2", "when": "2026-10-15T21:00", "party": 2, "lines": ["2 people …"],
                "timezone": "Europe/Madrid", "name": "Eva"}

    def test_gate_a_booking_call_without_an_act_is_never_placed(self):
        self.assertTrue(CR.ACT_REQUIRED)
        self.assertTrue(CR._no_act({"brief": {"purpose": "book"}}))
        self.assertFalse(CR._no_act({"brief": {"purpose": "book", "act_id": "act_1"}}))
        self.assertFalse(CR._no_act({"brief": {"purpose": "late"}}))                     # not a booking act
        self.assertNotIn("ACT_REQUIRED", "".join(l for l in inspect.getsource(CR).splitlines() if "getenv" in l or "environ" in l))

    def test_gate_simulate_dials_nothing(self):
        with mock.patch.object(C, "place_call", mock.AsyncMock()) as pc:
            got = run(VC.dial(ACCT, {"act_id": "act_1", "call_plan": {"phone": "+15005550193", "simulate": True}}, self.held()))
        self.assertEqual(got["status"], "simulated")
        pc.assert_not_called()

    def test_gate_bland_gets_the_plan_and_the_row_is_keyed_by_its_act(self):
        store = CS.MemoryCallStore()
        plan = {"phone": "+34910000000", "when": "now", "opening": BR.call_opening("calling to book a table for 2."),
                "rules": list(BR.CALL_RULES), "payload": dict(BR.CALL_PAYLOAD), "next_call": {"allowed": True}, "simulate": False}
        placed = C.Placed(placed=True, bland_call_id="bl_1", http_status=200, answer={"status": "success"}, why=None)
        with mock.patch.object(CR, "CALL_STORE", store), mock.patch.object(C, "calls_enabled", lambda: True), \
                mock.patch.object(C, "bland_key", lambda: "k"), mock.patch.object(C, "place_call", mock.AsyncMock(return_value=placed)) as pc:
            got = run(VC.dial(ACCT, {"act_id": "act_1", "call_plan": plan}, self.held()))
        self.assertEqual(got["status"], "placed")
        row = store.calls[got["call_id"]]
        self.assertEqual(row["brief"]["act_id"], "act_1")
        body = pc.call_args.args[2]
        self.assertEqual((body["phone_number"], body["first_sentence"], body["voicemail"], body["record"]),
                         ("+34910000000", plan["opening"], BR.CALL_PAYLOAD["voicemail"], False))
        self.assertTrue(body["first_sentence"].startswith(BR.CALL_DISCLOSURE[:40]))      # R7: the AI disclosure first

    def test_never_before_next_call_allowed_at(self):
        now = datetime(2026, 10, 14, 12, 0, tzinfo=timezone.utc)
        at = VC.due_at({"when": "now", "next_call": {"allowed": False, "allowed_at": "2026-10-14T12:30:00Z"}}, self.held(), now)
        self.assertEqual(at, datetime(2026, 10, 14, 12, 30, tzinfo=timezone.utc))
        closed = VC.due_at({"when": "when they open at 13:00", "opens_at": "13:00", "next_call": {"allowed": True}}, self.held(), now)
        self.assertEqual(closed, datetime(2026, 10, 14, 11, 10, tzinfo=timezone.utc) + timedelta(days=1))  # 13:00 Madrid has passed

    def test_gate_after_every_call_the_attempt_and_its_words(self):
        told = []

        async def tell(account, text):
            told.append(text)
            return "captured"
        reading = C.CallReading(state="not_reached", outcome=None, venue_words="", quote=None, why="no answer", offer=None)
        res = {"ok": True, "result": {"status": "recorded", "state": "no_answer", "say": BR.PHRASES["no_answer"],
                                      "next_step": {"kind": "their_page", "page": "https://casagate.es/reservas"}}}
        with mock.patch.object(VS, "call_attempt", mock.AsyncMock(return_value=res)) as ca, mock.patch.object(VC, "tell", tell):
            got = run(VC.after_call({"account_id": ACCT, "brief": {"act_id": "act_1"}}, reading))
        ca.assert_awaited_once_with(ACCT, "act_1", "no_answer", None, "none")
        self.assertEqual(told, [BR.PHRASES["no_answer"] + " https://casagate.es/reservas"])  # the next step, with it
        self.assertEqual(got["state"], "no_answer")

    def test_a_refused_attempt_is_the_dialler_s_bug_never_told_as_news(self):
        res = {"ok": True, "result": {"status": "refused", "rule": "R10", "reason": "too_soon"}}
        with mock.patch.object(VS, "call_attempt", mock.AsyncMock(return_value=res)), mock.patch.object(VC, "tell", mock.AsyncMock()) as t, \
                self.assertLogs("agapi.venue_calls", "ERROR"):
            got = run(VC.after_call({"account_id": ACCT, "brief": {"act_id": "act_1"}},
                                    C.CallReading(state="answered", outcome="yes", venue_words="sí", quote=None, why="", offer=None)))
        self.assertEqual(got["refused"], "too_soon")
        t.assert_not_called()

    def test_an_act_call_s_reading_goes_to_the_act(self):
        with mock.patch.object(VC, "after_call", mock.AsyncMock(return_value={"reported": True})) as ac:
            run(CR._follow_up({"call_id": "c", "account_id": ACCT, "brief": {"act_id": "act_1", "purpose": "book"}}, object()))
        ac.assert_awaited_once()


class TheWhatsAppYes(unittest.TestCase):
    def test_gate_the_tap_is_signed_as_agapi_checks_it(self):
        with mock.patch.dict(os.environ, {"SASHA_AGAPI_TAP_SECRET": "s3cret"}):
            sess = VS.whatsapp_session("rbk_1", "ab" * 32, {"wa_id": "+34 600 000 001", "message_id": "SM123"}, t=1760000000, nonce="n" * 16)
        want = hmac.new(b"s3cret", f"1760000000.{'n' * 16}.whatsapp.34600000001.SM123.rbk_1.{'ab' * 32}".encode(), hashlib.sha256).hexdigest()
        self.assertEqual(sess, {"kind": "whatsapp", "t": 1760000000, "nonce": "n" * 16, "wa_id": "34600000001", "message_id": "SM123",
                                "signature": want})

    def test_gate_a_signed_reply_is_in_app_tap_kind_whatsapp(self):
        seen = []

        async def call(account, op, body, approval=None):
            seen.append((op, body))
            return {"ok": True, "result": {"result": {"status": "calling", "act_id": "act_1"}}}
        tok = VS.WA.set({"wa_id": "+15005550101", "message_id": "SM9"})
        try:
            with mock.patch.dict(os.environ, {"SASHA_AGAPI_TAP_SECRET": "s"}), mock.patch.object(VS, "_call", call), \
                    mock.patch.object(VS, "_remember", mock.AsyncMock()):
                r = run(VS.submit(ACCT, {"read_back_id": "rbk_1", "prepared_id": "vpr_x", "end_user": "usr_1", "sha": "f" * 64}, "OK"))
        finally:
            VS.WA.reset(tok)
        self.assertTrue(r["ok"])
        ops = [o for o, _ in seen]
        self.assertEqual(ops, ["users.register", "approvals.in_app_tap"])                 # their number, then the tap
        self.assertEqual(seen[1][1]["session"]["kind"], "whatsapp")

    def test_only_a_signature_checked_message_sets_it(self):
        src = inspect.getsource(IP.sms)
        self.assertLess(src.index("p = await _verified(request"), src.index("VS.WA.set("))


class StatusSaysCalling(unittest.TestCase):
    def test_gate_calling_and_no_answer_are_said(self):
        st = {"venues": [{"venue": "Casa Gate", "date": "2026-10-15", "time": "21:00", "status": "calling",
                          "next_call": {"allowed": False, "allowed_at": "2026-10-15T12:30:00Z", "calls_left_today": 2}},
                         {"venue": "Bar Uno", "date": "2026-10-15", "time": "20:00", "status": "no_answer",
                          "next_step": {"kind": "their_page", "page": "https://baruno.es"}}]}
        line = SS.decide(st)["line"]
        self.assertIn("Not booked yet — I'm calling them: Casa Gate — 2026-10-15 21:00 · the next call from 12:30 UTC.", line)
        allowed = SS.decide({"venues": [{**st["venues"][0], "next_call": {"allowed": True, "allowed_at": "x", "calls_left_today": 3}}]})["line"]
        self.assertEqual(allowed, "Not booked yet — I'm calling them: Casa Gate — 2026-10-15 21:00.")   # never "now" or a count to retry on
        self.assertIn("Not booked — no one picked up: Bar Uno — 2026-10-15 20:00 · their page: https://baruno.es.", line)
        self.assertNotIn("Booked", line.replace("Not booked", ""))


# ── 5 · SILENCE ─────────────────────────────────────────────────────────────────────────────────────────────────────────────────
class TheFirstLineAtOnce(unittest.TestCase):
    def test_gate_a_request_for_work_gets_it_and_a_thanks_does_not(self):
        for m in ("I'd like you to book a trip for me if you could. To Australia.",
                  "About going on November 15 to November 27. And with just two of us", "Book a table for two tonight"):
            self.assertEqual(V.first_line(m), V.FIRST_LINE, m)
        for m in ("Yes", "Thanks!", "Hey Sasha", "What's the weather usually like in Lisbon in November?"):
            self.assertIsNone(V.first_line(m), m)
        self.assertEqual(V.PROGRESS_S, 5.0)

    def test_gate_it_is_the_stream_s_first_event_and_no_second_acknowledgement(self):
        async def turn():
            await asyncio.sleep(0.3)
            yield {"type": "filler", "text": "One moment."}
            yield {"type": "text", "delta": "Here."}
            yield {"type": "done", "text": "Here."}

        async def go():
            loop = asyncio.get_running_loop()
            t0, out = loop.time(), []
            async for e in S.with_holding(turn(), ACCT, first=V.FIRST_LINE):
                out.append((round(loop.time() - t0, 2), e))
            return out
        evs = run(go())
        self.assertEqual(evs[0][1]["text"], V.FIRST_LINE)
        self.assertLess(evs[0][0], 0.05)                                              # at once
        self.assertFalse([e for _, e in evs if e.get("type") == "filler"])           # the quiver's filler isn't said on top

    def test_gate_whatsapp_says_it_first(self):
        src = inspect.getsource(__import__("booking_signer.guest_whatsapp", fromlist=["x"])._brain_turn)
        self.assertIn("at_once = V.first_line(body) if body else None", src)
        self.assertIn("timeout=0 if at_once else V.HOLD_AFTER_S", src)

    def test_gate_the_page_says_it_at_once_from_the_one_rule(self):
        got = run(S.first_line_rule())
        self.assertEqual((got["line"], got["work"]), (V.FIRST_LINE, V._WORK.pattern))   # the words and the rule: voice.py's, read once
        fl = _tsx(self, "lib/first-line.ts")
        self.assertIn("apiUrl('/api/agent/first-line')", fl)
        self.assertNotIn("let me pull something together", fl)                 # the words are never written on the page
        self.assertIn("if (said1) { patch(m => ({ ...m, hold: said1 })); speaker.say(said1) }", _tsx(self, "app/s2/S2App.tsx"))
        self.assertIn("if (ev.first && said1) continue", _tsx(self, "app/s2/S2App.tsx"))
        chat = _tsx(self, "app/components/SashaChat.tsx")
        self.assertIn("if (said1) { show(said1); onWorking?.(said1); onSashaResponse?.(said1) }", chat)
        self.assertIn("if (ev.first && said1) continue", chat)

    def test_gate_next_shows_it_under_her_face_without_a_call(self):
        self.assertIn("onWorking?.(ev.text)", _tsx(self, "app/components/SashaChat.tsx"))
        self.assertIn("data-sasha-working-face", _tsx(self, "app/next/page.tsx"))


if __name__ == "__main__":
    unittest.main()
