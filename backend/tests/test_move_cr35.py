"""CR 35 (2) · RelocateMe on the bridge: "book my flights" inside a relocation saves the move as ONE trip on the account —
"Move to Madrid", through Sasha's plan_store (never written here) — with DATED days: the certificates, the application
window, the flight and first nights, the TIE appointment and its deadline, each from the consulate's sheet; past days out.
Sasha's bookings then land on those days by date. Offline: Duffel fakes as in CR 13; plan_store.save is captured.

    cd backend && python -m unittest tests.test_move_cr35 -v
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from booking_signer import plan_store as PS
from products.relocation import move as MV
from tests import test_guest_whatsapp_s75 as TG
from tests import test_trip_cr13 as T13

run = TG.run


def case(entry="2027-03-01", consulate=None):
    f = {"applicant": {"address_town": {"value": "Madrid"}, "address_street": {"value": "Calle de Ejemplo"},
                       "address_number": {"value": "12"}}}
    return {"id": "c1", "state": {"facts": f, "after": {"entry_date": entry, "consulate": consulate}}}


class Days(TG.unittest.TestCase):
    def test_the_move_dated_from_the_consulates_sheet(self):
        p = MV.plan(case(), "London", 3, date(2026, 10, 6))
        self.assertEqual(p["title"], "Move to Madrid")
        got = [(d["date"], [a["name"] for a in d["activities"]]) for d in p["days"]]
        self.assertEqual([d for d, _ in got], ["2026-12-01", "2027-03-01", "2027-03-02", "2027-03-03", "2027-03-22", "2027-03-31"])
        self.assertEqual(got[1][1], ["Fly London → Madrid", "Check in — your first nights"])
        self.assertIn("Book your TIE appointment", got[4][1])
        self.assertEqual([d["day"] for d in p["days"]], [1, 2, 3, 4, 5, 6])
        self.assertNotIn("Get your certificates", [n for _, ns in got for n in ns])   # 2 Oct 2026: already past, left out

    def test_a_us_consulate_only_what_its_page_says(self):
        from products.relocation import consulates as CS
        cid = next(iter(CS.READ))
        p = MV.plan(case(consulate={"id": cid, "office": "Consulate"}), "New York", 3, date(2026, 10, 6))
        names = [a["name"] for d in p["days"] for a in d["activities"]]
        self.assertNotIn("Your visa window opens", names)
        self.assertNotIn("TIE deadline", names)


class Trip(T13.Base):
    def setUp(self):
        super().setUp()
        self.saved_ps = PS.save
        self.plans = []

        async def save(account, itinerary, message, now):
            self.plans.append((account, itinerary, message))
            return "trip-move-1"
        PS.save = save

    def tearDown(self):
        PS.save = self.saved_ps
        super().tearDown()

    def test_book_my_flights_saves_the_move_before_the_first_booking(self):
        for t in ("relocation", "DEMO", "SIGNED", "UK", "SKIP", "1 March 2027"):
            self.say(t)
        self.say("book my flights")
        self.say("London")
        (account, itin, message), = self.plans
        self.assertEqual((account, itin["title"]), (TG.ACCOUNT, "Move to Madrid"))
        self.assertTrue(all(d.get("date") for d in itin["days"]))
        self.assertTrue(message.startswith("from "))
        self.assertIn("Your “Move to Madrid” trip is on your account", self.said())
        self.assertEqual(len(self.offer_requests()), 1)                 # then Sasha's own flight flow, as before


if __name__ == "__main__":
    TG.unittest.main()
