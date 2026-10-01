"""S-64 step 10 · a booking form filled from reservation/1 (booking_signer/formfill.py).
⛔ GOLDEN: Psi's dry-run fields built from the object are today's fields exactly — the same filled_values_sha256.

    cd backend && python -m unittest tests.test_formfill -v
"""
from __future__ import annotations

import unittest

from booking_signer import formfill as FF, reservation as RS, venues as VN

ACCT = "00000000-0000-4000-8000-000000000001"
BODIES = [
    {"date": "2026-10-02", "time": "20:00", "party": 2, "name": "Tyler Warren", "email": "tyler@example.test", "phone": "+34608445715"},
    {"date": "2026-10-12", "time": "13:30", "party": 1, "name": "Anna Johnson", "email": "anna@example.test", "phone": "+351912000000"},
]


def obj(**over):
    o = {"schema": "reservation/1", "flow": "book",
         "who": {"name": "Tyler Warren", "account_id": ACCT, "contact": {"email": "t@x.test", "mobile_e164": "+34608445715"}},
         "what": {"activity": "a 60-minute massage", "activity_venue_lang": "un masaje de 60 minutos", "category": "beauty",
                  "service": "Masaje relajante 60 min"},
         "where": {"venue_name": "Spa", "timezone": "Europe/Madrid", "venue_ids": []},
         "when": {"mode": "at", "at": "2026-10-03T11:00"}, "how_many": {"count": 1, "unit": "people"},
         "extras": {"notes": "first visit"}}
    o.update(over)
    return RS.validate(o)


class Golden(unittest.TestCase):
    def test_psis_fields_from_the_object_are_todays_fields(self):
        for body in BODIES:
            p = VN.parse_particulars(body)
            want = VN.build_for_venue(VN.PSI, p, "dry_run")
            o = RS.from_particulars(p, account_id=ACCT, venue_name="Restaurante Psi", timezone="Europe/Lisbon", lang="pt", email=p.email)
            got = FF.fill(o, FF.PSI_FIELDS, date_fmt=VN.psi_date, time_fmt=VN.psi_time)
            self.assertEqual(got, want["task"]["fields"], body)
            self.assertEqual(VN._sha256hex(VN.filled_values_lines(got)), want["filled_values_sha256"])


class Rules(unittest.TestCase):
    FORM = [{"name": "date", "role": "date", "required": True}, {"name": "time", "role": "time", "required": True},
            {"name": "svc", "role": "service", "required": True, "options": ["Masaje relajante 60 min", "Masaje relajante 90 min"]},
            {"name": "n", "role": "person_name", "required": True}, {"name": "comments", "role": "free_text"},
            {"name": "terms", "role": "consent"}, {"name": "hp", "role": "trap"}]

    def stop(self, o, form):
        with self.assertRaises(FF.Stop) as e:
            FF.fill(o, form)
        return e.exception.rule

    def test_a_spa_form_is_filled_with_the_exact_service_and_nothing_ticked(self):
        got = {f["name"]: f["value"] for f in FF.fill(obj(), self.FORM)}
        self.assertEqual(got, {"date": "2026-10-03", "time": "11:00", "svc": "Masaje relajante 60 min", "n": "Tyler Warren",
                               "comments": "first visit"})                      # consent and the honeypot untouched

    def test_never_the_nearest_service(self):
        o = obj(what={"activity": "a massage", "activity_venue_lang": "un masaje", "category": "beauty", "service": "Masaje 60"})
        self.assertEqual(self.stop(o, self.FORM), "service_not_exact")

    def test_stops_instead_of_guessing(self):
        self.assertEqual(self.stop(obj(how_many={"count": 2, "unit": "sessions"}), [{"name": "p", "role": "party_size", "required": True}]), "unit_mismatch")
        self.assertEqual(self.stop(obj(flow="availability", when={"mode": "venue_proposes"}), self.FORM[:1]), "no_time")
        self.assertEqual(self.stop(obj(), [{"name": "c", "role": "challenge"}]), "challenge")
        self.assertEqual(self.stop(obj(), [{"name": "t", "role": "consent", "required": True}]), "consent")
        self.assertEqual(self.stop(obj(), [{"name": "dob", "role": "birth_date", "required": True, "label": "Fecha de nacimiento"}]), "required_unknown")
        self.assertEqual(self.stop(obj(who={"name": "Tyler Warren", "account_id": ACCT, "contact": {}}), [{"name": "e", "role": "email", "required": True}]), "email_missing")
        self.assertEqual(self.stop(obj(), [{"name": "g", "role": "given_name"}]), "name_split")
        self.assertEqual(self.stop(obj(), [{"name": "x", "role": "mystery"}]), "role_unknown")

    def test_a_split_name(self):
        got = FF.fill(obj(who={"name": "Maria de la Cruz", "account_id": ACCT}),
                      [{"name": "g", "role": "given_name"}, {"name": "f", "role": "family_name"}])
        self.assertEqual([x["value"] for x in got], ["Maria de la", "Cruz"])


if __name__ == "__main__":
    unittest.main()
