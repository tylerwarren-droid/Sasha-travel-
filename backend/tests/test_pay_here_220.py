"""Sasha 220 · "Pay here, or on your phone?" — permanent, offline (Stripe, the basket and WhatsApp are stand-ins; 0 live calls).

  · asked once after the yes when they have WhatsApp; the answer pays (no second yes); no WhatsApp → here, never asked
  · the choice is read from their own words, remembered for the conversation, and switchable
  · ONE payment per basket: the same place again → the same session; the other place → the open one EXPIRED first, then a new
    one; already paid → "already paid", never a second charge
  · "here" is an embedded checkout (nothing to the phone); "phone" is the WhatsApp link as before
  · a late or repeated webhook books once (Pacioli's settle is idempotent)

    cd backend && python -m unittest tests.test_pay_here_220 -v
"""
from __future__ import annotations

import asyncio
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

from agapi import v0 as API

ACCOUNT = "00000000-0000-4000-8000-000000000220"


def run(c):
    return asyncio.run(c)


class Words(unittest.TestCase):
    def test_where_from_their_words(self):
        for said, want in (("Pay here", "here"), ("here please", "here"), ("on this phone", "here"), ("in the chat", "here"),
                           ("on my phone", "phone"), ("send it to my phone", "phone"), ("WhatsApp please", "phone"),
                           ("Yes, go ahead", None), ("yes", None)):
            self.assertEqual(API.pay_words(said), want, said)


class Book(unittest.TestCase):
    def setUp(self):
        API._HELD.clear(), API._PAY_ASKED.clear(), API._PAY_CHOICE.clear(), API._IDEM.clear(), API._CLAIMED.clear()
        API._HELD[ACCOUNT] = {"sha": "a" * 64, "at": datetime.now(timezone.utc) - timedelta(minutes=1), "result": {}}
        self.pay = mock.AsyncMock(side_effect=self._pay)
        self.calls = []
        self.p = [mock.patch("booking_signer.basket_book.pay", self.pay),
                  mock.patch("booking_signer.basket_book.in_progress", mock.AsyncMock(return_value=None)),
                  mock.patch("booking_signer.basket._run", lambda: None)]
        for p in self.p:
            p.start()

    def tearDown(self):
        for p in self.p:
            p.stop()
        API._HELD.clear(), API._PAY_ASKED.clear(), API._PAY_CHOICE.clear(), API._IDEM.clear(), API._CLAIMED.clear()

    async def _pay(self, account, sha, where="phone"):
        self.calls.append((sha, where))
        if where == "here":
            return {"where": "here", "session_id": "cs_test_h", "client_secret": "cs_test_h_secret_x", "url": None, "eur": 100.0}
        return {"where": "phone", "session_id": "cs_test_p", "url": "https://checkout.stripe.test/p", "phone": "sent", "eur": 100.0}

    def book(self, said, session="s1", key="k"):
        ctx = API.Ctx(account=ACCOUNT, user_said=said, session=session)
        return run(API.call(ctx, "book", {"approval": {"said": said}, "idempotency_key": key}))

    def linked(self, yes=True):
        return mock.patch.object(API, "_whatsapp_linked", mock.AsyncMock(return_value=yes))

    def test_asked_once_then_their_answer_pays_here(self):
        with self.linked():
            r = self.book("Yes, go ahead.")
            self.assertEqual(r["result"]["status"], "choose_payment")
            self.assertEqual(r["result"]["ask"], "Pay here, or on your phone?")
            self.assertEqual(self.calls, [])                                   # nothing paid on the question
            r = self.book("Here, please.", key="k2")
        self.assertEqual(r["result"]["payment"], "here")
        self.assertEqual(self.calls, [("a" * 64, "here")])
        self.assertEqual(r["result"]["checkout"]["client_secret"], "cs_test_h_secret_x")

    def test_their_answer_phone_is_the_whatsapp_link_as_before(self):
        with self.linked():
            self.book("Yes, go ahead.")
            r = self.book("On my phone.", key="k2")
        self.assertEqual(r["result"]["payment"], "sent_to_phone")
        self.assertEqual(self.calls, [("a" * 64, "phone")])
        self.assertNotIn("checkout", r["result"])

    def test_no_whatsapp_pays_here_and_never_asks(self):
        with self.linked(False):
            r = self.book("Yes, go ahead.")
        self.assertEqual(r["result"]["payment"], "here")
        self.assertEqual(self.calls, [("a" * 64, "here")])

    def test_a_yes_that_says_where_pays_at_once(self):
        with self.linked():
            r = self.book("Yes, on my phone please.")
        self.assertEqual(r["result"]["payment"], "sent_to_phone")

    def test_the_choice_is_remembered_for_the_conversation(self):
        with self.linked():
            self.book("Yes, here.")
            API._HELD[ACCOUNT]["at"] = datetime.now(timezone.utc) - timedelta(minutes=1)
            r = self.book("Yes, go ahead.", key="k3")
        self.assertEqual(r["result"]["payment"], "here")
        self.assertEqual([w for _, w in self.calls], ["here", "here"])

    def test_an_answer_with_no_question_asked_is_not_a_yes(self):
        with self.linked():
            r = self.book("Here.")
        self.assertEqual(r["error"]["code"], "no_explicit_yes")
        self.assertEqual(self.calls, [])

    def test_not_here_is_never_the_answer(self):
        with self.linked():
            self.book("Yes, go ahead.")
            r = self.book("No, not here.", key="k2")
        self.assertEqual(r["error"]["code"], "no_explicit_yes")
        self.assertEqual(self.calls, [])

    def test_switching_moves_the_same_payment(self):
        with self.linked(), mock.patch("booking_signer.basket_book.in_progress", mock.AsyncMock(return_value={"sid": "cs_test_h"})):
            r = self.book("Actually, send it to my phone.", key="k9")
        self.assertEqual(r["result"]["payment"], "sent_to_phone")
        self.assertEqual(self.calls, [("", "phone")])                           # no new read-back: the same rows, moved

    def test_already_paid_is_said(self):
        self.pay.side_effect = None
        self.pay.return_value = {"already_paid": True, "session_id": "cs_test_h"}
        with self.linked(), mock.patch("booking_signer.basket_book.in_progress", mock.AsyncMock(return_value={"sid": "cs_test_h"})):
            r = self.book("Send it to my phone.", key="k8")
        self.assertEqual(r["result"]["status"], "already_paid")
        self.assertFalse(r["result"]["booked"])


class OnePaymentPerBasket(unittest.TestCase):
    """booking_signer.basket_book._resume — what happens to a payment already under way."""

    def resume(self, state, where, expire_ok=True, after=None):
        from booking_signer import basket_book as BB, test_deposit as TD, paid_watch as PWT, guest_whatsapp as GW, basket as BK
        states = [state] + ([after] if after else [])
        ex, rel, tap = mock.AsyncMock(return_value=expire_ok), mock.AsyncMock(return_value=2), mock.AsyncMock(return_value="sent")
        with mock.patch.object(TD, "session_state", mock.AsyncMock(side_effect=states)), mock.patch.object(TD, "expire", ex), \
                mock.patch.object(PWT, "settle", mock.AsyncMock(return_value=None)), mock.patch.object(BK, "release", rel), \
                mock.patch.object(GW, "tap_to_pay", tap):
            out = run(BB._resume(ACCOUNT, {"sid": "cs_test_1", "trip_id": "t1"}, where))
        return out, ex, rel, tap

    def test_paid_is_already_paid_never_a_second_charge(self):
        out, ex, rel, _ = self.resume({"status": "complete", "paid": True, "embedded": True, "amount": 100.0}, "phone")
        self.assertTrue(out["already_paid"])
        ex.assert_not_called(), rel.assert_not_called()

    def test_the_same_place_again_is_the_same_session(self):
        out, ex, _, _ = self.resume({"status": "open", "paid": False, "embedded": True, "where": "here", "client_secret": "sec", "amount": 100.0}, "here")
        self.assertEqual((out["session_id"], out["client_secret"], out["resumed"]), ("cs_test_1", "sec", True))
        ex.assert_not_called()

    def test_the_phone_again_resends_the_same_link(self):
        out, ex, _, tap = self.resume({"status": "open", "paid": False, "embedded": False, "where": "phone", "url": "https://x", "amount": 100.0}, "phone")
        self.assertEqual(out["url"], "https://x")
        tap.assert_awaited_once()
        ex.assert_not_called()

    def test_the_other_place_expires_the_open_one_first(self):
        out, ex, rel, _ = self.resume({"status": "open", "paid": False, "embedded": True, "where": "here", "amount": 100.0}, "phone")
        self.assertIsNone(out)                                                 # the caller opens the new one
        ex.assert_awaited_once_with("cs_test_1")
        rel.assert_awaited_once()

    def test_paid_while_switching_is_already_paid(self):
        out, ex, rel, _ = self.resume({"status": "open", "paid": False, "embedded": True, "amount": 100.0}, "phone", expire_ok=False,
                                      after={"status": "complete", "paid": True, "embedded": True, "amount": 100.0})
        self.assertTrue(out["already_paid"])
        rel.assert_not_called()

    def test_pay_here_is_embedded_and_sends_nothing_to_the_phone(self):
        import hashlib
        from booking_signer import basket_book as BB, basket as BK, guest_whatsapp as GW, paid_watch as PWT, test_deposit as TD
        row = {"id": "r1", "kind": "flight", "state": "chosen", "price_amount": 120.0, "price_currency": "EUR", "day": "2026-11-12",
               "snapshot": {"id": "off_1", "amount": "120.00", "currency": "EUR", "owner": "Iberia", "flights": "IB 3166"}}
        cur = {"rows": [row], "party": 1, "trip_id": "t1", "title": "Trip"}
        sha = hashlib.sha256("\n".join(BB.lines_of(cur["rows"], 1)).encode()).hexdigest()
        co, tap = mock.AsyncMock(return_value={"id": "cs_test_e", "url": None, "client_secret": "sec_e", "embedded": True}), mock.AsyncMock()
        with mock.patch.dict("os.environ", {"SASHA_PAY_EMBEDDED": "1"}), \
                mock.patch.object(BB, "in_progress", mock.AsyncMock(return_value=None)), mock.patch.object(BB, "current", mock.AsyncMock(return_value=cur)), \
                mock.patch.object(TD, "checkout", co), mock.patch.object(BK, "hold", mock.AsyncMock()), \
                mock.patch.object(PWT, "remember", mock.AsyncMock(return_value="rec")), mock.patch.object(GW, "tap_to_pay", tap):
            got = run(BB.pay("acct", sha, "here"))
        self.assertEqual((co.call_args.kwargs.get("embedded"), co.call_args.kwargs.get("where")), (True, "here"))
        tap.assert_not_called()
        self.assertEqual((got["where"], got["client_secret"]), ("here", "sec_e"))


class HereWithoutTheKey(unittest.TestCase):
    def test_here_is_stripes_own_page_on_this_device_until_the_key_is_set(self):
        import hashlib
        from booking_signer import basket_book as BB, basket as BK, guest_whatsapp as GW, paid_watch as PWT, test_deposit as TD
        row = {"id": "r1", "kind": "flight", "state": "chosen", "price_amount": 120.0, "price_currency": "EUR", "day": "2026-11-12",
               "snapshot": {"id": "off_1", "amount": "120.00", "currency": "EUR", "owner": "Iberia", "flights": "IB 3166"}}
        cur = {"rows": [row], "party": 1, "trip_id": "t1", "title": "Trip"}
        sha = hashlib.sha256("\n".join(BB.lines_of(cur["rows"], 1)).encode()).hexdigest()
        co = mock.AsyncMock(return_value={"id": "cs_test_h", "url": "https://checkout.stripe.test/h", "embedded": False})
        with mock.patch.dict("os.environ", {"SASHA_PAY_EMBEDDED": ""}), \
                mock.patch.object(BB, "in_progress", mock.AsyncMock(return_value=None)), mock.patch.object(BB, "current", mock.AsyncMock(return_value=cur)), \
                mock.patch.object(TD, "checkout", co), mock.patch.object(BK, "hold", mock.AsyncMock()), \
                mock.patch.object(PWT, "remember", mock.AsyncMock(return_value="rec")), mock.patch.object(GW, "tap_to_pay", mock.AsyncMock()) as tap:
            got = run(BB.pay("acct", sha, "here"))
        self.assertEqual((co.call_args.kwargs.get("embedded"), got["url"]), (False, "https://checkout.stripe.test/h"))
        tap.assert_not_called()


class LateWebhook(unittest.TestCase):
    def test_a_settled_payment_books_once(self):
        from booking_signer import paid_watch as PWT
        row = {"id": "ti1", "status": "confirmed", "provider_name": "Whole-trip TEST", "booking_reference": "R1",
               "escalation_notes": PWT.DONE + '{"sid": "cs_test_1"}'}

        async def runner(fn):
            class C:
                async def fetchrow(self, *a):
                    return row
            return await fn(C())
        fulfil = mock.AsyncMock()
        with mock.patch.object(PWT, "_run", lambda: runner), mock.patch.object(PWT, "fulfil", fulfil):
            a = run(PWT.settle("cs_test_1"))
            b = run(PWT.settle("cs_test_1"))                                    # the late / repeated webhook
        self.assertEqual((a["status"], b["status"]), ("booked", "booked"))
        fulfil.assert_not_called()                                             # booked once, earlier — never again

    def test_the_webhook_settles_a_basket_payment(self):
        import inspect
        from app.api import payments as PAY
        self.assertIn("PWT.settle(", inspect.getsource(PAY.stripe_webhook))


class Render(unittest.TestCase):
    def test_the_pay_card_and_the_models_view(self):
        from app.agent import sasha as AG
        res = {"status": "awaiting_payment", "payment": "here", "session_id": "cs", "total_eur": 2479.28,
               "checkout": {"client_secret": "sec", "url": None, "session_id": "cs"}}
        ev = AG.render("book", res, {})
        self.assertEqual((ev["kind"], ev["client_secret"]), ("pay_here", "sec"))
        self.assertNotIn("sec", str(AG.clean_for_model(res)))                 # the secret is the page's, never hers
        self.assertTrue(AG.render("book", {"status": "already_paid"}, {})["already_paid"])
        self.assertIsNone(AG.render("book", {"status": "awaiting_payment", "payment": "sent_to_phone"}, {}))


if __name__ == "__main__":
    unittest.main()
