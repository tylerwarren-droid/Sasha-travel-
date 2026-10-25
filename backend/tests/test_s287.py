"""Sasha 287 · T67 — SASHA SENDS THE VENUE'S WHATSAPP HERSELF, FROM KANOE'S NUMBER, ON THE PERSON'S YES (beta: Tyler's and Jon's accounts,
Tyler's decision 23–24 Oct; AgAPI v1.29.3 carries the gate with `beta` and AGAPI_KANOE_WHATSAPP=on; CR 119 writes the beta rows).

ROOT TEST (written before the code):
  (1) ONE truth for "may this message leave Kanoe's number": AgAPI's gate — venue_messages.kanoe_send_allowed (agapi_service/
      venue_messages.py), checked by AgAPI at venue.prepare_booking (decision.sender "kanoe" | "person", its person_send.kanoe_sends), again
      at venue.submit_booking's read-back (status not_allowed) and again at the send (venue_submit._send_whatsapp → send_kanoe) — plus the
      approval S2 records: approvals.in_app_tap on THAT read-back's sha256 (AgAPI writes it on the booking's ONE record, record_yes, before the
      send; take_yes uses it up). S2 reads the gate's answer in ONE place: agapi/venues.py kanoe_whatsapp() — decision.sender from
      venue_submit.prepare, then venue_submit.read_back's not_allowed. S2 keeps no flag, no list and no second sender.
  (2) S2 deciding for itself whether Kanoe may send — its own flag or env switch, an allow-list of emails or accounts (the founder check),
      its own booking rules choosing request_whatsapp over AgAPI's answer, or a second send path beside 285's (s2_whatsapp._twilio, a
      messages.send_whatsapp of its own) = PATCH.
  (3) After it, S2 can never send without (a) AgAPI's gate saying yes for this person and (b) the person's tap on the exact read-back text,
      recorded before the send. The ratchet: the Kanoe card holds only on AgAPI's sender "kanoe" and a read-back; the send is only
      venue_submit.submit on the held read-back (in_app_tap on its sha256), once — a retry is AgAPI's approval_consumed, never a second send;
      no Kanoe flag / allow-list / Twilio post in S2's code; a "no" anywhere is the SAME card as their own WhatsApp (285's hand-over), never
      "can't".
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
       "when": {"at": "2099-11-01T21:00", "mode": "slot"}, "what": {"category": "restaurant"}}
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
                  mock.patch.object(VT, "decision", lambda p: PROFILE_DEC)]
        for p in self.p:
            p.start()
        VN.remember_cards(ACCT, [CARD])

    def tearDown(self):
        for p in self.p:
            p.stop()

    def hold(self):
        tok = VS.TAP.set({"kind": "supabase", "token": "their-session"})   # an in-app turn (/s2): its own session, for the whole turn
        try:
            return self._hold()
        finally:
            VS.TAP.reset(tok)

    def _hold(self):
        with mock.patch("agapi.test_venues.vet", mock.AsyncMock(side_effect=lambda c, a: a)), \
                mock.patch.object(VN, "_read", mock.AsyncMock(return_value=dict(RD))), \
                mock.patch.object(VN, "_reservation", mock.AsyncMock(return_value=RES)), \
                mock.patch.object(VN, "engine_channel", mock.AsyncMock(return_value=None)), \
                mock.patch.object(VN, "rules_for", mock.AsyncMock(side_effect=AssertionError("S2's own rules never decide a Kanoe send"))):
            out = run(VN.hold_venue(ctx("Book Casa Gate for 2 at 21:00 on 1 Nov"), {"name": "Casa Gate", "place_id": "ChIJ287",
                                                                                    "day": "2099-11-01", "time": "21:00", "party": 2}))
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


class GateYesOneSend(Base):
    """Offline 1 · gate yes → the exact read-back with ONE question → the tap → ONE send."""

    def test_the_card_is_agapis_read_back_with_the_one_question(self):
        out = self.hold()
        self.assertEqual(out["status"], "awaiting_yes")
        self.assertEqual(out["read_back"], LINES)                       # AgAPI's words, the exact text, as read back
        self.assertEqual(out["ask"], V.KANOE_ASK)                       # "Shall I send this from Kanoe's WhatsApp?"
        self.assertEqual([c["route"] for c in out["choices"]], ["send", "own"])
        ev = S.render("hold_venue", out, {})
        self.assertEqual((ev["kind"], ev["read_back_id"], ev["ask"]), ("read_back", "rbk_287", V.KANOE_ASK))
        self.assertEqual(V.read_back_line("hold_venue", {"ok": True, "result": out}), V.KANOE_ASK)
        self.assertEqual(self.agapi.sends, [])                          # nothing sent on the hold
        self.assertNotIn("approvals.request", self.agapi.ops)           # in the app: no SMS link, the tap is the yes

    def test_the_tap_sends_once_and_says_sent_at(self):
        self.hold()
        evs = self.tap()
        self.assertEqual(self.agapi.sends, ["rbk_287"], evs)
        said = _said(evs)
        self.assertRegex(said, r"^Sent at \d\d:\d\d · waiting for Casa Gate\.$")
        act = next(a for a in self.mem.kinds["venue_acts"] if a["act_id"] == "act_287")
        self.assertEqual((act["channel"], act["reference"]), ("whatsapp", "SM" + "2" * 32))   # the Twilio SID, on the booking


class GateNoTheHandOver(Base):
    """Offline 2 · gate no → the SAME card is their own WhatsApp (285's hand-over), AgAPI's words, nothing sent, never "can't"."""
    gate = False

    def test_not_in_beta_is_their_own_whatsapp(self):
        out = self.hold()
        self.assertEqual(out["status"], "page_link")
        self.assertEqual(out["page_url"], WA)
        self.assertEqual(out["button"], {"label": "Send on WhatsApp", "link": WA})
        self.assertTrue(out["say"].startswith(PROFILE_DEC["say_text"]))   # AgAPI's words for the person's own send
        self.assertNotIn("can't", out["say"].lower())
        self.assertNotIn("venue.submit_booking", self.agapi.ops)          # no read-back: nothing to say yes to
        self.assertEqual(self.agapi.sends, [])
        self.assertEqual(S.render("hold_venue", out, {})["kind"], "handover")
        self.assertEqual(self.mem.kinds[VN.PREPARED_KIND][-1]["url"], WA)  # the way back (283)


class GateNoAtTheReadBack(Base):
    gate, gate_at_read = True, False

    def test_refused_at_the_read_back_is_the_same_hand_over(self):
        out = self.hold()
        self.assertEqual((out["status"], out["page_url"]), ("page_link", WA))
        self.assertEqual(out["say"], V.OWN_WHATSAPP + " Say exactly that — never that it's booked.")   # AgAPI's "I can't…" never said
        self.assertEqual(self.agapi.sends, [])


class GateNoAtTheSend(Base):
    gate, gate_at_read, gate_at_send = True, True, False

    def test_refused_at_the_send_is_the_same_hand_over(self):
        self.hold()
        evs = self.tap()
        self.assertEqual(self.agapi.sends, [])
        self.assertEqual(_said(evs), V.OWN_WHATSAPP)
        ev = next(e for e in evs if e["type"] == "render")
        self.assertEqual((ev["kind"], ev["url"]), ("handover", WA))


class NoTapNoSend(Base):
    def test_no_tap_no_send(self):
        self.hold()
        self.assertEqual(self.agapi.sends, [])
        from agapi import v0 as API
        with self.assertRaises(API.ToolError):   # words that aren't a yes never send it
            run(VN.book_venue(ctx("hmm, maybe later"), {"name": "Casa Gate", "approval": {"said": "hmm, maybe later"}}))
        self.assertEqual(_said(self.tap(rid="rbk_other")), V.NOTHING_WAITING)   # a tap on a card that isn't the held one
        self.assertEqual(self.agapi.sends, [])
        self.assertNotIn("approvals.in_app_tap", self.agapi.ops)

    def test_own_is_their_whatsapp_never_a_send(self):
        self.hold()
        evs = self.tap(choice="own")
        self.assertEqual(self.agapi.sends, [])
        self.assertEqual(next(e for e in evs if e["type"] == "render")["url"], WA)


class RetryNoSecondSend(Base):
    def test_a_retry_never_sends_twice(self):
        self.hold()
        self.tap()
        self.tap()                                                        # the same tap again (a double tap, a retry)
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
    def test_waiting_then_the_reply_then_stop(self):
        self.hold()
        self.tap()
        with mock.patch.object(FakeAgAPI, "status", {"act_id": "act_287", "state": "sent", "venue_words": {"untrusted_text": ""}}):
            VS._ACTS.pop(ACCT, None)
            row = run(VS.bookings(ACCT))[0]
        self.assertEqual(row["status"], "requested")
        self.assertRegex(row["wa"], r"^Sent at \d\d:\d\d · waiting for Casa Gate\.$")
        from agapi import s2_status as SS
        self.assertIn(row["wa"], SS.decide({"venues": [row], "booked": [], "failed": []})["line"])
        with mock.patch.object(FakeAgAPI, "status", {"act_id": "act_287", "state": "confirmed",
                                                     "venue_words": {"untrusted_text": "Sí, confirmado para las 21:00"}}):
            row = run(VS.bookings(ACCT))[0]
        self.assertEqual((row["status"], row["venue_said"]["untrusted_text"]), ("confirmed", "Sí, confirmado para las 21:00"))
        self.assertEqual(row["wa"], V.wa_replied_line("Casa Gate", "Sí, confirmado para las 21:00"))
        VS._ACTS[ACCT][0].update({"state": "sent", "words": None, "answered": None})
        with mock.patch.object(FakeAgAPI, "status", {"act_id": "act_287", "state": "sent", "opted_out": True, "venue_words": {"untrusted_text": "STOP"}}):
            row = run(VS.bookings(ACCT))[0]
        self.assertEqual((row["status"], row["wa"]), ("stopped", V.wa_stopped_line("Casa Gate")))

    def test_a_stop_is_handed_to_agapi_and_kept(self):
        async def call(op, body, approval=None, account=None):
            return {"ok": True, "result": {"matched": True, "kept": True, "opted_out": True, "booking": None}}
        with mock.patch.object(VS, "CALL", call):
            got = run(VS.whatsapp_inbound("+34611222333", "STOP"))
        self.assertEqual((got["matched"], got["opted_out"]), (True, True))


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
        self.assertIn('d["action"] == "request_whatsapp"', va)
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

    def test_never_cant(self):
        for s in (V.KANOE_ASK, V.OWN_WHATSAPP, V.wa_sent_line("21:00", "X"), V.wa_stopped_line("X"), V.wa_replied_line("X", "ok")):
            self.assertNotIn("can't", s.lower())
            self.assertFalse(V.asks_for_link(s))


if __name__ == "__main__":
    unittest.main()
