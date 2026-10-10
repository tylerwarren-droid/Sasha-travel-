"""CR 63 · THE KEEP, WIRED — the paths docs/sasha/s2-keep-wiring.md wires, end to end with fixtures. SKIPPED until the wiring is
in (keep_list registered in v0); then it runs by itself: travel.order puts the documents on the account holder, book_paid fills
both flights of a round trip, /next never sends a typed passport or password to the model, hold_booking names the passport.
(CR 63 ran it with the wiring applied on a throwaway branch: 5/5, full suite 1654 OK.)"""
import asyncio, json, os, unittest
from unittest import mock
from agapi import keep as K, s2_keep as KEEP, s2_records as REC, v0 as API

ACCT = "00000000-0000-4000-8000-0000000000f0"
PP = {"number": "PAA123456", "country": "ES", "expires_on": "2031-05-01"}
run = asyncio.run


@unittest.skipUnless("keep_list" in API.BY_NAME, "the Keep isn't wired yet (docs/sasha/s2-keep-wiring.md) — these run once it is")
class Wired(unittest.TestCase):
    def setUp(self):
        REC.clear_memory()
        self.store, self.kms = KEEP.MemoryKeepStore(), K.LocalKms(os.urandom(32))
        for p in (mock.patch.object(KEEP, "STORE", self.store), mock.patch("booking_signer.vault.kms.kek", lambda: self.kms),
                  mock.patch.object(REC, "RUN", None), mock.patch("booking_signer.plan_store._run", lambda: None)):
            p.start(); self.addCleanup(p.stop)

    def test_tools_registered(self):
        self.assertIn("keep_list", API.BY_NAME); self.assertIn("keep_use", API.BY_NAME); self.assertIn("keep_list", API.READS)

    def test_travel_order_puts_the_documents_on_the_account_holder(self):
        from booking_signer import travel as T
        sent = {}

        async def http(method, path, body=None):
            if method == "GET":
                return 200, {"data": {"total_amount": "120.00", "total_currency": "EUR", "passengers": [{"id": "pas_1"}, {"id": "pas_2"}]}}
            sent["pax"] = body["data"]["passengers"]
            return 201, {"data": {"booking_reference": "UHQ9B1", "id": "ord_1"}}
        people = [{"given_name": "Jon", "family_name": "X", "born_on": "1990-01-01", "title": "mr", "gender": "m"},
                  {"given_name": "Ana", "family_name": "Y", "born_on": "1991-01-01", "title": "ms", "gender": "f", "is_account_holder": True}]
        docs = [{"type": "passport", "unique_identifier": "PAA123456", "issuing_country_code": "ES", "expires_on": "2031-05-01"}]
        with mock.patch.object(T, "token", lambda: "duffel_test_x"), mock.patch.object(T, "HTTP", http):
            o = run(T.order({"id": "off_1", "amount": "120.00", "currency": "EUR"}, "Ana Y", "a@x.test", None, people, documents=docs))
        self.assertEqual(o["booking_reference"], "UHQ9B1")
        self.assertNotIn("identity_documents", sent["pax"][0])
        self.assertEqual(sent["pax"][1]["identity_documents"], docs)

    def test_book_paid_fills_both_flights_of_a_round_trip_then_activity(self):
        from booking_signer import basket_book as BB, basket as BK, travel as T, guest_whatsapp as GW, guest_receipt as GR, passengers as PX
        item = run(KEEP.put(ACCT, "passport", PP))["item_id"]
        line = run(KEEP.bind(ACCT, item, "fill"))["line"]
        self.assertEqual(run(KEEP.approve(ACCT, ["I'll book it.", line], "Yes, book it.", "cs_1")), 1)
        rows = [{"id": f"r{i}", "account_id": ACCT, "state": "pending_payment", "kind": "flight", "snapshot": {}, "party": 1} for i in (1, 2)]
        got = []

        async def order(c, name, email, phone, people, documents=None):
            got.append(documents); return {"booking_reference": f"REF{len(got)}", "order_id": f"ord_{len(got)}"}
        with mock.patch.object(BK, "by_session", mock.AsyncMock(return_value=rows)), \
                mock.patch.object(GW, "api", mock.AsyncMock(return_value=(200, {"contact": {"name": "Ana"}}))), \
                mock.patch.object(GR, "address_of", mock.AsyncMock(return_value="a@x.test")), \
                mock.patch.object(PX, "saved", mock.AsyncMock(return_value=[])), mock.patch.object(BB, "_card", lambda r: {"id": r["id"]}), \
                mock.patch.object(T, "order", order), mock.patch.object(T, "RECORD", mock.AsyncMock(return_value=None)), \
                mock.patch.object(BK, "booked", mock.AsyncMock()), mock.patch.object(BK, "event", mock.AsyncMock()):
            try:
                run(BB.book_paid(ACCT, "cs_1"))
            except Exception:
                pass   # the receipt/notification tail after the loop is not under test
        self.assertEqual(len(got), 2)
        self.assertTrue(all(d and d[0]["unique_identifier"] == "PAA123456" for d in got))
        used = [a for a in REC.ACTS if a["kind"] == "keep_use"]
        self.assertEqual(used[0]["proof"]["reference"], "REF1, REF2")

    def test_next_never_sends_a_passport_to_the_model(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.agent import sasha as AG
        app = FastAPI(); app.include_router(AG.router)
        c = TestClient(app)
        with mock.patch("app.services.chat_account.chat_account", mock.AsyncMock(return_value=ACCT)), \
                mock.patch("app.services.chat_account.signed_in", lambda a: True), \
                mock.patch.object(AG, "turn_with_quiver", side_effect=AssertionError("the model was called")), \
                mock.patch.object(AG, "over_budget", mock.AsyncMock(return_value=None)):
            r = c.post("/api/agent/turn", json={"message": "my passport is PAA123456"}, headers={"x-sasha-surface": "s2"})   # Sasha 224 · /s2 first
            self.assertEqual(r.status_code, 200)
            evs = [json.loads(x[6:]) for x in r.text.split("\n\n") if x.startswith("data: ")]
            self.assertEqual([(e["type"], e["text"]) for e in evs], [("say", KEEP.GUARD_REPLY), ("done", KEEP.GUARD_REPLY)])
            r = c.post("/api/agent/turn", json={"message": "my password is hunter2!"})
            self.assertIn("passwords", r.text)
            self.assertEqual(c.get("/api/agent/keep").status_code, 200)   # mounted under /api/agent, once

    def test_hold_booking_names_the_bound_passport(self):
        item = run(KEEP.put(ACCT, "passport", PP))["item_id"]
        run(KEEP.bind(ACCT, item, "fill"))
        from booking_signer import basket_book as BB, passengers as PX, basket as BK
        with mock.patch.object(API, "_plan", mock.AsyncMock(return_value={"trip_id": "t1", "party": 1})), \
                mock.patch.object(API, "_party", lambda p: 1), mock.patch.object(PX, "saved", mock.AsyncMock(return_value=[{}])), \
                mock.patch.object(BB, "quote", mock.AsyncMock(return_value={"lines": ["✈️ IB3166", "Total €120.00 (TEST)"], "sha256": "s1", "eur": 120.0})), \
                mock.patch.object(BK, "items", mock.AsyncMock(return_value=[])), mock.patch.object(BK, "to_book", lambda rows: rows), \
                mock.patch.object(API, "breakdown", lambda rows, eur: {}):
            API._HELD.pop(ACCT, None)
            r = run(API.call(API.Ctx(account=ACCT, surface="s2"), "hold_booking", {"idempotency_key": "k-hold-1"}))   # Sasha 224 · /s2 first
        self.assertIn("I'll use your saved Passport ES ••••456 for this booking.", r["result"]["read_back"], r)


if __name__ == "__main__":
    unittest.main()
