"""Sasha 349 · the conversation has ONE owner, and her words travel WITH her cards (docs/sasha/S-349-one-conversation.md).
    cd backend && python -m unittest tests.test_s349_one_conversation -v
"""
from __future__ import annotations

import asyncio
import pathlib
import re
import unittest
from unittest import mock

from agapi import s2_memory as MEM

run = asyncio.run
ROOT = pathlib.Path(__file__).resolve().parents[2]
FE = ROOT / "frontend"
ACCT = "00000000-0000-4000-8000-000000000349"


class Mem:
    """the record with no table: this process's memory (s2_memory's own fallback)"""

    def __enter__(self):
        self.p = [mock.patch.object(MEM, "RUN", None), mock.patch.dict(MEM._MEM, {}, clear=True)]
        for x in self.p:
            x.start()
        return self

    def __exit__(self, *a):
        for x in reversed(self.p):
            x.stop()


class OneRecord(unittest.TestCase):
    def test_every_message_in_and_out_with_its_cards_and_its_tool(self):
        ev = {"type": "render", "kind": "flights", "card": {"title": "Flights · Madrid → London", "options": [{"name": "Iberia"}]}}
        m = MEM.fold(None, "one-way flight Madrid to London 20 Nov", "Here are the flights.", {"payload": [ev]})
        msgs = MEM.messages_of(m)
        self.assertEqual([(x["dir"], x["ch"], x.get("tool")) for x in msgs], [("in", "s2", None), ("out", "s2", "sasha")])
        self.assertEqual(msgs[1]["cards"], [ev])                                    # ONE payload: the reply's text WITH its cards
        self.assertNotIn("recent", m)                                              # no second copy: recent is read from the record
        self.assertEqual(MEM.recent_of(m)[-1], {"role": "assistant", "content": "Here are the flights.", "cards": True})

    def test_the_conversation_comes_back_without_a_welcome_back_line(self):
        """Found live (6 Nov): switching tabs and back, the chat was gone — recall returned it only with a "carry on" line."""
        with Mem():
            run(MEM.remember(ACCT, "s1", "hello", "Hi — what shall I book for you?", {}))
            got = run(MEM.recall(ACCT, "s2-new", surface="s2"))
        self.assertEqual([x["text"] for x in got["messages"]], ["hello", "Hi — what shall I book for you?"])
        self.assertTrue(got["recent"])

    def test_whatsapp_turns_are_recorded_once_at_the_door(self):
        with Mem():
            run(MEM.record(ACCT, MEM.message("in", "wa", "carry on")))
            run(MEM.remember(ACCT, "wa:k", "carry on", "Here's your trip.", {}))   # the brain's fold: no second copy
            run(MEM.record(ACCT, MEM.message("out", "wa", "Here's your trip.", "sasha")))
            msgs = MEM.messages_of(MEM._MEM[ACCT])
        self.assertEqual([(x["dir"], x["ch"]) for x in msgs], [("in", "wa"), ("out", "wa")])

    def test_capped_and_masked(self):
        m = {}
        for i in range(MEM.MESSAGES_MAX + 10):
            MEM.appended(m, MEM.message("in", "s2", f"line {i}"))
        self.assertEqual(len(MEM.messages_of(m)), MEM.MESSAGES_MAX)
        self.assertEqual(MEM.message("in", "s2", "my card is 4242 4242 4242 4242")["text"], MEM.REMOVED)


class AReplyAnswersTheToolThatSpokeLast(unittest.TestCase):
    """Found live (6 Nov 07:06): "Picking up: Flight Madrid → London…" (Travel) arrived while the space was Due diligence; "Carry on" went to AD."""

    def run_follow(self, last, pending, body="Carry on", payload=""):
        from booking_signer import guest_whatsapp as GW
        from products import space as SPC, whatsapp as PW
        st = {"pending": pending}
        with Mem(), mock.patch.object(PW, "_set_aside", mock.AsyncMock(side_effect=lambda st, ch: st.update(pending=None))), \
                mock.patch.object(PW, "_resume", mock.AsyncMock(return_value=None)), mock.patch.dict(SPC._SPACE, {}, clear=True):
            if last:
                run(MEM.record(ACCT, MEM.message("out", "wa", "a line", last)))
            run(GW._follow_last_tool({"account_id": ACCT, "wa_id_sha256": "k"}, st, ACCT, body, payload))
            return st, run(SPC.current_space(ACCT))

    def test_travel_spoke_last_so_carry_on_is_travels(self):
        st, space = self.run_follow("sasha", {"kind": "product", "product": "diligence", "step": "ask"})
        self.assertIsNone(st["pending"])                                            # AD's space stepped aside (kept), Travel answers
        self.assertEqual(space, "sasha")

    def test_ad_speaking_last_never_picks_ad(self):   # Sasha 361 · AD is the ONE router's (their keyword / tap), never "who spoke last"
        st, space = self.run_follow("diligence", None, body="what did you find?")
        self.assertEqual((st.get("pending"), space), (None, "sasha"))

    def test_a_tool_picked_by_the_message_itself_wins(self):
        st, _ = self.run_follow("sasha", {"kind": "product", "product": "diligence", "step": "ask"}, payload="kanoe:diligence")
        self.assertEqual(st["pending"]["product"], "diligence")                    # a tap chose: never moved by the record
        st, _ = self.run_follow("diligence", None, body="sasha")
        self.assertIsNone(st["pending"])                                            # her word: travel

    def test_every_message_out_names_its_tool(self):
        from booking_signer import guest_whatsapp as GW
        out = GW.Out().text("Picking up: Flight Madrid → London")
        self.assertEqual(GW._tool_of(out), "sasha")
        out.space = lambda: "diligence"
        self.assertEqual(GW._tool_of(out), "diligence")
        src = (ROOT / "backend/booking_signer/guest_whatsapp.py").read_text()
        self.assertIn("    await _record_out(ch, out.said(), _tool_of(out))\n    return results", src)   # deliver: every send recorded
        d = (ROOT / "backend/booking_signer/inbound_phone.py").read_text()   # Sasha 379b · where AgAPI's one call returns AD's answer
        self.assertIn('MEM.message("out", "wa", "[Applied Diligence answered on Kanoe\'s number]", "diligence")', d)   # AgAPI's reply


class OnePayload(unittest.TestCase):
    def test_what_s2_draws_is_one_list_on_both_sides(self):
        from app.agent import sasha as AG
        s2 = (FE / "app/s2/S2App.tsx").read_text()
        block = s2[s2.index("export const S2_KINDS = ["):s2.index("] as const", s2.index("export const S2_KINDS = ["))]
        self.assertEqual(set(re.findall(r"'([a-z_]+)'", block)), set(AG.S2_DRAWS))
        for k in AG.S2_DRAWS:
            self.assertIn(f"k === '{k}'", s2, k)                                    # each drawn by cardsOf, the one mapping
        for kind in set(AG.RENDER.values()) - {"inline"}:
            self.assertIn(kind, AG.S2_DRAWS, f"/s2 can't draw '{kind}' — her words would name a card that isn't there")

    def test_a_card_a_surface_cant_draw_is_never_shown_and_she_is_told(self):
        from app.agent import sasha as AG
        self.assertTrue(AG.draws("s2", "flights") and not AG.draws("s2", "focus") and AG.draws("next", "focus"))
        src = (ROOT / "backend/app/agent/sasha.py").read_text()
        self.assertIn('mr["on_screen"] = "nothing from this result was shown on their screen', src)
        self.assertNotIn("_V.promises_card", src)                                  # 345's phrase guard retired

    def test_the_page_draws_live_and_returning_messages_alike(self):
        s2 = (FE / "app/s2/S2App.tsx").read_text()
        self.assertIn("for (const c of cardsOf(ev)) add(c)", s2)                    # a live turn
        self.assertIn("const cards = untagDeep(evs.flatMap(cardsOf)) as Card[]", s2)   # the record's messages on return
        self.assertIn("const shown = fromRecord(rows).slice(-40)", s2)
        self.assertNotIn("if (!line) return", s2)                                  # never only with a "welcome back" line


class NoTripUntilChosen(unittest.TestCase):
    def test_the_trip_tab(self):
        tp = (FE / "app/components/workspace/TripPanel.tsx").read_text()
        self.assertIn("{!phone && <button type=\"button\" className=\"lw-handoff\"", tp)   # never "Continue on my phone" ON the phone
        self.assertIn("<span className=\"amt\">{tt ? eur(tt.total_eur) : '—'}</span>", tp)   # the record's figure, in €
        self.assertNotIn("`$${(richItinerary.estimated_total_usd", tp)
        self.assertIn("usePhone()", (FE / "app/next/page.tsx").read_text())          # ONE phone rule (lib/device)

    def test_a_search_makes_no_trip(self):
        v0 = (ROOT / "backend/agapi/v0.py").read_text()
        self.assertIn("await _keep_offers(ctx, {", v0)
        self.assertIn("party = int(a.get(\"passengers\") or 1)", v0)                 # never a silent 2 travellers


class SilentMode(unittest.TestCase):
    def test_on_the_person_text_only(self):
        from app.agent import voice as V
        put = mock.AsyncMock(return_value=True)
        with Mem(), mock.patch.dict(V._SILENT, {}, clear=True), mock.patch.object(MEM, "put_kind", put), \
                mock.patch.object(MEM, "kind", mock.AsyncMock(return_value=True)):
            run(V.set_silent(ACCT, True))
            put.assert_awaited_with(ACCT, "silent", True)                            # kept on the person's record
            V._SILENT.clear()
            self.assertTrue(run(V.silent(ACCT)))                                    # read back from it (another process, a restart)
        src = (ROOT / "backend/app/agent/sasha.py").read_text()
        self.assertIn("if quiet and ev.get(\"type\") == \"say\":", src)               # /s2: no spoken line leaves a silent turn
        self.assertIn("not await _VO.silent(account)", (ROOT / "backend/booking_signer/wa_agent.py").read_text())   # no voice notes
        s2 = (FE / "app/s2/S2App.tsx").read_text()
        self.assertIn("data-silent-mode aria-label=\"Silent mode\"", s2)              # ONE switch, labelled
        self.assertNotIn("s2_muted", s2)                                            # never this browser's copy


if __name__ == "__main__":
    unittest.main()


# ── the WhatsApp proof, end to end: the real turn (guest_whatsapp.turn), AgAPI's op and Twilio stood in ──────────────────────
from booking_signer import guest_whatsapp as GW   # noqa: E402
# Sasha 379b · CarryOnIsAnsweredByTheToolThatSpoke retired: whether a message is AD's is AgAPI's ONE decision (CR 192) — tests.test_s379b_one_decision


class FoundByTheLiveProof(unittest.TestCase):
    """The S2 flow proof (6 Nov) showed "€59 all in" beside "€58.55", "— pending_payment" in the Trip tab, and "Days 0" for a flight."""

    def test_every_basket_state_has_its_words(self):
        from booking_signer import basket as BK
        tf = (FE / "lib/trip-flights.mjs").read_text()
        words = tf[tf.index("export const WORDS = {"):tf.index("}", tf.index("export const WORDS = {"))]
        for state in set(BK.LIVE) | {"failed", "cancelled"}:
            self.assertIn(f"{state}:", words, state)

    def test_one_way_to_say_money(self):
        self.assertIn("export const eur = ", (FE / "lib/money.ts").read_text())
        for rel in ("app/s2/S2App.tsx", "app/components/cards/S2Cards.tsx", "app/components/PayHere.tsx", "app/components/workspace/TripPanel.tsx"):
            src = (FE / rel).read_text()
            self.assertIn("from '@/lib/money'", src, rel)
            self.assertNotRegex(src, r"€\$\{Math\.round|maximumFractionDigits: 0", rel)

    def test_a_flight_on_its_own_has_no_days(self):
        self.assertIn("{dayCount > 0 && <div className=\"lw-sumcell\"><span className=\"k\">Days</span>",
                      (FE / "app/components/workspace/TripPanel.tsx").read_text())
