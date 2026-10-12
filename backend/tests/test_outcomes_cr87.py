"""CR 87 · the booking outcomes ledger, Sasha's side: book_venue records each real attempt with its rung (form → zero_touch, handover /
page → human_tap, draft / email → request_reply, call → phone), and the venue's later reply updates it — keyed by the reservation's id;
never the person's details. AgAPI is faked.

    cd backend && python -m unittest tests.test_outcomes_cr87 -v
"""
from __future__ import annotations

import asyncio
import json
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

from agapi import s2_outcomes as OC
from agapi import venues as VN

ACC = "00000000-0000-4000-8000-000000000087"


def run(c):
    return asyncio.run(c)


class Fake:
    def __init__(self):
        self.calls = []

    async def __call__(self, op, body):
        self.calls.append((op, dict(body)))
        return {"ok": True, "result": {"outcome_id": "bko_1", **body}}


def held(rung, tid="11111111-2222-4333-8444-555555555555", **kw):
    return {"rung": rung, "id": f"{rung}-1", "trip_item_id": tid, "sector": "restaurant", "venue": "Casa Lucio",
            "at": datetime(2026, 10, 12, 10, 0, tzinfo=timezone.utc), "summary": "Sat 24 Oct, 21:00, 4 people", "when": "2026-10-24T21:00", **kw}


class Ledger(unittest.TestCase):
    def setUp(self):
        self.agapi = Fake()
        for p in (mock.patch.object(OC, "CALL", self.agapi), mock.patch.dict(OC._OPEN, {}, clear=True), mock.patch.object(OC, "_DONE", set()),
                  mock.patch.object(OC, "start", lambda: None)):
            p.start()
            self.addCleanup(p.stop)

    def test_each_rung_and_what_happened_at_once(self):
        for rung, result, want in (("form", {"status": "confirmed", "reference": "CL-4471"}, ("zero_touch", "web_form", "confirmed")),
                                   ("handover", {"status": "tap_to_finish"}, ("human_tap", "page_handover", "sent")),
                                   ("page", {"status": "page_on_phone"}, ("human_tap", "page_handover", "sent")),
                                   ("draft", {"status": "draft_on_phone"}, ("request_reply", "whatsapp", "sent")),
                                   ("email", {"status": "requested"}, ("request_reply", "email", "sent")),
                                   ("call", {"status": "scheduled"}, ("phone", "phone", "sent"))):
            run(OC.booked(ACC, held(rung, tid=f"t-{rung}"), "Casa Lucio", "Madrid", result=result))
            b = self.agapi.calls[-1][1]
            self.assertEqual((b["rung"], b["channel"], b["state"], b["ref"], b["sector"], b["city"]), (*want, f"sasha:t-{rung}", "restaurant", "Madrid"))
            self.assertEqual(b["asked_at"], "2026-10-12T10:00:00Z")
        self.assertEqual(self.agapi.calls[0][1]["confirmation_quote"], "Their reference: CL-4471")
        run(OC.booked(ACC, held("draft", tid="t-ig", channel="instagram"), "Casa Lucio", None, result={"status": "draft_message"}))
        self.assertEqual(self.agapi.calls[-1][1]["channel"], "instagram")
        run(OC.booked(ACC, held("email", tid="t-x"), "Casa Lucio", None, error="their mail server refused it"))
        self.assertEqual((self.agapi.calls[-1][1]["state"], self.agapi.calls[-1][1]["failure_reason"]), ("failed", "their mail server refused it"))
        self.assertEqual(sorted(OC._OPEN[ACC]), ["t-call", "t-draft", "t-email", "t-handover", "t-ig", "t-page"])   # open: updated later

    def test_never_the_persons_details(self):
        run(OC.booked(ACC, held("email", who={"name": "Alex", "contact": {"mobile_e164": "+34600000000"}}), "Casa Lucio", "Madrid",
                      result={"status": "requested"}))
        sent = json.dumps(self.agapi.calls[-1][1])
        for x in ("Alex", "+34600000000", ACC):
            self.assertNotIn(x, sent)

    def test_the_reply_lands_once(self):
        OC._OPEN[ACC] = {"t-email", "t-call", "t-page"}
        rows = [{"id": "t-email", "status": "confirmed", "status_words": "Confirmamos su mesa para 4 el sábado 24 a las 21:00."},
                {"id": "t-call", "status": "declined", "status_words": "Completo ese día."},
                {"id": "t-page", "status": "cancelled"}, {"id": "t-other", "status": "requested"}]
        self.assertEqual(run(OC.sync(ACC, rows)), 3)
        ups = {b["ref"]: b for op, b in self.agapi.calls if op == "outcomes.update"}
        self.assertEqual(ups["sasha:t-email"]["confirmation_quote"], "Confirmamos su mesa para 4 el sábado 24 a las 21:00.")
        self.assertEqual((ups["sasha:t-call"]["state"], ups["sasha:t-call"]["failure_reason"]), ("declined", "Completo ese día."))
        self.assertEqual(ups["sasha:t-page"]["failure_reason"], "cancelled before the venue answered")
        self.assertEqual(run(OC.sync(ACC, rows)), 0)                                                  # never sent twice
        self.assertEqual(OC._OPEN[ACC], set())

    def test_a_ledger_that_doesnt_answer_never_stops_a_booking(self):
        async def down(op, body):
            raise ConnectionError("x")
        with mock.patch.object(OC, "CALL", down):
            run(OC.booked(ACC, held("form"), "Casa Lucio", None, result={"status": "confirmed"}))   # no exception

    def test_book_venue_records_the_attempt(self):
        from agapi import v0 as API
        h = held("email")
        VN._HELD[ACC] = h
        ctx = API.Ctx(account=ACC, user_said="yes, book it", surface="s2", started=h["at"] + timedelta(minutes=1))
        with mock.patch("agapi.v0.stale", lambda at: False), mock.patch("agapi.v0.claim", mock.AsyncMock()), \
                mock.patch.object(VN, "_book_inner", mock.AsyncMock(return_value={"status": "requested", "venue": "Casa Lucio"})), \
                mock.patch.object(VN, "card_of", lambda *a: {"address": "Calle Cava Baja 35, 28005 Madrid, Spain"}), \
                mock.patch.object(VN, "_API", lambda: mock.Mock(plain_venue=lambda v: v)):
            run(VN.book_venue(ctx, {"approval": {"said": "yes, book it"}}))
        b = self.agapi.calls[-1][1]
        self.assertEqual((self.agapi.calls[-1][0], b["state"], b["rung"], b["city"]), ("outcomes.record", "sent", "request_reply", "Madrid"))
