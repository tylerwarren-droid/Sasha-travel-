"""Sasha 394 (2) · 382 + 387(b) · a trip's to-dos are Pacioli's, only that trip's, one to-do per open finding (root test: mailbox row 2069).

Measured: Sasha had no finding record or picker; the 18 Nov "dinner" sentence was the model's own (closed at the root by 392 + 393). CR 198
(agapi-live b8ea1634, contract 1.98.0) is the ONE checker: trip.check by movement, ONE finding shape, its own trip-level say.

THE CLASS: two movements on one organiser (Yerevan + another trip), findings on both — one with its official form, one not checked —
× every surface (S2's card, WhatsApp's lines) → ONLY the trip in talk, ONLY its open findings, ONE to-do each, who and form as Pacioli
gave them; "not checked" never becomes "nothing needed"; AgAPI not answering is never "nothing to sort"; no vault value is ever passed
(Tyler, 20 Nov: Keep references only — FOR CR); an organiser is never offered a second path to requirements (entry_documents).

    cd backend && python -m unittest tests.test_s394_trip_findings -v
"""
from __future__ import annotations

import asyncio
import pathlib
import re
import unittest
from unittest import mock

from app.agent import tool_need as TN
from booking_signer import group_book as GB, groups as G, trip_findings as TF, wa_agent as WA
from booking_signer import guest_whatsapp as GW
from kanoe_contract import OP

BACKEND = pathlib.Path(__file__).resolve().parents[1]
YEREVAN, DINNER = "mv_yerevan_394", "mv_dinner_394"
FORM = {"official_url": "https://www.gov.am/en/evisa", "prepare": {"operation": "entry.prepare", "input": {"country": "AM"}},
        "stops_at": ["sign or declare", "pay", "CAPTCHA", "submit"]}


def f(trip, say, who="organiser", status="open", form=None, traveller=None, kind="inconsistency"):
    return {"trip": trip, "traveller": traveller, "booking": None, "kind": kind, "rule_id": "r", "source": "AgAPI's booking record",
            "as_of": "2026-11-20", "needed": "x", "who": who, "form": form, "status": status, "say": say}


#: Pacioli's answer, as if a run had findings of BOTH trips (the picker must keep only the trip in talk — the finding's own identity)
ANSWER = {"trip_id": YEREVAN, "version": "trip-check/1", "checked_at": "2026-11-20T10:00:00", "say": "2 things to sort on this trip; 1 not checked yet.",
          "counts": {"open": 2, "not_checked": 1},
          "findings": [f(YEREVAN, "Ani's stay starts 16 Dec but she lands 15 Dec at 23:30: the night of 15 Dec isn't booked."),
                       f(YEREVAN, "Ani needs an Armenian e-visa.", who="traveller", form=FORM, traveller="m_ani", kind="requirement"),
                       f(YEREVAN, "Not checked: Rafael's documents.", who="the door", status="not_checked", traveller="m_raf"),
                       f(DINNER, "Both confirmations say Sunday 15 November, which has already passed.")]}


def run(c):
    return asyncio.get_event_loop().run_until_complete(c) if not asyncio.get_event_loop().is_closed() else asyncio.run(c)


class OnlyThisTripsOpenFindings(unittest.TestCase):
    def setUp(self):
        asyncio.set_event_loop(asyncio.new_event_loop())

    def test_the_picker_keeps_the_trip_in_talk_and_its_open_findings(self):
        t = TF.pick(ANSWER, YEREVAN, {"m_ani": "Ani", "m_raf": "Rafael"})
        says = [d["say"] for d in t["todos"]]
        self.assertEqual(len(says), 2)                                                # one to-do per OPEN finding of THIS trip
        self.assertFalse(any("Sunday 15 November" in s for s in says))               # never another trip's ("the dinner sentence")
        self.assertFalse(any(s.startswith("Not checked") for s in says))            # not checked: AgAPI's say carries it
        self.assertIn("not checked", t["say"])
        self.assertEqual(t["not_checked"], 1)
        visa = next(d for d in t["todos"] if d["who"] == "traveller")
        self.assertEqual((visa["for"], visa["form"]["link"], visa["form"]["prepared"]), ("Ani", FORM["official_url"], True))
        self.assertEqual(visa["form"]["you_only"], FORM["stops_at"])                 # the person does only their own step
        self.assertEqual(next(d for d in t["todos"] if d["who"] == "organiser")["for"], "you")
        other = TF.pick(ANSWER, DINNER)
        self.assertEqual([d["say"] for d in other["todos"]], ["Both confirmations say Sunday 15 November, which has already passed."])

    def call(self, answer):
        sent = []

        async def send(account, op, body, idem, approval=None):
            sent.append((op, body))
            return answer
        with mock.patch.object(GB, "_send", send), mock.patch.object(GB, "_organiser", mock.AsyncMock(return_value="eu_org")):
            got = run(TF.of_trip("acct394", YEREVAN, {"m_ani": "Ani"}))
        return got, sent

    def test_the_one_caller_reads_this_movement_and_passes_no_vault(self):
        got, sent = self.call({"ok": True, "result": ANSWER})
        self.assertEqual(sent, [(OP.TRIP_CHECK, {"trip_id": YEREVAN, "end_user": "eu_org", "travellers": []})])   # Keep refs only: FOR CR
        self.assertEqual(len(got["todos"]), 2)

    def test_unreachable_is_never_nothing_to_sort_and_nothing_booked_is_nothing_shown(self):
        got, _ = self.call({"ok": False, "error": {"code": "upstream_unreachable"}})
        self.assertEqual((got["todos"], got["say"], got.get("unchecked")), ([], TF.UNCHECKED, True))
        self.assertNotRegex(TF.UNCHECKED, r"(?i)nothing (?:needed|to sort)")
        got, _ = self.call({"ok": False, "error": {"code": "not_found"}})
        self.assertIsNone(got)


class EverySurface(unittest.TestCase):
    def setUp(self):
        asyncio.set_event_loop(asyncio.new_event_loop())

    def card(self):
        view = {"movement": {"id": YEREVAN, "company": "Acme", "destination": "Yerevan"},
                "rows": [{"member_id": "m_ani", "name": "Ani", "status": "booked", "price_eur": 410.0},
                         {"member_id": "m_raf", "name": "Rafael", "status": "booked", "price_eur": 390.0}], "counts": {"booked": 2}}
        seen = {}

        async def of_trip(account, mid, names):
            seen["mid"] = mid
            return TF.pick(ANSWER, mid, names)
        with mock.patch.object(G, "view", mock.AsyncMock(return_value=view)), mock.patch.object(TF, "of_trip", of_trip):
            c = run(G.card("acct394"))
        self.assertEqual(seen["mid"], YEREVAN)
        return c

    def test_s2s_card_carries_this_trips_todos_and_pacioli_s_say(self):
        c = self.card()
        self.assertEqual(len(c["todos"]), 2)
        self.assertEqual(c["check"], ANSWER["say"])
        self.assertIn(ANSWER["say"], c["say"])
        self.assertNotIn("Sunday 15 November", str(c))

    def test_whatsapp_lines_say_each_todo_and_its_form(self):
        out = GW.Out()
        WA.render({"kind": "group_list", **self.card()}, out, {}, None)
        text = "\n".join(str(i[1]) for i in out.items)
        self.assertIn("To do (you): Ani's stay starts 16 Dec", text)
        self.assertIn(f"To do (Ani): Ani needs an Armenian e-visa. Official form: {FORM['official_url']}", text)
        self.assertIn("they only sign or declare, pay, CAPTCHA, submit", text)
        self.assertNotIn("Sunday 15 November", text)


class Ratchets(unittest.TestCase):
    def test_only_trip_findings_calls_the_checker(self):
        hits = [str(p.relative_to(BACKEND)) for d in ("agapi", "app", "booking_signer", "products") for p in (BACKEND / d).rglob("*.py")
                if re.search(r"OP\.TRIP_CHECK|[\"']trip\.check[\"']", p.read_text())]
        self.assertEqual(hits, ["booking_signer/trip_findings.py"])

    def test_an_organiser_is_never_offered_a_second_path_to_requirements(self):
        tools = [{"name": n} for ns in TN.FAMILIES.values() for n in ns]
        for said in ("does Ani need a visa for Armenia?", "what entry documents do they need?", "prepare the e-visa form"):
            offered = {t["name"] for t in TN.select(tools, said, [], organiser=True)}
            self.assertFalse(offered & {"entry_documents", "prepare_entry"}, said)
            self.assertIn("group_list", offered)
        self.assertIn("entry_documents", {t["name"] for t in TN.select(tools, "do I need a visa for Japan?", [])})   # outside a group: FOR CR


if __name__ == "__main__":
    unittest.main()
