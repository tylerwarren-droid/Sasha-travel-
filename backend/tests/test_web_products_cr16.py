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
        return run(PWEB.web_turn(U, message, mode=mode, payload=payload, now=self.now, signed_in=True))

    def test_each_tab_opens_its_mode(self):
        r = self.turn(mode="relocation")
        self.assertEqual(r["response"], "Let's get your Spanish residence file ready. You sign it and you lodge it — I never "
                                        "file anything for you. Is this your first application, or a renewal?")   # EU 150
        r = self.turn(mode="campus")
        self.assertIn("I'll read their own visit calendars", r["response"])
        r = self.turn(mode="espana")
        self.assertIn("One rule first: I prepare everything, and you sign in and press", r["response"])
        self.assertEqual([q["payload"] for q in r["quick_replies"]], ["hx:es:salud", "hx:es:padron", "hx:es:identity"])

    def test_a_pressed_button_is_answered(self):
        self.turn(mode="espana")
        r = self.turn(payload="hx:es:padron")
        self.assertIn("○ *Padrón — registering at the town hall* — CONCEPT, not built yet", r["response"])
        r = self.turn(payload="hx:es:salud")
        self.assertIn("never why you need a doctor", r["response"])
        self.assertEqual([q["title"] for q in r["quick_replies"]], ["Yes, continue", "No"])

    def test_relocation_through_to_the_file_and_the_trip_hand_off(self):
        for t in ("first", "me", "myself"):
            self.turn(t) if t != "first" else (self.turn(mode="relocation"), self.turn(t))
        r = self.turn("DEMO")
        self.assertIn("Your EX-01 is prepared", r["response"])
        self.assertTrue(any(m["url"].endswith("EX-01-card.jpg") and m["link"].endswith("EX-01-prepared.pdf")
                            and "Open the full PDF" not in m["caption"] for m in r["media"]))   # CR 33 · the card opens the PDF
        for t in ("SIGNED", "UK", "SKIP", "1 March 2027"):
            self.turn(t)
        r = self.turn("book my flights")
        self.assertIn("Which city will you fly from?", r["response"])
        r = self.turn("London")
        self.assertEqual(r["handoff"], "flights from London to Madrid on 2027-03-01 for 1")

    def test_not_the_products_message_is_none(self):
        self.assertIsNone(self.turn("dinner for 2 tonight in Chamberí"))
        self.assertIsNone(run(PWEB.web_turn(None, "", mode="campus")))          # no account: no product state at all
        self.assertIsNone(self.turn(mode="vietnam"))

    def test_a_mode_word_on_whatsapp_and_exit_on_the_web_share_one_conversation(self):   # CR 20: one account, one state
        self.turn(mode="campus")
        self.link()
        self.say("relocation")                                                   # the WhatsApp line, its own state
        self.assertIn("I never file anything", "\n".join(self.bodies()))
        r = self.turn("sasha")
        self.assertIn("Back to Sasha", r["response"])

    def test_a_product_under_way_says_where_it_was(self):
        self.turn(mode="relocation")
        self.turn("first")
        self.turn("me")
        self.turn("sasha")                                                       # set aside? no — exit drops it; resume via mode
        self.turn(mode="relocation")
        self.turn("first")
        r = self.turn(mode="campus")                                             # relocation set aside mid-way
        r = self.turn(mode="relocation")
        self.assertIn("Back to your EX-01.", r["response"])


class SignedOut(Web):
    def test_a_visitor_without_a_verified_token_never_reaches_the_products(self):
        """The public demo account IS the founder's real account (CR 3): an anonymous visitor must never act on it."""
        self.turn(mode="relocation")                                             # the founder's own file, under way
        self.turn("first")
        r = run(PWEB.web_turn(U, "", mode="relocation", now=self.now))          # the same account, but no signed_in
        self.assertEqual(r["response"], "Sign in to use RelocateMe — it works on your own account: your own file, "
                                        "your own visits, your own itinerary.")
        self.assertIsNone(run(PWEB.web_turn(U, "me", now=self.now)))             # never an answer to his file's question
        self.assertIsNone(run(PWEB.web_turn(U, "book my flights", now=self.now)))   # never his itinerary
        self.assertIsNone(run(PWEB.web_turn(U, "", payload="hx:es:health", now=self.now)))
