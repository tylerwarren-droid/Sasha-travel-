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


class SplitDay(unittest.TestCase):
    """Calma's listing (Sasha 60): 10:00–14:00 and 16:00–20:00 — closed between, whatever the other source says."""
    SPLIT = {"kind": "hours", "source_kind": "places", "source_label": "their Google listing",
             "detail": {"periods": [{"open": {"day": 1, "hour": 10, "minute": 0}, "close": {"day": 1, "hour": 14, "minute": 0}},
                                    {"open": {"day": 1, "hour": 16, "minute": 0}, "close": {"day": 1, "hour": 20, "minute": 0}}]}}

    def test_a_split_day_stays_split_and_the_gap_is_closed(self):
        read = {"facts": [SITE, self.SPLIT]}
        week, _ = H.merge(H.sources(read))
        self.assertEqual(week[0], [(time(10), time(14)), (time(16), time(20))])
        at_1500 = datetime(2026, 10, 5, 13, 0, tzinfo=timezone.utc)          # Monday 15:00 in Madrid
        st = H.status(read, at_1500, "Europe/Madrid")
        self.assertEqual((st["open_now"], st["opens_at"]), (False, "2026-10-05 16:00"))
        self.assertEqual(st["call_at"], "2026-10-05T14:10:00+00:00")           # 16:10 Madrid
        at_1100 = datetime(2026, 10, 5, 9, 0, tzinfo=timezone.utc)
        self.assertTrue(H.status(read, at_1100, "Europe/Madrid")["open_now"])


class Rule(unittest.TestCase):
    def test_site_first_and_the_later_opening_wins(self):
        srcs = H.sources(READ)
        self.assertEqual([s["kind"] for s in srcs], ["site", "places"])
        week, notes = H.merge(srcs)
        self.assertEqual(week[0], [(time(10), time(20))])
        self.assertIn("Mon: sources disagree (09:00–20:00 / 10:00–20:00) — using 10:00–20:00", notes)
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


class OpenAt(unittest.TestCase):
    """S-68 step 4 · open at the time the guest asked for, from a listing's periods — split days stay split."""

    def P(self, day, oh, om, ch, cm, cday=None):
        return {"open": {"day": day, "hour": oh, "minute": om}, "close": {"day": day if cday is None else cday, "hour": ch, "minute": cm}}

    def test_a_split_day_gap_is_closed(self):
        from datetime import datetime as dt
        week = H.from_places_periods([self.P(2, 10, 0, 14, 0), self.P(2, 17, 0, 21, 0)])   # Tuesday (Google day 2)
        self.assertEqual(H.open_at(week, dt(2026, 10, 6, 17, 0))["words"], "Open Tue 17:00")
        self.assertEqual(H.open_at(week, dt(2026, 10, 6, 15, 0)), {"known": True, "open": False, "words": "Closed Tue 15:00 (opens 17:00)"})
        self.assertEqual(H.open_at(week, dt(2026, 10, 6, 21, 0))["words"], "Closed Tue 21:00 (no later opening that day)")
        self.assertEqual(H.open_at(week, dt(2026, 10, 5, 12, 0))["words"], "Closed all day Mon")
        self.assertEqual(H.open_at({}, dt(2026, 10, 6, 17, 0)), {"known": False, "open": None, "words": "hours not listed"})

    def test_past_midnight_and_open_24_hours(self):
        from datetime import datetime as dt
        bar = H.from_places_periods([self.P(5, 20, 0, 2, 0, cday=6)])                      # Fri 20:00 – Sat 02:00
        self.assertEqual(H.open_at(bar, dt(2026, 10, 3, 1, 0))["words"], "Open Sat 01:00")
        self.assertEqual(H.open_at(bar, dt(2026, 10, 2, 23, 0))["words"], "Open Fri 23:00")
        self.assertFalse(H.open_at(bar, dt(2026, 10, 3, 3, 0))["open"])
        always = H.from_places_periods([{"open": {"day": 0, "hour": 0, "minute": 0}}])
        self.assertTrue(all(H.open_at(always, dt(2026, 10, d, 4, 0))["open"] for d in range(1, 8)))
