"""Sasha 381f · EVERY WAY A PERSON NAMES THE BOOKING'S DAY IS READ BY ONE READER (agapi.said.days_in), EN and ES, resolved against today
(the venue's local date). NO PATCHES.

Found by 381e's gate (row 1980): "dinner for 2 in Hanoi on the 13th at 8pm" — the person gave the day, but said.day read a day of the
month only WITH its month, so AgAPI's term_not_given named "date" and Sasha asked "Which day?" in a loop. Day readers lived in FIVE places:
said.day (a matcher), handoff.plain_date (dates + tomorrow), itinerary_q.day_of (its own "the 5th"), handoff's weekday branch,
chat_request.plain_day (today / weekdays) and invitations.window (tomorrow / weekdays). Now ONE: days_in; the rest read it.
(booking_signer.heard is not one of them: it checks what a VENUE said on a call, in six languages, against the booking.)

    cd backend && python -m unittest tests.test_s381f_one_day_reader -v
"""
from __future__ import annotations

import asyncio
import inspect
import pathlib
import unittest
from datetime import date, timedelta
from unittest import mock

from agapi import said as SD, v0 as API, venues as VN
from tests.test_s254_handle_it_live import use_fake_agapi
from tests.test_s254_one_decider import ACCT, ALL4, Base, engine_from, reader

run = asyncio.run
BACKEND = pathlib.Path(__file__).resolve().parents[1]
FRI = date(2026, 11, 13)   # a Friday


class EveryForm(unittest.TestCase):
    def test_en_and_es(self):
        cases = {"2026-11-20": "2026-11-20", "20/11": "2026-11-20", "13 Nov": "2026-11-13", "the 13th of November": "2026-11-13",
                 "November 20": "2026-11-20", "20 de noviembre": "2026-11-20", "on the 13th": "2026-11-13", "the 5th": "2026-12-05",
                 "el 13": "2026-11-13", "el día 20": "2026-11-20", "today": "2026-11-13", "tonight": "2026-11-13", "hoy": "2026-11-13",
                 "esta noche": "2026-11-13", "tomorrow": "2026-11-14", "mañana": "2026-11-14", "pasado mañana": "2026-11-15",
                 "the day after tomorrow": "2026-11-15", "Saturday": "2026-11-14", "el sábado": "2026-11-14", "Friday": "2026-11-13",
                 "from 20 to 22 October": "2027-10-20", "del 20 al 22 de octubre": "2027-10-20"}
        for words, want in cases.items():
            got = SD.days_in(f"dinner for 2 {words} at 21:00", FRI)
            self.assertEqual(got[0].isoformat() if got else None, want, words)

    def test_what_is_not_a_day(self):
        for words in ("for 13 people", "at 13:00", "table for 2 at 9", "por la mañana", "13 personas", "a las 9"):
            self.assertEqual(SD.days_in(words, FRI), [], words)

    def test_said_day_is_the_reader(self):
        self.assertTrue(SD.day("dinner on the 13th at 8pm", FRI, FRI))
        self.assertFalse(SD.day("dinner on the 14th at 8pm", FRI, FRI))


class ThroughTheRealTurn(Base):
    """hold_venue with each form → scope.booking carries the day they named; with none → "Which day?" (AgAPI's term_not_given)."""

    def setUp(self):
        super().setUp()
        self.agapi = use_fake_agapi(self)

    def hold(self, words, day):
        args = {"name": "Casa Gate", "city": "Madrid", "country": "ES", "what": "dinner", "party": 2, "day": day, "time": "21:00",
                "place_id": "ChIJcasagate254"}
        rungs = {"email": ALL4["email"]}
        with mock.patch.object(VN, "_read", reader(rungs, "Casa Gate")), mock.patch.object(VN, "engine_channel", engine_from(rungs, None)):
            return run(VN.hold_venue(API.Ctx(account=ACCT, mode="test", user_said=words, session="s381f-" + words, surface="s2", via="wa"),
                                     args))

    def scope(self):
        return [b for o, b, _a in self.agapi.calls if o == "approvals.mandate"][-1]["scope"]["booking"]

    def test_each_form_reaches_scope_booking(self):
        today = VN._today("ES")
        nth = today + timedelta(days=3)
        forms = {f"book Casa Gate on the {nth.day}{'th' if 11 <= nth.day <= 13 else {1: 'st', 2: 'nd', 3: 'rd'}.get(nth.day % 10, 'th')} "
                 f"at 21:00 for 2": nth,
                 f"reserva en Casa Gate el {nth.day} a las 21:00 para 2": nth,
                 "book Casa Gate tomorrow at 21:00 for 2": today + timedelta(days=1),
                 "reserva Casa Gate mañana a las 21:00 para 2": today + timedelta(days=1),
                 f"book Casa Gate on {nth:%A} at 21:00 for 2": nth,
                 f"book Casa Gate on {nth.day} {nth:%b} at 21:00 for 2": nth}
        for words, want in forms.items():
            API._CLAIMED.clear()
            out = self.hold(words, want.isoformat())
            self.assertNotEqual(out.get("status"), "need_term", (words, out))
            self.assertEqual(self.scope()["date"], want.isoformat(), words)

    def test_no_day_is_asked_only_then(self):
        out = self.hold("book Casa Gate at 21:00 for 2", (VN._today("ES") + timedelta(days=3)).isoformat())
        self.assertEqual((out["status"], out["ask"]), ("need_term", "Which day?"))


class AFailedBuildsRecordingIsNeverReplayed(unittest.TestCase):
    """Sasha 381f · found by 381d/381e: the refusal-era replies recorded by a build whose gate FAILED were replayed by every later run
    (record mode fills only what's missing). Each recording carries its build; only this build's, a passed build's or an unmarked (older,
    passed) one is replayed — a failed build's is re-recorded."""

    def setUp(self):
        from booking_signer import model_gateway as MG
        from tests import test_s353_gateway as T353
        T353.fresh()

        class Replays(T353.Replays):
            ok = set()

            async def passed(self, b):
                return b in self.ok

            async def mark_passed(self, b):
                self.ok.add(b)
        self.MG, self.T353, self.store = MG, T353, Replays()
        MG.REPLAYS = self.store
        self.addCleanup(setattr, MG, "REPLAYS", None)
        self.addCleanup(setattr, MG, "STORE", None)
        self.ask = {"model": "claude-haiku-4-5", "max_tokens": 5, "messages": [{"role": "user", "content": "book Taverna Sandbox"}]}

    def record_as(self, build_id, sent):
        async def go():
            with mock.patch.dict("os.environ", {"SASHA_MODEL_REPLAY": "record", "RAILWAY_DEPLOYMENT_ID": build_id}):
                await self.T353.client(sent).messages.create(**self.ask)
        run(go())

    def replay_as(self, build_id):
        async def go():
            with mock.patch.dict("os.environ", {"SASHA_MODEL_REPLAY": "replay", "RAILWAY_DEPLOYMENT_ID": build_id}):
                return await self.T353.client([]).messages.create(**self.ask)
        return run(go())

    def test_a_failed_builds_recording_is_none_and_is_re_recorded(self):
        sent = []
        self.record_as("dep_failed", sent)                                                 # its gate never marks it passed
        self.assertEqual(next(iter(self.store.d.values()))["build"], "dep_failed")
        with self.assertRaises(self.MG.ReplayMissing):
            self.replay_as("dep_next")                                                    # never replayed by another build
        self.record_as("dep_next", sent)                                                  # a recording run re-records it …
        self.assertEqual((len(sent), next(iter(self.store.d.values()))["build"]), (2, "dep_next"))   # … live, replacing it

    def test_a_passed_builds_recording_is_replayed(self):
        sent = []
        self.record_as("dep_ok", sent)
        run(self.store.mark_passed("dep_ok"))
        self.assertEqual(self.replay_as("dep_later").content[0].text, "Hello.")

    def test_an_older_unmarked_recording_is_replayed(self):
        sent = []
        self.record_as("dep_x", sent)
        next(iter(self.store.d.values())).pop("build")
        self.assertEqual(self.replay_as("dep_later").content[0].text, "Hello.")

    def test_the_gate_marks_only_a_pass(self):
        from scripts import gate
        src = inspect.getsource(gate.main)
        i = src.index("DEPLOY GATE:")
        self.assertIn("if not bad:   # Sasha 381f", src[i:i + 400])
        self.assertIn("MG.mark_build_passed()", src[i:i + 600])


class TheRatchet(unittest.TestCase):
    def test_one_reader(self):
        from booking_signer import chat_request as CR, handoff as HO, invitations as IV, itinerary_q as IQ
        self.assertIn("SD.days_in(", inspect.getsource(HO.plain_date))
        self.assertIn("HO.plain_date(", inspect.getsource(CR.plain_day))
        self.assertIn("HO.plain_date(", inspect.getsource(IQ.day_of))
        self.assertIn("SD.days_in(", inspect.getsource(IV.window))
        self.assertIn("d in days_in(", inspect.getsource(SD.day))
        for m, gone in ((HO, "_WEEKDAYS"), (HO, "_MONTHS"), (CR, "_WEEKDAYS"), (IV, "_WEEKDAYS"), (IQ, "_ORD")):
            self.assertFalse(hasattr(m, gone), f"{m.__name__}.{gone}")


if __name__ == "__main__":
    unittest.main()
