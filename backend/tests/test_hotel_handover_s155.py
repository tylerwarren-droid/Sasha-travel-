"""Sasha 155 · the hotel sequence ends on the hotel's page, live: OUR test hotel (Kanoe Test Hotel), its terms box left for
the guest, opened only after the TEST payment. Offline.

    cd backend && python -m unittest tests.test_hotel_handover_s155 -v
"""
from __future__ import annotations

import asyncio
import json
import unittest

from booking_signer import form_rung as FR, hotel_test as HT


class _Req:
    def __init__(self, body: dict) -> None:
        self._b = body
        self.headers: dict = {}

    async def json(self):
        return self._b


class TestHotelPage(unittest.TestCase):
    def test_the_page_is_ours_with_the_same_fields_and_a_terms_box(self):
        r = asyncio.run(FR.test_venue("hotel"))
        html = r.body.decode()
        self.assertIn("Kanoe Test Hotel", html)
        self.assertIn("No es un hotel real", html)
        for name in FR.TEST_FIELDS:
            self.assertIn(f'name="{name}"', html)
        self.assertIn('name="acepto" type="checkbox" required', html)
        self.assertTrue(FR.is_test_venue(FR.test_venue_url("hotel")))
        self.assertTrue(FR.form_map(FR.test_venue_url("hotel"))["test"])

    def test_a_booking_needs_the_box_and_restates_the_stay(self):
        form = {"fecha": "2026-12-15", "hora": "15:00", "personas": "2", "nombre": "Prueba Sasha", "email": "p@example.com",
                "telefono": "600000000", "comentarios": "2 noches"}
        self.assertEqual(asyncio.run(FR._book("hotel", form)).status_code, 422)
        ok = asyncio.run(FR._book("hotel", {**form, "acepto": "on"})).body.decode()
        self.assertIn("Reserva confirmada", ok)
        self.assertIn("habitación para 2 personas", ok)
        self.assertIn("martes 15 de diciembre a las 15:00", ok)
        self.assertIn("Localizador: TV-", ok)

    def test_the_restaurant_variants_are_unchanged(self):
        self.assertIn("Sasha Test Venue", asyncio.run(FR.test_venue("plain")).body.decode())
        self.assertNotIn("acepto", asyncio.run(FR.test_venue("plain")).body.decode())


class TestHotelHandover(unittest.TestCase):
    def test_not_before_the_test_payment(self):
        body = {"hotel": "Hotel X", "city": "Madrid", "checkin": "2026-12-15", "nights": 2, "party": 2, "session_id": "cs_test_none"}
        r = asyncio.run(HT.handover(_Req(body)))
        self.assertEqual(r.status_code, 409)
        self.assertEqual(json.loads(r.body)["rule"], "hotel_not_paid")

    def test_the_words_say_it_is_our_test_page(self):
        s = HT.HANDOVER_SAY.format(hotel="Hotel X")
        self.assertIn("Kanoe Test Hotel", s)
        self.assertIn("not Hotel X's site", s)
        self.assertIn("fictional guest", s)


if __name__ == "__main__":
    unittest.main()
