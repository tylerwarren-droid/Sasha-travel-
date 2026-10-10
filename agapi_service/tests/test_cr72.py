"""CR 72 · the subscription radar — subscriptions.find / cancel_plan / cancel. Offline: the sample statement, fakes for the AI reader
and for Magellan; no request leaves a test, no message reaches a merchant.

    python -m unittest agapi_service.tests.test_cr72 -v      (from the repo root)
"""
from __future__ import annotations

import asyncio
import base64
import json
from unittest import mock

from agapi_service import config, engine as E, magellan as MG, rules as R, subscriptions as SB
from agapi_service.tests.test_service import Base


def b64(text: str) -> str:
    return base64.b64encode(text.encode()).decode()


class Detection(Base):
    def test_the_sample_statement_finds_its_ten_subscriptions_and_nothing_else(self):
        subs = SB.detect(SB.parse_csv(SB.sample_csv()))
        self.assertEqual(sorted(s["merchant"] for s in subs), sorted(["PureGym", "Adobe Creative Cloud", "The New York Times", "Calm", "Netflix",
                                                                       "YouTube Premium", "Spotify", "Disney+", "Amazon Prime", "Apple iCloud+"]))
        why = {s["merchant"]: s["why"] for s in subs if s["likely_unused"]}
        self.assertEqual(sorted(why), ["Calm", "Disney+", "YouTube Premium"])
        self.assertIn("a free trial on 2026-07-25 that became a paid plan on 2026-08-01", why["Calm"])
        self.assertIn("you also pay for Spotify (music)", why["YouTube Premium"])
        self.assertIn("you also pay for Netflix (video)", why["Disney+"])
        adobe = next(s for s in subs if s["merchant"] == "Adobe Creative Cloud")
        self.assertEqual((adobe["why"], adobe["likely_unused"]), (["the price went up from 24.19 to 26.43"], False))   # a rise isn't "unused"
        nyt = next(s for s in subs if s["merchant"] == "The New York Times")
        self.assertEqual((nyt["cadence"], nyt["per_month"]["amount_minor"]), ("weekly", 1842))                        # 4.25 × 52 / 12
        self.assertEqual(SB.monthly_total(subs), [{"amount_minor": 14577, "currency": "EUR"}])

    def test_card_numbers_are_masked_and_other_numbers_kept(self):
        self.assertEqual(SB.mask_cards("EL CORTE INGLES CARD 4111 1111 1111 1111"), "EL CORTE INGLES CARD ••••1111")
        self.assertEqual(SB.mask_cards("NETFLIX.COM 866-579-7172"), "NETFLIX.COM 866-579-7172")                 # a phone number, not a card
        self.assertEqual(SB.mask_cards("REF 1234567890123"), "REF 1234567890123")                               # not Luhn-valid: kept
        self.assertNotIn("4111", json.dumps([t["desc"] for t in SB.parse_csv(SB.sample_csv())]).replace("••••1111", ""))

    def test_statements_in_other_formats(self):
        eu = "Fecha;Concepto;Importe\n03/07/2026;NETFLIX.COM;-13,99\n03/08/2026;NETFLIX.COM;-13,99\n03/09/2026;NETFLIX.COM;-13,99\n"
        t = SB.parse_csv(eu)
        self.assertEqual((str(t[0]["date"]), t[0]["amount"]), ("2026-07-03", -13.99))                           # day-first, comma decimals
        us = "Date,Description,Amount\n07/31/2026,SPOTIFY,-10.99\n"
        self.assertEqual(str(SB.parse_csv(us)[0]["date"]), "2026-07-31")
        with self.assertRaises(Exception) as x:
            SB.parse_csv("a,b\n1,2\n")
        self.assertEqual(x.exception.code, "invalid_input")


class Radar(Base):
    def find(self, uid, **st):
        return self.ok("subscriptions.find", {"end_user": uid, **({"statement": st} if st else {})})

    def test_find_from_the_sample_never_keeping_the_statement(self):
        uid = self.user()
        out = self.find(uid, sample=True)
        self.assertEqual((len(out["subscriptions"]), out["likely_unused"]), (10, 3))
        self.assertEqual(out["monthly_total"], [{"amount_minor": 14577, "currency": "EUR"}])
        self.assertTrue(out["statement"]["sha256"].startswith("sha256:"))
        self.assertEqual(out["statement"]["transactions"], 48)
        dump = self.store.raw_dump()
        for never in (b"MERCADONA", b"NOMINA ACME", b"ALQUILER", b"4111 1111", b"RESTAURANTE"):
            self.assertNotIn(never, dump, never)                                                                # the statement isn't kept
        again = self.find(uid)                                                                                  # without a statement: what's known
        self.assertEqual(len(again["subscriptions"]), 10)
        self.find(uid, sample=True)                                                                             # the same statement again: no duplicates
        self.assertEqual(len(self.find(uid)["subscriptions"]), 10)

    def test_an_uploaded_csv_and_a_photo(self):
        uid = self.user()
        csv_ = "date,description,amount\n2026-07-11,SPOTIFY AB,-10.99\n2026-08-11,SPOTIFY AB,-10.99\n2026-09-11,SPOTIFY AB,-10.99\n"
        out = self.find(uid, media_type="text/csv", content_base64=b64(csv_))
        self.assertEqual([s["merchant"] for s in out["subscriptions"]], ["Spotify"])

        async def read(raw, media):
            self.assertEqual(media, "image/jpeg")
            return [{"date": SB._date(d), "desc": SB.mask_cards("NETFLIX.COM CARD 4111111111111111"), "amount": -13.99, "currency": "EUR"}
                    for d in ("2026-07-03", "2026-08-03", "2026-09-03")]
        with mock.patch.object(SB, "EXTRACT", read):
            out = self.find(uid, media_type="image/jpeg", content_base64=base64.b64encode(b"\xff\xd8 a photo").decode())
        n = next(s for s in out["subscriptions"] if s["merchant"] == "Netflix")
        self.assertIn("••••1111", n["descriptor"]["text"])
        with mock.patch.object(SB, "EXTRACT", SB._ai_transactions), mock.patch.object(config, "ANTHROPIC_KEY", ""):
            self.call("subscriptions.find", {"end_user": uid, "statement": {"media_type": "application/pdf", "content_base64": b64("%PDF")}},
                      expect="upstream_unreachable")
        self.call("subscriptions.find", {"end_user": uid, "statement": {"media_type": "text/csv", "content_base64": "not base64!"}},
                  expect="invalid_input")

    def test_plan_then_cancel_by_the_page_on_their_phone_after_the_yes(self):
        uid = self.user()
        netflix = next(s for s in self.find(uid, sample=True)["subscriptions"] if s["merchant"] == "Netflix")
        plan = self.ok("subscriptions.cancel_plan", {"end_user": uid, "subscription_id": netflix["subscription_id"]})
        page = next(r for r in plan["routes"] if r["kind"] == "page")
        self.assertIn("/fixtures/cancel/netflix", page["value"])
        self.assertIn("stand-in", page["quote"]["text"])
        p = self.client.get("/fixtures/cancel/netflix").text
        self.assertIn("It is <b>not</b> Netflix's site", p)                                                    # never pretends to be Netflix
        r, b = self.call("subscriptions.cancel", {"end_user": uid, "subscription_id": netflix["subscription_id"], "route": "page"},
                         expect="approval_required")
        lines = b["error"]["details"]["read_back"]["lines"]
        self.assertEqual(lines[0], "Cancel Netflix: EUR 13.99 monthly (last charged 2026-09-03).")
        self.assertIn("She never logs in for you.", lines[1])
        apv = self.tap_yes(b["error"]["details"]["read_back_id"])
        out = self.ok("subscriptions.cancel", {"end_user": uid, "subscription_id": netflix["subscription_id"], "route": "page"}, approval=apv)
        self.assertEqual((out["outcome"]["kind"], out["subscription"]["status"]), ("REQUESTED", "cancel_requested"))
        self.assertIn("Not cancelled until they confirm", out["outcome"]["target_words"]["text"])
        sent = [m for m in self.ok("sandbox.messages", {"end_user_id": uid})["messages"] if "To cancel Netflix" in m["body"]]
        self.assertEqual(len(sent), 1)                                                                          # to THEIR phone, captured
        self.assertTrue(self.ok("evidence.verify", {"evidence": self.ok("evidence.get", {"evidence_id": out["evidence_id"]})})["valid"])
        self.call("subscriptions.cancel", {"end_user": uid, "subscription_id": netflix["subscription_id"], "route": "page"},
                  expect="already_completed")

    def test_a_cancellations_own_yes_may_say_cancel(self):
        uid = self.user()
        calm = next(s for s in self.find(uid, sample=True)["subscriptions"] if s["merchant"] == "Calm")
        self.ok("subscriptions.cancel_plan", {"end_user": uid, "subscription_id": calm["subscription_id"]})
        r, b = self.call("subscriptions.cancel", {"end_user": uid, "subscription_id": calm["subscription_id"], "route": "page"}, expect="approval_required")
        rb = b["error"]["details"]["read_back_id"]
        self.call("sandbox.simulate_approval", {"read_back_id": rb, "said": "Yes, but what's the refund?"}, expect="no_explicit_yes")
        apv = self.ok("sandbox.simulate_approval", {"read_back_id": rb, "said": "Yes, cancel Calm."})["approval_id"]   # its own yes
        out = self.ok("subscriptions.cancel", {"end_user": uid, "subscription_id": calm["subscription_id"], "route": "page"}, approval=apv)
        self.assertEqual(out["subscription"]["status"], "cancel_requested")

    def test_cancel_by_email_is_captured_in_test_and_refused_live(self):
        uid = self.user()
        calm = next(s for s in self.find(uid, sample=True)["subscriptions"] if s["merchant"] == "Calm")
        self.ok("subscriptions.cancel_plan", {"end_user": uid, "subscription_id": calm["subscription_id"]})
        inp = {"end_user": uid, "subscription_id": calm["subscription_id"], "route": "email", "account_email": "ana@example.test"}
        r, b = self.call("subscriptions.cancel", inp, expect="approval_required")
        self.assertIn("cancel@calm.example", b["error"]["details"]["read_back"]["lines"][1])
        out = self.ok("subscriptions.cancel", inp, approval=self.tap_yes(b["error"]["details"]["read_back_id"]))
        m = [x for x in self.ok("sandbox.messages")["messages"] if x["to"] == "cancel@calm.example"][-1]
        self.assertIn("Subject: Cancel my Calm subscription", m["body"])
        self.assertIn("(account: ana@example.test)", m["body"])
        self.assertEqual(out["outcome"]["kind"], "REQUESTED")
        # live: a merchant's address isn't allow-listed → refused BEFORE anything is read back
        uid2 = self.user("u2", "+15005550007")
        sub = next(s for s in self.find(uid2, sample=True)["subscriptions"] if s["merchant"] == "Spotify")
        self.ok("subscriptions.cancel_plan", {"end_user": uid2, "subscription_id": sub["subscription_id"]})
        key = dict(self.store.one("select * from api_keys where account = ?", self.account), mode="live")
        ctx = E.Ctx(self.store, key, "req_" + "2" * 26, None, None)
        n = self.store.one("select count(*) as n from read_backs")["n"]
        with mock.patch.object(config, "EMAIL_ALLOW", {"tyler@kanoe.ai"}), self.assertRaises(Exception) as x:
            asyncio.run(SB.cancel(ctx, {"end_user": uid2, "subscription_id": sub["subscription_id"], "route": "email"}))
        self.assertEqual((x.exception.code, x.exception.details["reason"]), ("upstream_refused", "not_allow_listed"))
        self.assertEqual(self.store.one("select count(*) as n from read_backs")["n"], n)

    def test_live_plans_come_from_the_merchants_own_site_and_the_sample_is_test_only(self):
        uid = self.user()
        sub = next(s for s in self.find(uid, sample=True)["subscriptions"] if s["merchant"] == "Spotify")
        key = dict(self.store.one("select * from api_keys where account = ?", self.account), mode="live")
        ctx = E.Ctx(self.store, key, "req_" + "3" * 26, None, None)
        seen = []

        async def read(url, purpose):
            seen.append((url, purpose))
            q = R.wrap("To cancel Premium, go to your Account page and select Cancel Premium.", "site:https://support.spotify.com/x", "2026-10-10T00:00:00Z")
            return {"booking_channels": [{"kind": "form", "value": "https://www.spotify.com/account/subscription/", "source_url": "https://support.spotify.com/x",
                                          "quote": q, "confidence": 90}], "coverage": {"pages_read": 3}}
        with mock.patch.object(MG, "read_site", read):
            plan = asyncio.run(SB.cancel_plan(ctx, {"end_user": uid, "subscription_id": sub["subscription_id"]}))[0]
        self.assertEqual(seen, [("https://www.spotify.com", "merchant")])                                       # the merchant's OWN site
        self.assertEqual((plan["routes"][0]["kind"], plan["routes"][0]["value"]), ("page", "https://www.spotify.com/account/subscription/"))
        self.assertIn("select Cancel Premium", plan["routes"][0]["quote"]["text"])
        with self.assertRaises(Exception) as x:
            asyncio.run(SB.find(ctx, {"end_user": uid, "statement": {"sample": True}}))
        self.assertEqual(x.exception.code, "mode_not_available")
        self.assertIn("merchant", MG.PURPOSES)


if __name__ == "__main__":
    import unittest
    unittest.main()
