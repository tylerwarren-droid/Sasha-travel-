"""Sasha 329 · CR 161 — the person's answer goes back as `choices` on venue.submit_booking (the SAME prepared_id), then the platform cancel
(Tyler, 3 Nov: "do all of that, then the cancel capability").

ROOT TEST (written first: docs/sasha/S-329-cr161.md)
  ONE trip record — AgAPI's act: the answer lives on AgAPI's prepared booking (choices), My bookings reads the act's state from AgAPI
  (venue.bookings / venue.booking_status), a cancel moves THAT record to cancelled. ONE AgAPI path — prepare once → submit_booking's
  read-back → yes → submit_booking; the answer is submit_booking {prepared_id, choices} (never prepare_booking `answers`); the cancel is
  cancel_venue → _cancel_act → venue.cancel_booking read-back → yes → venue.cancel_booking with the approval (never a second path).
  The ONE second copy is the booking-rules PATCH (2.6, byte-identical to AgAPI's — test_s265's ROW_965).
Offline: a fake AgAPI answers exactly CR 161's contract (agapi_service/tests/test_cr161.py); nothing leaves the process.

    cd backend && python3 -m unittest tests.test_s329 -v
"""
from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import pathlib
import re
import unittest
from datetime import datetime, timezone
from unittest import mock

from agapi import v0 as V0, venue_submit as VS, venues as VN
from booking_signer import contacts as CT

run = asyncio.run
ACCT = "00000000-0000-4000-8000-000000000329"
STANDIN = "https://agapi-sandbox.example/fixtures/platform/covermanager?popup=1&lists=1"
CANCEL = "https://agapi-sandbox.example/fixtures/platform/covermanager/cancel?ref=SBX-ABC123"
VENUE = "Taberna Sandbox"
RD = {"venue": VENUE, "rungs": {}, "place_id": "ChIJ329", "read_id": "r329", "country": "ES"}
RES = {"who": {"name": "Tyler Warren", "contact": {"mobile_e164": "+15005550123"}}, "how_many": {"count": 2},
       "when": {"at": "2026-11-20T22:00"}, "what": {"category": "restaurant"}}
CARD = {"name": VENUE, "website": "https://taberna.example", "place_id": "ChIJ329", "phone": "+34910000329"}
DEC = {"route": "platform", "channel": "CoverManager booking", "how_far": "hand_over", "say_text": "They book on CoverManager.",
       "button": {"label": "Book on CoverManager", "link": STANDIN, "sends": False}}
ASK = {"choice": "zona", "label": "Zona", "options": ["Salón Interior", "Terraza 1"]}


class Ctx:
    def __init__(self, said="", surface="s2"):
        self.account, self.surface, self.user_said, self.via, self.session = ACCT, surface, said, "page", "sess-329"
        self.started = datetime.now(timezone.utc)
        self.idem = self.act_name = self.claimed = None
        self.turn, self.said_before = "turn_" + __import__("uuid").uuid4().hex, ""   # Sasha 381 · the instruction's own id (agapi.v0.Ctx)


class Memory:
    def __init__(self):
        self.kinds = {}

    async def kind(self, _a, name):
        return self.kinds.get(name)

    async def put_kind(self, _a, name, value):
        self.kinds[name] = json.loads(json.dumps(value, default=str))
        return True


class AgAPI:
    """CR 161 as AgAPI origin/main answers it (venue_submit.submit, venue_manage.platform_cancel, venue.booking_status):
    - prepare_booking → platform_book (a beta person);
    - submit_booking {prepared_id, choices?} without approval → approval_required; the read-back's first line carries "; zona: <option>"
      once chosen (choices are kept ON the prepared booking, as AgAPI's venue_prepared.data);
    - the yes (approvals.in_app_tap / an approval id) → the walk: no zona chosen → failed + ask; chosen → confirmed, ref SBX-ABC123;
    - cancel_booking {act_id} without approval → approval_required (AgAPI's two lines); with the yes → `cancel` (cancelled, or a stop);
    - booking_status / bookings → the ONE record's state."""

    def __init__(self, cancel="cancelled", beta=True):
        self.calls, self.prepared, self.rbs, self.acts, self.mandates = [], {}, {}, {}, []
        self.cancel, self.beta, self.n = cancel, beta, 0

    def _rb(self, op, body, lines):
        rid = "rb_" + hashlib.sha256(json.dumps([op, body.get("prepared_id") or body.get("act_id"), lines]).encode()).hexdigest()[:12]
        self.rbs[rid] = (op, dict(body))
        return {"ok": False, "error": {"code": "approval_required", "details": {
            "read_back_id": rid, "read_back": {"lines": lines}, "read_back_sha256": hashlib.sha256("\n".join(lines).encode()).hexdigest()}}}

    def _lines(self, pid):
        picked = "; ".join(f"{k}: {v}" for k, v in self.prepared[pid].items())
        return ["Sasha fills in your booking on CoverManager for Taberna Sandbox (stand-in) and presses Book: date: 2026-11-20; "
                "time: 22:00; party: 2" + (f"; {picked}" if picked else "") + ".",
                "If their page asks for a card, a deposit or a sign-in, or shows a security check, it stops and hands the booking back to you."]

    def _submit(self, body):
        pid = body["prepared_id"]
        self.prepared[pid].update(body.get("choices") or {})
        self.n += 1
        aid = f"act_{self.n:03d}"
        if "zona" not in self.prepared[pid]:
            self.acts[aid] = {"state": "failed"}
            return {"prepared_id": pid, "status": "failed", "submitted": True, "how": "platform_form", "venue": VENUE, "act_id": aid,
                    "say": "Their booking asks for Zona: Salón Interior, Terraza 1. Which one? Their page has your details ready.",
                    "hand_over": {"link": STANDIN, "copy": [], "why": "choice"}, "ask": dict(ASK)}
        self.acts[aid] = {"state": "confirmed", "words": "Reserva confirmada"}
        return {"prepared_id": pid, "status": "confirmed", "submitted": True, "how": "platform_form", "venue": VENUE, "act_id": aid,
                "reference": "SBX-ABC123", "say": "Booked: Taberna Sandbox, 2026-11-20 22:00, 2 people, ref SBX-ABC123."}

    def _cancel(self, body):
        aid = body["act_id"]
        if self.cancel == "cancelled":
            self.acts[aid] = {"state": "cancelled", "words": "Reserva anulada"}
            return {"act_id": aid, "status": "cancelled", "cancel_act_id": "act_cxl", "venue_words": {"untrusted_text": "Reserva anulada"},
                    "say": "Cancelled: Taberna Sandbox, 2026-11-20 22:00, 2 people, ref SBX-ABC123 — their page says “Reserva anulada”."}
        say = "Cancelling it there charges a fee — that's your call, so I cancelled nothing. Here's their page."
        return {"act_id": aid, "status": "not_allowed", "cancel_act_id": "act_cxl", "why": ["fee"], "takeover": CANCEL, "link": CANCEL,
                "manage_url": CANCEL, "say": f"{say} Here's their own link: {CANCEL}"}

    async def call(self, op, body, approval=None, account=None):
        self.calls.append((op, json.loads(json.dumps(body)), approval))
        if op == "users.register":
            return {"ok": True, "result": {"end_user_id": "eu_329"}}
        if op == "venue.prepare_booking":
            pid = f"vpr_{len(self.prepared) + 1:032x}"
            self.prepared[pid] = {}
            return {"ok": True, "result": {"prepared_id": pid, "link": "https://agapi.example/prepared/t1", "submitted": False,
                                           "decision": {"route": "platform_book", "how_far": "zero_touch",
                                                        "say_text": "I'll fill in their booking and press Book for you."},
                                           "hand_over": {"link": STANDIN, "platform": "CoverManager", "carried": [], "copy": []}}}
        if op == "approvals.mandate":   # Sasha 381 · CR 196 · the booking's instruction (the turn's proof), recorded
            self.mandates.append(body)
            return {"ok": True, "result": {"mandate_id": f"mdt_{len(self.mandates):026d}", "expires_at": "2099-01-01T00:00:00Z",
                                           "proof": {"kind": body["proof"]["kind"]}}}
        if op == "venue.submit_booking" and body.get("mandate_id"):   # CR 196 · approved BY the instruction, acted at once
            if body.get("choices"):
                self.prepared[body["prepared_id"]].update(body["choices"])
            return {"ok": True, "result": {**self._submit(body), "instructed": {
                "mandate_id": body["mandate_id"], "say": "Booking now: Taberna Sandbox, 2 people, Fri 20 Nov at 22:00."}}}
        if op == "venue.submit_booking":
            if not approval:
                if body.get("choices"):   # kept on the ONE prepared booking at the read-back (AgAPI: venue_prepared.data.choices)
                    self.prepared[body["prepared_id"]].update(body["choices"])
                return self._rb(op, body, self._lines(body["prepared_id"]))
            return {"ok": True, "result": self._submit(body)}
        if op == "venue.cancel_booking":
            if not self.beta:
                return {"ok": True, "result": {"act_id": body["act_id"], "status": "not_allowed", "link": CANCEL, "why": ["not in the beta"],
                                               "say": "I can't cancel it on their page for you — here's their own cancel link."}}
            if not approval:
                return self._rb(op, body, ["Kanoe opens Taberna Sandbox's own cancellation on CoverManager and presses its cancel for your "
                                           "booking Fri 20 Nov 22:00 (reference SBX-ABC123).",
                                           "Only this booking: if their page shows another one, a fee, a sign-in or a security check, it "
                                           "stops and hands it back to you."])
            return {"ok": True, "result": self._cancel(body)}
        if op in ("approvals.in_app_tap", "sandbox.simulate_approval"):
            rop, rbody = self.rbs[body["read_back_id"]]
            if op == "sandbox.simulate_approval":
                return {"ok": True, "result": {"approval_id": "apv_" + body["read_back_id"]}}
            return {"ok": True, "result": {"approval_id": "apv", "result": self._submit(rbody) if rop == "venue.submit_booking"
                                           else self._cancel(rbody)}}
        if op == "venue.booking_status":
            a = self.acts.get(body["act_id"])
            if not a:
                return {"ok": False, "error": {"code": "not_found"}}
            return {"ok": True, "result": {"act_id": body["act_id"], "state": a["state"],
                                           **({"venue_words": {"untrusted_text": a["words"]}} if a.get("words") else {})}}
        if op == "venue.bookings":
            return {"ok": True, "result": {"bookings": [{"act_id": k, "state": v["state"],
                                                         **({"venue_words": {"untrusted_text": v["words"]}} if v.get("words") else {})}
                                                        for k, v in self.acts.items()]}}
        if op == "venue.manage_options":
            return {"ok": False, "error": {"code": "unknown_operation"}}
        return {"ok": False, "error": {"code": "unexpected", "message": op}}

    def ops(self):
        return [op for op, _, _ in self.calls]

    def bodies(self, op, approved=None):
        return [b for o, b, a in self.calls if o == op and (approved is None or bool(a) == approved)]


class Base(unittest.TestCase):
    CANCEL = "cancelled"
    BETA = True
    TAP = True

    def setUp(self):
        from agapi import s2_memory as M, s2_outcomes as OC
        from booking_signer import guest_receipt as GR, live_events as LE, mailbox as MB, wa_brain as WB
        for d in (VN._HELD, VN._PREV, VN._CANCEL, VN._SENT, VS._ACTS, VS._RECORD):
            d.pop(ACCT, None)
        VS._USERS.clear()
        V0._CLAIMED.clear()
        self.mem, self.ag = Memory(), AgAPI(self.CANCEL, self.BETA)
        self.contacts = CT.MemoryContactStore()
        self.contacts.rows[ACCT] = {"account_id": ACCT, "name": "Tyler Warren", "mobile_e164": "+15005550123",
                                    "consent_at": datetime(2026, 11, 1, tzinfo=timezone.utc), "consent_wording_version": "v1",
                                    "consent_text_sha256": "0" * 64}
        GW = VN._API()
        self.p = [mock.patch.object(M, "kind", self.mem.kind), mock.patch.object(M, "put_kind", self.mem.put_kind),
                  mock.patch.object(VS, "CALL", self.ag.call), mock.patch.object(VS, "target", mock.AsyncMock(return_value="sandbox")),
                  mock.patch.object(CT, "STORE", self.contacts), mock.patch.object(MB, "STORE", MB.MemoryMailboxStore()),
                  mock.patch.object(GR, "address_of", mock.AsyncMock(return_value="t@example.test")),
                  mock.patch.object(WB, "trip_day_words", mock.AsyncMock(return_value="")),
                  mock.patch.object(OC, "booked_later", lambda *a, **k: None),
                  mock.patch.object(LE, "completed", mock.AsyncMock(return_value={})),
                  mock.patch.object(GW, "api", mock.AsyncMock(return_value=(200, {"reservations": []}))),
                  mock.patch.object(VN, "card_of", lambda acct, pid=None, name=None: CARD),
                  mock.patch("booking_signer.basket._run", lambda: None)]
        for p in self.p:   # Sasha 381 · cleanups, never tearDown: they run even when a subclass's setUp fails (s330's booked())
            p.start()
            self.addCleanup(p.stop)
        tok = VS.TAP.set({"kind": "supabase", "token": "test-session"} if self.TAP else None)
        self.addCleanup(VS.TAP.reset, tok)
        p = mock.patch.dict("os.environ", {"SASHA_AGAPI_TAP_SECRET": "s329-secret"})   # Sasha 381 · the instruction's proof is signed
        p.start()
        self.addCleanup(p.stop)
        for d in (VN._HELD, VN._CANCEL, VS._ACTS, VS._RECORD):
            self.addCleanup(d.pop, ACCT, None)

    def hold(self):
        return run(VN.follow(Ctx("book Taberna Sandbox friday 22:00 for 2"), {"name": VENUE, "city": "Madrid"}, RD, RES,
                             "2026-11-20T22:00", datetime.now(timezone.utc), CARD, DEC))

    def yes(self):
        return run(VN.book_venue(Ctx("Yes, book it"), {"approval": {"said": "Yes, book it"}}))

    def booked(self):
        q = self.hold()   # Sasha 381 · acted on the instruction at once: the walk's question (Zona) is what comes back
        done = run(VN.answer_card(Ctx("Salón Interior"), q["read_back_id"], "pick:Salón Interior"))
        self.assertEqual(done["status"], "confirmed", done)
        return done


class TheAskBecomesTapsAndGoesBackAsChoices(Base):
    def test_ask_taps_then_submit_with_the_same_prepared_id_and_choices(self):
        q = self.hold()   # Sasha 381 · no yes card: AgAPI pressed on at once and stopped on the term only they can give
        self.assertEqual(q["route"], "platform_book")
        print("\n── AgAPI's ask, asked ONCE ──\n" + json.dumps({k: q[k] for k in ("ask", "choices")}, ensure_ascii=False))
        self.assertEqual([c["title"] for c in q["choices"]], ASK["options"])                       # exactly AgAPI's options
        self.assertEqual([c["route"] for c in q["choices"]], ["pick:Salón Interior", "pick:Terraza 1"])
        self.assertIn("Zona", q["ask"])
        self.assertNotIn("CoverManager", q["ask"])                                                  # 249: never the platform
        done = run(VN.answer_card(Ctx("Salón Interior"), q["read_back_id"], "pick:Salón Interior"))
        pid = next(iter(self.ag.prepared))
        subs = self.ag.bodies("venue.submit_booking")
        print("── venue.submit_booking bodies ──\n" + "\n".join(json.dumps(b, ensure_ascii=False) for b in subs))
        self.assertEqual(len(self.ag.bodies("venue.prepare_booking")), 1)                          # prepared ONCE
        self.assertTrue(all("answers" not in b for b in self.ag.bodies("venue.prepare_booking")))   # never answers-on-prepare
        self.assertEqual({b["prepared_id"] for b in subs}, {pid})                                  # the SAME prepared_id
        self.assertEqual(subs[-1]["choices"], {"zona": "Salón Interior"})
        self.assertEqual(len(self.ag.mandates), 2)                      # the instruction, then their answer: each its own turn's proof
        print("── said ──\n" + done["line"])
        self.assertEqual(done["status"], "confirmed")
        for part in (VENUE, "22:00", "2 people", "SBX-ABC123"):   # Sasha 381 · Tyler's ONE line; their choice stays on the booking
            self.assertIn(part, done["line"])
        self.assertEqual(done["area"], "Salón Interior")
        self.assertEqual(self.ag.ops().count("approvals.in_app_tap"), 0)                           # no tap: the instructions approved it

    def test_my_bookings_shows_it_with_the_reference_and_the_choice(self):
        self.booked()
        rows = run(VS.bookings(ACCT))
        print("\n── My bookings ──\n" + json.dumps(rows, ensure_ascii=False))
        self.assertEqual(len(rows), 1)                                                              # the stop that asked is not a booking
        self.assertEqual((rows[0]["status"], rows[0]["reference"], rows[0]["route"], rows[0]["chosen"]),
                         ("confirmed", "SBX-ABC123", "platform", {"zona": "Salón Interior"}))


class NoVerifiedPersonNothingIsPressed(Base):
    """Sasha 381 · CR 196 · a turn with nothing to prove it by (no conversation of its own in the app, no signed WhatsApp message): the
    instruction can't be recorded as theirs — nothing is pressed, and never a simulated yes in its place."""
    TAP = False

    def test_nothing_pressed(self):
        ctx = Ctx("book Taberna Sandbox friday 22:00 for 2")
        ctx.session = None
        out = run(VN.follow(ctx, {"name": VENUE, "city": "Madrid"}, RD, RES, "2026-11-20T22:00", datetime.now(timezone.utc), CARD, DEC))
        self.assertEqual(out["status"], "not_sent")
        self.assertEqual(self.ag.bodies("venue.submit_booking", approved=True), [])
        self.assertNotIn("sandbox.simulate_approval", self.ag.ops())
        self.assertNotIn("approvals.mandate", self.ag.ops())


class CancelIt(Base):
    def test_cancel_it_read_back_then_yes_then_cancelled_on_the_one_record(self):
        done = self.booked()
        aid = done["act_id"]
        n = len(self.ag.calls)
        rb = run(VN.cancel_venue(Ctx("cancel it"), {"act_id": aid}))
        print("\n── \"cancel it\" ──\n" + rb["ask"] + "\n" + "\n".join(rb["read_back"]))
        self.assertEqual(rb["status"], "awaiting_yes")
        self.assertEqual(rb["ask"], "Cancel Taberna Sandbox, Fri 20 Nov 22:00, 2 people, ref SBX-ABC123?")
        self.assertEqual([(o, a) for o, _, a in self.ag.calls[n:] if o == "venue.cancel_booking"], [("venue.cancel_booking", None)])
        self.assertNotIn("approvals.in_app_tap", self.ag.ops()[n:])                                  # nothing pressed before the yes
        out = run(VN.cancel_venue(Ctx("Yes, cancel it"), {"act_id": aid, "approval": {"said": "Yes, cancel it"}}))
        print("── said ──\n" + out["line"])
        self.assertEqual(out["status"], "cancelled")
        self.assertTrue(out["line"].startswith("Cancelled — Taberna Sandbox, Fri 20 Nov 22:00, 2 people, ref SBX-ABC123."))
        self.assertIn("Reserva anulada", out["line"])
        self.assertEqual(self.ag.acts[aid]["state"], "cancelled")
        rows = run(VN.venue_bookings(ACCT, include_cancelled=True))
        print("── My bookings ──\n" + json.dumps(rows, ensure_ascii=False))
        self.assertEqual([(r["act_id"], r["status"]) for r in rows], [(aid, "cancelled")])           # the ONE booking reads cancelled
        self.assertNotIn("cancel", rows[0])                                                           # never "waiting for the venue"
        self.assertEqual(rows[0]["venue_said"], {"untrusted_text": "Reserva anulada"})                # AgAPI's record, read
        self.assertEqual(run(VN.venue_bookings(ACCT)), [])

    def test_cancel_la_taberna_by_name_from_the_app_still_reads_back_first(self):
        done = self.booked()
        rb = run(VN.cancel_venue(Ctx("Cancel Taberna Sandbox"), {"venue": VENUE}))
        self.assertEqual(rb["status"], "awaiting_yes")      # Sasha 314's one-instruction rule never sends a platform cancel
        self.assertEqual(self.ag.acts[done["act_id"]]["state"], "confirmed")
        with self.assertRaises(V0.ToolError) as e:           # "what will it say?" is not a yes
            run(VN.cancel_venue(Ctx("what does that mean?"), {"act_id": done["act_id"], "approval": {"said": "what does that mean?"}}))
        self.assertEqual(e.exception.code, "no_explicit_yes")
        self.assertEqual([a for o, _, a in self.ag.calls if o == "venue.cancel_booking" and a], [])
        self.assertEqual(self.ag.ops().count("approvals.in_app_tap"), 0)   # the booking's were instructions — and no cancel tap


class AFeeStops(Base):
    CANCEL = "fee"

    def test_fee_gives_their_link_the_phone_and_why(self):
        done = self.booked()
        run(VN.cancel_venue(Ctx("cancel it"), {"act_id": done["act_id"]}))
        out = run(VN.cancel_venue(Ctx("Yes, cancel it"), {"act_id": done["act_id"], "approval": {"said": "Yes, cancel it"}}))
        print("\n── a fee ──\n" + out["line"] + "\n" + json.dumps(out.get("button")))
        self.assertEqual((out["status"], out["cancelled"], out["page_url"], out["why"]), ("yours_there", False, CANCEL, ["fee"]))
        self.assertEqual(out["button"]["link"], CANCEL)
        self.assertIn("charges a fee", out["line"])
        self.assertIn("+34910000329", out["line"])
        from app.agent import sasha as S
        self.assertEqual(S.render("cancel_venue", out, {})["url"], CANCEL)
        self.assertEqual(run(VS.bookings(ACCT))[0]["status"], "confirmed")                          # still booked


class OutsideTheBeta(Base):
    BETA = False

    def test_link_and_phone_nothing_pressed(self):
        done = self.booked()
        out = run(VN.cancel_venue(Ctx("cancel it"), {"act_id": done["act_id"]}))
        self.assertEqual((out["status"], out["page_url"]), ("yours_there", CANCEL))
        self.assertIn("+34910000329", out["line"])
        self.assertEqual([a for o, _, a in self.ag.calls if o == "venue.cancel_booking" and a], [])


ROOT = pathlib.Path(__file__).resolve().parents[1]


class TheWholeClass(unittest.TestCase):
    def _py(self):
        for d in ("agapi", "booking_signer", "app"):
            for f in (ROOT / d).rglob("*.py"):
                yield f, f.read_text()

    def test_no_answers_on_prepare_left(self):
        self.assertNotIn("answers", inspect.signature(VS.prepare).parameters)
        self.assertNotIn("answers", inspect.getsource(VS.prepare).split('"""')[-1])   # its body (the docstring may say why)
        self.assertNotIn("VS.prepare(", inspect.getsource(VN.platform_answer))
        self.assertIn('"choices": choices}', inspect.getsource(VN.platform_answer))   # Sasha 381 · their answer, on the SAME prepared booking
        self.assertIn('{"choices": dict(held["choices"])}', inspect.getsource(VS.submit_instructed))   # … sent with its instruction (CR 196)
        for f, s in self._py():
            self.assertNotRegex(s, r"prepare\([^)]*answers\s*=", str(f))

    def test_the_walks_sentence_is_read_nowhere(self):
        for f, s in self._py():
            self.assertNotIn("Their booking asks for", s, str(f))
            self.assertNotIn("choice_of", s, str(f))

    def test_one_cancel_path(self):
        hits = sorted(str(f.relative_to(ROOT)) for f, s in self._py() if re.search(r'OP\.VENUE_CANCEL_BOOKING,\s*\{', s))
        self.assertEqual(hits, ["agapi/venue_submit.py"])
        self.assertFalse(hasattr(VN, "platform_cancel"))
        src = inspect.getsource(VN._cancel_act)
        self.assertEqual(src.count("VS.cancel_read_back("), 1)
        self.assertNotIn("return platform_cancel", src)

    def test_a_cancel_never_without_the_read_back_yes(self):
        """Every cancel_submit in _cancel_act is behind the explicit yes to a held read-back, or (never a platform act) one_instruction."""
        src = inspect.getsource(VN._cancel_act)
        first_submit = src.index("VS.cancel_submit(")
        self.assertLess(src.index("if not explicit_yes(said):"), first_submit)
        self.assertLess(src.index("if plat:   # Sasha 329 · CR 161 · pressing a cancel"), src.index("if await one_instruction("))


if __name__ == "__main__":
    unittest.main()
