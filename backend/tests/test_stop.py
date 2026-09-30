"""S-56 · STOP (booking_signer/stop.py): what counts, the call path through the sweeper, and the Postgres record.

    cd backend && python -m unittest tests.test_stop -v
"""
from __future__ import annotations

import asyncio
import json
import os
import pathlib
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from unittest import mock
from urllib.parse import urlsplit

from booking_signer import call_routes, calls as C, optins as O, stop as S
from booking_signer.call_store import MemoryCallStore

HERE = pathlib.Path(__file__).parent
SQL_DIR = HERE.parent / "booking_signer" / "sql"
PG_URL = os.getenv("BOOKING_TEST_DATABASE_URL", "")
NOW = datetime(2026, 10, 5, 11, 0, tzinfo=timezone.utc)


def run(c):
    return asyncio.run(c)


class Detect(unittest.TestCase):
    def test_stop_in_any_language_on_its_own_line(self):
        for said in ("STOP", "Stop.", "para", "PARE!", "Baja", "DUR", "Stopp", "Arrêt", "basta", "UNSUBSCRIBE", "No más", "Não quero"):
            self.assertEqual(S.detect(f"{said}\n\nThanks"), said, said)

    def test_stop_phrases_anywhere(self):
        for said in ("Please don't contact us again.", "Por favor, no nos llaméis más.", "Dadnos de baja, gracias.",
                     "Parem de enviar mensagens.", "Não nos contactem mais.", "Merci de ne plus nous contacter.", "Ne nous appelez plus.",
                     "Bitte nicht mehr kontaktieren.", "Non contattateci più.", "Lütfen bizi aramayın.", "Stop contacting us",
                     "We'd like to opt out", "Remove us from your list"):
            self.assertIsNotNone(S.detect(f"Hola,\n{said}"), said)

    def test_ordinary_words_are_not_a_stop(self):
        for said in ("Sí, perfecto: mesa para 4 el jueves.", "Para cualquier cambio, llamadnos.", "Feel free to stop by anytime!",
                     "Tenemos mesa. ¿Para cuántos?", "The bus stop is outside.", "Paramos a las 16:00.", "Pare de fumar"):
            self.assertIsNone(S.detect(said), said)

    def test_only_the_reply_counts_not_what_it_quotes(self):
        self.assertIsNone(S.detect("Confirmado.\n\nOn Tue, 29 Sep 2026 at 10:00, Sasha <s@k.test> wrote:\n> Reply STOP to stop"))
        self.assertIsNone(S.detect("Ok\n> STOP"))

    def test_on_a_call_a_lone_word_is_not_enough_but_a_phrase_is(self):
        self.assertIsNone(S.detect("Para", spoken=True))
        self.assertIsNone(S.detect("Stop.", spoken=True))
        self.assertEqual(S.detect("Mire, no nos llamen más, por favor.", spoken=True), "Mire, no nos llamen más, por favor.")

    def test_the_acknowledgement_is_in_the_call_instructions_in_its_language(self):
        p = C.parse_call_particulars({"date": "2026-10-08", "time": "20:00", "party": 2, "name": "Anna Johnson"})
        venue = C.CallVenue(key="read:x", name="La Contra", number_env="", language="es", timezone="Europe/Madrid", number="+34910000000")
        b = C.build_call(venue, p, NOW)["brief"]
        self.assertIn('"Entendido. Sasha no volverá a contactarles."', b["task"])
        self.assertLessEqual(len(b["task"]), 2000)
        c = C.build_call(venue, p, NOW, purpose="cancel", reference="Johnson")["brief"]
        self.assertIn("Entendido. Sasha no volverá a contactarles.", c["task"])
        self.assertLessEqual(len(c["task"]), 2000)


class CallTranscript(unittest.TestCase):
    """A venue that says stop ON THE CALL: the sweeper records it before the reading."""

    def setUp(self):
        self.env = mock.patch.dict(os.environ, {"BLAND_API_KEY": "test-key-not-real", "SASHA_CALLS_ENABLED": "1"})
        self.env.start()
        self.calls, self.optins = MemoryCallStore(), O.MemoryOptinStore()
        self.saved = (call_routes.CALL_STORE, call_routes.HTTP, call_routes.READER, call_routes.NOW, S.STOP_STORE, O.OPTIN_STORE)
        S.STOP_STORE, O.OPTIN_STORE = S.MemoryStopStore(self.optins, None, self.calls), self.optins
        self.details = None

        class R:
            def __init__(s, body):
                s.status_code, s._b = 200, body

            def json(s):
                return s._b

        async def http(method, url, headers, json=None):
            return R(self.details)

        async def reader(t):
            return json.dumps({"reading": "no", "quote": "no nos llamen más", "raised": []})
        call_routes.CALL_STORE, call_routes.HTTP, call_routes.READER, call_routes.NOW = self.calls, http, reader, (lambda: NOW)

    def tearDown(self):
        (call_routes.CALL_STORE, call_routes.HTTP, call_routes.READER, call_routes.NOW, S.STOP_STORE, O.OPTIN_STORE) = self.saved
        self.env.stop()

    def placed(self, ids, cid="11111111-1111-4111-8111-000000000009"):
        venue = C.CallVenue(key="read:x", name="La Contra", number_env="", language="es", timezone="Europe/Madrid",
                            number="+34910000000", venue_ids=tuple(ids))
        b = C.build_call(venue, C.parse_call_particulars({"date": "2026-10-08", "time": "20:00", "party": 2, "name": "Anna Johnson"}), NOW)
        row = {"call_id": cid, "account_id": "a", "venue_key": "read:x", "dialled_number": "+34910000000", "language": "es",
               "guest_name": "Anna Johnson", "guest_phone": None, "brief": b["brief"], "brief_sha256": b["brief_sha256"],
               "read_back_lines": b["read_back_lines"], "read_back_sha256": b["read_back_sha256"], "created_at": NOW,
               "venue_name": "La Contra", "local_date": NOW.date(), "local_time": NOW.time(), "local_timezone": "Europe/Madrid", "party_size": 2}
        run(self.calls.put_call(row, None))
        run(self.calls.claim("a", cid, {}, NOW, NOW - timedelta(minutes=1), 3, NOW - timedelta(days=1)))
        run(self.calls.mark_placed(cid, C.Placed(True, "bland-9", 200, {}, None), NOW))
        return cid

    def test_a_stop_said_on_the_call_is_recorded_verbatim_and_ends_email_too(self):
        cid = self.placed(["places:ChIJ-x", "host:lacontra.test"])
        self.details = {"completed": True, "status": "completed", "answered_by": "human", "transcripts": [
            {"user": "assistant", "text": "Hola, soy Sasha…"}, {"user": "user", "text": "No, gracias. Y no nos llamen más, por favor."},
            {"user": "assistant", "text": "Entendido. Sasha no volverá a contactarles."}]}
        self.assertEqual(run(call_routes.sweep_once()), 1)
        row = self.optins.rows[-1]
        self.assertEqual((row["venue_id"], row["channel"], row["scope"], row["withdrawn_how"]),
                         ("places:ChIJ-x", "phone", "+34910000000", "said stop by phone"))
        self.assertEqual(row["withdrawn_evidence"]["verbatim"], "No, gracias. Y no nos llamen más, por favor.")
        self.assertEqual(row["withdrawn_evidence"]["call_id"], cid)
        self.assertEqual(O.check_send(self.optins.rows, "email").rule, "venue_opted_out")

    def test_sashas_own_words_on_the_call_never_count(self):
        self.placed(["places:ChIJ-x"])
        self.details = {"completed": True, "status": "completed", "answered_by": "human", "transcripts": [
            {"user": "assistant", "text": "Si no quieren que les llamemos, dígannos: no nos llamen más."},
            {"user": "user", "text": "Sí, perfecto, mesa para dos."}]}
        run(call_routes.sweep_once())
        self.assertEqual(self.optins.rows, [])

    def test_it_closes_every_live_opt_in_chain_and_marks_only_pending_requests(self):
        run(self.optins.add({"venue_id": "host:lacontra.test", "channel": "whatsapp", "scope": "+34600111222", "status": "active",
                             "recorded_at": NOW - timedelta(days=5)}))
        out = run(S.STOP_STORE.record(["places:ChIJ-x", "host:lacontra.test"], "email", "r@lacontra.test", "STOP", {}, NOW))
        self.assertEqual((out.first, out.rows), (True, 2))
        self.assertEqual({(r["channel"], r["status"]) for r in self.optins.rows[-2:]}, {("email", "withdrawn"), ("whatsapp", "withdrawn")})
        again = run(S.STOP_STORE.record(["places:ChIJ-x"], "email", "r@lacontra.test", "STOP", {}, NOW + timedelta(minutes=1)))
        self.assertFalse(again.first)


@unittest.skipUnless(PG_URL, "BOOKING_TEST_DATABASE_URL is not set — the Postgres half did NOT run")
class OnPostgres(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if "test" not in urlsplit(PG_URL).path.lstrip("/"):
            raise unittest.SkipTest("refusing a database whose name does not contain 'test'")

        async def fresh():
            import asyncpg
            c = await asyncpg.connect(PG_URL)
            try:
                await c.execute("drop schema if exists auth cascade; drop schema public cascade; create schema public;")
                await c.execute((HERE / "fixtures" / "model_a_live_2026-09-28.sql").read_text(encoding="utf-8"))
                for f in ("001_booking_storage.sql", "002_prepared_status.sql", "003_phone_calls.sql", "004_ladder.sql",
                          "005_slot_links.sql", "007_retention_log.sql", "008_venue_optins.sql", "009_venue_optin_requests.sql",
                          "010_withdrawal_channels.sql"):
                    await c.execute((SQL_DIR / f).read_text(encoding="utf-8"))
                # 010 refuses a second run
                try:
                    await c.execute((SQL_DIR / "010_withdrawal_channels.sql").read_text(encoding="utf-8"))
                    raise AssertionError("010 ran twice")
                except asyncpg.exceptions.RaiseError as e:
                    assert "already applied" in str(e)
            finally:
                await c.close()
        run(fresh())

    def test_the_record_lands_and_an_active_opt_in_still_cannot_name_phone(self):
        from booking_signer.store import PostgresStore

        async def go():
            import asyncpg
            base = PostgresStore(PG_URL)
            try:
                out = await S.PostgresStopStore(base).record(["places:ChIJ-x"], "phone", "+34910000000",
                                                             "No nos llamen más.", {"call_id": "c1"}, NOW)
                rows = await base._run(lambda c: c.fetch("select channel, status, withdrawn_evidence from venue_optins"))
                with self_.assertRaises(asyncpg.exceptions.CheckViolationError):
                    await base._run(lambda c: c.execute(
                        "insert into venue_optins (venue_id, channel, scope, status, agreed_at, method, wording_version, wording_sha256, "
                        "wording_text, evidence) values ('v','phone','+34','active',now(),'form','v2',repeat('a',64),'t','{}'::jsonb)"))
                return out, [dict(r) for r in rows]
            finally:
                await base.close()
        self_ = self
        out, rows = run(go())
        self.assertEqual((out.first, out.rows, out.guests_told), (True, 1, 0))
        self.assertEqual((rows[0]["channel"], rows[0]["status"]), ("phone", "withdrawn"))
        ev = rows[0]["withdrawn_evidence"]
        ev = json.loads(ev) if isinstance(ev, str) else ev
        self.assertEqual(ev["verbatim"], "No nos llamen más.")


if __name__ == "__main__":
    unittest.main()
