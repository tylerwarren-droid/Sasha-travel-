"""Sasha 381h · EVERY WAY A PERSON SAYS A BOOKING'S TIME IS READ BY ONE READER (agapi.said.times_in), EN and ES. NO PATCHES.

Found by 381g (row 1988): said.time_ read 21:30 only as "21:30" — "9:30pm", "9.30 pm", "half past nine" were not read (Sasha asked "What
time?" in a loop) — and it read "at nine thirty" as 21:00 (a time they never said, accepted). A wrong read is worse than no read
(KANOE: a term not given is asked, never guessed). Time readers lived in many places: said.time_, handoff.plain_time /
context_time / plain_open_at / the bare_time + restaurant_time guess ("a restaurant's 9 is the evening"), chat_request._time,
guest_whatsapp (_SPA_T, _EAT_T, _hhmm, _at_time — unused), wa_brain.hour_said / spoken_time / book_added's evening guess / the hour
answer, itinerary_q._hm, s2_fine_print (an accident's time), s2_manage._option_named and flight_pick (a time naming an offer),
products health.parse_when / cita.when / itinerary.parse_day_time. Now ONE: times_in (a bare hour without its side → unsure_hours,
asked "9am or 9pm?"; a venue's known hours open on one side only → that side; a time naming an offered option → times_matching).
Not readers of the person's words, left: heard / mailbox / campus confirm / venue_submit's offered time (a VENUE's or a school's
words), v0.hhmm / s2_manage new_time (the model's structured argument), spoken / recap (Sasha's own speech).
Also: the second "already sent" memory (venues._SENT) is deleted — a bare yes with nothing held reads THE record of what was sent.

    cd backend && python -m unittest tests.test_s381h_one_time_reader -v
"""
from __future__ import annotations

import asyncio
import inspect
import pathlib
import re
import time
import unittest
from datetime import timedelta
from unittest import mock

from agapi import said as SD, v0 as API, venues as VN, venue_submit as VS
from app.agent import voice as V
from tests.test_s254_handle_it_live import use_fake_agapi
from tests.test_s254_one_decider import ACCT, ALL4, Base, engine_from, reader

run = asyncio.run
BACKEND = pathlib.Path(__file__).resolve().parents[1]


class EveryForm(unittest.TestCase):
    def test_en_and_es(self):
        cases = {"21:30": "21:30", "at 9:30pm": "21:30", "at 9.30 pm": "21:30", "21h30": "21:30", "at 2130": "21:30",
                 "half past nine at night": "21:30", "half past nine tonight": "21:30", "half nine tonight": "21:30",
                 "nine thirty tonight": "21:30", "quarter past nine tonight": "21:15", "quarter to nine tonight": "20:45",
                 "dinner at nine": "21:00", "tonight at nine": "21:00", "at nine at night": "21:00", "9pm": "21:00",
                 "a las nueve y media de la noche": "21:30", "cena a las nueve y cuarto": "21:15", "a las nueve de la noche": "21:00",
                 "las nueve menos cuarto de la noche": "20:45", "21h": "21:00", "breakfast at 9": "09:00", "at 9 in the morning": "09:00",
                 "10 in the morning": "10:00", "lunch at 1": "13:00", "at noon": "12:00"}
        for words, want in cases.items():
            self.assertEqual(SD.times_in(f"a table for 2 on Saturday {words}"), [want], words)

    def test_a_bare_hour_is_unsure_never_read(self):
        for words, hm in (("at nine", (9, 0)), ("a las nueve", (9, 0)), ("at nine thirty", (9, 30)), ("table for 2 at 9", (9, 0)),
                          ("lunch at 8", (8, 0))):
            self.assertEqual((SD.times_in(words), SD.unsure_hours(words)), ([], [hm]), words)

    def test_a_clock_hour_without_its_side_is_asked_too(self):
        """"9:30", "09:00" with no side said: asked — speech-to-text writes a spoken "nine" as "09:00" (Sasha 167's live failure)."""
        for words, hm in (("at 9:30", (9, 30)), ("a romantic restaurant on October 27 at 09:00", (9, 0)), ("at 11:00", (11, 0))):
            # Sasha 381i · SPOKEN (through speech-to-text) — typed, the same clock is the 24-hour clock as written
            self.assertEqual((SD.times_in(words, spoken=True), SD.unsure_hours(words, spoken=True)), ([], [hm]), words)
            self.assertEqual(SD.times_in(words, spoken=False), [f"{hm[0]:02d}:{hm[1]:02d}"], words)
        for words, want in (("dinner at 9:30", "21:30"), ("breakfast at 9:30", "09:30"), ("a dinner at 08:00 at night", "20:00")):
            self.assertEqual(SD.times_in(words), [want], words)

    def test_what_is_not_a_time(self):
        for words in ("for 13 people", "for 2 tonight", "table for 4 at night", "party of 6 in the evening", "on 20.11", "the 13th",
                      "13 personas", "para 2 esta noche"):
            self.assertEqual(SD.times_in(words), [], words)

    def test_the_wrong_read_never_happens(self):
        """"nine thirty" can NEVER yield 21:00 — with or without a side, in any phrasing."""
        for words in ("at nine thirty", "nine thirty", "nine thirty tonight", "dinner at nine thirty", "at 9:30", "dinner at 9:30",
                      "half past nine", "half past nine at night", "a las nueve y media", "a las nueve y media de la noche"):
            self.assertNotIn("21:00", SD.times_in(words), words)
            self.assertFalse(SD.time_(words, "21:00"), words)

    def test_the_venues_hours_decide_only_one_side(self):
        self.assertEqual(SD.times_in("Tuesday 10:00", open_between=(7, 21)), ["10:00"])   # 22:00 is closed
        self.assertEqual(SD.times_in("at nine", open_between=(7, 23)), [])                 # open both: asked
        self.assertEqual(SD.times_in("at 2", open_between=(12, 23)), ["14:00"])

    def test_a_time_naming_an_offer(self):
        self.assertEqual(SD.times_matching("the 7:44 please"), ["07:44", "19:44"])         # matched to what's offered, never sent


class ThroughTheRealTurn(Base):
    """hold_venue with each form → scope.booking carries the time they said; a bare hour → "9am or 9pm?", then their answer books it."""

    def setUp(self):
        super().setUp()
        self.agapi = use_fake_agapi(self)

    def hold(self, words, day, at, before=""):
        args = {"name": "Casa Gate", "city": "Madrid", "country": "ES", "what": "dinner", "party": 3, "day": day, "time": at,
                "place_id": "ChIJcasagate254"}
        rungs = {"email": ALL4["email"]}
        with mock.patch.object(VN, "_read", reader(rungs, "Casa Gate")), mock.patch.object(VN, "engine_channel", engine_from(rungs, None)):
            return run(VN.hold_venue(API.Ctx(account=ACCT, mode="test", user_said=words, said_before=before, session="s381h-" + words,
                                             surface="s2", via="wa"), args))

    def scope(self):
        return [b for o, b, _a in self.agapi.calls if o == "approvals.mandate"][-1]["scope"]["booking"]

    def test_each_form_reaches_scope_booking(self):
        day = (VN._today("ES") + timedelta(days=3)).isoformat()
        forms = {"book Casa Gate on Saturday at 21:30 for 3": "21:30", "book Casa Gate at 9:30pm for 3": "21:30",
                 "book Casa Gate at 9.30 pm for 3": "21:30", "book Casa Gate at 21h30 for 3": "21:30",
                 "book Casa Gate at half past nine at night, three people": "21:30", "book Casa Gate at nine thirty tonight for 3": "21:30",
                 "book Casa Gate at quarter past nine tonight for 3": "21:15", "book Casa Gate at quarter to nine tonight for 3": "20:45",
                 "dinner for 3 at Casa Gate at nine": "21:00", "reserva Casa Gate a las nueve y media de la noche para 3": "21:30",
                 "reserva Casa Gate a las nueve y cuarto de la noche para 3": "21:15", "reserva Casa Gate a las nueve de la noche para 3": "21:00"}
        for words, want in forms.items():
            API._CLAIMED.clear()
            out = self.hold(f"{words} on {day}", day, want)
            self.assertNotEqual(out.get("status"), "need_term", (words, out))
            self.assertEqual(self.scope()["time"], want, words)

    def test_a_bare_hour_asks_its_side_then_books(self):
        day = (VN._today("ES") + timedelta(days=3)).isoformat()
        first = f"book Casa Gate on {day} at nine for 3"
        out = self.hold(first, day, "21:00")
        self.assertEqual((out["status"], out["ask"]), ("need_term", "9am or 9pm?"))
        self.assertEqual(V.yes_line("hold_venue", {"ok": True, "result": out}), "9am or 9pm?")   # said by code, word for word
        out = self.hold("9pm", day, "21:00", before=first)
        self.assertNotEqual(out.get("status"), "need_term", out)
        self.assertEqual(self.scope()["time"], "21:00")

    def test_nine_thirty_never_books_21_00(self):
        day = (VN._today("ES") + timedelta(days=3)).isoformat()
        out = self.hold(f"book Casa Gate on {day} at nine thirty for 3", day, "21:00")   # the model's guess: never accepted
        self.assertEqual((out["status"], out["ask"]), ("need_term", "9:30am or 9:30pm?"))


class OneSentMemory(unittest.TestCase):
    """(4) venues._SENT is gone: a bare yes with nothing held reads THE record of what was sent (venue_submit's acts)."""

    def test_gone(self):
        self.assertFalse(hasattr(VN, "_SENT"))
        self.assertNotIn("_SENT", (BACKEND / "agapi/venues.py").read_text())

    def test_a_bare_yes_reads_the_record(self):
        with mock.patch.dict(VS._ACTS, {ACCT: [{"act_id": "a1", "venue": "Casa Gate", "at": time.time()}]}, clear=True):
            self.assertEqual(run(VN.last_sent(ACCT))["venue"], "Casa Gate")
        with mock.patch.dict(VS._ACTS, {ACCT: [{"act_id": "a1", "venue": "Casa Gate", "at": time.time() - 3600}]}, clear=True):
            self.assertIsNone(run(VN.last_sent(ACCT)))                                   # long ago: not this yes


class TheRatchet(unittest.TestCase):
    def test_one_reader(self):
        from booking_signer import chat_request as CR, flight_pick as FP, handoff as HO, itinerary_q as IQ, wa_brain as WB
        from agapi import s2_fine_print as FPR, s2_manage as SM
        from products import itinerary as PI
        from products.health import cita as CI, turn as HT
        self.assertIn("in times_in(", inspect.getsource(SD.time_))
        for f in (HO.plain_time, HO.plain_open_at, CR._time, IQ._hm, PI.parse_day_time, HT.parse_when, CI.when):
            self.assertIn("SD.times_in(", inspect.getsource(f), f.__name__)
        self.assertIn("SD.unsure_hours(", inspect.getsource(WB.hour_said))
        for f in (SM._option_named, FP):
            self.assertIn("SD.times_matching(", inspect.getsource(f))
        self.assertIn("SD.times_in(", inspect.getsource(FPR))
        for m, gone in ((HO, "context_time"), (HO, "restaurant_time"), (HO, "_DINNER"), (WB, "spoken_time"), (WB, "_EVENINGISH"),
                        (WB, "_HHMM"), (WB, "_SPOKEN"), (IQ, "_TIME")):
            self.assertFalse(hasattr(m, gone), f"{m.__name__}.{gone}")
        gw = (BACKEND / "booking_signer/guest_whatsapp.py").read_text()
        for gone in ("_SPA_T", "_EAT_T", "def _at_time", "def _hhmm", "restaurant_time", "context_time", "spoken_time", "bare_time"):
            self.assertNotIn(gone, gw)
        self.assertIsNone(re.search(r"\bbare_time\b", (BACKEND / "booking_signer/handoff.py").read_text()))


if __name__ == "__main__":
    unittest.main()
