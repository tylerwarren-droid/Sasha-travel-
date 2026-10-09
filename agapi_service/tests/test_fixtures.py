"""CR 64 · DIVE PREP — the hosted fake supplier /fixtures/taverna: a real form an agent can fill (date, time, party size, name), a
confirmation page with a reference, a supplier's real refusals — and nothing leaves the sandbox.

    python -m unittest agapi_service.tests.test_fixtures -v      (from the repo root)
"""
from __future__ import annotations

import re
import unittest
from datetime import date, timedelta

from agapi_service import config  # noqa: F401
from agapi_service import fixtures as FX
from agapi_service.tests.test_service import Base


def next_weekday(wd: int, after: int = 3) -> str:
    d = date.today() + timedelta(days=after)
    while d.weekday() != wd:
        d += timedelta(days=1)
    return d.isoformat()


class Taverna(Base):
    def book(self, **over):
        f = {"date": next_weekday(4), "time": "21:00", "party_size": "4", "name": "Ana Ejemplo"}
        f.update(over)
        return self.client.post("/fixtures/taverna/book", data=f)

    def test_the_form_an_agent_fills(self):
        r = self.client.get("/fixtures/taverna")
        self.assertEqual(r.status_code, 200)
        for marker in ('id="booking-form"', 'name="date"', 'name="time"', 'name="party_size"', 'name="name"', 'id="book"',
                       'name="robots" content="noindex,nofollow"', "not a real restaurant", FX.WHATSAPP):
            self.assertIn(marker, r.text)
        self.assertEqual(r.headers["x-robots-tag"], "noindex, nofollow")

    def test_a_booking_is_confirmed_with_a_reference_and_can_be_read_again(self):
        r = self.book()
        self.assertEqual(r.status_code, 201)
        ref = re.search(r'id="reference">(TAV-[0-9A-F]{6})<', r.text).group(1)
        self.assertIn('data-party="4"', r.text)
        self.assertIn('data-time="21:00"', r.text)
        again = self.client.get(f"/fixtures/taverna/booking/{ref}")
        self.assertEqual((again.status_code, ref in again.text), (200, True))
        self.assertEqual(self.client.get("/fixtures/taverna/booking/TAV-000000").status_code, 404)

    def test_a_suppliers_real_refusals(self):
        for over, words in [({"date": next_weekday(0)}, "closed on Mondays"), ({"party_size": "10"}, "WhatsApp"),
                            ({"date": next_weekday(5), "time": "21:00"}, "full at 21:00"), ({"time": "18:00"}, "one of our times"),
                            ({"date": (date.today() - timedelta(days=1)).isoformat()}, "from today"), ({"name": ""}, "a name"),
                            ({"name": "<script>x</script>"}, "a name"), ({"date": "not-a-date"}, "choose a date")]:
            r = self.book(**over)
            self.assertIn(r.status_code, (400, 409), over)
            self.assertIn('id="refusal"', r.text)
            self.assertIn(words, r.text, over)
            self.assertNotIn('id="reference"', r.text)

    def test_names_are_escaped_and_nothing_goes_out(self):
        r = self.book(name="O'Brien & Co")
        self.assertIn("O&#x27;Brien &amp; Co", r.text)
        # the sandbox's network guard is on in every test (ZeroLiveCalls): the fixture is a local page, it calls nothing


if __name__ == "__main__":
    unittest.main()
