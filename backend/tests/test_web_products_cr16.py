"""CR 16 · the products on the web chat (the product tabs): the SAME router as WhatsApp, keyed "web:<account>" — a tab
opens its product's mode, buttons come back as quick replies, a pressed one is answered, the trip plan hands Sasha its
sentence, and anything that isn't the products' is None (Sasha's own web flow). Offline.

    cd backend && python -m unittest tests.test_web_products_cr16 -v
"""
from __future__ import annotations

from booking_signer import guest_whatsapp as GW
from products import store as ST, web as PWEB
from tests import test_guest_whatsapp_s75 as TG

run = TG.run
U = TG.ACCOUNT


class Web(TG.Base):
    def setUp(self):
        super().setUp()
        self.saved = ST.STORE
        ST.STORE = ST.MemoryCaseStore()

    def tearDown(self):
        ST.STORE = self.saved
        super().tearDown()

    def turn(self, message="", mode=None, payload=None):
        return run(PWEB.web_turn(U, message, mode=mode, payload=payload, now=self.now))

    def test_each_tab_opens_its_mode(self):
        r = self.turn(mode="relocation")
        self.assertIn("I never file anything", r["response"])
        r = self.turn(mode="campus")
        self.assertIn("CampusMe here", r["response"])
        r = self.turn(mode="espana")
        self.assertIn("EspañaMe 🇪🇸", r["response"])
        self.assertEqual([q["payload"] for q in r["quick_replies"]], ["hx:es:health", "hx:es:padron", "hx:es:movistar"])

    def test_a_pressed_button_is_answered(self):
        self.turn(mode="espana")
        r = self.turn(payload="hx:es:padron")
        self.assertIn("🏛 *Padrón* — CONCEPT, not built yet", r["response"])
        r = self.turn(payload="hx:es:health")
        self.assertIn("never why you need a doctor", r["response"])
        self.assertEqual([q["title"] for q in r["quick_replies"]], ["Yes, continue", "No"])

    def test_relocation_through_to_the_file_and_the_trip_hand_off(self):
        for t in ("first", "me", "myself"):
            self.turn(t) if t != "first" else (self.turn(mode="relocation"), self.turn(t))
        r = self.turn("DEMO")
        self.assertIn("Your EX-01 is prepared", r["response"])
        self.assertTrue(any(m["url"].endswith("EX-01-prepared.pdf") for m in r["media"]))
        for t in ("SIGNED", "UK", "SKIP", "1 March 2027"):
            self.turn(t)
        r = self.turn("book my flights")
        self.assertIn("Which city will you fly from?", r["response"])
        r = self.turn("London")
        self.assertEqual(r["handoff"], "flights from London to Madrid on 2027-03-01 for 1")

    def test_not_the_products_message_is_none(self):
        self.assertIsNone(self.turn("dinner for 2 tonight in Chamberí"))
        self.assertIsNone(run(PWEB.web_turn(None, "", mode="campus")))          # signed out: no product state at all
        self.assertIsNone(self.turn(mode="vietnam"))

    def test_web_and_whatsapp_keep_separate_conversations(self):
        self.turn(mode="campus")
        self.link()
        self.say("relocation")                                                   # the WhatsApp line, its own state
        self.assertIn("I never file anything", "\n".join(self.bodies()))
        r = self.turn("sasha")
        self.assertIn("Back to Sasha", r["response"])
