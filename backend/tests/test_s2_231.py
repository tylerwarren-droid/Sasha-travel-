"""Sasha 231 · (2) the pickup reminder for an ACCOUNT LIST (Tyler + Jon); (3) "thank you" → dormant, any language she speaks;
(4) memory across visits on /s2 — masked, the thing they were looking at, a hold awaiting a yes, a question she asked. Offline.

    cd backend && python -m unittest tests.test_s2_231 -v
"""
from __future__ import annotations

import asyncio
import unittest
from datetime import date, datetime, timedelta, timezone
from unittest import mock

from agapi import s2_closing as CL, s2_memory as MEM
from booking_signer import rental_moments as RM

FOUNDER = "11111111-1111-4111-8111-111111111111"
JON = "4ff7c9c1-4215-46fd-a69f-c181d093db97"
GUEST = "00000000-0000-4000-8000-000000000231"
run = asyncio.run
TOMORROW = (date.today() + timedelta(days=1)).isoformat()


def evening():
    from zoneinfo import ZoneInfo
    return datetime.combine(date.today(), datetime.min.time().replace(hour=18, minute=30), ZoneInfo("Europe/Lisbon")).astimezone(timezone.utc)


class PickupForAList(unittest.TestCase):
    def setUp(self):
        RM._MEM.clear()
        self.asked = []

        async def moment(account, event):
            self.asked.append(account)
            return {"speak": True, "line": "Tomorrow at the counter: decline the CDW."}
        from agapi import s2_fine_print as FP
        from booking_signer import live_events as LE
        for p in (mock.patch.object(RM, "RUN", None), mock.patch("booking_signer.identity.founder_account", lambda: FOUNDER),
                  mock.patch.object(FP, "moment", moment), mock.patch.object(LE, "publish", lambda a, ev: None),
                  mock.patch.object(RM, "_whatsapp", mock.AsyncMock(return_value="not sent: outside the 24-hour window"))):
            p.start()
            self.addCleanup(p.stop)
        for a in (FOUNDER, JON, GUEST):
            run(RM.note(a, {"rental_company": "Example Rentals", "country": "PT", "pickup_date": TOMORROW, "pickup_time": "10:00"}))

    def test_the_list(self):
        with mock.patch.dict("os.environ", {"SASHA_PROACTIVE_RENTALS": f"founder, {JON}, not-an-id"}):
            self.assertEqual(RM.accounts(), [FOUNDER, JON])
        with mock.patch.dict("os.environ", {"SASHA_PROACTIVE_RENTALS": "1"}):
            self.assertEqual(RM.accounts(), [FOUNDER])                       # as 227
        with mock.patch.dict("os.environ", {"SASHA_PROACTIVE_RENTALS": ""}):
            self.assertEqual(RM.accounts(), [])

    def test_tyler_and_jon_each_once_never_a_guest(self):
        with mock.patch.dict("os.environ", {"SASHA_PROACTIVE_RENTALS": f"founder,{JON}"}):
            first = run(RM.tick(evening()))
            again = run(RM.tick(evening()))
        self.assertEqual(sorted(self.asked), sorted([FOUNDER, JON]))
        self.assertEqual((len(first), again), (2, []))                       # one per rental, ever; the guest never


class Dormant(unittest.TestCase):
    def test_closings_in_her_languages(self):
        for said, lang in [("Thanks!", "en"), ("thank you so much", "en"), ("That's all, bye", "en"), ("Perfect, thanks Sasha 🙏", "en"),
                           ("Gracias, eso es todo", "es"), ("Merci beaucoup", "fr"), ("Danke schön!", "de"), ("Grazie mille", "it"),
                           ("Obrigada", "pt"), ("Dank je wel", "nl"), ("Moltes gràcies", "ca"), ("ok thanks", "en")]:
            self.assertEqual(CL.closing(said), lang, said)

    def test_not_a_closing(self):
        for said in ["Thanks — and book the spa too", "Thanks, what time is it booked for?", "ok", "yes", "Book dinner",
                     "Thank you, can you email Jon the details?", "Bye the way, is it open on Sunday?", ""]:
            self.assertIsNone(CL.closing(said), said)

    def test_her_one_line(self):
        self.assertEqual(CL.line("en"), "OK! Just tap me if you need me — I'm right here.")
        self.assertEqual(set(CL.LINES), set(CL._PHRASES))


SEARCH = {"cards": [{"place_id": "p1", "name": "Casa Gate", "photo": "https://x/photo.jpg", "rating": 4.6}, {"place_id": "p2", "name": "Namaste"}],
          "ribbon": "5 Indian restaurants in Madrid · tonight 21:00",
          "calls": [{"tool": "search_venues", "ok": True}]}


class Memory(unittest.TestCase):
    def setUp(self):
        MEM._MEM.clear()
        p = mock.patch.object(MEM, "RUN", None)
        p.start()
        self.addCleanup(p.stop)

    def test_a_search_is_the_thing_and_comes_back(self):
        run(MEM.remember(GUEST, "s-1", "Book me a table for two at an Indian restaurant in Madrid tonight at 9.", "Here are five — tap one?", SEARCH))
        m = MEM._MEM[GUEST]
        self.assertEqual(m["thing"], "Indian restaurants in Madrid, tonight 21:00")
        self.assertNotIn("photo", m["screen"]["cards"][0])                  # no photo fetched on return
        self.assertEqual(MEM.line_for(m, GUEST), "Welcome back — we were looking at Indian restaurants in Madrid, tonight 21:00. Want to carry on?")
        self.assertEqual(m["pending"], {"kind": "question", "asked": "Here are five — tap one?", "at": m["pending"]["at"]})

    def test_recall_puts_her_cards_back_on_screen_for_the_new_session(self):
        from app.agent import sasha as AG
        from agapi import venues as VN
        run(MEM.remember(GUEST, "s-1", "Indian in Madrid tonight", "Here are five.", SEARCH))
        got = run(MEM.recall(GUEST, "s-2"))
        self.assertTrue(got["line"].startswith("Welcome back — we were looking at "))
        self.assertEqual([m["role"] for m in got["recent"]], ["user", "assistant"])
        self.assertEqual(AG._SCREEN["s-2"]["names"], ["Casa Gate", "Namaste"])  # she may name them again
        self.assertEqual(VN.card_of(GUEST, "p2")["name"], "Namaste")
        AG._SCREEN.pop("s-2", None)

    def test_a_hold_awaiting_yes(self):
        run(MEM.remember(GUEST, "s-1", "Indian in Madrid tonight", "Here are five.", SEARCH))
        seen = {"cards": [SEARCH["cards"][0]], "ribbon": "Casa Gate · tonight 21:00", "calls": [{"tool": "hold_venue", "ok": True, "status": "awaiting_yes"}]}
        run(MEM.remember(GUEST, "s-1", "This one: “Casa Gate”", "Casa Gate, two people, tonight at 21:00. Shall I send it?", seen))
        m = MEM._MEM[GUEST]
        self.assertEqual(m["pending"]["kind"], "hold")
        self.assertEqual(m["thing"], "Casa Gate, tonight 21:00 — it's ready, waiting for your yes")
        self.assertEqual(MEM.line_for(m, GUEST), "Welcome back — we were looking at Casa Gate, tonight 21:00. Want to carry on?")  # lapsed: what it was

    def test_booked_leaves_nothing_to_carry_on(self):
        run(MEM.remember(GUEST, "s-1", "x", "Here are five.", SEARCH))
        run(MEM.remember(GUEST, "s-1", "Yes, book it.", "✅ Booked — Casa Gate, tonight at 21:00.", {"calls": [{"tool": "book_venue", "ok": True, "status": "confirmed"}]}))
        m = MEM._MEM[GUEST]
        self.assertIsNone(MEM.line_for(m, GUEST))
        self.assertIn("done: Indian restaurants in Madrid, tonight 21:00", m["summary"])

    def test_masks_only(self):
        run(MEM.remember(GUEST, "s-1", "my card is 4242 4242 4242 4242", "I can't take a card number here.", {}))
        run(MEM.remember(GUEST, "s-1", "my passport number is PAA123456", "Use the photo instead.", {}))
        run(MEM.remember(GUEST, "s-1", "use my passport", "I have your passport (ES ••••456) and will apply it.", {}))
        lines = [x["content"] for x in MEM._MEM[GUEST]["recent"]]
        self.assertEqual(lines[0], MEM.REMOVED)
        self.assertEqual(lines[2], MEM.REMOVED)
        self.assertIn("ES ••••456", lines[5])                                 # a mask is kept
        self.assertNotIn("4242", " ".join(lines))
        self.assertNotIn("123456", " ".join(lines))

    def test_kept_recent_and_for_24_hours(self):
        for i in range(15):
            run(MEM.remember(GUEST, "s-1", f"line {i}", "ok.", SEARCH))
        m = MEM._MEM[GUEST]
        self.assertEqual(len(m["recent"]), MEM.KEEP)
        m["updated_at"] = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
        self.assertIsNone(MEM.line_for(m, GUEST))

    def test_closing_clears_the_thing_but_not_a_waiting_hold(self):
        run(MEM.remember(GUEST, "s-1", "x", "Here are five.", SEARCH))
        run(MEM.closing(GUEST, "thanks", CL.line("en")))
        self.assertIsNone(MEM._MEM[GUEST]["thing"])
        seen = {"ribbon": "Casa Gate · tonight 21:00", "calls": [{"tool": "hold_venue", "ok": True, "status": "awaiting_yes"}]}
        run(MEM.remember(GUEST, "s-1", "Casa Gate", "Shall I send it?", seen))
        run(MEM.closing(GUEST, "bye", CL.line("en")))
        self.assertEqual(MEM._MEM[GUEST]["pending"]["kind"], "hold")


if __name__ == "__main__":
    unittest.main()
