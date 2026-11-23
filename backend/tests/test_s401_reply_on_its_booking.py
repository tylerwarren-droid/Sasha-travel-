"""Sasha 401 · A REPLY LANDS ON THE BOOKING IT ANSWERS (EU 292 claim 2; root test: mailbox row 2122).

Measured (EU 292, verified): a venue's SMS / WhatsApp / voicemail landed on the LATEST call to that number (inbound_phone.call_for_number,
"order by created_at desc limit 1"); an email to Sasha's own address on the LAST email ever sent to that sender (ladder_store.
email_for_sender, no window); match_written took the newest call when a surname named several. All outside 399's one rule.

THE CLASS: every inbound channel (SMS, WhatsApp, voicemail, email to Sasha's own address, a written email after a call — and one that
doesn't exist yet) × one booking contacted / several / none → the channel GATHERS its contacted bookings, one_booking.reply_for reads the
words into one_booking.decide: exactly one → it; several → held and SAID to each person it might be for; never "the most recent one".

    cd backend && python -m unittest tests.test_s401_reply_on_its_booking -v
"""
from __future__ import annotations

import asyncio
import pathlib
import re
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

from booking_signer import one_booking as OB

BACKEND = pathlib.Path(__file__).resolve().parents[1]
NOW = datetime(2037, 11, 19, 15, 0, tzinfo=timezone.utc)
NUMBER = "+34910000401"
#: two bookings at the same venue, close in time (fictional people; one evening)
EARLY = {"call_id": "k1", "trip_item_id": "ti_early", "account_id": "acct_a", "venue": "Casa Gate", "dialled_number": NUMBER,
         "local_date": "2037-11-19", "local_time": "21:30", "status": "answered", "created_at": NOW - timedelta(hours=3),
         "brief": {"own_reference": "K-4401", "name": "Ana Fictia"}}
LATE = {**EARLY, "call_id": "k2", "trip_item_id": "ti_late", "account_id": "acct_b", "local_time": "21:45",
        "created_at": NOW - timedelta(hours=1), "brief": {"own_reference": "K-4402", "name": "Ben Fictio"}}
KEY = lambda c: c["trip_item_id"]


def run(c):
    return asyncio.run(c)


class TheOneReader(unittest.TestCase):
    def pick(self, words, cands=(EARLY, LATE)):
        cands = [{**c, "own_reference": c["brief"]["own_reference"]} for c in cands]
        got, why, ok = OB.reply_for(cands, words, NOW, KEY)
        return (got or {}).get("trip_item_id"), why

    def test_a_reply_naming_neither_is_held_never_the_latest(self):
        self.assertEqual(self.pick("Confirmado, gracias. Un saludo."), (None, OB.AMBIGUOUS.format(rule="the only booking it can be answering")))
        self.assertIsNone(self.pick("Confirmada la reserva para el 19 de noviembre de 2037")[0])   # both that day: held

    def test_the_words_decide(self):
        self.assertEqual(self.pick("Confirmada su reserva del 19 de noviembre de 2037 a las 21:30")[0], "ti_early")   # day and time
        self.assertEqual(self.pick("Re: K-4402 — confirmed")[0], "ti_late")                                       # Sasha's reference
        self.assertEqual(self.pick("Confirmado", cands=(EARLY,))[0], "ti_early")                                 # the only one called

    def test_a_voicemail_has_no_words(self):
        self.assertIsNone(self.pick(None)[0])
        self.assertEqual(self.pick(None, cands=(LATE,))[0], "ti_late")


class EveryChannelGathersNeverPicks(unittest.TestCase):
    def test_phone_sms_whatsapp_voicemail(self):
        from booking_signer import call_store as CS, inbound_phone as IP
        calls = CS.MemoryCallStore()
        calls.calls = {"k1": dict(EARLY), "k2": dict(LATE)}
        st = IP.MemoryInboundStore(calls)
        self.assertEqual({c["call_id"] for c in run(st.calls_for_number(NUMBER, NOW - timedelta(days=1)))}, {"k1", "k2"})   # a list
        told = []

        async def tell(account, text, **kw):
            told.append((account, text))
            return {"to": "s2"}
        from booking_signer import channel as CH
        with mock.patch.object(IP, "STORE", st), mock.patch.object(IP, "NOW", lambda: NOW), mock.patch.object(CH, "tell", tell):
            call, held = run(IP.reply_call(NUMBER, "Confirmado, gracias", NOW))
            self.assertIsNone(call)
            run(OB.say_held(*held))
            call, held = run(IP.reply_call(NUMBER, "Confirmada para las 21:45 del 19 de noviembre de 2037", NOW))
        self.assertEqual((call["call_id"], held), ("k2", None))
        self.assertEqual(sorted(a for a, _ in told), ["acct_a", "acct_b"])                     # each person it might be for, told
        self.assertTrue(all("Casa Gate sent a message I can't tie" in t and "Confirmado" not in t for _, t in told))   # never the words

    def test_email_to_sashas_own_address(self):
        from booking_signer import ladder_store as LS
        st = LS.MemoryLadderStore() if hasattr(LS, "MemoryLadderStore") else None
        if st is None:
            self.skipTest("no memory ladder store")
        st.emails = {"e1": {"status": "sent", "email": {"to": "reservas@casagate.example"}, "trip_item_id": "ti_early",
                            "sent_at": NOW - timedelta(hours=3), "local_date": "2037-11-19", "local_time": "21:30", "venue_name": "Casa Gate"},
                     "e2": {"status": "sent", "email": {"to": "reservas@casagate.example"}, "trip_item_id": "ti_late",
                            "sent_at": NOW - timedelta(hours=1), "local_date": "2037-11-19", "local_time": "21:45", "venue_name": "Casa Gate"}}
        cands = run(st.emails_for_sender("Reservas@casagate.example", NOW - timedelta(days=21)))
        self.assertEqual({c["email_id"] for c in cands}, {"e1", "e2"})
        self.assertFalse(OB.reply_for(cands, "Perfecto, confirmado.", NOW, KEY)[2])                # held, never e2 (the last)
        self.assertEqual(OB.reply_for(cands, "confirmado: 19 de noviembre de 2037, 21:30", NOW, KEY)[0]["email_id"], "e1")

    def test_a_written_email_after_a_call(self):
        from booking_signer import inbound_phone as IP
        both = [{**EARLY, "brief": {**EARLY["brief"], "name": "Ana Lopez", "sasha_email": True}},
                {**LATE, "brief": {**LATE["brief"], "name": "Eva Lopez", "sasha_email": True}}]
        st = mock.Mock(booking_calls_since=mock.AsyncMock(return_value=both))
        with mock.patch.object(IP, "STORE", st):
            self.assertIsNone(run(IP.match_written("Reserva Lopez", "Confirmada la reserva a nombre de Lopez", NOW)))   # was: the newest
            self.assertEqual(run(IP.match_written("K-4401", "ok", NOW))["trip_item_id"], "ti_early")


#: the ONE lookup by sender that may take the newest row: it resolves the VENUE for a venue-wide STOP (every channel ended), never a booking
VENUE_SCOPE = {"booking_signer/stop.py"}


class Ratchet(unittest.TestCase):
    def files(self):
        for d in ("agapi", "app", "booking_signer", "products"):
            for p in (BACKEND / d).rglob("*.py"):
                yield p.relative_to(BACKEND).as_posix(), p.read_text()

    def test_no_module_picks_the_latest_booking_contacted_at_a_sender(self):
        for rel, src in self.files():
            self.assertNotRegex(src, r"def (call_for_number|email_for_sender)\(", rel)            # EU 292's two pickers are gone
            if rel in VENUE_SCOPE:
                continue
            # a function that looks a contact up BY ITS SENDER (the number dialled, the address emailed) and keeps only the newest —
            # in SQL ("desc limit 1") or in Python (max by key / reverse=True). Among ONE booking's own calls is not the class.
            for f in re.split(r"\n(?=\s*(?:async )?def )", src):
                by_sender = re.search(r"dialled_number|email->>'to'|\[\"email\"\]\.get\(\"to\"", f)
                newest = re.search(r"desc\s+limit\s+1|\bmax\([^()]*key=|reverse=True", f, re.I)
                self.assertFalse(by_sender and newest, f"{rel}: picks the latest booking contacted at a sender — {f.strip()[:90]}")

    def test_every_writer_of_an_inbounds_booking_decides_by_the_one_rule(self):
        # an INBOUND row (it carries the provider's message id) given a booking, or a reply filed on an email
        writes = re.compile(r'"provider_id":[^}]*"trip_item_id":\s*str\(|add_reply\(\{[^}]*"email_id":\s*act', re.S)
        for rel, src in self.files():
            if writes.search(src):
                self.assertTrue("one_booking" in src or rel == "booking_signer/written.py", f"{rel} writes an inbound's booking outside the rule")
        self.assertIn("OB.reply_for(", (BACKEND / "booking_signer/inbound_phone.py").read_text())
        self.assertIn("OB.reply_for(", (BACKEND / "booking_signer/ladder_routes.py").read_text())
        self.assertIn("from .one_booking import decide", (BACKEND / "booking_signer/inbound_phone.py").read_text())   # match_written


if __name__ == "__main__":
    unittest.main()
