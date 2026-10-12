"""CR 86 · OUTLOOK / MICROSOFT 365 for the subscription finder: Microsoft's sign-in (delegated Mail.Read, read-only) sealed in the vault
like Gmail's, used only by outlook_read; ONE narrow Graph search; the chat says Outlook's own consent sentence and looks only after a
yes in a later turn; test mode reads Outlook's own fake inbox. Microsoft and AgAPI are faked — no test reads mail.

    cd backend && python -m unittest tests.test_outlook_cr86 -v
"""
from __future__ import annotations

import json
import os
from datetime import date
from unittest import mock

from agapi import s2_outlook_receipts as OR
from agapi import s2_subscriptions as SUBS
from booking_signer import calendar_sync as CS, outlook as OL
from booking_signer.vault import crypto as VC
from tests import test_calendar_s79 as TC
from tests.test_s2_subscriptions_cr84 import ACCOUNT, FakeAgAPI, ctx, run

MS_ENV = {"SASHA_MS_CLIENT_ID": "ms-cid", "SASHA_MS_CLIENT_SECRET": "ms-secret", "SASHA_MS_REDIRECT": "https://api.test/api/booking/outlook/callback"}


def app_for(account):
    from fastapi import FastAPI, Request
    from fastapi.testclient import TestClient
    app = FastAPI()

    @app.middleware("http")
    async def who(request: Request, call_next):
        request.state.account = account
        return await call_next(request)
    app.include_router(OL.router)
    return TestClient(app)


class Connect(TC.Base):
    def setUp(self):
        super().setUp()
        self.ms = mock.patch.dict(os.environ, {**MS_ENV, "SASHA_OUTLOOK_ACCOUNTS": TC.ACCOUNT})
        self.ms.start()
        self.addCleanup(self.ms.stop)

    def test_consent_ticked_then_microsofts_sign_in_read_only(self):
        c = app_for(TC.ACCOUNT)
        v = c.get("/outlook").json()
        self.assertEqual((v["configured"], v["invited"], v["connected"]), (True, True, False))
        self.assertEqual(c.post("/outlook/connect", json={}).status_code, 422)                       # the sentence must be ticked
        url = c.post("/outlook/connect", json={"consent_version": v["consent"]["version"], "consent_sha256": v["consent"]["sha256"]}).json()["url"]
        self.assertTrue(url.startswith("https://login.microsoftonline.com/organizations/oauth2/v2.0/authorize?"))
        self.assertIn("scope=offline_access+https%3A%2F%2Fgraph.microsoft.com%2FMail.Read", url)
        self.assertNotIn("ReadWrite", url)
        self.assertNotIn("Send", url)
        self.assertEqual(app_for(TC.OTHER).post("/outlook/connect", json={}).json()["rule"], "outlook_by_invitation")

    def test_the_callback_seals_the_token_and_only_outlook_read_may_use_it(self):
        sent = []

        async def ms(method, url, data=None):
            sent.append((url, dict(data or {})))
            return 200, {"access_token": "eyJ.access", "refresh_token": "M.R3-refresh-SECRET", "scope": "Mail.Read offline_access"}
        with mock.patch.object(OL, "MS_HTTP", ms):
            r = app_for(TC.ACCOUNT).get(f"/outlook/callback?state={CS.make_state(TC.ACCOUNT, 'v1', product='outlook')}&code=abc",
                                        follow_redirects=False)
        self.assertEqual(r.status_code, 303)
        self.assertTrue(r.headers["location"].endswith("/you?outlook=connected#outlook"))
        self.assertEqual(sent[0][1]["grant_type"], "authorization_code")
        lk = run(OL.link(TC.ACCOUNT))
        self.assertEqual((lk["provider"], lk["label"]), ("microsoft.com", "Outlook (read-only)"))
        self.assertNotIn("refresh-SECRET", json.dumps(VC.STORE.items, default=str))                  # sealed, never in the clear

        async def refresh(tok):
            assert tok == "M.R3-refresh-SECRET"
            return {"access_token": "eyJ.graph", "refresh_token": "M.R3-rotated-SECRET"}
        with mock.patch.object(VC, "MICROSOFT_REFRESH", refresh):
            self.assertEqual(run(VC.use_connection(TC.ACCOUNT, lk["id"], purpose="outlook_read")), "eyJ.graph")
            with self.assertRaises(VC.UseRefused):
                run(VC.use_connection(TC.ACCOUNT, lk["id"], purpose="gmail_read"))                    # Google's purposes never use it

        async def rotated(tok):
            assert tok == "M.R3-rotated-SECRET"                                                        # Microsoft's rotated token was kept
            return {"access_token": "eyJ.graph2"}
        with mock.patch.object(VC, "MICROSOFT_REFRESH", rotated):
            self.assertEqual(run(VC.use_connection(TC.ACCOUNT, lk["id"], purpose="outlook_read")), "eyJ.graph2")
        r = app_for(TC.ACCOUNT).delete("/outlook").json()
        self.assertTrue(r["disconnected"])
        self.assertIn("myapps.microsoft.com", r["at_microsoft"])
        self.assertIsNone(run(OL.link(TC.ACCOUNT)))

    def test_a_gmail_state_never_connects_outlook(self):
        r = app_for(TC.ACCOUNT).get(f"/outlook/callback?state={CS.make_state(TC.ACCOUNT, 'v1', product='gmail')}&code=x")
        self.assertEqual((r.status_code, r.json()["rule"]), (400, "state_invalid"))


class Receipts(TC.Base):
    def test_one_narrow_graph_search_and_the_text_only(self):
        self.assertTrue(OR.query(date(2026, 10, 11)).startswith("received>=2025-09-06 AND (subject:receipt OR subject:invoice"))
        seen = []

        async def graph(url, token, params=None):
            seen.append((url, params))
            return 200, {"value": [{"id": "AAMk1", "subject": "Your LinkedIn Premium receipt", "receivedDateTime": "2026-09-21T08:00:00Z",
                                    "from": {"emailAddress": {"name": "LinkedIn", "address": "billing@linkedin.com"}},
                                    "body": {"contentType": "html", "content": "<p>Amount: €59.99 <a href=\"https://www.linkedin.com/premium/manage/\">Manage</a></p>"}}]}
        with mock.patch.object(OR, "GRAPH_HTTP", graph), mock.patch.object(OL, "link", mock.AsyncMock(return_value={"id": "i1"})), \
                mock.patch.object(VC, "use_connection", mock.AsyncMock(return_value="eyJ")) as use:
            out = run(OR.receipts(ACCOUNT))
        self.assertEqual(use.await_args.kwargs["purpose"], "outlook_read")
        self.assertEqual(len(seen), 1)                                                                   # ONE search, nothing else listed
        self.assertEqual(seen[0][0], "https://graph.microsoft.com/v1.0/me/messages")
        self.assertEqual(seen[0][1]["$search"], f'"{OR.query()}"')
        self.assertEqual(out[0]["from"], "LinkedIn <billing@linkedin.com>")
        self.assertIn("Manage [https://www.linkedin.com/premium/manage/]", out[0]["text"])


class Chat(TC.Base):
    def setUp(self):
        super().setUp()
        self.agapi = FakeAgAPI()
        for p in (mock.patch.object(SUBS, "CALL", self.agapi), mock.patch.dict(SUBS._USERS, {}, clear=True), mock.patch.dict(SUBS._PENDING, {}, clear=True),
                  mock.patch.dict(SUBS._CONSENT_ASKED, {}, clear=True), mock.patch.dict(SUBS._CONSENTED, {}, clear=True),
                  mock.patch.dict(SUBS._LAST, {}, clear=True), mock.patch.dict(SUBS._SOURCE, {}, clear=True)):
            p.start()
            self.addCleanup(p.stop)

    def finds(self):
        return [b for op, b, _ in self.agapi.calls if op == "subscriptions.find"]

    def test_outlooks_own_sentence_first_then_its_fake_inbox_in_test_mode(self):
        r = run(SUBS.run_tool(ctx(), "find_subscriptions", {"from_outlook": True}))
        self.assertEqual((r["result"]["status"], r["result"]["ask"]), ("needs_consent", OR.CONSENT))
        self.assertIn("Outlook", OR.CONSENT)
        self.assertEqual(self.finds(), [])
        r = run(SUBS.run_tool(ctx("yes", ago=5), "find_subscriptions", {"from_outlook": True, "consent_yes": True}))
        sent = self.finds()[-1]["emails"]
        self.assertEqual((sent["sample"], sent["provider"], sent["consent"]["text_sha256"]), (True, "outlook", OR.consent()["text_sha256"]))
        self.assertTrue(r["result"]["say"].startswith("From your receipts (a fake Outlook inbox — test mode), you're paying for 4:"))
        self.assertEqual(r["result"]["render"]["source"], "receipts (a fake Outlook inbox — test mode)")

    def test_a_gmail_yes_is_not_an_outlook_yes(self):
        SUBS._CONSENTED[ACCOUNT] = {"version": "s2-subs-1"}
        r = run(SUBS.run_tool(ctx(), "find_subscriptions", {"from_outlook": True}))
        self.assertEqual(r["result"]["status"], "needs_consent")

    def test_asked_for_gmail_with_only_outlook_connected_reads_outlook(self):
        SUBS._CONSENTED[ACCOUNT + "|outlook"] = {"version": "s2-outlook-1"}
        msgs = [{"message_id": "AAMk1", "from": "Zoom <billing@zoom.us>", "subject": "Zoom Workplace Pro - payment receipt", "date": "", "text": "Total paid: €13.99"}]
        with mock.patch("agapi.s2_gmail_receipts.connected", mock.AsyncMock(return_value=False)), \
                mock.patch.object(OR, "connected", mock.AsyncMock(return_value=True)), mock.patch.object(OR, "receipts", mock.AsyncMock(return_value=msgs)):
            r = run(SUBS.run_tool(ctx(), "find_subscriptions", {"from_gmail": True}))
        self.assertEqual(r["result"]["render"]["source"], "receipts in your Outlook")
        self.assertEqual(self.finds()[-1]["emails"]["messages"], msgs)
        with mock.patch.dict(os.environ, {"SASHA_SUBSCRIPTIONS_VIA": "live"}), mock.patch.object(OR, "connected", mock.AsyncMock(return_value=False)):
            self.assertEqual(run(SUBS.run_tool(ctx(), "find_subscriptions", {"from_outlook": True}))["error"]["code"], "outlook_not_connected")
