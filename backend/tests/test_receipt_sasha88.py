"""Sasha 88 · the booking receipt: one reservation as it can be shown and proved — the place by its name, both
references, their words, the two-sided transcript, what they wrote, and the yes it rests on. Offline.

    cd backend && python -m unittest tests.test_receipt_sasha88 -v
"""
from __future__ import annotations

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

    def test_the_receipt_names_the_place_and_carries_both_references_the_transcript_and_the_proof(self):
        prep = self.booked()
        r = self.c.get(f"/api/booking/reservations/{prep['trip_item_id']}/receipt")
        self.assertEqual(r.status_code, 200, r.text)
        rc = r.json()
        self.assertEqual(rc["venue"]["name"], BOTAVARA)                                      # never "dinner in Chamberí"
        self.assertNotIn("dinner", rc["venue"]["name"])
        self.assertEqual((rc["what"], rc["count"], rc["date"], rc["time"], rc["for_whom"]), ("a table", 2, "2026-10-10", "21:00", "Warren"))
        self.assertEqual(rc["references"]["venue"], "4417")                                  # theirs, as they said it
        self.assertRegex(rc["references"]["sasha"], SP.REF_RX)                               # hers, as she said it
        self.assertEqual([t["who"] for t in rc["transcript"]], ["Sasha", "Venue", "Sasha", "Venue", "Sasha", "Venue", "Sasha", "Venue"])
        self.assertNotIn("Ended call", json.dumps(rc["transcript"]))
        self.assertEqual(rc["recording"], {"kept": False, "why": RC.RECORDING_NOT_KEPT})
        self.assertEqual(rc["written"][0]["text"], "Confirmada mesa sábado 21h Warren")
        self.assertEqual(rc["proof"]["read_back_sha256"], prep["read_back"]["sha256"])        # the yes it rests on
        self.assertEqual(rc["proof"]["read_back"], prep["read_back"]["lines"])               # exactly the words approved
        self.assertEqual((rc["proof"]["approved"]["how"], rc["proof"]["approved"]["said"]), ("chat", "Yeah."))
        self.assertIn(rc["references"]["sasha"], " ".join(rc["proof"]["read_back"]))
        self.assertNotIn(BOTAVARA, json.dumps(self.calls.calls[prep["call_id"]], default=str))   # shown, never stored

    def test_another_accounts_reservation_has_no_receipt(self):
        prep = self.booked()
        self.calls.calls[prep["call_id"]]["account_id"] = "22222222-2222-4222-8222-222222222222"
        self.assertEqual(self.c.get(f"/api/booking/reservations/{prep['trip_item_id']}/receipt").status_code, 404)


if __name__ == "__main__":
    unittest.main()
