"""Sasha 287 · T67 — SASHA SENDS THE VENUE'S WHATSAPP HERSELF, FROM KANOE'S NUMBER (beta: Tyler's and Jon's accounts, person_access
kanoe_whatsapp = beta). MINIMUM INVOLVEMENT (Tyler, 25 Oct 06:34: "cut down on the user involvement" — no message read-back).

ROOT TEST (written before the code):
  (1) ONE truth for "may this message leave Kanoe's number": AgAPI's gate — venue_messages.kanoe_send_allowed (agapi_service/
      venue_messages.py), checked by AgAPI at venue.prepare_booking (decision.sender "kanoe" | "person"), at venue.submit_booking's
      read-back (not_allowed) and at the send (_send_whatsapp → send_kanoe) — plus the consent S2 records: approvals.in_app_tap on THAT
      read-back (AgAPI's record_yes before the send, take_yes uses it up) and, on S2's booking record (venue_acts), what the consent was:
      their own words, or their tap / spoken yes. S2 reads the gate's answer in ONE place: agapi/venues.py kanoe_whatsapp().
  (2) S2 deciding for itself whether Kanoe may send — its own flag or env switch, an allow-list of emails or accounts, its own booking
      rules choosing request_whatsapp over AgAPI's answer, or a second send path beside 285's (s2_whatsapp._twilio, a send of its own) = PATCH.
  (3) Can S2 ever send a detail (venue, day, time, people) the person neither said nor confirmed? The ratchet: it sends without asking ONLY
      when agapi/said.which() reads all four in THIS turn's words, each matching the booking exactly (conservative: unread = not said);
      any one S2 filled in → ONE line names all four and asks, and only their yes sends it. Consent is single-use (AgAPI's approval; a
      durable claim on their words), so a retry never sends again.
Offline: a fake AgAPI only — nothing reaches AgAPI, Twilio or a phone.
    cd backend && python -m unittest tests.test_s287 -v
"""
from __future__ import annotations

import ast
import asyncio
import inspect
import pathlib
import re
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

from agapi import agapi_route as AR, s2_memory as M, venue_submit as VS, venue_truth as VT, venues as VN
from app.agent import sasha as S, voice as V

run = asyncio.run
BACKEND = pathlib.Path(__file__).resolve().parents[1]
ACCT = "00000000-0000-4000-8000-000000000287"
PID = "vpr_" + "a" * 32
WA = "https://wa.me/34611222333?text=Hola%2C%20quer%C3%ADa%20reservar"
T1 = "Hola, escribo de parte de Alex Gate vía Sasha (Kanoe): ¿tienen disponibilidad para 2 personas el 01/11/2099 a las 21:00? Gracias."
LINES = [f"Sasha writes to Casa Gate by WhatsApp from Kanoe's number, asking for: {T1}", "It's a request: you'll be told when they answer."]
CARD = {"name": "Casa Gate", "place_id": "ChIJ287", "ref": "casa", "website": "https://casagate.example/"}
RD = {"venue": "Casa Gate", "place_id": "ChIJ287", "read_id": "r287", "rungs": {}, "country": "ES", "facts": []}
RES = {"who": {"name": "Alex Gate", "contact": {"mobile_e164": "+447700900287"}}, "how_many": {"count": 2},
       "when": {"at": "2099-10-30T21:00", "mode": "slot"}, "what": {"category": "restaurant"}}
PROFILE_DEC = {"route": "message", "channel": "WhatsApp", "how_far": "request", "sender": "person",
               "say_text": "Casa Gate takes bookings by WhatsApp: I've written it for you: tap “Send on WhatsApp” and it goes from your phone; "
                           "they'll reply to you.", "button": {"label": "Send on WhatsApp", "link": WA, "sends": False}}


class FakeAgAPI:
    """AgAPI's half, as its code does it: the gate at prepare, the read-back, the gate again at submit, the single-use yes, ONE send."""

    def __init__(self, gate=True, gate_at_read=None, gate_at_send=None):
        self.gate, self.ops, self.sends, self.used = gate, [], [], set()
        self.gate_at_read = gate if gate_at_read is None else gate_at_read
        self.gate_at_send = self.gate_at_read if gate_at_send is None else gate_at_send

    async def __call__(self, op, body, approval=None, account=None):
        self.ops.append(op)
        if op == "users.register":
            return {"ok": True, "result": {"end_user_id": "eu_287"}}
        if op == "venue.prepare_booking":
            k = self.gate
            dec = {**PROFILE_DEC, "sender": "kanoe" if k else "person",
                   "say_text": "Casa Gate takes bookings by WhatsApp: I can send it for you and tell you when they answer." if k else PROFILE_DEC["say_text"],
                   "button": {"label": "Send the request" if k else "Send on WhatsApp", "link": WA, "sends": k},
                   "options": [{"kind": "whatsapp", "label": "Send on WhatsApp", "link": WA, "sends": k}]}
            return {"ok": True, "result": {"prepared_id": PID, "submitted": False, "link": "https://agapi.test/prepared/x", "decision": dec,
                                           "person_send": {"whatsapp": WA, "kanoe_sends": k}}}
        if op == "venue.submit_booking":
            if not self.gate_at_read:
                return {"ok": True, "result": {"status": "not_allowed", "submitted": False,
                                               "say": "I can't send this one for you (sending from Kanoe's number isn't on for this person)."}}
            return {"ok": False, "error": {"code": "approval_required", "message": "read it back first",
                                           "details": {"read_back_id": "rbk_287", "read_back_sha256": "f" * 64, "read_back": {"lines": LINES}}}}
        if op == "approvals.in_app_tap":
            if body["read_back_sha256"] != "f" * 64:
                return {"ok": False, "error": {"code": "approval_void", "message": "not that card"}}
            if body["read_back_id"] in self.used:   # AgAPI: _check_and_consume — the yes is single-use
                return {"ok": False, "error": {"code": "approval_consumed", "message": "that yes was already used"}}
            self.used.add(body["read_back_id"])
            if not self.gate_at_send:   # _send_whatsapp: the gate again — nothing sent, said
                return {"ok": True, "result": {"approval_id": "apv_287", "result": {
                    "status": "failed", "act_id": "act_287f", "venue": "Casa Gate", "how": "whatsapp",
                    "say": "Not booked — Casa Gate's form answered: \"sending from Kanoe's number isn't on for this person — nothing was sent.\""}}}
            self.sends.append(body["read_back_id"])
            return {"ok": True, "result": {"approval_id": "apv_287", "result": {
                "status": "sent", "act_id": "act_287", "venue": "Casa Gate", "how": "whatsapp_template", "reference": "SM" + "2" * 32,
                "say": "Sent to Casa Gate. I'll tell you when they reply."}}}
        if op == "approvals.request":
            return {"ok": True, "result": {}}
        if op == "venue.booking_status":
            return {"ok": True, "result": self.status}
        raise AssertionError(f"unexpected op {op}")

    status = {"act_id": "act_287", "state": "sent", "venue_words": {"untrusted_text": ""}, "say": "No answer from Casa Gate yet."}


class Memory:
    def __init__(self):
        self.kinds = {}

    async def kind(self, _a, name):
        return self.kinds.get(name)

    async def put_kind(self, _a, name, value):
        self.kinds[name] = [dict(r) for r in value]
        return True


def ctx(said="", surface="s2"):
    from agapi import v0 as API
    c = API.Ctx(account=ACCT, surface=surface, user_said=said, mode="test")
    c.started = datetime.now(timezone.utc)
    return c


FULL_DEFAULT = "Book Casa Gate for 2 on Friday at 9pm"


class Base(unittest.TestCase):
    gate = True
    gate_at_read = None
    gate_at_send = None

    def setUp(self):
        VN._HELD.pop(ACCT, None)
        VN._SENT.pop(ACCT, None)
        VN._PREPARED.pop(ACCT, None)
        VS._ACTS.pop(ACCT, None)
        VS._USERS.clear()
        from agapi import v0 as API
        API._CLAIMED.clear()
        self.agapi = FakeAgAPI(self.gate, self.gate_at_read, self.gate_at_send)
        self.mem = Memory()
        from agapi import s2_outcomes as OC
        from booking_signer import basket as BK, guest_receipt as GR, wa_brain as WB
        self.p = [mock.patch.object(BK, "_run", lambda: None),   # the claim in-process (no database here): once per tap, as in Postgres
                  mock.patch.object(VS, "CALL", self.agapi), mock.patch.object(M, "kind", self.mem.kind),
                  mock.patch.object(M, "put_kind", self.mem.put_kind), mock.patch.object(OC, "booked", mock.AsyncMock()),
                  mock.patch.object(GR, "address_of", mock.AsyncMock(return_value="alex.gate@example.com")),
                  mock.patch.object(WB, "trip_day_words", mock.AsyncMock(return_value="")),
                  mock.patch.object(VS, "target", mock.AsyncMock(return_value="live")),
                  mock.patch.object(VT, "decision", lambda p: PROFILE_DEC),
                  mock.patch.object(VN, "_today", lambda country: __import__("datetime").date(2099, 10, 27))]   # a Tuesday: Friday is this week
        for p in self.p:
            p.start()
        VN.remember_cards(ACCT, [CARD])

    def tearDown(self):
        for p in self.p:
            p.stop()

    def hold(self, words=FULL_DEFAULT):
        tok = VS.TAP.set({"kind": "supabase", "token": "their-session"})   # an in-app turn (/s2): its own session, for the whole turn
        try:
            return self._hold(words)
        finally:
            VS.TAP.reset(tok)

    def _hold(self, words):
        with mock.patch("agapi.test_venues.vet", mock.AsyncMock(side_effect=lambda c, a: a)), \
                mock.patch.object(VN, "_read", mock.AsyncMock(return_value=dict(RD))), \
                mock.patch.object(VN, "_reservation", mock.AsyncMock(return_value=RES)), \
                mock.patch.object(VN, "engine_channel", mock.AsyncMock(return_value=None)), \
                mock.patch.object(VN, "rules_for", mock.AsyncMock(side_effect=AssertionError("S2's own rules never decide a Kanoe send"))):
            out = run(VN.hold_venue(ctx(words), {"name": "Casa Gate", "place_id": "ChIJ287", "day": RES["when"]["at"][:10],
                                                 "time": "21:00", "party": 2}))
        if ACCT in VN._HELD:
            VN._HELD[ACCT]["at"] -= timedelta(minutes=1)   # the yes comes in a later turn
        return out

    def tap(self, rid="rbk_287", choice="send"):
        tok = VS.TAP.set({"kind": "supabase", "token": "their-session"})
        try:
            evs = run(_collect(S.card_tap(ACCT, "s287", "s2", {"read_back_id": rid, "choice": choice}, "Yes, send it")))
        finally:
            VS.TAP.reset(tok)
        return evs


async def _collect(agen):
    return [e async for e in agen]


def _said(evs):
    return next(e["delta"] for e in evs if e["type"] == "text")


FULL = "Book Casa Gate for 2 on Friday at 9pm"


class FullRequestSendsNoQuestion(Base):
    """Offline 1 · Sasha 309 MOVED (was: their words are the yes, sent with nothing shown): a full request is READ BACK first — the
    complete message on its card, one button — and ONE tap sends it."""

    def test_a_full_request_is_read_back_then_one_tap_sends(self):
        out = self.hold(FULL)
        self.assertEqual((out["status"], out["read_back"], out["ask"]), ("awaiting_yes", LINES, "Casa Gate, Friday 21:00 for 2. Shall I send?"))
        self.assertEqual(self.agapi.sends, [])
        evs = self.tap()
        self.assertEqual(self.agapi.sends, ["rbk_287"])
        self.assertEqual(_said(evs), "Done — I've asked Casa Gate for Friday at 21:00 for 2. I'll tell you when they reply.")
        act = next(a for a in self.mem.kinds["venue_acts"] if a["act_id"] == "act_287")
        self.assertEqual((act["channel"], act["reference"]), ("whatsapp", "SM" + "2" * 32))   # Twilio's message id, on the booking
        self.assertEqual(act["consent"]["kind"], "in_app_tap")                                 # the tap on the card they saw
        self.assertNotIn("approvals.request", self.agapi.ops)


class OneDetailInferredAsksOnce(Base):
    """Offline 2 · one detail S2 filled in (no party said: the default 2) → ONE line, no message text → sent on their yes."""

    def test_asks_once_with_the_message(self):   # Sasha 309 MOVED: the card IS the message as it goes (it was hidden)
        out = self.hold("Book Casa Gate on Friday at 9pm")
        self.assertEqual(out["status"], "awaiting_yes")
        self.assertEqual(out["ask"], "Casa Gate, Friday 21:00 for 2. Shall I send?")
        self.assertEqual(out["read_back"], LINES)
        self.assertEqual(out["filled_in"], ["people"])
        self.assertNotIn("message_if_asked", out)
        ev = S.render("hold_venue", out, {})
        self.assertEqual((ev["kind"], ev["read_back"], ev["ask"], ev["read_back_id"]), ("read_back", LINES, out["ask"], "rbk_287"))
        self.assertEqual(V.read_back_line("hold_venue", {"ok": True, "result": out}), out["ask"])
        self.assertEqual(self.agapi.sends, [])

    def test_the_tap_sends(self):
        self.hold("Book Casa Gate on Friday at 9pm")
        evs = self.tap()
        self.assertEqual(self.agapi.sends, ["rbk_287"], evs)
        self.assertEqual(_said(evs), "Done — I've asked Casa Gate for Friday at 21:00 for 2. I'll tell you when they reply.")
        act = next(a for a in self.mem.kinds["venue_acts"] if a["act_id"] == "act_287")
        self.assertEqual(act["consent"]["kind"], "in_app_tap")

    def test_the_spoken_yes_sends(self):
        self.hold("Book Casa Gate on Friday at 9pm")
        tok = VS.TAP.set({"kind": "supabase", "token": "their-session"})
        try:
            out = run(VN.book_venue(ctx("yes, send it"), {"name": "Casa Gate", "approval": {"said": "yes, send it"}}))
        finally:
            VS.TAP.reset(tok)
        self.assertEqual((out["status"], self.agapi.sends), ("requested", ["rbk_287"]))


class NoYesNoSend(Base):
    """Offline 3 · no yes → nothing sent."""

    def test_no_yes_no_send(self):
        self.hold("Book Casa Gate on Friday")
        self.assertEqual(self.agapi.sends, [])
        from agapi import v0 as API
        with self.assertRaises(API.ToolError):   # words that aren't a yes never send it
            run(VN.book_venue(ctx("hmm, maybe later"), {"name": "Casa Gate", "approval": {"said": "hmm, maybe later"}}))
        self.assertEqual(_said(self.tap(rid="rbk_other")), V.NOTHING_WAITING)   # a tap on a card that isn't the held one
        self.assertEqual(self.agapi.sends, [])
        self.assertNotIn("approvals.in_app_tap", self.agapi.ops)


class GateNoTheHandOver(Base):
    """Offline 4 · gate no → the same line is their own WhatsApp (285's hand-over), nothing sent, never "can't" — even for a full request."""
    gate = False

    def test_not_in_beta_is_their_own_whatsapp(self):
        out = self.hold(FULL)
        self.assertEqual((out["status"], out["page_url"]), ("page_link", WA))
        self.assertEqual(out["button"], {"label": "Send on WhatsApp", "link": WA})
        self.assertTrue(out["say"].startswith(V.OWN_WHATSAPP))
        self.assertNotIn("can't", out["say"].lower())
        self.assertNotIn("venue.submit_booking", self.agapi.ops)
        self.assertEqual(self.agapi.sends, [])
        self.assertEqual(S.render("hold_venue", out, {})["kind"], "handover")
        self.assertEqual(self.mem.kinds[VN.PREPARED_KIND][-1]["url"], WA)  # the way back (283)


class GateNoAtTheReadBack(Base):
    gate, gate_at_read = True, False

    def test_refused_at_the_read_back_is_the_same_hand_over(self):
        out = self.hold(FULL)
        self.assertEqual((out["status"], out["page_url"]), ("page_link", WA))
        self.assertEqual(out["say"], V.OWN_WHATSAPP + " Say exactly that — never that it's booked.")   # AgAPI's "I can't…" never said
        self.assertEqual(self.agapi.sends, [])


class GateNoAtTheSend(Base):
    gate, gate_at_read, gate_at_send = True, True, False

    def test_refused_at_the_send_is_the_same_hand_over(self):   # Sasha 309 MOVED: at the send = on his yes (no send unasked)
        self.hold(FULL)
        tok = VS.TAP.set({"kind": "supabase", "token": "their-session"})
        try:
            out = run(VN.book_venue(ctx("yes, send it"), {"name": "Casa Gate", "approval": {"said": "yes, send it"}}))
        finally:
            VS.TAP.reset(tok)
        self.assertEqual(self.agapi.sends, [])
        self.assertEqual((out["status"], out["page_url"], out["line"]), ("page_link", WA, V.OWN_WHATSAPP))


class RetryNoSecondSend(Base):
    """Offline 5 · consent is single-use: the same request again, a double tap, a retry at the send — never a second send."""

    def test_the_same_request_again(self):   # Sasha 309 MOVED: asked again after the tap → read back again, never sent again unasked
        self.hold(FULL)
        self.tap()
        out = self.hold(FULL)
        self.assertEqual(self.agapi.sends, ["rbk_287"])
        self.assertNotIn(out["status"], ("requested", "confirmed", "sent"))

    def test_a_double_tap(self):
        self.hold("Book Casa Gate on Friday at 9pm")
        self.tap()
        self.tap()
        self.assertEqual(self.agapi.sends, ["rbk_287"])
        held = {"rung": "agapi", "kanoe": True, "read_back_id": "rbk_287", "prepared_id": PID, "end_user": "eu_287", "sha": "f" * 64}
        tok = VS.TAP.set({"kind": "supabase", "token": "their-session"})
        try:
            r = run(VS.submit(ACCT, held, "yes"))                          # even straight at the send: AgAPI's yes is used up
        finally:
            VS.TAP.reset(tok)
        self.assertEqual(r["error"]["code"], "approval_consumed")
        self.assertEqual(self.agapi.sends, ["rbk_287"])


class RepliesComeBackToTheBooking(Base):
    def _row(self, status):
        with mock.patch.object(FakeAgAPI, "status", status):
            for a in VS._ACTS.get(ACCT) or []:
                a.update({"answered": None, "words": None, "state": "sent"})
            return run(VS.bookings(ACCT))[0]

    def test_one_line_for_each_answer_and_stop(self):
        self.hold(FULL)
        self.tap()   # Sasha 309 · sent on the one yes
        row = self._row({"act_id": "act_287", "state": "sent", "venue_words": {"untrusted_text": ""}})
        self.assertEqual(row["status"], "requested")
        self.assertRegex(row["wa"], r"^Asked at \d\d:\d\d · waiting for Casa Gate\.$")
        from agapi import s2_status as SS
        self.assertIn(row["wa"], SS.decide({"venues": [row], "booked": [], "failed": []})["line"])
        row = self._row({"act_id": "act_287", "state": "confirmed", "venue_words": {"untrusted_text": "Sí, confirmado"}})
        self.assertEqual((row["status"], row["venue_said"]["untrusted_text"]), ("confirmed", "Sí, confirmado"))
        self.assertRegex(row["wa"], r"^Casa Gate said yes — .+ 21:00 for 2\.$")
        row = self._row({"act_id": "act_287", "state": "proposed", "venue_words": {"untrusted_text": "Lo sentimos, ¿podéis a las 21:30?"}})
        self.assertEqual(row["wa"], "Casa Gate offered 21:30 — shall I take it?")
        row = self._row({"act_id": "act_287", "state": "declined", "venue_words": {"untrusted_text": "Completo"}})
        self.assertEqual(row["wa"], "Casa Gate said no.")
        row = self._row({"act_id": "act_287", "state": "sent", "opted_out": True, "venue_words": {"untrusted_text": "STOP"}})
        self.assertEqual((row["status"], row["wa"]), ("stopped", V.wa_stopped_line("Casa Gate")))

    def test_a_stop_is_handed_to_agapi_and_kept(self):
        async def call(op, body, approval=None, account=None):
            return {"ok": True, "result": {"matched": True, "kept": True, "opted_out": True, "booking": None}}
        with mock.patch.object(VS, "CALL", call):
            got = run(VS.whatsapp_inbound("+34611222333", "STOP"))
        self.assertEqual((got["matched"], got["opted_out"]), (True, True))


class TheirWords(unittest.TestCase):
    """THE RATCHET (3) · said.which: a detail counts only when THEIR words give it, matching the booking."""
    TODAY = __import__("datetime").date(2099, 10, 27)   # a Tuesday
    AT = "2099-10-30T21:00"                           # Friday 21:00

    def w(self, words, at=None, party=2, name="Casa Gate", today=None):
        from agapi import said as SD
        return SD.which(words, name, at or self.AT, party, today or self.TODAY)

    def test_the_full_request(self):
        for words in ("book Casa Gate for 2 on Friday at 9pm", "mesa para dos en Casa Gate el viernes a las 21:00",
                      "Casa Gate, Friday 30 Oct, 21:00, 2 people", "Book Lamucca for 4 Tuesday at 9"):
            lam = "Lamucca" in words   # Tyler's example: said on a Thursday, for the coming Tuesday
            got = self.w(words, at="2099-11-03T21:00" if lam else None, party=4 if lam else 2, name="Lamucca" if lam else "Casa Gate",
                         today=__import__("datetime").date(2099, 10, 29) if lam else None)
            self.assertTrue(all(got.values()), (words, got))

    def test_each_detail_s2_filled_in_is_not_said(self):
        self.assertFalse(self.w("book Casa Gate on Friday at 9pm")["people"])          # the default party
        self.assertFalse(self.w("book Casa Gate for 2 on Friday")["time"])             # a time she picked
        self.assertFalse(self.w("book Casa Gate for 2 at 9pm")["day"])                 # a day she worked out
        self.assertFalse(self.w("book it for 2 on Friday at 9pm")["venue"])            # a venue from earlier
        self.assertFalse(self.w("book Casa Gate for 3 on Friday at 9pm")["people"])    # their 3 is not the booking's 2
        self.assertFalse(self.w("book Casa Gate for 2 on Friday at 9:30pm")["time"])   # 21:30 is not 21:00
        self.assertFalse(self.w("book Casa Gate for 2 on Thursday at 9pm")["day"])
        self.assertFalse(self.w("book Casa Gate for 2 next week at 9pm")["day"])
        self.assertFalse(self.w("book Casa Gate for 2 on Friday at 9pm", at="2099-11-06T21:00")["day"])   # a Friday a week on: not this one
        self.assertFalse(self.w("book the restaurant for 2 on Friday at 9pm", name="The Restaurant")["venue"])   # only generic words

    def test_the_card_they_tapped_is_their_venue(self):
        self.assertTrue(self.w("This one: “Casa Gate” [their tap on the card on their screen: Casa Gate · place_id ChIJ287 — use this place_id]")["venue"])

    def test_s2_never_sends_unasked(self):   # Sasha 309 MOVED: the request is never the yes — the read-back comes first, always
        src = inspect.getsource(VN.kanoe_card)
        self.assertNotIn("if all(got.values()):", src)
        self.assertFalse(hasattr(VN, "_kanoe_now"))
        self.assertIn("str(getattr(ctx, \"user_said\", \"\") or \"\")", src)   # THIS turn's own words — never the model's arguments


class TheLane(unittest.TestCase):
    def test_a_background_run_says_so_on_every_agapi_call(self):
        seen = {}

        class R:
            status_code, headers = 200, {}

            def json(self):
                return {"ok": True, "result": {}}

        class Client:
            def __init__(self, *a, **k):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def post(self, url, headers=None, content=None):
                seen.update(headers or {})
                return R()
        with mock.patch("httpx.AsyncClient", Client):
            run(AR.post("https://agapi.test", "k", "venue.profile", {}, {"Authorization": "Bearer k"}, 5))
            self.assertNotIn("AgAPI-Lane", seen)
            with AR.lane("background"):
                run(AR.post("https://agapi.test", "k", "venue.profile", {}, {"Authorization": "Bearer k"}, 5))
        self.assertEqual(seen["AgAPI-Lane"], "background")


class TheRatchet(unittest.TestCase):
    """ROOT TEST (3)."""

    def test_s2_reads_the_gate_in_one_place(self):
        src = inspect.getsource(VN.kanoe_whatsapp).replace(VN.kanoe_whatsapp.__doc__, "")   # its code, not its docstring
        self.assertIn('get("sender") != "kanoe"', src)                  # AgAPI's answer at prepare
        self.assertIn("VS.read_back(", src)                              # and at the read-back
        for bad in ("getenv", "environ", "founder", "@", "allow", "rules_for", "BD.", "_twilio", "send_whatsapp"):
            self.assertNotIn(bad, src, bad)                              # no flag, no list, no rules of its own, no second sender

    def test_the_kanoe_card_comes_before_s2s_own_rules(self):
        src = inspect.getsource(VN.hold_venue)
        self.assertLess(src.index("kanoe_route(dec)"), src.index("follows(dec, at)"))
        self.assertLess(src.index("kanoe_route(dec)"), src.index("rules_for("))
        va = inspect.getsource(VN._via_agapi)   # S2's own read finding a WhatsApp (no AgAPI decision): AgAPI's send, the same question
        self.assertIn('d["action"] in MESSAGE_ACTIONS', va)   # Sasha 288 · every message request, WhatsApp among them
        self.assertIn("request_whatsapp", VN.MESSAGE_ACTIONS)
        self.assertIn("kanoe_card(", va)

    def test_the_send_is_only_the_held_read_back_once(self):
        ac = inspect.getsource(VN.answer_card)
        self.assertIn('held.get("kanoe")', ac)
        self.assertIn('held.get("read_back_id") != read_back_id', ac)
        self.assertIn("VS.submit(", inspect.getsource(VN._agapi_send))
        self.assertIn("in_app_tap(account, rid,", inspect.getsource(VS.submit))   # the tap on that read-back's sha256

    def test_no_kanoe_flag_allow_list_or_twilio_post_in_s2(self):
        bad = []
        for d in ("agapi", "app", "booking_signer", "products"):
            for f in (BACKEND / d).rglob("*.py"):
                rel = str(f.relative_to(BACKEND))
                tree = ast.parse(f.read_text(encoding="utf-8"))
                for n in ast.walk(tree):
                    if isinstance(n, ast.Constant) and isinstance(n.value, str) and re.fullmatch(r"(SASHA_|AGAPI_)?KANOE_WHATSAPP\w*", n.value):
                        bad.append(f"{rel}:{n.lineno}")
                    if isinstance(n, ast.Constant) and isinstance(n.value, str) and n.value == "messages.send_whatsapp":
                        bad.append(f"{rel}:{n.lineno} messages.send_whatsapp")
        self.assertEqual(bad, [])                                       # (Twilio's closed list: test_s285.NoSecondTwilioSender)

    def test_her_voice_names_no_channel(self):
        lines = [V.kanoe_ask("X", "Friday", "21:00", 2), V.wa_done_line("X", "Friday", "21:00", 2), V.OWN_WHATSAPP, V.wa_sent_line("21:00", "X"),
                 V.wa_yes_line("X", "Friday", "21:00", 2), V.wa_offered_line("X", "21:30"), V.wa_no_line("X"), V.wa_stopped_line("X"),
                 V.wa_replied_line("X", "ok")]
        self.assertEqual(V.check(lines), [])
        for x in lines:
            self.assertNotIn("can't", x.lower())
            self.assertFalse(V.asks_for_link(x))


if __name__ == "__main__":
    unittest.main()
