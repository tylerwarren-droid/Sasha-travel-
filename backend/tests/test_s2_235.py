"""Sasha 235 · My Keep (masks, what each was used for and when) · loyalty applied (Duffel's loyalty field for the airline; the
hotel booking's record) · the page route's hours check lives in test_s2_233.HoursCheck235. Offline: the in-memory Keep under a
local key, a stand-in Duffel — fixtures only, never a real number.

    cd backend && python -m unittest tests.test_s2_235 -v
"""
from __future__ import annotations

import asyncio
import os
import unittest
from unittest import mock

from agapi import keep as K, s2_keep as KEEP, s2_records as REC

ACCT = "00000000-0000-4000-8000-000000000235"
run = asyncio.run


class KeepFixture(unittest.TestCase):
    def setUp(self):
        REC.clear_memory()
        self.store, self.kms = KEEP.MemoryKeepStore(), K.LocalKms(os.urandom(32))
        for p in (mock.patch.object(KEEP, "STORE", self.store), mock.patch("booking_signer.vault.kms.kek", lambda: self.kms),
                  mock.patch.object(REC, "RUN", None), mock.patch("booking_signer.plan_store._run", lambda: None)):
            p.start()
            self.addCleanup(p.stop)
        self.iberia = run(KEEP.put(ACCT, "loyalty", {"program": "Iberia Plus", "number": "IB98765432"}))
        self.bonvoy = run(KEEP.put(ACCT, "loyalty", {"program": "Marriott Bonvoy", "number": "MB1234567"}))

    def cards(self):
        async def go():
            async with KEEP.loyalty(ACCT) as cards:
                return [dict(c) for c in cards]
        return run(go())


class MyKeep(KeepFixture):
    def test_masks_with_what_each_was_used_for_and_when(self):
        run(KEEP.loyalty_used(ACCT, {"item_id": self.iberia["item_id"], "masked": self.iberia["masked"]}, "Iberia IB 3166 booking ABC123"))
        items = {i["masked"]: i for i in run(KEEP.list_with_uses(ACCT))}
        self.assertEqual(set(items), {"Iberia Plus ••••432", "Marriott Bonvoy ••••567"})
        uses = items["Iberia Plus ••••432"]["uses"]
        self.assertEqual([u["what"] for u in uses], ["Used", "Saved"])
        self.assertEqual(uses[0]["for"], "Iberia IB 3166 booking ABC123")
        self.assertTrue(uses[0]["at"])
        self.assertNotIn("98765432", repr(items))                          # never a value

    def test_the_route_returns_the_uses(self):
        src = open(KEEP.__file__).read()
        self.assertIn('"items": await list_with_uses(account)', src)


class LoyaltyOpened(KeepFixture):
    def test_opened_for_the_loop_then_dropped(self):
        held = []

        async def go():
            async with KEEP.loyalty(ACCT) as cards:
                held.extend(cards)
                return {c["program"]: c["number"] for c in cards}
        self.assertEqual(run(go()), {"Iberia Plus": "IB98765432", "Marriott Bonvoy": "MB1234567"})
        self.assertEqual([c["number"] for c in held], [None, None])        # dropped after: no number outlives the loop

    def test_matching(self):
        self.assertEqual(KEEP.airlines_of("Iberia Plus"), ("IB",))
        self.assertEqual(KEEP.airlines_of("Marriott Bonvoy"), ())
        self.assertTrue(KEEP.hotel_matches("Marriott Bonvoy", "Madrid Marriott Auditorium Hotel"))
        self.assertTrue(KEEP.hotel_matches("Marriott Bonvoy", "The Westin Palace, Madrid"))
        self.assertFalse(KEEP.hotel_matches("Marriott Bonvoy", "Hotel Example Madrid"))
        self.assertFalse(KEEP.hotel_matches("Iberia Plus", "Madrid Marriott Auditorium Hotel"))


class LoyaltyOnTheBooking(KeepFixture):
    echo = True   # Duffel's order shows the account back

    def test_sent_but_not_shown_back_is_said_as_that(self):   # live, 11 Oct: Duffel TEST orders echo an empty list
        self.echo = False
        _, _, applied = self.book(self.FLIGHT, card={"id": "r1", "owner": "British Airways", "flights": "BA 461"})
        self.assertEqual(applied, ["I sent your Iberia Plus ••••432 to British Airways with this booking, but their booking doesn't show it "
                                   "back yet — check it's on your boarding pass."])

    def book(self, rows, card=None, sent=None):
        from booking_signer import basket_book as BB, basket as BK, hotel_test as HT, travel as T
        got, records, applied = [], [], []

        async def order(c, name, email, phone, people, **kw):
            got.append(kw)
            out = sent if sent is not None else [a["airline_iata_code"] for a in kw.get("loyalty") or []]
            return {"booking_reference": "ABC123", "order_id": "ord_1", "loyalty_sent": out,
                    "loyalty_on_order": out if self.echo else []}

        async def add(account, item_id, extra):
            records.append(extra)
            return True
        with mock.patch.object(BB, "_card", lambda r: card or {"id": r["id"], "owner": "Iberia", "flights": "IB 3166"}), \
                mock.patch.object(T, "order", order), mock.patch.object(T, "RECORD", mock.AsyncMock(return_value=None)), \
                mock.patch.object(HT, "RECORD", mock.AsyncMock(return_value=None)), mock.patch.object(BK, "add_to_record", add), \
                mock.patch.object(BK, "booked", mock.AsyncMock()), mock.patch.object(BK, "event", mock.AsyncMock()), \
                mock.patch.object(BK, "failed", mock.AsyncMock()):
            run(BB._book_rows(ACCT, "cs_1", rows, {"name": "Ana"}, "a@x.test", [], None, None, cards=self.cards(), applied=applied))
        return got, records, applied

    FLIGHT = [{"id": "r1", "account_id": ACCT, "state": "pending_payment", "kind": "flight", "snapshot": {}, "party": 1}]

    def test_the_airlines_number_goes_in_duffels_loyalty_field(self):
        got, _, applied = self.book(self.FLIGHT)
        self.assertEqual(got[0]["loyalty"], [{"airline_iata_code": "IB", "account_number": "IB98765432"}])
        self.assertEqual(applied, ["I've added your Iberia Plus ••••432 to this booking."])
        uses = {i["masked"]: i["uses"] for i in run(KEEP.list_with_uses(ACCT))}["Iberia Plus ••••432"]
        self.assertEqual(uses[0]["for"], "Iberia IB 3166 booking ABC123")

    def test_another_airline_gets_nothing(self):   # offered to the order (Iberia Plus → IB); easyJet's offer takes only U2 → not carried
        got, _, applied = self.book(self.FLIGHT, card={"id": "r1", "owner": "easyJet", "flights": "U2 7652"}, sent=[])
        self.assertEqual(got[0]["loyalty"], [{"airline_iata_code": "IB", "account_number": "IB98765432"}])
        self.assertEqual(applied, [])

    def test_a_ba_flight_takes_iberia_plus(self):   # Duffel: BA's offers list IB among their supported programmes
        got, _, applied = self.book(self.FLIGHT, card={"id": "r1", "owner": "British Airways", "flights": "BA 461"})
        self.assertEqual(applied, ["I've added your Iberia Plus ••••432 to this booking."])

    def test_said_only_when_duffel_carried_it(self):
        _, _, applied = self.book(self.FLIGHT, sent=[])                     # the offer didn't take Iberia Plus
        self.assertEqual(applied, [])

    def test_the_hotel_groups_number_on_the_stays_record(self):
        rows = [{"id": "r2", "account_id": ACCT, "state": "pending_payment", "kind": "stay", "day": "2026-11-02", "party": 2,
                 "snapshot": {"name": "Madrid Marriott Auditorium Hotel", "city": "Madrid", "nights": 2}}]
        _, records, applied = self.book(rows)
        self.assertEqual(records, [{"loyalty": {"program": "Marriott Bonvoy", "masked": "Marriott Bonvoy ••••567"}}])
        self.assertNotIn("MB1234567", repr(records))                       # the record carries the mask, never the number
        self.assertEqual(applied, ["I've added your Marriott Bonvoy ••••567 to this booking."])

    def test_a_hotel_of_another_group_gets_nothing(self):
        rows = [{"id": "r3", "account_id": ACCT, "state": "pending_payment", "kind": "stay", "day": "2026-11-02", "party": 2,
                 "snapshot": {"name": "Hotel Example Madrid", "city": "Madrid", "nights": 1}}]
        _, records, applied = self.book(rows)
        self.assertEqual((records, applied), ([], []))


class DuffelOrderCarriesIt(unittest.TestCase):
    def order(self, supported):
        from booking_signer import travel as T
        sent = {}
        offer = {"id": "off_1", "total_amount": "100.00", "total_currency": "EUR", "passengers": [{"id": "pas_1"}],
                 **({"supported_loyalty_programmes": supported} if supported is not None else {})}

        async def http(method, path, body=None):
            if method == "GET":
                return 200, {"data": offer}
            sent.update(body["data"])
            return 201, {"data": {"id": "ord_1", "booking_reference": "ABC123", "live_mode": False}}
        with mock.patch.object(T, "HTTP", http), mock.patch.object(T, "token", lambda: "duffel_test_x"):
            o = run(T.order({"id": "off_1", "amount": "100.00", "currency": "EUR"}, "Ana Test", "a@x.test", None,
                            loyalty=[{"airline_iata_code": "IB", "account_number": "IB98765432"}]))
        return o, sent

    def test_on_the_passenger(self):
        o, sent = self.order(["IB", "BA"])
        self.assertEqual(sent["passengers"][0]["loyalty_programme_accounts"], [{"airline_iata_code": "IB", "account_number": "IB98765432"}])
        self.assertEqual(o["loyalty_sent"], ["IB"])
        self.assertEqual(o["loyalty_on_order"], [])   # the stand-in's order shows none back

    def test_an_unsupported_programme_never_fails_the_order(self):
        o, sent = self.order(["BA"])
        self.assertNotIn("loyalty_programme_accounts", sent["passengers"][0])
        self.assertEqual(o["loyalty_sent"], [])

    def test_duffels_test_iberia_takes_none(self):   # live, 11 Oct: Duffel's TEST Iberia offers list supported_loyalty_programmes []
        o, sent = self.order([])
        self.assertNotIn("loyalty_programme_accounts", sent["passengers"][0])
        self.assertEqual(o["loyalty_sent"], [])

    def test_an_offer_that_doesnt_say_takes_only_its_own_airline(self):
        o, sent = self.order(None)   # no slices in the stand-in → no airline of its own → nothing sent
        self.assertNotIn("loyalty_programme_accounts", sent["passengers"][0])


if __name__ == "__main__":
    unittest.main()


class UpgradeMyRoom(unittest.TestCase):
    """Sasha 235 · 'Upgrade my room': the TEST stay's request goes to OUR test hotel at the address its own page lists (read through
    the ladder), read back, sent only on a later yes — captured — and the test hotel's reply comes back in its words."""
    STAY = {"kind": "hotel", "title": "Madrid Marriott Auditorium Hotel (TEST booking — no hotel contacted)", "when": "2026-11-02",
            "where": "Madrid", "nights": 2, "status": "booked", "reference": "TEST-ABC123", "id": "b1"}

    def setUp(self):
        from datetime import datetime, timedelta, timezone
        from agapi import s2_hotel as H, s2_manage as M, s2_tools as S, venues as VN
        S._HELD.clear(); S.OUTBOX.clear(); H.REPLIES.clear()
        self.H, self.S, self.reads = H, S, []
        desk = "recepcion-prueba@booking.kanoe.ai"

        async def api(account, method, path, body=None, timeout=90.0):
            if path == "/api/booking/venues/read":
                self.reads.append(body)
                return 200, {"read_id": "rd1", "facts": [{"kind": "email", "value": desk, "source_url": body["website"]}]}
            return 200, {"contact": {"name": "Alex Gate"}}
        GW = type("GW", (), {"api": staticmethod(api)})
        for p in (mock.patch.object(M, "plans_of", mock.AsyncMock(return_value=[self.STAY])), mock.patch.object(VN, "_API", lambda: GW),
                  mock.patch("booking_signer.basket.event", mock.AsyncMock()), mock.patch("agapi.v0.claim", mock.AsyncMock()),
                  mock.patch.object(S, "live_for", lambda a: False)):
            p.start()
            self.addCleanup(p.stop)
        self.t0 = datetime.now(timezone.utc)
        self.later = lambda: datetime.now(timezone.utc) + timedelta(seconds=5)

    def turn(self, said, started, **a):
        from agapi import v0 as API
        return run(API.call(API.Ctx(account=ACCT, user_said=said, started=started), "hotel_request",
                            {"ask": "upgrade", "idempotency_key": f"k-{said}-{started.timestamp()}", **a}))

    def test_read_back_then_yes_then_their_words(self):
        r = self.turn("Upgrade my room", self.t0)["result"]
        self.assertEqual(r["status"], "awaiting_yes")
        self.assertIn("Kanoe Test Hotel's own website lists recepcion-prueba@booking.kanoe.ai", r["read_back"][0])
        self.assertIn("captured, it never leaves Kanoe", r["read_back"][0])
        self.assertTrue(any("mejora de habitación" in l for l in r["read_back"]))
        self.assertTrue(any("TEST-ABC123" in l for l in r["read_back"]))
        self.assertTrue(self.reads[0]["website"].endswith("/api/booking/test-venue/hotel"))   # the address READ from its own page
        self.assertEqual(self.S.OUTBOX, [])                                               # nothing yet
        done = self.turn("Yes, send it.", self.later())["result"]
        self.assertEqual(done["status"], "not_sent")                                       # captured — never "sent"
        self.assertEqual(len(self.S.OUTBOX), 1)
        self.assertEqual(self.S.OUTBOX[0]["message"]["to"]["address"], "recepcion-prueba@booking.kanoe.ai")
        self.assertIn("habitación superior", done["their_reply"]["text"])
        self.assertIn("no es un hotel real", done["their_reply"]["text"])
        again = self.turn("Did they answer?", self.later(), check_reply=True)["result"]
        self.assertEqual(again["their_reply"]["text"], done["their_reply"]["text"])

    def test_a_question_is_not_a_yes(self):
        self.turn("Upgrade my room", self.t0)
        from agapi import v0 as API
        r = run(API.call(API.Ctx(account=ACCT, user_said="Yes — how much will it cost?", started=self.later()), "hotel_request",
                         {"ask": "upgrade", "idempotency_key": "k-q"}))
        self.assertEqual(r["error"]["code"], "no_explicit_yes")
        self.assertEqual(self.S.OUTBOX, [])

    def test_s2_only(self):
        from agapi import v0 as API
        from app.agent import s2 as S2
        self.assertNotIn("hotel_request", [t["name"] for t in API.TOOLS])                  # S1's list untouched
        self.assertIn("hotel_request", S2.S2_TOOLS)
