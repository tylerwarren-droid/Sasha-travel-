"""Sasha 313 · the Google Calendar sync follows THE BOOKING RECORD (the one itinerary: AgAPI's acts, the Duffel orders, the stays) — each
booking created / updated / deleted in the person's connected calendar, once per version; its Google id derived from Sasha 312's UID.
Offline: a fake Google Calendar API.

    cd backend && python -m unittest tests.test_s313 -v
"""
from __future__ import annotations

import asyncio
import pathlib
import unittest
from unittest import mock

from booking_signer import calendar_sync as CS

ROOT = pathlib.Path(__file__).resolve().parents[1]
ACCT = "00000000-0000-4000-8000-000000000313"


def run(c):
    return asyncio.run(c)


class FakeGoogle:
    """Google Calendar's events API as it answers: GET 404 until made; POST with our id; PATCH; DELETE (a deleted event reads cancelled)."""

    def __init__(self):
        self.events, self.calls = {}, []

    async def __call__(self, method, url, token=None, json_body=None, data=None):
        eid = url.rsplit("/events", 1)[-1].lstrip("/")
        self.calls.append((method, eid or (json_body or {}).get("id")))
        if method == "GET":
            return (200, dict(self.events[eid])) if eid in self.events else (404, {})
        if method == "POST":
            self.events[json_body["id"]] = {**json_body, "status": json_body.get("status", "confirmed")}
            return 200, self.events[json_body["id"]]
        if method == "PATCH":
            self.events[eid] = {**self.events[eid], **json_body}
            return 200, self.events[eid]
        if method == "DELETE":
            self.events[eid] = {**self.events[eid], "status": "cancelled"}
            return 204, {}
        return 400, {}

    def writes(self):
        return [c for c in self.calls if c[0] != "GET"]


DINNER = {"kind": "dinner", "title": "DiverXO", "when": "2026-11-13T21:00", "status": "confirmed", "id": "act_DX", "source": "venue",
          "country": "ES", "reference": "DX-1"}
FLIGHT = {"kind": "flight", "title": "British Airways BA 0107", "when": "2026-11-21T15:29:00", "where": "SNZ → MAD", "status": "booked",
          "id": "c097b002-fa4a-4348-9b0e-53317af88548", "source": "flight", "tz": "America/Sao_Paulo", "minutes": 690}
STAY = {"kind": "hotel", "title": "Hotel WhatsApp (sandbox)", "when": "2026-11-15T15:00", "status": "confirmed", "id": "act_ST",
        "source": "venue", "check_in": "2026-11-15", "check_out": "2026-11-19", "nights": 4}


class Base(unittest.TestCase):
    def setUp(self):
        self.google = FakeGoogle()
        self.store = CS.MemoryCalendarStore()
        run(self.store.put_link({"account_id": ACCT, "vault_item_id": "v", "google_calendar_id": "sasha-cal", "scopes": "x",
                                 "consent_at": None, "consent_wording_version": "v1", "consent_text_sha256": "x"}))
        self.rows = [dict(DINNER), dict(FLIGHT), dict(STAY)]
        self.p = [mock.patch.object(CS, "STORE", self.store), mock.patch.object(CS, "GOOGLE_HTTP", self.google),
                  mock.patch.object(CS, "_token", mock.AsyncMock(return_value="tok")),
                  mock.patch("agapi.itinerary.of", mock.AsyncMock(side_effect=lambda a: [dict(r) for r in self.rows]))]
        for p in self.p:
            p.start()

    def tearDown(self):
        for p in self.p:
            p.stop()

    def ev(self, row):
        return self.google.events.get(CS.google_id(f"{row['id']}@sasha.kanoe"))


class FromTheRecord(Base):
    def test_every_kind_is_made_with_the_312_uid(self):
        run(CS.sync_account(ACCT))
        for row in self.rows:
            e = self.ev(row)
            self.assertEqual(e["iCalUID"], f"{row['id']}@sasha.kanoe")
            self.assertEqual(e["status"], "confirmed")
        self.assertEqual(self.ev(STAY)["end"], {"date": "2026-11-19"})                                   # the record's own check-out
        self.assertEqual(self.ev(FLIGHT)["start"]["timeZone"], "America/Sao_Paulo")
        self.assertEqual(self.ev(DINNER)["end"]["dateTime"], "2026-11-13T23:00:00")

    def test_once_per_version(self):
        run(CS.sync_account(ACCT))
        n = len(self.google.writes())
        run(CS.sync_account(ACCT))
        self.assertEqual(len(self.google.writes()), n)   # nothing changed on the record: nothing written

    def test_a_cancel_deletes_and_a_change_updates(self):   # Tyler's DiverXO: cancelled on AgAPI's record → gone from his calendar
        run(CS.sync_account(ACCT))
        self.rows[0]["status"] = "cancelled"
        self.rows[2].update(check_out="2026-11-18", nights=3)
        run(CS.sync_account(ACCT))
        self.assertEqual(self.ev(DINNER)["status"], "cancelled")
        self.assertEqual(self.ev(STAY)["end"], {"date": "2026-11-18"})
        w = self.google.writes()[-2:]
        self.assertEqual(sorted(m for m, _ in w), ["DELETE", "PATCH"])

    def test_a_request_is_tentative_and_marked(self):
        self.rows = [{**DINNER, "status": "asked"}]
        run(CS.sync_account(ACCT))
        e = self.ev(DINNER)
        self.assertEqual((e["status"], e["summary"]), ("tentative", "(requested) DiverXO"))

    def test_an_expired_connection_is_kept_not_written(self):
        run(self.store.set_link(ACCT, needs_reconnect_at="2026-10-10T15:53:32Z"))
        self.assertEqual(run(CS.sync_account(ACCT)), ["kept: the connection needs reconnecting"])
        self.assertEqual(self.google.calls, [])


class TripItemsIsNoLongerASource(unittest.TestCase):
    def test_the_loop_syncs_the_record(self):
        src = (ROOT / "booking_signer" / "calendar_sync.py").read_text()
        loop = src[src.index("async def _forever"):src.index("def start()")]
        self.assertIn("await sync_all()", loop)
        self.assertNotIn("drain_once()", loop)

    def test_the_google_id_is_googles_alphabet_and_stable(self):
        a = CS.google_id("act_DX@sasha.kanoe")
        self.assertRegex(a, r"^[a-v0-9]{5,1024}$")
        self.assertEqual(a, CS.google_id("act_DX@sasha.kanoe"))


if __name__ == "__main__":
    unittest.main()
