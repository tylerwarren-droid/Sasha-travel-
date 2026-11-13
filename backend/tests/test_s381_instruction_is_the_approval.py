"""Sasha 381 · THE INSTRUCTION IS THE APPROVAL — no separate yes for a venue booking (Tyler, KANOE_DECISIONS.md, 12 Nov 20:11), and a term
the person didn't give is ASKED — only that term — never guessed, never a yes card (12 Nov 20:20, reading B). NO PATCHES.

Found: every venue act (Kanoe's form / email / WhatsApp, the call, the platform's Book) stopped on a read-back card ("Shall I send this to
Casa Gate? Every detail is on the card." · "Casa, Fri 13 Nov 21:00 for 2. Send?" · the call's OK) and waited for a yes in a later turn; a
party the person never gave was 2 (venues._reservation). Now ONE act path (venues._act), CR 196's shape: AgAPI's prepared booking →
approvals.mandate scope.booking {prepared_id, party, date, time} (every term as the person gave it; the door's proof of THIS turn — in the
app its id, on WhatsApp its signed message — used once) → ONE venue.submit_booking {prepared_id, mandate_id}, in the same turn, once.
A term AgAPI says they didn't give (term_not_given, missing) is asked — only it. Said in ONE line: AgAPI's instructed.say ("Booking now:
<venue>, <N> people, <date> at <time>.", CR 196, from the booking record) then "Booked — reference X." / "Requested — I'll tell you when
they reply."

    cd backend && python -m unittest tests.test_s381_instruction_is_the_approval -v
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import inspect
import os
import pathlib
import re
import unittest
from datetime import date
from unittest import mock

from agapi import v0 as API, venue_submit as VS, venue_truth as VT, venues as VN
from app.agent import voice as V
from tests.test_s254_handle_it_live import MDT, PREP, use_fake_agapi
from tests.test_s254_one_decider import ACCT, ALL4, Base, local, reader, engine_from

run = asyncio.run
BACKEND = pathlib.Path(__file__).resolve().parents[1]


class TheTermsAreTheirs(unittest.TestCase):
    """The door owns the person's words (what they SAID); AgAPI owns which terms are REQUIRED (term_not_given)."""

    def ctx(self, said, before=""):
        return API.Ctx(account=ACCT, user_said=said, said_before=before, surface="s2")

    def test_said_terms_reads_only_their_words(self):
        a = {"name": "Casa Gate", "day": "2026-11-20", "time": "21:00", "country": "ES", "party": 2}
        self.assertEqual(VN.said_terms(self.ctx("book Casa Gate 2026-11-20 at 21:00 for 2"), a), {"date": "2026-11-20", "time": "21:00", "party": 2})
        self.assertEqual(VN.said_terms(self.ctx("book Casa Gate 2026-11-20 at 21:00"), a), {"date": "2026-11-20", "time": "21:00"})   # 2 not said
        self.assertEqual(VN.said_terms(self.ctx("book Casa Gate at 21:00 for 2"), a), {"time": "21:00", "party": 2})

    def test_the_answer_completes_the_instruction_across_turns(self):
        a = {"name": "Casa Gate", "day": "2026-11-20", "time": "21:00", "country": "ES", "party": 4}
        self.assertEqual(set(VN.said_terms(self.ctx("4 people", before="book Casa Gate on 2026-11-20 at 21:00"), a)), {"date", "time", "party"})

    def test_the_question_is_agapis_term_in_her_words(self):
        self.assertEqual(V.TERM_ASK["party"], "For how many people?")
        self.assertFalse(hasattr(VN, "unsaid_term"))   # no list of her own of what's required


class ActedOnTheInstruction(Base):
    def setUp(self):
        super().setUp()
        self.agapi = use_fake_agapi(self)
        self.agapi.submit.update(status="sent", venue="La Taberna de Peñalver")

    def instruct(self, said, party=2, **extra):
        day, hhmm = local(72.0)
        args = {"name": "Casa Gate", "city": "Madrid", "country": "ES", "what": "dinner", "day": day, "time": hhmm,
                "place_id": "ChIJcasagate254", **({"party": party} if party else {}), **extra}
        rungs = {"email": ALL4["email"]}
        with mock.patch.object(VN, "_read", reader(rungs, "Casa Gate")), mock.patch.object(VN, "engine_channel", engine_from(rungs, None)):
            return run(VN.hold_venue(API.Ctx(account=ACCT, mode="test", user_said=said.format(day=day, hhmm=hhmm), session="s381",
                                             surface="s2", via="wa"), args)), day, hhmm

    def test_no_party_agapi_names_it_and_she_asks_only_it(self):
        out, day, hhmm = self.instruct("book Casa Gate {day} at {hhmm}", party=None)
        self.assertEqual((out["status"], out["ask"], out["terms"]), ("need_term", "For how many people?", ["party"]))
        self.assertNotIn("venue.prepare_booking", self.agapi.ops())                               # nothing prepared
        (m,) = [b for o, b, _a in self.agapi.calls if o == "approvals.mandate"]                  # AgAPI asked, with ONLY what they said
        self.assertEqual(m["scope"]["booking"], {"date": day, "time": hhmm})
        self.assertEqual(V.yes_line("hold_venue", {"ok": True, "result": out}), "For how many people?")   # said by code, word for word

    def test_the_whole_instruction_books_in_the_same_turn_in_one_line(self):
        out, day, hhmm = self.instruct("book Casa Gate {day} at {hhmm} for 2")
        self.assertNotEqual(out["status"], "awaiting_yes")                                        # never a yes card
        (m,) = [b for o, b, _a in self.agapi.calls if o == "approvals.mandate"]                  # CR 196 · the instruction, recorded
        self.assertEqual(m["scope"]["booking"], {"prepared_id": PREP, "party": 2, "date": day, "time": hhmm})   # the person's own terms
        (sub,) = [b for o, b, _a in self.agapi.calls if o == "venue.submit_booking"]              # ONE submit — no read-back, no tap
        self.assertEqual(sub["mandate_id"], MDT)
        self.assertNotIn("approvals.in_app_tap", self.agapi.ops())
        d = date.fromisoformat(day)
        # AgAPI's prepared venue (the fake's "Casa Gate"; CR 194: its identity) — the line is Tyler's, word for word
        self.assertEqual(out["line"], f"Booking now: Casa Gate, 2 people, {d:%a} {d.day:02d} {d:%b} at {hhmm}. "
                                      "Requested — I'll tell you when they reply.")
        self.assertNotIn(ACCT, VN._HELD)                                                          # nothing waits for a yes

    def test_a_guessed_party_never_reaches_scope_booking(self):
        out, day, hhmm = self.instruct("book Casa Gate {day} at {hhmm}", party=2)                # the model filled 2 in; they never said it
        self.assertEqual(out["ask"], "For how many people?")
        (m,) = [b for o, b, _a in self.agapi.calls if o == "approvals.mandate"]
        self.assertNotIn("party", m["scope"]["booking"])

    def test_a_term_agapi_says_they_didnt_give_is_asked_only_it(self):
        real = self.agapi.__call__

        async def missing(op, body, approval=None, account=None):
            if op == "approvals.mandate":
                self.agapi.calls.append((op, body, approval))
                return {"ok": False, "error": {"code": "invalid_input", "message": "asked, never guessed",
                                               "details": {"path": "/scope/booking", "rule": "term_not_given", "missing": ["time"]}}}
            return await real(op, body, approval, account)
        with mock.patch.object(VS, "CALL", missing):
            out, _d, _h = self.instruct("book Casa Gate {day} at {hhmm} for 2")
        self.assertEqual((out["status"], out["ask"]), ("need_term", "What time?"))                # exactly AgAPI's missing term
        self.assertNotIn("venue.submit_booking", self.agapi.ops())

    def test_outside_the_instruction_is_its_read_back_with_its_own_yes(self):
        real = self.agapi.__call__

        async def outside(op, body, approval=None, account=None):
            if op == "venue.submit_booking" and body.get("mandate_id"):
                self.agapi.calls.append((op, body, approval))
                return {"ok": False, "error": {"code": "approval_required", "message": "outside", "details": {
                    "read_back_id": "rb_x", "read_back": {"lines": ["Casa Gate, 2 people, at 21:30."]},
                    "mandate": {"mandate_id": body["mandate_id"], "outside": [{"why": "another_time"}]}}}}
            return await real(op, body, approval, account)
        with mock.patch.object(VS, "CALL", outside):
            out, _d, _h = self.instruct("book Casa Gate {day} at {hhmm} for 2")
        self.assertEqual((out["status"], out["read_back_id"]), ("awaiting_yes", "rb_x"))              # AgAPI's read-back, its own yes
        self.assertIn("a different day or time", out["ask"])                                      # the reason said
        self.assertEqual(V.read_back_line("hold_venue", {"ok": True, "result": out}), out["ask"])   # said by code
        self.assertNotIn("mandate_id", VN._HELD[ACCT])                                            # their yes, not the instruction

    def test_confirmed_says_booked_with_its_reference(self):
        self.agapi.submit.update(status="confirmed", reference="TB-4471")
        out, day, hhmm = self.instruct("book Casa Gate {day} at {hhmm} for 2")
        self.assertIn(". Booked — reference TB-4471.", out["line"])                         # then Sasha 279's closing, as before


class TheProof(unittest.TestCase):
    """CR 196 · the booking's instruction as approvals.mandate: THE ONE signer (agapi_mandate.sign, CR 187's form) over AgAPI's own
    mandate_sha256 of {end_user, words (as AgAPI keeps them), scope.booking, limits {} (a booking has none), minutes}."""

    def test_the_mandate_is_the_turns_and_carries_no_limits(self):
        from booking_signer import agapi_mandate as AM
        calls = []

        async def call(op, body, approval=None, account=None):
            calls.append((op, body))
            return {"ok": True, "result": {"mandate_id": "mdt_1", "expires_at": "2099-01-01T00:00:00Z", "proof": {"kind": "in_app"}}}
        ctx = API.Ctx(account="acct_1", user_said="book  Casa Gate\n for 4", session="conv_1", surface="s2", via="page")
        with mock.patch.dict(os.environ, {"SASHA_AGAPI_TAP_SECRET": "s381-secret"}), mock.patch.object(VS, "CALL", call):
            got = run(AM.for_booking(ctx, "eu_1", ctx.user_said, {"prepared_id": "vpr_" + "a" * 32, "party": 4, "date": "2026-11-20",
                                                                   "time": "21:00"}))
        self.assertEqual(got, {"mandate_id": "mdt_1"})
        (op, body), = calls
        scope = {"booking": {"prepared_id": "vpr_" + "a" * 32, "party": 4, "date": "2026-11-20", "time": "21:00"}}
        self.assertEqual((op, body["words"], body["scope"], body["expires_in_minutes"]), ("approvals.mandate", "book Casa Gate for 4", scope,
                                                                                           AM.BOOKING_MIN))
        self.assertNotIn("limits", body)
        pr = body["proof"]
        self.assertEqual((pr["kind"], pr["instruction_id"], pr["session_id"]), ("in_app", ctx.turn, "conv_1"))   # THIS turn's own id
        sha = AM.mandate_sha256("eu_1", "book Casa Gate for 4", scope, {}, AM.BOOKING_MIN)
        want = hmac.new(b"s381-secret", f"{pr['t']}.{pr['nonce']}.mandate.in_app.{ctx.turn}.acct_1.{sha}".encode(), hashlib.sha256).hexdigest()
        self.assertEqual(pr["signature"], want)

    def test_no_proof_nothing_recorded(self):
        from booking_signer import agapi_mandate as AM
        ctx = API.Ctx(account="acct_1", user_said="book it", surface="wa", via="wa")   # WhatsApp with no signed message on this turn
        got = run(AM.for_booking(ctx, "eu_1", "book it", {"prepared_id": "vpr_" + "a" * 32, "party": 2, "date": "2026-11-20", "time": "21:00"}))
        self.assertEqual(got["code"], "no_proof")


class TheCardsName(unittest.TestCase):
    def test_agapis_identity_never_a_page_heading(self):
        site = {"name": {"value": "Restaurante Mediterraneo en Madrid"}, "identity": {"name": "La Taberna de Peñalver", "source": "place"}}
        self.assertEqual(VT.shape({"name": "La Taberna de Peñalver", "place_id": "p1"}, site)["name"], "La Taberna de Peñalver")
        self.assertEqual(VT.shape({"name": "La Taberna de Peñalver", "place_id": "p1"}, {"name": {"value": "Restaurante Mediterraneo"}})["name"],
                         "La Taberna de Peñalver")                                                  # a page's reading never names it


class TheRatchet(unittest.TestCase):
    def test_the_party_is_never_required_by_the_tool(self):
        """Found by the sandbox proof (13 Nov): hold_venue's schema REQUIRED party — a missing one was refused before she could ask,
        and a model told "missing: party" fills one in: the guess Tyler's 20:20 decision forbids. Never required, on any surface."""
        t = API.BY_NAME["hold_venue"]
        self.assertNotIn("party", t["input_schema"]["required"])
        self.assertNotIn("party", VN.with_under(t)["input_schema"]["required"])
        self.assertIn("never guessed", t["input_schema"]["properties"]["party"]["description"])

    def test_no_yes_card_for_a_venue_act_and_no_default_party(self):
        src = (BACKEND / "agapi/venues.py").read_text()
        for gone in ("kanoe_card", "_kanoe_now", "BR_ask_call", "OK_CHOICES", "KANOE_CHOICES", "kanoe_ask", "wa_done_line", "booking_now"):
            self.assertNotIn(gone + "(", src.replace("def " + gone, ""), gone)
            self.assertFalse(hasattr(V, gone) or hasattr(VN, gone), gone)
        self.assertIsNone(re.search(r"""a\.get\(["']party["']\)\s*or\s*[1-9]""", src))
        for rung in ('"agapi"', '"agapi_call"'):                                                 # an act is never held for a yes
            self.assertNotIn(f"_hold(ctx, {rung}", src)
        for f in (VN._agapi_send, VN._agapi_call):   # CR 196 · the instructed submit; the person's own yes ONLY for a read-back outside it
            src = inspect.getsource(f)
            self.assertIn('VS.submit_instructed(ctx.account, held, how.get("said") or "") if held.get("mandate_id") else', src)
        self.assertNotIn("VS.read_back(", inspect.getsource(VN._act) + inspect.getsource(VN.platform_answer))
        for gone in ("instruction_tap", "instruction_session"):   # the tap kind CR 196 never built
            self.assertFalse(hasattr(VS, gone), gone)


if __name__ == "__main__":
    unittest.main()
