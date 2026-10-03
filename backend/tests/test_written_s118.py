"""Sasha 118 · confirmed in writing, whichever way it comes (written.py): a venue's email or text to Sasha for ANY booking
she made, and a confirmation the guest forwards — filed on the one booking it names, never guessed. Offline.

    cd backend && python -m unittest tests.test_written_s118 -v
"""
from __future__ import annotations

import asyncio
import os
import unittest
from datetime import datetime, timezone
from unittest import mock

from booking_signer import call_store as CS, guest_whatsapp as GW, inbound_phone as IP, written as W
from tests import test_guest_whatsapp_s75 as TG

NOW = datetime(2026, 10, 2, 10, 0, tzinfo=timezone.utc)
A, B = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"


def req(day, hhmm, party, name):
    return {"schema": "reservation/1", "flow": "book", "who": {"name": name}, "what": {"activity": "a table", "activity_venue_lang": "una mesa", "category": "restaurant"},
            "where": {}, "when": {"mode": "at", "at": f"{day}T{hhmm}"}, "how_many": {"count": party, "unit": "people"}}


def cand(tid, venue, day, hhmm, party, name, account=A, **kw):
    return {"trip_item_id": tid, "account_id": account, "venue": venue, "date_time": datetime.fromisoformat(f"{day}T{hhmm}:00+02:00"),
            "local_timezone": "Europe/Madrid", "party": party, "status": kw.pop("status", "unclear"), "booking_reference": kw.pop("ref", None),
            "own_reference": kw.pop("own", None), "call_id": kw.pop("call_id", None), "request": req(day, hhmm, party, name), **kw}


BOTAVARA = cand("t-bota", "Botavara Chamberí", "2026-10-03", "21:00", 2, "Tyler Warren", own="KHH42", call_id=None)
HANAKURA = cand("t-hana", "Hanakura", "2026-10-03", "21:00", 2, "Tyler Warren", status="requested")
LUCIO = cand("t-lucio", "Casa Lucio", "2026-10-08", "21:00", 4, "Ana García", account=B, ref="TF8842")


def run(c):
    return asyncio.get_event_loop().run_until_complete(c)


class Pick(unittest.TestCase):
    def test_each_rule_and_never_a_guess(self):
        cs = [BOTAVARA, HANAKURA, LUCIO]
        self.assertEqual(W.pick(cs, None, "Confirmada su reserva, referencia K-HH42. Gracias.", NOW)[0]["trip_item_id"], "t-bota")
        self.assertEqual(W.pick(cs, "Reserva", "Localizador TF8842 confirmado", NOW)[0]["trip_item_id"], "t-lucio")
        got, why = W.pick(cs, None, "Hanakura: confirmamos la mesa el sábado 3 de octubre a las 21:00 para 2 personas.", NOW)
        self.assertEqual((got["trip_item_id"], why), ("t-hana", "the venue's name and the day"))
        got, why = W.pick(cs, None, "Reserva a nombre de García, jueves 8 de octubre, 21:00, 4 personas. Confirmada.", NOW)
        self.assertEqual((got["trip_item_id"], why), ("t-lucio", "the guest's surname and the day"))
        got, why = W.pick(cs, None, "Confirmada la reserva de Warren para el sábado 3 de octubre a las 21:00.", NOW)
        self.assertIsNone(got)                                                     # Botavara AND Hanakura: two fit
        self.assertIn("not guessed", why)
        self.assertIsNone(W.pick(cs, None, "Gracias por su visita.", NOW)[0])

    def test_a_forward_is_read_for_the_venues_words(self):
        fwd = ("Look, they confirmed!\n\n---------- Forwarded message ---------\nFrom: Hanakura <info@hanakura.es>\n"
               "Date: Fri, 2 Oct 2026\nSubject: Reserva\nTo: tyler@example.com\n\n> Confirmamos su reserva: sábado 3 de octubre, 21:00, 2 personas.")
        words = W.venue_words(fwd, forwarded=True)
        self.assertEqual(words, "Confirmamos su reserva: sábado 3 de octubre, 21:00, 2 personas.")
        self.assertNotIn("Look, they confirmed", words)


class Filing(unittest.TestCase):
    def setUp(self):
        asyncio.set_event_loop(asyncio.new_event_loop())
        self.saved = IP.STORE
        calls = CS.MemoryCallStore()
        calls.trip_items = {c["trip_item_id"]: {"id": c["trip_item_id"], "status": c["status"]} for c in (BOTAVARA, HANAKURA, LUCIO)}
        IP.STORE = IP.MemoryInboundStore(calls)
        IP.STORE.candidates = [BOTAVARA, HANAKURA, LUCIO]

    def tearDown(self):
        IP.STORE = self.saved

    def test_4_a_form_bookings_confirmation_emailed_to_sasha_confirms_it(self):
        got = run(W.file("rcv-1", "email", "info@hanakura.es", "Re: reserva",
                         "Hanakura: confirmamos su mesa el sábado 3 de octubre a las 21:00 para 2 personas. Le esperamos.", NOW))
        self.assertEqual((got["trip_item_id"], got["result"]), ("t-hana", "confirmed"), got)
        self.assertEqual(IP.STORE.calls.trip_items["t-hana"]["status"], "confirmed")
        row = IP.STORE.rows["rcv-1"]
        self.assertEqual((row["channel"], row["trip_item_id"], row["reading"]["result"]), ("email", "t-hana", "confirmed"))
        self.assertTrue(row["from_key"].startswith("sha256:"))                     # the sender, hashed
        self.assertEqual(run(W.file("rcv-1", "email", "x", None, "Hanakura confirma … sábado 3 de octubre 21:00 2 personas", NOW))["result"],
                         "already filed")                                          # a redelivery is filed once

    def test_3_a_forward_from_the_guest_is_scoped_to_their_own_bookings(self):
        text = "---------- Forwarded message ---------\nFrom: TheFork\n\nReserva confirmada en Casa Lucio, localizador TF8842."
        self.assertIsNone(run(W.file("fwd-1", "email", "tyler@example.com", None, text, NOW, account=A, forwarded=True)))   # not A's
        got = run(W.file("fwd-2", "email", "ana@example.com", None, text, NOW, account=B, forwarded=True))
        self.assertEqual(got["trip_item_id"], "t-lucio")
        self.assertEqual(IP.STORE.rows["fwd-2"]["reading"]["forwarded_by"], "guest")

    def test_a_no_never_cancels_and_another_time_is_proposed(self):
        got = run(W.file("rcv-2", "email", "r@botavara.es", None, "Sobre K-HH42: el sábado 3 de octubre solo tenemos a las 22:30 para 2.", NOW))
        self.assertEqual(got["result"], "proposed")
        self.assertEqual(IP.STORE.calls.trip_items["t-bota"]["status"], "proposed")


class OnWhatsApp(TG.Base):
    def setUp(self):
        super().setUp()
        self.link()
        run(GW.STORE.put_state(GW.wa_key(TG.GUEST), {"history": [], "pending": None, "last_inbound_at": TG.NOW, "link_tries": []}))
        self.ip = IP.STORE
        calls = CS.MemoryCallStore()
        calls.trip_items = {"t-hana": {"id": "t-hana", "status": "requested"}}
        IP.STORE = IP.MemoryInboundStore(calls)
        IP.STORE.candidates = [{**HANAKURA, "account_id": TG.ACCOUNT}]

    def tearDown(self):
        IP.STORE = self.ip
        super().tearDown()

    def test_3_a_forwarded_confirmation_on_whatsapp_is_filed_and_answered(self):
        self.say("Reenviado: Hanakura — Su reserva está confirmada para el sábado 3 de octubre a las 21:00, 2 personas. ¡Le esperamos!")
        self.assertEqual(self.bodies()[-1], "✅ Confirmed in writing: Hanakura, Saturday 3 October. I've filed their confirmation on it (forwarded by you).")
        self.assertEqual(IP.STORE.calls.trip_items["t-hana"]["status"], "confirmed")
        self.assertEqual(GW.api.calls, [])                                         # no search, nothing booked

    def test_a_new_request_is_never_taken_for_a_forward(self):
        self.say("Dinner for 2 on Saturday 3 October at 21:00 in Chamberí please, your booking help is great")
        self.assertIn("/api/booking/venues/find", self.api_paths())
        self.assertEqual(IP.STORE.rows, {})


if __name__ == "__main__":
    unittest.main()


from tests import test_booking_ladder as TBL  # noqa: E402


@unittest.skipUnless(TBL.PG_URL, "BOOKING_TEST_DATABASE_URL is not set — the Postgres half did NOT run")
class OnPostgres(unittest.TestCase):
    """The candidates query and the sign-in address lookup against real tables (the memory stores hid a SQL bug once)."""

    @classmethod
    def setUpClass(cls):
        TBL.OnPostgres.setUpClass.__func__(cls)
        import asyncpg, pathlib
        sql = (pathlib.Path(__file__).resolve().parents[1] / "booking_signer" / "sql" / "018_booking_forms.sql").read_text()

        async def apply():
            c = await asyncpg.connect(TBL.PG_URL)
            try:
                if not await c.fetchval("select to_regclass('public.booking_forms') is not null"):
                    await c.execute(sql[sql.index("begin;"):sql.index("-- VERIFY")])
            finally:
                await c.close()
        asyncio.run(apply())

    def test_candidates_scoped_by_account_and_by_what_sasha_made(self):
        import asyncpg, uuid as U
        from booking_signer.store import PostgresStore
        from booking_signer.ladder_store import PostgresLadderStore

        async def go():
            c = await asyncpg.connect(TBL.PG_URL)
            try:
                trip = await c.fetchval("insert into trips (owner_id, title) values ($1, 'w118') returning id", U.UUID(TBL.DEMO_ACCOUNT_ID))
                item = await c.fetchval("insert into trip_items (trip_id, type, status, provider_name, date_time) values "
                                        "($1, 'restaurant', 'requested', 'Hanakura', now() + interval '1 day') returning id", trip)
            finally:
                await c.close()
            base = PostgresStore(TBL.PG_URL)
            st = IP.PostgresInboundStore(base)
            mine = await st.written_candidates(datetime(2026, 1, 1, tzinfo=timezone.utc), TBL.DEMO_ACCOUNT_ID)
            anyone = await st.written_candidates(datetime(2026, 1, 1, tzinfo=timezone.utc), None)
            nobody = await PostgresLadderStore(base).account_by_email("nobody@example.com")
            c = await asyncpg.connect(TBL.PG_URL)
            try:
                await c.execute("delete from trip_items where id = $1", item)
                await c.execute("delete from trips where id = $1", trip)
            finally:
                await c.close()
            return str(item), mine, anyone, nobody
        item, mine, anyone, nobody = asyncio.run(go())
        self.assertIn(item, [m["trip_item_id"] for m in mine])                     # the guest's own: any of theirs
        self.assertNotIn(item, [m["trip_item_id"] for m in anyone])               # a venue writing: only what Sasha made
        self.assertIsNone(nobody)
