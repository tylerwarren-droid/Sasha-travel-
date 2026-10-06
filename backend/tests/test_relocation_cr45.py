"""CR 45 · RelocateMe from EU 178's live check: (d) every form Kanoe fills is "prepared — sign it" in the pack (the visa form
too), only where Kanoe fills it; (e) a caption names its TRUE source — "your Keep" only for values from the vault; and every
form lives in the "Move to Madrid" journey with its PDF one tap away and where it goes next.

    cd backend && python -m unittest tests.test_relocation_cr45 -v
"""
from __future__ import annotations

from products.relocation import consulates as CS, facts as F, keep as KP, package as PK, turn as RT
from tests import test_guest_whatsapp_s75 as TG
from tests.test_forms_cr44 import demo

run = TG.run


class Pack(TG.unittest.TestCase):
    def test_kanoes_forms_are_prepared_only_where_it_fills_them(self):
        items = [{"n": 1, "key": "visa_form", "label": "Visa form", "words": "", "copies": None},
                 {"n": 2, "key": "ex01", "label": "EX-01", "words": "", "copies": None}]
        self.assertEqual([x["status"] for x in CS.pack(items, set(), CS.prepared_for("newyork"))], ["prepared", "prepared"])
        self.assertEqual([x["status"] for x in CS.pack(items, set(), CS.prepared_for("losangeles"))], ["missing", "prepared"])


class Captions(TG.unittest.TestCase):
    def test_true_source(self):
        self.assertEqual(KP.where_from(demo()), "this file's answers")         # DEMO is never kept
        f = demo()
        f["applicant"]["email"] = F.fact("a@b.co", KP.SOURCE, "")
        self.assertEqual(KP.where_from(f), "your Keep")


class Journey(TG.unittest.TestCase):
    def test_forms_with_pdf_and_next(self):
        forms = PK._with_links(PK._forms({"status": "prepared", "after": {"consulate": {"three": "newyork"}}}), "cid1")
        by = {f["name"]: f for f in forms}
        self.assertTrue(by["National visa application"]["pdf"].endswith("/api/products/relocation/cid1/visa-form.pdf"))
        self.assertTrue(by["TA.1 (Social Security number)"]["pdf"].endswith("/TA-1.pdf"))
        self.assertIsNone(by["Padrón"]["pdf"])                                  # values to copy, no PDF
        self.assertEqual(by["EX-01"]["next"], "signed, to your consulate appointment")
        self.assertTrue(all(f["next"] for f in forms))


if __name__ == "__main__":
    TG.unittest.main()
