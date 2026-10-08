"""Sasha 212 · C (no raw figures spoken), D (a proposal offered, never done), A's words (booked only when booked; a
failure said plainly with the next step).

    cd backend && python -m unittest tests.test_spoken_s212 -v
"""
import re
import unittest

from app.agent import sasha as AG, spoken as SP
from booking_signer import live_events as LE


class Spoken(unittest.TestCase):
    def test_money_is_rounded_and_in_words(self):
        self.assertEqual(SP.speakable("The whole trip comes to €4,213.47 for the two of you."),
                         "The whole trip comes to about four thousand two hundred euros for the two of you.")
        self.assertEqual(SP.speakable("About £4,200 all in."), "About four thousand two hundred pounds all in.")
        self.assertEqual(SP.speakable("It's 2,770.81 euros."), "It's about two thousand eight hundred euros.")

    def test_dates_and_times_are_written_out(self):
        self.assertEqual(SP.speakable("It leaves at 08:30 on Saturday 21 November and lands at 21:05."),
                         "It leaves at eight thirty in the morning on Saturday the twenty-first of November and lands at nine oh five in the evening.")
        self.assertEqual(SP.speakable("Home on 2026-12-03, a table at 9pm."), "Home on the third of December, a table at nine in the evening.")

    def test_names_and_codes_digit_by_digit_and_nothing_left_as_a_figure(self):
        self.assertEqual(SP.speakable("222 Tattoo is lovely."), "Two two two Tattoo is lovely.")
        self.assertIn("IB six four five three", SP.speakable("Iberia IB6453 at 9:30 p.m."))
        for t in ("12 days, 11 nights, 3 people, €120/night, the 1st, 50 metres", "Hotel 1898 · €1,468"):
            self.assertIsNone(re.search(r"\d", SP.speakable(t)), SP.speakable(t))

    def test_the_display_keeps_its_digits(self):
        t = "The whole trip comes to €4,213.47."
        SP.speakable(t)
        self.assertEqual(t, "The whole trip comes to €4,213.47.")


class Offered(unittest.TestCase):
    def test_a_proposal_is_offered_never_done(self):
        for done in ("I've put together your Ecuador trip!", "Here's what I've put together, Tyler.", "I've put your trip together.",
                     "I've planned your Japan itinerary for you two."):
            self.assertIn("for your consideration", AG.as_offer(done), done)
        self.assertEqual(AG.as_offer("I've booked a table."), "I've booked a table.")
        self.assertEqual(AG.as_offer("Here's what I've put together for your consideration, Alex."),
                         "Here's what I've put together for your consideration, Alex.")   # never twice


class PaymentWords(unittest.TestCase):
    def test_booked_names_the_email_only_when_it_went(self):
        w = LE.words_for({"status": "booked"}, "tyler@kanoe.ai")
        self.assertEqual(w["text"], "That's gone through — you're booked. Your confirmation is on its way to tyler@kanoe.ai, "
                                    "and your full itinerary is here.")
        self.assertNotIn("@", w["spoken"])
        self.assertNotIn("confirmation", LE.words_for({"status": "booked"}, None)["text"])

    def test_a_failure_is_said_plainly_with_the_next_step_never_booked(self):
        w = LE.words_for({"status": "failed", "failed": ["Iberia IB6453: the fare was withdrawn"]}, None)
        self.assertNotIn("you're booked", w["text"])
        self.assertIn("didn't", w["text"])
        self.assertTrue(w["text"].endswith("?"))
        p = LE.words_for({"status": "failed", "booked": ["Hotel X"], "failed": ["the flight home"]}, None)
        self.assertIn("not everything", p["text"])


if __name__ == "__main__":
    unittest.main()
