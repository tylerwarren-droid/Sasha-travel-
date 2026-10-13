"""Sasha 252 · G3 — Sasha's OWN questions answered on the one brain, tap or typed (Tyler: "a typed yes to Sasha's own questions
is lost"). The brain's state lives in its own key (st["agent"]); st["pending"] holds only Sasha's open question; one resolver,
before the model, answers it with the code that answers it today (_answer_pending) — or hands the message to the brain and
leaves the question open. Offline: the brain is a stand-in at wa_agent.agent_turn's boundary; no network, no model, no database.

    cd backend && python -m unittest tests.test_s252_g3 -v
"""
from __future__ import annotations

import os
import unittest
from unittest import mock

from booking_signer import guest_whatsapp as GW, invitations as IV, mailbox as MB, wa_agent as WA
from tests import test_guest_whatsapp_s75 as TG

run, ACCOUNT, GUEST, NOW = TG.run, TG.ACCOUNT, TG.GUEST, TG.NOW
BRAIN: dict = {}   # Sasha 253 · item 5: no switch any more (SASHA_WA_BRAIN retired) — every account is on the one brain


class Api(TG.FakeApi):
    """The booking routes Sasha's own questions answer through, faked at the same in-process boundary."""

    async def __call__(self, account, method, path, body=None, timeout=90.0):
        if path.startswith("/api/booking/payments/") and path.endswith("/approve"):
            self.calls.append((account, method, path, body))
            return 200, {"say": "I've asked Casa Lucio for their payment link."}
        if path.startswith("/api/booking/mailbox/finds/"):
            self.calls.append((account, method, path, body))
            return 200, {"say": "Added: Casa Lucio, Saturday 21:00." if body.get("yes") else "OK — left out."}
        if path.startswith("/api/booking/links/") and path.endswith("/booked"):
            self.calls.append((account, method, path, body))
            return 200, {"ok": True}
        return await super().__call__(account, method, path, body, timeout)


class Base(TG.Base):
    def setUp(self):
        super().setUp()
        GW.api = Api()
        self.seen = []

        async def brain(ch, body, payload, st, out, now, button_text="", voice_in=False):
            self.seen.append(body or payload)
            WA.set_agent_state(st, last_seen=now.isoformat())   # the brain keeps its own state, as the real turn does
            out.text(f"agent: {body or payload}")
            return "x"
        self.patches = [mock.patch.object(WA, "agent_turn", brain), mock.patch.dict(os.environ, BRAIN),
                        mock.patch.object(MB, "NOW", lambda: self.now), mock.patch.object(IV, "NOW", lambda: self.now),
                        mock.patch.object(MB, "STORE", None)]   # no Gmail linked (no database)
        for p in self.patches:
            p.start()
        self.iv_saved = IV.STORE
        IV.STORE = IV.MemoryInviteStore()
        self.ch = self.link()
        self.say("hello")                     # a brain turn first: the 24-hour window is open, the brain has state
        self.seen.clear()

    def tearDown(self):
        IV.STORE = self.iv_saved
        for p in reversed(self.patches):
            p.stop()
        super().tearDown()

    def st(self):
        return run(GW.STORE.get_state(GW.wa_key(GUEST)))

    def pend(self):
        return self.st().get("pending") or {}

    def paths(self):
        return self.api_paths()

    def in_between(self):
        """A different message: the brain's, and Sasha's question is still open afterwards (and the brain's state kept)."""
        kind = self.pend().get("kind")
        self.say("what's the weather in Madrid tomorrow")
        self.assertEqual(self.seen[-1], "what's the weather in Madrid tomorrow")
        self.assertEqual(self.pend().get("kind"), kind)
        self.assertTrue(WA.agent_state(self.st()).get("last_seen"))

    def last_buttons(self):
        return [b[1] for b in GW.SENDER.contents[-1][1]]


# ── each kind: tap → answered; TYPED → answered (was lost); a message in between → the brain, the question still open ─────

class Payment(Base):
    def ask(self):
        run(GW.push_payment_question({"account_id": ACCOUNT}, {"id": "pay-1234567890", "read_back_sha256": "b" * 64, "payee": "Casa Lucio",
                                                              "read_back_lines": ["Casa Lucio asks a €20 deposit.", "Ask them for the payment link?"]}))
        self.assertEqual(self.pend()["kind"], "payment")

    def test_tap(self):
        self.ask()
        self.say("", payload=self.last_buttons()[0], text="Yes, ask them")
        self.assertIn("/api/booking/payments/pay-1234567890/approve", self.paths())
        self.assertEqual(self.seen, [])
        self.assertIsNone(self.st()["pending"])

    def test_typed_yes_after_a_message_in_between(self):
        self.ask()
        self.in_between()
        self.say("yes please")
        self.assertIn("/api/booking/payments/pay-1234567890/approve", self.paths())
        self.assertEqual(GW.api.calls[-1][3]["approval"], {"how": "whatsapp_text", "said": "yes please"})
        self.assertEqual(self.bodies()[-1], "I've asked Casa Lucio for their payment link.")
        self.assertEqual(self.seen, ["what's the weather in Madrid tomorrow"])

    def test_typed_no(self):
        self.ask()
        self.say("no")
        self.assertIn("I haven't asked Casa Lucio for anything", self.bodies()[-1])
        self.assertIsNone(self.st()["pending"])


class Mailbox(Base):
    def ask(self):
        run(MB._offer_on_whatsapp(ACCOUNT, [{"id": "find-123456789", "offer_sha256": "d" * 64,
                                             "offered_sentence": "Found in your Gmail: Casa Lucio, Saturday 21:00. Add it?"}]))
        self.assertEqual(self.pend()["kind"], "mailbox")

    def test_tap(self):
        self.ask()
        self.say("", payload=self.last_buttons()[0], text="Yes")
        self.assertEqual(GW.api.calls[-1][2:], ("/api/booking/mailbox/finds/find-123456789", {"offer_sha256": "d" * 64, "yes": True}))
        self.assertEqual(self.seen, [])

    def test_typed_yes_after_a_message_in_between(self):
        self.ask()
        self.in_between()
        self.say("yes")
        self.assertEqual(GW.api.calls[-1][2:], ("/api/booking/mailbox/finds/find-123456789", {"offer_sha256": "d" * 64, "yes": True}))
        self.assertEqual(self.bodies()[-1], "Added: Casa Lucio, Saturday 21:00.")
        self.assertIsNone(self.st()["pending"])

    def test_typed_no(self):
        self.ask()
        self.say("no thanks")
        self.assertEqual(GW.api.calls[-1][3], {"offer_sha256": "d" * 64, "yes": False})


class NoReplyCall(Base):
    B = {"id": "bk-12345678-0000", "venue": "Botavara Chamberí", "date": "2026-10-03", "time": "21:00", "party": 2, "read_id": "r-1"}
    READ = {"read_id": "r-1", "read": {"name": "Botavara Chamberí", "country": "ES", "facts": [{"kind": "phone"}]}}

    def ask(self):
        # Sasha 254 · the old flow's route is the booking rules' (agapi.booking_decide.legacy_decision): this person may call
        p = mock.patch("agapi.booking_decide.access_cached", lambda a: {"mode": "live", "calls": "on", "real_venue_sends": "on"})
        p.start()
        self.addCleanup(p.stop)
        run(GW.offer_no_reply_call(self.ch, self.B, self.READ))
        self.assertEqual(self.pend()["kind"], "no_reply_call")

    def test_tap_then_the_routes_own_question_tapped(self):
        self.ask()
        self.say("", payload=self.last_buttons()[0], text="Yes, prepare the call")
        # Sasha 254 · the rules decided the call: its OWN read-back and yes (no second "which way?" question — decide.ladder retired)
        self.assertEqual((self.pend()["kind"], self.pend()["rung"]), ("confirm", "call"))
        self.say("", payload=self.last_buttons()[0], text="Yes")
        self.assertIn("/api/booking/calls", self.paths())            # its read-back made and approved, the call placed (old _approve)
        self.assertTrue(any(p.endswith("/place") for p in self.paths()))
        self.assertEqual(self.seen, [])

    def test_typed_yes_after_a_message_in_between_and_typed_to_the_routes_question(self):
        self.ask()
        self.in_between()
        self.say("yes")                                               # was: → the brain → lost
        self.assertEqual((self.pend()["kind"], self.pend()["rung"]), ("confirm", "call"))   # Sasha 254 · the call's own read-back
        self.in_between()
        self.say("yes")
        self.assertTrue(any(p.endswith("/place") for p in self.paths()))
        self.assertEqual(self.seen, ["what's the weather in Madrid tomorrow"] * 2)

    def test_typed_no(self):
        self.ask()
        self.say("no")
        self.assertEqual(self.bodies()[-1], "OK — nothing more. I'll show you their reply if one arrives.")
        self.assertIsNone(self.st()["pending"])


class TheirPageSent(Base):
    URL = "https://www.thefork.es/restaurante/casa-lucio-r123"

    def send_page(self):
        r = run(GW.tap_platform(ACCOUNT, f"Their page: {self.URL}", self.URL, link_id="lnk-1", venue="Casa Lucio", when="Sat 21:00"))
        self.assertIn("sent", r)

    def tearDown(self):
        GW._TAPPED.discard(self.URL)
        super().tearDown()

    def test_typed_booked_after_a_message_in_between(self):
        self.send_page()
        self.assertEqual(self.pend()["kind"], "link")
        self.in_between()
        self.say("BOOKED")
        self.assertEqual(GW.api.calls[-1][2], "/api/booking/links/lnk-1/booked")
        self.assertIn("watch_gmail_confirmation", self.spawned)
        self.assertTrue(self.bodies()[-1].startswith("Noted — booked on their page, by you."))

    def test_the_page_sent_during_a_brain_turn_is_not_saved_over(self):
        async def brain(ch, body, payload, st, out, now, button_text="", voice_in=False):
            WA.set_agent_state(st, last_seen=now.isoformat())
            await GW.tap_platform(ACCOUNT, f"Their page: {self.URL}", self.URL, link_id="lnk-1", venue="Casa Lucio")   # as VN 647
            out.text("Sent you their page.")
            return "x"
        with mock.patch.object(WA, "agent_turn", brain):
            self.say("book Casa Lucio on TheFork for Saturday")
        self.assertEqual(self.pend()["kind"], "link")                 # was: overwritten by the turn's own save (row 98)
        self.say("booked")
        self.assertEqual(GW.api.calls[-1][2], "/api/booking/links/lnk-1/booked")


class Invitations(Base):
    def test_typed_days_then_a_typed_area_then_a_typed_pick(self):
        self.say("book dinner with Jon")                              # invitation words stay in front (unchanged)
        self.assertEqual(self.pend()["kind"], "invite_window")
        self.in_between()
        self.say("next week")                                         # was: → the brain → lost
        self.assertIsNone(self.pend().get("kind"))
        inv = next(iter(IV.STORE.rows.values()))
        self.assertIn(inv["code"], " ".join(self.bodies()))
        run(IV._tell_inviter(inv, 0))                                 # Jon picked a time; no area → "Where should I look?"
        self.assertEqual(self.pend()["kind"], "invite_where")
        self.in_between()
        self.say("Chamberí")
        self.assertIn("/api/booking/venues/find", self.paths())
        self.assertEqual((self.pend()["kind"], self.pend()["invite_code"]), ("cards", inv["code"]))
        self.in_between()
        self.say("the first one")
        self.assertIn("/api/booking/venues/read", self.paths())
        self.assertEqual(self.seen, ["what's the weather in Madrid tomorrow"] * 3)

    def test_card_tap(self):
        self.say("book dinner with Jon")
        self.say("next week")
        run(IV._tell_inviter(next(iter(IV.STORE.rows.values())), 0))
        self.say("in Chamberí")
        pick = next(b[1] for _, btns in GW.SENDER.contents for b in btns if b[1].startswith("pick:"))
        self.say("", payload=pick, text="Botavara")
        self.assertIn("/api/booking/venues/read", self.paths())
        self.assertEqual(self.seen, [])

    def test_a_question_is_never_taken_for_an_area(self):
        self.say("book dinner with Jon")
        self.say("next week")
        run(IV._tell_inviter(next(iter(IV.STORE.rows.values())), 0))
        self.say("what time is it in Tokyo?")
        self.assertEqual(self.seen[-1], "what time is it in Tokyo?")
        self.assertEqual(self.pend()["kind"], "invite_where")


# ── the slot itself ──────────────────────────────────────────────────────────────────────────────────────────────────────

class TheSlot(Base):
    def test_a_brain_turn_never_writes_pending(self):
        self.say("find me sushi in Chamberí")
        self.assertIsNone(self.st()["pending"])                       # was {"kind": "wa_agent", …} (G12)
        self.assertTrue(WA.agent_state(self.st())["last_seen"])

    def test_the_real_agent_turn_keeps_its_state_in_its_own_key(self):
        async def quiver(account, message, history, session, surface="s1"):
            yield {"type": "render", "kind": "keep_capture", "what": "passport"}
            yield {"type": "done", "text": "Send me the photo."}

        async def nothing(*a, **k):
            return None
        st = {"history": [], "pending": {"kind": "payment", "at": NOW.isoformat(), "id": "p", "sha": "s", "venue": "V"}}
        self.patches[0].stop()                                        # the REAL wa_agent.agent_turn this time
        try:
            with mock.patch("app.agent.sasha.turn_with_quiver", quiver), mock.patch("app.agent.sasha.over_budget", nothing), \
                    mock.patch("agapi.s2_memory.remember", nothing), mock.patch("agapi.s2_memory.recall", mock.AsyncMock(return_value={})):
                run(WA.agent_turn(self.ch, "save my passport", "", st, GW.Out(), NOW))
        finally:
            self.patches[0].start()
        self.assertEqual(st["pending"]["kind"], "payment")              # Sasha's question untouched
        self.assertEqual(st["agent"]["photo_for"]["kind"], "passport")  # the brain's state in its own key

    def test_the_old_wa_agent_pending_is_read_once(self):
        key = GW.wa_key(GUEST)
        GW.STORE.state[key] = {**GW.STORE.state[key], "pending": {"kind": "wa_agent", "photo_for": {"kind": "loyalty", "at": NOW.isoformat()},
                                                                   "last_seen": NOW.isoformat()}}
        st = self.st()
        self.assertIsNone(st["pending"])
        self.assertEqual(WA.agent_state(st)["photo_for"]["kind"], "loyalty")
        raw = {"pending": {"kind": "wa_agent", "dormant": "x"}}       # a state built by hand: agent_state migrates it too
        self.assertEqual(WA.agent_state(raw), {"dormant": "x"})
        self.assertIsNone(raw["pending"])
        run(GW.STORE.put_state(key, st))                              # saved back: the column carries it under "_agent"
        self.assertEqual(GW.STORE.state[key]["pending"]["_agent"]["photo_for"]["kind"], "loyalty")
        self.assertNotIn("kind", GW.STORE.state[key]["pending"])

    def test_a_question_and_the_brains_state_share_the_column_and_come_back_apart(self):
        run(GW.push_payment_question({"account_id": ACCOUNT}, {"id": "pay-1234567890", "read_back_sha256": "b" * 64, "payee": "Casa Lucio",
                                                              "read_back_lines": ["x", "Ask them?"]}))
        st = self.st()
        self.assertEqual(st["pending"]["kind"], "payment")
        self.assertNotIn("_agent", st["pending"])
        self.assertTrue(st["agent"]["last_seen"])

    def test_a_newer_question_of_the_brains_takes_a_bare_yes(self):
        st = {"pending": {"kind": "payment", "at": NOW.isoformat()}, "agent": {"asked": (NOW + GW.timedelta(minutes=1)).isoformat()}}
        self.assertFalse(GW.answers_sashas_question(st, "yes", "", NOW))
        st["agent"]["asked"] = (NOW - GW.timedelta(minutes=1)).isoformat()
        self.assertTrue(GW.answers_sashas_question(st, "yes", "", NOW))

    def test_only_sashas_own_kinds(self):
        for kind in ("product", "amb", "need"):
            self.assertFalse(GW.answers_sashas_question({"pending": {"kind": kind, "at": NOW.isoformat()}}, "yes", "", NOW), kind)


class ProductsSeeNoQuestionAfterABrainTurn(Base):
    """G12 · the brain no longer sits in `pending`, so a product sees Sasha's question only when she has one open
    (test_modes_cr15 AdIsOnlyAWholeWord, on the brain)."""

    def setUp(self):
        super().setUp()
        from tests import test_modes_cr15 as M
        from products import diligence as DG, store as ST
        self.saved2 = (ST.STORE, DG.HTTP)
        ST.STORE = ST.MemoryCaseStore()
        self.calls = []

        async def http(url, key, body):
            self.calls.append(url)
            return 200, M.LIVE
        DG.HTTP = http
        self.env2 = mock.patch.dict(os.environ, {"AD_PREVIEW_URL": "https://ad.test", "AD_PREVIEW_KEY": "k", "AD_PREVIEW_SAMPLE": ""})
        self.env2.start()

    def tearDown(self):
        from products import diligence as DG, store as ST
        ST.STORE, DG.HTTP = self.saved2
        self.env2.stop()
        super().tearDown()

    def test_a_bare_ad_after_a_brain_turn_is_ad_and_waits_while_sasha_asks(self):
        run(GW.push_payment_question({"account_id": ACCOUNT}, {"id": "pay-1234567890", "read_back_sha256": "b" * 64, "payee": "Casa Lucio",
                                                              "read_back_lines": ["x", "Ask them?"]}))
        self.say("ad check TotalEnergies in France")
        self.assertEqual(self.calls, [])                              # Sasha's own question is open: not the AD mode
        self.say("no")                                                # answered → closed
        self.say("ad check TotalEnergies in France")
        self.assertEqual(len(self.calls), 1)                          # was: never (the brain's state looked like a question)


if __name__ == "__main__":
    unittest.main()
