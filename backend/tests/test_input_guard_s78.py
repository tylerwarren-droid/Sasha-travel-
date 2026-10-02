"""S-78 step 1 · a password, code, key or card number typed in the chat never reaches the model and is never stored.

    cd backend && python -m unittest tests.test_input_guard_s78 -v
"""
from __future__ import annotations

import asyncio
import os
import sqlite3
import tempfile
import unittest
from unittest import mock

from booking_signer.vault import guard as G


class WhatTripsIt(unittest.TestCase):
    def test_secrets(self):
        for s in ("my Mercadona password is hunter2!", "Password: hunter2", "la contraseña es Gato1234", "pwd=abc",
                  "my PIN is 4821", "the one-time code is 552901", "mot de passe: soleil",
                  "here's the key sk-ant-api03-AbCdEfGh1234567890XyZ", "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0"):
            self.assertEqual(G.looks_like_secret(s), "secret", s)

    def test_card_numbers(self):
        for s in ("4111 1111 1111 1111", "card 5555-5555-5555-4444 exp 12/29", "378282246310005"):
            self.assertEqual(G.looks_like_secret(s), "card", s)

    def test_ordinary_booking_lines_pass(self):
        for s in ("Book a luxury dinner for two in Chamberí on Saturday at nine.", "cancel Botavara",
                  "my number is +44 7915 914215", "call me on 0044 7915 914215", "yes", "I forgot my password for Booking.com",
                  "reference K-7Q2M, booking 4567", "https://www.hanakura.es/reservas?date=2026-10-03&time=21:00",
                  "tyler.someone.long.address@example-domain.com", "4111 1111 1111 1112",
                  "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d"):
            self.assertIsNone(G.looks_like_secret(s), s)


class TheModelNeverSeesIt(unittest.TestCase):
    def setUp(self):
        asyncio.set_event_loop(asyncio.new_event_loop())   # ideas_agent makes an asyncio.Lock at import (3.9 needs a loop)
        from app.services import chat_store, conductor
        self.cs, self.co = chat_store, conductor
        fd, self.db = tempfile.mkstemp(suffix=".db"); os.close(fd)
        self.p_db = mock.patch.object(chat_store, "DB_PATH", self.db); self.p_db.start()
        self.model = mock.AsyncMock(side_effect=AssertionError("the model was called"))
        self.p_model = mock.patch.object(conductor.client.messages, "create", self.model); self.p_model.start()

    def tearDown(self):
        self.p_model.stop(); self.p_db.stop(); os.unlink(self.db)

    def _everything_stored(self) -> str:
        with sqlite3.connect(self.db) as c:
            names = [r[0] for r in c.execute("select name from sqlite_master where type='table'")]
            return " ".join(str(row) for n in names for row in c.execute(f"select * from {n}"))

    def test_hunter2_is_not_sent_not_stored_and_gets_the_fixed_reply(self):
        """S-78 §4.4, the fixture: the model mock is not called, no stored turn holds hunter2, the reply is the fixed one."""
        from fastapi.testclient import TestClient
        from app.main import app
        r = TestClient(app).post("/api/agents/conductor", json={"message": "my Mercadona password is hunter2!", "session_id": None})
        if r.status_code == 401:
            self.skipTest("CONDUCTOR_API_SECRET is set here")
        self.assertEqual(r.status_code, 200, r.text[:300])
        self.assertEqual(r.json()["response"], G.SECRET_REPLY)
        self.model.assert_not_called()
        self.assertNotIn("hunter2", self._everything_stored())
        self.assertNotIn("hunter2", str(r.json()["conversation_history"]))

    def test_a_card_typed_in_chat_is_refused_and_not_stored(self):
        from fastapi.testclient import TestClient
        from app.main import app
        r = TestClient(app).post("/api/agents/conductor", json={"message": "use my card 4111 1111 1111 1111"})
        if r.status_code == 401:
            self.skipTest("CONDUCTOR_API_SECRET is set here")
        self.assertEqual(r.json()["response"], G.CARD_REPLY)
        self.model.assert_not_called()
        self.assertNotIn("4111", self._everything_stored())

    def test_the_browser_sending_it_back_as_history_is_blanked_too(self):
        """The browser keeps what was typed and sends it as history next turn: it must not reach anything that reads it."""
        hist = [{"role": "user", "content": "my Mercadona password is hunter2!"}, {"role": "assistant", "content": G.SECRET_REPLY}]
        out = asyncio.get_event_loop().run_until_complete(
            self.co.conduct("find me a tattoo studio in Nairobi, KE", hist))
        self.assertEqual(out["booking_find"]["where"], "Nairobi")
        self.assertNotIn("hunter2", str(out["messages"]))
        self.model.assert_not_called()

    def test_save_turn_refuses_on_its_own(self):
        """A second, independent guard: even a caller that skipped the conductor cannot store it."""
        asyncio.get_event_loop().run_until_complete(self.cs.save_turn(
            session_id="s78", user_id=None, user_message="Password: hunter2", assistant_response="ok", title="Password: hunter2"))
        self.assertNotIn("hunter2", self._everything_stored())

    def test_the_voice_log_line_withholds_it(self):
        self.assertTrue(G.for_log("my pin is 4821").startswith("[withheld"))
        self.assertEqual(G.for_log("dinner for two"), "dinner for two")


if __name__ == "__main__":
    unittest.main()
