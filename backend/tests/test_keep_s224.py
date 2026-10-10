"""Sasha 224 · the Keep on /s2 (CR 63's, wired there only) + adding to it FROM A PHOTO; S1 only behind SASHA_KEEP_S1 (founder).
Offline: the vision read is a stand-in, the Keep is the in-memory store under a local key — fixtures only, never a real passport.

    cd backend && python -m unittest tests.test_keep_s224 -v
"""
from __future__ import annotations

import asyncio
import json
import os
import unittest
from unittest import mock

from agapi import keep as K, keep_scan as SCAN, s2_keep as KEEP, s2_records as REC, v0 as API

ACCT = "00000000-0000-4000-8000-000000000224"
FOUNDER = "11111111-1111-4111-8111-111111111111"
run = asyncio.run


def specimen(number="XDA123456", state="ESP", dob="800201", sex="M", expiry="310501", personal="") -> list:
    """A FICTIONAL ICAO 9303 TD3 MRZ with correct check digits (no real person or document)."""
    cd = SCAN.check_digit
    num = (number + "<" * 9)[:9]
    pers = (personal + "<" * 14)[:14]
    l2 = num + cd(num) + state + dob + cd(dob) + sex + expiry + cd(expiry) + pers + cd(pers)
    l2 += cd(l2[0:10] + l2[13:20] + l2[21:43])
    l1 = ("P<" + state + "SPECIMEN<<TEST<FIXTURE" + "<" * 44)[:44]
    return [l1, l2]


class Mrz(unittest.TestCase):
    def test_a_checked_mrz_reads(self):
        self.assertEqual(SCAN.parse_td3(*specimen()), {"number": "XDA123456", "country": "ES", "expires_on": "2031-05-01"})

    def test_one_wrong_character_is_refused(self):
        l1, l2 = specimen()
        bad = l2[:3] + ("8" if l2[3] != "8" else "7") + l2[4:]
        with self.assertRaises(SCAN.ScanRefused) as e:
            SCAN.parse_td3(l1, bad)
        self.assertEqual(e.exception.rule, "mrz_check_failed")

    def test_not_an_mrz_is_refused(self):
        with self.assertRaises(SCAN.ScanRefused):
            SCAN.parse_td3("hello", "world")

    def test_miscounted_fillers_are_refilled_and_still_checked(self):
        l1, l2 = specimen()
        self.assertEqual(SCAN.parse_td3(l1.rstrip("<") + "<<<", l2[:28] + "<<<<<<<<" + l2[-2:])["number"], "XDA123456")
        with self.assertRaises(SCAN.ScanRefused):   # a digit misread is still refused after the refill
            SCAN.parse_td3(l1, l2[:28] + "<<<<<<" + ("1" if l2[-2] != "1" else "2") + l2[-1])

    def test_germany_is_d(self):
        self.assertEqual(SCAN.parse_td3(*specimen(state="D<<"))["country"], "DE")


class FromAPhoto(unittest.TestCase):
    def setUp(self):
        REC.clear_memory()
        self.store, self.kms = KEEP.MemoryKeepStore(), K.LocalKms(os.urandom(32))
        for p in (mock.patch.object(KEEP, "STORE", self.store), mock.patch("booking_signer.vault.kms.kek", lambda: self.kms),
                  mock.patch.object(REC, "RUN", None), mock.patch("booking_signer.plan_store._run", lambda: None)):
            p.start()
            self.addCleanup(p.stop)
        SCAN._PENDING.clear()

    def read(self, got):
        async def r(kind, image, media_type):
            return got
        return mock.patch.object(SCAN, "READ", r)

    def test_passport_photo_masked_then_saved_encrypted(self):
        with self.read({"mrz": specimen()}):
            out = run(SCAN.scan(ACCT, "passport", b"\xff\xd8 fixture jpeg", "image/jpeg"))
        self.assertEqual(out["masked"], "Passport ES ••••456")
        self.assertNotIn("XDA123456", json.dumps(out))                      # the card is masked
        pend = SCAN._PENDING[out["token"]]
        self.assertNotIn("image", pend)                                     # the photo is not kept
        saved = run(SCAN.confirm(ACCT, out["token"]))
        self.assertEqual(saved["item"], "Passport ES ••••456")
        self.assertNotIn(out["token"], SCAN._PENDING)
        blob = json.dumps([dict(i, nonce=None, ciphertext=None) for i in self.store.items.values()], default=str)
        self.assertNotIn("XDA123456", blob)                                 # only the mask and the ciphertext are stored
        self.assertEqual([i["masked"] for i in run(KEEP.list_(ACCT))], ["Passport ES ••••456"])

    def test_loyalty_from_a_wallet_screenshot(self):
        with self.read({"program": "Iberia Plus", "number": "IB 9876 5432"}):
            out = run(SCAN.scan(ACCT, "loyalty", b"png", "image/png"))
        self.assertEqual(out["masked"], "Iberia Plus ••••432")
        self.assertEqual(run(SCAN.confirm(ACCT, out["token"]))["type"], "loyalty")

    def test_an_unchecked_read_is_never_saved(self):
        l1, l2 = specimen()
        with self.read({"mrz": [l1, l2[:-1] + ("0" if l2[-1] != "0" else "1")]}), self.assertRaises(SCAN.ScanRefused):
            run(SCAN.scan(ACCT, "passport", b"jpeg", "image/jpeg"))
        self.assertEqual(SCAN._PENDING, {})

    def test_another_account_cannot_confirm(self):
        with self.read({"mrz": specimen()}):
            out = run(SCAN.scan(ACCT, "passport", b"jpeg", "image/jpeg"))
        with self.assertRaises(SCAN.ScanRefused):
            run(SCAN.confirm("00000000-0000-4000-8000-000000000999", out["token"]))

    def test_keep_add_puts_the_picker_on_screen(self):
        from app.agent import sasha as AG
        res = run(SCAN.keep_add(API.Ctx(account=ACCT, surface="s2"), {"kind": "frequent flyer"}))
        self.assertEqual(AG.render("keep_add", res, {}), {"type": "render", "kind": "keep_capture", "what": "loyalty"})


class S1IsUnchanged(unittest.TestCase):
    def seen(self, account, surface, env):
        import app.services.llm as LLM
        from app.agent import sasha as AG
        from app.agent.fakes import Block, client
        seen = []

        async def go():
            async for _ in AG.turn(account, "hello", [], f"s224-{surface}", None, surface):
                pass
        with mock.patch.dict("os.environ", env), mock.patch.object(LLM, "client", client([[Block(type="text", text="Hi.")]], seen=seen)), \
                mock.patch("booking_signer.identity.founder_account", lambda: FOUNDER):
            run(go())
        return [t["name"] for t in seen[0]["tools"]], seen[0]["system"][1]["text"]

    def test_next_has_no_keep_by_default(self):
        names, extra = self.seen(FOUNDER, "s1", {"SASHA_KEEP_S1": ""})
        self.assertFalse({"keep_list", "keep_use", "keep_add"} & set(names))
        self.assertNotIn("Their Keep", extra)
        self.assertEqual(names, [t["name"] for t in API.TOOLS])

    def test_the_flag_turns_it_on_for_the_founder_only(self):
        names, extra = self.seen(FOUNDER, "s1", {"SASHA_KEEP_S1": "1"})
        self.assertTrue({"keep_list", "keep_use"} <= set(names))
        self.assertNotIn("keep_add", names)                 # /next has no photo picker
        self.assertIn("Their Keep", extra)
        names, _ = self.seen(ACCT, "s1", {"SASHA_KEEP_S1": "1"})
        self.assertFalse({"keep_list", "keep_use", "keep_add"} & set(names))

    def test_s2_has_all_three(self):
        names, _ = self.seen(ACCT, "s2", {"SASHA_KEEP_S1": ""})
        self.assertTrue({"keep_list", "keep_use", "keep_add"} <= set(names))

    def test_a_passport_typed_on_next_still_reaches_the_turn_by_default(self):   # S1 exactly as before (S-78's guard only)
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.agent import sasha as AG
        called = []

        async def fake(account, message, history, session, surface="s1"):
            called.append(surface)
            yield {"type": "done", "text": "ok", "guard": [], "tools": []}
        app = FastAPI()
        app.include_router(AG.router)
        with mock.patch.dict("os.environ", {"SASHA_KEEP_S1": ""}), \
                mock.patch("app.services.chat_account.chat_account", mock.AsyncMock(return_value=ACCT)), \
                mock.patch("app.services.chat_account.signed_in", lambda a: True), mock.patch.object(AG, "turn_with_quiver", fake), \
                mock.patch.object(AG, "over_budget", mock.AsyncMock(return_value=None)):
            TestClient(app).post("/api/agent/turn", json={"message": "my passport is XDA123456"})
            r = TestClient(app).post("/api/agent/turn", json={"message": "my passport is XDA123456"}, headers={"x-sasha-surface": "s2"})
        self.assertEqual(called, ["s1"])                    # /next as before; /s2 withheld it
        evs = [json.loads(x[6:]) for x in r.text.split("\n\n") if x.startswith("data: ")]
        self.assertEqual([e.get("text") for e in evs], [KEEP.GUARD_REPLY, KEEP.GUARD_REPLY])


class BookingNeverFailsForTheKeep(unittest.TestCase):
    def test_a_closed_keep_books_without_documents(self):
        from booking_signer import basket_book as BB, basket as BK, travel as T, guest_whatsapp as GW, guest_receipt as GR, passengers as PX
        rows = [{"id": "r1", "account_id": ACCT, "state": "pending_payment", "kind": "flight", "snapshot": {}, "party": 1}]
        got = []

        async def order(c, name, email, phone, people, **kw):
            got.append(kw)
            return {"booking_reference": "REF1", "order_id": "ord_1"}

        class Boom:
            async def __aenter__(self):
                raise RuntimeError("relation keep_fills does not exist")

            async def __aexit__(self, *a):
                return False
        with mock.patch.object(KEEP, "fill", lambda a, s: Boom()), mock.patch.object(BK, "by_session", mock.AsyncMock(return_value=rows)), \
                mock.patch.object(GW, "api", mock.AsyncMock(return_value=(200, {"contact": {"name": "Ana"}}))), \
                mock.patch.object(GR, "address_of", mock.AsyncMock(return_value="a@x.test")), \
                mock.patch.object(PX, "saved", mock.AsyncMock(return_value=[])), mock.patch.object(BB, "_card", lambda r: {"id": r["id"]}), \
                mock.patch.object(T, "order", order), mock.patch.object(T, "RECORD", mock.AsyncMock(return_value=None)), \
                mock.patch.object(BK, "booked", mock.AsyncMock()) as booked, mock.patch.object(BK, "event", mock.AsyncMock()):
            try:
                run(BB.book_paid(ACCT, "cs_1"))
            except Exception:
                pass   # the receipt tail after the loop is not under test
        self.assertEqual(got, [{}])                          # ordered, with no documents
        booked.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
