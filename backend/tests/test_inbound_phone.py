"""S-70 · Sasha's own number answers: a venue's SMS or voicemail lands on the reservation, Twilio-signed, never stored
with the number's digits, never replied to automatically. Offline.

    cd backend && python -m unittest tests.test_inbound_phone -v
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from booking_signer import inbound_phone as IP, places_terms as PT, routes, stop as S
from booking_signer.call_store import MemoryCallStore

TOKEN = "0123456789abcdef0123456789abcdef"
BASE = "https://sasha.test"
SITE_NUMBER, LISTING_NUMBER = "+34915001122", "+34911223344"
O = {"schema": "reservation/1", "flow": "book", "who": {"name": "Anna Johnson"},
     "what": {"activity": "a table", "activity_venue_lang": "una mesa", "category": "restaurant"},
     "where": {}, "when": {"mode": "at", "at": "2026-10-08T20:00"}, "how_many": {"count": 4, "unit": "people"}}


def sign(path, form):
    url = f"{BASE}/api/booking/twilio/{path}"
    return base64.b64encode(hmac.new(TOKEN.encode(), (url + "".join(f"{k}{form[k]}" for k in sorted(form))).encode(), hashlib.sha1).digest()).decode()


class InboundPhone(unittest.TestCase):
    def setUp(self):
        self.env = mock.patch.dict(os.environ, {"TWILIO_AUTH_TOKEN": TOKEN, "TWILIO_WEBHOOK_BASE": BASE, "SASHA_BOOKING_KEY": "k"})
        self.env.start()
        self.calls = MemoryCallStore()
        now = datetime.now(timezone.utc)
        for cid, item, dialled in (("c-site", "t-site", SITE_NUMBER), ("c-list", "t-list", PT.number_key(LISTING_NUMBER))):
            self.calls.trip_items[item] = {"id": item, "status": "unclear", "request": O}
            self.calls.calls[cid] = {"call_id": cid, "trip_item_id": item, "dialled_number": dialled, "status": "answered",
                                     "created_at": now - timedelta(hours=1), "brief": {"venue_ids": ["places:x"], "followup": {"request": O}}}
        self.saved = (IP.STORE, S.STOP_STORE)
        IP.STORE = IP.MemoryInboundStore(self.calls)
        app = FastAPI()
        app.include_router(routes.router)
        self.c = TestClient(app)

    def tearDown(self):
        IP.STORE, S.STOP_STORE = self.saved
        self.env.stop()

    def post(self, path, form, signed=True):
        h = {"X-Twilio-Signature": sign(path, form)} if signed else {}
        return self.c.post(f"/api/booking/twilio/{path}", data=form, headers=h)

    def sms(self, sid, sender, body, signed=True):
        return self.post("sms", {"MessageSid": sid, "From": sender, "To": "+447700900000", "Body": body}, signed)

    def test_an_unsigned_or_forged_request_is_refused_and_nothing_kept(self):
        self.assertEqual(self.sms("SM1", SITE_NUMBER, "Confirmado", signed=False).status_code, 403)
        r = self.c.post("/api/booking/twilio/sms", data={"MessageSid": "SM2", "From": SITE_NUMBER, "Body": "x"}, headers={"X-Twilio-Signature": "AAAA"})
        self.assertEqual(r.status_code, 403)
        self.assertEqual(IP.STORE.rows, {})

    def test_a_confirming_sms_lands_on_its_reservation_and_confirms_it(self):
        r = self.sms("SM10", SITE_NUMBER, "Confirmado: mesa para 4 personas el jueves 8 de octubre a las 20:00, a nombre de Johnson.")
        self.assertEqual((r.status_code, r.text.endswith("<Response></Response>")), (200, True))      # never an automatic reply
        row = IP.STORE.rows["SM10"]
        self.assertEqual((row["trip_item_id"], row["reading"]["result"]), ("t-site", "confirmed"))
        self.assertEqual(self.calls.trip_items["t-site"]["status"], "confirmed")
        self.assertNotIn(SITE_NUMBER, json.dumps(row, default=str))                                    # never the digits
        self.assertEqual(row["from_key"], PT.number_key(SITE_NUMBER))

    def test_a_listing_numbers_sms_is_matched_by_its_hash(self):
        self.sms("SM11", LISTING_NUMBER, "Os podemos dar el jueves 8 a las 22:00 para 4.")
        self.assertEqual(IP.STORE.rows["SM11"]["trip_item_id"], "t-list")
        self.assertEqual(self.calls.trip_items["t-list"]["status"], "proposed")

    def test_an_unknown_sender_is_kept_but_moves_nothing_and_a_redelivery_is_kept_once(self):
        self.sms("SM12", "+34600000000", "Hola, ¿quién es?")
        self.sms("SM12", "+34600000000", "Hola, ¿quién es?")
        self.assertEqual((len(IP.STORE.rows), IP.STORE.rows["SM12"]["trip_item_id"]), (1, None))
        self.assertEqual({t["status"] for t in self.calls.trip_items.values()}, {"unclear"})

    def test_a_stop_by_sms_ends_every_channel(self):
        seen = []

        class Stops:
            async def record(self, venue_ids, said_on, scope, words, evidence, now):
                seen.append((venue_ids, said_on, scope))
                return S.Stopped(rows=1, guests_told=0, first=True) if hasattr(S, "Stopped") else None
        S.STOP_STORE = Stops()
        self.sms("SM13", SITE_NUMBER, "No nos escribáis más, gracias.")
        self.assertEqual(seen and seen[0][:2], (["places:x"], "sms"))
        self.assertEqual(self.calls.trip_items["t-site"]["status"], "unclear")                         # a stop is not a booking

    def test_a_call_gets_the_greeting_and_its_recording_is_filed(self):
        r = self.post("voice", {"CallSid": "CA1", "From": SITE_NUMBER, "To": "+447700900000"})
        self.assertIn("ha llamado a Sasha", r.text)
        self.assertIn('<Record maxLength="120"', r.text)
        self.assertIn(f'recordingStatusCallback="{BASE}/api/booking/twilio/recording"', r.text)
        self.assertEqual(IP.STORE.rows["CA1"]["trip_item_id"], "t-site")
        r = self.post("recording", {"CallSid": "CA1", "RecordingUrl": "https://api.twilio.com/rec/RE1", "RecordingDuration": "14"})
        self.assertEqual(r.status_code, 204)
        self.assertEqual((IP.STORE.rows["CA1"]["recording_url"], IP.STORE.rows["CA1"]["recording_seconds"]), ("https://api.twilio.com/rec/RE1", 14))

    def test_the_signature_scheme(self):
        form = {"b": "2", "a": "1"}
        self.assertTrue(IP.signature_ok(f"{BASE}/api/booking/twilio/sms", form, sign("sms", form), TOKEN))
        self.assertFalse(IP.signature_ok(f"{BASE}/api/booking/twilio/sms", {**form, "a": "9"}, sign("sms", form), TOKEN))
        self.assertFalse(IP.signature_ok(f"{BASE}/api/booking/twilio/sms", form, sign("sms", form), ""))   # no token: refused


if __name__ == "__main__":
    unittest.main()


from tests import test_booking_ladder as TBL  # noqa: E402


@unittest.skipUnless(TBL.PG_URL, "BOOKING_TEST_DATABASE_URL is not set — the Postgres half did NOT run")
class OnPostgres(unittest.TestCase):
    """The Postgres store against 016, with a real prepared call answered by a venue."""
    make_stores = TBL.OnPostgres.make_stores
    _q = TBL.OnPostgres._q

    @classmethod
    def setUpClass(cls):
        TBL.OnPostgres.setUpClass.__func__(cls)
        import asyncio, asyncpg, pathlib
        sql = (pathlib.Path(__file__).resolve().parents[1] / "booking_signer" / "sql" / "016_inbound_phone.sql").read_text()

        async def apply():
            c = await asyncpg.connect(TBL.PG_URL)
            try:
                await c.execute(sql[sql.index("begin;"):sql.index("-- VERIFY")])
            finally:
                await c.close()
        asyncio.run(apply())

    def setUp(self):
        TBL.LadderRoutes.setUp(self)
        self.tok = mock.patch.dict(os.environ, {"TWILIO_AUTH_TOKEN": TOKEN, "TWILIO_WEBHOOK_BASE": BASE})
        self.tok.start()
        v = TBL.LadderRoutes.read(self)
        prep = self.c.post("/api/booking/calls", json={"read_id": v["read_id"], **TBL.LadderRoutes.BOOKING}).json()
        self._q("update booking_calls set status = 'answered', outcome = 'unclear' where call_id = $1::uuid", prep["call_id"])
        self.item = prep["trip_item_id"]
        self.saved_ip = IP.STORE
        IP.STORE = IP.PostgresInboundStore(self.base)

    def tearDown(self):
        IP.STORE = self.saved_ip
        self.tok.stop()
        TBL.LadderRoutes.tearDown(self)

    def test_an_sms_lands_on_the_reservation_in_postgres(self):
        form = {"MessageSid": "SMpg1", "From": "+34915001122", "To": "+447700900000",
                "Body": "Confirmado: mesa para 4 personas el jueves 8 de octubre a las 20:00, a nombre de Johnson."}
        r = self.c.post("/api/booking/twilio/sms", data=form, headers={"X-Twilio-Signature": sign("sms", form)})
        self.assertEqual(r.status_code, 200, r.text)
        row = self._q("select * from booking_inbound where provider_id = 'SMpg1'")[0]
        self.assertEqual((str(row["trip_item_id"]), row["from_key"]), (self.item, PT.number_key("+34915001122")))
        self.assertEqual(self._q("select status from trip_items where id = $1::uuid", self.item)[0]["status"], "confirmed")
