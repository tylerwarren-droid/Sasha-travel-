"""Sasha 140 · speed: cards never wait on photos (a budget, then the late ones follow on their own); each venue's own photo is
cached by its website; a recent read of the same listing is reused (its Google facts re-read now).

    cd backend && python -m unittest tests.test_perf_s140 -v
"""
from __future__ import annotations

import asyncio
import os
import time
import unittest
from unittest import mock

from booking_signer import guest_whatsapp as GW, style as ST
from tests import test_guest_whatsapp_s75 as TG


class Photos(unittest.TestCase):
    def setUp(self):
        GW.PHOTO_CACHE.clear()
        self.calls = []

    def test_a_photo_is_fetched_once_then_cached_with_none_remembered(self):
        async def page_text(http, url, resolve):
            self.calls.append(url)
            return {"image": "https://a.example/og.jpg"} if "a." in url else {"why": "no image"}
        with mock.patch.object(ST, "page_text", page_text):
            shown = [{"place_id": "a", "website": "https://a.example"}, {"place_id": "b", "website": "https://b.example"}]
            self.assertEqual(asyncio.run(GW._photos("x", "dinner", shown)), {"a": "https://a.example/og.jpg"})
            asyncio.run(GW._photos("x", "dinner", shown))
        self.assertEqual(sorted(self.calls), ["https://a.example", "https://b.example"])   # once each, "none" remembered too

    def test_slow_photos_never_hold_the_cards(self):
        async def page_text(http, url, resolve):
            await asyncio.sleep(0.5 if "slow" in url else 0)
            return {"image": url + "/og.jpg"}
        with mock.patch.object(ST, "page_text", page_text):
            async def go():
                t = time.perf_counter()
                ready, late = await GW._photos_within([{"place_id": "f", "website": "https://fast.example"},
                                                       {"place_id": "s", "website": "https://slow.example"}], 0.1)
                took = time.perf_counter() - t
                for x in late:
                    x.cancel()
                return ready, late, took
            ready, late, took = asyncio.run(go())
        self.assertEqual(list(ready), ["f"])
        self.assertEqual(len(late), 1)
        self.assertLess(took, 0.3)


class Cards(TG.Base):
    def test_the_cards_go_within_the_budget_and_late_photos_follow(self):
        self.link()
        GW.PHOTO_CACHE.clear()

        async def page_text(http, url, resolve):
            await asyncio.sleep(5)
            return {"image": "https://x/og.jpg"}
        cands = [{**c, "website": f"https://site{i}.example"} for i, c in enumerate(TG.CANDS)]
        with mock.patch.object(ST, "page_text", page_text), mock.patch.object(TG, "CANDS", cands), \
                mock.patch.dict(os.environ, {"SASHA_PHOTO_WAIT_S": "0.05"}):
            t = time.perf_counter()
            self.say("dinner for 2 in Chamberí on Saturday at 9")
            took = time.perf_counter() - t
        self.assertLess(took, 1.0)                                   # not the 5 s the photos would take
        self.assertEqual(GW.SENDER.contents[-1][0], "Which one?")
        self.assertIn("_late_photos", self.spawned)


class ReadReuse(unittest.TestCase):
    def test_a_recent_read_of_the_same_listing_is_reused(self):
        from datetime import datetime, timedelta, timezone
        from booking_signer import ladder_store as LS
        s = LS.MemoryLadderStore()
        now = datetime.now(timezone.utc)
        asyncio.run(s.put_read({"read_id": "r1", "account_id": "a", "query": {"place_id": "P"}, "read": {}, "created_at": now - timedelta(hours=1)}))
        asyncio.run(s.put_read({"read_id": "r0", "account_id": "a", "query": {"place_id": "P"}, "read": {}, "created_at": now - timedelta(hours=9)}))
        self.assertEqual(asyncio.run(s.recent_read("a", "P", now - timedelta(hours=6)))["read_id"], "r1")
        self.assertIsNone(asyncio.run(s.recent_read("b", "P", now - timedelta(hours=6))))   # never another account's
        self.assertIsNone(asyncio.run(s.recent_read("a", "P", now - timedelta(minutes=30))))
