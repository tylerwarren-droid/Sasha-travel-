"""S-66 · is the venue open? (booking_signer/hours.py) — its own site first, then Google; the later opening wins.

    cd backend && python -m unittest tests.test_hours -v
"""
from __future__ import annotations

import unittest
from datetime import datetime, time, timezone

from booking_signer import hours as H

# Calma, 1 Oct 2026: its site says 09:00, its Google listing says Monday 10:00
SITE = {"kind": "hours", "source_kind": "site", "source_label": "their website, calmadrid.com",
        "detail": {"week": {str(d): [["09:00", "20:00"]] for d in range(5)}}}
GOOGLE_PERIODS = [{"open": {"day": d, "hour": 10, "minute": 0}, "close": {"day": d, "hour": 20, "minute": 0}} for d in range(1, 6)] + \
                 [{"open": {"day": 6, "hour": 10, "minute": 0}, "close": {"day": 6, "hour": 14, "minute": 0}}]
GOOGLE = {"kind": "hours", "source_kind": "places", "source_label": "their Google listing (Calma Madrid Masajes)",
          "detail": {"periods": GOOGLE_PERIODS}}
READ = {"facts": [GOOGLE, SITE]}
MON_0930_MADRID = datetime(2026, 10, 5, 7, 30, tzinfo=timezone.utc)


class Parse(unittest.TestCase):
    def test_schema_org_both_forms(self):
        self.assertEqual(H.from_jsonld({"openingHours": "Mo-Fr 09:00-20:00"})[4], [(time(9), time(20))])
        spec = {"openingHoursSpecification": [{"dayOfWeek": ["https://schema.org/Saturday"], "opens": "10:00", "closes": "14:00"}]}
        self.assertEqual(H.from_jsonld(spec), {5: [(time(10), time(14))]})

    def test_google_counts_from_sunday(self):
        w = H.from_places_periods(GOOGLE_PERIODS)
        self.assertEqual((w[0], w[5]), ([(time(10), time(20))], [(time(10), time(14))]))
        self.assertNotIn(6, w)                                         # Sunday: closed


class Rule(unittest.TestCase):
    def test_site_first_and_the_later_opening_wins(self):
        srcs = H.sources(READ)
        self.assertEqual([s["kind"] for s in srcs], ["site", "places"])
        week, notes = H.merge(srcs)
        self.assertEqual(week[0], [(time(10), time(20))])
        self.assertIn("Mon: sources disagree (09:00, 10:00 opening) — using 10:00–20:00", notes)
        self.assertNotIn(5, week)                                      # Saturday: the site does not list it — closed
        self.assertIn("Sat: one source lists it closed — treated as closed", notes)

    def test_calma_at_0930_is_closed_and_is_called_at_1010(self):
        st = H.status(READ, MON_0930_MADRID, "Europe/Madrid")
        self.assertEqual((st["known"], st["open_now"], st["local_now"], st["opens_at"]), (True, False, "2026-10-05 09:30", "2026-10-05 10:00"))
        self.assertEqual(st["call_at"], "2026-10-05T08:10:00+00:00")
        self.assertEqual(H.read_back_line(st, email_now=False),
                         "If they're closed when you say yes, I'll call when they open — they open at 10:00 on 2026-10-05, so I'd call at 10:10. Your yes covers that call.")

    def test_open_now_and_unknown(self):
        st = H.status(READ, datetime(2026, 10, 5, 9, 0, tzinfo=timezone.utc), "Europe/Madrid")   # 11:00 Madrid
        self.assertTrue(st["open_now"])
        self.assertEqual(st["opens_at"], "2026-10-06 10:00")                                   # what the read-back would promise
        self.assertEqual(H.status({"facts": []}, MON_0930_MADRID, "Europe/Madrid")["known"], False)
        self.assertIsNone(H.read_back_line(H.status({"facts": []}, MON_0930_MADRID, "Europe/Madrid"), False))


if __name__ == "__main__":
    unittest.main()
