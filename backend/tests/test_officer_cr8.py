"""CR 8 · the case officer's queue: five FICTIONAL EX-01 applications through the SAME checks a real file gets, sorted by
what needs attention; "return to applicant" RECORDS the exact list and sends nothing.

    cd backend && python -m unittest tests.test_officer_cr8 -v
"""
from __future__ import annotations

import unittest
from datetime import date
from unittest import mock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from products import routes as PR, store as ST
from products.relocation import checker as CK, officer as O
import asyncio


def run(c):
    return asyncio.run(c)     # a fresh loop each time: these tests never depend on another test's loop

TODAY = date(2026, 10, 3)


class Queue(unittest.TestCase):
    def test_the_counts_come_from_the_checker_not_from_the_page(self):
        bruno = next(a for a in O.queue(TODAY) if a["id"] == "A-1042")
        self.assertEqual(bruno["counts"], {"problem": 2, "missing": 2, "check": 0})
        self.assertIn("postcode 08010 is in Barcelona, but the province written is Madrid", [i["why"] for i in bruno["items"]])
        fixed = {**O.APPLICATIONS[0], "base": {**O.APPLICATIONS[0]["base"], "address_postcode": "28010"}}
        self.assertEqual(O.assess(fixed, TODAY)["counts"]["problem"], 0)     # correct the file → the problem goes, by itself

    def test_each_existing_check_appears(self):
        whys = " ".join(i["why"] for a in O.queue(TODAY) for i in a["items"])
        self.assertIn("fails its control letter", whys)                      # NIE (checker)
        self.assertIn("may not fit this box on paper", whys)                 # text too long (checker)
        self.assertIn("LESS than a year", whys)                              # passport validity (the consulate's checklist)
        self.assertIn("Medical certificate from a registered doctor", whys)  # a missing document (the checklist, verbatim)
        self.assertTrue(all(a["left_for_applicant"] == 8 for a in O.queue(TODAY)))   # signature, consent, intent: theirs

    def test_most_attention_first_and_one_complete(self):
        q = O.queue(TODAY)
        self.assertEqual([a["id"] for a in q], ["A-1042", "A-1044", "A-1043", "A-1045", "A-1046"])
        self.assertEqual([a["status"] for a in q], ["return", "return", "return", "return", "complete"])
        self.assertEqual(q[-1]["items"], [])

    def test_no_percentage_anywhere(self):
        self.assertNotIn("%", str(O.queue(TODAY)))
        self.assertNotIn("%", O.return_message(O.queue(TODAY)[0]))

    def test_the_message_is_the_list_word_for_word(self):
        a = O.queue(TODAY)[0]
        m = O.return_message(a)
        for i in a["items"]:
            self.assertIn(f"{i['field']}: {i['why']}", m)
        self.assertIn("Section 5, the Dehú consent and the signature remain yours to complete.", m)


class Routes(unittest.TestCase):
    def setUp(self):
        self.saved = ST.STORE
        ST.STORE = ST.MemoryCaseStore()
        self.cid = run(ST.STORE.put("relocation", "11111111-1111-4111-8111-111111111111", "showcase",
                                    {"kind": "officer_queue", "showcase": True, "fictional": True, "returned": {}}))
        app = FastAPI(); app.include_router(PR.router)
        self.c = TestClient(app)

    def tearDown(self):
        ST.STORE = self.saved

    def test_queue_return_records_and_sends_nothing(self):
        j = self.c.get(f"/products/relocation/officer/{self.cid}").json()
        self.assertEqual((len(j["applications"]), j["sends"], j["kind"]), (5, False, "click-through"))
        r = self.c.post(f"/products/relocation/officer/{self.cid}/return/A-1042").json()
        self.assertFalse(r["sent"])
        self.assertIn("postcode 08010 is in Barcelona", r["returned"]["message"])
        again = self.c.post(f"/products/relocation/officer/{self.cid}/return/A-1042").json()
        self.assertEqual(again["returned"]["at"], r["returned"]["at"])                  # recorded once
        j = self.c.get(f"/products/relocation/officer/{self.cid}").json()
        self.assertEqual(next(a for a in j["applications"] if a["id"] == "A-1042")["returned"]["at"], r["returned"]["at"])

    def test_a_complete_application_has_nothing_to_return(self):
        self.assertEqual(self.c.post(f"/products/relocation/officer/{self.cid}/return/A-1046").status_code, 409)
        self.assertEqual(self.c.post(f"/products/relocation/officer/{self.cid}/return/A-9999").status_code, 404)

    def test_only_an_officer_case_serves_the_queue(self):
        other = run(ST.STORE.put("relocation", "11111111-1111-4111-8111-111111111111", "k", {"rows": []}))
        self.assertEqual(self.c.get(f"/products/relocation/officer/{other}").status_code, 404)
