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


class CancelPageReachesTheChat(unittest.TestCase):
    """Live (scratch A, 2913e9a): after the yes she said Spotify's cancel page "is in the chat now" — and nothing was. It is now a card."""
    def test_the_yes_hands_over_the_page_as_a_card(self):
        from datetime import datetime, timedelta, timezone
        from agapi import s2_subscriptions as SUBS, v0 as API
        from app.agent import sasha
        SP = "https://www.spotify.com/account/subscription/"

        async def call(op, body, approval=None):
            if op == "sandbox.simulate_approval":
                return {"ok": True, "result": {"approval_id": "apv_1"}}
            if op == "subscriptions.cancel":
                return {"ok": True, "result": {"subscription": {"status": "handed_over", "merchant": "Spotify", "routes": [{"kind": "page", "value": SP}]},
                                               "outcome": {"target_words": {"text": "Spotify's own cancel page: you press cancel."}}}}
            raise AssertionError(op)
        key = f"{ACCOUNT}|sub_sp"
        with mock.patch.object(SUBS, "CALL", call), mock.patch.dict(SUBS._USERS, {ACCOUNT: "usr_" + "3" * 26}), \
                mock.patch.dict(SUBS._PENDING, {key: {"read_back_id": "rb_1", "route": "page", "at": 0}}), mock.patch.object(SUBS, "via", lambda: "sandbox"):
            ctx = API.Ctx(account=ACCOUNT, user_said="yes", surface="s2", started=datetime.now(timezone.utc) + timedelta(seconds=1))
            r = asyncio.run(SUBS.run_tool(ctx, "cancel_subscription", {"subscription_id": "sub_sp"}))
        self.assertEqual(r["result"]["render"], {"kind": "handover", "url": SP, "external": True})
        self.assertEqual(sasha.render("cancel_subscription", r["result"], {}), {"type": "render", "kind": "handover", "url": SP, "external": True})
        from booking_signer import wa_agent as WA
        out = _Out()
        WA.render({"kind": "handover", "url": SP, "external": True}, out, {}, None)
        self.assertEqual(out.sent, [f"Tap to finish: {SP}"])


class ListKeepsWhatIsStillPaid(unittest.TestCase):
    """Live (scratch A, 9028243): Spotify, its cancel page handed over, left the list while AgAPI's €67.03 still counted it; and /next's
    later plain call said 'From statement' for a list read from receipts."""
    def test_handed_over_stays_marked_and_the_source_is_remembered(self):
        from datetime import datetime, timezone
        from agapi import s2_subscriptions as SUBS, v0 as API
        rows = [{"subscription_id": "sub_nf", "merchant": "Netflix", "amount": {"amount_minor": 1399, "currency": "EUR"}, "cadence": "monthly",
                 "last_charge": "2026-10-03", "likely_unused": False, "why": [], "status": "active"},
                {"subscription_id": "sub_sp", "merchant": "Spotify", "amount": {"amount_minor": 1099, "currency": "EUR"}, "cadence": "monthly",
                 "last_charge": "2026-10-11", "likely_unused": False, "why": [], "status": "handed_over"},
                {"subscription_id": "sub_x", "merchant": "Gone", "amount": {"amount_minor": 500, "currency": "EUR"}, "cadence": "monthly",
                 "last_charge": "2026-09-01", "likely_unused": False, "why": [], "status": "cancelled"}]

        async def call(op, body, approval=None):
            if op == "users.register":
                return {"ok": True, "result": {"end_user_id": "usr_" + "4" * 26}}
            return {"ok": True, "result": {"subscriptions": rows, "monthly_total": [{"amount_minor": 2498, "currency": "EUR"}], "likely_unused": 0}}
        with mock.patch.object(SUBS, "CALL", call), mock.patch.dict(SUBS._USERS, {}, clear=True), mock.patch.dict(SUBS._SOURCE, {ACCOUNT: "receipts in your Gmail"}), \
                mock.patch.dict(SUBS._LAST, {}, clear=True):
            ctx = API.Ctx(account=ACCOUNT, user_said="", surface="s1", started=datetime.now(timezone.utc))
            r = asyncio.run(SUBS.run_tool(ctx, "find_subscriptions", {}))["result"]
        self.assertEqual([i["service"] for i in r["render"]["items"]], ["Netflix", "Spotify"])
        self.assertEqual(r["render"]["items"][1]["not_yet"], "cancel page handed over — not cancelled yet")
        self.assertEqual(r["render"]["source"], "receipts in your Gmail")
        self.assertIn("Spotify: EUR 10.99 a month (cancel page handed over — not cancelled yet)", r["say"])
        self.assertTrue(r["say"].startswith("From your receipts in your Gmail"))


if __name__ == "__main__":
    unittest.main()
