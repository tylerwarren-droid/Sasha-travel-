"""Sasha 316 · a platform hand-over is ONE short honest message, and its link is the platform's own page (Tyler: "duplicative… one
message and more concise… nothing is filled in").
Live 07:25 (La Mi Venta via CoverManager, Sat 14 Nov 14:00 for 2) — TWO messages: (1) a "ready to copy" card + AgAPI's /prepared/ page +
"book on CoverManager — you press Book there" + "Done? Back to Sasha: …/s2"; (2) the model's "Your details are filled in for… Their page is
on your phone, so press Book there." The /prepared/ page led to CoverManager with NOTHING filled in: message 2 was false.

ROOT TEST (written before the code)
(1) ONE truth: AgAPI's platform hand-over decision — venue.prepare_booking's decision (route "platform") and its hand_over (CR 107's
    platform-link table: the link, what it carries, the platform). Sasha says only that: voice.handover_message.
(2) ONE message: the hand-over itself, never a second one restating it (on WhatsApp the model's reply after it is not sent), no way back
    line, and "filled in" never — a platform is never given his details; the link opens on the slot only when the table says it carries
    the date, the time and the party.
(3) The whole class: every platform (CoverManager, TheFork, OpenTable, Zenchef…) goes the same way, and his "booked" after it is
    answered in ONE line on the hand-over's own record.
Offline: AgAPI, the model and WhatsApp stood in; nothing leaves the process.

    cd backend && python -m unittest tests.test_s316 -v
"""
from __future__ import annotations

import asyncio
import inspect
import unittest
from datetime import datetime, timezone
from unittest import mock

from agapi import venue_truth as VT, venues as VN
from app.agent import voice as V
from tests import test_s284 as T

run = asyncio.run
CM = "https://www.covermanager.com/reserve/module_restaurant/restaurante-la-mi-venta/spanish"
PREP = "https://agapi.example/prepared/tok316"
FIELDS_RES = {"who": {"name": "Tyler Warren", "contact": {"mobile_e164": "+34608445715"}}, "how_many": {"count": 2},
              "when": {"at": "2026-11-14T14:00"}, "what": {"category": "restaurant"}}
ONE = ("La Mi Venta books on CoverManager — open it, pick Sat 14 Nov 14:00 for 2, and press Book. "
       "Your details to paste: Tyler Warren · tyler@kanoe.ai · +34608445715\n" + CM)


def platform_dec(name="CoverManager", link=PREP):
    return {"route": "platform", "channel": f"{name} booking", "how_far": "hand_over",
            "say_text": f"La Mi Venta books on {name} — your details are on the card to copy. You press Book there; I never book on a platform.",
            "button": {"label": f"Book on {name}", "link": link, "sends": False}}


class Base(unittest.TestCase):
    """test_s284's hand-over harness (the real follow → the prepared rung), with AgAPI's prepare answering as v1.49 does: its own
    /prepared/ page as `link`, the decision's button on it, and the platform's own page in `hand_over`."""
    PLATFORM, PAGE, CARRIED = "CoverManager", CM, []
    RD = {"venue": "La Mi Venta", "rungs": {}, "place_id": "ChIJ316", "read_id": "r316"}

    def setUp(self):
        T.TheHoldFollows.setUp(self)
        self.addCleanup(T.TheHoldFollows.tearDown, self)   # cleanups run last-in first-out: these patches stop first
        test = self

        async def call(op, body):
            test.calls.append(op)
            return {"ok": True, "result": {"link": PREP, "submitted": False, "human_step": f"book on {test.PLATFORM} — you press Book there",
                                           "say": "Ready for you to confirm: La Mi Venta, Sat 14 Nov 14:00, 2 people. Nothing has been sent yet.",
                                           "decision": platform_dec(test.PLATFORM, PREP),
                                           "hand_over": {"link": test.PAGE, "carried": test.CARRIED, "platform": test.PLATFORM,
                                                         "evidence": "none", "copy": []}}}
        p = mock.patch.object(VT, "CALL", call)
        p.start()
        self.addCleanup(p.stop)
        from booking_signer import guest_receipt as GR
        p2 = mock.patch.object(GR, "address_of", mock.AsyncMock(return_value="tyler@kanoe.ai"))
        p2.start()
        self.addCleanup(p2.stop)

    def hand_over(self):
        self.dec = platform_dec(self.PLATFORM, self.PAGE)   # venue.profile's decision: its button is the platform's own page
        return run(VN.follow(T.Ctx(), {"name": "La Mi Venta"}, self.RD, FIELDS_RES, "2026-11-14T14:00", datetime.now(timezone.utc),
                             {"website": "https://lamiventa.example", "place_id": "ChIJ316"}, self.dec))


class OneMessage(Base):
    def test_a_tylers_la_mi_venta_is_one_message_word_for_word(self):
        out = self.hand_over()
        self.assertEqual(self.told, [ONE])                                  # ONE message to his phone, exactly the ticket's
        self.assertFalse(out["booked"])

    def test_b_never_filled_never_a_way_back_never_the_prepared_page(self):
        self.hand_over()
        msg = self.told[-1]
        for never in ("filled", "Back to Sasha", "/prepared/", "ready to copy", "/s2"):
            self.assertNotIn(never, msg)

    def test_c_the_link_is_the_platforms_own_page(self):
        out = self.hand_over()
        self.assertEqual(out["prepared"]["url"], CM)                       # the card on /s2 opens the same page
        self.assertEqual(self.mem.kinds[VN.PREPARED_KIND][-1]["url"], CM)  # and the record the way back reads

    def test_d_what_she_says_in_the_app_is_the_same_line(self):
        out = self.hand_over()
        self.assertEqual(out["say"], ONE.split("\n")[0])
        self.assertEqual(out["page_says"], ONE.split("\n")[0])
        self.assertNotIn("filled", out["say"])


class TheLinkCarriesOnlyWhatTheTableSays(Base):
    PLATFORM, PAGE, CARRIED = "Zenchef", "https://bookings.zenchef.com/results?rid=316&day=2026-11-14&slot=14:00&pax=2", ["date", "time", "party"]

    def test_a_a_link_that_carries_the_slot_says_it_opens_on_it(self):
        self.hand_over()
        self.assertIn("open it — it opens on Sat 14 Nov 14:00 for 2 — and press Book", self.told[-1])
        self.assertTrue(self.told[-1].endswith(self.PAGE))


class EveryPlatform(Base):
    def test_a_the_whole_class(self):
        for name, page in (("TheFork", "https://widget.thefork.com/en/x/homepage/y"), ("OpenTable", "https://www.opentable.com/r/la-mi-venta")):
            self.told.clear()
            self.PLATFORM, self.PAGE = name, page
            VN._HELD.pop(T.ACCT, None)
            self.hand_over()
            self.assertEqual(len(self.told), 1, name)
            self.assertTrue(self.told[-1].startswith(f"La Mi Venta books on {name} — open it, pick Sat 14 Nov 14:00 for 2, and press Book."), name)
            self.assertTrue(self.told[-1].endswith(page), name)

    def test_b_no_platform_page_from_agapi_keeps_the_decisions_own(self):   # hand_over missing: venue.profile's button, never /prepared/
        self.PAGE = None
        self.dec = platform_dec(self.PLATFORM, CM)
        run(VN.follow(T.Ctx(), {"name": "La Mi Venta"}, self.RD, FIELDS_RES, "2026-11-14T14:00", datetime.now(timezone.utc),
                      {"website": "https://lamiventa.example", "place_id": "ChIJ316"}, self.dec))
        self.assertTrue(self.told[-1].endswith(CM))

    def test_c_one_writer(self):
        self.assertIn("_platform_handover(", inspect.getsource(VN._book_inner))   # the prepared rung's platform route goes there
        self.assertEqual(inspect.getsource(VN).count("V.handover_message("), 1)   # ONE writer of the message, ONE place it is sent
        self.assertEqual(inspect.getsource(V).count("def handover_message("), 1)


class OnWhatsAppNothingFollowsIt(unittest.TestCase):
    def test_a_the_models_second_message_is_not_sent(self):
        from booking_signer import guest_whatsapp as GW, wa_agent as WA

        async def quiver(account, message, history, session, surface="s1"):
            yield {"type": "text", "delta": "Your details are filled in for La Mi Venta. Their page is on your phone, so press Book there."}
            yield {"type": "done", "text": "Your details are filled in for La Mi Venta. Their page is on your phone, so press Book there.",
                   "tools": [{"tool": "book_venue", "ok": True, "status": "page_on_phone"}]}

        async def nothing(*a, **k):
            return None
        out = GW.Out()
        with mock.patch("app.agent.sasha.turn_with_quiver", quiver), mock.patch("app.agent.sasha.over_budget", nothing), \
                mock.patch("agapi.s2_memory.remember", nothing), mock.patch("agapi.s2_memory.recall", mock.AsyncMock(return_value={})):
            run(WA.agent_turn({"account_id": T.ACCT, "wa_id_sha256": "x" * 64}, "yes", "",
                              {"history": [{"role": "user", "content": "x"}], "pending": None}, out, datetime.now(timezone.utc)))
        self.assertEqual([it for it in out.items if it[0] == "text"], [])

    def test_b_any_other_reply_still_goes(self):
        from booking_signer import guest_whatsapp as GW, wa_agent as WA

        async def quiver(account, message, history, session, surface="s1"):
            yield {"type": "done", "text": "Three places near Sol.", "tools": [{"tool": "search_venues", "ok": True}]}

        async def nothing(*a, **k):
            return None
        out = GW.Out()
        with mock.patch("app.agent.sasha.turn_with_quiver", quiver), mock.patch("app.agent.sasha.over_budget", nothing), \
                mock.patch("agapi.s2_memory.remember", nothing), mock.patch("agapi.s2_memory.recall", mock.AsyncMock(return_value={})):
            run(WA.agent_turn({"account_id": T.ACCT, "wa_id_sha256": "x" * 64}, "sushi", "",
                              {"history": [{"role": "user", "content": "x"}], "pending": None}, out, datetime.now(timezone.utc)))
        self.assertIn("Three places near Sol.", [it[1] for it in out.items if it[0] == "text"])


class BookedIsOneLine(unittest.TestCase):
    def test_a_his_booked_after_the_hand_over_is_answered_once_on_its_record(self):
        from booking_signer import guest_whatsapp as GW
        now = datetime.now(timezone.utc)
        pend = {"kind": "handed", "at": now.isoformat(), "venue": "La Mi Venta", "key": "La Mi Venta|2026-11-14|14:00"}
        st = {"pending": pend, "history": []}
        self.assertTrue(GW.answers_sashas_question(st, "booked", "", now))
        self.assertTrue(GW.answers_sashas_question(st, "Booked!", "", now))
        self.assertFalse(GW.answers_sashas_question(st, "find me a bar nearby", "", now))
        out = GW.Out()
        answer = mock.AsyncMock(return_value={"ok": True, "say": V.BOOKED_BY_YOU})
        with mock.patch.object(VN, "answer_word", answer):
            handled = run(GW._answer_pending({"account": T.ACCT, "st": st, "now": now, "out": out, "ch": {}, "frm": ""}, "booked", ""))
        self.assertTrue(handled)
        answer.assert_awaited_once_with(T.ACCT, pend["key"], True, "chat")
        self.assertEqual([it[1] for it in out.items if it[0] == "text"], [V.BOOKED_BY_YOU])
        self.assertIsNone(st["pending"])

    def test_b_the_hand_over_leaves_that_question_open(self):
        self.assertIn("GW.await_booked(", inspect.getsource(VN._platform_handover))


if __name__ == "__main__":
    unittest.main()
