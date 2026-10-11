"""Sasha 237 · WhatsApp on the one brain (EU 232 §1.1–1.2): the flag routes a message to the agent (surface "wa"); every render
kind has a WhatsApp drawing; taps come back as the turns /s2 sends; STOP still wins; an old flow's button still finishes there.
Offline: the agent is a stand-in at wa_agent.agent_turn's boundary, or the real turn with a scripted model.

    cd backend && python -m unittest tests.test_wa_one_brain -v
"""
from __future__ import annotations

import os
import unittest
from datetime import datetime, timezone
from unittest import mock

from booking_signer import guest_whatsapp as GW, wa_agent as WA
from tests.test_guest_whatsapp_s75 import ACCOUNT, Base, run

NOW = datetime(2026, 10, 11, 12, 0, tzinfo=timezone.utc)


class Flag(unittest.TestCase):
    def test_modes(self):
        with mock.patch.dict(os.environ, {"SASHA_WA_BRAIN": ""}):
            self.assertFalse(WA.on(ACCOUNT))                                   # default: today's path exactly
        with mock.patch.dict(os.environ, {"SASHA_WA_BRAIN": "old"}):
            self.assertFalse(WA.on(ACCOUNT))
        with mock.patch.dict(os.environ, {"SASHA_WA_BRAIN": "agent"}):
            self.assertTrue(WA.on(ACCOUNT))
        with mock.patch.dict(os.environ, {"SASHA_WA_BRAIN": f"agent_for:11111111-1111-4111-8111-111111111111,{ACCOUNT.upper()}"}):
            self.assertTrue(WA.on(ACCOUNT))
            self.assertFalse(WA.on("33333333-3333-4333-8333-333333333333"))


class EveryKindIsDrawn(unittest.TestCase):
    def test_every_render_kind_has_a_whatsapp_drawing(self):
        from app.agent import sasha as AG
        kinds = set(AG.RENDER.values()) | AG.KINDS | AG.KINDS_S2_ONLY
        self.assertEqual(sorted(k for k in kinds if k not in WA.KIND_MAP), [], "a render kind with no WhatsApp drawing")


class Drawing(unittest.TestCase):
    def draw(self, ev):
        out, st = GW.Out(), {}
        WA.render({"type": "render", **ev}, out, st, NOW)
        return out.items, st

    def test_venues_are_a_list_picker_with_their_place_ids(self):
        items, _ = self.draw({"kind": "venues", "preset": {"cards": [
            {"name": "Botavara Chamberí", "rating": 4.6, "area": "Chamberí", "place_id": "p0"},
            {"name": "Casa Lucio", "rating": 4.4, "area": "La Latina", "place_id": "p2"}]}})
        lst = [i for i in items if i[0] == "list"][0]
        self.assertIn("1. Botavara Chamberí · ★4.6 · Chamberí", lst[1])
        self.assertEqual([r[2] for r in lst[3]], ["pick:p0", "pick:p2"])
        self.assertTrue(all(len(r[0]) <= 24 and len(r[1]) <= 72 for r in lst[3]))

    def test_a_read_back_asks_yes_or_no(self):
        items, _ = self.draw({"kind": "read_back", "read_back": ["⚠ TEST", "Book Casa Lucio, Sat 21:00, for 2."]})
        self.assertEqual(items, [("ask", "Book Casa Lucio, Sat 21:00, for 2.", [("Yes", "yn:yes"), ("No", "yn:no")])])

    def test_flights_say_what_s1s_choose_says(self):
        items, _ = self.draw({"kind": "flights", "card": {"title": "Flights · MAD → LIS", "options": [
            {"name": "easyJet", "detail": "dep 09:55", "price": "€48.36 total for 1 · TEST", "pick": "the easyJet flight out at 09:55"}]}})
        self.assertEqual(items[0][3][0][2], "say:the easyJet flight out at 09:55")

    def test_pay_and_tap_to_finish_are_links(self):
        self.assertEqual(self.draw({"kind": "pay_here", "url": "https://pay.test/x"})[0], [("text", "Pay here (Apple Pay opens on the page): https://pay.test/x")])
        self.assertEqual(self.draw({"kind": "handover", "url": "https://h.test/v"})[0], [("text", "Tap to finish: https://h.test/v")])

    def test_cards_are_text_and_their_s2_page(self):
        items, _ = self.draw({"kind": "plans", "items": [{"when": "2026-10-17T21:00", "title": "Casa Lucio", "status": "booked"}]})
        self.assertIn("2026-10-17 21:00 · Casa Lucio · booked", items[0][1])
        self.assertIn("See the card: ", items[0][1])

    def test_the_photo_picker_asks_for_the_photo_here(self):
        items, st = self.draw({"kind": "keep_capture", "what": "passport"})
        self.assertIn("passport's photo page here", items[0][1])
        self.assertEqual(st["photo_for"]["kind"], "passport")


class Taps(unittest.TestCase):
    def test_taps_are_the_turns_s2_sends(self):
        with mock.patch("app.agent.sasha.pick_hint", lambda a, pid, m: f"{m} [place_id {pid}]"):
            self.assertEqual(WA.message_of(ACCOUNT, "", "pick:p0", "Botavara Chamberí"), "Botavara Chamberí [place_id p0]")
        self.assertEqual(WA.message_of(ACCOUNT, "", "say:the easyJet flight out at 09:55"), "the easyJet flight out at 09:55")
        self.assertEqual(WA.message_of(ACCOUNT, "", "yn:yes"), "Yes")
        self.assertTrue(WA.ours("yn:no") and not WA.ours("call:abc:yes"))

    def test_long_words_split_at_sentence_ends(self):
        parts = WA.split("One. " * 400, 100)
        self.assertTrue(all(len(p) <= 100 and p.endswith(".") for p in parts))


class Routing(Base):
    def setUp(self):
        super().setUp()
        self.seen = []

        async def fake(ch, body, payload, st, out, now, button_text=""):
            self.seen.append((body, payload))
            out.text(f"agent: {body or payload}")
            return "x"
        self.p = mock.patch.object(WA, "agent_turn", fake)
        self.p.start()

    def tearDown(self):
        self.p.stop()
        super().tearDown()

    def test_flag_on_sends_a_new_message_to_the_agent(self):
        self.link()
        with mock.patch.dict(os.environ, {"SASHA_WA_BRAIN": f"agent_for:{ACCOUNT}"}):
            self.say("book me a table for 2 tomorrow at 9")
            self.say("", payload="yn:yes", text="Yes")
        self.assertEqual(self.seen, [("book me a table for 2 tomorrow at 9", ""), ("", "yn:yes")])
        self.assertIn("agent: book me a table for 2 tomorrow at 9", self.bodies())

    def test_flag_off_is_todays_path(self):
        self.link()
        with mock.patch.dict(os.environ, {"SASHA_WA_BRAIN": "old"}):
            self.say("help")
        self.assertEqual(self.seen, [])

    def test_an_old_flows_button_finishes_there(self):
        self.link()
        with mock.patch.dict(os.environ, {"SASHA_WA_BRAIN": "agent"}):
            self.say("", payload="call:abc:yes", text="Yes")
        self.assertEqual(self.seen, [])

    def test_stop_still_wins(self):
        self.link()
        with mock.patch.dict(os.environ, {"SASHA_WA_BRAIN": "agent"}):
            self.say("STOP")
        self.assertEqual(self.seen, [])

    def test_a_password_never_reaches_the_agent(self):
        self.link()
        with mock.patch.dict(os.environ, {"SASHA_WA_BRAIN": "agent"}):
            self.say("my card is 4242 4242 4242 4242")
        self.assertEqual(self.seen, [])


class TheAgentTurn(unittest.TestCase):
    """wa_agent.agent_turn with a stand-in agent: surface "wa", session "wa:<key>", history kept, memory awaited."""

    def test_surface_session_history_memory(self):
        calls, kept = [], []

        async def quiver(account, message, history, session, surface="s1"):
            calls.append((message, session, surface, list(history)))
            yield {"type": "text", "delta": "Two places near you."}
            yield {"type": "render", "kind": "read_back", "read_back": ["Book Casa Lucio, Sat 21:00, for 2."]}
            yield {"type": "done", "text": "Two places near you."}

        async def remember(account, session, message, reply, seen):
            kept.append((session, message, reply))

        async def no_budget(account):
            return None
        ch = {"account_id": ACCOUNT, "wa_id_sha256": "k" * 64}
        st = {"history": [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "Hello!"}]}
        out = GW.Out()
        with mock.patch("app.agent.sasha.turn_with_quiver", quiver), mock.patch("app.agent.sasha.over_budget", no_budget), \
                mock.patch("agapi.s2_memory.remember", remember):
            run(WA.agent_turn(ch, "a table for 2 tomorrow at 9", "", st, out, NOW))
        self.assertEqual(calls[0][1:3], ("wa:" + "k" * 64, "wa"))
        self.assertEqual(calls[0][3][-1]["content"], "Hello!")
        self.assertEqual(out.items[0], ("text", "Two places near you."))
        self.assertEqual(out.items[1][0], "ask")
        self.assertEqual(st["history"][-1], {"role": "assistant", "content": "Two places near you."})
        self.assertEqual(kept, [("wa:" + "k" * 64, "a table for 2 tomorrow at 9", "Two places near you.")])


class SurfaceWa(unittest.TestCase):
    def test_wa_is_s2_for_tools_with_its_own_note(self):
        from app.agent import s2 as S2
        src = open(__import__("app.agent.sasha", fromlist=["x"]).__file__).read()
        self.assertIn('wa = surface == "wa"', src)
        self.assertIn("S2.s2_system() + (S2.WA_NOTE if wa else \"\")", src)
        self.assertIn("never \"on your screen\"", S2.WA_NOTE)


if __name__ == "__main__":
    unittest.main()
