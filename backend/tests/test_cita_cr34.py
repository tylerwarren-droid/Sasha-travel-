"""CR 34 · EspañaMe, from the form to the cita: the citizen's centro de salud from SERMAS's own finder (read live; here, the
page shapes read 6 Oct 2026), its routes — go, call (the founder's account only, read-back + one yes), or the Comunidad's
online cita sent to the phone (its CAPTCHA and Enviar the citizen's) — and the result in the itinerary with a calendar link
and what to bring (from the 1449F1's own §6). Never a login, a press or a slot search. Offline; specimens only.

    cd backend && python -m unittest tests.test_cita_cr34 -v
"""
from __future__ import annotations

import os
from unittest import mock

from booking_signer import guest_whatsapp as GW
from products.health import cita as CI
from tests import test_guest_whatsapp_s75 as TG
from tests import test_tarjeta_cr30 as TT

run = TG.run
FINDER_PAGE = ('<input type="hidden" name="__VIEWSTATE" id="__VIEWSTATE" value="v" />'
               '<input type="hidden" name="__EVENTVALIDATION" id="__EVENTVALIDATION" value="e" />'
               '<select name="ctl00$ContenedorContenidoSeccion$cbxLocalidades" id="ctl00_ContenedorContenidoSeccion_cbxLocalidades">'
               '<option value="073">HUMANES DE MADRID</option><option value="079">MADRID</option></select>')
RESULT_PAGE = ("<table><tbody><tr><td data-label=\"Dirección\"><a href='../RedAsistencial/DetalleAsistenciales.aspx?ID=454' "
               "class=\"link\">CALLE DE EJEMPLO GALIANO, 1</a></td><td data-label=\"Localidad\">MADRID</td></tr>"
               "<tr><td data-label=\"Dirección\"><a href='../RedAsistencial/DetalleAsistenciales.aspx?ID=453' class=\"link\">"
               "CALLE DE EJEMPLO, 1</a></td><td data-label=\"Localidad\">MADRID</td></tr></tbody></table>")
DETAIL_PAGE = ("<h1>Detalles del centro</h1><h2>Detalles del centro</h2><h3>C.S. LAS CORTES</h3><p>Código de centro: 2360</p>"
               "<p>Dirección postal: CRA DE SAN JERONIMO, 32</p><p>Municipio: MADRID</p><p>Código postal: 28014</p>"
               "<p>Horario del centro: Lunes a viernes de 8:00 a 21:00</p><p>Teléfono de información: 91 369 04 91</p>"
               "<p>Teléfono cita previa: 91 369 04 91</p><p>Otras modalidades de gestión de cita: Cita previa sanitaria por "
               "Internet</p><a>Ampliar el mapa de situación</a>")


class Finder:
    def __init__(self, result=RESULT_PAGE):
        self.calls, self.result = [], result

    async def __call__(self, method, url, data=None, cookies=None):
        self.calls.append((method, url, data))
        if "misCentroPorDireccion" in url:
            return 200, (FINDER_PAGE if method == "GET" else self.result), {"ASP.NET_SessionId": "s"}
        if "DetalleAsistenciales.aspx?ID=453" in url:
            return 200, DETAIL_PAGE, {}
        return 404, "", {}


class Base(TT.Base):
    def setUp(self):
        super().setUp()
        self.finder, self.saved_http = Finder(), CI.HTTP
        CI.HTTP = self.finder
        CI._CENTRES.clear()

    def tearDown(self):
        CI.HTTP = self.saved_http
        super().tearDown()

    def to_offer(self):
        self.to_photo()
        self.say("DEMO")
        self.say("", payload=f"hx:ts:ok:{self.pend()['ts_sha']}")
        self.answers()

    def to_centre(self):
        self.to_offer()
        self.say("", payload="hx:ci:find")


class FindIt(Base):
    def test_the_exact_address_on_sermas_own_finder(self):
        c = run(CI.find("C. EJEMPLO 1 P02 A", "MADRID"))
        self.assertEqual((c["name"], c["code"], c["phone_cita"], c["phone_e164"]), ("C.S. LAS CORTES", "2360", "91 369 04 91",
                                                                                   "+34913690491"))
        (m1, u1, _), (m2, u2, form), (m3, u3, _) = self.finder.calls
        self.assertEqual((m1, m2, m3), ("GET", "POST", "GET"))
        self.assertEqual(form["ctl00$ContenedorContenidoSeccion$cbxLocalidades"], "079")
        self.assertEqual(form["ctl00$ContenedorContenidoSeccion$txtDireccion"], "CALLE EJEMPLO")
        self.assertTrue(u3.endswith("ID=453"))                     # "EJEMPLO GALIANO" is another street: never the nearest

    def test_no_exact_match_is_said_never_guessed(self):
        with self.assertRaises(CI.Choose):
            run(CI.find("CALLE EJEMPLO 3", "MADRID"))
        with self.assertRaises(CI.Choose):
            run(CI.find("CALLE EJEMPLO 1", "ATLANTIS"))

    def test_what_to_bring_is_the_forms_own(self):
        self.assertIn("the 1449F1, printed and SIGNED by you", CI.bring("NUEVA"))
        self.assertIn("volante de empadronamiento", CI.bring("DOMICILIO")[-1])


class Routes(Base):
    def test_after_the_form_the_offer_then_the_centre_from_the_finder(self):
        self.to_offer()
        self.assertIn("Next: your centro de salud — I'll find it from your address on SERMAS's own finder.", self.said())   # CR 52
        self.mark()
        self.say("", payload="hx:ci:find")
        got = self.last()
        self.assertIn("C.S. LAS CORTES", got)
        self.assertIn("CRA DE SAN JERONIMO, 32, 28014 Madrid", got)
        self.assertIn("en horario de atención al público (8.30 a 20.30h)", got)
        self.assertEqual(self.pend()["step"], "ci_route")

    def test_i_will_just_go_goes_in_the_itinerary_with_what_to_bring(self):
        self.to_centre()
        self.say("", payload="hx:ci:go")
        self.mark()
        self.say("Tuesday 10:00")
        got = self.last()
        self.assertIn("C.S. LAS CORTES, Tuesday", got)
        self.assertIn("the 1449F1, printed and SIGNED by you", got)
        self.assertIn("https://calendar.google.com/calendar/render?", got)
        self.assertNotIn("ci", self.pend() or {})                   # the address and copy lines are dropped

    def test_online_goes_with_the_details_to_copy_and_the_captcha_is_theirs(self):
        self.to_centre()
        self.mark()
        self.say("", payload="hx:ci:web")
        got = self.last()
        self.assertIn(CI.SERMAS_REGISTRY["url"], got)
        self.assertIn("\n99999999R\n", "\n" + got + "\n")                      # each detail its own message
        self.assertIn("“No soy un robot” and Enviar: both yours", got)
        self.assertIn(CI.SERMAS_ONLINE_NEEDS_CIPA, got)             # SERMAS's own online cita: not before a first card
        self.mark()
        self.say("booked Thursday 9:30, code 12345")
        self.assertIn("(cita 12345)", self.last())

    def test_calling_is_the_founders_account_only(self):
        self.to_centre()
        self.mark()
        self.say("", payload="hx:ci:call")
        self.assertIn("isn't open yet", self.last())
        self.assertFalse([c for c in GW.api.calls if c[2] == "/api/booking/calls"])

    def test_the_founder_call_reads_back_first_and_dials_only_on_the_yes(self):
        from booking_signer import ladder_routes as LR
        reads = []

        class Store:
            async def put_read(self, r):
                reads.append(r)
        with mock.patch.dict(os.environ, {"FOUNDER_ACCOUNT_ID": TG.ACCOUNT}), mock.patch.object(LR, "LADDER_STORE", Store()):
            self.to_centre()
            self.say("", payload="hx:ci:call")
            self.say("Tuesday 10:00")
            (_, _, _, body), = [c for c in GW.api.calls if c[2] == "/api/booking/calls"]
            self.assertEqual(body["reservation"]["what"]["activity_venue_lang"],
                             "una cita para entregar la solicitud de la tarjeta sanitaria")
            self.assertIn("I agree to nothing else", self.said())
            self.assertFalse([c for c in GW.api.calls if c[2].endswith("/place")])
            self.say("", payload=self.buttons()[0][1])
            self.assertEqual(len([c for c in GW.api.calls if c[2].endswith("/place")]), 1)
            self.assertIn("watch_call", self.spawned)
            self.assertEqual(self.pend()["step"], "ci_booked")
            self.assertEqual(reads[0]["read"]["facts"][0]["value"], "+34913690491")       # the finder's own cita line
            self.assertIn("SERMAS's own centre finder", reads[0]["read"]["facts"][0]["source_label"])

    def test_not_now_keeps_nothing(self):
        self.to_offer()
        self.say("", payload="hx:ci:no")
        self.assertNotIn("ci", self.pend() or {})
        self.assertEqual(self.finder.calls, [])                     # no lookup without the yes


if __name__ == "__main__":
    TG.unittest.main()
