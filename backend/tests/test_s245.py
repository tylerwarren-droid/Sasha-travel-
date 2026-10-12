"""Sasha 245 · the claim guard sees fine print's and activities' prices as given (live, 244: every Lisbon price — "16 EUR",
"€12,00", amount_minor 1200 — failed it, and the forced rewrite made her "correct herself" for a check she had run). Invented
prices still fail. And CR 86's Outlook is offered where /you used to say Sasha doesn't read Outlook."""
from __future__ import annotations

import unittest

from app.agent import sasha as AG

CARDS = [{"name": "Museu Calouste Gulbenkian", "price": {"text": "16 EUR", "quote": "Museum – 16,00 €"}},
         {"name": "Oceanário de Lisboa", "price": {"text": "27.7 EUR", "quote": "12 PM - 3:30 PM | FREE | 16.6€ | 27.7€ | 18.8€"}},
         {"name": "MAAT", "price": {"text": "12 EUR", "quote": "Residentes em Portugal\nPrice\n€12,00", "amount": {"amount_minor": 1200, "currency": "EUR"}}},
         {"name": "Mosteiro dos Jerónimos", "price": {"text": "18 EUR", "quote": "Regular: 18.00 €"}}]


class GuardSeesActivityPrices(unittest.TestCase):
    def allowed(self):
        out: set = set()
        AG._amounts({"render": {"kind": "activities", "cards": CARDS}}, out)
        return out

    def test_the_prices_on_the_cards_may_be_said(self):
        a = self.allowed()
        for said in ("The Gulbenkian is €16.", "The Oceanário is €27.70 at midday.", "MAAT is €12.", "Jerónimos is €18.", "Kids are €16.60."):
            self.assertEqual(AG.guard_check(said, a, False), [], said)

    def test_an_invented_price_still_fails(self):
        a = self.allowed()
        for said in ("It's €14.", "About €25 each.", "€20 for two."):
            self.assertTrue(AG.guard_check(said, a, False), said)

    def test_money_forms(self):
        self.assertEqual([AG._money(x) for x in ("16,00", "1,200", "1.200,50", "27.7", "18.00", "12")], [16.0, 1200.0, 1200.5, 27.7, 18.0, 12.0])

    def test_minor_units(self):
        out: set = set()
        AG._amounts({"amount": {"amount_minor": 2500, "currency": "EUR"}}, out)
        self.assertIn(25.0, out)


if __name__ == "__main__":
    unittest.main()
