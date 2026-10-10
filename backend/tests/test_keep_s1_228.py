"""Sasha 228 · the Keep on S1 (/next) for EVERY signed-in account (SASHA_KEEP_S1=all); the passport said up front ("I have your
passport (ES ••••456) and will apply it."); nothing saved → "Add from your phone" (a one-time code, 10 minutes, the same
account) and /next hears it the moment it's confirmed. Offline: the vision read is a stand-in, the Keep is the in-memory store
under a local key — FICTIONAL fixtures only, never a real passport.

    cd backend && python -m unittest tests.test_keep_s1_228 -v
"""
from __future__ import annotations

import asyncio
import json
import os
import unittest
from datetime import timedelta
from unittest import mock

from agapi import keep as K, keep_handoff as HO, keep_scan as SCAN, s2_keep as KEEP, s2_records as REC, v0 as API
from tests.test_keep_s224 import specimen

ACCT = "00000000-0000-4000-8000-000000000228"
OTHER = "00000000-0000-4000-8000-000000000999"
FOUNDER = "11111111-1111-4111-8111-111111111111"
DEMO = "00000000-0000-4000-8000-0000000d3e00"
run = asyncio.run


class Gate(unittest.TestCase):
    def on(self, value, account):
        from agapi.keep_gate import s1_on
        with mock.patch.dict("os.environ", {"SASHA_KEEP_S1": value}), mock.patch("booking_signer.identity.founder_account", lambda: FOUNDER):
            return s1_on(account)

    def test_all_is_every_signed_in_account_never_the_demo(self):
        self.assertTrue(self.on("all", ACCT))
        self.assertTrue(self.on("all", FOUNDER))
        self.assertFalse(self.on("all", DEMO))
        self.assertFalse(self.on("all", None))

    def test_one_stays_founder_only_and_unset_is_off(self):
        self.assertFalse(self.on("1", ACCT))
        self.assertFalse(self.on("", ACCT))
        self.assertFalse(self.on("yes", ACCT))


class _Keep(unittest.TestCase):
    def setUp(self):
        REC.clear_memory()
        self.store, self.kms = KEEP.MemoryKeepStore(), K.LocalKms(os.urandom(32))
        self.published = []
        from booking_signer import live_events as LE
        for p in (mock.patch.object(KEEP, "STORE", self.store), mock.patch("booking_signer.vault.kms.kek", lambda: self.kms),
                  mock.patch.object(REC, "RUN", None), mock.patch("booking_signer.plan_store._run", lambda: None),
                  mock.patch.object(LE, "publish", lambda a, ev: self.published.append((a, ev)) or ev),
                  mock.patch.object(SCAN, "READ", self._read)):
            p.start()
            self.addCleanup(p.stop)
        SCAN._PENDING.clear()
        HO._CODES.clear()

    @staticmethod
    async def _read(kind, image, media_type):
        return {"mrz": specimen()}


class Handoff(_Keep):
    def test_the_phone_adds_to_the_same_account_once(self):
        h = HO.mint(ACCT, "passport")
        self.assertEqual(HO.mint(ACCT, "passport")["code"], h["code"])        # an open code is reused, never a second one
        self.assertNotIn(ACCT, json.dumps(HO.peek(h["code"])))                 # the phone learns nothing about the account
        card = run(HO.scan(h["code"], b"\xff\xd8 fixture", "image/jpeg"))
        self.assertEqual(card["masked"], "Passport ES ••••456")
        self.assertNotIn("XDA123456", json.dumps(card))
        out = run(HO.confirm(h["code"], card["token"]))
        self.assertEqual(out["item"], "Passport ES ••••456")
        self.assertEqual([i["masked"] for i in run(KEEP.list_(ACCT))], ["Passport ES ••••456"])   # THIS account's Keep
        self.assertEqual(run(KEEP.list_(OTHER)), [])
        with self.assertRaises(HO.HandoffRefused):                             # one-time: spent on Confirm
            run(HO.scan(h["code"], b"jpeg", "image/jpeg"))
        self.assertNotEqual(HO.mint(ACCT, "passport")["code"], h["code"])

    def test_confirm_tells_the_accounts_open_pages_the_mask_only(self):
        h = HO.mint(ACCT)
        card = run(HO.scan(h["code"], b"jpeg", "image/jpeg"))
        run(HO.confirm(h["code"], card["token"]))
        acct, ev = self.published[-1]
        self.assertEqual(acct, ACCT)
        self.assertEqual(ev["type"], "keep_added")
        self.assertEqual(ev["text"], "Got it — Passport ES ••••456. I'll apply it.")
        self.assertNotIn("XDA123456", json.dumps(ev))

    def test_ten_minutes_then_gone(self):
        h = HO.mint(ACCT)
        HO._CODES[h["code"]]["at"] -= HO.TTL + timedelta(seconds=1)
        with self.assertRaises(HO.HandoffRefused):
            HO.peek(h["code"])
        with self.assertRaises(HO.HandoffRefused):
            HO.peek("nosuchcode")

    def test_a_handful_of_photos_at_most(self):
        h = HO.mint(ACCT)
        for _ in range(HO.MAX_SCANS):
            run(HO.scan(h["code"], b"jpeg", "image/jpeg"))
        with self.assertRaises(HO.HandoffRefused):
            run(HO.scan(h["code"], b"jpeg", "image/jpeg"))

    def test_a_token_from_another_code_is_refused(self):
        a, b = HO.mint(ACCT), HO.mint(OTHER)
        card = run(HO.scan(a["code"], b"jpeg", "image/jpeg"))
        with self.assertRaises(SCAN.ScanRefused):
            run(HO.confirm(b["code"], card["token"]))                          # another account's code can't confirm it
        self.assertEqual(run(KEEP.list_(OTHER)), [])

    def test_routes(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        import base64
        app = FastAPI()
        app.include_router(HO.router)
        c, h = TestClient(app), HO.mint(ACCT)
        self.assertEqual(c.get(f"/keep/handoff/{h['code']}").json()["kind"], "passport")
        r = c.post(f"/keep/handoff/{h['code']}/scan", json={"image": base64.b64encode(b"jpeg").decode(), "media_type": "image/jpeg"}).json()
        self.assertEqual(r["masked"], "Passport ES ••••456")
        self.assertEqual(c.post(f"/keep/handoff/{h['code']}/{r['token']}/confirm").json()["item"], "Passport ES ••••456")
        self.assertEqual(c.get(f"/keep/handoff/{h['code']}").status_code, 410)


class SaidUpFront(_Keep):
    def ctx(self, surface="s1"):
        return API.Ctx(account=ACCT, surface=surface)

    def passport(self, env="all", surface="s1", flights=True, bind=True):
        from booking_signer import basket as BK
        rows = [{"kind": "flight"}] if flights else [{"kind": "hotel"}]
        with mock.patch.dict("os.environ", {"SASHA_KEEP_S1": env}), mock.patch.object(BK, "items", mock.AsyncMock(return_value=rows)):
            return run(API._s1_passport(self.ctx(surface), "trip-1", bind=bind))

    def add(self):
        run(KEEP.put(ACCT, "passport", {"number": "XDA123456", "country": "ES", "expires_on": "2031-05-01"}))

    def test_in_the_keep_said_and_bound_for_the_read_back(self):
        self.add()
        k = self.passport()
        self.assertEqual(k["say_first"], "I have your passport (ES ••••456) and will apply it.")
        self.assertEqual(run(KEEP.lines(ACCT)), [K.use_line("Passport ES ••••456")])   # named in the read-back; opened only after the yes
        self.passport()
        self.assertEqual(len(run(KEEP.lines(ACCT))), 1)                                   # bound once, not again each hold
        self.assertNotIn("XDA123456", json.dumps(k))

    def test_nothing_saved_the_hold_offers_the_phone(self):
        k = self.passport()
        self.assertEqual(k["status"], "passport_needed")
        self.assertIn(k["handoff"]["code"], HO._CODES)
        from app.agent import sasha as AG
        ev = AG.render("hold_booking", k, {})
        self.assertEqual(ev["kind"], "keep_handoff")
        self.assertIn("keep_handoff", AG.KINDS)                                           # /next renders it
        self.assertNotIn("keep_handoff", AG.KINDS_S2_ONLY)

    def test_the_plan_says_it_but_never_asks(self):
        self.assertIsNone(self.passport(bind=False))                                      # nothing saved: the hold asks, not the plan
        self.add()
        self.assertEqual(self.passport(bind=False)["say_first"], "I have your passport (ES ••••456) and will apply it.")
        self.assertEqual(run(KEEP.lines(ACCT)), [])                                       # the plan binds nothing

    def test_not_without_a_flight_not_on_s2_not_when_off(self):
        self.add()
        self.assertIsNone(self.passport(flights=False))
        self.assertIsNone(self.passport(surface="s2"))
        self.assertIsNone(self.passport(env=""))
        self.assertIsNone(self.passport(env="1"))                                         # "1" is the founder's only

    def test_a_closed_keep_books_as_before(self):
        with mock.patch.object(KEEP, "STORE", None), mock.patch("booking_signer.plan_store._run", lambda: None):
            self.assertIsNone(self.passport())


class OnlyWhatTheAirlineTakes(unittest.TestCase):
    """Found live (228): Duffel's easyJet TEST offers take no identity document; sending the passport anyway would fail the order."""
    def order(self, supported):
        from booking_signer import travel as T
        sent = {}

        async def http(method, path, body=None):
            if method == "GET":
                return 200, {"data": {"total_amount": "50.00", "total_currency": "EUR", "passengers": [{"id": "pas_1"}],
                                      "supported_passenger_identity_document_types": supported}}
            sent.update(body["data"]["passengers"][0])
            return 201, {"data": {"booking_reference": "ABC123", "id": "ord_1", "live_mode": False}}
        people = [{"given_name": "Test", "family_name": "Fixture", "born_on": "1980-02-01", "title": "mr", "gender": "m", "is_account_holder": True}]
        doc = [{"type": "passport", "unique_identifier": "XDA123456", "issuing_country_code": "ES", "expires_on": "2031-05-01"}]
        with mock.patch.object(T, "HTTP", http), mock.patch.object(T, "token", lambda: "duffel_test_x"):
            o = run(T.order({"id": "off_1", "amount": "50.00", "currency": "EUR"}, "Test Fixture", "f@example.com", "+34600000000", people, documents=doc))
        return o, sent

    def test_a_passport_goes_where_the_airline_takes_one(self):
        o, sent = self.order(["passport", "known_traveler_number"])
        self.assertEqual(o["documents_sent"], 1)
        self.assertEqual(sent["identity_documents"][0]["type"], "passport")

    def test_never_where_it_doesnt_and_the_order_still_goes(self):
        o, sent = self.order([])
        self.assertEqual((o["booking_reference"], o["documents_sent"]), ("ABC123", 0))
        self.assertNotIn("identity_documents", sent)


class SaidByCode(unittest.TestCase):
    def test_the_line_is_said_once_by_code_on_next(self):
        import app.services.llm as LLM
        from app.agent import sasha as AG
        from app.agent.fakes import Block, client
        line = "I have your passport (ES ••••456) and will apply it."

        async def hold(ctx, a):
            return {"read_back": ["Flight MAD→LIS", K.use_line("Passport ES ••••456")], "total_eur": 120.0, "read_back_sha256": "x",
                    "status": "not booked — waiting for the yes", "keep": {"masked": "Passport ES ••••456", "say_first": line}}
        script = [[Block(type="tool_use", id="t1", name="hold_booking", input={})], [Block(type="text", text="That's €120 all in. Shall I book it?")]]
        evs = []

        async def go():
            async for e in AG.turn(ACCT, "book it", [], "s228", None, "s1"):
                evs.append(e)
        with mock.patch.dict(API.BY_NAME, {"hold_booking": {**API.BY_NAME["hold_booking"], "fn": hold}}), \
                mock.patch.dict("os.environ", {"SASHA_KEEP_S1": "all"}), mock.patch.object(LLM, "client", client(script)):
            run(go())
        text = next(e for e in evs if e.get("type") == "done")["text"]
        self.assertTrue(text.startswith(line), text)
        self.assertEqual(text.count("I have your passport"), 1)


if __name__ == "__main__":
    unittest.main()
