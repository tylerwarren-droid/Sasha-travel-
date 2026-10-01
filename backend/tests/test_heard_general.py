"""S-64 step 7 · heard.py generalised (§5): window, venue_proposes, units, duration, the meal; French, Italian, German.
The S-59 tests (tests/test_heard.py) run unchanged beside these.

    cd backend && python -m unittest tests.test_heard_general -v
"""
from __future__ import annotations

import unittest

from booking_signer import heard as H, reservation as RS

ACCT = "00000000-0000-4000-8000-000000000001"
TABLE = {"date": "2026-10-02", "time": "13:00", "party": 2, "name": "Tyler Warren"}   # Friday 2 Oct, 13:00, two


def obj(**over):
    o = {"schema": "reservation/1", "flow": "book", "who": {"name": "Tyler Warren", "account_id": ACCT},
         "what": {"activity": "a relaxing massage", "activity_venue_lang": "un masaje relajante", "category": "beauty"},
         "where": {"venue_name": "Spa", "timezone": "Europe/Madrid", "venue_ids": []},
         "when": {"mode": "at", "at": "2026-10-03T11:00", "duration_min": 60}, "how_many": {"count": 1, "unit": "people"}}
    o.update(over)
    return H.asked_from(RS.validate(o))


def whats(line, asked):
    return [m["what"] for m in H.mismatches([line], asked)]


class FrenchItalianGerman(unittest.TestCase):
    def test_times(self):
        self.assertEqual(whats("Oui, à treize heures, c'est noté.", TABLE), [])
        self.assertEqual(whats("Nous avons de la place à quinze heures.", TABLE), ["time"])
        self.assertEqual(whats("À midi, plutôt ?", TABLE), ["time"])
        self.assertEqual(whats("Va bene, alle tredici.", TABLE), [])
        self.assertEqual(whats("Va bene all'una.", TABLE), [])
        self.assertEqual(whats("Abbiamo posto alle tre.", TABLE), ["time"])
        self.assertEqual(whats("Ja, um 13 Uhr, gerne.", TABLE), [])
        self.assertEqual(whats("Wir hätten um drei etwas frei.", TABLE), ["time"])

    def test_party_day_and_name(self):
        self.assertEqual(whats("Une table pour 4 personnes ?", TABLE), ["party"])
        self.assertEqual(whats("Per due persone, va bene.", TABLE), [])
        self.assertEqual(whats("Für vier Personen?", TABLE), ["party"])
        self.assertEqual(whats("Samedi, alors ?", TABLE), ["day"])
        self.assertEqual(whats("Venerdì va bene.", TABLE), [])
        self.assertEqual(whats("Am Donnerstag?", TABLE), ["day"])
        self.assertEqual(whats("Au nom de Martin, c'est ça ?", TABLE), ["name"])
        self.assertEqual(whats("Auf den Namen Warren, gut.", TABLE), [])


class Window(unittest.TestCase):
    ASKED = None

    def setUp(self):
        self.asked = obj(when={"mode": "window", "window": {"earliest": "2026-10-03T10:00", "latest": "2026-10-03T13:00"}, "duration_min": 60})

    def test_a_time_inside_the_window_is_not_a_mismatch(self):
        self.assertEqual(whats("Vale, a las 11:30, el de 60.", self.asked), [])
        self.assertEqual(whats("A las doce, perfecto.", self.asked), [])

    def test_a_time_outside_it_is(self):
        self.assertEqual(whats("Solo a las cinco de la tarde.", self.asked), ["time"])
        self.assertEqual(whats("El domingo a las once.", self.asked), ["day"])


class VenueProposes(unittest.TestCase):
    def test_times_are_proposals_not_mismatches(self):
        asked = obj(flow="quote_first", when={"mode": "venue_proposes"},
                    what={"activity": "a fine-line tattoo", "activity_venue_lang": "a fine-line tattoo", "category": "beauty"},
                    how_many={"count": 1, "unit": "pieces"})
        line = "We could do Tuesday at 3 or Thursday at 4."
        self.assertEqual(whats(line, asked), [])
        self.assertEqual([p["hour"] for p in H.proposals([line])], [3, 4])


class UnitsDurationAndTheMeal(unittest.TestCase):
    def test_units(self):
        sessions = obj(how_many={"count": 1, "unit": "sessions"})
        self.assertEqual(whats("Serían dos sesiones, ¿vale?", sessions), ["count"])
        self.assertEqual(whats("Una sesión, perfecto.", sessions), [])
        self.assertEqual(whats("Para seis, ¿no?", {**TABLE, "party": 4}), ["party"])

    def test_duration(self):
        asked = obj()
        self.assertEqual(whats("Solo tenemos el de 90.", asked), ["duration"])
        self.assertEqual(whats("Sería hora y media.", asked), ["duration"])
        self.assertEqual(whats("Son 60 minutos, a las once.", asked), [])
        self.assertEqual(whats("A las 11 horas, perfecto.", asked), [])          # a time of day, not a length
        self.assertEqual(whats("It's a half-day session.", asked), ["duration"])

    def test_the_meal(self):
        lunch = {**TABLE, "activity": "lunch una mesa para comer"}
        self.assertEqual(whats("Para la cena tenemos sitio.", lunch), ["what"])
        self.assertEqual(whats("Para comer, a la una, perfecto.", lunch), [])
        self.assertEqual(whats("Reserva confirmada, la mesa está lista.", lunch), [])   # generic words never count


class Unchanged(unittest.TestCase):
    def test_la_contra_still_fails_on_time_and_name(self):
        off = H.mismatches(["Vale, a las tres de hora.", "¿Me puede me puede repetir apellido? Apellido Tyler"], TABLE)
        self.assertEqual([m["what"] for m in off], ["time", "name"])


if __name__ == "__main__":
    unittest.main()
