"""CR 75 · finish the fine-print demo minimum: when Sasha speaks up (step 6), the accident playbook (step 7). Offline: the committed snapshot
(read on the sandbox server) and the Example Bank / Example Rentals fixtures — not a real bank, not a real rental company.

    python -m unittest agapi_service.tests.test_cr75 -v      (from the repo root)
"""
from __future__ import annotations

import base64
import json
import unittest

from agapi_service.fineprint import model as M, moments as MO
from agapi_service.tests.test_service import Base

READS = json.loads((M.DATA / "reads.json").read_text())["reads"]
HAS_EMAIL = any(f["field"] == "contact_email" for f in (READS.get("example-rentals-pt") or {}).get("facts", []))


class Moments(Base):
    def setUp(self):
        super().setUp()
        self.uid = self.user()

    def card(self, product="Example Bank Travel Visa", network="visa"):
        return self.ok("keep.put", {"end_user": self.uid, "type": "card_product", "value": {"issuer": "Example Bank", "product": product, "network": network}})

    def moment(self, **ev):
        return self.ok("cards.moment", {"end_user": self.uid, "event": ev})

    def test_rental_booked_speaks_once_with_the_counter_card(self):
        self.card()
        m = self.moment(id="bk-1", kind="rental_booked", country="PT", rental_company="Example Rentals", place="Portugal")
        self.assertTrue(m["speak"])
        self.assertEqual(m["why"], "saves_money")
        self.assertTrue(m["line"].startswith("Pay this rental with your Example Bank Travel Visa"))
        self.assertEqual(m["card"]["type"], "counter_card")
        self.assertEqual(len(m["card"]["counter"]["decline"]), 1)
        again = self.moment(id="bk-1", kind="rental_booked", country="PT", rental_company="Example Rentals")
        self.assertEqual((again["speak"], again["why_silent"]), (False, "already said once for this event"))

    def test_silent_when_nothing_saves_money_and_when_turned_off(self):
        self.card("Example Bank Everyday Mastercard", "mastercard")                           # its terms say nothing of rental cover
        m = self.moment(id="bk-2", kind="rental_booked", country="PT", rental_company="Example Rentals")
        self.assertEqual((m["speak"], m["why_silent"]), (False, "nothing here saves money or prevents a mistake"))
        self.card()
        self.ok("cards.moment_settings", {"end_user": self.uid, "moment": "rental_booked", "on": False})
        m = self.moment(id="bk-3", kind="rental_booked", country="PT", rental_company="Example Rentals")
        self.assertEqual(m["why_silent"], "turned off by the person")
        s = self.ok("cards.moment_settings", {"end_user": self.uid})["moments"]
        self.assertEqual({x["moment"]: x["on"] for x in s}, {"rental_booked": False, "pickup_tomorrow": True, "which_card": True, "rental_returned": True})

    def test_the_day_before_pickup_and_which_card(self):
        self.card()
        m = self.moment(id="pk-1", kind="pickup_tomorrow", country="PT", rental_company="Example Rentals", pickup_time="10:00", place="Lisbon airport")
        self.assertEqual(m["line"], "Tomorrow 10:00, Lisbon airport: here's your counter card — what to decline, keep and bring, and the claims line.")
        self.assertTrue(m["card"]["report"])
        w = self.moment(id="wc-1", kind="which_card", purchase={"amount_minor": 40000, "currency": "USD", "kind": "car_rental"})
        self.assertEqual(w["line"], "Information from your cards' own terms. You decide.")

    def test_after_return_only_a_real_difference_speaks(self):
        quoted = [{"label": "Rental 7 days", "amount_minor": 21000}, {"label": "Fuel", "amount_minor": 0}]
        same = self.moment(id="rt-1", kind="rental_returned", quoted=quoted, final=quoted, currency="EUR", rental_company="Example Rentals", country="PT")
        self.assertFalse(same["speak"])
        final = [{"label": "Rental 7 days", "amount_minor": 21000}, {"label": "Fuel", "amount_minor": 8400}, {"label": "Damage", "amount_minor": 10000}]
        m = self.moment(id="rt-2", kind="rental_returned", quoted=quoted, final=final, currency="EUR", rental_company="Example Rentals", country="PT")
        self.assertEqual(m["line"], "The final charge is EUR 184.00 more than the quote (Fuel + Damage). Want me to draft a dispute?")
        self.assertEqual([r["difference_minor"] for r in m["card"]["rows"]], [0, 8400, 10000])
        return m

    @unittest.skipUnless(HAS_EMAIL, "the fixture rental's contact address is read on the sandbox first")
    def test_draft_a_dispute_read_back_yes_sent(self):
        m = self.test_after_return_only_a_real_difference_speaks()
        r, b = self.call("cards.rental_dispute", {"end_user": self.uid, "moment_id": m["moment_id"]}, expect="approval_required")
        lines = b["error"]["details"]["read_back"]["lines"]
        self.assertIn("accidents@example-rentals.example", lines[0])
        self.assertIn("Fuel: quoted EUR 0.00, charged EUR 84.00", lines)
        apv = self.ok("sandbox.simulate_approval", {"read_back_id": b["error"]["details"]["read_back_id"], "said": "Yes, send it."})["approval_id"]
        out = self.ok("cards.rental_dispute", {"end_user": self.uid, "moment_id": m["moment_id"]}, approval=apv)
        self.assertEqual(out["state"], "sent")
        self.call("cards.rental_dispute", {"end_user": self.uid, "moment_id": m["moment_id"]}, expect="already_completed")

    def test_no_address_in_the_terms_is_a_draft_only(self):
        quoted = [{"label": "Rental", "amount_minor": 20000}]
        m = self.moment(id="rt-3", kind="rental_returned", quoted=quoted, final=[{"label": "Rental", "amount_minor": 26000}], currency="EUR",
                        rental_company="Hertz", country="ES")
        out = self.ok("cards.rental_dispute", {"end_user": self.uid, "moment_id": m["moment_id"]})
        self.assertEqual(out["state"], "draft_only")
        self.assertIn("EUR 60.00 more than the quote", out["draft"])

    def test_the_diff_is_pure_and_exact(self):
        d = MO.returned_diff([{"label": "A", "amount_minor": 100}], [{"label": "a", "amount_minor": 130}], "EUR")
        self.assertIsNone(d)                                                                     # under 0.50: not worth a word
        d = MO.returned_diff([{"label": "A", "amount_minor": 1000}], [{"label": "A", "amount_minor": 500}], "EUR")
        self.assertEqual((d["line"], d["can_dispute"]), ("The final charge is EUR 5.00 less than the quote.", False))


PNG = base64.b64encode(b"\x89PNG\r\n fake accident photo").decode()


class Accident(Base):
    def setUp(self):
        super().setUp()
        self.uid = self.user()
        M.ensure_loaded(self.store)
        self.store.x("update card_products set accepted_at = '2026-10-10T12:00:00Z', accepted_by = 'test' where key in ('law_es', 'law_fr', 'law_de', 'law_it')")
        self.item = self.ok("keep.put", {"end_user": self.uid, "type": "card_product",
                                         "value": {"issuer": "Example Bank", "product": "Example Bank Travel Visa", "network": "visa"}})["item_id"]

    def start(self, country="PT", **kw):
        return self.ok("cards.accident_start", {"end_user": self.uid, "country": country, "place": "a roundabout in Lisbon",
                                                "rental_company": "Example Rentals", "card_item_id": self.item, "at": "2026-10-10T14:00:00", **kw})

    def step(self, cid, answer=None, **kw):
        return self.ok("cards.accident_step", {"end_user": self.uid, "case_id": cid, **({"answer": answer} if answer else {}), **kw})

    def test_safety_first_nothing_else_until_answered(self):
        a = self.start()
        self.assertEqual((a["step"], a["say"]), ("safety", "Is anyone hurt?"))
        self.assertNotIn("clocks", a)
        self.call("cards.accident_photo", {"end_user": self.uid, "case_id": a["case_id"], "shot": "your_car_front", "media_type": "image/png",
                                           "content_base64": PNG}, expect="invalid_input")                    # safety first
        s = self.step(a["case_id"], "duties please")
        self.assertEqual(s["step"], "safety")                                                             # not answered: still safety
        s = self.step(a["case_id"], "not sure")
        self.assertEqual(s["say"], "Call 112 now.")
        self.assertIn("A nivel europeo", s["call"]["source"]["quote"])                                    # DGT's own words, quoted
        self.assertEqual(s["step"], "safety")
        s = self.step(a["case_id"], "help is on the way")
        self.assertEqual(s["step"], "duties")

    def test_injuries_mean_the_hand_off(self):
        a = self.start()
        s = self.step(a["case_id"], "yes")
        self.assertEqual(s["handoff"], "This needs a lawyer or your insurer's legal team. I can find one for you, and I'll keep doing only the paperwork.")
        a = self.start()
        s = self.step(a["case_id"], "no", flags=["fault_disputed"])
        self.assertIn("lawyer", s["handoff"])

    def test_duties_only_from_a_source_read_at_source(self):
        a = self.start("PT")
        s = self.step(a["case_id"], "no")
        self.assertFalse(s["read_at_source"])                                                             # ASF couldn't be read: nothing quoted
        self.assertTrue(s["say"].startswith("The official rules for Portugal aren't read at source yet, so I won't quote them."))
        a = self.start("DE")
        s = self.step(a["case_id"], "no")
        self.assertTrue(s["read_at_source"])
        self.assertTrue(any("unverzüglich zu halten" in q["quote"] for l in s["lines"] for q in l["quotes"]))

    def test_the_whole_lisbon_flow_to_the_claim(self):
        a = self.start("PT")
        cid = a["case_id"]
        self.step(cid, "no")
        s = self.step(cid, "done")
        self.assertEqual((s["step"], s["next"]), ("photos", "done"))
        for shot in ("your_car_front", "the_damage_close_up"):
            p = self.ok("cards.accident_photo", {"end_user": self.uid, "case_id": cid, "shot": shot, "media_type": "image/png", "content_base64": PNG})
            self.assertTrue(p["saved"]["sha256"].startswith("sha256:") and p["saved"]["evidence_id"])
        self.assertTrue(next(x for x in p["shots"] if x["shot"] == "the_damage_close_up")["taken"])
        s = self.step(cid, "done", facts={"date": "2026-10-10", "time": "14:00", "place": "Rotunda do Marquês, Lisboa",
                                          "your_vehicle": {"plate": "AA-00-ZZ", "make": "a test car"}})
        self.assertEqual(s["step"], "statement")
        self.assertEqual(s["form"], "Declaração Amigável de Acidente Automóvel")
        self.assertEqual(s["left_for_you"], ["circumstances boxes (1–17)", "the sketch", "the signature"])
        self.assertNotIn("circumstances", json.dumps(s["facts"]))                                       # never a fault box
        self.assertIn("I never sign", s["say"])
        s = self.step(cid, "done")
        clocks = {c["who"]: c for c in s["clocks"]}
        self.assertEqual(clocks["the rental company"]["due"], "2026-10-12 14:00")                       # 48 hours from the accident's own time
        self.assertIn("within 48 hours", clocks["the rental company"]["quotes"][0]["quote"])
        self.assertTrue(any(k.startswith("your card's insurer") and c["due"] == "2026-12-09" for k, c in clocks.items()))   # 60 days
        self.assertEqual(clocks["PT"]["say"], "Portugal's own deadline: its official rules aren't read at source yet — not shown.")
        s = self.step(cid, "done")
        self.assertEqual(s["step"], "notify")
        r, b = self.call("cards.accident_notify", {"end_user": self.uid, "case_id": cid}, expect="approval_required")
        lines = b["error"]["details"]["read_back"]["lines"]
        self.assertIn("accidents@example-rentals.example", lines[0])
        self.assertIn("With: 2 photo(s), each recorded with its fingerprint and time.", lines)
        apv = self.ok("sandbox.simulate_approval", {"read_back_id": b["error"]["details"]["read_back_id"], "said": "Yes, send it."})["approval_id"]
        out = self.ok("cards.accident_notify", {"end_user": self.uid, "case_id": cid}, approval=apv)
        self.assertEqual((out["state"], out["step"]), ("sent", "claim"))
        claim = self.ok("cards.claim_status", {"end_user": self.uid, "case_id": out["claim_case_id"]})
        self.assertEqual((claim["kind"], claim["state"]), ("rental_damage", "preparing"))
        self.assertEqual(next(e for e in claim["evidence"] if e["item"] == "photos")["have"], ["your_car_front.jpg", "the_damage_close_up.jpg"])
        self.assertEqual(next(e for e in claim["evidence"] if e["item"] == "accident_statement")["have"], ["accident-statement-facts.txt"])
        self.assertIn("Vehicle: make a test car, plate AA-00-ZZ", lines)
