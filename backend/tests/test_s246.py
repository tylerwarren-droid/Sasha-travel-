"""Sasha 246 · HOW SHE STARTS: every return — /s2, /next, WhatsApp — only "Hey <first name>, what can I help you with?". A new person
is asked once what to call her, and it's remembered. Memory and history are kept exactly as before (handed to the model, never
recited). And WhatsApp's way back from a space ("sasha") is unchanged."""
from __future__ import annotations

import asyncio
import unittest
from unittest import mock

from agapi import s2_memory as MEM

A = "00000000-0000-4000-8000-000000000246"
SEARCH = {"ribbon": "5 Indian restaurants in Madrid · tonight 21:00", "cards": [{"place_id": "p1", "name": "Casa Gate"}],
          "calls": [{"tool": "search_venues", "ok": True}]}


def run(c):
    return asyncio.run(c)


class _Contacts:
    def __init__(self, name=None):
        self.name = name

    async def get(self, account):
        return {"name": self.name} if self.name else None


class Opening(unittest.TestCase):
    def setUp(self):
        for p in (mock.patch.object(MEM, "RUN", None), mock.patch.dict(MEM._MEM, {}, clear=True)):
            p.start()
            self.addCleanup(p.stop)

    def contacts(self, name):
        from booking_signer import contacts as CT
        return mock.patch.object(CT, "STORE", _Contacts(name))

    def test_a_known_person_hears_only_hey_name(self):
        run(MEM.remember(A, "s-1", "Indian in Madrid tonight", "Here are five.", SEARCH))
        with self.contacts("Tyler Warren"):
            got = run(MEM.recall(A, "s-2"))
        self.assertEqual(got["line"], "Hey Tyler, what can I help you with?")
        self.assertNotIn("Indian", got["line"])                                   # never the last topic
        self.assertEqual([m["role"] for m in got["recent"]], ["user", "assistant"])   # the history is kept
        from app.agent import sasha as AG
        self.assertIn("never bring this up yourself", AG._HANDOVER.pop("s-2"))    # she uses it only when THEY refer to it
        AG._SCREEN.pop("s-2", None)

    def test_a_new_person_is_asked_once_and_the_name_is_remembered(self):
        with self.contacts(None):
            self.assertEqual(run(MEM.recall(A, None))["line"], MEM.ASK_NAME)
            self.assertEqual(run(MEM.recall(A, None))["line"], "Hey, what can I help you with?")   # never asked twice
            from agapi import s2_home as H
            r = run(H.remember_name(type("C", (), {"account": A})(), {"name": "  maría josé "}))
            self.assertEqual(r["name"], "María")
            self.assertEqual(run(MEM.recall(A, None))["line"], "Hey María, what can I help you with?")

    def test_not_a_name(self):
        self.assertIsNone(MEM._clean_name("12345"))
        self.assertIsNone(MEM._clean_name(""))

    def test_the_tool_is_offered_on_s2_and_next(self):
        from agapi import v0 as API
        from app.agent import s2 as S2, sasha as AG
        self.assertIn("remember_name", [t["name"] for t in API.HOME_TOOLS])
        self.assertIn("remember_name", S2.S2_TOOLS)
        self.assertEqual(AG.RENDER["remember_name"], "inline")


class WhatsAppGreeting(unittest.TestCase):
    def test_greetings(self):
        from booking_signer import wa_agent as WA
        for g in ("Sasha", "hi", "Hi Sasha!", "hey there", "Hola", "good morning"):
            self.assertTrue(WA.GREETING.match(g), g)
        for r in ("Can you make me a reservation tonight", "hi, book Indian tonight", "sasha book a table"):
            self.assertFalse(WA.GREETING.match(r), r)

    def test_the_way_back_from_a_space_is_sasha(self):
        from products import whatsapp as PW
        self.assertTrue(PW._EXIT.match("sasha"))
        self.assertTrue(PW._EXIT.match("Back to Sasha"))


if __name__ == "__main__":
    unittest.main()
