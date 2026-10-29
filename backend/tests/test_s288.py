"""Sasha 288 · T68 — EMAIL VENUES GET THE SAME RULE AS WHATSAPP: SHE SENDS IT, ONE LINE (Tyler 25 Oct 06:34: "cut down on the user
involvement"; CR 119b's run: 6 of 32 venues book by email).

ROOT TEST (written before the code, scratchpad s288/root-test.md):
  (1) ONE send path for a venue: venue.submit_booking (CR 121: messages.send_whatsapp refuses a venue's number). S2 calls it in ONE place,
      agapi/venue_submit.submit() (in the app: approvals.in_app_tap, which runs venue.submit_booking), from venues._agapi_send. Email goes
      through the SAME call: the booking rules' request_email → _execute → _via_agapi (venue.prepare_booking → the read-back) → the yes →
      _agapi_send → VS.submit. AgAPI sends it (venue_submit._send_message, how "email", Reply-To reply+<act_id>@…).
  (2) An email-only branch in S2, its own consent copy, or a second sender = PATCH: the 287 card (kanoe_card / _kanoe_now / _kanoe_sent)
      is THE card for every message request (venues.MESSAGE_ACTIONS), its lines the same voice lines; the booking row's one line serves
      every message channel (venue_submit.MESSAGE_CHANNELS).
  (3) Can S2 send an email request with a detail the person neither said nor confirmed? 287's ratchet, extended: unasked only when
      said.which() reads all four in THIS turn's words; otherwise ONE line asks and only their yes sends it.
Offline: a fake AgAPI only — nothing reaches AgAPI, an inbox or a phone.
    cd backend && python -m unittest tests.test_s288 -v
"""
from __future__ import annotations

import ast
import inspect
import pathlib
import re
import unittest
from unittest import mock

from agapi import s2_status as SS, venue_submit as VS, venue_truth as VT, venues as VN
from app.agent import voice as V
from tests import test_s287 as T

BACKEND = pathlib.Path(__file__).resolve().parents[1]
ACCT, PID, CARD, RES = T.ACCT, T.PID, T.CARD, T.RES
TO = "reservas@casagate.example"
LINES = [f"Sasha writes to Casa Gate by email from Kanoe's address, asking for: a table for 2 on 30/10/2099 at 21:00 (Alex Gate)",
         "It's a request: you'll be told when they answer."]
EMAIL_DEC = {"route": "message", "channel": "email", "how_far": "request", "sender": "kanoe",
             "say_text": "Casa Gate: I can send it for you and tell you when they answer.",
             "button": {"label": "Send the request", "link": None, "sends": True}}
#: the booking rules' answer for an email venue (booking_rules R4 · request_email), as rules_for returns it
RULES = {"action": "request_email", "say": "request_email", "say_text": "I'll ask them for you and tell you when they reply.",
         "takeover": {"say": "Or take it over yourself.", "link": "https://casagate.example/"}, "channels": [{"kind": "email", "value": TO}],
         "refusals": [], "ctx": {}, "follow_ups": []}


class FakeAgAPI(T.FakeAgAPI):
    """AgAPI's email half: the read-back, the single-use yes, ONE send (how "email" — its reference the message id)."""

    async def __call__(self, op, body, approval=None, account=None):
        if op == "venue.prepare_booking":
            self.ops.append(op)
            return {"ok": True, "result": {"prepared_id": PID, "submitted": False, "link": "https://agapi.test/prepared/x", "decision": EMAIL_DEC}}
        if op == "venue.submit_booking" and self.gate_at_read:
            self.ops.append(op)
            return {"ok": False, "error": {"code": "approval_required", "message": "read it back first",
                                           "details": {"read_back_id": "rbk_288", "read_back_sha256": "f" * 64, "read_back": {"lines": LINES}}}}
        if op == "approvals.in_app_tap" and body.get("read_back_id") not in self.used and body.get("read_back_sha256") == "f" * 64 and self.gate_at_send:
            self.ops.append(op)
            self.used.add(body["read_back_id"])
            self.sends.append(body["read_back_id"])
            return {"ok": True, "result": {"approval_id": "apv_288", "result": {
                "status": "sent", "act_id": "act_288", "venue": "Casa Gate", "how": "email", "reference": "em_288",
                "say": "I've emailed Casa Gate. I'll tell you when they reply."}}}
        if op == "approvals.in_app_tap" and body.get("read_back_id") not in self.used and not self.gate_at_send:
            self.ops.append(op)
            self.used.add(body["read_back_id"])
            return {"ok": True, "result": {"approval_id": "apv_288", "result": {"status": "not_allowed", "submitted": False, "venue": "Casa Gate",
                                                                                "say": "I can't send this one for you."}}}
        return await super().__call__(op, body, approval, account)

    status = {"act_id": "act_288", "state": "sent", "venue_words": {"untrusted_text": ""}, "say": "No answer from Casa Gate yet."}


class Base(T.Base):
    def setUp(self):
        super().setUp()
        self.agapi = FakeAgAPI(self.gate, self.gate_at_read, self.gate_at_send)
        for p in (mock.patch.object(VS, "CALL", self.agapi), mock.patch.object(VT, "decision", lambda p: EMAIL_DEC)):
            p.start()
            self.p.append(p)

    def tearDown(self):
        for p in reversed(self.p):   # these patch over 287's: stopped last-first, so nothing of either leaks into the next test
            p.stop()

    def _hold(self, words):
        with mock.patch("agapi.test_venues.vet", mock.AsyncMock(side_effect=lambda c, a: a)), \
                mock.patch.object(VN, "_read", mock.AsyncMock(return_value=dict(T.RD, rungs={"email": {"value": TO}}))), \
                mock.patch.object(VN, "_reservation", mock.AsyncMock(return_value=RES)), \
                mock.patch.object(VN, "engine_channel", mock.AsyncMock(return_value=None)), \
                mock.patch.object(VN, "rules_for", mock.AsyncMock(return_value=dict(RULES))), \
                mock.patch.object(VN, "_email", mock.AsyncMock(side_effect=AssertionError("never S2's own email sender"))):
            out = T.run(VN.hold_venue(T.ctx(words), {"name": "Casa Gate", "place_id": "ChIJ287", "day": RES["when"]["at"][:10],
                                                     "time": "21:00", "party": 2}))
        if ACCT in VN._HELD:
            VN._HELD[ACCT]["at"] -= T.timedelta(minutes=1)
        return out

    def tap(self, rid="rbk_288", choice="send"):
        return super().tap(rid, choice)


DONE = "Done — I've asked Casa Gate for Friday at 21:00 for 2. I'll tell you when they reply."


class FullRequestSendsNoQuestion(Base):
    """Offline 1 · their words give venue, day, time and people → the email is sent, no question, ONE line (never "I've emailed")."""

    def test_their_words_are_the_yes(self):
        out = self.hold(T.FULL)
        self.assertEqual((out["status"], out["line"]), ("requested", DONE))
        self.assertEqual(self.agapi.sends, ["rbk_288"])
        self.assertNotIn("ask", out)
        act = next(a for a in self.mem.kinds["venue_acts"] if a["act_id"] == "act_288")
        self.assertEqual((act["channel"], act["reference"]), ("email", "em_288"))
        self.assertEqual(act["consent"], {"kind": "their_words", "said": T.FULL})
        self.assertNotIn("email", out["line"].lower())


class OneDetailInferredAsksOnce(Base):
    """Offline 2 · one detail S2 filled in → ONE line, no message text → sent on the tap or a spoken yes."""

    def test_asks_once(self):
        out = self.hold("Book Casa Gate on Friday at 9pm")
        self.assertEqual((out["status"], out["ask"], out["read_back"]), ("awaiting_yes", "Casa Gate, Friday 21:00 for 2. Send?", []))
        self.assertEqual((out["filled_in"], out["message_if_asked"]), (["people"], LINES))
        self.assertEqual(self.agapi.sends, [])

    def test_the_tap_sends(self):
        self.hold("Book Casa Gate on Friday at 9pm")
        evs = self.tap()
        self.assertEqual(self.agapi.sends, ["rbk_288"], evs)
        self.assertEqual(T._said(evs), DONE)
        act = next(a for a in self.mem.kinds["venue_acts"] if a["act_id"] == "act_288")
        self.assertEqual((act["channel"], act["consent"]["kind"]), ("email", "in_app_tap"))

    def test_the_spoken_yes_sends(self):
        self.hold("Book Casa Gate for 2 on Friday")
        tok = VS.TAP.set({"kind": "supabase", "token": "their-session"})
        try:
            out = T.run(VN.book_venue(T.ctx("yes, send it"), {"name": "Casa Gate", "approval": {"said": "yes, send it"}}))
        finally:
            VS.TAP.reset(tok)
        self.assertEqual((out["status"], out["line"], self.agapi.sends), ("requested", DONE, ["rbk_288"]))


class NoYesNoSend(Base):
    """Offline 3 · no yes → nothing."""

    def test_no_yes_no_send(self):
        self.hold("Book Casa Gate on Friday")
        from agapi import v0 as API
        with self.assertRaises(API.ToolError):
            T.run(VN.book_venue(T.ctx("hmm, maybe later"), {"name": "Casa Gate", "approval": {"said": "hmm, maybe later"}}))
        self.assertEqual(T._said(self.tap(rid="rbk_other")), V.NOTHING_WAITING)
        self.assertEqual(self.agapi.sends, [])
        self.assertNotIn("approvals.in_app_tap", self.agapi.ops)


class RetryNoSecondSend(Base):
    """Offline 4 · the same request again, a double tap → never a second email."""

    def test_the_same_request_again(self):
        self.hold(T.FULL)
        out = self.hold(T.FULL)
        self.assertEqual((self.agapi.sends, out["status"]), (["rbk_288"], "already_sent"))

    def test_a_double_tap(self):
        self.hold("Book Casa Gate on Friday at 9pm")
        self.tap()
        self.tap()
        self.assertEqual(self.agapi.sends, ["rbk_288"])


class NotAllowedAtTheSendIsAHandOver(Base):
    gate, gate_at_read, gate_at_send = True, True, False

    def test_never_cant(self):
        out = self.hold(T.FULL)
        self.assertEqual(self.agapi.sends, [])
        self.assertEqual(out["status"], "page_link")
        self.assertTrue(out["line"])
        self.assertNotIn("can't", (out["line"] + out["say"]).lower())


class AnAmbiguousReplyIsNeverConfirmed(Base):
    """Offline 5 · the venue's emailed reply comes back to the booking in one line; one that isn't clearly yes or no is never "confirmed"
    — even when AgAPI's reading says so (its YES takes a leading "ok": CR 122 (a)). She says what they wrote."""

    def _row(self, status):
        with mock.patch.object(FakeAgAPI, "status", status):
            for a in VS._ACTS.get(ACCT) or []:
                a.update({"answered": None, "words": None, "state": "sent"})
            return T.run(VS.bookings(ACCT))[0]

    def test_replies(self):
        self.hold(T.FULL)
        row = self._row({"act_id": "act_288", "state": "sent", "venue_words": {"untrusted_text": ""}})
        self.assertRegex(row["wa"], r"^Asked at \d\d:\d\d · waiting for Casa Gate\.$")
        for words in ("ok, we'll check", "OK, we will get back to you", "Vale, lo miramos y te decimos", "ok, what time?", "To be confirmed"):
            row = self._row({"act_id": "act_288", "state": "confirmed", "venue_words": {"untrusted_text": words}})   # AgAPI says confirmed
            self.assertEqual(row["status"], "requested", words)
            self.assertEqual(row["wa"], f"Casa Gate replied: “{words}”")
            line = SS.decide({"venues": [row], "booked": [], "failed": []})["line"]
            self.assertTrue(line.startswith("Requested — not confirmed yet"), line)
            self.assertNotRegex(line.replace(words, "").lower(), r"\b(booked|said yes)\b|(?<!not )confirmed", line)   # her words, not theirs
            self.assertIn(words, line)
        for words in ("Yes, confirmed for 21:00", "Sí, perfecto, os esperamos", "Confirmed! Any allergies?"):
            row = self._row({"act_id": "act_288", "state": "confirmed", "venue_words": {"untrusted_text": words}})
            self.assertEqual(row["status"], "confirmed", words)
            self.assertRegex(row["wa"], r"^Casa Gate said yes — .+ 21:00 for 2\.$")
        row = self._row({"act_id": "act_288", "state": "replied", "venue_words": {"untrusted_text": "We'll check and come back"}})
        self.assertEqual((row["status"], row["wa"]), ("requested", "Casa Gate replied: “We'll check and come back”"))
        row = self._row({"act_id": "act_288", "state": "declined", "venue_words": {"untrusted_text": "Sorry, fully booked"}})
        self.assertEqual(row["wa"], "Casa Gate said no.")


class TheRatchet(unittest.TestCase):
    """ROOT TEST (1)–(3), in the code."""

    def test_one_card_for_every_message_request(self):
        self.assertEqual(VN.MESSAGE_ACTIONS, ("request_whatsapp", "request_email"))
        self.assertEqual(VS.MESSAGE_CHANNELS, ("whatsapp", "email"))
        va = inspect.getsource(VN._via_agapi)
        self.assertIn('d["action"] in MESSAGE_ACTIONS', va)
        self.assertEqual(va.count("kanoe_card("), 1)

    def test_no_email_branch_no_second_sender(self):
        for fn in (VN.kanoe_card, VN._kanoe_now, VN._kanoe_sent, VN._agapi_send, VN._via_agapi):
            code = inspect.getsource(fn).replace(fn.__doc__ or "", "")
            code = "\n".join(re.sub(r"#.*$", "", x) for x in code.splitlines())
            self.assertNotRegex(code, r"""(?:==|!=|\bin)\s*\(?["']email["']""", fn.__name__)   # no `if channel == "email"` copy
            for bad in ("/api/booking/emails", "_email(", "send_email", "resend", "messages.send"):
                self.assertNotIn(bad, code, (fn.__name__, bad))
        self.assertIn("VS.submit(", inspect.getsource(VN._agapi_send))   # the ONE send: venue.submit_booking

    def test_the_send_unasked_needs_all_four(self):
        src = inspect.getsource(VN.kanoe_card)
        self.assertLess(src.index("if all(got.values()):"), src.index("_kanoe_now("))
        self.assertEqual(src.count("_kanoe_now("), 1)

    def test_her_voice_never_names_the_channel(self):
        lines = [V.kanoe_ask("X", "Friday", "21:00", 2), V.wa_done_line("X", "Friday", "21:00", 2), V.wa_sent_line("21:00", "X"),
                 V.wa_replied_line("X", "ok, we'll check")]
        self.assertEqual(V.check(lines), [])
        for x in lines:
            self.assertNotRegex(x.lower(), r"e-?mail")


class FakeStoresHaveTheRealShape(unittest.TestCase):
    """The gate's log line "[guest_whatsapp] the brain's result is not watched: '_Store' object has no attribute 'get_state'": the venue
    suite's fake STORE (scripts/venue_suite.py) had channel_of_account but not get_state, so watch_for_brain threw on IT. The real stores
    (MemoryGuestStore, PostgresGuestStore) both have get_state — a real guest's result was never lost to it. Every fake GW.STORE is now
    the memory store itself, so a fake can never lack a method the real one has."""

    def test_every_fake_guest_store_is_the_memory_store(self):
        from booking_signer import guest_whatsapp as GW
        for cls in (GW.MemoryGuestStore, GW.PostgresGuestStore):
            self.assertTrue(inspect.iscoroutinefunction(cls.get_state), cls)
        bad = []
        for f in list((BACKEND / "scripts").rglob("*.py")) + list((BACKEND / "tests").rglob("*.py")):
            src = f.read_text(encoding="utf-8")
            if '"STORE"' not in src and "GW.STORE =" not in src and "GW.STORE," not in src:
                continue
            for n in ast.walk(ast.parse(src)):
                if isinstance(n, ast.ClassDef) and n.name == "_Store" and any(
                        isinstance(b, ast.AsyncFunctionDef) and b.name == "channel_of_account" for b in n.body) and not n.bases:
                    bad.append(f"{f.relative_to(BACKEND)}:{n.lineno}")
        self.assertEqual(bad, [])

    def test_the_watch_works_on_the_suites_store(self):
        from booking_signer import guest_whatsapp as GW

        class _Store(GW.MemoryGuestStore):
            async def channel_of_account(self, acct):
                return {"wa_id_sha256": "x" * 64}
        spawned = []
        with mock.patch.object(GW, "STORE", _Store()), mock.patch.object(GW, "guest_numbers", lambda: {"+15550000000"}), \
                mock.patch.object(GW, "_spawn", lambda c: (spawned.append(c), c.close())):
            got = T.run(GW.watch_for_brain(ACCT, call_id="call_288", venue="Casa Gate"))
        self.assertEqual((got, len(spawned)), ("watching", 1))


if __name__ == "__main__":
    unittest.main()
