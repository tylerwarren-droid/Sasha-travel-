"""Sasha 321 · option (c), Tyler's go: the voice avatar and the REST chat BOOK — a venue booking there runs the one brain (wa_agent.agent_turn
→ search_venues / hold_venue / book_venue → AgAPI's send, venues._via_agapi), the same path /s2 and WhatsApp use; the person's yes is AgAPI's
in_app_tap from THAT request's own session. "I'll hand this to Tyler" only when AgAPI has no route.

Root test: (1) one truth — AgAPI's act (venue.submit_booking), approved by the request's own session (venue_submit.session_of, the ONE
reader for /s2, /next, the avatar and the REST chat). (2) No surface-only sender: voice_turn never reaches guest_whatsapp's venue rungs for
a venue turn. (3) Whole class: a venue booking, its follow-up words ("Sasha Test Venue", "Handle it", "yes") and a cancellation, typed or
spoken; a flight / hotel / trip stays on its own flow, even right after a venue turn. Offline.

    cd backend && python -m unittest tests.test_s321 -v
"""
from __future__ import annotations

import asyncio
import pathlib
import types
import unittest
from datetime import datetime, timezone
from unittest import mock

from agapi import venue_submit as VS
from booking_signer import guest_whatsapp as GW, voice_turn as VT, wa_agent as WA

BACK = pathlib.Path(__file__).resolve().parents[1]
ACCT = "acct-321"


class _Store:
    def __init__(self):
        self.rows = {}

    async def get_state(self, key):
        return WA.unpack_state(dict(self.rows.get(key) or {"history": [], "pending": None, "last_inbound_at": None}))

    async def put_state(self, key, st):
        self.rows[key] = {**st, "pending": WA.pack_pending(st)}


def run_turns(turns, tap=None, venues_only=False):
    """Each turn through voice_turn.turn; the agent and guest_whatsapp's flow are recorded, never run."""
    store, seen = _Store(), []

    async def agent_turn(ch, body, payload, st, out, now, **kw):
        seen.append(("agent", body, VS.TAP.get(), ch["account_id"]))
        out.text("Done — I've asked Sasha Test Venue." if body == "yes" else "Which one?")
        return out.said()

    async def new_request(ctx, t):
        seen.append(("old", t, VS.TAP.get(), ctx["account"]))
        ctx["out"].text("old flow")

    async def no_pending(ctx, t, b):
        return False

    out = []
    with mock.patch.object(GW, "STORE", store), mock.patch.object(WA, "agent_turn", agent_turn), \
            mock.patch.object(GW, "_new_request", new_request), mock.patch.object(GW, "_answer_pending", no_pending), \
            mock.patch("agapi.person_access.warm", mock.AsyncMock()):
        for t in turns:
            out.append(asyncio.run(VT.turn(ACCT, t, [], tap=tap, venues_only=venues_only)))
    return seen, out


class AVenueTurnIsTheOneBrains(unittest.TestCase):
    def test_typed_booking_its_follow_ups_and_the_yes_go_to_the_agent_with_his_session(self):
        tap = {"kind": "supabase", "token": "tok"}
        seen, out = run_turns(["dinner for 2 in Chamberí, Madrid on Saturday at 9pm", "Sasha Test Venue", "Handle it", "yes"], tap=tap)
        self.assertEqual([s[0] for s in seen], ["agent"] * 4)                       # never guest_whatsapp's venue rungs
        self.assertTrue(all(s[2] == tap for s in seen))                              # his yes = AgAPI's in_app_tap, from THIS request
        self.assertIsNone(VS.TAP.get())                                              # held for the turn only
        self.assertIn("Done", out[-1]["response"])

    def test_a_spoken_booking_and_a_cancellation_are_the_agents(self):
        for said in ("Uh, a table for two at the Sasha Test Venue in Madrid, Saturday at nine at night, please.",
                     "cancel my Sasha Test Venue booking"):
            seen, _ = run_turns([said])
            self.assertEqual(seen[0][0], "agent", said)

    def test_a_flight_stays_on_its_own_flow_even_right_after_a_venue(self):
        seen, _ = run_turns(["dinner for 2 in Chamberí, Madrid on Saturday at 9pm", "book a flight from Madrid to London on 3 January"])
        self.assertEqual([s[0] for s in seen], ["agent", "old"])

    def test_the_rest_chat_takes_only_venue_turns(self):
        seen, out = run_turns(["book a flight from Madrid to London on 3 January"], venues_only=True)
        self.assertEqual((seen, out), ([], [None]))                                  # the conductor's, as before
        seen, _ = run_turns(["dinner for 2 in Chamberí, Madrid on Saturday at 9pm"], venues_only=True)
        self.assertEqual(seen[0][0], "agent")

    def test_venue_ask(self):
        now = datetime.now(timezone.utc)
        self.assertTrue(VT.venue_ask("dinner for 2 in Chamberí, Madrid on Saturday at 9pm", now))
        for t in ("book a flight from Madrid to London", "a hotel in Madrid for 2 nights", "tell me about Hue", ""):
            self.assertFalse(VT.venue_ask(t, now), t)


class OneSessionReader(unittest.TestCase):
    def req(self, **h):
        return types.SimpleNamespace(headers={k.replace("_", "-"): v for k, v in h.items()})

    def test_in_app_session(self):
        self.assertEqual(VS.session_of(self.req(authorization="Bearer abc")), {"kind": "supabase", "token": "abc"})
        self.assertEqual(VS.session_of(self.req(x_sasha_session="founder")), {"kind": "founder"})
        self.assertIsNone(VS.session_of(self.req()))

    def test_every_surface_reads_it(self):
        self.assertIn("_VS.session_of(request)", (BACK / "app/agent/sasha.py").read_text())
        vc = (BACK / "app/api/voice_conductor.py").read_text()
        self.assertIn("tap=_VS.session_of(request)", vc)
        rc = (BACK / "app/api/conductor.py").read_text()
        self.assertIn("tap=_VS.session_of(request), venues_only=True", rc)


class TheGateAssertsIt(unittest.TestCase):
    def test_core_suites_want_an_agapi_act_never_tyler(self):
        cs = (BACK / "scripts/core_suites.py").read_text()
        for name in ("REST typed → the test venue booked through AgAPI", "REST voice phrasing → the test venue booked through AgAPI",
                     "GUIDED 7: the trip's restaurant is booked through AgAPI"):
            self.assertIn(name, cs)
        self.assertNotIn("REST typed → the test venue is handed to Tyler", cs)


if __name__ == "__main__":
    unittest.main()
