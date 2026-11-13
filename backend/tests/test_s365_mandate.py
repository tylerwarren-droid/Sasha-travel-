"""Sasha 365 · THE MANAGER'S INSTRUCTION IS THE APPROVAL — Sasha plans, books and reports on her own, asking ONLY when something is missing
or outside the company's limits.

Found (Tyler, 10 Nov 07:32–07:36, iPhone, the demo organiser, London 15–17 Dec, 6 executives): "planning…" with no sign of work, and he had
to ask before she finished; the hotel searched one room at a time ("try six rooms?" → "still one room's price… flights, or a different
hotel?", the hotel list again and again); "if I say book all executives, she should just do it, then tell us when she is finished — she
doesn't need to keep asking for permission"; and her face covered the send button while typing.

ONE source for "may I act": booking_signer.mandate — the instruction + the company's limits on the record.

    cd backend && python -m unittest tests.test_s365_mandate -v
"""
from __future__ import annotations

import asyncio
import pathlib
import re
import unittest
from unittest import mock

from agapi import v0 as API
from booking_signer import group_book as GB, group_outcome as GO, groups as G, live_events as LE, mandate as M
from tests import test_s339_book_all as W339

run = asyncio.run
OWNER = W339.OWNER
ROOT = pathlib.Path(__file__).resolve().parents[2]
SAID = "Book all executives to London 15–17 December"


def _executives(names):
    roster = {p["name"]: p for p in run(G.roster(OWNER))["people"]}
    for n in names:
        run(G.edit_person(OWNER, roster[n]["id"], {"role": "executive"}))


#: Sasha 381e · an S2 turn's door, as sasha.agent_turn records it (VS.TAP ← session_of(request)): the organiser's verified session
S2_SESSION = {"kind": "supabase", "token": "s365-organiser"}


def s2(coro):
    """Run a coroutine as an S2 turn: its door recorded first, exactly where the entry point records it (that turn's context only)."""
    async def go():
        from agapi import venue_submit as VS
        VS.TAP.set(S2_SESSION)
        return await coro
    return go()


def _instruction(said=SAID):
    """The chat's door, as the model calls it with the organiser's own words (the filter is theirs; the engine picks the people)."""
    async def go():
        from agapi import venue_submit as VS
        VS.TAP.set(S2_SESSION)   # Sasha 381e · the S2 door, as its entry point records it
        events = LE.subscribe(OWNER)
        ctx = API.Ctx(account=OWNER, user_said=said, surface="s2", session="s365-session")
        r = await API.call(ctx, "group_select", {"change": "new", "destination": "London", "starts_on": "2026-12-15", "ends_on": "2026-12-17",
                                                 "roles": ["executives"]})
        await M.finished(OWNER)
        out = []
        while not events.empty():
            out.append(events.get_nowait())
        LE.unsubscribe(OWNER, events)
        return r, out
    return run(go())


SIX = ["Amara Sample", "Bruno Example", "Chloé Placeholder", "Dario Fixture", "Elena Mockup", "Fritz Testperson"]


class ZeroQuestionsInsideTheLimits(unittest.TestCase):
    def test_book_all_executives_end_to_end(self):
        with W339.World() as w, mock.patch.object(G, "HOTELS", G._hotel_search):   # the real ONE search, through AgAPI's stand-in
            _executives(SIX)
            r, events = _instruction()
            view = run(G.view(OWNER))
        self.assertTrue(r["ok"], r)
        said = r["result"]["say"]
        self.assertNotIn("?", said)                                                        # no question: the instruction IS the yes
        self.assertIn("I'll tell you", said)
        lines = [e.get("text") or "" for e in events]
        progress = [e for e in events if e.get("type") == "group_progress"]
        done = [e for e in events if e.get("type") == "group_done"]
        self.assertTrue(progress, lines)                                                   # live progress, unasked
        self.assertTrue(any(re.match(r"Planning \d+ of 6", x) for x in lines), lines)
        self.assertTrue(any("Hotel: 6 rooms at" in x for x in lines), lines)
        self.assertEqual(len(done), 1, lines)                                              # the ONE finish, unasked
        fin = done[0]["text"]
        self.assertTrue(fin.startswith("All 6 booked (TEST)."), fin)
        self.assertIn("references are on the master list", fin)
        self.assertNotIn("?", fin)                                                         # inside the limits: zero questions
        self.assertEqual(sorted(r["status"] for r in view["rows"]), ["booked"] * 6)
        stays = [b for op, b in w.agapi.calls if op == "travel.find_stays"]
        self.assertEqual(len(stays), 1, stays)                                             # ONE group search …
        self.assertEqual(stays[0]["party"], 6)                                             # … for 6 rooms, the trip's dates
        self.assertEqual(stays[0]["check_in"], "2026-12-15")
        self.assertNotIn("country", stays[0]["city"])                                      # never a country of its own (London ≠ ES)
        self.assertIn("Hotel: 6 rooms at", view["hotel_line"])                             # ONE line on the master list


class OneGroupedQuestionOutsideTheLimits(unittest.TestCase):
    def test_over_the_limit_is_asked_once_after_the_rest_is_booked(self):
        casablanca = ["Rania Mithal"]   # from Casablanca: over the worker's €600 flights
        with W339.World(W339.PricedAgAPI(per_night=9000)), mock.patch.object(G, "HOTELS", G._hotel_search):
            _executives(SIX[:5] + casablanca)
            r, events = _instruction()
        fin = [e for e in events if e.get("type") == "group_done"][0]["text"]
        self.assertTrue(fin.startswith("5 of 6 booked (TEST)."), fin)
        self.assertEqual(fin.count("?"), 1, fin)                                           # ONE grouped question
        self.assertIn(casablanca[0], fin)
        self.assertIn("over the company's limit", fin)


class EveryMissingPassportIsInvited(unittest.TestCase):
    """08:01 (Tyler): every person without a passport gets the secure link by email AUTOMATICALLY — the count and the list from ONE
    source (the master list's own ✓), the new person included."""

    def test_on_the_instruction_and_for_a_new_person(self):
        from agapi import s2_keep as KEEP
        from booking_signer import traveller_vault as TV
        with W339.World() as w, mock.patch.object(G, "HOTELS", G._hotel_search), mock.patch.object(G, "INVITE", None):
            _executives(SIX)
            amara = next(m for m in w.members() if m["name"] == "Amara Sample")           # she has an email on the list
            run(KEEP.delete(amara["person_id"]))
            before = len(w.mails)
            r, events = _instruction()
            fin = [e for e in events if e.get("type") == "group_done"][0]["text"]
            mails = w.mails[before:]
            self.assertTrue(any("add your passport" in m for m in mails), mails)               # emailed, unasked
            self.assertIn("I've emailed 1 person their secure link for their passport (Amara Sample)", fin)
            self.assertNotIn("Amara Sample:", fin)                                              # never asked about
            self.assertTrue(fin.startswith("5 of 6 booked (TEST)."), fin)
            self.assertNotIn("?", fin)
            view = run(G.view(OWNER))
            self.assertEqual([x["name"] for x in view["rows"] if not x["vault"]["passport"]], ["Amara Sample"])   # the same ONE source
        src = (ROOT / "backend" / "booking_signer" / "groups.py").read_text()
        self.assertIn("await invite_missing(account, movement_id, only=links)", src)               # a new person: on going on the trip


class ARefusalIsTriedOnceMoreThenNamed(unittest.TestCase):
    """Found by the iPhone proof (10 Nov): Duffel refused two Vueling orders (upstream_refused) and the finish said "not booked just
    now". Inside the instruction: once more with a fresh fare (its own read-back, the same yes) — then, still refused, said plainly."""

    def test_once_more_then_said_plainly(self):
        with W339.World(W339.PricedAgAPI(refused={"Amara Sample"}, refused_twice={"Bruno Example"})) as w, mock.patch.object(G, "HOTELS", G._hotel_search):
            _executives(SIX)
            r, events = _instruction()
        fin = [e for e in events if e.get("type") == "group_done"][0]["text"]
        self.assertTrue(fin.startswith("5 of 6 booked (TEST)."), fin)                     # Amara: booked on the second try
        self.assertIn("Bruno Example: the airline refused the booking, twice", fin)       # Bruno: named, never "just now"
        self.assertNotIn("not booked just now", fin)
        self.assertTrue(fin.rstrip().endswith("?"), fin)                                  # the ONE question comes last


class OneSourceForMayIAct(unittest.TestCase):
    def test_no_per_step_permission_is_left(self):
        """Whole class: every group door goes through the mandate; the asks that waited for a second yes are gone."""
        src = (ROOT / "backend" / "agapi" / "v0.py").read_text()
        self.assertIn("M.carry_out(", src)
        self.assertNotIn("Nothing changes until they say yes (group_confirm)", src)
        self.assertNotIn("nothing is booked until they tap Yes", src)
        outcome = (ROOT / "backend" / "booking_signer" / "group_outcome.py").read_text()
        self.assertIn("M.carry_out(", outcome)                                             # the page's Book all: the same instruction
        groups = (ROOT / "backend" / "booking_signer" / "groups.py").read_text()
        self.assertNotIn('"Spain", "ES"', groups)                                          # one hotel search, never per person, never Spain
        book = (ROOT / "backend" / "booking_signer" / "group_book.py").read_text()
        self.assertNotIn('"country": "ES"', book)
        for words in ("when they're planned, say “book them all”", "Shall I go ahead"):
            self.assertNotIn(words, groups)

    def test_what_may_be_done_is_decided_in_one_place(self):
        self.assertTrue(M.wants_booking("Book all executives to London 15–17 December"))
        self.assertTrue(M.wants_booking("book them all"))
        self.assertFalse(M.wants_booking("plan a London trip for the executives, don't book yet"))
        self.assertFalse(M.wants_booking("plan a London trip for the executives"))


class TheFaceNeverCoversTheComposer(unittest.TestCase):
    def test_the_group_page_reads_at_phone_width_and_follows_book_all(self):
        page = (ROOT / "frontend" / "app" / "components" / "group" / "GroupView.tsx").read_text()
        self.assertIn("@media (max-width:640px){.gv-wide{display:none}.gv-cards{display:block}}", page)   # each person a card
        self.assertIn("data-person-card={p.id}", page)
        self.assertIn("j.status === 'preparing' || j.status === 'booking'", page)          # Book all = the chat's, its live line followed

    def test_the_floating_face_keeps_clear_of_the_input_and_send(self):
        s2 = (ROOT / "frontend" / "app" / "s2" / "S2App.tsx").read_text()
        self.assertIn("<footer data-face-clear", s2)                                       # the ONE composer, marked
        hello = (ROOT / "frontend" / "app" / "s2" / "S2Hello.tsx").read_text()
        self.assertIn("document.querySelector('[data-face-clear]')", hello)                # measured wherever she lands …
        self.assertIn("window.visualViewport", hello)                                      # … in the visible viewport (the keyboard open)


if __name__ == "__main__":
    unittest.main()
