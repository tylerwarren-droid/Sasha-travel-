"""CR 45 · CampusMe confirmations: the school's own confirmation (its page after the family's press, or its email pasted here)
is checked against what was prepared — school, student, date, time — and its number kept: "Registered ✓ — Yale, Mon 16 Nov
9:30am, confirmation #…". No confirmation, or one that doesn't match: "Registration not confirmed", never assumed.

    cd backend && python -m unittest tests.test_campus_confirm_cr45 -v
"""
from __future__ import annotations

import os
from unittest import mock

from products import store as ST
from products.campus import confirm as CF, schools as SC, tour as TR
from tests import test_guest_whatsapp_s75 as TG
from tests.test_tour_cr38 import Base

run = TG.run
YALE = CF.expect(SC.SCHOOLS["yale"], {"day": "2026-11-16", "start": "09:30"}, "Prueba")
PAGE = ("Thank you for registering, Prueba! Campus Tour — Monday, November 16, 2026 at 9:30 AM. "
        "Your confirmation number: YL-48213. We look forward to seeing you.")


class Read(TG.unittest.TestCase):
    def test_the_schools_page_matching_with_its_number(self):
        r = CF.read(PAGE, YALE, from_page=True)
        self.assertTrue(r["confirmed"])
        self.assertEqual(r["number"], "YL-48213")
        self.assertEqual(CF.line(YALE, r), "Registered ✓ — Yale, Mon 16 Nov 9:30am, confirmation #YL-48213")

    def test_another_time_or_day_is_not_confirmed(self):
        r = CF.read(PAGE.replace("9:30 AM", "1:30 PM"), YALE, from_page=True)
        self.assertFalse(r["confirmed"])
        self.assertIn("another time (13:30)", CF.line(YALE, r))
        r = CF.read(PAGE.replace("November 16", "November 17"), YALE, from_page=True)
        self.assertIn("another day (November 17)", CF.line(YALE, r))

    def test_no_confirmation_never_assumed(self):
        r = CF.read("Please complete the required fields.", YALE, from_page=True)
        self.assertFalse(r["confirmed"])
        self.assertTrue(CF.line(YALE, r).startswith("Registration not confirmed"))
        self.assertTrue(CF.line(YALE, None).startswith("Registration not confirmed — no confirmation from Yale"))

    def test_an_email_must_name_the_school_and_the_student(self):
        self.assertFalse(CF.read(PAGE, YALE)["confirmed"])                    # an email that never says "Yale"
        self.assertTrue(CF.read(PAGE + " — Yale Undergraduate Admissions", YALE)["confirmed"])
        self.assertFalse(CF.read(PAGE.replace("Prueba", "Alex") + " Yale", YALE)["confirmed"])


class OnATour(Base):
    def prepared(self):
        with mock.patch.dict(os.environ, {"FOUNDER_ACCOUNT_ID": TG.ACCOUNT, "BROWSERBASE_API_KEY": "k"}):
            self.through_intake()
            self.say("", payload=f"cm:tyes:{self.pend()['tour']['sha']}")
        return self.pend()["tour"]["case_id"]

    def visit(self, cid, school):
        return next(v for v in run(ST.STORE.get(cid))["state"]["plan"]["visits"] if v["school"] == school)

    def test_the_page_after_the_press_lands_on_that_visit(self):
        cid = self.prepared()
        run(TR._status(cid, "yale", "filled — waiting for your press", "h-yale"))
        x = self.visit(cid, "yale")["session"]
        from datetime import date
        d = date.fromisoformat(x["day"])
        h, mi = map(int, x["start"].split(":"))
        page = (f"Thank you for registering, Prueba! Campus Tour — {d.strftime('%A, %B')} {d.day}, {d.year} at "
                f"{h % 12 or 12}:{mi:02d} {'AM' if h < 12 else 'PM'}. Confirmation number: YL-90001.")
        run(TR._live_done({"id": "h-yale", "answer_text": page, "answered_at": "2026-10-06T21:00:00"}))
        v = self.visit(cid, "yale")
        self.assertTrue(v["status"].startswith("Registered ✓ — Yale"))
        self.assertTrue(v["status"].endswith("confirmation #YL-90001"))
        self.assertEqual(v["confirmation"]["source"], "the school's page after your press")

    def test_registered_on_its_own_is_not_confirmed_then_the_email_decides(self):
        cid = self.prepared()
        self.say("registered Brown")
        self.assertIn("I'll mark it registered when its confirmation says so", self.said())
        self.assertTrue(self.visit(cid, "brown")["status"].startswith("Registration not confirmed"))
        x = self.visit(cid, "brown")["session"]
        from datetime import date
        d = date.fromisoformat(x["day"])
        h, mi = map(int, x["start"].split(":"))
        self.say(f"Brown University Admission: Thank you for registering, Prueba. Information Session and Campus Tour on "
                 f"{d.strftime('%B')} {d.day}, {d.year} at {h % 12 or 12}:{mi:02d} {'AM' if h < 12 else 'PM'}. "
                 "Registration number BR-7731.")
        self.assertIn("✅ Registered ✓ — Brown", self.said())
        self.assertTrue(self.visit(cid, "brown")["status"].endswith("confirmation #BR-7731"))


def load_tests(loader, tests, pattern):
    suite = TG.unittest.TestSuite()
    suite.addTests(loader.loadTestsFromTestCase(Read))
    for n in ("test_the_page_after_the_press_lands_on_that_visit", "test_registered_on_its_own_is_not_confirmed_then_the_email_decides"):
        suite.addTest(OnATour(n))
    return suite


if __name__ == "__main__":
    TG.unittest.main()
