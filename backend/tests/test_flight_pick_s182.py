"""Sasha 182 · the live loop of 7 Oct: every flight pick re-ran the search. Each of the founder's own words, and the other ways."""
import unittest

from booking_signer.flight_pick import pick, named_missing, is_flight_list

O = [{"name": "Air China", "detail": "07:44 LHR → HAN", "price": "€1,027.17 total for 2", "provider_amount": "1027.17"},
     {"name": "China Eastern Airlines", "detail": "12:10", "price": "€1,099.42 total for 2", "provider_amount": "1099.42"},
     {"name": "China Eastern Airlines", "detail": "MU 9662 · 21:05", "price": "€1,099.42 total for 2", "provider_amount": "1099.42"}]


class Pick(unittest.TestCase):
    def test_the_founders_words(self):
        self.assertEqual(pick("The China Eastern airline, the first China Eastern airline. Can we book that, please?", O), 1)
        self.assertEqual(pick("Can I book the first Air China flight, please?", O), 0)
        self.assertEqual(pick("Okay. Thank you. Let's let's let's forget about the flights. No flights.", O), "none")
        self.assertEqual(pick("Sasha, let's book it.", O), 0)

    def test_every_other_way(self):
        for m, i in (("the second one", 1), ("MU 9662", 2), ("the 21:05 one", 2), ("the one for 1099", 1), ("this one", 0),
                     ("the cheapest", 0), ("the last one", 2), ("number 2", 1)):
            self.assertEqual(pick(m, O), i, m)
        self.assertIsNone(pick("what's the weather in Hanoi", O))

    def test_an_airline_not_on_the_list_is_said_never_swapped(self):
        bo = [{"name": "British Airways"}, {"name": "Duffel Airways"}, {"name": "China Eastern Airlines"}]
        self.assertEqual(named_missing("Can I book the first Air China flight, please?", bo), "Air China")
        self.assertIsNone(named_missing("the first China Eastern", bo))

    def test_the_list_and_the_read_back_are_recognised(self):
        self.assertTrue(is_flight_list("I found a few flights to Hanoi from London — …"))
        self.assertTrue(is_flight_list("British Airways — … Here's exactly what I'll book (TEST — no real ticket"))


class TapToPay(unittest.TestCase):
    def test_it_never_crashes_before_the_phone(self):   # live 7 Oct: an unset variable — every flight/hotel/trip payment 500'd
        import asyncio
        from booking_signer import guest_whatsapp as GW
        said = asyncio.run(GW.tap_to_pay(None, "€1.00", "Duffel Airways ZZ 3829 (TEST stand-in)", "https://checkout.stripe.com/c/pay/cs_test_x"))
        self.assertEqual(said, "not sent: no account")


if __name__ == "__main__":
    unittest.main()
