"""Sasha 386 · A RECORDED REPLY THAT ACTS WITH A DATE IS NEVER REPLAYED ON ANOTHER DAY.

Found by 386's recording run (166527ff, 17 Nov): "…Saturday at half past nine at night…" → "Which day?". The replay key leaves the
day's date out on purpose (recordings stay usable across days), so the reply recorded on Fri 13 Nov — hold_venue day 2026-11-14 — was
replayed on Tue 17 Nov: a past Saturday, not the one said; Sasha's reader rightly refused it. Now each recording keeps its day; a reply
whose tool call carries a date is usable only on that day, and a recording run re-records it.

    cd backend && python -m unittest tests.test_s386_dated_replies -v
"""
from __future__ import annotations

import asyncio
import unittest
from unittest import mock

from booking_signer import model_gateway as MG

run = asyncio.run
DATED = {"reply": {"content": [{"type": "tool_use", "name": "hold_venue", "input": {"day": "2026-11-14", "time": "21:30", "party": 3}}]},
         "build": None, "day": "2026-11-13"}
PLAIN = {"reply": {"content": [{"type": "text", "text": "Hello."}]}, "build": None, "day": "2026-11-13"}


class DatedReplies(unittest.TestCase):
    def test_a_dated_reply_holds_only_its_day(self):
        with mock.patch.object(MG, "recorded_on", lambda: "2026-11-13"):
            self.assertTrue(run(MG._usable(DATED)))
        with mock.patch.object(MG, "recorded_on", lambda: "2026-11-17"):
            self.assertFalse(run(MG._usable(DATED)))                                   # four days on: re-recorded, never replayed

    def test_an_undated_reply_holds_across_days(self):
        with mock.patch.object(MG, "recorded_on", lambda: "2026-11-17"):
            self.assertTrue(run(MG._usable(PLAIN)))

    def test_an_older_dated_recording_without_its_day_is_re_recorded(self):
        with mock.patch.object(MG, "recorded_on", lambda: "2026-11-17"):
            self.assertFalse(run(MG._usable({k: v for k, v in DATED.items() if k != "day"})))

    def test_every_recording_keeps_its_day(self):
        import inspect
        self.assertIn('"day": recorded_on()', inspect.getsource(MG._record))
        self.assertTrue(MG.dated(DATED))
        self.assertFalse(MG.dated(PLAIN))


if __name__ == "__main__":
    unittest.main()
