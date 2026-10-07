"""CR 35 · the centre finder on the founder's live run: "VEREDA DE PALACIO, Nº 1, PORTAL 8, 11-B" (Alcobendas) was refused
with "doesn't list that exact address — look yourself". Now: the address is split (type, name, number; portal, floor and
door dropped for the lookup), the finder is asked in several spellings, a street is taken only when its name IS the
citizen's ("VEREDA DE PALACIO" = SERMAS's "CALLE DE LA VEREDA DE PALACIO"), otherwise the finder's closest streets are
offered to pick, or the citizen types it as on their padrón. Never "look yourself". Offline: a fake finder that searches
like SERMAS's (the typed text inside the street name, at that number; the ID is the centre's area).

    cd backend && python -m unittest tests.test_finder_cr35 -v
"""
from __future__ import annotations

import re
import unittest

from products.health import address as A, cita as CI
from tests import test_cita_cr34 as TC
from tests import test_guest_whatsapp_s75 as TG

run = TG.run
STREETS = {"006": [("700", "CALLE DE LA VEREDA DE PALACIO", "1"), ("700", "CALLE DE LA VEREDA DE LAS PEÑAS", "1"),
                   ("700", "CALLE VEREDA CORTA", "1"), ("701", "PLAZA DEL PALACIO", "1")],
           "079": [("453", "CALLE DE EJEMPLO", "1"), ("454", "CALLE DE EJEMPLO GALIANO", "1"), ("455", "RONDA DE SEGOVIA", "10"),
                   ("455", "CALLE DE SEGOVIA", "10")]}
FINDER_PAGE = TC.FINDER_PAGE.replace('<option value="073">HUMANES DE MADRID</option>', '<option value="006">ALCOBENDAS</option>')
DETAILS = {"700": ("C.S. ARROYO DE LA VEGA", "BULEV DE SALVADOR ALLENDE, 22", "ALCOBENDAS", "28108", "91 484 11 49"),
           "701": ("C.S. OTRO", "CALLE OTRA, 1", "ALCOBENDAS", "28100", "91 000 00 00"),
           "453": ("C.S. LAS CORTES", "CRA DE SAN JERONIMO, 32", "MADRID", "28014", "91 369 04 91"),
           "455": ("C.S. PASEO IMPERIAL", "CALLE DE TOLEDO, 180", "MADRID", "28005", "91 364 07 62")}


class Finder:
    def __init__(self):
        self.calls = []

    async def __call__(self, method, url, data=None, cookies=None):
        self.calls.append((method, url, data))
        if "misCentroPorDireccion" in url and method == "GET":
            return 200, FINDER_PAGE, {}
        if "misCentroPorDireccion" in url:
            q, n = data["ctl00$ContenedorContenidoSeccion$txtDireccion"], data["ctl00$ContenedorContenidoSeccion$txtNumero"]
            rows = [(i, st) for i, st, num in STREETS.get(data["ctl00$ContenedorContenidoSeccion$cbxLocalidades"], [])
                    if q in st and num == n]
            body = "".join(f"<tr><td><a href='../RedAsistencial/DetalleAsistenciales.aspx?ID={i}' class=\"link\">{st}, {n}</a>"
                           f"</td><td>X</td></tr>" for i, st in rows)
            return 200, FINDER_PAGE + f"<table>{body}</table>", {}
        m = re.search(r"ID=(\d+)", url)
        if m and m.group(1) in DETAILS:
            name, addr, muni, cp, tel = DETAILS[m.group(1)]
            return 200, (f"Detalles del centro {name} Código de centro: {m.group(1)}0 Dirección postal: {addr} Municipio: {muni} "
                         f"Código postal: {cp} Horario del centro: Lunes a viernes de 8:00 a 21:00 Teléfono de información: {tel} "
                         f"Teléfono cita previa: {tel} Volver"), {}
        return 404, "", {}


class Parse(unittest.TestCase):
    def test_the_founders_line_and_its_kin(self):
        self.assertEqual(A.parse("VEREDA DE PALACIO, Nº 1, PORTAL 8, 11-B"),
                         {"type": "VEREDA", "name": "DE PALACIO", "number": "1", "portal": "8", "stair": "", "floor": "11",
                          "door": "B", "block": ""})
        p = A.parse("CL MAYOR 5 ESC 2 PL 3 PTA D")
        self.assertEqual((p["type"], p["number"], p["stair"], p["floor"], p["door"]), ("CALLE", "5", "2", "3", "D"))
        p = A.parse("C. PADRE DAMIAN 41 P05 B")
        self.assertEqual((p["name"], p["number"], p["floor"], p["door"]), ("PADRE DAMIAN", "41", "05", "B"))

    def test_the_same_street_with_or_without_its_type_never_a_neighbour(self):
        p = A.parse("VEREDA DE PALACIO, Nº 1")
        self.assertTrue(A.same(p, "CALLE DE LA VEREDA DE PALACIO"))
        self.assertFalse(A.same(p, "PLAZA DEL PALACIO"))
        self.assertFalse(A.same(p, "CALLE VEREDA CORTA"))
        self.assertTrue(A.same(A.parse("RDA. DE SEGOVIA 10"), "RONDA DE SEGOVIA"))
        self.assertFalse(A.same(A.parse("RDA. DE SEGOVIA 10"), "CALLE DE SEGOVIA"))


class Base(TC.Base):
    def setUp(self):
        super().setUp()
        self.finder = Finder()
        CI.HTTP = self.finder


class Find(Base):
    def test_the_founders_address_finds_his_centre(self):
        c = run(CI.find("VEREDA DE PALACIO, Nº 1, PORTAL 8, 11-B", "ALCOBENDAS"))
        self.assertEqual(c["name"], "C.S. ARROYO DE LA VEGA")
        posted = [d["ctl00$ContenedorContenidoSeccion$txtDireccion"] for m, _, d in self.finder.calls if m == "POST"]
        self.assertEqual(posted, ["VEREDA DE PALACIO"])                  # the type word kept: it's part of the name here

    def test_two_streets_in_one_area_are_still_two_streets(self):
        c = run(CI.find("RDA. DE SEGOVIA 10, 4º IZQ", "MADRID"))
        self.assertEqual(c["name"], "C.S. PASEO IMPERIAL")

    def test_no_exact_street_offers_the_finders_closest(self):
        with self.assertRaises(CI.Choose) as e:
            run(CI.find("PLAZA DE LA VEREDA 1", "ALCOBENDAS"))
        self.assertTrue(e.exception.cands)
        self.assertIn("CALLE DE LA VEREDA DE PALACIO", [x["street"] for x in e.exception.cands])


class Conversation(Base):
    def test_did_you_mean_then_the_pick_then_the_centre(self):
        self.to_offer()
        ci = self.pend()["ci"]
        self.assertTrue(ci["line"])
        CI_find = CI.find

        async def find(line, town):
            return await CI_find("PLAZA DE LA VEREDA 1", "ALCOBENDAS")
        CI.find = find
        try:
            self.mark()
            self.say("", payload="hx:ci:find")
        finally:
            CI.find = CI_find
        got = self.last()
        self.assertIn("Did you mean one of these", got)
        self.assertNotIn("look yourself", got.lower())
        n = re.search(r"(\d)\. Calle De La Vereda De Palacio", got).group(1)   # the list's own number, as typed
        self.assertTrue(any(pl.startswith("hx:ci:pick:") for _, pl in self.buttons()))
        self.mark()
        self.say(n)
        self.assertIn("C.S. ARROYO DE LA VEGA", self.last())
        self.assertEqual(self.pend()["step"], "ci_route")

    def test_nothing_like_it_asks_for_the_street_as_on_the_padron(self):
        self.to_offer()
        CI_find = CI.find

        async def find(line, town):
            raise CI.Choose([], "SERMAS's finder has no “Calle Inventada, 9” in Madrid")
        CI.find = find
        try:
            self.mark()
            self.say("", payload="hx:ci:find")
        finally:
            CI.find = CI_find
        self.assertIn("as your padrón has them", self.last())
        self.assertNotIn("look yourself", self.last().lower())
        self.mark()
        self.say("Calle de la Vereda de Palacio 1, Alcobendas")
        self.assertIn("C.S. ARROYO DE LA VEGA", self.last())


class Again(Base):
    @unittest.skip('Sasha 194 · STRICT SPACES: a space is entered/left only by its word — this pinned the automatic switching the founder removed; CR to rewrite to the strict rule')
    def test_find_my_centre_again_rebuilds_from_the_forms_own_case(self):
        self.to_offer()
        self.say("", payload="hx:ci:no")                               # (the founder's run: the old lookup ended the step)
        self.assertNotIn("ci", self.pend() or {})
        self.mark()
        self.say("find my centre")
        self.assertIn("C.S. LAS CORTES", self.last())
        self.assertEqual(self.pend()["step"], "ci_route")


if __name__ == "__main__":
    unittest.main()


class TwoDevices(TC.Base):
    """CR 35 · the founder's laptop run: one conversation per account; RelocateMe waiting at "Postcode?" while EspañaMe's
    health card asked last (on the phone). "28010" is relocation's answer — never swallowed by the health card's question."""

    @unittest.skip('Sasha 194 · STRICT SPACES: a space is entered/left only by its word — this pinned the automatic switching the founder removed; CR to rewrite to the strict rule')

    def test_an_answer_goes_to_the_product_waiting_for_it(self):
        from tests.test_relocation_cr1 import OnWhatsApp as R
        for t in ("relocation", "first application", "me", "myself"):
            self.say(t)
        for a in R.ANSWERS[:R.ANSWERS.index("28010")]:
            self.say(a)
        self.assertEqual(self.bodies()[-1], "Postcode?")
        self.to_photo()                                            # the phone: EspañaMe → Salud → yes → the health card
        self.say("DEMO")
        self.say("", payload=f"hx:ts:ok:{self.pend()['ts_sha']}")
        self.say("", payload="hx:ts:m:NUEVA")
        self.say("", payload="hx:ts:addr:yes")
        self.say("28013")                                          # the health card's own postcode
        self.assertIn("mobile number", self.bodies()[-1])
        self.say("28010")                                          # the laptop: relocation's postcode
        self.assertEqual(self.bodies()[-1], "Province?")
