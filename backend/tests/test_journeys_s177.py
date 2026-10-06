"""Sasha 177 · one trips space: a booking belongs to the journey whose dates AND place fit — never by date alone. Offline.

    cd backend && python -m unittest tests.test_journeys_s177 -v
"""
import unittest

from booking_signer import journeys as JN
from booking_signer.itinerary_q import TRIP, TRIPS

VIETNAM = {"trip_id": "v", "title": "8 Days in Vietnam: Hanoi → Hue → Hoi An", "start": "2026-11-12", "end": "2026-11-19",
           "cities": ["Hanoi", "Hue", "Hoi An", "Ho Chi Minh City"], "country": "VN"}
CAMPUS = {"trip_id": "c", "title": "Campus tour — week of 15 Nov", "start": "2026-11-15", "end": "2026-11-17",
          "cities": ["New Haven", "Providence", "Philadelphia"], "country": "US"}


class FiledByDatesAndPlace(unittest.TestCase):
    def test_the_live_bug(self):
        """Azerai Hue on Yale's day; Nam Hai + The Boat Riverside on Brown's — they are Vietnam's."""
        for item in ({"date": "2026-11-15", "venue": "Azerai La Residence Hue (TEST booking)", "location": "Hue", "timezone": "Asia/Ho_Chi_Minh"},
                     {"date": "2026-11-16", "venue": "Four Seasons The Nam Hai", "location": "Hoi An", "timezone": "Asia/Ho_Chi_Minh"},
                     {"date": "2026-11-16", "venue": "The Boat Riverside Restaurant & Bar (TEST stand-in)", "read_city": "Hoi An",
                      "timezone": "Europe/Madrid"}):
            self.assertTrue(JN.fits(item, VIETNAM), item["venue"])
            self.assertFalse(JN.fits(item, CAMPUS), item["venue"])

    def test_flights_on_the_days_around(self):
        self.assertTrue(JN.fits({"date": "2026-11-11", "venue": "Flight BA 0117 Madrid → Hanoi (TEST booking)", "location": "MAD → HAN"}, VIETNAM))

    def test_a_place_that_fits_no_journey_stays_home(self):
        self.assertFalse(JN.fits({"date": "2026-11-16", "venue": "Calma", "read_city": "Madrid", "timezone": "Europe/Madrid"}, VIETNAM))
        self.assertFalse(JN.fits({"date": "2026-10-07", "venue": "Red Bean (TEST stand-in)", "read_city": "Hoi An"}, VIETNAM))   # wrong dates

    def test_labels(self):
        self.assertEqual(JN.label(VIETNAM), "Vietnam, Nov")
        self.assertEqual(JN.label(CAMPUS), "Campus tour, week of 15 Nov")
        self.assertEqual(JN.label({"title": "Move to Madrid", "start": "2026-12-01"}), "Move to Madrid")

    def test_journeys_and_only_its_own(self):
        rows = [{"id": "1", "trip_id": "v", "status": "confirmed"}, {"id": "2", "trip_id": "g", "status": "requested"}]
        self.assertEqual([r["id"] for r in JN.for_journey(rows, "v")], ["1"])
        self.assertEqual(JN.for_journey(rows, None), [])


class WhatsAppWords(unittest.TestCase):
    def test_the_trips_space_on_whatsapp(self):
        for m in ("show me my trips", "my requests", "my receipts", "list my journeys"):
            self.assertTrue(TRIPS.search(m), m)
        for m in ("show me my Vietnam trip", "my move to Madrid", "my campus tour"):
            self.assertTrue(TRIP.search(m), m)


if __name__ == "__main__":
    unittest.main()
