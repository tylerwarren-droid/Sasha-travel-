"""Sasha 330 · "give me a button" (Tyler, 3 Nov 16:38) — the cancel read-back's [Yes, cancel it] [No, keep it], on /s2 and WhatsApp.

ROOT TEST (written first: docs/sasha/S-330-cancel-buttons.md)
  THE ONE PLACE a read-back gets its buttons is sasha.yes_buttons(tool, res): book (hold_venue / book_venue), pay (hold_booking) and
  cancel (cancel_venue) all take theirs from it; /s2 draws them with the ONE CallCard, WhatsApp with wa_agent._buttons (from the
  event's own choices). A tap → sasha.card_tap: ctx.idem = card_tap:<account>:<read_back_id>:<choice>, claimed once — the booking
  card's claim-once rule, for the cancel's Yes and No, from /s2 and from WhatsApp.
Offline: test_s329's fake AgAPI (CR 161's contract); nothing leaves the process.

    cd backend && python3 -m unittest tests.test_s330 -v
"""
from __future__ import annotations

import asyncio
import inspect
import json
import os
import pathlib
import re
import unittest
import uuid
from datetime import datetime, timezone
from unittest import mock

from agapi import v0 as V0, venue_submit as VS, venues as VN, yes_gate as YG
from app.agent import sasha as S, voice as V
from booking_signer import wa_agent as WA
from tests.test_s329 import ACCT, Base

run = asyncio.run
ROOT = pathlib.Path(__file__).resolve().parents[2]


def s2ctx(said: str) -> V0.Ctx:
    return V0.Ctx(account=ACCT, mode="test", user_said=said, session="sess-330", surface="s2")


def tap(choice: str, rid: str, surface: str = "s2") -> list:
    async def go():
        return [ev async for ev in S.card_tap(ACCT, "sess-330", surface, {"read_back_id": rid, "choice": choice},
                                              "Yes, cancel it" if choice == "cancel" else "No, keep it")]
    return run(go())


class Out:
    """WhatsApp's out (guest_whatsapp.Out's shape): what would be sent, in order."""
    def __init__(self):
        self.items = []

    def text(self, t):
        self.items.append(("text", t))

    def ask(self, body, buttons):
        self.items.append(("ask", body, list(buttons)))

    def pick(self, body, label, rows):
        self.items.append(("list", body, rows))

    def media(self, caption, url):
        self.items.append(("media", caption, url))


class Cancel(Base):
    def setUp(self):
        super().setUp()
        for d in (YG._RB, YG._APV):
            d.pop((ACCT, "cancel_venue"), None)
        self.mp = mock.patch("agapi.s2_memory.remember", mock.AsyncMock(return_value={}))
        self.mp.start()
        self.aid = self.booked()["act_id"]
        self.n = len(self.ag.calls)
        r = run(V0.call(s2ctx("cancel it"), "cancel_venue", {"act_id": self.aid, "idempotency_key": uuid.uuid4().hex}))
        self.assertTrue(r["ok"], r)
        self.rb = r["result"]
        self.ev = S.render("cancel_venue", self.rb, {})

    def tearDown(self):
        self.mp.stop()
        super().tearDown()

    def cancels(self):
        """The cancel's approvals AgAPI received (the tap, either kind, or an approved venue.cancel_booking)."""
        rid = self.rb["read_back_id"]
        return [(o, b) for o, b, a in self.ag.calls[self.n:]
                if (o == "approvals.in_app_tap" and b["read_back_id"] == rid) or (o == "venue.cancel_booking" and a)]


class TheS2Card(Cancel):
    def test_the_read_back_is_a_card_with_yes_and_no(self):
        print("\n── the cancel read-back's render event ──\n" + json.dumps(self.ev, ensure_ascii=False))
        self.assertEqual(self.ev["kind"], "read_back")
        self.assertEqual(self.ev["act"], "cancel")
        self.assertEqual(self.ev["ask"], "Cancel Taberna Sandbox, Fri 20 Nov 22:00, 2 people, ref SBX-ABC123?")
        self.assertEqual(self.ev["choices"], [{"title": "Yes, cancel it", "route": "cancel"}, {"title": "No, keep it", "route": "keep"}])
        self.assertEqual(self.ev["read_back_id"], VN._CANCEL[ACCT]["read_back_id"])
        self.assertEqual(self.cancels(), [])                                   # nothing pressed before the tap

    def test_tap_yes_cancels_once_and_a_second_tap_does_nothing(self):
        evs = tap("cancel", self.ev["read_back_id"])
        done = evs[-1]
        print("\n── S2 tap [Yes, cancel it] ──\n" + done["text"])
        self.assertTrue(done["text"].startswith("Cancelled — Taberna Sandbox, Fri 20 Nov 22:00, 2 people, ref SBX-ABC123."))
        self.assertEqual(done["tools"], [{"tool": "cancel_venue", "ok": True, "status": "cancelled"}])
        self.assertIn({"type": "trip_changed"}, evs)
        self.assertEqual(self.ag.acts[self.aid]["state"], "cancelled")
        self.assertEqual(len(self.cancels()), 1)                               # venue.cancel_booking, with the tap's approval, ONCE
        self.assertNotIn(ACCT, VN._CANCEL)
        self.assertNotIn((ACCT, "cancel_venue"), YG._RB)                       # CR 76's one-yes gate ran, and consumed the yes
        calls = len(self.ag.calls)
        again = tap("cancel", self.ev["read_back_id"])[-1]
        keep = tap("keep", self.ev["read_back_id"])[-1]
        print("── the same card tapped again ──\n" + again["text"])
        self.assertEqual((again["text"], keep["text"]), (V.CARD_ANSWERED, V.CARD_ANSWERED))
        self.assertEqual(len(self.ag.calls), calls)                            # AgAPI not called at all

    def test_a_tap_on_another_card_does_nothing(self):
        out = tap("cancel", "rb_not_this_one")[-1]
        self.assertEqual(out["text"], V.CARD_ANSWERED)
        self.assertEqual(self.cancels(), [])
        self.assertIn(ACCT, VN._CANCEL)                                        # the real card still answers

    def test_the_claim_is_card_taps(self):
        """Two taps at once (the read-back still held for both): the second hits card_tap's claim — nothing sent twice."""
        V0._CLAIMED.add(__import__("hashlib").sha256(f"card_tap:{ACCT}:{self.ev['read_back_id']}:cancel".encode()).hexdigest()[:40])
        out = tap("cancel", self.ev["read_back_id"])[-1]
        self.assertEqual(out["text"], V.CARD_ANSWERED)
        self.assertEqual(self.cancels(), [])

    def test_tap_no_keeps_it(self):
        out = tap("keep", self.ev["read_back_id"])[-1]
        self.assertEqual(out["text"], "Kept — nothing changed.")
        self.assertEqual(self.cancels(), [])
        self.assertNotIn(ACCT, VN._CANCEL)
        self.assertNotIn((ACCT, "cancel_venue"), YG._RB)                       # its one-yes read-back dropped too
        self.assertEqual(self.ag.acts[self.aid]["state"], "confirmed")

    def test_typed_yes_still_works(self):
        r = run(V0.call(s2ctx("Yes, cancel it"), "cancel_venue",
                        {"act_id": self.aid, "approval": {"said": "Yes, cancel it"}, "idempotency_key": uuid.uuid4().hex}))
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["result"]["status"], "cancelled")
        self.assertEqual(len(self.cancels()), 1)
        self.assertEqual(tap("cancel", self.ev["read_back_id"])[-1]["text"], V.CARD_ANSWERED)   # its card, after: nothing
        self.assertEqual(len(self.cancels()), 1)

    def test_typed_no_still_cancels_nothing(self):
        r = run(V0.call(s2ctx("No"), "cancel_venue", {"act_id": self.aid, "approval": {"said": "No"}, "idempotency_key": uuid.uuid4().hex}))
        self.assertEqual(r["error"]["code"], "no_explicit_yes")
        self.assertEqual(self.cancels(), [])


class TheWhatsAppCard(Cancel):
    """Booked in the app (test_s329's fixture); the cancel's card is tapped on WhatsApp: no in-app session, only the signed message."""

    def setUp(self):
        super().setUp()
        self.no_tap = VS.TAP.set(None)
        self.env = mock.patch.dict(os.environ, {"SASHA_AGAPI_TAP_SECRET": "test-only-secret"})
        self.env.start()
        self.ch = {"account_id": ACCT, "wa_id_sha256": "wa330"}

    def tearDown(self):
        self.env.stop()
        VS.TAP.reset(self.no_tap)
        super().tearDown()

    def wa_tap(self, payload, mid):
        tok = VS.WA.set({"wa_id": "15005550123", "message_id": mid})
        try:
            out, st = Out(), {}
            run(WA.agent_turn(self.ch, "", payload, st, out, datetime.now(timezone.utc), button_text=""))
            return out, st
        finally:
            VS.WA.reset(tok)

    def test_reply_buttons_come_from_the_cards_choices(self):
        out = Out()
        WA.render(self.ev, out, {}, datetime.now(timezone.utc))
        print("\n── WhatsApp ──\n" + json.dumps(out.items, ensure_ascii=False))
        kind, body, buttons = out.items[0]
        self.assertEqual(kind, "ask")
        self.assertIn("Cancel Taberna Sandbox, Fri 20 Nov 22:00, 2 people, ref SBX-ABC123?", body)
        rid = self.ev["read_back_id"]
        self.assertEqual(buttons, [("Yes, cancel it", f"card:{rid}:cancel"), ("No, keep it", f"card:{rid}:keep")])

    def test_tap_no_keeps_it_and_nothing_is_sent(self):
        out, st = self.wa_tap(f"card:{self.ev['read_back_id']}:keep", "SM1")
        print("\n── WhatsApp tap [No, keep it] ──\n" + json.dumps(out.items, ensure_ascii=False))
        self.assertEqual(out.items, [("text", "Kept — nothing changed.")])
        self.assertEqual(self.cancels(), [])
        self.assertNotIn(ACCT, VN._CANCEL)
        self.assertEqual(st["history"][-1], {"role": "assistant", "content": "Kept — nothing changed."})

    def test_tap_yes_cancels_once_then_a_second_tap_does_nothing(self):
        out, _ = self.wa_tap(f"card:{self.ev['read_back_id']}:cancel", "SM2")
        print("\n── WhatsApp tap [Yes, cancel it] ──\n" + json.dumps(out.items, ensure_ascii=False))
        self.assertTrue(out.items[0][1].startswith("Cancelled — Taberna Sandbox"))
        sent = self.cancels()
        self.assertEqual(len(sent), 1)
        self.assertEqual(sent[0][1]["session"]["kind"], "whatsapp")               # signed by this WhatsApp message
        n = len(self.ag.calls)
        again, _ = self.wa_tap(f"card:{self.ev['read_back_id']}:cancel", "SM3")
        self.assertEqual(again.items, [("text", V.CARD_ANSWERED)])
        self.assertEqual(len(self.ag.calls), n)                                   # no second AgAPI call

    def test_typed_yes_still_works_on_whatsapp(self):
        self.assertEqual(WA.message_of(ACCT, "", "yn:yes"), "Yes")                 # the old typed buttons are unchanged


class TheOnePlace(unittest.TestCase):
    """Every read-back that needs a yes — book, pay, cancel — gets its buttons from sasha.yes_buttons, and only from there."""

    BOOK_CALL = {"status": "awaiting_yes", "read_back": ["Call Casa Test for 2, Fri 21:00"], "ask": "Fill in their page or call them?",
                 "choices": [{"title": "Fill in their page", "route": "page"}, {"title": "Call them", "route": "call"}], "read_back_id": "rb_call"}
    BOOK_PLAIN = {"status": "awaiting_yes", "read_back": ["Casa Test, Fri 21:00, 2 people"], "ask": "Shall I send this to Casa Test?",
                  "read_back_id": "sha_plain"}
    PAY = {"read_back": ["Flights: …", "Total €1,234.00"], "read_back_sha256": "f" * 64, "total_eur": 1234.0}
    CANCEL = {"status": "awaiting_yes", "read_back": ["Kanoe cancels …"], "ask": "Cancel Casa Test, Fri 21:00, 2 people?", "read_back_id": "rb_cxl"}

    def test_book_pay_cancel_all_from_the_one_function(self):
        cases = [("hold_venue", self.BOOK_CALL), ("book_venue", self.BOOK_PLAIN), ("hold_booking", self.PAY), ("cancel_venue", self.CANCEL)]
        seen = []
        with mock.patch.object(S, "yes_buttons", wraps=S.yes_buttons) as one:
            for tool, res in cases:
                ev = S.render(tool, res, {})
                want = S.yes_buttons(tool, res)
                self.assertTrue(want.get("choices") and want.get("read_back_id"), tool)
                self.assertEqual({k: ev[k] for k in ("ask", "choices", "read_back_id")}, want, tool)
                seen.append((tool, [c["route"] for c in ev["choices"]]))
        self.assertEqual({c.args[0] for c in one.call_args_list}, {t for t, _ in cases})
        print("\n── the one place ──\n" + "\n".join(f"{t}: {r}" for t, r in seen))
        self.assertEqual(dict(seen), {"hold_venue": ["page", "call"], "book_venue": ["say:Yes, book it", "say:No"],
                                      "hold_booking": ["say:Yes, book it", "say:No"], "cancel_venue": ["cancel", "keep"]})

    def test_pay_yes_is_the_persons_words(self):
        """book()'s yes must be their words: the pay card's Yes SENDS "Yes, book it", which yes_to_book accepts and the gate binds."""
        yes = next(c for c in S.yes_buttons("hold_booking", self.PAY)["choices"] if c["route"].startswith("say:Yes"))
        self.assertTrue(V0.yes_to_book(yes["route"][4:]))
        self.assertFalse(V0.yes_to_book("Yes, cancel it"))
        self.assertTrue(V0.yes_to_cancel("Yes, cancel it"))

    def test_no_second_button_set(self):
        src = inspect.getsource(S.render)
        self.assertEqual(len(re.findall(r'"choices":', src)), 0)                                  # render builds no choices itself
        self.assertEqual(src.count("yes_buttons(tool, res)"), 3)                                  # book, cancel, the generic read-back (pay)
        app = (ROOT / "frontend/app/s2/S2App.tsx").read_text()
        self.assertEqual(len(re.findall(r"function \w*Card\(\{ c, tap \}", app)), 2)             # CallCard + the no-answer card, as before
        self.assertIn("if (c.k === 'read_back' && c.choices && c.choices.length && c.read_back_id) return <CallCard", app)
        self.assertIn("const YES = new Set(['call', 'send', 'cancel'])", app)
        wa = inspect.getsource(WA._read_back)
        self.assertNotIn('"yn:yes"', wa)                                                           # drawn by _buttons, from choices
        self.assertNotIn("CANCEL_CHOICES", inspect.getsource(WA._buttons))                         # never its own copy of the words


if __name__ == "__main__":
    unittest.main()
