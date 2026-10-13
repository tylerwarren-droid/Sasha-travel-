"""CR 84 · /s2's subscription finder from Gmail RECEIPTS: its own consent sentence (said, then a yes in a later turn); ONE narrow search
(receipt subjects, 13 months); the emails go to AgAPI and are dropped; the list card; cancel the one named — email when it cancels by email,
else its own page handed over. Offline: a stand-in AgAPI and a stand-in Gmail.

    cd backend && python -m unittest tests.test_s2_subscriptions_cr84 -v
"""
from __future__ import annotations

import asyncio
import base64
import os
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

from agapi import s2_gmail_receipts as GR
from agapi import s2_subscriptions as SUBS
from agapi import v0 as API

ACCOUNT = "00000000-0000-4000-8000-000000000084"


def run(c):
    return asyncio.run(c)


def ctx(said="", ago=0):
    return API.Ctx(account=ACCOUNT, user_said=said, surface="s2", started=datetime.now(timezone.utc) + timedelta(seconds=ago))


def S(sid, merchant, minor, cadence, renews=None, basis=None, plan=None):
    return {"subscription_id": sid, "merchant": merchant, "amount": {"amount_minor": minor, "currency": "EUR"}, "cadence": cadence,
            "last_charge": "2026-10-03", "likely_unused": False, "why": [], "status": "active", "source": "email",
            **({"next_renewal": renews, "next_expected": renews, "next_basis": "stated in the email"} if renews and not basis else {}),
            **({"next_expected": renews, "next_basis": basis} if basis else {}), **({"service": plan} if plan else {})}


LIST = [S("sub_prime", "Amazon Prime", 4990, "yearly", "2027-03-14"), S("sub_fit", "FitBox Madrid", 3490, "monthly"),
        S("sub_nf", "Netflix", 1399, "monthly", "2026-11-03"),
        S("sub_sp", "Spotify", 1099, "monthly", "2026-11-10", "expected from the last charge — not stated in the email", "Spotify Premium Individual")]


class FakeAgAPI:
    def __init__(self):
        self.calls = []

    async def __call__(self, op, body, approval=None):
        self.calls.append((op, dict(body), approval))   # a copy: what was SENT
        if op == "users.register":
            return {"ok": True, "result": {"end_user_id": "usr_" + "1" * 26}}
        if op == "subscriptions.find":
            return {"ok": True, "result": {"subscriptions": LIST, "monthly_total": [{"amount_minor": 6404, "currency": "EUR"}], "likely_unused": 0,
                                           "note": "From their receipt emails", "emails": {"receipts_read": 8, "bodies_kept": 0}}}
        if op == "subscriptions.cancel_plan":
            routes = {"sub_sp": [{"kind": "page", "value": "https://www.spotify.com/account/subscription/"}],
                      "sub_fit": [{"kind": "email", "value": "bajas@fitbox-madrid.example"}]}[body["subscription_id"]]
            return {"ok": True, "result": {"merchant": "x", "routes": routes, "never": "never logs in"}}
        if op == "subscriptions.cancel":
            if not approval:
                line = {"page": "Here is Spotify's own cancel page: https://www.spotify.com/account/subscription/ — you open it and press cancel.",
                        "email": "Sasha emails bajas@fitbox-madrid.example — FitBox Madrid's cancellation address — asking them to cancel."}[body["route"]]
                return {"ok": False, "error": {"code": "approval_required", "details": {"read_back_id": "rb_9", "read_back": {"lines": ["Cancel …", line]}}}}
            raise AssertionError("no yes in these tests")
        raise AssertionError(op)


class GmailReceipts(unittest.TestCase):
    def setUp(self):
        self.agapi = FakeAgAPI()
        for p in (mock.patch.object(SUBS, "CALL", self.agapi), mock.patch.dict(SUBS._USERS, {}, clear=True), mock.patch.dict(SUBS._PENDING, {}, clear=True),
                  mock.patch.dict(SUBS._CONSENT_ASKED, {}, clear=True), mock.patch.dict(SUBS._CONSENTED, {}, clear=True), mock.patch.dict(SUBS._LAST, {}, clear=True)):
            p.start()
            self.addCleanup(p.stop)

    def finds(self):
        return [b for op, b, _ in self.agapi.calls if op == "subscriptions.find"]

    def test_connecting_is_the_consent_she_reads_at_once_and_says_so(self):   # Sasha 259 · moved (rule 0b): no question, one statement
        r = run(SUBS.run_tool(ctx(), "find_subscriptions", {"from_gmail": True}))
        self.assertNotEqual(r["result"].get("status"), "needs_consent")                        # never asked
        self.assertEqual(self.finds()[-1]["emails"]["consent"]["text_sha256"], GR.consent()["text_sha256"])   # the consent still goes with the read
        self.assertTrue(self.finds()[-1]["emails"]["sample"])                                   # no Gmail connected, sandbox: the fake inbox
        self.assertTrue(r["result"]["say"].startswith(SUBS.STATEMENT["gmail"] + " "))
        r["result"]["say"] = r["result"]["say"][len(SUBS.STATEMENT["gmail"]) + 1:]
        self.assertEqual(r["result"]["say"], "From your receipts (a fake inbox — test mode), you're paying for 4: Amazon Prime: EUR 49.90 a year, renews "
                         "2027-03-14; FitBox Madrid: EUR 34.90 a month; Netflix: EUR 13.99 a month, renews 2026-11-03; Spotify: EUR 10.99 a month, renews "
                         "2026-11-10 (expected — the email doesn't say). That's about EUR 64.04 a month.")
        card = r["result"]["render"]
        self.assertEqual(card["kind"], "subscriptions")
        self.assertEqual(card["items"][3], {"service": "Spotify", "price": "EUR 10.99", "how_often": "monthly", "renews": "2026-11-10", "expected": True,
                                            "subscription_id": "sub_sp"})

    def test_a_connected_gmail_is_searched_once_narrowly_and_the_emails_are_dropped(self):
        SUBS._CONSENTED[ACCOUNT] = {"version": "s2-subs-1"}
        mails = [{"message_id": "m1", "from": "Spotify <no-reply@spotify.com>", "subject": "Your Spotify Premium receipt", "date": "", "text": "Total: €10.99"}]
        with mock.patch.object(GR, "connected", mock.AsyncMock(return_value=True)), mock.patch.object(GR, "receipts", mock.AsyncMock(return_value=mails)):
            r = run(SUBS.run_tool(ctx(), "find_subscriptions", {"from_gmail": True}))
        self.assertEqual(r["result"]["render"]["source"], "receipts in your Gmail")
        self.assertEqual(self.finds()[-1]["emails"]["messages"], mails)                          # sent once to AgAPI (then dropped here)
        self.assertTrue(GR.QUERY.startswith("newer_than:400d subject:("))
        with mock.patch.dict(os.environ, {"SASHA_SUBSCRIPTIONS_VIA": "live"}), mock.patch.object(GR, "connected", mock.AsyncMock(return_value=False)):
            self.assertEqual(run(SUBS.run_tool(ctx(), "find_subscriptions", {"from_gmail": True}))["error"]["code"], "gmail_not_connected")

    def test_receipts_uses_only_the_one_search(self):
        from booking_signer import mailbox as MB
        seen = []

        async def http(method, url, token, params=None):
            seen.append((url, params))
            if url.endswith("/messages"):
                return 200, {"messages": [{"id": "a1"}]}
            body = base64.urlsafe_b64encode(b"<p>Total: 10,99 EUR. <a href=\"https://www.spotify.com/account/\">Manage</a></p>").decode()
            return 200, {"payload": {"mimeType": "text/html", "body": {"data": body}, "headers": [{"name": "From", "value": "Spotify <x@spotify.com>"},
                                                                                                  {"name": "Subject", "value": "Your receipt"}]}}

        class Store:
            async def get_link(self, account):
                return {"vault_item_id": "v1"}

        from booking_signer.vault import crypto as VCR

        async def use(account, item, purpose):
            assert purpose == "gmail_read"
            return "tok"
        with mock.patch.object(MB, "STORE", Store()), mock.patch.object(MB, "GMAIL_HTTP", http), mock.patch.object(VCR, "use_connection", use):
            out = run(GR.receipts(ACCOUNT))
        self.assertEqual(seen[0][1], {"q": GR.QUERY, "maxResults": GR.MAX})
        self.assertEqual(out[0]["subject"], "Your receipt")
        self.assertIn("Manage [https://www.spotify.com/account/]", out[0]["text"])               # a link's address after its words

    def test_cancel_the_one_named_by_its_own_route(self):
        run(SUBS.run_tool(ctx(), "find_subscriptions", {}))
        SUBS._LAST[ACCOUNT] = [SUBS._brief(s) for s in LIST]
        r = run(SUBS.run_tool(ctx(), "cancel_subscription", {"service": "spotify"}))
        self.assertEqual(r["result"]["status"], "awaiting_yes")
        self.assertIn("you open it and press cancel", r["result"]["read_back"][1])
        self.assertEqual([b for op, b, _ in self.agapi.calls if op == "subscriptions.cancel"][-1]["route"], "page")
        r = run(SUBS.run_tool(ctx(), "cancel_subscription", {"service": "FitBox"}))
        self.assertIn("bajas@fitbox-madrid.example", r["result"]["read_back"][1])
        self.assertEqual([b for op, b, _ in self.agapi.calls if op == "subscriptions.cancel"][-1]["route"], "email")
        self.assertEqual(run(SUBS.run_tool(ctx(), "cancel_subscription", {"service": "Disney"}))["error"]["code"], "which_subscription")

    def test_the_card_is_an_s2_kind(self):
        from app.agent import sasha
        self.assertIn("subscriptions", sasha.KINDS_S2_ONLY)
        ev = sasha.render("find_subscriptions", {"render": {"kind": "subscriptions", "items": []}}, {})
        self.assertEqual(ev, {"type": "render", "kind": "subscriptions", "items": []})
