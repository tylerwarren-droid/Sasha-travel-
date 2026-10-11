"""Sasha 242 (EU's walk, row 730) · the spa search keeps a venue whose own site has a CAPTCHA (Hammam Al Ándalus), and the
rehearsal card never reaches a real account."""
from __future__ import annotations

import asyncio
import os
import unittest
from unittest import mock

from booking_signer import ladder_routes as LR

HAMMAM = {"name": "Hammam Madrid Plaza Mayor", "facts": [
    {"kind": "phone", "value": "+34914299020", "source_kind": "site"},
    {"kind": "challenge", "value": "captcha", "source_kind": "site"}]}


class _Store:
    def __init__(self, read):
        self.read = read

    async def recent_read(self, account, place_id, since):
        return {"read": self.read}


class SpaKeepsTheCaptchaSite(unittest.TestCase):
    def test_online_by_hand(self):
        self.assertTrue(LR.online_by_hand(HAMMAM))
        self.assertFalse(LR.online_by_hand({"facts": [{"kind": "phone", "value": "+34", "source_kind": "site"}]}))
        self.assertFalse(LR.online_by_hand({"facts": [{"kind": "challenge", "source_kind": "places"}]}))
        self.assertFalse(LR.online_by_hand(None))

    def test_online_route_keeps_hammam(self):
        with mock.patch.object(LR, "LADDER_STORE", _Store(HAMMAM)), mock.patch.object(LR, "read_reuse_hours", lambda: 24), \
                mock.patch.object(LR.L, "choose", lambda read, account=None: {"rungs": [{"rung": "call", "available": True}]}):
            got = asyncio.run(LR._online_route("11111111-1111-4111-8111-111111111111", {"place_id": "ChIJ9WUZv38oQg0RLSoWPZUJeP4"},
                                               {"what": "Arab baths spa", "where": "Madrid"}))
        self.assertEqual(got, "their own site (you finish it — it has a CAPTCHA)")

    def test_phone_only_still_dropped(self):
        phone_only = {"facts": [{"kind": "phone", "value": "+34", "source_kind": "site"}]}
        with mock.patch.object(LR, "LADDER_STORE", _Store(phone_only)), mock.patch.object(LR, "read_reuse_hours", lambda: 24), \
                mock.patch.object(LR.L, "choose", lambda read, account=None: {"rungs": [{"rung": "call", "available": True}]}):
            self.assertIsNone(asyncio.run(LR._online_route("a", {"place_id": "x"}, {"what": "spa", "where": "Madrid"})))


class OneTotalInEuros(unittest.TestCase):
    """EU's walk: chat "€496 ALL IN", Trip tab "Hotels $340". The Trip tab's total is the basket's, the figure she says."""

    def _rows(self, cur="EUR"):
        return [{"kind": "flight", "state": "chosen", "price_amount": 85.0, "price_currency": cur, "price_source": "quoted"},
                {"kind": "flight", "state": "chosen", "price_amount": 98.3, "price_currency": cur, "price_source": "quoted"},
                {"kind": "stay", "state": "suggested", "price_amount": 312.8, "price_currency": cur, "price_source": "estimate"},
                {"kind": "flight", "state": "suggested", "price_amount": 999.0, "price_currency": cur, "price_source": "quoted"}]

    def _total(self, rows, trip="t1"):
        from booking_signer import basket as BK

        async def items(account, trip_id, states=None):
            return rows
        with mock.patch.object(BK, "items", items):
            return asyncio.run(LR.trip_total("a", trip))

    def test_the_figure_she_says(self):
        got = self._total(self._rows())
        self.assertEqual(got["total_eur"], 496.1)   # an unchosen flight is never counted
        self.assertEqual((got["flights_eur"], got["stays_eur"], got["stays_are"], got["trip_id"]), (183.3, 312.8, "estimates", "t1"))

    def test_nothing_until_priced_in_euros(self):
        self.assertIsNone(self._total([]))
        self.assertIsNone(self._total(self._rows("USD")))
        self.assertIsNone(self._total(self._rows(), trip=None))

    def test_persona_never_mentions_earlier_drafts(self):
        from app.agent import s2
        self.assertIn("never mentions an earlier draft", s2.S2_WHO)
        self.assertIn("never mentions an earlier draft", s2.S1_CAN)   # /next inherits it (241's parity)


class RehearsalNeverForRealAccounts(unittest.TestCase):
    def test_real_account_never_sees_the_test_venue(self):
        out = {"query": "tattoo studio in Madrid", "candidates": [{"place_id": "a"}, {"place_id": "b"}],
               "ranking": {"orders": {"rated": ["a", "b"]}}}
        real = "e359d295-0000-4000-8000-000000000242"
        with mock.patch.dict(os.environ, {"SASHA_REHEARSAL": "1", "FOUNDER_ACCOUNT_ID": ""}):
            self.assertEqual(LR._with_rehearsal(real, out), out)
            self.assertNotIn("Sasha Test Venue", str(LR._with_rehearsal(real, out)))


if __name__ == "__main__":
    unittest.main()
