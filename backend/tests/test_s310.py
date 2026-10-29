"""Sasha 310 · the stay's nights change proved live (AgAPI CR 138); My trips draws a stay as AgAPI's record has it; the morning brief,
like every reminder, re-reads the record at the send — a booking cancelled after it was planned is never in it.

    cd backend && python -m unittest tests.test_s310 -v
"""
from __future__ import annotations

import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class TheBriefReadsTheRecordAtTheSend(unittest.TestCase):
    def test_only_the_bookings_still_on_the_record(self):
        src = (ROOT / "booking_signer" / "proactive.py").read_text()
        self.assertIn('live = {r["id"]: r for r in now_rows}', src)
        self.assertIn('extra = {**extra, "items": [live[x["id"]] for x in extra.get("items") or [] if x.get("id") in live]}', src)
        self.assertIn('"skipped: nothing left on the record today"', src)
        self.assertNotIn('if kind != "morning_brief" else b\\n', src.replace("\r", ""))   # the brief no longer keeps its own list


class MyTripsHasTheStayAsRecorded(unittest.TestCase):
    def test_my_plans_carries_check_in_check_out_nights(self):
        src = (ROOT / "agapi" / "s2_manage.py").read_text()
        self.assertIn('"nights", "check_in", "check_out", "change_answer"', src)


if __name__ == "__main__":
    unittest.main()
