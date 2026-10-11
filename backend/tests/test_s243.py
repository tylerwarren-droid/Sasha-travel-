"""Sasha 243 · entry.check from the person's OWN Keep (242 found it couldn't see the passport saved on /keep): the passport's issuing
country — read from its mask, never the number — goes to AgAPI as passport_country; an AgAPI from before that input is asked as before.
And CR 84's subscriptions list drawn on WhatsApp as text + the /s2 link; Gmail by invitation includes the accounts listed."""
from __future__ import annotations

import asyncio
import os
import unittest
from unittest import mock

ACCOUNT = "7536a3f0-0000-4000-8000-000000000243"


class EntryCheckFromTheirKeep(unittest.TestCase):
    def _run(self, keep_items, agapi_knows_the_input=True):
        from agapi import s2_fine_print as FP, s2_keep as KEEP
        sent = []

        async def call(op, body, approval=None):
            sent.append((op, dict(body)))
            if op == "users.register":
                return {"ok": True, "result": {"end_user_id": "usr_" + "2" * 26}}
            if "passport_country" in body and not agapi_knows_the_input:
                return {"ok": False, "error": {"code": "invalid_input", "message": "passport_country: unexpected"}}
            pc = body.get("passport_country")
            if not pc:
                return {"ok": True, "result": {"passport": None, "destinations": [], "say": "I need your passport's country — add your passport to your Keep (a photo of it)."}}
            return {"ok": True, "result": {"passport": {"item_id": None, "masked": None, "country": pc, "from": "caller"},
                                           "destinations": [{"country": "GB", "verdict": "needed", "deadline": {"apply_by": "2026-10-28"}}],
                                           "say": "You need an electronic travel authorisation (ETA) (\"…\")."}}

        async def list_(account):
            return keep_items
        with mock.patch.object(FP, "CALL", call), mock.patch.dict(FP._USERS, {}, clear=True), mock.patch.object(KEEP, "list_", list_):
            ctx = type("C", (), {"account": ACCOUNT})()
            r = asyncio.run(FP.run_tool(ctx, "entry_documents", {"destinations": [{"country": "gb", "arrival_date": "2026-11-02"}]}))
        return r, [b for op, b in sent if op == "entry.check"]

    def test_the_eta_answer_without_asking_the_nationality(self):
        r, checks = self._run([{"type": "passport", "masked": "Passport ES ••••041", "item_id": "x"}])
        self.assertEqual(checks[0]["passport_country"], "ES")
        self.assertEqual(r["result"]["destinations"][0]["verdict"], "needed")
        self.assertIn("ETA", r["result"]["say"])
        self.assertEqual(r["result"]["passport"], "your passport (ES), from your Keep")
        self.assertNotIn("XA2420041", repr(checks) + repr(r))   # the country only, never the number
        self.assertEqual(set(checks[0]), {"end_user", "destinations", "passport_country"})

    def test_no_passport_in_the_keep_sends_nothing_and_still_asks(self):
        r, checks = self._run([{"type": "loyalty", "masked": "Iberia Plus ••••678"}])
        self.assertNotIn("passport_country", checks[0])
        self.assertIn("I need your passport's country", r["result"]["say"])

    def test_an_agapi_without_the_input_is_asked_as_before(self):
        r, checks = self._run([{"type": "passport", "masked": "Passport ES ••••041"}], agapi_knows_the_input=False)
        self.assertEqual(len(checks), 2)
        self.assertNotIn("passport_country", checks[1])
        self.assertTrue(r["ok"])


class _Out:
    def __init__(self):
        self.sent = []

    def text(self, t):
        self.sent.append(t)

    def ask(self, t, buttons):
        self.sent.append(t)


class SubscriptionsOnWhatsApp(unittest.TestCase):
    EV = {"type": "render", "kind": "subscriptions", "total": "EUR 67.03", "source": "receipts (a fake inbox — test mode)",
          "items": [{"service": "Netflix", "price": "EUR 13.99", "how_often": "monthly", "renews": "2026-11-03", "expected": False},
                    {"service": "Spotify", "price": "EUR 10.99", "how_often": "monthly", "renews": "2026-11-10", "expected": True},
                    {"service": "ChatGPT Plus", "price": "USD 20.00", "how_often": "unknown (the email doesn't say)", "renews": None}]}

    def test_text_and_link(self):
        from booking_signer import wa_agent as WA
        out = _Out()
        WA.render(self.EV, out, {}, None)
        t = out.sent[0]
        self.assertIn("*Your subscriptions*", t)
        self.assertIn("Netflix · EUR 13.99 a month · renews 2026-11-03", t)
        self.assertIn("Spotify · EUR 10.99 a month · renews 2026-11-10 (expected)", t)
        self.assertIn("ChatGPT Plus · USD 20.00", t)
        self.assertIn("About EUR 67.03 a month", t)
        self.assertIn("See the card: ", t)

    def test_drawn_once_a_turn(self):
        from booking_signer import wa_agent as WA
        self.assertEqual(len(WA.last_of_each_card([self.EV, dict(self.EV)])), 1)


class GmailByInvitation(unittest.TestCase):
    def test_a_listed_account_is_invited(self):
        from booking_signer import mailbox as MB
        jon = "4ff7c9c1-4215-46fd-a69f-c181d093db97"
        with mock.patch.dict(os.environ, {"FOUNDER_ACCOUNT_ID": "", "SASHA_GMAIL_ACCOUNTS": f" {jon} "}):
            self.assertTrue(MB.invited(jon))
            self.assertFalse(MB.invited(ACCOUNT))


if __name__ == "__main__":
    unittest.main()
