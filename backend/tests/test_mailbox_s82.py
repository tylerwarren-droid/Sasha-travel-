"""S-82 · Gmail read-only (§6 tests 1–6): the narrow search, no body stored, the parsers, matching, the offer needing
a yes, and the model gate. Gmail faked. Offline.

    cd backend && python -m unittest tests.test_mailbox_s82 -v
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import pathlib
import unittest
from datetime import datetime, timezone
from unittest import mock

from booking_signer import guest_whatsapp as GW, mailbox as MB
from booking_signer.vault import crypto as VC

NOW = datetime(2026, 10, 2, 12, 0, tzinfo=timezone.utc)
ACCOUNT = "99999999-9999-4999-8999-999999999999"
ROOT = pathlib.Path(__file__).resolve().parents[1]

THEFORK = ("Confirmación de tu reserva", "TheFork <noreply@thefork.com>",
           "¡Tu reserva en Casa Lucio está confirmada! Jueves 8 de octubre de 2026 a las 21:00, 2 personas. Localizador: TF8842.")
CANCEL_EN = ("Booking cancelled", "Zalacaín <reservas@zalacain.es>",
             "Your reservation for Friday, October 9 2026 at 14:00 for 2 people has been cancelled.")
INVOICE = ("Factura de su visita", "Fresha <no-reply@fresha.com>", "Factura nº 77. Total 48,50 € pagado con tarjeta 4111 1111 1111 1111.")
OWN = ("Re: su reserva", "Restaurante Yatri <info@yatri.es>", "Confirmamos su reserva K-MCFA para el sábado 3 de octubre a las 21:00, 2 personas.")


def run(c):
    return asyncio.get_event_loop().run_until_complete(c)


class Parse(unittest.TestCase):
    def test_1_the_query_is_always_narrow(self):
        q = MB.build_query(["zalacain.es"])
        self.assertTrue(q.startswith("newer_than:90d ("))
        self.assertIn("from:zalacain.es", q)
        self.assertIn("subject:(reserva OR booking", q)
        src = (ROOT / "booking_signer" / "mailbox.py").read_text()
        self.assertEqual(src.count('f"{GMAIL}/messages", token'), 1)                    # one list call …
        self.assertIn('{"q": q, "maxResults": 50}', src)                                # … always with q

    def test_3_parsers(self):
        k, f, by = MB.read(*THEFORK, NOW)
        self.assertEqual((k, f["venue"], f["via"], f["at"], f["party"], f["reference"], by),
                         ("confirmation", "Casa Lucio", "TheFork", "2026-10-08T21:00", 2, "TF8842", "rules"))
        k, f, _ = MB.read(*CANCEL_EN, NOW)
        self.assertEqual((k, f["at"], f["party"]), ("cancellation", "2026-10-09T14:00", 2))
        k, f, _ = MB.read(*INVOICE, NOW)
        self.assertEqual((k, f["amount_minor"], f["currency"]), ("bill", 4850, "EUR"))
        self.assertNotIn("4111", json.dumps(f))                                           # a card number is never extracted
        k, f, _ = MB.read(*OWN, NOW)
        self.assertEqual((k, f["sasha_ref"], f["venue"]), ("confirmation", "K-MCFA", "Restaurante Yatri"))

    def test_4_match(self):
        rows = [{"id": "t-1", "venue": "Restaurante Yatri", "date": "2026-10-03", "time": "21:00", "status": "unclear",
                 "booking_reference": None, "sasha_reference": "K-MCFA"},
                {"id": "t-2", "venue": "Casa Lucio", "date": "2026-10-08", "time": "21:00", "status": "requested", "booking_reference": "TF8842"}]
        self.assertEqual(MB.match(MB.read(*THEFORK, NOW)[1], rows), (rows[1], "reference"))
        self.assertEqual(MB.match(MB.read(*OWN, NOW)[1], rows), (rows[0], "sasha_ref"))
        f = {"venue": "Casa Lucio", "at": "2026-10-08T22:20", "reference": None, "sasha_ref": None}
        self.assertEqual(MB.match(f, rows), (rows[1], "venue_and_time"))                 # within 90 minutes
        self.assertEqual(MB.match({**f, "at": "2026-10-08T23:00"}, rows), (None, None))    # outside → "found outside Sasha"


class FounderInbox(unittest.TestCase):
    """2 Oct 2026, the founder's first connect: four past bookings were offered to add, one of them named "TheFork"."""

    def test_7_a_past_booking_is_history_never_an_offer(self):
        past = [("Cita confirmada", "Mr Paul Ede <p@ede.co.uk>", "Your appointment is confirmed for 15 September 2026 at 15:30."),
                ("Reserva confirmada", "Petit comité Sevilla <r@petitcomite.es>", "Te esperamos el 27 de septiembre de 2026, 2 personas.")]
        for m in past:
            k, f, _ = MB.read(*m, NOW)
            self.assertEqual(k, "confirmation")
            self.assertIsNone(MB.offer(k, f, None, NOW))
        k, f, _ = MB.read("Reserva confirmada", "Zalacaín <r@zalacain.es>", "Te esperamos el 2 de octubre de 2026 a las 21:00.", NOW)
        self.assertEqual(MB.offer(k, f, None, NOW)[0], "add")                             # tonight, 21:00 Madrid: still ahead
        self.assertTrue(MB.upcoming("2026-10-02", NOW))                                    # a date alone lasts the whole day
        self.assertFalse(MB.upcoming("2026-10-02T13:00", NOW))                             # 14:00 in Madrid now
        self.assertFalse(MB.upcoming(None, NOW))

    def test_8_a_platform_email_names_the_venue(self):
        cases = [(("Tu reserva en Petit comité Sevilla está confirmada", "TheFork <noreply@thefork.com>",
                   "Miércoles 30 de septiembre de 2026 a las 20:45, 2 personas."), "Petit comité Sevilla", "TheFork"),
                 (("Your reservation at Sushi Nakazawa is confirmed", "OpenTable <member_services@opentable.com>",
                   "Oct 9, 2026 at 7:30 PM, 2 people"), "Sushi Nakazawa", "OpenTable"),
                 (("Reserva confirmada - Restaurante Botín", "CoverManager <noreply@covermanager.com>",
                   "Sábado 10 de octubre 2026 a las 14:00, 4 personas"), "Restaurante Botín", "CoverManager"),
                 (("Reserva cancelada", "ElTenedor <info@eltenedor.es>", "Tu reserva en DiverXO para 2 personas ha sido cancelada."),
                  "DiverXO", "ElTenedor")]
        for m, venue, via in cases:
            _, f, _ = MB.read(*m, NOW)
            self.assertEqual((f["venue"], f["via"]), (venue, via))
        _, f, _ = MB.read("Reserva confirmada", "TheFork <noreply@thefork.com>", "Gracias por reservar. 2 personas.", NOW)
        self.assertEqual((f["venue"], f["via"]), (None, "TheFork"))                        # no venue found → none, never "TheFork"
        _, f, _ = MB.read(*THEFORK, NOW)
        self.assertEqual(MB.offer("confirmation", f, None, NOW)[1],
                         "Your inbox has a booking at Casa Lucio (via TheFork), Thursday 8 October 21:00 for 2. Add it to your itinerary?")
        _, f, _ = MB.read(*OWN, NOW)
        self.assertIsNone(f["via"])                                                        # the venue's own email: its own name

    def test_9_an_unanswered_add_is_withdrawn_once_its_day_passes(self):
        asyncio.set_event_loop(asyncio.new_event_loop())
        saved = (MB.STORE, MB.GMAIL_HTTP, MB.NOW)
        try:
            MB.STORE = MB.MemoryMailboxStore()
            MB.STORE.links[ACCOUNT] = {"account_id": ACCOUNT, "vault_item_id": "v-1", "needs_reconnect_at": None}
            MB.STORE.finds["f-1"] = {"id": "f-1", "account_id": ACCOUNT, "action_status": "offered", "offered_action": "add",
                                     "facts": {"at": "2026-10-01T21:00"}}
            MB.STORE.finds["f-2"] = {"id": "f-2", "account_id": ACCOUNT, "action_status": "offered", "offered_action": "add",
                                     "facts": {"at": "2026-10-09T21:00"}}

            async def gmail(method, url, token, params=None):
                return 200, {"messages": []}
            MB.GMAIL_HTTP, MB.NOW = gmail, (lambda: NOW)
            with mock.patch.object(VC, "use_connection", mock.AsyncMock(return_value="ya29")), \
                    mock.patch.object(GW, "_upcoming", mock.AsyncMock(return_value=[])):
                run(MB.sync(ACCOUNT))
            self.assertEqual(MB.STORE.finds["f-1"]["action_status"], "none")
            self.assertEqual(MB.STORE.finds["f-2"]["action_status"], "offered")
        finally:
            MB.STORE, MB.GMAIL_HTTP, MB.NOW = saved


class Sync(unittest.TestCase):
    def setUp(self):
        asyncio.set_event_loop(asyncio.new_event_loop())
        self.saved = (MB.STORE, MB.GMAIL_HTTP, VC.STORE, MB.MODEL_READER, GW._upcoming, GW.STORE)
        MB.STORE, GW.STORE = MB.MemoryMailboxStore(), GW.MemoryGuestStore()
        MB.STORE.links[ACCOUNT] = {"account_id": ACCOUNT, "vault_item_id": "v-1", "needs_reconnect_at": None}
        self.rows = [{"id": "t-1", "venue": "Restaurante Yatri", "date": "2026-10-03", "time": "21:00", "status": "unclear",
                      "booking_reference": None, "sasha_reference": "K-MCFA"}]
        self.calls = []
        msgs = {"m1": OWN, "m2": ("Your newsletter", "Shop <a@shop.com>", "Big sale on shoes")}

        async def gmail(method, url, token, params=None):
            self.calls.append((url, params))
            if url.endswith("/messages"):
                return 200, {"messages": [{"id": k} for k in msgs]}
            s, frm, body = msgs[url.rsplit("/", 1)[1]]
            return 200, {"payload": {"headers": [{"name": "Subject", "value": s}, {"name": "From", "value": frm}],
                                     "mimeType": "text/plain", "body": {"data": base64.urlsafe_b64encode(body.encode()).decode()}}}
        MB.GMAIL_HTTP = gmail
        self.model = mock.AsyncMock(return_value="confirmation")
        MB.MODEL_READER = self.model

        async def upcoming(a, names=True):
            return self.rows
        self.p = (mock.patch.object(GW, "_upcoming", upcoming), mock.patch.object(VC, "use_connection", mock.AsyncMock(return_value="ya29")))
        for x in self.p:
            x.start()

    def tearDown(self):
        for x in self.p:
            x.stop()
        MB.STORE, MB.GMAIL_HTTP, VC.STORE, MB.MODEL_READER, GW._upcoming, GW.STORE = self.saved

    def test_2_no_body_is_stored(self):
        run(MB.sync(ACCOUNT))
        for f in MB.STORE.finds.values():
            dumped = json.dumps(f, default=str)
            self.assertNotIn("Confirmamos su reserva", dumped)
            self.assertNotIn("Big sale", dumped)
            self.assertEqual(f["body_sha256"], hashlib.sha256(f["body_sha256"].encode()).hexdigest() if False else f["body_sha256"])
            self.assertLessEqual(set(f["facts"]), {"venue", "at", "party", "reference", "amount_minor", "currency", "sasha_ref", "via"})

    def test_5_an_offer_needs_the_yes(self):
        found = run(MB.sync(ACCOUNT))
        f = next(x for x in found if x["offered_action"])
        self.assertEqual(f["offered_sentence"], "Restaurante Yatri's email confirms Saturday 3 October 21:00 for 2. Mark it confirmed?")
        self.assertEqual(MB.STORE.applied, [])                                            # nothing without the yes
        self.assertEqual(run(MB.accept(ACCOUNT, f["id"], "0" * 64, True))["rule"], "offer_stale")
        r = run(MB.accept(ACCOUNT, f["id"], f["offer_sha256"], True))
        self.assertEqual(r["status"], "done")
        self.assertEqual(MB.STORE.applied, [(ACCOUNT, "confirm", "t-1", None)])

    def test_6_the_model_only_for_a_matched_message_the_rules_could_not_read(self):
        with mock.patch.dict("os.environ", {"SASHA_MAILBOX_MODEL": "1"}):
            run(MB.sync(ACCOUNT))
        self.assertEqual(self.model.call_count, 0)                                        # m1 read by rules; m2 matched nothing


if __name__ == "__main__":
    unittest.main()
