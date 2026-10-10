"""CR 74 · S2's fine print — /s2 only. Offline: a scripted model and a stand-in AgAPI (no call leaves a test).

    cd backend && python -m unittest tests.test_s2_fine_print -v
"""
from __future__ import annotations

import asyncio
import base64
import json
import unittest
from unittest import mock

from agapi import s2_fine_print as FP
from agapi import v0 as API
from app.agent.fakes import Block, client

ACCOUNT = "00000000-0000-4000-8000-000000000074"
CARDS = [{"item_id": "kpi_" + "1" * 26, "masked": "Example Bank Travel Visa · Visa", "issuer": "Example Bank", "product": "Example Bank Travel Visa",
          "network": "visa", "terms": {"product_id": "cpr_" + "1" * 26}, "status": "terms read 2026-10-10"},
         {"item_id": "kpi_" + "2" * 26, "masked": "Example Bank Everyday Mastercard · Mastercard", "issuer": "Example Bank",
          "product": "Example Bank Everyday Mastercard", "network": "mastercard", "terms": {"product_id": "cpr_" + "2" * 26}, "status": "terms read 2026-10-10"}]
ANSWER = ("Your Example Bank Travel Visa's terms (read 2026-10-10) say: \"Excluded countries: Ireland, Israel, Jamaica.\" So: no, as the terms "
          "state it. Source: https://agapi-sandbox-production.up.railway.app/fixtures/cards/example-bank-travel-visa/guide-to-benefits.pdf.")


def run(c):
    return asyncio.run(c)


class FakeAgAPI:
    """AgAPI's answers, in its real shapes (the deployed sandbox's cards.* on 10 Oct)."""

    def __init__(self, cards=CARDS):
        self.calls, self.cards = [], cards

    async def __call__(self, op, body):
        self.calls.append((op, body))
        if op == "users.register":
            return {"ok": True, "result": {"end_user_id": "usr_" + "0" * 26}}
        if op == "cards.mine":
            return {"ok": True, "result": {"cards": self.cards}}
        if op == "cards.intake":
            return {"ok": True, "result": {"card": {"issuer": "Example Bank", "product": "Example Bank Travel Visa", "network": "visa"}, "saved": True,
                                           "masked": "Example Bank Travel Visa · Visa", "terms": {"product_id": "cpr_" + "1" * 26},
                                           "note": "Only the card's product was kept — no number, not even the last four digits. The image wasn't kept."}}
        if op == "keep.put":
            if any(ch.isdigit() for ch in body["value"]["product"]):
                return {"ok": False, "error": {"code": "invalid_input", "details": {"rule": "never_card"}}}
            return {"ok": True, "result": {"masked": f"{body['value']['product']} · Visa"}}
        if op == "cards.ask":
            return {"ok": True, "result": {"card": "Example Bank Travel Visa", "answer": "no", "text": ANSWER,
                                           "quotes": [{"source_url": "https://agapi-sandbox-production.up.railway.app/fixtures/cards/example-bank-travel-visa/guide-to-benefits.pdf"}]}}
        if op == "cards.which":
            return {"ok": True, "result": {"framing": "Information from your cards' own terms. You decide.", "net_view": "Travel: FX ≈ USD 0.00",
                                           "cards": [{"card": "Example Bank Travel Visa", "reasons": [{"text": "FX fee 0% ≈ USD 0.00"}]}], "skipped": []}}
        raise AssertionError(op)


class Ctx:
    def __init__(self, account=ACCOUNT):
        self.account = account


class FinePrint(unittest.TestCase):
    def setUp(self):
        self.agapi = FakeAgAPI()
        for p in (mock.patch.object(FP, "CALL", self.agapi), mock.patch.dict(FP._USERS, {}, clear=True), mock.patch.dict(FP._IMAGES, {}, clear=True)):
            p.start()
            self.addCleanup(p.stop)

    def test_card_cover_says_agapis_quoted_answer_as_given(self):
        r = run(FP.run_tool(Ctx(), "card_cover", {"question": "Can I rent a car in Ireland on it?", "card": "travel visa"}))
        self.assertEqual((r["result"]["say"], r["result"]["answer"]), (ANSWER, "no"))
        self.assertEqual(self.agapi.calls[-1], ("cards.ask", {"end_user": "usr_" + "0" * 26, "card_item_id": "kpi_" + "1" * 26,
                                                             "question": "Can I rent a car in Ireland on it?"}))
        self.assertIn("Never add cover the quotes don't state", r["result"]["how"])

    def test_two_cards_and_no_name_asks_which_never_guesses(self):
        r = run(FP.run_tool(Ctx(), "card_cover", {"question": "Does it cover baggage?"}))
        self.assertEqual(r["result"]["answer"], "which_card")
        self.assertFalse(any(op == "cards.ask" for op, _ in self.agapi.calls))

    def test_add_a_card_by_photo_read_once_or_by_name_never_digits(self):
        ref = FP.keep_image(ACCOUNT, b"\x89PNG fake", "image/png")
        self.assertEqual(run(FP.run_tool(Ctx("someone-else"), "add_card", {"card_image_ref": ref}))["error"]["code"], "image_unknown")
        ref = FP.keep_image(ACCOUNT, b"\x89PNG fake", "image/png")
        r = run(FP.run_tool(Ctx(), "add_card", {"card_image_ref": ref}))
        self.assertEqual(r["result"]["added"], "Example Bank Travel Visa · Visa")
        sent = [b for op, b in self.agapi.calls if op == "cards.intake"][-1]
        self.assertEqual(base64.b64decode(sent["image"]["content_base64"]), b"\x89PNG fake")
        self.assertNotIn(ref, FP._IMAGES)                                                     # read once, then gone
        self.assertEqual(run(FP.run_tool(Ctx(), "add_card", {"issuer": "Chase", "product": "Sapphire 4242"}))["error"]["code"], "invalid_input")
        self.assertEqual(run(FP.run_tool(Ctx(), "add_card", {"issuer": "Chase", "product": "Sapphire Reserve"}))["result"]["added"], "Sapphire Reserve · Visa")
        with self.assertRaises(ValueError):
            FP.keep_image(ACCOUNT, b"x", "application/pdf")

    def test_which_card_keeps_the_framing(self):
        r = run(FP.run_tool(Ctx(), "which_card", {"amount": 400, "currency": "usd", "kind": "car_rental"}))
        self.assertEqual(r["result"]["framing"], "Information from your cards' own terms. You decide.")
        self.assertEqual([b for op, b in self.agapi.calls if op == "cards.which"][-1]["purchase"], {"amount_minor": 40000, "currency": "USD", "kind": "car_rental"})

    def test_not_switched_on_without_a_key(self):
        with mock.patch.object(FP, "CALL", FP._agapi), mock.patch.dict("os.environ", {"SASHA_AGAPI_TEST_KEY": ""}):
            r = run(FP.run_tool(Ctx(), "my_cards", {}))
        self.assertEqual(r["error"]["code"], "unavailable")


class OnlyOnS2(unittest.TestCase):
    def seen(self, surface):
        import app.services.llm as LLM
        from app.agent import sasha as AG
        seen = []

        async def go():
            async for _ in AG.turn(ACCOUNT, "hello", [], f"s74-{surface}", None, surface):
                pass
        with mock.patch.object(LLM, "client", client([[Block(type="text", text="Hi!")]], seen=seen)):
            run(go())
        return [t["name"] for t in seen[0]["tools"]]

    def test_s1_never_sees_fine_print_and_s2_does(self):
        from app.agent import sasha as AG
        s1 = self.seen("s1")
        self.assertEqual(s1, [t["name"] for t in AG.tools_for_model()])
        self.assertFalse(set(FP.TOOL_NAMES) & set(s1))
        self.assertTrue(set(FP.TOOL_NAMES) <= set(self.seen("s2")))

    def test_s1_fingerprint_with_zero_fine_print_calls(self):
        import app.services.llm as LLM
        from app.agent import sasha as AG
        engine, fine = [], []

        async def call(c, name, args):
            engine.append(name)
            return {"ok": True, "result": {"venues": [{"name": "Casa Marea"}]}}

        async def agapi(*a, **k):
            fine.append(a)
            return {"ok": False}

        def once():
            evs = []

            async def go():
                async for e in AG.turn(ACCOUNT, "dinner near Sol", [], "s74-fp", None, "s1"):
                    evs.append(json.dumps({k: v for k, v in e.items() if k not in ("ms", "steps", "step_ms", "timing", "first_text_ms")},
                                          sort_keys=True, default=str))
            steps = [[Block(type="tool_use", id="t1", name="search_venues", input={"what": "dinner", "where": "Sol"})], [Block(type="text", text="Here.")]]
            with mock.patch.object(LLM, "client", client(steps)), mock.patch.object(API, "call", call), mock.patch.object(FP, "CALL", agapi):
                run(go())
            return evs
        a, b = once(), once()
        self.assertEqual(a, b)
        self.assertEqual(engine.count("search_venues"), 2)
        self.assertEqual(fine, [])

    def test_the_card_image_route_is_s2_only(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.agent import sasha as AG
        app = FastAPI()
        app.include_router(AG.router)
        c = TestClient(app)
        body = {"media_type": "image/png", "content_base64": base64.b64encode(b"\x89PNG").decode()}
        with mock.patch("app.services.chat_account.chat_account", mock.AsyncMock(return_value=ACCOUNT)), \
                mock.patch("app.services.chat_account.signed_in", lambda a: True):
            self.assertEqual(c.post("/api/agent/s2/card-image", json=body).status_code, 404)
            r = c.post("/api/agent/s2/card-image", json=body, headers={"x-sasha-surface": "s2"})
            self.assertTrue(r.json()["card_image_ref"].startswith("ci_"))
            self.assertEqual(c.post("/api/agent/s2/card-image", json={"content_base64": "%%%"}, headers={"x-sasha-surface": "s2"}).status_code, 400)
        with mock.patch("app.services.chat_account.chat_account", mock.AsyncMock(return_value=None)), \
                mock.patch("app.services.chat_account.signed_in", lambda a: False):
            self.assertEqual(c.post("/api/agent/s2/card-image", json=body, headers={"x-sasha-surface": "s2"}).status_code, 403)


if __name__ == "__main__":
    unittest.main()
