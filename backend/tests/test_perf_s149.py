"""Sasha 149 · performance round 2, the parts that change behaviour. Offline.
  · the database: no session reset on release (one round trip fewer per query); prepared statements cached only on a
    session pooler; one connection always open;
  · outbound HTTP: one pooled, kept-alive client per event loop;
  · WhatsApp (SASHA_STREAM_CARDS=1): the header goes first, then each card the moment its OWN photo is ready, in rank
    order; a slow photo holds only its own card, and follows later; the buttons come last, as before;
  · the keep-warm pass touches the database and the hot path's hosts' root pages (never a billed API call).

    cd backend && python -m unittest tests.test_perf_s149 -v
"""
from __future__ import annotations

import asyncio
import os
import time
import unittest
from unittest import mock

from booking_signer import guest_whatsapp as GW, http_pool as HP, perf_ops as PO, store as S, style as ST
from tests import test_guest_whatsapp_s75 as TG


class TheDatabase(unittest.TestCase):
    def test_no_session_reset_on_release(self):
        cls = S._pooler_connection_class()
        self.assertEqual(cls._get_reset_query(None), "")   # it reads nothing of the connection

    def test_statements_cached_only_on_a_session_pooler(self):
        with mock.patch.dict(os.environ, {"SASHA_DB_STATEMENT_CACHE": ""}):
            self.assertEqual(S.statement_cache("postgresql://u:p@aws-0-eu-west-1.pooler.supabase.com:5432/postgres"), 100)
            self.assertEqual(S.statement_cache("postgresql://u:p@aws-0-eu-west-1.pooler.supabase.com:6543/postgres"), 0)
        with mock.patch.dict(os.environ, {"SASHA_DB_STATEMENT_CACHE": "0"}):
            self.assertEqual(S.statement_cache("postgresql://u:p@h:5432/db"), 0)


class OutboundHTTP(unittest.TestCase):
    def test_one_kept_alive_client_per_event_loop(self):
        async def two():
            return HP.client(), HP.client()
        a, b = asyncio.run(two())
        self.assertIs(a, b)
        c, _ = asyncio.run(two())
        self.assertIsNot(a, c)                       # a new loop gets its own client


class StreamedCards(TG.Base):
    def test_each_card_goes_as_soon_as_its_own_photo_is_ready(self):
        self.link()
        GW.PHOTO_CACHE.clear()
        sent_at = []
        real_send = GW.SENDER.send

        async def send(frm, to, **kw):
            sent_at.append((time.perf_counter(), kw.get("body") or "", kw.get("media")))
            return await real_send(frm, to, **kw)
        GW.SENDER.send = send

        async def page_text(http, url, resolve):
            # by rank (rating): site1 (4.8) is card 1, site0 (4.6) card 2, site2 (4.4) card 3
            await asyncio.sleep({"site1": 0.0, "site0": 0.15, "site2": 3.0}[url.split("//")[1].split(".")[0]])
            return {"image": url + "/og.jpg"}
        cands = [{**c, "website": f"https://site{i}.example"} for i, c in enumerate(TG.CANDS)]
        with mock.patch.object(ST, "page_text", page_text), mock.patch.object(TG, "CANDS", cands), \
                mock.patch.dict(os.environ, {"SASHA_PHOTO_WAIT_S": "0.4", "SASHA_STREAM_CARDS": "1"}):
            t0 = time.perf_counter()
            self.say("dinner for 2 in Chamberí on Saturday at 9")
            took = time.perf_counter() - t0
        bodies = [b for _, b, _ in sent_at]
        cards = [(t, b, m) for t, b, m in sent_at if "·" in b and "From Google Maps" not in b]
        self.assertTrue(any("From Google Maps" in b for b in bodies[:1]))     # the header first
        self.assertEqual(len(cards), 3)
        self.assertEqual([m is not None for _, _, m in cards], [True, True, False])   # the slow photo isn't waited for
        self.assertGreater(cards[1][0] - cards[0][0], 0.1)                    # card 1 went before card 2's photo (0.15 s) was ready
        self.assertLess(took, 1.0)                                            # nor anyone for the 3-s photo
        self.assertEqual(GW.SENDER.contents[-1][0], "Which one?")              # the buttons last, as before
        self.assertIn("_late_photos", self.spawned)

    def test_off_unless_switched_on(self):
        self.assertFalse(GW.stream_cards())


class KeepWarm(unittest.TestCase):
    def test_a_pass_touches_the_database_and_only_free_root_pages(self):
        seen = []

        async def req(method, url, *, timeout, **kw):
            seen.append(url)
        store = mock.Mock()
        store._run = mock.AsyncMock(return_value=1)
        with mock.patch("booking_signer.routes.STORE", store), mock.patch("booking_signer.http_pool.request", req):
            out = asyncio.run(PO.warm_once())
        self.assertIn("db_ms", out)
        self.assertEqual(seen, list(PO.WARM_URLS))
        self.assertTrue(all(u.endswith(".com/") for u in seen))              # a host's root page: no API call, nothing billed

    def test_stats(self):
        self.assertEqual(PO.stats([10, 20, 30, 40, 500]), {"n": 5, "p50": 30, "p95": 500, "max": 500})


if __name__ == "__main__":
    unittest.main()
