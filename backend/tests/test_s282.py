"""Sasha 282 · T62 — A PAID THING IS BOOKED ONLY FROM ITS RECORD (the deploy gate, 23 Oct 05:35: ForeignKeyViolationError on
trips_owner_id_fkey from guest_whatsapp.watch_flight_payment, and AGENT 8 FAILED).

ONE SOURCE OF TRUTH: trips.owner_id → auth.users(id) ON DELETE CASCADE. The paid_watch record (written before paying) goes with
its owner. The flight watcher had a SECOND BOOKER: no record → ask Stripe itself → order and write the trip for the account it
was handed. The flight suite's watcher outlived its deleted scratch guest; inside AGENT 8's "everything is paid" window it booked,
and the trip insert hit the FK. Now: paid_watch.settle is the ONE booker (flight, whole trip, and the WhatsApp TEST hotel), from
its record only; a watcher only asks settle and stops when the record is gone; no payment is offered without its record.
AGENT 8's own check moved to Sasha 279's words. Offline: fakes only.

    cd backend && python -m unittest tests.test_s282 -v
"""
from __future__ import annotations

import asyncio
import inspect
import json
import pathlib
import unittest
from unittest import mock

from booking_signer import guest_whatsapp as GW, paid_watch as PW, test_deposit as TD

run = asyncio.run
ACCT = "00000000-0000-4000-8000-000000000282"
BACKEND = pathlib.Path(__file__).resolve().parents[1]


def _never(*_a, **_k):
    raise AssertionError("a watcher booked by itself")


class AWatcherNeverBooks(unittest.TestCase):
    def test_no_record_stops_it_and_nothing_is_booked(self):
        """THE BUG: settle finds no record (its owner deleted) and Stripe says paid → the old watcher ordered and wrote the trip."""
        told = []

        async def settle(_sid):
            return None

        async def gone(_sid):
            return False

        async def paid(_sid):
            return True

        async def tell(_ch, _frm, text):
            told.append(text)
        from booking_signer import travel as TR
        with mock.patch.object(GW, "WATCH_PAY", (0, 5)), mock.patch.object(PW, "settle", settle), mock.patch.object(GW, "_remembered", gone), \
                mock.patch.object(TD, "session_paid", paid), mock.patch.object(TR, "order", _never), mock.patch.object(TR, "RECORD", _never), \
                mock.patch.object(GW, "_tell_if_linked", tell):
            run(GW.watch_payment(None, "", "cs_test_282", "unpaid"))
        self.assertEqual(told, [])   # stopped at once: no one to book for, nothing said

    def test_it_only_asks_settle_and_ends_when_booked(self):
        calls = []

        async def settle(sid):
            calls.append(sid)
            return {"status": "booked"} if len(calls) == 2 else {"status": "booking"}
        with mock.patch.object(GW, "WATCH_PAY", (0, 5)), mock.patch.object(PW, "settle", settle):
            run(GW.watch_payment(None, "", "cs_test_282", "unpaid"))
        self.assertEqual(calls, ["cs_test_282", "cs_test_282"])

    def test_unpaid_for_ten_minutes_is_said(self):
        told = []

        async def settle(_sid):
            return None

        async def held(_sid):
            return True

        async def tell(_ch, _frm, text):
            told.append(text)
        with mock.patch.object(GW, "WATCH_PAY", (0, 3)), mock.patch.object(PW, "settle", settle), mock.patch.object(GW, "_remembered", held), \
                mock.patch.object(GW, "_tell_if_linked", tell):
            run(GW.watch_payment(None, "", "cs_test_282", "unpaid words"))
        self.assertEqual(told, ["unpaid words"])

    def test_the_second_booker_is_gone(self):
        src = inspect.getsource(GW)
        self.assertNotIn("async def watch_flight_payment", src)
        self.assertNotIn("async def watch_hotel_payment", src)
        body = inspect.getsource(GW.watch_payment)
        for booker in ("TR.order", "TR.RECORD", "HT.RECORD", "session_paid"):
            self.assertNotIn(booker, body)
        self.assertIn("await PWT.settle(session_id)", body)


class NoPaymentWithoutItsRecord(unittest.TestCase):
    def _ctx(self):
        return {"account": ACCT, "ch": None, "frm": "", "out": GW.Out(), "st": {}}

    def test_flight(self):
        async def checkout(*_a, **_k):
            return {"id": "cs_test_282", "url": "https://checkout.stripe.com/c/pay/cs_test_282"}

        async def nothing(*_a, **_k):
            return None
        ctx = self._ctx()
        card = {"amount": "120", "currency": "EUR", "owner": "Iberia", "flights": "IB 3100", "from": "MAD", "to": "LIS", "departs": "2026-11-12T08:30"}
        with mock.patch.object(TD, "checkout", checkout), mock.patch.object(PW, "remember", nothing), mock.patch.object(GW, "_spawn", _never):
            run(GW._flight_approve(ctx, {"card": card, "sha": "a" * 64, "name": "Scratch", "email": "", "phone": None}))
        said = ctx["out"].said()
        self.assertNotIn("checkout.stripe.com", said)
        self.assertIn("Nothing was booked", said)

    def test_hotel(self):
        async def checkout(*_a, **_k):
            return {"id": "cs_test_282h", "url": "https://checkout.stripe.com/c/pay/cs_test_282h"}

        async def nothing(*_a, **_k):
            return None
        ctx = self._ctx()
        pend = {"hotel": "Hotel Gate", "city": "Lisbon", "country": "PT", "checkin": "2026-11-12", "nights": 2, "party": 1, "eur": 90.0, "sha": "b" * 64}
        with mock.patch.object(TD, "checkout", checkout), mock.patch.object(PW, "remember", nothing), mock.patch.object(GW, "_spawn", _never):
            run(GW._hotel_test_pay(ctx, pend))
        said = ctx["out"].said()
        self.assertNotIn("checkout.stripe.com", said)
        self.assertIn("No test booking was made", said)

    def test_hotel_with_its_record_is_offered_and_watched(self):
        got = {}

        async def checkout(*_a, **_k):
            return {"id": "cs_test_282h", "url": "https://checkout.stripe.com/c/pay/cs_test_282h"}

        async def remember(account, kind, sid, payload, label, when, tz):
            got.update(kind=kind, sid=sid, payload=payload)
            return "row-282"
        spawned = []
        ctx = self._ctx()
        pend = {"hotel": "Hotel Gate", "city": "Lisbon", "country": "PT", "checkin": "2026-11-12", "nights": 2, "party": 1, "eur": 90.0, "sha": "b" * 64}
        with mock.patch.object(TD, "checkout", checkout), mock.patch.object(PW, "remember", remember), \
                mock.patch.object(GW, "_spawn", lambda c: (spawned.append(c), c.close())):
            run(GW._hotel_test_pay(ctx, pend))
        self.assertIn("checkout.stripe.com", ctx["out"].said())
        self.assertEqual((got["kind"], got["sid"]), ("hotel", "cs_test_282h"))
        self.assertEqual(got["payload"]["stay"]["hotel"], "Hotel Gate")
        self.assertEqual(spawned[0].cr_code.co_name, "watch_payment")


class TheHotelIsBookedBySettle(unittest.TestCase):
    def test_fulfil_hotel_records_it_and_marks_the_payment_done(self):
        rows = []

        class Conn:
            async def execute(self, sql, *a):
                rows.append((sql, a))

        async def fake_run(fn):
            return await fn(Conn())
        recorded = []

        async def record(*a):
            recorded.append(a)
            return "item-282"
        from booking_signer import hotel_test as HT
        stay = {"hotel": "Hotel Gate", "city": "Lisbon", "country": "PT", "checkin": "2026-11-12", "nights": 2, "party": 1}
        with mock.patch.object(PW, "_run", lambda: fake_run), mock.patch.object(HT, "RECORD", record):
            r = run(PW.fulfil("row-282", {"kind": "hotel", "sid": "cs_test_282h", "account": ACCT, "stay": stay}))
        self.assertEqual(r["status"], "booked")
        self.assertTrue(r["booking_reference"])
        self.assertIn("Hotel Gate", r["title"])
        self.assertEqual(recorded[0][0], ACCT)
        sql, args = rows[-1]
        self.assertIn("status = 'cancelled'", sql)   # the payment row is done; the stay is its own item
        notes = args[-1]
        self.assertTrue(notes.startswith(PW.DONE))
        self.assertEqual(json.loads(notes[len(PW.DONE):])["status"], "booked")

    def test_not_recorded_is_failed_never_booked(self):
        async def fake_run(fn):
            class C:
                async def execute(self, *_a):
                    return None
            return await fn(C())

        async def record(*_a):
            return None
        from booking_signer import hotel_test as HT
        stay = {"hotel": "Hotel Gate", "city": "Lisbon", "country": "PT", "checkin": "2026-11-12", "nights": 2, "party": 1}
        with mock.patch.object(PW, "_run", lambda: fake_run), mock.patch.object(HT, "RECORD", record):
            r = run(PW.fulfil("row-282", {"kind": "hotel", "sid": "s", "account": ACCT, "stay": stay}))
        self.assertEqual(r["status"], "failed")


class TheGateReads279sWords(unittest.TestCase):
    def test_agent_8_reads_279s_words(self):
        src = (BACKEND / "scripts" / "agent_suite.py").read_text()
        self.assertIn('ev.get("emailed") is True and ev.get("text", "").endswith(V.closing_line(True))', src)
        self.assertNotIn('"gate@example.com" in ev.get("text", "")', src)
        self.assertIn('mails[0]["to"] == "gate@example.com"', src)   # the email still goes to the address


if __name__ == "__main__":
    unittest.main()
