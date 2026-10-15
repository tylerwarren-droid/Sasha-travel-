"""Sasha 269 · T51 — "CALL THEM AGAIN" IS THE ENGINE'S (CR 100, mailbox rows 965/985; Tyler: after a no-answer ask "try once more, or fill
in their form?"; after a second, recommend the form). ONE source of truth: AgAPI v1.15.0's act ledger + booking-rules/2.1. Offline.

  (a) booking-rules/2.1 vendored byte-identical (the hashes are test_s265's ROW_965)
  (b) NO retry loop, timer or call decision of Sasha's own: venue_calls._again, call_routes.confirm_unclear / retry_confirmation,
      guest_whatsapp.auto_call_from_email / offer_no_reply_call / offer_escalation — gone; after a call nothing is redialled
  (c) after a no-answer: AgAPI's `say` + its ONE question as a card (its choices); "Try once more" → venue.call_again person_asked (no new
      card, no approval asked); asked twice = ONE call (one booking_calls row per call_plan.call_id); the second: the line + the page
  (d) a Google-listing number goes to the act as call {phone, source "listing"} — Sasha keeps its place and hash, never its digits
  (e) /you: users.link_whatsapp (nothing sent) → the code FROM that number → users.confirm_whatsapp (Sasha-signed) → only then linked
  (f) get_status shows venue.booking_status's own fields (state, say, ask, choices, next_step, calls) — never re-derived

    cd backend && python -m unittest tests.test_s269 -v
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
import pathlib
import re
import unittest
from unittest import mock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from agapi import s2_status as SS, venue_calls as VC, venue_submit as VS, venues as VN
from agapi.booking_rules import booking_rules as BR
from app.agent import sasha as S, voice as V
from booking_signer import call_routes as CR, call_store as CS, calls as C, guest_whatsapp as GW, proactive as PR

ACCT = "00000000-0000-4000-8000-000000000269"
FRONT = pathlib.Path(__file__).resolve().parents[2] / "frontend"
PAGE = "https://agapi-sandbox.test/fixtures/taverna"
LISTING = "+15005550179"
FIRST = {"status": "recorded", "state": "no_answer", "no_answers": 1, "say": BR.PHRASES["no_answer_first"], "ask": BR.PHRASES["ask_try_again"],
         "choices": [{"id": "call_again", "label": "Try once more"}, {"id": "their_page", "label": "Fill in their form", "page": PAGE}],
         "next_step": {"kind": "their_page", "page": PAGE}, "next_call": {"allowed": False, "reason": "too_soon", "needs": "person_asks"}}
SECOND = {"status": "recorded", "state": "no_answer", "no_answers": 2, "say": BR.PHRASES["no_answer"], "next_step": {"kind": "their_page", "page": PAGE}}
NOBODY = type("R", (), {"state": "not_reached", "outcome": None, "venue_words": "", "why": "no answer"})()


def run(c):
    return asyncio.run(c)


def _src(case, rel):
    f = FRONT / rel
    if not f.exists():
        case.skipTest("frontend/ is not in this checkout (a backend-only build)")
    return re.sub(r"/\*[\s\S]*?\*/|//[^\n]*", "", f.read_text())


class TheRules21(unittest.TestCase):
    def test_gate_the_engine_s_words(self):
        self.assertTrue(BR.VERSION.startswith("booking-rules/2.1"))
        self.assertEqual(BR.PHRASES["no_answer_first"], "They didn't pick up.")
        self.assertEqual(BR.PHRASES["no_answer"], "They didn't pick up again — the form is the fastest way.")
        self.assertEqual(BR.no_answer(PAGE, n=1)["ask_text"], BR.PHRASES["ask_try_again"])
        self.assertNotIn("ask", BR.no_answer(PAGE, n=2))


class NoSecondCopy(unittest.TestCase):
    def test_gate_sashas_own_retries_and_follow_up_calls_are_deleted(self):
        self.assertFalse(hasattr(VC, "_again"))
        for gone in ("confirm_unclear", "retry_confirmation", "confirm_brief"):
            self.assertFalse(hasattr(CR, gone), gone)
        for gone in ("auto_call_from_email", "offer_no_reply_call", "offer_escalation"):
            self.assertFalse(hasattr(GW, gone), gone)
        src = pathlib.Path(PR.__file__).read_text()
        self.assertIn('VC.again(account, act["act_id"], "R5")', src)                    # R5: the act's own follow-up
        self.assertIn('VC.again(ctx.account, r["act_id"], "R6")', pathlib.Path(VN.__file__).read_text())   # R6 too

    def test_gate_nothing_is_redialled_after_a_call(self):
        with mock.patch.object(VS, "call_attempt", mock.AsyncMock(return_value={"ok": True, "result": dict(FIRST)})), \
                mock.patch.object(VS, "acts_of", mock.AsyncMock(return_value=[])), mock.patch.object(VC, "tell", mock.AsyncMock()), \
                mock.patch.object(VS, "call_again", mock.AsyncMock(side_effect=AssertionError("redialled"))), \
                mock.patch.object(VC, "dial", mock.AsyncMock(side_effect=AssertionError("dialled"))):
            got = run(VC.after_call({"account_id": ACCT, "brief": {"act_id": "act_1"}}, NOBODY))
        self.assertEqual(got["state"], "no_answer")

    def test_one_path_never_makes_sashas_own_call(self):
        src = pathlib.Path(VN.__file__).read_text()
        block = src[src.index("    if one_path(ctx) and (key == \"ask_page_or_call\""):src.index("    if action == \"ask_one_question\":")]
        self.assertIn("_call_question", block)
        self.assertNotIn("await _call(", block)


class AfterANoAnswer(unittest.TestCase):
    def after(self, res):
        told = []

        async def tell(account, text, card=None, wa_text=None):
            told.append((text, card, wa_text))
            return "captured"
        with mock.patch.object(VS, "call_attempt", mock.AsyncMock(return_value={"ok": True, "result": dict(res)})), \
                mock.patch.object(VS, "acts_of", mock.AsyncMock(return_value=[])), mock.patch.object(VC, "tell", tell):
            run(VC.after_call({"account_id": ACCT, "brief": {"act_id": "act_1"}}, NOBODY))
        return told[0]

    def test_gate_the_first_the_line_then_the_one_question_card(self):
        text, card, wa = self.after(FIRST)
        self.assertEqual(text, "They didn't pick up. " + BR.PHRASES["ask_try_again"])
        self.assertEqual((card["kind"], card["act_id"], card["ask"]), ("no_answer", "act_1", BR.PHRASES["ask_try_again"]))
        self.assertEqual([c["id"] for c in card["choices"]], ["call_again", "their_page"])
        self.assertEqual(card["choices"][1]["page"], PAGE)                                   # "Fill in their form" → next_step.page
        self.assertIn(V.WA_TRY_AGAIN, wa)
        self.assertIn(PAGE, wa)                                                              # WhatsApp: no card — in words, with the link

    def test_gate_the_second_the_line_and_the_link_no_question(self):
        text, card, wa = self.after(SECOND)
        self.assertEqual(text, f"{BR.PHRASES['no_answer']} {PAGE}")
        self.assertEqual((card["choices"], card["ask"], card["page"]), ([], None, PAGE))
        self.assertNotIn(V.WA_TRY_AGAIN, wa)

    def test_the_page_draws_the_card_and_the_tap_is_the_act_s(self):
        app = _src(self, "app/s2/S2App.tsx")
        self.assertIn("ev.render?.kind === 'no_answer' && ev.render.act_id", app)
        self.assertIn("data-card-choice=\"call_again\"", app)
        self.assertIn("route === 'call_again' ? { act_id: rid, choice: route }", app)
        src = pathlib.Path(S.__file__).read_text()
        self.assertIn('if tap.get("choice") == "call_again" and tap.get("act_id"):', src)


class TryOnceMore(unittest.TestCase):
    ACT = {"act_id": "act_1", "venue": "Taverna Sandbox", "when": "2026-10-16T21:00", "party": 2, "route": "call", "state": "no_answer",
           "call": {"venue": "Taverna Sandbox", "timezone": "Europe/Madrid", "lines": ["2 people at Taverna Sandbox"],
                    "call_ref": {**VC.number_ref(LISTING, "ChIJ-taverna"), "source": "listing"}}}
    OPEN = {"act_id": "act_1", "status": "calling", "reason": "person_asked", "say": "On it — I'll try them again in 30 minutes.",
            "approval": {"inherited": True, "approval_id": "apv_1", "asked_again": False},
            "call_plan": {"phone": LISTING, "source": "listing", "when": "in 30 minutes", "simulate": False, "call_id": "vcp_1",
                          "next_call": {"allowed": False, "allowed_at": "2099-01-01T00:00:00Z"}, "payload": dict(BR.CALL_PAYLOAD),
                          "opening": BR.call_opening("calling about the booking."), "rules": list(BR.CALL_RULES)}}

    def setUp(self):
        self.ops, self.store = [], CS.MemoryCallStore()

        async def call(op, body, approval=None, account=None):
            self.ops.append((op, body))
            if op == "users.register":
                return {"ok": True, "result": {"end_user_id": "usr_1"}}
            if op == "venue.call_again":
                return {"ok": True, "result": json.loads(json.dumps(self.OPEN))}
            raise AssertionError(f"unexpected {op}")
        acts = [json.loads(json.dumps(self.ACT))]

        async def remember(account, act):
            acts[:] = [a for a in acts if a["act_id"] != act["act_id"]] + [act]

        async def listing_number(http, ref, now):
            self.assertEqual(ref["sha256"], hashlib.sha256(LISTING.encode()).hexdigest())
            return LISTING
        for p in (mock.patch.object(VS, "CALL", call), mock.patch.object(VS, "acts_of", mock.AsyncMock(side_effect=lambda a: list(acts))),
                  mock.patch.object(VS, "_remember", remember), mock.patch.object(VS, "target", mock.AsyncMock(return_value="sandbox")),
                  mock.patch("booking_signer.places_terms.listing_number", listing_number), mock.patch.object(CR, "CALL_STORE", self.store),
                  mock.patch.object(C, "calls_enabled", lambda: True), mock.patch.object(C, "bland_key", lambda: "k"),
                  mock.patch.object(C, "place_call", mock.AsyncMock(side_effect=AssertionError("dialled before the act allows it")))):
            p.start()
            self.addCleanup(p.stop)
        VS._USERS.clear()

    def test_gate_the_tap_is_call_again_person_asked_with_no_new_card(self):
        evs = run(self.collect(S._try_again(ACCT, "act_1")))
        self.assertEqual(evs[-1]["text"], self.OPEN["say"])                                  # the act's own words
        again = [b for op, b in self.ops if op == "venue.call_again"]
        self.assertEqual(again, [{"act_id": "act_1", "reason": "person_asked", "call": {"phone": LISTING, "source": "listing"}, "end_user": "usr_1"}])
        self.assertFalse([op for op, _ in self.ops if op.startswith("approvals.") or op == "venue.submit_booking"])   # no new approval

    def test_gate_asked_twice_is_one_call(self):
        run(VC.again(ACCT, "act_1"))
        second = run(VC.again(ACCT, "act_1"))
        self.assertEqual(second["dial"], "already_open")
        rows = [r for r in self.store.calls.values() if (r["brief"] or {}).get("call_plan_id") == "vcp_1"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["approval"]["scheduled_for"][:4], "2099")                  # at next_call.allowed_at, never sooner
        self.assertTrue(rows[0]["dialled_number"].startswith("sha256:"))                     # a listing's: its hash, never its digits
        self.assertNotIn(LISTING[1:], json.dumps(rows[0], default=str))

    @staticmethod
    async def collect(gen):
        return [ev async for ev in gen]


class ListingNumbers(unittest.TestCase):
    def test_gate_the_listing_number_goes_to_the_act_for_one_call(self):
        rd = {"facts": [{"kind": "phone", "source_kind": "places", "value": LISTING}]}
        self.assertIsNone(VN.own_number(rd))
        self.assertEqual(VN.listing_number(rd), LISTING)
        src = pathlib.Path(VN.__file__).read_text()
        self.assertIn('phone, source = listing_number(rd), "listing"', src)
        self.assertIn('rb = await VS.read_back(ctx.account, p["prepared_id"], route="call", call=call)', src)   # passed again (gate)
        brief = VC.brief_of("act_1", {"phone": LISTING, "source": "listing", "call_id": "vcp_1"}, {"place_id": "ChIJ-t"})
        self.assertIsNone(brief["number"])
        self.assertNotIn(LISTING[1:], json.dumps(brief))
        self.assertEqual(brief["number_ref"]["place_id"], "ChIJ-t")


class WhatsAppVerifiedAtLinking(unittest.TestCase):
    def test_gate_the_signature_is_cr100_s(self):
        body = hashlib.sha256(b"Kanoe link 123456").hexdigest()
        want = hmac.new(b"s3cret", f"1760000000.{'n' * 16}.whatsapp_link.15005550194.SM1.{body}".encode(), hashlib.sha256).hexdigest()
        self.assertEqual(VS.whatsapp_link_signature("s3cret", 1760000000, "n" * 16, "15005550194", "SM1", "Kanoe link 123456"), want)

    def test_gate_linking_registers_unverified_and_sends_nothing(self):
        app = FastAPI()
        app.include_router(GW.router, prefix="/api/booking")
        saved = (GW.STORE, GW.SENDER)
        GW.STORE, GW.SENDER = GW.MemoryGuestStore(), mock.MagicMock()
        self.addCleanup(lambda: setattr(GW, "STORE", saved[0]) or setattr(GW, "SENDER", saved[1]))
        link = mock.AsyncMock(return_value={"ok": True, "state": "awaiting_message", "sent": False, "code": "123456", "text": "Kanoe link 123456",
                                            "expires_at": "2099-01-01T00:00:00Z"})
        c = GW.consent()
        with mock.patch("booking_signer.account.account_for", lambda r: ACCT), mock.patch.object(VS, "link_whatsapp", link), \
                mock.patch.object(GW, "guest_numbers", lambda: {"+14155238886"}):
            r = TestClient(app).post("/api/booking/whatsapp/link", json={"consent_version": c["version"], "consent_sha256": c["sha256"],
                                                                         "whatsapp": "+1 500 555 0194"})
            bad = TestClient(app).post("/api/booking/whatsapp/link", json={"consent_version": c["version"], "consent_sha256": c["sha256"]})
        self.assertEqual(r.status_code, 200, r.text)
        j = r.json()
        link.assert_awaited_once_with(ACCT, "+15005550194")
        self.assertEqual((j["text"], j["sent"]), ("Kanoe link 123456", False))
        self.assertIn("Kanoe%20link%20123456", j["wa_link"])
        self.assertEqual(bad.status_code, 422)                                               # no number: no code
        GW.SENDER.assert_not_called()
        self.assertEqual(GW.SENDER.method_calls, [])


class GetStatusIsTheEngines(unittest.TestCase):
    def test_gate_booking_status_fields_as_they_are(self):
        self.assertNotIn("no_answer", VS.FINAL)                                              # 2.1: not final — read again
        acts = [{"act_id": "act_1", "venue": "Taverna Sandbox", "when": "2026-10-16T21:00", "party": 2, "state": "calling", "route": "call"}]
        st = {"state": "no_answer", "say": FIRST["say"], "ask": FIRST["ask"], "choices": FIRST["choices"], "next_step": FIRST["next_step"],
              "calls": {"made": 1, "no_answers": 1, "open": False}}
        with mock.patch.object(VS, "acts_of", mock.AsyncMock(return_value=acts)), mock.patch.object(VS, "status", mock.AsyncMock(return_value=st)), \
                mock.patch.dict(VS._ACTS, {ACCT: acts}), mock.patch("agapi.s2_memory.put_kind", mock.AsyncMock(return_value=True)):
            rows = run(VS.bookings(ACCT))
        row = rows[0]
        self.assertEqual((row["status"], row["how"], row["ask"], row["choices"], row["next_step"], row["calls"]),
                         ("no_answer", FIRST["say"], FIRST["ask"], FIRST["choices"], FIRST["next_step"], st["calls"]))
        line = SS._call_line(row)
        self.assertIn(FIRST["say"], line)
        self.assertIn(FIRST["ask"], line)
        self.assertIn(PAGE, line)


if __name__ == "__main__":
    unittest.main()
