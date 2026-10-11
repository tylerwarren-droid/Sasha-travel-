"""CR 78 · /s2's accident: the facts given in chat reach AgAPI under its own keys; an open case is never restarted by a later fact;
a claim works without the card named first; claim deadlines are never offered for a calendar. Offline (a stand-in AgAPI).

    cd backend && python -m unittest tests.test_s2_accident_cr78 -v
"""
from __future__ import annotations

import unittest

from agapi import s2_fine_print as FP
from tests.test_s2_fine_print import CARDS, Ctx, FinePrint, run

SAID = "14:00, Rotunda do Marquês, AA-00-ZZ"


class AccidentCR78(FinePrint):
    def steps(self):
        return [b for op, b in self.agapi.calls if op == "cards.accident_step"]

    def test_the_facts_in_chat_go_to_agapi_under_its_own_keys(self):
        run(FP.run_tool(Ctx(), "accident", {"country": "PT", "place": "Lisbon", "rental_company": "Example Rentals"}))
        run(FP.run_tool(Ctx(said=SAID), "accident", {"facts": {"time": "14:00", "place": "Rotunda do Marquês", "other_vehicle_plate": "AA-00-ZZ"}}))
        self.assertEqual(self.steps()[-1]["facts"], {"time": "14:00", "place": "Rotunda do Marquês", "other_vehicle": {"plate": "AA-00-ZZ"}})

    def test_a_later_place_never_restarts_the_case(self):
        run(FP.run_tool(Ctx(), "accident", {"country": "PT", "place": "Lisbon", "rental_company": "Example Rentals"}))
        run(FP.run_tool(Ctx(said=SAID), "accident", {"country": "PT", "place": "Rotunda do Marquês", "facts": {"other_vehicle_plate": "AA-00-ZZ"}}))
        self.assertEqual([op for op, _ in self.agapi.calls].count("cards.accident_start"), 1)
        self.assertEqual(self.steps()[-1]["facts"]["place"], "Rotunda do Marquês")

    def test_the_time_they_typed_is_kept_when_the_model_leaves_it_out(self):
        self.assertEqual(FP.agapi_facts({"other_vehicle_plate": "AA-00-ZZ"}, SAID), {"other_vehicle": {"plate": "AA-00-ZZ"}, "time": "14:00"})
        self.assertNotIn("other_vehicle", FP.agapi_facts({}, SAID))          # a plate is never guessed from the words
        self.assertEqual(FP.agapi_facts({"time": "2pm"}, ""), {})            # AgAPI's HH:MM only

    def test_facts_given_when_starting_go_with_the_start(self):
        run(FP.run_tool(Ctx(said=SAID), "accident", {"country": "PT", "place": "Rotunda do Marquês", "facts": {"other_vehicle_plate": "AA-00-ZZ"}}))
        start = [b for op, b in self.agapi.calls if op == "cards.accident_start"][-1]
        self.assertEqual(start["facts"], {"other_vehicle": {"plate": "AA-00-ZZ"}, "time": "14:00"})
        self.assertNotIn("card_item_id", start)                              # no card named: none guessed

    def test_a_claim_without_the_card_named_first_asks_which(self):
        run(FP.run_tool(Ctx(), "accident", {"country": "PT", "place": "Lisbon", "rental_company": "Example Rentals"}))
        r = run(FP.run_tool(Ctx(), "file_claim", {}))
        self.assertEqual((r["result"]["status"], r["result"]["ask"]), ("which_card", "Which card did you pay the rental with?"))
        self.assertEqual(r["result"]["cards"], ["Example Bank Travel Visa", "Example Bank Everyday Mastercard"])     # from My cards
        run(FP.run_tool(Ctx(said="my travel visa"), "accident", {"card": "travel visa"}))
        self.assertEqual(self.steps()[-1]["card_item_id"], CARDS[0]["item_id"])

    def test_the_step_that_asks_for_the_card_is_said(self):
        real = self.agapi.__call__

        async def call(op, body, approval=None):
            r = await real(op, body, approval)
            if op == "cards.accident_step":
                r["result"].update(step="clocks", ask_card={"say": "Which card did you pay the rental with?",
                                                            "cards": [{"item_id": c["item_id"], "issuer": c["issuer"], "product": c["product"], "masked": c["masked"]} for c in CARDS]})
            return r
        FP.CALL = call
        run(FP.run_tool(Ctx(), "accident", {"country": "PT", "rental_company": "Example Rentals"}))
        r = run(FP.run_tool(Ctx(), "accident", {"answer": "done"}))
        self.assertEqual(r["result"]["ask"], "Which card did you pay the rental with?")
        self.assertIn("Never offer to put these dates in a calendar", r["result"]["how"])

    def test_no_calendar_for_a_claim_deadline(self):
        from app.agent import s2
        self.assertIn("she never offers to put a claim's", open(s2.__file__).read())
        self.assertIn("never offered for a calendar", next(t for t in FP.TOOLS if t["name"] == "accident")["description"])


if __name__ == "__main__":
    unittest.main()


class MoneyBackCR78(FinePrint):
    """CR 78 · money back on /s2: the check's own words; the claim read back first, filed only on the yes in a later turn."""

    def setUp(self):
        super().setUp()
        from unittest import mock
        p = mock.patch.dict(FP._MONEY, {}, clear=True)
        p.start()
        self.addCleanup(p.stop)
        real = self.agapi.__call__

        async def call(op, body, approval=None):
            self.agapi.calls.append((op, body))
            if op == "money.flight_check":
                return {"ok": True, "result": {"case_id": "mny_" + "1" * 26, "verdict": "yes", "amount": {"amount_minor": 25000, "currency": "EUR"},
                                               "rules": [{"rule": "compensation_short", "quotes": [{"quote": "a) 250 euros para vuelos de hasta 1 500 kilómetros;"}]}],
                                               "say": "Your flight EX123 (1,246 km) is covered: under EU rules you may be owed EUR 250. Want me to claim it?"}}
            if op == "money.flight_claim":
                if not approval:
                    return {"ok": False, "error": {"code": "approval_required", "details": {"read_back_id": "rb_mny", "read_back": {"lines": [
                        "File a compensation claim with Example Air at claims@example-air.example (the address on its own claims page), in your name — I file it for you."]}}}}
                return {"ok": True, "result": {"case_id": body["case_id"], "state": "filed", "say": "Filed with Example Air. They say they reply within 30 days."}}
            self.agapi.calls.pop()
            return await real(op, body, approval)
        FP.CALL = call

    def test_check_says_the_amount_as_given_and_upper_cases_codes(self):
        r = run(FP.run_tool(Ctx(), "flight_money_back", {"airline": "ex", "number": "123", "date": "2026-10-09", "from": "mad", "to": "lhr",
                                                          "what": "delayed", "arrival_delay_minutes": 220}))
        self.assertIn("may be owed EUR 250", r["result"]["say"])
        self.assertIn("Never name an amount it didn't give", r["result"]["how"])
        sent = [b for op, b in self.agapi.calls if op == "money.flight_check"][-1]
        self.assertEqual((sent["flight"]["airline"], sent["flight"]["from"], sent["flight"]["to"]), ("EX", "MAD", "LHR"))

    def test_the_claim_is_read_back_then_filed_only_on_a_later_yes(self):
        self.assertEqual(run(FP.run_tool(Ctx(), "file_flight_claim", {}))["error"]["code"], "no_case")
        run(FP.run_tool(Ctx(), "flight_money_back", {"airline": "EX", "date": "2026-10-09", "from": "MAD", "to": "LHR", "what": "delayed",
                                                      "arrival_delay_minutes": 220}))
        r = run(FP.run_tool(Ctx(), "file_flight_claim", {"booking_reference": "EXA1B2", "passengers": ["Alex Doe"]}))
        self.assertEqual(r["result"]["status"], "awaiting_yes")
        self.assertIn("claims@example-air.example", r["result"]["read_back"][0])
        same = run(FP.run_tool(Ctx(said="Yes, file it.", ago=-60), "file_flight_claim", {"booking_reference": "EXA1B2", "passengers": ["Alex Doe"]}))
        self.assertNotEqual(same["result"].get("status"), "filed")                                      # the same turn is never the yes
        done = run(FP.run_tool(Ctx(said="Yes, file it.", ago=60), "file_flight_claim", {"booking_reference": "EXA1B2", "passengers": ["Alex Doe"]}))
        self.assertEqual(done["result"]["status"], "filed")
