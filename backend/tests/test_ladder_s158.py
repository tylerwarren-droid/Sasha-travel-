"""Sasha 158 · search anything anywhere, name it, the no-slot request, cancelling an email booking. Offline.

    cd backend && python -m unittest tests.test_ladder_s158 -v
"""
import asyncio
import unittest
from datetime import date

from booking_signer import emailing as E, guest_whatsapp as GW
from booking_signer.handoff import booking_handoff, known_place, restaurant_time


def find(m):
    return (booking_handoff(m) or {}).get("booking_find")


class Search(unittest.TestCase):
    def test_any_kind_of_place_anywhere(self):
        for m, what, where in (("tattoo parlour in Istanbul", "tattoo parlour", "Istanbul"), ("a dentist in Buenos Aires", "dentist", "Buenos Aires"),
                               ("pottery class in Kyoto", "pottery class", "Kyoto"), ("I need a barber in Berlin", "barber", "Berlin"),
                               ("tattoo artist near Kreuzberg, Berlin", "tattoo artist", "Kreuzberg, Berlin")):
            f = find(m)
            self.assertEqual((f or {}).get("what"), what, m)
            self.assertEqual((f or {}).get("where"), where, m)

    def test_things_to_do_is_a_real_search(self):   # Sasha 175 (EU 172) · never the 4 Aug cache's priced list
        self.assertEqual(find("things to do in Kyoto"), {"what": "things to do", "where": "Kyoto"})
        self.assertEqual(find("something fun to do in Hoi An this evening"), {"what": "things to do", "where": "Hoi An", "country": "VN"})

    def test_seoul_is_not_sol(self):
        self.assertIsNone(known_place("Seoul"))
        self.assertEqual(find("nail salon in Seoul")["where"], "Seoul")
        self.assertEqual(known_place("Chambhuri")[0], "Chamberí")   # a real near-miss still corrects

    def test_not_a_search(self):
        for m in ("plan a 7 day trip in Vietnam", "what is the weather in Hanoi", "7 days in Hanoi",
                  "best time to visit Bali", "I like the food in Hanoi", "a hotel in Madrid for 2 nights"):
            self.assertIsNone(find(m), m)

    def test_one_sentence_before(self):
        self.assertEqual(booking_handoff("tattoo parlour in Istanbul")["response"], "Here are the best-rated tattoo parlours in Istanbul.")


class NameIt(unittest.TestCase):
    def test_a_venue_by_name(self):
        f = find("book Casa Lucio tomorrow at 9 for 2")
        self.assertEqual((f["what"], f["named"]), ("Casa Lucio", True))
        self.assertEqual(f["bare_time"]["hour"], 9)
        self.assertEqual(restaurant_time(f["bare_time"])[-5:], "21:00")   # a restaurant's "9" is the evening
        self.assertEqual(find("book casa lucio in Madrid on Friday at 21:00")["where"], "Madrid")
        self.assertEqual(find("book a table at Botín tonight at 8")["what"], "Botín")

    def test_a_kind_is_not_a_name(self):
        self.assertNotIn("named", find("book dinner for 2 in Madrid tomorrow") or {})

    def test_city_of_an_address(self):
        self.assertEqual(GW.city_of("Calle de la Cava Baja, 35, Centro, 28005 Madrid, Spain"), "Madrid")


class NoSlot(unittest.TestCase):
    def test_the_request_asks_for_a_date_and_a_quote(self):
        p = E.parse_quote_particulars({"name": "Tyler Warren", "email": "t@example.com",
                                       "quote": {"what": "a fine-line swallow on the wrist, about 5 cm", "dates": "any weekday in November",
                                                 "photos": ["https://x.example/a.jpg", "http://insecure/b.jpg"]}})
        self.assertEqual(p.photos, ("https://x.example/a.jpg",))
        e = E.compose("es", "Ink", "hola@ink.example", p, "11111111-1111-4111-8111-111111111111")
        self.assertEqual(e["kind"], "quote")
        self.assertIn("presupuesto", e["text"])
        self.assertIn("inteligencia artificial", e["text"])         # the AI disclosure, always
        self.assertIn("https://x.example/a.jpg", e["text"])
        self.assertIn("any weekday in November", e["text"])         # the dates that suit them, as they said them
        en = E.compose("en", "Ink", "hi@ink.example", p, "11111111-1111-4111-8111-111111111111")
        self.assertIn("a date you can offer and a quote", en["text"])

    def test_a_request_needs_words(self):
        with self.assertRaises(E.EmailRefused):
            E.parse_quote_particulars({"name": "Tyler Warren", "email": "t@example.com", "quote": {"what": "x"}})


class Wording(unittest.TestCase):
    def test_the_guest_sees_what_is_sent_not_the_machinery(self):
        lines = ["I'll email X at a@b.c — the address on their website — from Sasha <s@k.ai>.", "You're copied privately (BCC) at …",
                 "Their reply comes to me at act-…", "Subject: Solicitud", "Hola, soy Sasha…", "Shall I send it?"]
        self.assertEqual(GW.guest_lines("email", lines), ["Hola, soy Sasha…"])
        self.assertEqual(GW.DONE_ASKED, "Done — I've asked them and I'll confirm here as soon as they reply.")


class CancelByEmail(unittest.TestCase):
    def test_an_email_booking_is_found_for_its_cancellation(self):
        from booking_signer import ladder_store as LS
        s = LS.MemoryLadderStore()
        s.emails["e1"] = {"email_id": "e1", "account_id": "a", "trip_item_id": "t1", "read_id": "r1", "status": "sent"}
        got = asyncio.run(s.email_for_item("a", "t1"))
        self.assertEqual(got["email_id"], "e1")
        self.assertIsNone(asyncio.run(s.email_for_item("someone-else", "t1")))


if __name__ == "__main__":
    unittest.main()
