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
from tests.test_guest_whatsapp_s75 import ACCOUNT, GUEST, SANDBOX, Base, run

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
        self.assertEqual(WA.agent_state(st)["photo_for"]["kind"], "passport")   # 238 · in the state the store keeps


class Taps(unittest.TestCase):
    def test_taps_are_the_turns_s2_sends(self):
        with mock.patch("app.agent.sasha.pick_hint", lambda a, pid, m: f"{m} [place_id {pid}]"):
            self.assertEqual(WA.message_of(ACCOUNT, "", "pick:p0", "Botavara Chamberí"), "Botavara Chamberí [place_id p0]")
        self.assertEqual(WA.message_of(ACCOUNT, "", "say:the easyJet flight out at 09:55"), "the easyJet flight out at 09:55")
        self.assertEqual(WA.message_of(ACCOUNT, "", "yn:yes"), "Yes")
        self.assertTrue(WA.ours("yn:no") and not WA.ours("call:abc:yes"))
        # Sasha 249 · an old flow's button reaches her as what it is — never a bare "Yes" (her read-back's yes), never empty
        for body in ("", "Yes"):
            m = WA.message_of(ACCOUNT, body, "call:abc:yes", "Yes")
            self.assertTrue(m.startswith("[they tapped an old “Yes” button") and m != "Yes", m)

    def test_a_card_tap_is_never_taken_for_a_password(self):   # Sasha 249 · found live: the place_id tripped the guard
        from agapi import s2_keep as KEEP
        with mock.patch("app.agent.sasha.pick_hint", lambda a, pid, m: f"{m} [place_id {pid}]"):
            msg = WA.message_of(ACCOUNT, "Taberna Ancla", "pick:ChIJtest056d5064023de4a87989", "Taberna Ancla")
        self.assertTrue(KEEP.chat_guard(msg))      # the composed message WOULD trip it …
        self.assertFalse(KEEP.chat_guard("Taberna Ancla"))   # … so the guard reads their words, which don't

    def test_long_words_split_at_sentence_ends(self):
        parts = WA.split("One. " * 400, 100)
        self.assertTrue(all(len(p) <= 100 and p.endswith(".") for p in parts))


class Routing(Base):
    def setUp(self):
        super().setUp()
        self.seen = []

        async def fake(ch, body, payload, st, out, now, button_text="", voice_in=False):
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

    def test_a_button_nothing_is_waiting_on_goes_to_the_agent(self):   # Sasha 249 · step 1: every button, not only ours
        self.link()
        with mock.patch.dict(os.environ, {"SASHA_WA_BRAIN": "agent"}):
            self.say("", payload="call:abc:yes", text="Yes")
        self.assertEqual(self.seen, [("", "call:abc:yes")])

    def test_the_button_the_old_flow_is_waiting_on_finishes_there(self):   # Sasha 249 · one question, one owner
        self.link()
        st = run(GW.STORE.get_state(GW.wa_key(GUEST))) or {}
        st["pending"] = {"kind": "demo_reset", "nonce": "n1", "asked_at": NOW}
        run(GW.STORE.put_state(GW.wa_key(GUEST), st))
        with mock.patch.dict(os.environ, {"SASHA_WA_BRAIN": "agent"}):
            try:
                self.say("", payload="no:n1", text="No")
            except Exception:
                pass
        self.assertEqual(self.seen, [])

    def test_an_empty_message_and_a_file_reach_the_agent_never_help(self):   # Sasha 249 · W1
        self.link()
        ch = run(GW.STORE.channel_for(GW.wa_key(GUEST)))
        with mock.patch.dict(os.environ, {"SASHA_WA_BRAIN": "agent"}):
            self.say("")
            run(GW.turn(ch, SANDBOX, {"From": f"whatsapp:{GUEST}", "To": f"whatsapp:{SANDBOX}", "Body": "", "NumMedia": "1",
                                      "MediaContentType0": "application/pdf", "MediaUrl0": "https://x.test/a.pdf"}))
        self.assertEqual([b for b, _ in self.seen], ["[an empty message]", "[they sent a file (application/pdf) with no words]"])

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


# ── Sasha 238 · photos, memory + closing, voice ───────────────────────────────────────────────────────────────────────────────

class Photos(unittest.TestCase):
    CH = {"account_id": ACCOUNT, "wa_id_sha256": "k" * 64}

    def setUp(self):
        import asyncio
        asyncio.set_event_loop(asyncio.new_event_loop())   # the shared run() needs a current loop (another test may have closed it)

        async def fetch(p):
            return b"\xff\xd8 fixture jpeg"
        self.p = [mock.patch.object(WA, "FETCH", fetch)]
        for x in self.p:
            x.start()
        WA._HELD_PHOTOS.clear()

    def tearDown(self):
        for x in self.p:
            x.stop()

    def test_purpose_order_asked_then_caption_then_a_question(self):
        self.assertEqual(WA.purpose_of("my passport"), "passport")
        self.assertEqual(WA.purpose_of("iberia plus card"), "loyalty")
        self.assertEqual(WA.purpose_of("bank statement"), "statement")
        self.assertEqual(WA.purpose_of("the damage on the door"), "damage")
        st, out = {}, GW.Out()
        run(WA.photo_intake(self.CH, {"NumMedia": "1", "MediaContentType0": "image/jpeg", "MessageSid": "SM1"}, st, out, NOW))
        self.assertEqual(out.items[0][0], "ask")
        self.assertEqual([b for b, _ in out.items[0][2]], ["Passport", "Loyalty card", "Something else"])
        self.assertIn("SM1", WA._HELD_PHOTOS)

    def test_a_passport_photo_is_read_masked_then_saved_on_yes(self):
        from agapi import keep_scan as SCAN
        scans, saved = [], []

        async def scan(account, kind, image, mime):
            scans.append(kind)
            return {"token": "t1", "kind": kind, "masked": "Passport ES ••••456", "shown": ["Passport ES ••••456", "Expires 2031-05"]}

        async def confirm(account, token):
            saved.append(token)
            return {"item": "Passport ES ••••456", "created": True, "type": "passport"}
        st = {}
        WA.set_agent_state(st, photo_for={"kind": "passport", "at": NOW.isoformat()})   # she asked for it (keep_capture)
        out = GW.Out()
        with mock.patch.object(SCAN, "scan", scan), mock.patch.object(SCAN, "confirm", confirm):
            run(WA.photo_intake(self.CH, {"NumMedia": "1", "MediaContentType0": "image/jpeg", "Body": ""}, st, out, NOW))
            self.assertEqual(scans, ["passport"])
            self.assertIn("Passport ES ••••456", out.items[0][1])
            self.assertEqual([i for _, i in out.items[0][2]], ["keep:yes", "keep:no"])
            out2 = GW.Out()
            run(WA.agent_turn(self.CH, "", "keep:yes", st, out2, NOW))
        self.assertEqual(saved, ["t1"])
        self.assertIn("Saved to your Keep: Passport ES ••••456", out2.items[0][1])
        self.assertNotIn("photo", WA.agent_state(st))

    def test_a_statement_photo_goes_to_subscriptions_then_the_agent(self):
        from agapi import s2_subscriptions as SUBS
        seen = []

        async def agent(ch, body, payload, st, out, now, button_text="", voice_in=False):
            seen.append(body)
            return "x"
        with mock.patch.object(SUBS, "keep_statement", lambda a, raw, mime: "st_ref1"), mock.patch.object(WA, "agent_turn", agent):
            run(WA.photo_intake(self.CH, {"NumMedia": "1", "MediaContentType0": "image/jpeg", "Body": "my bank statement"}, {}, GW.Out(), NOW))
        self.assertIn("statement_ref st_ref1", seen[0])

    def test_damage_goes_to_the_accident_case(self):
        from agapi import s2_fine_print as FP
        sent, seen = [], []
        st = {}
        WA.render({"type": "render", "kind": "accident", "view": {"step": "photos", "say": "Next: your car from the front.",
                   "shots": [{"shot": "front", "say": "Your car from the front"}, {"shot": "damage_close", "say": "The damage"}]}},
                  GW.Out(), st, NOW)
        self.assertEqual(WA.agent_state(st)["shots"], ["front", "damage_close"])

        async def photo(account, shot, mime, b64):
            sent.append(shot)
            return {"ok": True}

        async def agent(ch, body, payload, st, out, now, button_text="", voice_in=False):
            seen.append(body)
            return "x"
        with mock.patch.object(FP, "accident_photo", photo), mock.patch.object(WA, "agent_turn", agent):
            run(WA.photo_intake(self.CH, {"NumMedia": "1", "MediaContentType0": "image/jpeg", "Body": "the damage"}, st, GW.Out(), NOW))
        self.assertEqual(sent, ["front"])                                        # the case's own next shot
        self.assertIn("saved to the case as evidence; still to send: damage_close", seen[0])
        self.assertEqual(WA.agent_state(st)["shots"], ["damage_close"])

    def test_before_the_photos_step_it_says_so(self):
        out = GW.Out()
        run(WA.photo_intake(self.CH, {"NumMedia": "1", "MediaContentType0": "image/jpeg", "Body": "the damage"}, {}, out, NOW))
        self.assertIn("at the photo step", out.items[0][1])

    def test_a_card_twice_in_a_turn_is_drawn_once(self):
        rs = [{"kind": "accident", "view": {"say": "old"}}, {"kind": "read_back", "read_back": ["x"]}, {"kind": "accident", "view": {"say": "new"}}]
        self.assertEqual([r.get("view", {}).get("say") for r in WA.last_of_each_card(rs)], [None, "new"])

    def test_the_agents_state_survives_the_stores_columns(self):
        st = {"history": [], "pending": None}
        WA.set_agent_state(st, photo_for={"kind": "loyalty", "at": NOW.isoformat()})
        store = GW.MemoryGuestStore()
        run(store.put_state("k", st))
        self.assertEqual(WA.agent_state(run(store.get_state("k")))["photo_for"]["kind"], "loyalty")


class MemoryClosingVoice(unittest.TestCase):
    CH = {"account_id": ACCOUNT, "wa_id_sha256": "k" * 64}

    def setUp(self):
        import asyncio
        asyncio.set_event_loop(asyncio.new_event_loop())

    def run_turn(self, body, st, recall=None, voice_in=False, reply="Here you go."):
        calls, notes = [], []

        async def quiver(account, message, history, session, surface="s1"):
            calls.append(list(history))
            yield {"type": "done", "text": reply}

        async def nothing(*a, **k):
            return None

        async def rec(account, session):
            return recall or {"line": None, "recent": []}

        async def tts(text):
            notes.append(text)
            return b"mp3"
        out = GW.Out()
        with mock.patch("app.agent.sasha.turn_with_quiver", quiver), mock.patch("app.agent.sasha.over_budget", nothing), \
                mock.patch("agapi.s2_memory.remember", nothing), mock.patch("agapi.s2_memory.closing", nothing), \
                mock.patch("agapi.s2_memory.recall", rec), mock.patch.object(WA, "TTS", tts):
            run(WA.agent_turn(self.CH, body, "", st, out, NOW, voice_in=voice_in))
        return out, calls, notes

    def test_away_she_opens_with_what_she_remembers_from_s2(self):
        # Sasha 246 · a request on return is simply answered — the topic is never recited; /s2's conversation still carried
        out, calls, _ = self.run_turn("hi again", {}, recall={"line": "Hey Alex, what can I help you with?",
                                                           "recent": [{"role": "user", "content": "a table near Gran Vía"}]})
        self.assertNotIn("Gran Vía", " ".join(str(i[1]) for i in out.items if i[0] == "text"))
        self.assertEqual(calls[0][0]["content"], "a table near Gran Vía")        # /s2's conversation carried into WhatsApp
        out, calls, _ = self.run_turn("Hi Sasha!", {}, recall={"line": "Hey Alex, what can I help you with?",
                                                             "recent": [{"role": "user", "content": "a table near Gran Vía"}]})
        self.assertEqual([i for i in out.items if i[0] == "text"], [("text", "Hey Alex, what can I help you with?")])   # a greeting: only that
        self.assertEqual(calls, [])

    def test_thanks_closes_and_rests_until_the_next_message(self):
        st = {"history": [{"role": "user", "content": "book it"}, {"role": "assistant", "content": "Booked."}]}
        WA.set_agent_state(st, last_seen=NOW.isoformat())
        out, calls, _ = self.run_turn("thanks!", st)
        self.assertEqual(calls, [])                                              # no model call: a short close
        self.assertTrue(WA.agent_state(st).get("dormant"))
        out, calls, _ = self.run_turn("one more thing", st)
        self.assertFalse(WA.agent_state(st).get("dormant"))                      # woken by their message

    def test_voice_in_gets_voice_out_text_in_text_out(self):
        out, _, notes = self.run_turn("hello", {"history": [{"role": "user", "content": "x"}]}, voice_in=True)
        self.assertEqual(notes, ["Here you go."])
        self.assertTrue(any(i[0] == "media" and "/api/agent/voice/note/" in i[2] for i in out.items))
        out, _, notes = self.run_turn("hello", {"history": [{"role": "user", "content": "x"}]}, voice_in=False)
        self.assertEqual(notes, [])
        token = [i for i in self.run_turn("hey", {"history": [{"role": "user", "content": "x"}]}, voice_in=True)[0].items
                 if i[0] == "media"][0][2].rsplit("/", 1)[1][:-4]
        self.assertEqual(WA.note_audio(token), b"mp3")
