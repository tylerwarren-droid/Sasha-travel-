"""CR 36 · the product preview opens on its opener for tomorrow: a tab opened with nothing answered yet starts on the opener
(never the bare first question); once something is answered it says where it was ("Back to your EX-01. …"), and the
product's own name while it's asking never re-asks the same question (which the never-ask-twice line turned into a lecture).

    cd backend && python -m unittest tests.test_opener_cr36 -v
"""
from __future__ import annotations

from products import web as PWEB
from tests import test_guest_whatsapp_s75 as TG
from tests import test_web_media_cr30 as W

run = TG.run


class Opener(W.WebPhoto):
    def tab(self):
        return run(PWEB.web_turn(TG.ACCOUNT, "", mode="relocation", now=self.now, signed_in=True))["response"]

    def test_opened_twice_with_nothing_answered_it_is_the_opener_both_times(self):
        first = self.tab()
        self.assertTrue(first.startswith("Let's get your Spanish residence file ready"))
        self.assertEqual(self.tab(), first)

    def test_once_answered_it_says_where_it_was_never_the_lecture(self):
        self.tab()
        W.web(self, "first")
        again = self.tab()
        self.assertTrue(again.startswith("Back to your EX-01."), again)
        self.assertNotIn("I asked that a moment ago", again)
        self.assertIn("economic resources", again)

    def test_its_own_name_typed_while_it_asks(self):
        W.web(self, "relocation")
        W.web(self, "first")
        r = W.web(self, "relocation")["response"]
        self.assertTrue(r.startswith("Back to your EX-01."), r)


if __name__ == "__main__":
    TG.unittest.main()


class Booked(TG.unittest.TestCase):
    """CR 36 · the citizen's booked cita, as they send it: their words or the office's own confirmation, pasted."""

    def test_the_confirmation_as_pasted(self):
        from datetime import date, datetime, timezone
        from products.health import cita as CI
        now = datetime(2026, 10, 6, 12, 0, tzinfo=timezone.utc)
        self.assertEqual(CI.when("jueves, 8 de octubre de 2026 a las 10:30", now), (date(2026, 10, 8), "10:30"))
        self.assertEqual(CI.when("Fecha: 08/10/2026 Hora: 10:30 Código de cita: A1B2C", now), (date(2026, 10, 8), "10:30"))
        self.assertEqual(CI.when("booked Thursday 9:30, code 12345", now), (date(2026, 10, 8), "09:30"))

    def test_the_registry_page_opens_on_sermas_own_service(self):
        from products.health import cita as CI
        self.assertTrue(CI.SERMAS_REGISTRY["url"].endswith("OFIREG?servicio=3152"))   # the page opens on "Solicitar cita"
        self.assertEqual(CI.SERMAS_REGISTRY["service"], "01-REGISTRO DE DOCUMENTACIÓN")
