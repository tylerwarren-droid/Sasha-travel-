"""S-64 step 1 · `reservation/1` (booking_signer/reservation.py): validation, canonical sha, from_particulars.

    cd backend && python -m unittest tests.test_reservation -v
"""
from __future__ import annotations

import copy
import unittest

from booking_signer import calls as C, emailing as E, reservation as RS, venue_read as V

ACCT = "00000000-0000-4000-8000-000000000001"


def base(**over):
    o = {"schema": "reservation/1", "flow": "book",
         "who": {"name": "Tyler Warren", "account_id": ACCT, "contact": {}},
         "what": {"activity": "lunch", "activity_venue_lang": "una mesa para comer", "category": "restaurant"},
         "where": {"venue_name": "La Contra", "timezone": "Europe/Madrid", "venue_ids": ["places:ChIJ-x"]},
         "when": {"mode": "at", "at": "2026-10-02T13:00"},
         "how_many": {"count": 4, "unit": "people"}}
    for k, v in over.items():
        o[k] = v
    return o


class Examples(unittest.TestCase):
    """S-64 §6 — each worked example is a valid object."""

    def test_la_contra_a_table(self):
        o = RS.validate(base())
        self.assertEqual(o["extras"], {"constraints": {"no_deposit": True, "no_card": True}})

    def test_king_ink_quote_first_then_book(self):
        quote = RS.validate(base(flow="quote_first",
            what={"activity": "a fine-line tattoo on the forearm, about 10 cm", "activity_venue_lang": "a fine-line tattoo on the forearm, about 10 cm",
                  "category": "beauty", "spec": "fine-line, forearm, about 10 cm", "photos": ["asset:1", "asset:2"]},
            where={"venue_name": "King Ink Tattoos", "timezone": "Africa/Nairobi", "venue_ids": []},
            when={"mode": "venue_proposes"}, how_many={"count": 1, "unit": "pieces"}))
        self.assertEqual(quote["when"], {"mode": "venue_proposes"})
        book = RS.validate(base(where={"venue_name": "King Ink Tattoos", "timezone": "Africa/Nairobi", "venue_ids": []},
                                when={"mode": "at", "at": "2026-10-08T15:00", "duration_min": 120}, how_many={"count": 1, "unit": "sessions"},
                                what={"activity": "tattoo session", "activity_venue_lang": "tattoo session", "category": "beauty"}))
        self.assertEqual(book["when"]["duration_min"], 120)

    def test_the_kayak_tour_with_a_fixed_start(self):
        o = RS.validate(base(what={"activity": "a 3-hour kayak tour", "activity_venue_lang": "passeio de caiaque de 3 horas", "category": "experience"},
                             where={"venue_name": "Kayak Lisboa", "timezone": "Europe/Lisbon", "venue_ids": []},
                             when={"mode": "at", "at": "2026-10-03T09:30", "fixed_start": True, "duration_min": 180},
                             how_many={"count": 2, "unit": "people"}))
        self.assertTrue(o["when"]["fixed_start"])

    def test_the_spa_window(self):
        o = RS.validate(base(what={"activity": "a 60-minute relaxing massage", "activity_venue_lang": "un masaje relajante de 60 minutos",
                                   "category": "beauty", "service": "Masaje relajante 60 min"},
                             when={"mode": "window", "window": {"earliest": "2026-10-03T10:00", "latest": "2026-10-03T13:00"}, "duration_min": 60},
                             how_many={"count": 1, "unit": "people"}))
        self.assertEqual(o["when"]["window"]["latest"], "2026-10-03T13:00")


class Rules(unittest.TestCase):
    def refused(self, obj):
        with self.assertRaises(RS.ReservationRefused) as e:
            RS.validate(obj)
        return e.exception.rule

    def test_nothing_is_guessed(self):
        o = base()
        del o["how_many"]
        self.assertEqual(self.refused(o), "unit_invalid")
        o = base()
        o["when"] = {"mode": "at"}
        self.assertEqual(self.refused(o), "when_invalid")
        o = base()
        o["when"] = {"mode": "window", "window": {"earliest": "2026-10-03T10:00"}}
        self.assertEqual(self.refused(o), "when_invalid")

    def test_a_booking_needs_a_time(self):
        self.assertEqual(self.refused(base(when={"mode": "venue_proposes"})), "when_invalid")

    def test_no_deposit_no_card_cannot_be_changed(self):
        self.assertEqual(self.refused(base(extras={"constraints": {"no_deposit": False, "no_card": True}})), "constraints_fixed")

    def test_unknown_fields_and_bad_values(self):
        self.assertEqual(self.refused(base(price=10)), "field_unknown")
        self.assertEqual(self.refused(base(when={"mode": "at", "at": "2026-02-30T13:00"})), "when_invalid")
        self.assertEqual(self.refused(base(when={"mode": "at", "at": "2026-10-02T13:00+02:00"})), "when_invalid")
        self.assertEqual(self.refused(base(what={"activity": "lunch", "activity_venue_lang": "comida", "category": "golf"})), "category_invalid")
        self.assertEqual(self.refused(base(where={"venue_name": "X", "timezone": "Mars/Base", "venue_ids": []})), "timezone_invalid")
        self.assertEqual(self.refused(base(who={"name": "R2-D2", "account_id": ACCT})), "name_invalid")

    def test_the_hash_is_canonical_and_moves_with_any_change(self):
        a = base()
        b = copy.deepcopy(a)
        b["who"] = {"contact": {}, "account_id": ACCT, "name": "Tyler  Warren"}   # key order and spacing: same object
        self.assertEqual(RS.sha256(a), RS.sha256(b))
        c = copy.deepcopy(a)
        c["when"]["at"] = "2026-10-02T13:30"
        self.assertNotEqual(RS.sha256(a), RS.sha256(c))
        self.assertRegex(RS.sha256(a), r"^[0-9a-f]{64}$")


class FromParticulars(unittest.TestCase):
    def test_todays_call_particulars_become_the_object(self):
        p = C.parse_call_particulars({"date": "2026-10-02", "time": "13:00", "party": 2, "name": "Tyler Warren", "phone": "+34 608 445 715"})
        o = RS.from_particulars(p, account_id=ACCT, venue_name="La Contra", timezone="Europe/Madrid", lang="es",
                                venue_ids=["places:ChIJ-x"], read_id="r1")
        self.assertEqual(o["when"], {"mode": "at", "at": "2026-10-02T13:00"})
        self.assertEqual(o["how_many"], {"count": 2, "unit": "people"})
        self.assertEqual(o["what"]["activity_venue_lang"], "una mesa")
        self.assertEqual(o["who"]["contact"], {"mobile_e164": "+34608445715"})
        self.assertEqual(RS.columns(o)["party_size"], 2)

    def test_todays_email_particulars_carry_the_guest_email(self):
        p = E.parse_email_particulars({"date": "2026-10-02", "time": "13:00", "party": 2, "name": "Tyler Warren", "email": "t@example.test"},
                                      C.parse_call_particulars)
        o = RS.from_particulars(p, account_id=ACCT, venue_name="La Contra", timezone="Europe/Madrid", lang="es")
        self.assertEqual(o["who"]["contact"], {"email": "t@example.test"})


class Kenya(unittest.TestCase):
    def test_a_nairobi_number_is_read(self):
        self.assertEqual(V.to_e164("0725 909 800", "KE"), "+254725909800")
        self.assertEqual(V.COUNTRIES["KE"][2:], ("en", "Africa/Nairobi"))


if __name__ == "__main__":
    unittest.main()
