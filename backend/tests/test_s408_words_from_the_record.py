"""Sasha 408 · SASHA'S WORDS COME FROM THE RECORD (P0; EU 309 findings 1 and 2).

The live case (Tyler, /s2, 26 Nov 06:54 UTC): "Wellness Boutique Experience", Fri 27 Nov 12:00, 1 person — she said "their form asks you to
prove you're human, so I've filled it in for you" over six Copy buttons; nothing was filled (AgAPI's prepare recorded no form schema and carried
nothing into their page). Sasha decided "filled" from bool(prep), said fixed sentences ("Done — it's on your screen", "their page is filled
in", voice.NOT_FILLED), and AgAPI's phrasebook line whatever its prepare recorded. Same class: "Nothing is booked yet" with no record read, and
booked workers shown "planned" when the group record wasn't read (reconcile returned {}).

THE CLASS: every sentence about a booking's state — filled, a human check, booked, nothing booked — is read from the record, by ONE writer
(agapi/booking_words); unread is said as unread. Any venue, any door.

    cd backend && python -m unittest tests.test_s408_words_from_the_record -v
"""
from __future__ import annotations

import inspect
import pathlib
import re
import unittest

from agapi import booking_words as BW

BACKEND = pathlib.Path(__file__).resolve().parents[1]
#: the live case's prepare, as AgAPI's record holds it: no form schema, nothing carried, the fields to copy
SPA = {"prepared_id": "vpr_x", "link": "https://agapi.example/prepared/x", "form": None, "human_step": "book on their page",
       "fills": [{"field": "name", "role": "name"}, {"field": "date", "role": "date"}, {"field": "time", "role": "time"}],
       "decision": {"channel": {"kind": "form", "captcha": True}}}


class TheRecordSaysIt(unittest.TestCase):
    def test_the_live_case_is_never_called_filled(self):
        f = BW.facts(SPA)
        self.assertEqual(f["filled"], [])
        line = BW.handover_line("Wellness Boutique Experience", f)
        self.assertNotIn("filled in", line)
        self.assertIn("to copy in", line)
        self.assertIn("prove you're human", line)                                        # AgAPI's record names a check: said as ITS (FOR CR)
        self.assertNotIn("prove", BW.handover_line("X", BW.facts({**SPA, "decision": {"channel": {"kind": "form"}}})))   # none: never said
        self.assertIn("filled in", BW.handover_line("X", BW.facts({**SPA, "hand_over": {"carried": ["date", "party"]}})))   # carried: said

    def test_status_words_read_the_row(self):
        self.assertIn("ready to copy", BW.status_words({"filled": False}))
        self.assertIn("filled in", BW.status_words({"filled": True}))
        self.assertNotIn("filled", BW.status_words({}))                                     # an older row: no fill claimed


#: the doors' line writers — none may hold a fixed fill / human-check / state sentence of its own
DOORS = ("agapi/venues.py", "app/agent/voice.py", "agapi/s2_status.py", "agapi/itinerary.py", "booking_signer/guest_whatsapp.py",
         "booking_signer/group_book.py", "booking_signer/groups.py", "app/agent/sasha.py", "booking_signer/wa_agent.py")
CLAIM = re.compile(r"filled in|filled it|page is filled|prove you.re human|Everything's filled|Done — it's on your screen", re.I)


def literals(src: str):
    code = "\n".join(l.split("#", 1)[0] for l in src.splitlines())
    code = re.sub(r'"""[\s\S]*?"""', "", code)                                                # docstrings say what happened; not lines
    return re.findall(r'"(?:[^"\\\n]|\\.)*"', code)


class Ratchet(unittest.TestCase):
    def test_no_door_writes_a_fill_or_human_check_of_its_own(self):
        for rel in DOORS:
            hits = [s for s in literals((BACKEND / rel).read_text()) if CLAIM.search(s)]
            self.assertEqual(hits, [], f"{rel}: a booking-state sentence not read from the record — booking_words writes it")

    def test_no_page_states_a_booking_it_didnt_read(self):
        fe = BACKEND.parent / "frontend"
        claim = re.compile(r"Nothing is booked|filled in for you|Everything's filled|so I've filled it", re.I)
        for p in list((fe / "app").rglob("*.tsx")) + list((fe / "lib").rglob("*.ts")):
            if "node_modules" in p.parts:
                continue
            code = re.sub(r"/\*[\s\S]*?\*/", "", p.read_text())
            code = "\n".join(l.split("//", 1)[0] for l in code.splitlines())
            self.assertNotRegex(code, claim, p.as_posix())

    def test_filled_is_the_records_never_a_result_existing(self):
        from agapi import venues as VN
        src = inspect.getsource(VN._book_inner)
        self.assertNotIn("filled = bool(prep)", src)
        self.assertIn('filled = bool(fx["filled"])', src)
        self.assertIn("BW.handover_line(", src)

    def test_unread_is_said_as_unread(self):
        from booking_signer import group_book as GB, groups as G
        rec = inspect.getsource(GB.reconcile)
        self.assertNotRegex(rec, r"_agapi_reachable\(account\):\s*\n\s*return \{\}")       # unreachable → Unread, never {}
        self.assertIn("raise Unread(", rec)
        self.assertIn('view.get("record_unread")', inspect.getsource(GB.booked_line))
        self.assertIn('"not read yet" if unread', inspect.getsource(G.view))


if __name__ == "__main__":
    unittest.main()
