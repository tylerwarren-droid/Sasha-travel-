"""S-64 · the Stage B hooks in the CTO's conductor. ⛔ This FAILS when a CTO drop removed one and Stage B did not put it
back — booking-in-chat is the core, so its absence is a failed suite, not a quiet change.

    cd backend && python -m unittest tests.test_stage_b_hooks -v
"""
from __future__ import annotations

import unittest
from datetime import datetime, timezone

from booking_signer import chat_request as CR, routes

NOW = datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc)


class Hooks(unittest.TestCase):
    def test_both_hooks_are_in_the_conductor_in_order(self):
        h = routes.chat_hooks()
        self.assertEqual(h, {"psi_handoff": True, "booking_drafts": True, "response_fields": True, "in_order": True},
                         "a Stage B conductor hook is missing — re-apply it (CLAUDE.md, Stage B) and redeploy")


class TheResponseCarriesIt(unittest.TestCase):
    def test_the_http_response_carries_booking_find(self):
        """1 Oct: the conductor returned booking_find, and the HTTP model dropped it — the chat never saw it."""
        from fastapi.testclient import TestClient
        from app.main import app
        r = TestClient(app).post("/api/agents/conductor", json={"message": "find me a tattoo studio in Nairobi, KE"})
        if r.status_code == 401:
            self.skipTest("CONDUCTOR_API_SECRET is set here; the model check above still holds")
        self.assertEqual(r.json().get("booking_find"), {"what": "tattoo studio", "where": "Nairobi", "country": "KE"}, r.text[:300])


class Turn(unittest.TestCase):
    def test_a_booking_is_drafted_over_several_turns_asking_one_thing_at_a_time(self):
        t1 = CR.booking_turn("I'd like to book a massage", [], NOW)
        self.assertEqual(t1["response"], "Which day and time — or shall I ask them when they have space?")
        t2 = CR.booking_turn("3 October at 11:00", t1["messages"], NOW)
        self.assertEqual(t2["response"], "How many people is it for?")
        t3 = CR.booking_turn("just me, 1 person", t2["messages"], NOW)
        self.assertEqual(t3["reservation_draft"]["missing"], [])
        self.assertEqual(t3["reservation_draft"]["parts"]["when"], {"mode": "at", "at": "2026-10-03T11:00"})
        self.assertEqual(t3["response"], "So: a massage, 1 person, 2026-10-03 at 11:00. Which place? I'll look them up, "
                                         "book it, and read it all back to you before anything happens.")

    def test_ordinary_chat_is_left_to_the_conductor(self):
        self.assertIsNone(CR.booking_turn("What's the weather in Hanoi?", [], NOW))
        self.assertIsNone(CR.booking_turn("Find me a good massage place", [], NOW))       # no booking verb: not ours
        self.assertIsNone(CR.booking_turn("3 October at 11:00", [{"role": "assistant", "content": "Hello!"}], NOW))


if __name__ == "__main__":
    unittest.main()
