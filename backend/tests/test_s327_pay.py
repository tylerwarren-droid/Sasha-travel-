"""Sasha 327 · PAY IN ONE TAP — wallets + the saved card, through the ONE place money is taken (booking_signer/test_deposit.py: Stripe
TEST Checkout, and now the saved card's PaymentIntent). Offline: Stripe is a fake that answers like Stripe's API.

    cd backend && python -m unittest tests.test_s327_pay -v
"""
from __future__ import annotations

import asyncio
import pathlib
import re
import unittest
from unittest import mock

from booking_signer import basket_book as BB, test_deposit as TD

BACKEND = pathlib.Path(__file__).resolve().parents[1]
ACCT = "00000000-0000-4000-8000-000000000327"
run = asyncio.run


class Stripe:
    """Stripe's API as Sasha calls it (TEST). `sca`: the first off-session confirm needs his bank; `decline`: the card is declined."""

    def __init__(self, sca=False, decline=False):
        self.calls, self.sca, self.decline = [], sca, decline
        self.pms = []          # what Stripe saved on the customer (Stripe's, never Sasha's)
        self.pi = {}

    async def __call__(self, method, path, data=None):
        data = dict(data or {})
        self.calls.append((method, path, data))
        if path == "/customers" and method == "POST":
            return 200, {"id": "cus_T327", "livemode": False}
        if path == "/checkout/sessions" and method == "POST":
            if data.get("payment_intent_data[setup_future_usage]") == "off_session":   # paid on the page with "save": Stripe keeps the card
                self.pms = [{"id": "pm_T327", "type": "card", "card": {"brand": "visa", "last4": "4242", "wallet": None}}]
            return 200, {"id": "cs_test_" + "a" * 20, "url": "https://checkout.stripe.com/c/pay/cs_test_x", "livemode": False}
        if re.fullmatch(r"/customers/cus_T327/payment_methods", path):
            return 200, {"data": list(self.pms)}
        if re.fullmatch(r"/payment_methods/pm_\w+/detach", path):
            self.pms = []
            return 200, {}
        if path == "/payment_intents" and method == "POST":
            self.pi = {"id": "pi_T327aaaaaaaaaa", "status": "requires_confirmation", "amount": int(data["amount"]), "currency": "eur",
                       "payment_method": data["payment_method"], "livemode": False, "created": 1}
            return 200, dict(self.pi)
        if path.endswith("/confirm"):
            if self.decline:
                return 402, {"error": {"code": "card_declined", "message": "Your card was declined."}}
            if self.sca and data.get("off_session") == "true":
                return 402, {"error": {"code": "authentication_required", "message": "Authentication required",
                                       "payment_method": {"id": self.pi["payment_method"]}, "payment_intent": {"id": self.pi["id"]}}}
            if self.sca:
                self.pi.update(status="requires_action", next_action={"type": "redirect_to_url",
                                                                     "redirect_to_url": {"url": "https://hooks.stripe.com/3d_secure_2/x"}})
                return 200, dict(self.pi)
            self.pi["status"] = "succeeded"
            return 200, dict(self.pi)
        if path.endswith("/cancel"):
            self.pi["status"] = "canceled"
            return 200, dict(self.pi)
        if path.startswith("/payment_intents/"):
            return 200, dict(self.pi)
        return 404, {"error": {"message": path}}


class World:
    def __init__(self, stripe):
        self.stripe, self.held, self.records, self.settled, self.mem = stripe, [], [], [], {}

    def __enter__(self):
        async def kind(a, k):
            return self.mem.get(k)

        async def put(a, k, v):
            self.mem[k] = v
            return True

        async def remember(account, kind_, sid, payload, title, ref, tz):
            self.records.append(sid)
            return True

        async def settle(sid):
            self.settled.append(sid)
        cur = {"trip_id": "trip-327", "rows": [{"kind": "flight", "id": "r1"}], "party": 2, "title": "Madrid"}
        self.p = [mock.patch.object(TD, "HTTP", self.stripe), mock.patch.dict("os.environ", {"STRIPE_TEST_SECRET_KEY": "sk_test_x"}),
                  mock.patch("agapi.s2_memory.kind", kind), mock.patch("agapi.s2_memory.put_kind", put),
                  mock.patch.object(BB, "in_progress", mock.AsyncMock(return_value=None)), mock.patch.object(BB, "current", mock.AsyncMock(return_value=cur)),
                  mock.patch.object(BB, "lines_of", lambda rows, party: ["Madrid trip"]),
                  mock.patch.object(BB, "charge_of", mock.AsyncMock(return_value={"amount": 412.5})),
                  mock.patch.object(BB.BK, "hold", mock.AsyncMock(side_effect=lambda a, t, sid: self.held.append(sid))),
                  mock.patch.object(BB.BK, "release", mock.AsyncMock()),
                  mock.patch("booking_signer.paid_watch.remember", remember), mock.patch("booking_signer.paid_watch.settle", settle),
                  mock.patch("booking_signer.guest_whatsapp.tap_to_pay", mock.AsyncMock(return_value="sent")),
                  mock.patch("booking_signer.form_rung.public_base", lambda: "https://sasha.test")]
        for x in self.p:
            x.start()
        return self

    def __exit__(self, *a):
        for x in self.p:
            x.stop()

    def pay(self, where):
        import hashlib
        async def go():
            r = await BB.pay(ACCT, hashlib.sha256(b"Madrid trip").hexdigest(), where)
            await asyncio.sleep(0)   # the spawned settle runs
            return r
        return run(go())

    def posts(self, path):
        return [c for c in self.stripe.calls if c[0] == "POST" and c[1] == path]


class FirstWithSaveThenYesAlone(unittest.TestCase):
    def test_the_page_saves_it_then_yes_pays(self):
        with World(Stripe()) as w:
            first = w.pay("here")                                                       # 1st booking: the Pay-now page, "save" ON
            cs = w.posts("/checkout/sessions")[0][2]
            self.assertEqual((cs["customer"], cs["payment_intent_data[setup_future_usage]"]), ("cus_T327", "off_session"))
            self.assertEqual(cs["custom_text[submit][message]"], TD.SAVE_WORDS)        # the wording he sees where he pays
            self.assertEqual(cs["saved_payment_method_options[payment_method_remove]"], "enabled")   # removable on the page
            self.assertNotIn("payment_method_types[0]", cs)   # wallets (Apple Pay, Google Pay, Link) are Stripe's own, shown first
            card = run(TD.saved_card(ACCT))
            self.assertEqual(card["words"], "your saved Visa ending 4242")
            second = w.pay("saved")                                                     # 2nd booking: "Yes" alone
        self.assertTrue(first["session_id"].startswith("cs_test_"))
        self.assertEqual((second["where"], second["paid"], second["card"]), ("saved", True, "your saved Visa ending 4242"))
        self.assertEqual(len(w.posts("/checkout/sessions")), 1)                         # no page the second time
        pi = second["session_id"]
        self.assertEqual(w.records, [first["session_id"], pi])                           # recorded BEFORE the charge
        order = [c[1] for c in w.stripe.calls]
        self.assertLess(order.index("/payment_intents"), order.index(f"/payment_intents/{pi}/confirm"))
        self.assertEqual(w.settled, [pi])                                                # Pacioli books it: the one entry
        self.assertTrue(run(_paid(w, pi)))


async def _paid(w, pi):
    with mock.patch.object(TD, "HTTP", w.stripe), mock.patch.dict("os.environ", {"STRIPE_TEST_SECRET_KEY": "sk_test_x"}):
        return bool(await TD.session_paid(pi))


class SCA(unittest.TestCase):
    def test_one_confirm_with_your_bank_link_then_paid(self):
        st = Stripe(sca=True)
        st.pms = [{"id": "pm_T327", "type": "card", "card": {"brand": "visa", "last4": "3155"}}]
        with World(st) as w:
            w.mem[TD.CUSTOMER_KIND] = "cus_T327"
            r = w.pay("saved")
        self.assertEqual(r["confirm_url"], "https://hooks.stripe.com/3d_secure_2/x")
        self.assertEqual(w.settled, [])                                                  # not paid yet: nothing booked
        conf = [c for c in st.calls if c[1].endswith("/confirm")]
        self.assertEqual(conf[1][2]["return_url"], f"https://sasha.test/api/booking/test-pay/done?s={r['session_id']}")
        st.pi["status"] = "succeeded"                                                     # he confirms with his bank
        self.assertTrue(run(_paid(w, r["session_id"])))
        self.assertTrue(TD._SID.fullmatch(r["session_id"]))                              # the return page knows it


class Declined(unittest.TestCase):
    def test_said_plainly_the_page_offered_nothing_held(self):
        st = Stripe(decline=True)
        st.pms = [{"id": "pm_T327", "type": "card", "card": {"brand": "visa", "last4": "0002"}}]
        with World(st) as w:
            w.mem[TD.CUSTOMER_KIND] = "cus_T327"
            r = w.pay("saved")
        self.assertTrue(r["declined"])
        self.assertIn("declined", r["why"])
        self.assertTrue(any(c[1].endswith("/cancel") for c in st.calls))                 # that payment can never be charged
        self.assertEqual(w.settled, [])


class RemoveIt(unittest.TestCase):
    def test_removed_then_the_page_again(self):
        st = Stripe()
        st.pms = [{"id": "pm_T327", "type": "card", "card": {"brand": "visa", "last4": "4242"}}]
        with World(st) as w:
            w.mem[TD.CUSTOMER_KIND] = "cus_T327"
            self.assertEqual(run(TD.remove_saved(ACCT)), 1)
            self.assertIsNone(run(TD.saved_card(ACCT)))
            from agapi import v0 as API
            out = run(API.remove_saved_card(API.Ctx(account=ACCT, mode="test"), {}))
        self.assertEqual(out["removed"], 0)
        self.assertIn("remove_saved_card", API.BY_NAME)


class TheWholeClass(unittest.TestCase):
    def test_money_is_taken_in_one_place(self):
        """No booking path takes money another way: Stripe's money endpoints are called from test_deposit.py only, and Sasha never
        handles a card number (no card / cvc field anywhere)."""
        hits = []
        for f in BACKEND.rglob("*.py"):
            if "tests" in f.parts or "venv" in f.parts:
                continue
            t = f.read_text(errors="ignore")
            if re.search(r"[\"'](?:/v1)?/(?:checkout/sessions|payment_intents|charges)[\"'/]", t) and f.name != "test_deposit.py":
                hits.append(str(f.relative_to(BACKEND)))
            if re.search(r"\.(?:Session|PaymentIntent|Charge)\.create\b", t) and f.name != "test_deposit.py":
                hits.append(f"{f.relative_to(BACKEND)}: a Stripe create")
            if re.search(r"[\"'](?:card_number|cvc|card\[number\])[\"']", t):
                hits.append(f"{f.relative_to(BACKEND)}: a card field")
        self.assertEqual(hits, [], hits)

    def test_the_yes_pays_the_saved_card_in_book(self):
        import inspect
        from agapi import v0 as API
        src = inspect.getsource(API.book)
        self.assertIn('where = "saved"', src)
        self.assertIn("_TD.saved_card(ctx.account)", src)


if __name__ == "__main__":
    unittest.main()
