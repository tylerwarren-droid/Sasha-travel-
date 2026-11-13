"""Sasha 385 · THE GROUP FINISH — ONE "so what" in the chat and ONE final report, traveller by traveller, from the ONE source (the master
list + the trip record's send record). KANOE_DECISIONS 13 Nov 15:12.

Found (Tyler's Yerevan demo, 13 Nov 15:07): a wall — "1 of 7 booked … Confirmations have been sent to each traveller's registered email
… Ana García and Carmen Castro: the airline hasn't confirmed yet … part of the trip is booked and the rest isn't" — only 6 of 7 named,
"sent to each traveller" while 1 of 7 was booked, no fix for the half-booked, then "Hey Sam, what can I help you with?" mid-flow.

THE CLASS, made impossible: 7 travellers in mixed states (+1 dropped from the list) → every one counted exactly once, the missing one
said, "emailed" only from the send record, the chat line within its template, the half-booked offered the fix, each itinerary once.

    cd backend && python -m unittest tests.test_s385_one_group_finish -v
"""
from __future__ import annotations

import asyncio
import inspect
import pathlib
import re
import unittest
from unittest import mock

from booking_signer import group_book as GB, group_outcome as GO, group_report as GR, groups as G
from tests import test_s332 as W

run = asyncio.run
OWNER = W.OWNER
BACKEND = pathlib.Path(__file__).resolve().parents[1]
COMPANY = "Acme Components (fictional)"   # the world's own company (its roster is the one state() reads)
#: name, email, the state the master list will hold
SEVEN = [("Ana García", "ana@example.test", "confirming"), ("Carmen Castro", "carmen@example.test", "confirming"),
         ("Elena Ortega", "elena@example.test", "incomplete"), ("Luis Pérez", "luis@example.test", "incomplete"),
         ("Marta Ruiz", "marta@example.test", "incomplete"), ("Javier Moreno", "javier@example.test", "booked"),
         ("Sofía Lago", None, "over limit")]
TEMPLATE = re.compile(r"^Yerevan, 15–20 Dec: \d+ of \d+ fully booked( · \d+ waiting on the airline)?( · \d+ need a new flight)?"
                      r"( · \d+ need a new hotel)?( · \d+ not booked)?( · \d+ missing from the list \([^)]*\))?\.$")


def _world(scenario, drop=None):
    with W.World() as w:
        async def go():
            await GO.run(OWNER, "person_add", {"rows": [{"name": n, "home_city": "Madrid", "role": "executive", **({"email": e} if e else {})}
                                                        for n, e, _ in SEVEN], "company": COMPANY})
            ids = [p["id"] for p in (await G.state(OWNER))["roster"]]
            await G.create_trip(OWNER, None, "Yerevan", "2026-12-15", "2026-12-20", None, ids)
            await G.planned(OWNER)
            real_view = G.view
            state = {n: s for n, _, s in SEVEN}

            async def view(account, mid=None):
                v = await real_view(account, mid)
                for r in v["rows"]:
                    r["status"] = state[r["name"]]
                    if r["status"] == "incomplete":
                        r.update(booked_parts=["stay"], record_why="upstream_refused", hotel="Hotel Ararat (test)")
                    if r["status"] == "booked":
                        r.update(references=["YRV123"], transport="MAD→EVN · 15 Dec", hotel="Hotel Ararat (test)")
                if drop:
                    v["rows"] = [r for r in v["rows"] if r["name"] != drop]
                return v
            sent = []

            async def send(msg):
                sent.append(msg)
                return {"sent": True}
            with mock.patch.object(G, "view", view), mock.patch("booking_signer.live_events.SEND", send), \
                    mock.patch.object(GB, "invoice", mock.AsyncMock(return_value={"number": "KAN-F36AD62B-TEST", "total": "€828.27"})):
                mid = next(m["id"] for m in await G.store().trips(OWNER) if m.get("destination") == "Yerevan")   # THIS trip (the world has others)
                return await scenario(mid, sent)
        return run(go())


class TheSoWhat(unittest.TestCase):
    def test_every_traveller_counted_once_within_the_template(self):
        async def s(mid, sent):
            return await GB.finish(OWNER, mid, [], [{"name": "Sofía Lago", "code": "over_limit"}])
        fin = _world(s)
        self.assertEqual(fin["line"], "Yerevan, 15–20 Dec: 1 of 7 fully booked · 2 waiting on the airline · 3 need a new flight · 1 not booked.")
        self.assertRegex(fin["line"], TEMPLATE)
        body = fin["line"].split(":", 1)[1]
        booked, total = (int(x) for x in re.search(r"(\d+) of (\d+) fully booked", body).groups())
        self.assertEqual(booked + sum(int(x) for x in re.findall(r"· (\d+) ", body)), total == 7 and 7)   # each exactly once, all 7
        self.assertEqual(fin["say"].count("?"), 1, fin["say"])                                    # ONE grouped question
        for gone in ("Confirmations have been sent", "sent to each", "invoice", "part of the trip is booked"):
            self.assertNotIn(gone, fin["say"])

    def test_the_half_booked_are_offered_the_fix(self):
        async def s(mid, sent):
            return await GB.finish(OWNER, mid, [], [])
        fin = _world(s)
        self.assertEqual(fin["question"]["ask"], "Rebook the 3 on the next flights?")
        self.assertEqual([c["title"] for c in fin["question"]["choices"]], ["Rebook them", "Release the hotels"])
        self.assertTrue(all(c["route"].startswith("say:") for c in fin["question"]["choices"]))
        self.assertIn("Elena Ortega, Luis Pérez and Marta Ruiz", fin["question"]["choices"][0]["route"])
        self.assertTrue(fin["card"]["read_back_id"].startswith("gfin_"))                        # a card with taps: rule 4 sees mid-flow

    def test_a_traveller_missing_from_the_list_is_said(self):
        async def s(mid, sent):
            return await GB.finish(OWNER, mid, [], [])
        fin = _world(s, drop="Ana García")
        self.assertIn("1 missing from the list (Ana García)", fin["line"])
        self.assertRegex(fin["line"], TEMPLATE)
        self.assertIn("of 7 fully booked", fin["line"])                                         # still 7: never silence


class TheReport(unittest.TestCase):
    def test_a_row_per_traveller_from_the_record(self):
        async def s(mid, sent):
            await GB.finish(OWNER, mid, [], [{"name": "Sofía Lago", "code": "over_limit"}])
            rep = await GR.report(OWNER, mid)
            return rep, sent, GR.page(rep)
        rep, sent, page = _world(s)
        rows = {r["name"]: r for r in rep["rows"]}
        self.assertEqual(sorted(rows), sorted(n for n, _, _ in SEVEN))                            # every one, once
        self.assertEqual(rows["Javier Moreno"]["emailed"], "yes")                                # from the send record
        self.assertEqual(rows["Javier Moreno"]["references"], ["YRV123"])
        self.assertEqual([m["to"] for m in sent], ["javier@example.test"])                       # only the fully booked one, their own
        self.assertIn("next flights", rows["Elena Ortega"]["fix"])                               # the half-booked: the fix
        self.assertIn("release the hotel", rows["Elena Ortega"]["fix"])
        self.assertIn("the airline refused the booking", rows["Elena Ortega"]["missing"])
        self.assertEqual(rows["Ana García"]["status"], "waiting on the airline")
        self.assertEqual(rows["Sofía Lago"]["missing"], "over the company's limit")
        for k in ("flight", "hotel", "status", "references", "emailed", "missing", "fix"):
            self.assertIn(k, rows["Ana García"])
        self.assertEqual(rep["invoice"]["number"], "KAN-F36AD62B-TEST")
        self.assertIn("<th>Itinerary emailed</th>", page)
        self.assertNotIn("<script", page)

    def test_each_itinerary_goes_once_and_sent_is_never_claimed_without_the_record(self):
        async def s(mid, sent):
            await GB.finish(OWNER, mid, [], [])
            await GB.finish(OWNER, mid, [], [])                                                   # the finish again (a re-run)
            return sent, await GR.sent_record(OWNER, mid)
        sent, rec = _world(s)
        self.assertEqual(len(sent), 1)                                                           # once
        self.assertEqual(len(rec), 1)

    def test_a_send_that_failed_is_never_emailed_yes(self):
        async def s(mid, sent):
            async def fail(msg):
                return {"sent": False, "why": "down"}
            with mock.patch("booking_signer.live_events.SEND", fail):
                await GB.finish(OWNER, mid, [], [])
            return await GR.report(OWNER, mid)
        rep = _world(s)
        self.assertEqual(next(r for r in rep["rows"] if r["name"] == "Javier Moreno")["emailed"], "no")

    def test_the_link_is_signed_and_dated(self):
        tok = GR.token("acct", "mv", now=1_000_000)
        self.assertEqual(GR.read_token(tok, now=1_000_100), ("acct", "mv"))
        self.assertIsNone(GR.read_token(tok[:-1] + ("0" if tok[-1] != "0" else "1"), now=1_000_100))   # tampered
        self.assertIsNone(GR.read_token(tok, now=1_000_000 + 31 * 86400))                               # expired


class OneSource(unittest.TestCase):
    def test_only_the_list_and_the_record(self):
        fin = inspect.getsource(GB.finish)
        for gone in ("Confirmations have been sent", "_confirmations(", "part of the trip is booked", "The invoice"):
            self.assertNotIn(gone, fin)
        self.assertIn("GR.buckets(rows)", fin)
        self.assertFalse(hasattr(GB, "_confirmations"))                                          # the second sender is gone
        self.assertIn("rules", inspect.getsource(GR.sent_record))                               # "emailed" = the trip's send record
        # (the greeting rule inside a running flow — S2App rule4 — is held by the frontend's prebuild: check-outcome-surfaces)


if __name__ == "__main__":
    unittest.main()
