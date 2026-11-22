"""Sasha 399 · A CONFIRMATION LANDS ON THE ACT IT BELONGS TO (root test: mailbox row 2111; FOR CR: row 2112).

Measured (Tyler's real 19 Nov booking — La Taberna de Peñalver, BARRIO SALAMANCA, 2 people, 21:45): AgAPI's record holds it right
(listing ChIJnx_fKOApQg0RlDK1xQwDUBI) but "failed"; no confirmation was matched at all. Three acts that evening at 21:45 carry "La
Taberna de Peñalver" — two at Barrio Salamanca (a retry), one at Cava Baja — and two of Sasha's three confirmation matchers took the
FIRST that looked near (venue_submit.attach_from_mail, mailbox.match). An unmatched forward was said, then dropped.

THE CLASS: every matcher (a forward or paste · Sasha's own address and number · the Gmail reader for the ladder's bookings · the Gmail
reader for AgAPI's acts) × one fits / several fit / none fits → exactly one booking, or NONE (held and said); a RATCHET: nothing writes
a venue, date or time onto an act copy but its creation and AgAPI's record.

    cd backend && python -m unittest tests.test_s399_confirmation_on_its_act -v
"""
from __future__ import annotations

import asyncio
import pathlib
import re
import unittest
from datetime import datetime, timezone
from unittest import mock

from agapi import s2_memory as MEM, s2_status as ST, venue_submit as VS
from booking_signer import mailbox as MB, one_booking as OB, proactive as PR, written as W

BACKEND = pathlib.Path(__file__).resolve().parents[1]
ACCT = "00000000-0000-4000-8000-000000000399"
NOW = datetime(2037, 11, 19, 15, 0, tzinfo=timezone.utc)

#: the three acts of 19 Nov 21:45, as Sasha keeps them (fictional account; Tyler's venues and times)
SALAMANCA = {"act_id": "act_sal", "route": "platform", "venue": "La Taberna de Peñalver", "when": "2037-11-19T21:45", "party": 2,
             "place_id": "ChIJnx_fKOApQg0RlDK1xQwDUBI"}
SAL_RETRY = {**SALAMANCA, "act_id": "act_sal_retry"}
CAVA_BAJA = {"act_id": "act_cava", "route": "platform", "venue": "La Taberna de Peñalver Cava Baja | Restaurante La Latina",
             "when": "2037-11-19T21:45", "party": 2, "place_id": "ChIJvVxOe_cnQg0RgAIhtCFzZx4"}
MAIL = {"via": "CoverManager", "venue": "La Taberna de Peñalver", "at": "2037-11-19T21:45", "party": 2}


def run(c):
    return asyncio.run(c)


class Kinds(unittest.TestCase):
    """The one conversation record's kinds (production: its database row), stood in by a dict."""

    def setUp(self):
        self.kinds: dict = {}

        async def put_kind(account, name, value):
            self.kinds[(account, name)] = value
            return True

        async def kind(account, name):
            return self.kinds.get((account, name))
        for p in (mock.patch.object(MEM, "put_kind", put_kind), mock.patch.object(MEM, "kind", kind)):
            p.start()
            self.addCleanup(p.stop)

    def acts(self, *acts):
        VS._ACTS[ACCT] = [dict(a) for a in acts]
        self.kinds[(ACCT, "venue_acts")] = VS._ACTS[ACCT]
        self.addCleanup(VS._ACTS.pop, ACCT, None)


class TheOneRule(unittest.TestCase):
    def test_one_fits_several_fit_none_fits(self):
        key = lambda r: r["id"]
        self.assertEqual(OB.decide([("ref", [{"id": 1}])], key)[:2], ({"id": 1}, "ref"))
        got, why, ok = OB.decide([("ref", []), ("venue", [{"id": 1}, {"id": 2}]), ("day", [{"id": 1}])], key)
        self.assertEqual((got, ok), (None, False))
        self.assertIn("not guessed", why)                                                  # several: never the first, never the next tier
        self.assertEqual(OB.decide([("ref", []), ("venue", [])], key)[:1], (None,))        # none


class AgAPIsActs(Kinds):
    def attach(self, facts):
        return run(VS.attach_from_mail(ACCT, facts, None))

    def test_tylers_evening_is_held_never_the_nearest_looking_act(self):
        self.acts(SALAMANCA, SAL_RETRY, CAVA_BAJA)
        act, why = self.attach(MAIL)
        self.assertIsNone(act)
        self.assertIn("not guessed", why)
        self.assertFalse(any(a.get("confirmed_by_mail") for a in VS._ACTS[ACCT]))           # nothing written onto any act

    def test_exactly_one_act_fits_its_reference_or_its_venue_at_its_time(self):
        self.acts(SALAMANCA, CAVA_BAJA)
        self.assertIsNone(self.attach(MAIL)[0])                                            # both named "La Taberna de Peñalver"
        self.assertIsNone(self.attach({**MAIL, "venue": "La Taberna de Peñalver Cava Baja"})[0])   # the bare name fits it too: held
        lhardy = {**SALAMANCA, "act_id": "act_lhardy", "venue": "Lhardy", "place_id": "p_lhardy"}
        self.acts(lhardy, CAVA_BAJA)
        act, basis = self.attach({**MAIL, "venue": "La Taberna de Peñalver Cava Baja"})
        self.assertEqual((act["act_id"], basis), ("act_cava", "the venue at its time"))
        self.acts({**SALAMANCA, "reference": "CM-7781"}, CAVA_BAJA)
        act, basis = self.attach({**MAIL, "reference": "cm-7781"})
        self.assertEqual((act["act_id"], basis), ("act_sal", "reference"))
        self.assertEqual((act["venue"], act["when"], act["party"]), (SALAMANCA["venue"], SALAMANCA["when"], 2))   # terms untouched

    def test_another_party_or_time_is_not_that_act(self):
        self.acts(SALAMANCA)
        self.assertEqual(self.attach({**MAIL, "party": 4}), (None, ""))
        self.assertEqual(self.attach({**MAIL, "at": "2037-11-20T21:45"}), (None, ""))


class TheLaddersBookings(unittest.TestCase):
    ROWS = [{"id": "ti_1", "venue": "La Taberna de Peñalver", "date": "2037-11-19", "time": "21:45", "status": "link_sent"},
            {"id": "ti_2", "venue": "La Taberna de Peñalver Cava Baja", "date": "2037-11-19", "time": "21:30", "status": "link_sent"}]

    def test_several_fit_is_said_never_the_first(self):
        row, why = MB.match({"venue": "Taberna Peñalver", "at": "2037-11-19T21:45"}, self.ROWS)
        self.assertIsNone(row)
        self.assertIn("not guessed", why)
        self.assertEqual(MB.match({"venue": "Taberna Peñalver Cava Baja", "at": "2037-11-19T21:30"}, self.ROWS)[0]["id"], "ti_2")
        self.assertEqual(MB.match({"venue": "Casa Lucio", "at": "2037-11-19T21:30"}, self.ROWS), (None, None))   # none: outside Sasha

    def test_one_platform_day_link_only_when_it_is_the_only_one(self):
        f = {"via": "Booksy", "venue": "", "at": "2037-11-19T10:30"}
        self.assertIsNone(MB.match(f, self.ROWS)[0])                                        # two open links that day: held
        self.assertEqual(MB.match(f, self.ROWS[:1])[0]["id"], "ti_1")


class HeldAndSaid(Kinds):
    def test_a_forward_that_names_no_one_booking_is_held_and_said(self):
        st = mock.Mock()
        st.written_candidates = mock.AsyncMock(return_value=[
            {"trip_item_id": "ti_1", "venue": "La Taberna de Peñalver", "date_time": NOW, "local_timezone": "Europe/Madrid"},
            {"trip_item_id": "ti_2", "venue": "La Taberna de Peñalver", "date_time": NOW, "local_timezone": "Europe/Madrid"}])   # a retry
        body = "Your reservation at La Taberna de Peñalver is confirmed for Thursday 19 November 2037 at 21:45, 2 people."
        from booking_signer import inbound_phone as IP
        with mock.patch.object(IP, "STORE", st):
            self.assertIsNone(run(W.file("wa-fwd-1", "whatsapp", None, None, body, NOW, account=ACCT, forwarded=True)))
        held = run(W.held(ACCT, NOW))
        self.assertEqual([(h["id"], h["channel"]) for h in held], [("wa-fwd-1", "whatsapp")])
        self.assertNotIn("venue", held[0])                                                  # its words only — no venue, date or time taken
        self.assertIn("kept it aside", ST.UNMATCHED.format(n=1, s=""))
        src = (BACKEND / "agapi/s2_status.py").read_text()
        self.assertIn('"unmatched_line"', src)                                              # get_status says it
        self.assertIn("kept it aside as unmatched", (BACKEND / "booking_signer/guest_whatsapp.py").read_text())

    def test_the_gmail_reader_holds_what_several_fit(self):
        src = (BACKEND / "booking_signer/mailbox.py").read_text()
        self.assertEqual(src.count("await W.hold("), 2)                                     # the ladder's and AgAPI's acts
        self.assertNotIn('"match_basis": "agapi_act"', src)                                 # the table refused it: no find was ever kept


class TheBriefSaysEachState(unittest.TestCase):
    def test_never_not_confirmed_yet_for_a_page_handed_over_or_a_failed_press(self):
        items = [{"time": "21:45", "venue": "La Taberna de Peñalver", "status": "link_sent",
                  "status_words": ST.WORDS["prepared"]},
                 {"time": "14:00", "venue": "Casa Gate", "status": "failed", "status_words": ST.WORDS["failed"]},
                 {"time": "20:00", "venue": "Lhardy", "status": "confirmed"}]
        line = PR.render("morning_brief", items[0], {"items": items})
        self.assertNotIn("not confirmed yet", line)
        self.assertIn("La Taberna de Peñalver (prepared, not booked", line)
        self.assertIn("Casa Gate (not booked)", line)
        self.assertIn("Lhardy (confirmed)", line)


#: Sasha 399 · the ONLY places an act copy's venue / date / time (venue_acts: "venue", "when", "party") is written: its creation from
#: the send (venue_submit._remember) and AgAPI's record (venue_submit.bookings' write-back). Every other writer adds pointers only.
TERMS = ("venue", "when", "party")
WRITERS_OF_TERMS = {"_remember", "bookings"}


class Ratchet(unittest.TestCase):
    def test_no_venue_date_or_time_written_onto_an_act_but_by_its_record(self):
        src = (BACKEND / "agapi/venue_submit.py").read_text()
        funcs = re.split(r"\n(?=async def |def )", src)
        for f in funcs:
            name = (re.match(r"(?:async )?def (\w+)", f) or [None, None])[1]
            if name in WRITERS_OF_TERMS or name is None:
                continue
            for k in TERMS:   # a key literal set on an act (kw / update / dict merge), outside the two writers
                self.assertNotRegex(f, rf"kw\[\"{k}\"\]\s*=|\.update\(\s*\{{\s*\"{k}\"|_amend\([^)]*\b{k}\s*=", (name, k))
        for p in [*(BACKEND / "agapi").rglob("*.py"), *(BACKEND / "booking_signer").rglob("*.py")]:
            for m in re.finditer(r"_amend\(([^)]*)\)", p.read_text()):
                self.assertNotRegex(m.group(1), r"\b(?:venue|when|party|date|time)\s*=", f"{p.name}: {m.group(0)}")

    def test_the_written_matcher_sets_an_outcome_never_terms(self):
        src = (BACKEND / "booking_signer/written.py").read_text()
        self.assertNotRegex(src, r"(?i)update\s+trip_items\s+set[^\"']*(date_time|provider_name|location_name|party_size)")
        for f in ("booking_signer/written.py", "booking_signer/mailbox.py", "agapi/venue_submit.py"):
            self.assertIn("one_booking import decide", (BACKEND / f).read_text(), f)          # one rule, every matcher


if __name__ == "__main__":
    unittest.main()
