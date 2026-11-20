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

    def test_ratchet_no_module_but_s2_memory_reads_or_writes_conversation_history(self):
        """Tyler (392): no door keeps a history of its own — WhatsApp's st["history"], the voice door's, the page's body history, the
        CTO doors' conversation_history: every one is gone or handed to s2_memory's door reader, the ONE place."""
        import pathlib
        import re
        root = pathlib.Path(__file__).resolve().parents[1]
        copy = re.compile(r"""\[\s*["']history["']\s*\]|\.get\(\s*["']history["']|_remember_history|verified_history|\b(?:recent_of|messages_of)\(""")
        page = re.compile(r"\b(?:body|request)\.conversation_history\b")
        hits = []
        for d in ("agapi", "app", "booking_signer", "products"):
            for f in sorted((root / d).rglob("*.py")):
                rel = f.relative_to(root).as_posix()
                if rel == "agapi/s2_memory.py":
                    continue
                if rel == "app/api/golf.py":   # the CTO's golf router: never mounted — the moment it is, it reads the ONE record too
                    self.assertNotIn("golf", (root / "app/main.py").read_text())
                    continue
                for n, line in enumerate(f.read_text().splitlines(), 1):
                    code = line.split("#", 1)[0]
                    if copy.search(code) or (page.search(code) and "_MEM392.door_history(" not in code):
                        hits.append(f"{rel}:{n}: {line.strip()[:90]}")
        self.assertEqual(hits, [])

    def test_whatsapp_and_every_door_read_the_one_reader(self):
        self.assertIn("MEM.conversation(account", inspect.getsource(WA.agent_turn))
        self.assertIn("booking=bool(getattr(out", inspect.getsource(GW._send))
        for rel in ("app/api/conductor.py", "app/api/voice_conductor.py"):   # the CTO's doors: Stage B (scripts/stage_b_one_record_392.py)
            src = (__import__("pathlib").Path(__file__).resolve().parents[1] / rel).read_text()
            self.assertIn("_MEM392.door_history(", src, rel)
            self.assertIn("_MEM392.door_said(", src, rel)


class EveryDoorWritesTheOneRecord(unittest.TestCase):
    """Found on the 392 gate (b3137d84): the voice / REST door kept its own history copy and never wrote the ONE record — once the brain
    read only the record, its "yes" landed on nothing. Every door that calls the brain records what it hears and says."""

    def test_the_voice_doors_second_turn_hears_its_first(self):
        from datetime import datetime, timezone
        from booking_signer import voice_turn as VTN
        MEM._MEM.clear()
        seen = []

        async def quiver(account, message, history, session, surface="s1"):
            seen.append([m["content"] for m in history])
            yield {"type": "done", "text": "For how many people?" if len(seen) == 1 else "Booked."}

        async def nothing(*a, **k):
            return None
        st = {}
        with mock.patch("app.agent.sasha.turn_with_quiver", quiver), mock.patch("app.agent.sasha.over_budget", nothing), \
                mock.patch("agapi.s2_memory.remember", nothing), mock.patch("agapi.s2_memory.closing", nothing), \
                mock.patch("agapi.person_access.warm", mock.AsyncMock()), mock.patch.object(GW, "STORE", GW.MemoryGuestStore()):
            for said in ("Book a restaurant in Madrid on Saturday at 21:00", "4 people"):
                asyncio.run(VTN.turn(ACCT, said, [], tap=None, venues_only=True))
        self.assertEqual(seen[0], [])
        self.assertEqual(seen[1], ["Book a restaurant in Madrid on Saturday at 21:00", "For how many people?"])   # from the ONE record

    def test_the_public_demo_has_no_record_and_a_signed_in_page_is_never_read(self):
        MEM._MEM.clear()
        page = [{"role": "user", "content": "Book for 4"}, {"role": "assistant", "content": "Booked — 4 people."}]
        self.assertEqual(asyncio.run(MEM.door_history(ACCT, True, "hi", page)), [])          # signed in: the record (empty), never the page
        self.assertEqual(asyncio.run(MEM.door_history(None, False, "hi", page)), page)       # the demo: no person, books nothing
        asyncio.run(MEM.door_said(ACCT, True, "rest", "Book for 4", {"response": "Booked.", "booking_ref": "R1"}))
        self.assertEqual(asyncio.run(MEM.conversation(ACCT)), [{"role": "user", "content": "Book for 4"}, {"role": "assistant", "content": MEM.POINTER}])
        asyncio.run(MEM.door_said(ACCT, True, "rest", "again", {"response": "x", "recorded": True}))   # voice_turn recorded it: once
        self.assertEqual(len(asyncio.run(MEM.conversation(ACCT))), 2)


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
