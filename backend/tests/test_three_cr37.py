"""CR 37 · RelocateMe, three consulates end to end — London, New York, Washington DC — each from its own page READ LIVE on
6 Oct 2026: the fees in local currency up front (by nationality), the 790-052 (its amount there, pre-filled where the official
form allows), the booking route (one tap; each detail its own message), ONE print-ready pack in the consulate's order with
SIGN HERE beside every signature box, and the booked appointment on the "Move to Madrid" trip with what to bring.
Rehearsed with the fictional applicant (DEMO); nothing is booked, sent or signed.

    cd backend && python -m unittest tests.test_three_cr37 -v
"""
from __future__ import annotations

import io
from datetime import date

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pypdf import PdfReader

from booking_signer import guest_whatsapp as GW, plan_store as PS
from products import routes as PR, store as ST
from products.relocation import three as TH
from tests import test_consulates_cr12 as T12
from tests import test_guest_whatsapp_s75 as TG

run = TG.run


def client():
    app = FastAPI(); app.include_router(PR.router)
    return TestClient(app)


class Base(T12.NewYorkOnWhatsApp):
    def setUp(self):
        super().setUp()
        self.saved_ps = (PS.latest, PS.add_day, PS.add_place)
        self.trip = {"trip_id": "trip-move", "title": "Move to Madrid", "plan": {"days": []}}
        self.placed = []

        async def latest(account, hint=None):
            return self.trip

        async def add_day(account, trip_id, day, city):
            self.trip["plan"]["days"].append({"day": len(self.trip["plan"]["days"]) + 1, "date": day, "city": city, "activities": []})
            return True

        async def add_place(account, trip_id, day, activity):
            self.placed.append((day, activity))
            return True
        PS.latest, PS.add_day, PS.add_place = latest, add_day, add_place

    def tearDown(self):
        PS.latest, PS.add_day, PS.add_place = self.saved_ps
        super().tearDown()

    def case_id(self):
        return run(GW.STORE.get_state(GW.wa_key(TG.GUEST)))["pending"]["case_id"]

    def pdfs(self):
        cid, c = self.case_id(), client()
        pack, f790 = c.get(f"/products/relocation/{cid}/pack.pdf"), c.get(f"/products/relocation/{cid}/790-052.pdf")
        card = c.get(f"/products/relocation/{cid}/790-card.jpg")
        self.assertEqual((pack.status_code, f790.status_code, card.status_code), (200, 200, 200))
        return PdfReader(io.BytesIO(pack.content)), PdfReader(io.BytesIO(f790.content))


class London(Base):
    def test_london_end_to_end(self):
        for t in ("relocation", "DEMO", "SIGNED", "UK"):
            self.say(t)
        said = self.said()
        self.assertIn("Visado-de-residencia-no-lucrativa.aspx (July 6, 2026)", said)
        self.assertIn("Which consulate you use is decided by where you live", said)                 # the differences, plainly
        self.assertIn("Visa fee: not stated — the list doesn't name this visa for Canadians", said)   # never a guess
        self.assertIn("£9.60 — “Aut. Inicial residencia temporal 9,60”", said)
        self.assertIn("https://uk.blsspainglobal.com/Global/account/login", said)
        self.assertIn("EXAMPLE000", self.bodies())                                                   # its own message
        pack, f790 = self.pdfs()
        self.assertEqual(len(pack.pages), 12)                 # checklist · CR 44 national visa form (5) · EX-01 (3) · photo · 790 (2)
        got = {k: str(v.get("/V")) for k, v in (f790.get_fields() or {}).items() if v.get("/V") not in (None, "", "/Off")}
        self.assertEqual((got["Nacionalidad"], got["PRINCIPAL"], got["Activado1_3"]), ("CANADÁ", "/Yes", "/Yes"))
        self.assertNotIn("NIF", got)                          # no NIE: left blank, as the instructions say
        self.say("SKIP")
        self.say("1 March 2027")
        self.say("consulate booked 12 November 10:00")
        (x,) = self.added
        self.assertEqual(x["tz"], "Europe/London")
        self.assertIn("20 St Andrew Street", x["location"])
        self.assertIn("On your “Move to Madrid” trip", self.said())
        (day, act), = self.placed
        self.assertIn("Visa appointment — BLS", act["name"])


class Washington(Base):
    def test_washington_end_to_end_never_new_yorks_page(self):
        for t in ("relocation", "DEMO", "SIGNED", "USA", "Maryland"):
            self.say(t)
        said = self.said()
        self.assertIn("*Sección Consular de la Embajada de España en Washington*", said)
        self.assertIn("washington/en/ServiciosConsulares/Paginas/Consular/Visado-de-residencia-no-lucrativa.aspx", said)
        self.assertNotIn("cog.nuevayork", said)                                                      # the old read was NY's page
        self.assertIn("Visa fee: $789 — “Citizens of Canada: $789”", said)
        self.assertIn("Total: $822.", said)                                                          # 789 + 13 + BLS 20
        self.assertIn("https://usa.blsspainglobal.com/Global/account/login", said)
        pack, _ = self.pdfs()
        self.assertEqual(len(pack.pages), 12)   # CR 44 · + the national visa form (5)
        self.assertEqual(len(self.after()["checklist"]), 17)


class Fees(TG.unittest.TestCase):
    def test_each_consulates_own_table_by_nationality(self):
        self.assertEqual(TH.fees("london", "British")[1], "£540.45")             # 516 + 9.60 + 14.85
        self.assertEqual(TH.fees("london", "Utopian")[1], "£103.45")             # 79 + 9.60 + 14.85
        self.assertIsNone(TH.fees("london", "USA")[1])                            # its list has no line: said, not guessed
        self.assertEqual(TH.fees("newyork", "USA")[1], "$153")
        self.assertEqual(TH.fees("newyork", "Utopian")[1], "$119")
        self.assertEqual(TH.fees("washington", "USA")[1], "$173")                # 140 + 13 + BLS 20 (SMS optional, out)

    def test_the_790_refuses_the_applicants_boxes(self):
        for field in ("NIF", "Ciudad_Solicitud", "Fecha_Actual", "EN EFECTIVO"):
            with self.assertRaises(ValueError):
                TH.fill_790([{"field": field, "value": "X", "source": "x"}])

    def test_the_790_pdf_is_the_one_read(self):
        import hashlib
        self.assertEqual(hashlib.sha256(TH.F790.read_bytes()).hexdigest(), TH.F790_SHA256)


if __name__ == "__main__":
    TG.unittest.main()
