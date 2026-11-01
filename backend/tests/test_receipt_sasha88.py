"""Sasha 88 · the booking receipt: one reservation as it can be shown and proved — the place by its name, both
references, their words, the two-sided transcript, what they wrote, and the yes it rests on. Offline.

    cd backend && python -m unittest tests.test_receipt_sasha88 -v
"""
from __future__ import annotations
import tests.founder_fixture  # noqa: F401,E402  (Sasha 249 · the fixtures name the founder; no fallback any more)

import json
import unittest

from booking_signer import call_routes as CRT, receipt as RC, spoken as SP
from tests import test_places_terms as TPT
from tests.test_booking_ladder import NOW

BOTAVARA = "Botavara Chamberí"
#: the call of 1 Oct 2026 (a1c85ca6), its venue's lines verbatim
TURNS = [("assistant", "Hola, soy Sasha, una concierge de inteligencia artificial…"), ("user", "Sí, claro, dígame un nombre, por favor."),
         ("assistant", "El apellido es Warren."), ("user", "Mesa reservada, gracias."), ("agent-action", "Ended call"),
         ("assistant", "¿Me da un número de reserva o localizador?"), ("user", "Sí, el localizador es 4417."),
         ("assistant", "Para confirmar: … a nombre de Warren. ¿Correcto?"), ("user", "Correcto.")]


class Receipt(unittest.TestCase):
    make_stores = TPT.PlacesTerms.make_stores
    tearDown = TPT.PlacesTerms.tearDown

    def setUp(self):
        from tests.act_machinery import open_act_check; open_act_check(self)   # Sasha 265 · the placing machinery (CR 99)
        TPT.PlacesTerms.setUp(self)
        self.web.listing = {**TPT.listing(), "displayName": {"text": BOTAVARA}}

    def booked(self):
        r = self.c.post("/api/booking/venues/read", json={"name": BOTAVARA, "city": "Chamberí", "place_id": TPT.PID, "asked_for": "dinner"})
        reservation = {"schema": "reservation/1", "flow": "book", "who": {"name": "Warren", "contact": {"mobile_e164": "+34608445715"}},
                       "what": {"activity": "a table", "activity_venue_lang": "una mesa", "category": "restaurant"}, "where": {},
                       "when": {"mode": "at", "at": "2026-10-10T21:00"}, "how_many": {"count": 2, "unit": "people"}}
        prep = self.c.post("/api/booking/calls", json={"read_id": r.json()["read_id"], "reservation": reservation}).json()
        placed = self.c.post(f"/api/booking/calls/{prep['call_id']}/place",
                             json={"read_back_sha256": prep["read_back"]["sha256"], "approval": {"how": "chat", "said": "Yeah."}})
        self.assertEqual(placed.json()["status"], "placed", placed.text)
        call = self.calls.calls[prep["call_id"]]
        call.update(status="answered", outcome="yes", venue_words="Sí, claro, dígame un nombre, por favor. / Mesa reservada, gracias. / Correcto.",
                    reading={"outcome": "yes", "quote": "Mesa reservada, gracias.", "reference": "4417", "read_by": "an AI reading"},
                    bland_details={"transcripts": [{"user": u, "text": t, "created_at": f"2026-10-01T17:57:{i:02d}Z"} for i, (u, t) in enumerate(TURNS)]})
        self.calls.trip_items[prep["trip_item_id"]]["status"] = "confirmed"
        self.calls.written = [{"trip_item_id": prep["trip_item_id"], "channel": "sms", "body_text": "Confirmada mesa sábado 21h Warren",
                               "received_at": "2026-10-01T18:05:00Z"}]
        return prep

if __name__ == "__main__":
    unittest.main()


class GuestReceipt(Receipt):
    """Sasha 90 · after every booking, the guest gets the receipt by email from Sasha's own address — whatever the outcome."""
    ENV = {"SASHA_EMAILS_ENABLED": "1", "SASHA_RESEND_API_KEY": "k", "SASHA_EMAIL_FROM": "Sasha <sasha@booking.kanoe.ai>",
           "SASHA_INBOUND_DOMAIN": "booking.kanoe.ai", "SASHA_FOUNDER_EMAIL": "founder@kanoe.test"}

    def send(self, prep):
        import asyncio, os
        from unittest import mock
        from booking_signer import guest_receipt as GR
        with mock.patch.dict(os.environ, self.ENV):
            return asyncio.run(GR.send_after_call(self.calls.calls[prep["call_id"]]))

class WrittenPromise(unittest.TestCase):
    """Sasha 90 (a) · what the venue said when asked to confirm in writing — verbatim, on the receipt."""
    def test_their_answer_is_kept_verbatim(self):
        turns = [{"who": "Sasha", "text": "Para confirmar: … ¿Correcto?"}, {"who": "Venue", "text": "Correcto."},
                 {"who": "Sasha", "text": "¿Nos podrían enviar una confirmación por SMS o por email? Al móvil del cliente, …"},
                 {"who": "Venue", "text": "Sí, te mando un SMS ahora."}, {"who": "Venue", "text": "Al móvil."}, {"who": "Sasha", "text": "Gracias."}]
        self.assertEqual(RC.written_promise({"confirm_ask": "x"}, turns),
                         {"asked": turns[2]["text"], "their_answer": "Sí, te mando un SMS ahora. / Al móvil."})
        self.assertIsNone(RC.written_promise({}, turns))                      # not asked on this call
        self.assertEqual(RC.written_promise({"confirm_ask": "x"}, turns[:2])["asked"], None)


class EmailedConfirmation(unittest.TestCase):
    """Sasha 90 (a) · a venue's email to Sasha's own address lands on the booking — by her reference, or one surname only."""
    def setUp(self):
        import asyncio
        from datetime import datetime, timezone, timedelta
        from booking_signer import inbound_phone as IP
        from booking_signer.call_store import MemoryCallStore
        self.asyncio, self.IP = asyncio, IP
        self.now = datetime(2026, 10, 1, 19, 0, tzinfo=timezone.utc)
        self.calls = MemoryCallStore()
        O = {"schema": "reservation/1", "flow": "book", "who": {"name": "Warren"},
             "what": {"activity": "a table", "activity_venue_lang": "una mesa", "category": "restaurant"}, "where": {},
             "when": {"mode": "at", "at": "2026-10-03T21:00"}, "how_many": {"count": 2, "unit": "people"}}
        for cid, item, name, ref in (("c1", "t1", "Warren", "K-HH42"), ("c2", "t2", "García", "K-7FA3")):
            self.calls.trip_items[item] = {"id": item, "status": "unclear", "request": {**O, "who": {"name": name}}}
            self.calls.calls[cid] = {"call_id": cid, "trip_item_id": item, "status": "answered", "created_at": self.now - timedelta(hours=1),
                                     "brief": {"purpose": "book", "name": name, "own_reference": ref, "sasha_email": "sasha@booking.kanoe.ai",
                                               "venue_ids": ["places:x"], "followup": {"request": {**O, "who": {"name": name}}}}}
        self.saved = IP.STORE
        IP.STORE = IP.MemoryInboundStore(self.calls)

    def tearDown(self):
        self.IP.STORE = self.saved

    def file(self, pid, subject, text):
        return self.asyncio.run(self.IP.on_written_email(pid, "reservas@botavara.test", subject, text, self.now))

    def test_by_sashas_reference_it_lands_and_confirms(self):
        self.assertTrue(self.file("re1", "Reserva K-HH42", "Confirmado: mesa para 2 personas el sábado 3 de octubre a las 21:00, a nombre de Warren."))
        row = self.IP.STORE.rows["re1"]
        self.assertEqual((row["channel"], row["trip_item_id"]), ("email", "t1"))
        self.assertNotIn("botavara", json.dumps(row, default=str))               # the sender, hashed
        self.assertEqual(self.calls.trip_items["t1"]["status"], "confirmed")

    def test_by_a_surname_only_when_it_is_the_only_one_and_never_by_guess(self):
        self.assertTrue(self.file("re2", "Reserva", "Hola, confirmamos la mesa de García."))
        self.assertEqual(self.IP.STORE.rows["re2"]["trip_item_id"], "t2")
        self.assertFalse(self.file("re3", "Reserva", "Hola, confirmamos las mesas de Warren y García."))   # two: not guessed
        self.assertFalse(self.file("re4", "Hola", "¿Tenéis mesa mañana?"))                                # none
        self.assertNotIn("re3", self.IP.STORE.rows)


class Cancelling(Receipt):
    """Sasha 96 · "cancel X" is found by the chat; after the cancel call the guest gets the copy, with the proof."""
    ENV = GuestReceipt.ENV

    def test_cancel_requests_are_recognised_and_nothing_else(self):
        from booking_signer import handoff as H
        self.assertEqual(H.cancel_request("cancel my booking at Botavara Chamberí"), {"venue": "Botavara Chamberí"})
        self.assertEqual(H.cancel_request("Cancela la reserva en Botavara, por favor"), {"venue": "Botavara"})
        self.assertEqual(H.cancel_request("cancel Botavara"), {"venue": "Botavara"})
        self.assertIsNone(H.cancel_request("book dinner for 2 in Chamberí on Saturday at 9pm"))
        turn = H.booking_handoff("cancel Botavara")
        self.assertEqual(turn["booking_cancel"], {"venue": "Botavara"})
        self.assertIn("I'll ask you once before I cancel anything", turn["response"])

    def test_no_text_to_the_guest_unless_switched_on(self):
        import asyncio
        from booking_signer import guest_receipt as GR
        self.assertEqual(asyncio.run(GR.send_sms("+34608445715", "x")), "sms not sent: texts to guests are off (SASHA_SMS_TO_GUEST is not 1)")
