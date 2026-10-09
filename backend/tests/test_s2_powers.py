"""CR 60 · S2's first powers as Sasha's tools (agapi/s2_tools.py) on the shared logic (agapi/powers.py — byte for byte the module the
AgAPI sandbox runs). Fixtures only, 0 live calls: the booking API and the basket are recorders; email is captured (TEST mode).

    cd backend && python -m unittest tests.test_s2_powers -v
"""
from __future__ import annotations

import asyncio
import json
import os
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from agapi import powers as P, s2_tools as S, v0 as API

VEC = json.loads((Path(__file__).parent / "fixtures" / "agapi_powers_vectors.json").read_text(encoding="utf-8"))
ACCOUNT = "00000000-0000-4000-8000-0000000000c0"


def run(c):
    return asyncio.run(c)


class SharedVectors(unittest.TestCase):
    """The same frozen vectors the AgAPI sandbox passes — so Sasha and partners get the same bytes."""

    def test_email_and_calendar_vectors(self):
        for c in VEC["email"]:
            i = c["input"]
            m = P.email_message(i["from"], i["to"]["address"], i["to"].get("name"), i["subject"], i["body"])
            self.assertEqual((m, P.email_read_back(m), P.sha256(m)), (c["expect"]["message"], c["expect"]["read_back"], c["expect"]["payload_sha256"]))
        for c in VEC["email_refused"]:
            with self.assertRaises(P.Refused):
                i = c["input"]
                P.email_message("Sasha <s@x.test>", i["to"]["address"], i["to"].get("name"), i["subject"], i["body"])
        for c in VEC["calendar"]:
            self.assertEqual(P.ics(c["event"], c["dtstamp"]), c["expect"]["ics"])
            self.assertEqual(P.calendar_links(c["event"], c["ics_url"]), c["expect"]["links"])


class Email(unittest.TestCase):
    MSG = {"to": {"address": "marta@example.com", "name": "Marta"}, "subject": "Our trip", "body": "Hi Marta,\nWe land at 09:00.\nAna"}

    def setUp(self):
        S._HELD.clear()
        S.OUTBOX.clear()
        self.p = mock.patch("booking_signer.basket.event", mock.AsyncMock())
        self.p.start()

    def tearDown(self):
        self.p.stop()

    def turn(self, said, msg=None, started=None):
        ctx = API.Ctx(account=ACCOUNT, user_said=said)
        if started:
            ctx.started = started
        return run(API.call(ctx, "send_email", {**(msg or self.MSG), "approval": {"said": said}, "idempotency_key": f"k-{said}-{datetime.now().timestamp()}"}))

    def later(self):
        return datetime.now(timezone.utc) + timedelta(seconds=5)

    def test_read_back_then_a_later_yes_sends_once_captured(self):
        turn_start = datetime.now(timezone.utc)
        r = self.turn("email Marta our plan", started=turn_start)
        self.assertEqual(r["result"]["status"], "awaiting_yes")
        self.assertIn("To: Marta <marta@example.com>", r["result"]["read_back"])
        self.assertTrue(r["result"]["read_back"][0].startswith("Send this email from"))
        r = self.turn("Yes, send it.", started=turn_start)                   # the SAME turn as the read-back: never
        self.assertEqual(r["result"]["status"], "awaiting_yes")
        self.assertEqual(S.OUTBOX, [])
        r = self.turn("Yes — what will it say?", started=self.later())       # a later turn, but a question
        self.assertEqual(r["error"]["code"], "no_explicit_yes")
        self.assertEqual(S.OUTBOX, [])
        r = self.turn("Yes, send it.", started=self.later())
        self.assertEqual(r["result"]["status"], "not_sent", r)               # CR 61: never "sent" for a message that didn't leave
        self.assertEqual(r["result"]["outcome"]["kind"], "NOT_SENT")
        self.assertTrue(r["result"]["outcome"]["reference"].startswith("test_msg_"))
        self.assertEqual(len(S.OUTBOX), 1)                                   # captured, never sent
        r = self.turn("Yes, send it.", started=self.later() + timedelta(seconds=5))
        self.assertEqual(r["result"]["status"], "awaiting_yes")              # the yes was used: a new send needs a new read-back
        self.assertEqual(len(S.OUTBOX), 1)

    def test_any_change_is_a_new_read_back(self):
        self.turn("email Marta")
        r = self.turn("Yes, send it.", msg={**self.MSG, "subject": "Our trip!!"}, started=self.later())
        self.assertEqual(r["result"]["status"], "awaiting_yes")
        self.assertEqual(S.OUTBOX, [])

    def test_a_stale_read_back_is_never_sent(self):
        self.turn("email Marta")
        S._HELD[ACCOUNT]["at"] -= timedelta(minutes=20)
        r = self.turn("Yes, send it.", started=self.later())
        self.assertEqual(r["result"]["status"], "awaiting_yes")
        self.assertEqual(S.OUTBOX, [])

    def test_refusals_and_the_models_view(self):
        r = self.turn("email", msg={**self.MSG, "subject": "Hi\nBcc: evil@example.com"})
        self.assertEqual(r["error"]["code"], "invalid_input")
        t = {x["name"]: x for x in S.tools()}
        self.assertNotIn("approval", API.schema_for_model(t["send_email"])["input_schema"]["properties"])
        self.assertNotIn("idempotency_key", API.schema_for_model(t["send_email"])["input_schema"]["properties"])


FOUNDER, JON, OTHER = ("00000000-0000-4000-8000-0000000000f0", "00000000-0000-4000-8000-0000000000a1",
                        "00000000-0000-4000-8000-0000000000b2")


class LiveEmailAllowList(unittest.TestCase):
    """CR 61 · Tyler: real sending ON for the founder and Jon's allow-listed account only; off for everyone else."""

    def env(self, **over):
        e = {"SASHA_S2_EMAIL_LIVE": "1", "FOUNDER_ACCOUNT_ID": FOUNDER, "SASHA_REAL_CONTACT_ACCOUNTS": JON}
        e.update(over)
        return mock.patch.dict(os.environ, e)

    def test_who_may_send_for_real(self):
        with self.env():
            self.assertEqual([S.live_for(a) for a in (FOUNDER, JON, JON.upper(), OTHER, None, "")], [True, True, True, False, False, False])
        with self.env(SASHA_S2_EMAIL_LIVE="0"):                                       # the kill switch: nobody
            self.assertEqual([S.live_for(a) for a in (FOUNDER, JON, OTHER)], [False, False, False])

    def send(self, account):
        S._HELD.clear()
        S.OUTBOX.clear()
        got = mock.MagicMock(sent=True, provider_id="re_123", http_status=200, why=None)
        with self.env(), mock.patch("booking_signer.basket.event", mock.AsyncMock()), \
                mock.patch("agapi.v0.claim", mock.AsyncMock()), \
                mock.patch("booking_signer.emailing.send", mock.AsyncMock(return_value=got)) as em:
            t0 = datetime.now(timezone.utc)
            run(API.call(API.Ctx(account=account, user_said="email Marta", started=t0), "send_email",
                         {**Email.MSG, "idempotency_key": f"a-{account}-{t0.timestamp()}", "approval": {"said": "email Marta"}}))
            t1 = t0 + timedelta(seconds=5)
            r = run(API.call(API.Ctx(account=account, user_said="Yes, send it.", started=t1), "send_email",
                             {**Email.MSG, "idempotency_key": f"b-{account}-{t1.timestamp()}", "approval": {"said": "Yes, send it."}}))
            return r.get("result") or r, em.await_count

    def test_the_founder_and_jon_send_for_real_a_guest_never(self):
        for who in (FOUNDER, JON):
            r, sends = self.send(who)
            self.assertEqual((r["status"], r["outcome"]["reference"], sends, S.OUTBOX), ("sent", "re_123", 1, []), r)
        r, sends = self.send(OTHER)
        self.assertEqual((r["status"], sends, len(S.OUTBOX)), ("not_sent", 0, 1), r)
        self.assertIn("Not sent", r["outcome"]["target_words"])


class Calendar(unittest.TestCase):
    def ctx(self):
        return API.Ctx(account=ACCOUNT)

    def test_a_confirmed_table(self):
        rows = {"reservations": [{"id": "ti-1", "venue": "Casa Lucio", "date": "2026-11-20", "time": "21:00", "timezone": "Europe/Madrid",
                                  "party": 2, "status": "confirmed"},
                                 {"id": "ti-2", "venue": "Botín", "date": "2026-11-21", "time": "20:00", "timezone": "Europe/Madrid",
                                  "party": 4, "status": "requested"}]}
        GW = mock.MagicMock()
        GW.api = mock.AsyncMock(return_value=(200, rows))
        GW.plain_venue = lambda v: v
        with mock.patch("agapi.venues._API", lambda: GW):
            r = run(API.call(self.ctx(), "add_to_calendar", {"booking_id": "ti-1"}))
            self.assertTrue(r["ok"], r)
            ev = r["result"]["event"]
            self.assertEqual((ev["title"], ev["starts_at"]), ("Table for 2 at Casa Lucio", "2026-11-20T20:00:00Z"))   # 21:00 Madrid
            self.assertEqual(r["result"]["event_sha256"], P.sha256(ev))
            self.assertTrue(r["result"]["links"]["google"].startswith("https://calendar.google.com/"))
            self.assertIn("/api/agent/ics/", r["result"]["links"]["apple"])
            r = run(API.call(self.ctx(), "add_to_calendar", {"booking_id": "ti-2"}))
            self.assertEqual(r["error"]["code"], "not_confirmed")

    def test_a_booked_flight_and_unknown(self):
        GW = mock.MagicMock()
        GW.api = mock.AsyncMock(return_value=(200, {"reservations": []}))
        row = {"id": "bk-1", "kind": "flight", "booking_reference": "UHQ9B1",
               "snapshot": {"owner": "Air Europa", "flights": "UX 1013", "from": "MAD", "to": "LGW", "departs": "2026-11-12T07:30:00",
                            "from_tz": "Europe/Madrid", "minutes": 150}}
        with mock.patch("agapi.venues._API", lambda: GW), \
                mock.patch("booking_signer.plan_store.latest", mock.AsyncMock(return_value={"trip_id": "t-1"})), \
                mock.patch("booking_signer.basket.items", mock.AsyncMock(return_value=[row])):
            r = run(API.call(self.ctx(), "add_to_calendar", {"booking_id": "bk-1"}))
            self.assertTrue(r["ok"], r)
            ev = r["result"]["event"]
            self.assertEqual((ev["title"], ev["starts_at"], ev["ends_at"]), ("Flight UX1013 MAD → LGW", "2026-11-12T06:30:00Z", "2026-11-12T09:00:00Z"))
            self.assertIn("UHQ9B1", ev["details"])
            self.assertEqual(run(API.call(self.ctx(), "add_to_calendar", {"booking_id": "nope"}))["error"]["code"], "booking_unknown")


class Wired(unittest.TestCase):
    def test_the_powers_are_sashas_tools(self):
        """Sasha 216 · wired for real (agapi/v0.py registers them) — no longer added and removed around these tests."""
        for name in ("send_email", "add_to_calendar"):
            self.assertIn(name, API.BY_NAME)
        self.assertIn("send_email", API.ACTS)   # claimed once, durably, before it sends


if __name__ == "__main__":
    unittest.main()
