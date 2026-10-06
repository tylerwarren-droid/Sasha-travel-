"""CR 44 · RelocateMe: every form found and filled (EU 174's map, docs/relocateme/forms-map.md). The person signs, ticks and
presses; nothing is sent.

  · A1 the national visa application — flat (no fields), so each value is drawn under its own printed label (found on the
    page): New York's own 2023 form; London and Washington the Ministry's bilingual one. Place/date, signature, photo never.
  · ONE Keep record: asked once, offered to the vault once, reused under the person's yes; never asked again.
  · After arrival: padrón (values + cita, in person), EX-17 (waiting for the founder's copy, said plainly), 790-012 (a CAPTCHA:
    prepared to copy, never filled by us), TA.1 (its AcroForm filled; NSS, consent, place/date, signature never).
  · Every form dated on the "Move to Madrid" trip, in process order.

    cd backend && python -m unittest tests.test_forms_cr44 -v
"""
from __future__ import annotations

import io
import json
import re
from datetime import date
from unittest import mock

from pypdf import PdfReader

from booking_signer import guest_whatsapp as GW
from products.relocation import arrival as AR, facts as F, keep as KP, move as MV, three as TH, turn as RT, visa_form as VF
from tests import test_guest_whatsapp_s75 as TG
from tests.test_three_cr37 import Base, client

run = TG.run


def demo(**kw):
    vals = dict(RT.DEMO, **kw)
    return {"applicant": {k: F.fact(v, "t", "") for k, v in vals.items()},
            "choices": {"residence": F.fact("united states", "t", ""), "notices_to_own_address": F.fact("yes", "t", "")}}


def text_of(pdf: bytes, page: int) -> str:
    import pypdfium2 as P
    return P.PdfDocument(pdf)[page].get_textpage().get_text_range()


class VisaForm(TG.unittest.TestCase):
    def test_each_consulate_its_own_form_filled_never_signed(self):
        for cid, form in (("newyork", "ny"), ("london", "generic"), ("washington", "generic")):
            pdf, placed, sign, got = VF.build({"facts": demo(), "after": {"entry_date": "2027-02-01"}}, cid)
            self.assertEqual(got, form)
            keys = {p["key"] for p in placed}
            for k in ("surnames", "given_names", "birth_date", "passport_number", "passport_issued", "passport_issuer",
                      "home", "phone", "occupation", "purpose", "arrival", "spain_address", "sex_M", "marital_C"):
                self.assertIn(k, keys, (cid, k))
            self.assertGreaterEqual(len(placed), 20)
            self.assertNotIn("signature", keys)
            self.assertNotIn("place_date", keys)
            self.assertIsNotNone(sign)                                          # the pack's SIGN HERE
            alltext = text_of(pdf, 0) + text_of(pdf, 1)
            self.assertIn("EJEMPLO PRUEBA", text_of(pdf, 0))                  # drawn onto the official page, in capitals
            for x in ("EXAMPLE000", "RETIRED TEACHER", "01-02-2027", "PASSPORT CANADA"):
                self.assertIn(x, alltext, (cid, x))
            self.assertNotIn("Ana Ejemplo", text_of(pdf, sign[0]))           # nothing written as a signature

    def test_a_moved_label_refuses_never_guesses(self):
        bad = dict(VF.ANCHORS["ny"], surnames=(r"1\. Apellido que no existe", "text"))
        with mock.patch.dict(VF.ANCHORS, {"ny": bad}):
            with self.assertRaises(VF.FormChanged):
                VF.build({"facts": demo()}, "newyork")

    def test_residence_abroad_ticks_from_nationality_and_where_you_live(self):
        v = VF.values(demo(nationality="estadounidense"), {}, "united states")
        self.assertIn("abroad_no", v)
        v = VF.values(demo(), {}, "united states")                             # a Canadian living in the US
        self.assertIn("abroad_yes", v)

    def test_no_entry_date_no_arrival(self):
        self.assertNotIn("arrival", VF.values(demo(), {}, None))


class Arrival(TG.unittest.TestCase):
    def test_ta1_filled_and_never_the_persons_own(self):
        rows = AR.ta1_rows(demo(nie="Y1234567X", father_name="Juan Ejemplo"))
        got = {k: str(v.get("/V")) for k, v in (PdfReader(io.BytesIO(AR.fill_ta1(rows))).get_fields() or {}).items()
               if v.get("/V") not in (None, "", "/Off")}
        self.assertEqual((got["Texto1"], got["Texto3"], got["Texto8"], got["Texto13"]), ("EJEMPLO", "ANA", "Y1234567X", "JUAN EJEMPLO"))
        self.assertEqual((got["Texto21"], got["Texto22"], got["Texto24"], got["Texto27"], got["Texto28"]), ("CALLE", "DE EJEMPLO", "12", "3", "B"))
        self.assertEqual(got["A"], "/1")                                        # asignación número de Seguridad Social
        self.assertEqual(got["d"], "/0")                                        # notices: the address above
        for never in ("Texto9", "Si", "Texto67", "Texto68"):
            self.assertNotIn(never, got)
        with self.assertRaises(ValueError):
            AR.fill_ta1(rows + [{"field": "Texto68", "value": "x", "source": "t"}])

    def test_790_012_prepared_to_copy_with_its_row_and_fee(self):
        vals = dict(AR.p790_012(demo(nie="Y1234567X")))
        self.assertEqual(vals["NIF / NIE"], "Y1234567X")
        self.assertIn("TIE que documenta la primera concesión", vals["Trámite"])
        self.assertIn("16.08 €", vals["Trámite"])

    def test_padron_values_and_ex17_waiting(self):
        vals = dict(AR.padron(demo()))
        self.assertEqual(vals["Documento"], "Pasaporte EXAMPLE000")             # no NIE yet: the passport
        self.assertIn("CALLE DE EJEMPLO 12", vals["Domicilio"])
        if not AR.ex17_ready():
            self.assertIn("waiting for the official PDF", AR.EX17_WAITING)

    def test_every_form_dated_in_process_order(self):
        case = {"state": {"facts": demo(), "after": {"entry_date": "2027-03-01", "consulate": {"office": "Consulado", "three": "london"}}}}
        days = MV.days(case, "London", 3, date(2026, 10, 6))
        names = [(d["date"], a["name"]) for d in days for a in d["activities"]]
        order = [n for _, n in names if re.search(r"Padrón|TIE appointment|TA\.1|Health card", n)]
        self.assertEqual([re.search(r"Padrón|TIE|TA\.1|Health", n).group(0) for n in order], ["Padrón", "TIE", "TA.1", "Health"])
        window = next(a["blurb"] for d in days for a in d["activities"] if a["name"] == "Your visa window opens")
        self.assertIn("the national visa form, the EX-01, the 790-052", window)


class HealthCard(TG.unittest.TestCase):
    """Row 10 · the 1449F1 fed from the same Keep: the RelocateMe answers, in the health form's own shapes."""

    def test_from_relocation(self):
        from products import store as ST
        from products.health import tarjeta as TS
        saved = ST.STORE
        ST.STORE = ST.MemoryCaseStore()
        try:
            run(ST.STORE.put("relocation", "acct-1", "w", {"facts": demo(nie="Y1234567X")}))
            f = run(TS.from_relocation("acct-1"))
            self.assertEqual({k: f[k]["value"] for k in ("dni", "sex", "postcode", "phone", "address_line")},
                             {"dni": "Y1234567X", "sex": "F", "postcode": "28010", "phone": "600000000",
                              "address_line": "Calle de Ejemplo 12, 3º B"})
            rows = {r["field"]: r["value"] for r in TS.rows({**f, "motive": TS._fact("NUEVA", "t")}, date(2026, 10, 6))}
            self.assertEqual((rows["CDDOCIDENT_INTER"], rows["DSSEXO_INTER"], rows["TLPAISNAC_INTER"]), ("Y1234567X", "M", "CANADÁ"))
            self.assertEqual(run(TS.from_relocation("someone-else")), {})
        finally:
            ST.STORE = saved


class Package(TG.unittest.TestCase):
    """For Sasha 178 (3): read-only, form by form, the next dated step, the tab."""

    def test_status(self):
        from products import store as ST
        from products.relocation import package_status
        saved = ST.STORE
        ST.STORE = ST.MemoryCaseStore()
        try:
            self.assertIsNone(run(package_status("acct-none")))
            run(ST.STORE.put("relocation", "acct-1", "w", {"facts": demo(), "rows": [{}], "status": "signed_on_your_word",
                                                          "after": {"entry_date": "2027-03-01", "consulate": {"three": "london"}}}))
            got = run(package_status("acct-1", date(2026, 10, 6)))
            states = {f["name"]: f["state"] for f in got["forms"]}
            self.assertEqual((states["EX-01"], states["National visa application"], states["Padrón"]), ("signed", "filled", "missing"))
            self.assertEqual(states["EX-17 (TIE)"], "filled" if AR.ex17_ready() else "waiting")
            self.assertEqual(got["tab"], "Move to Madrid")
            self.assertEqual(got["next_deadline"]["on"], "2026-12-01")              # entry − 90: the visa window
        finally:
            ST.STORE = saved


class Keep(TG.unittest.TestCase):
    def test_a_fictional_applicant_is_never_kept(self):
        f = {"applicant": {"surname_1": F.fact("Ejemplo", RT.FICTIONAL, ""), "email": F.fact("a@b.co", "said on WhatsApp", "")}}
        self.assertEqual(KP.keepable(f), {"email": "a@b.co"})


class OnWhatsApp(Base):
    def test_ny_pack_card_and_after_arrival(self):
        for t in ("relocation", "DEMO", "SIGNED", "United States", "New York"):
            self.say(t)
        said = self.said()
        self.assertIn("Your national visa application (New York's own Application for a National Visa (2023))", said)
        self.assertIn("filled from this file's answers", said)                # CR 45 · a DEMO applicant is never "your Keep"
        self.assertTrue(any("/visa-form-card.jpg" in (m.get("media") or "") for m in GW.SENDER.sent))
        self.assertIn("The application form's own footer prints an older one (cog.nuevayork.vis@maec.es)", said)
        self.assertIn("say “after arrival”", said)
        cid, c = self.case_id(), client()
        self.assertEqual(c.get(f"/products/relocation/{cid}/visa-form.pdf").status_code, 200)
        self.assertEqual(c.get(f"/products/relocation/{cid}/visa-form-card.jpg").headers["content-type"], "image/jpeg")
        # CR 44 fix · the file page reads consulate.source.* — CR 37's {office, three} made every such page answer 500
        con = c.get(f"/products/relocation/{cid}").json()["after"]["consulate"]
        self.assertTrue(all(con["source"][k] for k in ("name", "url", "dated", "read")))
        self.assertEqual((con["appointment_email"], con["office"]), ("cog.nuevayork.visnac@maec.es", TH.CONSULATES["newyork"]["office"]))
        self.assertTrue(con["appointment_words"])
        from products import store as ST                      # a file saved before the fix: shaped on read
        st = run(ST.STORE.get(cid))["state"]
        st["after"]["consulate"] = {"office": "x", "three": "newyork", "id": "newyork"}
        run(ST.STORE.update(cid, st))
        con = c.get(f"/products/relocation/{cid}").json()["after"]["consulate"]
        self.assertEqual(con["source"]["read"], TH.READ_ON)
        self.say("after arrival")
        said = self.said()
        self.assertIn("Padrón — in person", said)
        self.assertIn("waiting for the official PDF", said)
        self.assertIn("https://sede.policia.gob.es/Tasa790_012/ImpresoRellenar", said)
        self.assertIn("Your NIE isn't on file yet", said)
        self.assertTrue(any("/TA-1-card.jpg" in (m.get("media") or "") for m in GW.SENDER.sent))
        self.say("my NIE is Y1234567X")
        self.assertIn("Noted: NIE Y1234567X", self.said())
        self.assertIn("NIF / NIE: Y1234567X", self.bodies())
        ta1 = PdfReader(io.BytesIO(c.get(f"/products/relocation/{cid}/TA-1.pdf").content)).get_fields()
        self.assertEqual(str(ta1["Texto8"]["/V"]), "Y1234567X")
        self.assertEqual(c.get(f"/products/relocation/{cid}/EX-17.pdf").status_code, 404 if not AR.ex17_ready() else 200)


class KeepOnWhatsApp(TG.Base):
    """Asked once: the offer after the last answer; a new file under one yes fills from it and asks only what's missing."""

    def setUp(self):
        super().setUp()
        from products import store as ST
        self.saved = (ST.STORE,)
        ST.STORE = ST.MemoryCaseStore()
        self.link()

    def tearDown(self):
        from products import store as ST
        (ST.STORE,) = self.saved
        super().tearDown()

    def said(self):
        return "\n".join(self.bodies() + [b for b, _ in GW.SENDER.contents])

    def test_kept_then_a_new_file_fills_from_it(self):
        from tests.test_relocation_cr1 import OnWhatsApp as R
        kept = {}

        async def save(account, f):
            kept.update(KP.keepable(f))
            return True

        async def item(account):
            return {"id": "k1", "label": KP.LABEL} if kept else None

        async def open_into(account, item_id, f, appr, read_on):
            self.assertEqual(appr["read_back_sha256"], KP.approval(self.now, "button", "")["read_back_sha256"])
            for k, v in kept.items():
                f["applicant"].setdefault(k, F.fact(v, KP.SOURCE, read_on))
            return len(kept)
        with mock.patch.object(KP, "save", save), mock.patch.object(KP, "item", item), mock.patch.object(KP, "open_into", open_into):
            for t in ("relocation", "first application", "me", "myself"):
                self.say(t)
            for a in R.ANSWERS:
                self.say(a)
            self.say("yes")
            self.say("", payload="rx:keep:yes")
            self.assertIn("Kept in your vault as “RelocateMe details”", self.said())
            self.assertEqual(kept["occupation"], "Retired teacher")
            self.assertIn("✅ Your EX-01 is prepared", self.said())
            # a new file ("start over" → yes): the details are NOT asked again
            self.say("start over")
            self.say("", payload="so:yes:relocation")
            GW.SENDER.sent.clear(); GW.SENDER.contents.clear()
            for t in ("first application", "me", "myself"):
                self.say(t)
            self.assertIn("Your details are kept in your vault", "\n".join(b for b, _ in GW.SENDER.contents))
            self.say("", payload="rx:keep:use")
            said = self.said()
            self.assertIn("I'll ask only what's missing", said)
            self.assertNotIn("Your passport number?", said)
            self.assertNotIn("Your current occupation?", said)
            self.assertIn("Do you have children of school age", said)            # about this file, never kept


if __name__ == "__main__":
    TG.unittest.main()


def load_tests(loader, tests, pattern):
    """Only this file's own tests (OnWhatsApp inherits the consulate tests, which run in their own files)."""
    suite = TG.unittest.TestSuite()
    for cls in (VisaForm, Arrival, HealthCard, Package, Keep, KeepOnWhatsApp):
        suite.addTests(loader.loadTestsFromTestCase(cls))
    suite.addTest(OnWhatsApp("test_ny_pack_card_and_after_arrival"))
    return suite
