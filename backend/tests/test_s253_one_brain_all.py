"""Sasha 253 · item 5 — ONE BRAIN FOR EVERYONE on WhatsApp, the old flow retired (Tyler, mailbox 807/809). The gate's check
(scripts/one_truth_suite.py T25):

  · every LINKED account's text, button, media and empty message reaches the brain (wa_agent.agent_turn) — no env switch:
    SASHA_WA_BRAIN and its agent_for list are gone, and the old scope gate (_new_request) is never the answer;
  · an UNLINKED number gets ONE short line — link this number once at /you — at most every ten minutes, only its hash and the
    time kept, and NO guest account is created (Sasha 153's automatic guest is retired);
  · IN FRONT of the brain, unchanged: STOP / START, STOP REMINDERS / YES REMINDERS, the product spaces by keyword, invitations,
    LINK codes, Sasha's own open questions (the G3 resolver), and — until Tyler answers G11 — the three demos' entry points.

Offline: the brain is stood in at wa_agent.agent_turn; the stores are memory stores; no network, no model, no Twilio.

    cd backend && python -m unittest tests.test_s253_one_brain_all -v
"""
from __future__ import annotations

import inspect
import json
import os
import pathlib
import unittest
from datetime import timedelta
from unittest import mock

from booking_signer import guest_accounts as GA, guest_whatsapp as GW, invitations as IV, proactive as PR, wa_agent as WA
from products import store as ST
from tests import test_guest_whatsapp_s75 as TG

run, ACCOUNT, GUEST, NOW, SANDBOX = TG.run, TG.ACCOUNT, TG.GUEST, TG.NOW, TG.SANDBOX
OTHER_ACCOUNT, OTHER = "33333333-3333-4333-8333-333333333333", "+447700900456"
BACKEND = pathlib.Path(__file__).resolve().parents[1]


class Base(TG.Base):
    def setUp(self):
        super().setUp()
        os.environ.pop("SASHA_WA_BRAIN", None)   # (mock.patch.dict in TG.Base restores the environment afterwards)
        TG.stand_in_brain(self)
        self.old = mock.patch.object(GW, "_new_request", mock.AsyncMock(side_effect=AssertionError("the old scope gate ran")))
        self.old.start()
        self.addCleanup(self.old.stop)
        self.saved = (ST.STORE, IV.STORE, PR.STORE)
        ST.STORE, IV.STORE, PR.STORE = ST.MemoryCaseStore(), IV.MemoryInviteStore(), PR.MemoryProactiveStore()
        self.addCleanup(self._restore)

    def _restore(self):
        ST.STORE, IV.STORE, PR.STORE = self.saved

    def link_other(self):
        run(GW.STORE.link({"account_id": OTHER_ACCOUNT, "wa_id_sha256": GW.wa_key(OTHER), "number_e164": OTHER, "linked_at": NOW,
                           "consent_at": NOW, "consent_wording_version": "v3", "consent_text_sha256": GW.consent()["sha256"]}))
        return run(GW.STORE.channel_for(GW.wa_key(OTHER)))

    def turn(self, ch, number, **p):
        return run(GW.turn(ch, SANDBOX, {"From": f"whatsapp:{number}", "To": f"whatsapp:{SANDBOX}", **p}))


# ── no switch: every linked account, every kind of message ────────────────────────────────────────────────────────────────

class EveryAccountEveryMessage(Base):
    def test_text_button_media_and_empty_reach_the_brain_for_every_account(self):
        for ch, number in ((self.link(), GUEST), (self.link_other(), OTHER)):
            self.brain_saw.clear()
            self.turn(ch, number, Body="dinner for 2 in Chamberí on Saturday at 9")
            self.turn(ch, number, Body="", ButtonPayload="yn:yes", ButtonText="Yes")
            self.turn(ch, number, Body="", NumMedia="1", MediaContentType0="application/pdf", MediaUrl0="https://x.test/a.pdf")
            self.turn(ch, number, Body="")
            self.assertEqual(self.brain_saw, ["dinner for 2 in Chamberí on Saturday at 9", "yn:yes",
                                              "[they sent a file (application/pdf) with no words]", "[an empty message]"], number)
            self.assertNotIn(GW.HELP, self.bodies())                          # the old HELP text never answers

    def test_an_old_flows_button_with_nothing_waiting_goes_to_the_brain(self):
        self.link()
        self.say("", payload="pick:a1b2c3:0", text="Casa Lucio")
        self.assertEqual(self.brain_saw, ["pick:a1b2c3:0"])

    def test_the_switch_is_gone(self):
        self.assertFalse(hasattr(WA, "on") or hasattr(WA, "mode"))
        for d in ("booking_signer", "agapi", "app", "products"):
            for f in (BACKEND / d).rglob("*.py"):
                src = f.read_text(encoding="utf-8")
                self.assertNotIn('getenv("SASHA_WA_BRAIN"', src, str(f))
                self.assertNotIn("WA.on(", src, str(f))
        turn_src = inspect.getsource(GW.turn)
        self.assertNotIn("_new_request(", turn_src)                           # no WhatsApp message reaches the old scope gate


# ── an unlinked number: one /you line, no guest account ───────────────────────────────────────────────────────────────────

class Unlinked(Base):
    def dispatch(self, sid, body, sender="+34600111222"):
        async def no_venue(number):
            return False
        return run(GW.dispatch({"MessageSid": sid, "From": f"whatsapp:{sender}", "To": f"whatsapp:{SANDBOX}", "Body": body}, no_venue))

    def test_one_line_to_link_at_you_and_no_guest_account(self):
        made = mock.AsyncMock(return_value=({"account_id": "g-wa"}, None))
        with mock.patch.dict(os.environ, {"SASHA_AUTO_GUESTS": "1"}), mock.patch.object(GA, "create_guest", made):
            r = self.dispatch("SM1", "spa in Madrid")
            again = self.dispatch("SM2", "hello?")
            self.now = NOW + timedelta(minutes=11)
            later = self.dispatch("SM3", "anyone?")
        self.assertIn("Sasha by Kanoe. To use me on WhatsApp, link this number once at https://sasha.test/you#whatsapp — it takes a "
                      "minute.", r)
        self.assertEqual(r.count("<Message>"), 1)                              # ONE line
        self.assertEqual(again, "")                                            # not again within ten minutes
        self.assertEqual(later.count("<Message>"), 1)                          # then once more
        made.assert_not_awaited()                                              # never an automatic guest account
        self.assertIsNone(run(GW.STORE.channel_for(GW.wa_key("+34600111222"))))   # nothing linked
        self.assertEqual(self.brain_saw, [])                                   # never the brain, never the old flow
        kept = json.dumps(GW.STORE.state, default=str)
        self.assertNotIn("600111222", kept)                                    # only the hash …
        self.assertNotIn("spa in Madrid", kept)                                # … and the time

    def test_a_link_code_still_links(self):
        c = GW.consent()
        run(GW.STORE.put_code({"code": "123456", "account_id": ACCOUNT, "consent_at": NOW, "consent_wording_version": "v3",
                               "consent_text_sha256": c["sha256"], "created_at": NOW}))
        r = self.dispatch("SM4", "LINK 123456", sender=GUEST)
        self.assertIn("Linked.", r)
        self.assertEqual(run(GW.STORE.channel_for(GW.wa_key(GUEST)))["account_id"], ACCOUNT)

    def test_an_invitee_code_still_reaches_the_invitation(self):
        with mock.patch.object(IV, "on_invite_message", mock.AsyncMock(return_value="You're in.")) as inv:
            r = self.dispatch("SM5", "INVITE ABCD2345")
        inv.assert_awaited()
        self.assertIn("You're in.", r)


# ── in front of the brain, unchanged ───────────────────────────────────────────────────────────────────────────────────────

class InFront(Base):
    def setUp(self):
        super().setUp()
        self.link()
        run(GW.STORE.put_state(GW.wa_key(GUEST), {"history": [], "pending": None, "last_inbound_at": NOW, "link_tries": []}))

    def test_stop_and_start(self):
        self.say("STOP")
        self.say("dinner for 2 tomorrow")
        self.say("START")
        self.assertEqual(self.bodies(), [GW.STOPPED, GW.STARTED])
        self.assertEqual(self.brain_saw, [])

    def test_the_reminders_words(self):
        self.say("STOP REMINDERS")
        self.say("YES REMINDERS")
        self.assertTrue(self.bodies()[0].startswith("OK — no more reminders."))
        self.assertTrue(self.bodies()[1].startswith("Done — reminders are on"))
        self.assertEqual(self.brain_saw, [])

    def test_a_space_by_its_keyword(self):
        self.say("campus")
        self.assertIn("CampusMe", "\n".join(self.bodies() + [b for b, _ in GW.SENDER.contents]))
        self.assertEqual(self.brain_saw, [])

    def test_an_invitation_request_goes_to_its_own_handler(self):
        with mock.patch.object(GW, "_invite", mock.AsyncMock()) as inv:
            self.say("book dinner with Jon this week")
        inv.assert_awaited()
        self.assertEqual(inv.await_args.args[1]["invitee"], "Jon")
        self.assertEqual(self.brain_saw, [])

    def test_sashas_own_question_is_answered_by_the_code_that_asked_it(self):   # the G3 resolver
        st = run(GW.STORE.get_state(GW.wa_key(GUEST)))
        st["pending"] = {"kind": "payment", "at": NOW.isoformat(), "id": "pay-1", "sha": "p" * 64, "venue": "Botavara"}
        run(GW.STORE.put_state(GW.wa_key(GUEST), st))
        with mock.patch.object(GW, "_answer_pending", mock.AsyncMock(return_value=True)) as ap:
            self.say("yes")
        ap.assert_awaited()
        self.assertEqual(self.brain_saw, [])

    def test_the_three_demos_are_retired(self):   # Sasha 254 · Tyler row 817: their words are ordinary messages for the brain
        for words in ("dinner and a massage in Madrid on Tuesday", "book a massage with my spa membership on Friday at 18:00",
                      "reorder my usual from Kanoe Demo Market"):
            self.say(words)
        self.assertEqual(len(self.brain_saw), 3)
        self.assertFalse(hasattr(GW, "DEMO_STARTS"))


if __name__ == "__main__":
    unittest.main()
