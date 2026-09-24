import unittest
from datetime import datetime, timedelta, timezone

from app.services.duffel import _normalise_offer, card_has_live_offer


class DuffelAdapterTests(unittest.TestCase):
    def test_normalises_duffel_offer_into_sasha_card_option(self):
        future = (datetime.now(timezone.utc) + timedelta(minutes=20)).isoformat()
        offer = {
            "id": "off_test_123",
            "total_amount": "412.50",
            "total_currency": "USD",
            "expires_at": future,
            "live_mode": False,
            "passengers": [{"id": "pas_1"}, {"id": "pas_2"}],
            "owner": {"name": "Example Air"},
            "slices": [{
                "duration": "PT8H25M",
                "segments": [{
                    "origin": {"iata_code": "MAD"},
                    "destination": {"iata_code": "JFK"},
                    "operating_carrier": {"name": "Example Air"},
                }],
            }],
        }
        option = _normalise_offer(
            offer,
            origin_query="Madrid",
            destination_query="New York",
            departure_date="2026-10-10",
        )
        self.assertEqual(option["provider"], "duffel")
        self.assertEqual(option["provider_offer_id"], "off_test_123")
        self.assertEqual(option["amount_usd"], 412.50)
        self.assertEqual(option["party_size"], 2)
        self.assertIn("Operated by Example Air", option["detail"])
        self.assertIn("total for 2", option["price"])

    def test_duffel_card_expiry_is_enforced(self):
        future = (datetime.now(timezone.utc) + timedelta(minutes=20)).isoformat()
        past = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
        self.assertTrue(card_has_live_offer({
            "_provider": "duffel",
            "options": [{"expires_at": future}],
        }))
        self.assertFalse(card_has_live_offer({
            "_provider": "duffel",
            "options": [{"expires_at": past}],
        }))

    def test_non_duffel_cards_are_untouched(self):
        self.assertTrue(card_has_live_offer({"type": "flight", "options": []}))


if __name__ == "__main__":
    unittest.main()
