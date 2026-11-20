"""Sasha 392 · chat history is never a source of THIS request's facts (EU 287 S5 / S10 / S11), plus each place's own photo on WhatsApp.

Measured (main 633f72d4): S5 · sasha.py built ctx.said_before from the last 4,000 characters of EVERY user line, and venues.said_terms
read a party / day / time from it — "4" from Saturday's request was SAID for Sunday's. S11 · the model got the last 40 history lines raw,
her old "Booked … 21:00, 4 people" among them (WhatsApp from its own st["history"] copy). S10 · each act kept the hold's when / party,
never refreshed after a change; AgAPI's venue.bookings (CR 132) gives both from the ONE record.

    cd backend && python -m unittest tests.test_s392_this_request_only -v
"""
from __future__ import annotations

import asyncio
import inspect
import unittest
from datetime import date, timedelta
from unittest import mock

from agapi import s2_memory as MEM, v0 as API, venue_submit as VS, venues as VN
from app.agent import sasha as AG
from booking_signer import guest_whatsapp as GW, wa_agent as WA

ACCT = "00000000-0000-4000-8000-000000000392"
SAT = (date.today() + timedelta(days=(5 - date.today().weekday()) % 7 or 7)).isoformat()
SUN = (date.fromisoformat(SAT) + timedelta(days=1)).isoformat()


class TwoRequests(unittest.TestCase):
    def setUp(self):
        VN.request_closed(ACCT)

    def ctx(self, said):
        VN.request_heard(ACCT, said)
        return API.Ctx(account=ACCT, user_said=said, surface="s2")

    def test_the_second_request_never_takes_the_firsts_party(self):
        first = self.ctx("Book dinner for 4 at La Taberna de Peñalver on Saturday at 21:00")
        self.assertIn("party", VN.said_terms(first, {"day": SAT, "time": "21:00", "party": 4, "country": "ES"}))
        VN.request_closed(ACCT)   # the first became an act (venues._act claims it) — its request ends
        second = self.ctx("Book lunch at Peñalver Callao on Sunday")
        got = VN.said_terms(second, {"day": SUN, "time": "14:00", "party": 4, "country": "ES"})   # the model carried 4 over
        self.assertNotIn("party", got)                                                          # → asked, never taken
        self.assertIn("date", got)

    def test_an_answer_to_the_requests_own_ask_joins_it(self):
        self.ctx(f"Book Casa Gate on {SAT} at 21:00")
        self.assertIn("party", VN.said_terms(self.ctx("4 people"), {"day": SAT, "time": "21:00", "party": 4, "country": "ES"}))

    def test_no_history_window_feeds_the_terms(self):
        src = inspect.getsource(AG.turn)
        self.assertNotIn("[-4000:]", src)
        self.assertNotIn("said_before=", src)
        self.assertIn("request_heard(account, message)", src)
        self.assertNotIn("said_before", inspect.getsource(VN._words_of))
        self.assertIn("request_closed(ctx.account)", inspect.getsource(VN._act))


class TheRecordsTimeAndParty(unittest.TestCase):
    def test_a_booking_changed_at_agapi_is_said_as_the_record_has_it(self):
        act = {"act_id": "act_392", "venue": "Casa Lucio", "when": "2026-11-21T21:00", "party": 4, "state": "confirmed", "words": "ok",
               "answered": True}
        rec = [{"act_id": "act_392", "at": "2026-11-21T22:30", "party": 2, "state": "confirmed"}]
        with mock.patch.object(VS, "acts_of", mock.AsyncMock(return_value=[dict(act)])), \
                mock.patch.object(VS, "record", mock.AsyncMock(return_value=rec)), \
                mock.patch.object(VS, "status", mock.AsyncMock(return_value=None)), \
                mock.patch("agapi.s2_memory.put_kind", mock.AsyncMock()):
            rows = asyncio.run(VS.bookings(ACCT))
        row = next(r for r in rows if r["act_id"] == "act_392")
        self.assertEqual((row["time"], row["party"]), ("22:30", 2))   # the record's, never the hold's 21:00 / 4


class HistoryIsAPointer(unittest.TestCase):
    def test_a_booking_line_reaches_the_model_as_a_pointer(self):
        m = MEM.fold({}, "Book Casa Lucio Saturday 21:00 for 4", "Booking now: Casa Lucio, 4 people, Sat at 21:00. Booked — reference CL1.",
                     {"calls": [{"tool": "hold_venue", "ok": True, "status": "confirmed"}]})
        lines = MEM.recent_of(m)
        self.assertEqual(lines[-1]["content"], MEM.POINTER)
        self.assertEqual(MEM.messages_of(m)[-1]["text"].split(".")[0], "Booking now: Casa Lucio, 4 people, Sat at 21:00")   # kept for them
        chat = MEM.fold({}, "hi", "Hello! Where to?", {"calls": []})
        self.assertEqual(MEM.recent_of(chat)[-1]["content"], "Hello! Where to?")                       # chat stays chat

    def test_whatsapp_reads_the_one_record(self):
        src = inspect.getsource(WA.agent_turn)
        self.assertIn("MEM.recent_of(await MEM._load(account))", src)
        self.assertNotIn('st.get("history")', src)
        self.assertIn("booking=bool(getattr(out", inspect.getsource(GW._send))


class EachPlacesPhotoOnWhatsApp(unittest.TestCase):
    def test_the_photos_then_the_list_one_ordered_answer(self):
        cards = [{"name": n, "place_id": f"p{i}", "photo": f"https://lh3.googleusercontent.com/p{i}"}
                 for i, n in enumerate(("La Taberna de Peñalver", "Taberna de Peñalver Callao", "… Cava Baja"), 1)]
        out = GW.Out().text("Three Peñalver places — which one?")
        WA.render({"kind": "venues", "preset": {"cards": cards}}, out, {}, None)
        out.one = True
        out.compose()
        kinds = [i[0] for i in out.items]
        self.assertEqual(kinds, ["media", "media", "media", "list"])                                # images first, then the list
        self.assertEqual([i[2] for i in out.items[:3]], [c["photo"] for c in cards])                # each its own place's photo
        self.assertIn("which one?", out.items[3][1])


if __name__ == "__main__":
    unittest.main()
