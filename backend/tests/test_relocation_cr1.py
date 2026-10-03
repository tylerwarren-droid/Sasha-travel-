"""CR 1 · relocation: the EX-01 assembled from the applicant's own words, every value with its source, the reviewer's
checks, the official PDF filled — and NEVER a signature, a consent or an intent written for anyone; nothing filed; the
model never called. Offline; the WhatsApp turn is the real one.

    cd backend && python -m unittest tests.test_relocation_cr1 -v
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

from booking_signer import guest_whatsapp as GW
from products import routes as PR, store as ST
from products.relocation import checker as CK, ex01 as E, facts as F, turn as RT
from tests import test_guest_whatsapp_s75 as TG

run = TG.run
TODAY = date(2026, 10, 3)
IRREDUCIBLE = {"Texto68"} | {f"Casilla de verificación{i}" for i in range(20, 27)}


def ana(**over):
    v = {**RT.DEMO, **over}
    return {"applicant": {k: F.fact(x, "said on WhatsApp", "3 Oct 2026") for k, x in v.items()},
            "choices": {"notices_to_own_address": F.fact("yes", "said on WhatsApp", "3 Oct 2026")}}


NA = {"2": False, "3": False, "legal_rep": False}


class Form(TG.unittest.TestCase):
    def test_every_widget_once_and_the_eight_are_left_for_the_applicant(self):
        rows = E.rows(ana(), NA)
        self.assertEqual(len(rows), 96)
        self.assertEqual(len({r["name"] for r in rows}), 96)
        self.assertEqual({r["name"] for r in rows if r["state"] == E.PREPARED}, IRREDUCIBLE)
        sig = next(r for r in rows if r["name"] == "Texto68")
        self.assertEqual(sig["the_person_must"], "sign it themselves — nothing we place is a signature")
        c = E.counts(rows)
        self.assertEqual(sum(c.values()), 96)
        self.assertEqual(c["blank_unplaced"], 0)              # every widget classified from the rendered form
        self.assertEqual(c["not_applicable"], 3 + 22 + 13)    # the legal-representative row (3) + section 2 (22) + section 3 (13)
        self.assertEqual(c["blank_no_mapping"], 3)            # DIRIGIDA A, DIR3, PROVINCIA — the consulate's

    def test_the_date_and_the_nie_land_in_their_own_boxes(self):
        rows = {r["name"]: r for r in E.rows(ana(nie="X-0000000-T"), NA)}
        self.assertEqual((rows["Texto8"]["value"], rows["Texto9"]["value"], rows["Texto10"]["value"]), ("14", "03", "1985"))
        self.assertEqual((rows["Texto2"]["value"], rows["Texto3"]["value"], rows["Texto4"]["value"]), ("X", "0000000", "T"))
        self.assertEqual(rows["Casilla de verificación4"]["state"], E.FILLED)      # M (mujer)
        self.assertEqual(rows["Casilla de verificación3"]["state"], E.SIBLING)
        self.assertEqual(rows["Texto54"]["value"], "Ana Ejemplo Prueba")           # section 4, by the applicant's choice
        self.assertIn("copied from section 1", rows["Texto54"]["provenance"])

    def test_the_pdf_holds_exactly_the_filled_rows_and_nothing_irreducible(self):
        rows = E.rows(ana(), NA)
        got = E.read_back(E.fill(rows))
        self.assertEqual(set(got), {r["name"] for r in rows if r["state"] == E.FILLED})
        self.assertFalse(IRREDUCIBLE & set(got))
        self.assertEqual(got["Casilla de verificación6"], "/Yes")                   # married (C)

    def test_a_value_aimed_at_the_signature_is_refused_whatever_the_caller_meant(self):
        rows = E.rows(ana(), NA)
        sig = next(r for r in rows if r["name"] == "Texto68")
        sig.update(state=E.FILLED, value="Ana Ejemplo", provenance="anything")
        with self.assertRaises(E.DeclarationRefused):
            E.fill(rows)
        consent = next(r for r in E.rows(ana(), NA) if r["name"] == "Casilla de verificación20")
        with self.assertRaises(E.DeclarationRefused):
            E.fill([{**consent, "state": E.FILLED, "value": "✓", "provenance": "x", "type": "checkbox"}])

    def test_a_value_without_a_source_is_refused(self):
        rows = E.rows(ana(), NA)
        rows[0].update(provenance=None)
        with self.assertRaises(E.DeclarationRefused):
            E.fill(rows)


class Reviewer(TG.unittest.TestCase):
    def review(self, f):
        return {r["name"]: r for r in CK.review(E.rows(f, NA), f, TODAY)}

    def test_the_nie_control_letter(self):
        self.assertTrue(F.nie_ok("X", "0000000", "T"))
        self.assertFalse(F.nie_ok("X", "0000000", "A"))
        r = self.review(ana(nie="X-0000000-A"))["Texto4"]
        self.assertEqual(r["verdict"], CK.PROBLEM)
        self.assertIn("fails its control letter", r["checks"][0]["why"])

    def test_postcode_and_province_must_agree(self):
        r = self.review(ana(address_postcode="08010"))["Texto20"]
        self.assertEqual(r["verdict"], CK.PROBLEM)
        self.assertIn("postcode 08010 is in Barcelona, but the province written is Madrid", r["checks"][0]["why"])
        self.assertEqual(self.review(ana())["Texto20"]["verdict"], CK.OK)

    def test_two_sources_that_disagree_are_both_shown(self):
        f = ana()
        f["documents"] = {"applicant.surname_1": [F.fact("Ejemplo-Ruiz", "passport photo page", "3 Oct 2026")]}
        r = self.review(f)["Texto5"]
        self.assertEqual(r["verdict"], CK.PROBLEM)
        self.assertIn("two sources disagree", r["checks"][0]["why"])

    def test_an_expired_passport_and_a_clipped_box(self):
        rows = self.review(ana(passport_expiry="2026-01-31"))
        self.assertIn("this passport expired on 2026-01-31", json.dumps(rows["Texto1"]["checks"]))
        self.assertIn("may not fit this box", json.dumps(rows["Texto18"]["checks"]))    # "3º B" in the tiny Piso box

    def test_the_irreducible_rows_are_checked_empty(self):
        rows = self.review(ana())
        self.assertTrue(all(rows[n]["verdict"] == CK.OK for n in IRREDUCIBLE))


class OnWhatsApp(TG.Base):
    ANSWERS = ["EXAMPLE000", "Ejemplo", "Prueba", "Ana", "F", "14/03/1985", "Toronto", "Canadá", "canadiense", "30/06/2031",
               "married", "NONE", "NONE", "NONE", "Calle de Ejemplo", "12", "3º B", "Madrid", "28010", "Madrid",
               "+34 600 000 000", "ana@example.com", "no"]

    def setUp(self):
        super().setUp()
        self.saved = (ST.STORE,)
        ST.STORE = ST.MemoryCaseStore()
        self.link()

    def tearDown(self):
        (ST.STORE,) = self.saved
        super().tearDown()

    def test_answers_to_a_prepared_file_with_its_pdf_and_nothing_filed(self):
        self.say("relocation")
        self.assertIn("I never file anything", self.bodies()[-2])
        self.assertIn("first* application", self.bodies()[-1])
        self.say("first application")
        self.say("me")
        self.say("myself")
        self.assertEqual(self.bodies()[-1], "Your passport number?")
        self.say("not a passport!")
        self.assertIn("letters and digits", self.bodies()[-1])
        for a in self.ANSWERS:
            self.say(a)
        self.say("yes")                                                    # notices to my own address
        said = "\n".join(self.bodies())
        self.assertIn("✅ Your EX-01 is prepared: 31 boxes filled", said)
        self.assertIn("8 left for you", said)
        cid = next(s["body"] for s in GW.SENDER.sent if "relocation-file/" in s["body"]).split("relocation-file/")[1][:22]
        pdf = next(s for s in GW.SENDER.sent if s["media"])
        self.assertEqual(pdf["media"], f"https://sasha.test/api/products/relocation/{cid}/EX-01-prepared.pdf")
        case = run(ST.STORE.get(cid))["state"]
        self.assertEqual(case["status"], "prepared")
        self.assertEqual(case["facts"]["choices"]["route"]["value"], "initial")
        got = E.read_back(E.fill(case["rows"]))
        self.assertEqual(got["Texto1"], "EXAMPLE000")
        self.assertFalse(IRREDUCIBLE & set(got))
        self.say("SIGNED")
        self.assertIn("I didn't sign or tick anything for you", self.bodies()[-2])   # then: where you lodge it
        self.assertEqual(run(ST.STORE.get(cid))["state"]["status"], "signed_on_your_word")
        st = run(GW.STORE.get_state(GW.wa_key(TG.GUEST)))
        self.assertNotIn("EXAMPLE000", json.dumps(st.get("history"), default=str))   # never in Sasha's history

    def test_demo_is_fictional_and_says_so(self):
        self.say("relocation")
        self.say("DEMO")
        said = "\n".join(self.bodies())
        self.assertIn("*fictional* applicant, Ana Ejemplo Prueba", said)
        cid = next(s["body"] for s in GW.SENDER.sent if "relocation-file/" in s["body"]).split("relocation-file/")[1][:22]
        case = run(ST.STORE.get(cid))["state"]
        self.assertTrue(case["fictional"])
        self.assertTrue(all("fictional" in r["provenance"] for r in case["rows"] if r["state"] == E.FILLED
                            and "section 1" not in r["provenance"]))

    def test_the_reviewer_page_and_the_pdf_route(self):
        self.say("relocation")
        self.say("DEMO")
        cid = next(s["body"] for s in GW.SENDER.sent if "relocation-file/" in s["body"]).split("relocation-file/")[1][:22]
        app = FastAPI(); app.include_router(PR.router)
        c = TestClient(app)
        j = c.get(f"/products/relocation/{cid}").json()
        self.assertEqual((j["form"]["widgets"], j["submits"], j["fictional"]), (96, False, True))
        self.assertNotIn("%", json.dumps(j["counts"]))
        r = c.get(f"/products/relocation/{cid}/EX-01-prepared.pdf")
        self.assertEqual(r.headers["content-type"], "application/pdf")
        self.assertTrue(r.content.startswith(b"%PDF"))
