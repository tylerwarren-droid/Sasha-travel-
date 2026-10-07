"""CR 20 · back and forth between WhatsApp and the web tab: ONE account, ONE case, ONE state, wherever the guest types.
A file started on the phone continues on the laptop at the same question with the same answers (and the reverse); a
Yale session picked on the laptop is "what's next?" on the phone; EspañaMe's health flow crosses with its own buttons.
Offline: the real WhatsApp turn and the real web turn (products.web.web_turn), the model and the schools faked.

    cd backend && python -m unittest tests.test_cross_channel_cr20 -v
"""
from __future__ import annotations
import unittest

from booking_signer import guest_whatsapp as GW
from products import store as ST, web as PWEB
from tests import test_campusme_cr1 as TC
from tests import test_guest_whatsapp_s75 as TG
from tests import test_relocation_m3_cr1 as TR

run = TG.run


def web(t, message="", mode=None, payload=None):
    return run(PWEB.web_turn(TG.ACCOUNT, message, mode=mode, payload=payload, now=t.now, signed_in=True))


def wa_pend(t):
    return run(GW.STORE.get_state(GW.wa_key(TG.GUEST)))["pending"]


class Relocation(TR.Flow):
    def test_phone_then_laptop_then_phone(self):
        for t in ("relocate", "first", "me", "myself"):                       # two questions answered, then the passport
            self.say(t)
        self.photo()
        self.assertIn("• Passport number: AB1234567 ✓", "\n".join(self.bodies() + [b for b, _ in GW.SENDER.contents]))
        # the laptop: the SAME application, at the same question — the read-back, with its own buttons
        r = web(self, mode="relocation")
        self.assertTrue(r["response"].startswith("Back to your EX-01."))
        self.assertIn("AB1234567", r["response"])
        self.assertEqual([q["payload"] for q in r["quick_replies"]][:1], ["rx:doc:yes"])
        r = web(self, payload="rx:doc:yes")                                  # one step finished on the laptop
        self.assertIn("Your second surname?", r["response"])
        # the phone knows: its next answer is the laptop's next question, the passport fields kept
        self.say("Prueba")
        a = wa_pend(self)["facts"]["applicant"]
        self.assertEqual((a["passport_number"]["value"], a["surname_2"]["value"]), ("AB1234567", "Prueba"))
        self.assertNotIn("Your second surname?", self.bodies()[-1])             # never asked twice
        # and the laptop sees the phone's answer
        r = web(self, "what's next for my application?")
        self.assertIn("Back to your EX-01.", r["response"])
        self.assertTrue(r["response"].endswith(self.bodies()[-1]))

    def test_a_file_finished_on_one_channel_is_not_resumed_from_the_others_old_copy(self):
        self.start()
        web(self, mode="relocation")
        web(self, "sasha")                                                     # dropped on the laptop
        self.say("me")                                                          # the phone's stale copy says "asking…"
        self.assertNotIn("Your passport number?", "\n".join(self.bodies()[-1:]))
        self.assertIsNone((wa_pend(self) or {}).get("product"))


class Campus(TC.Fixtures):
    def setUp(self):
        super().setUp()
        self.link()

    @unittest.skip('Sasha 194 · STRICT SPACES: a space is entered/left only by its word — this pinned the automatic switching the founder removed; CR to rewrite to the strict rule')

    def test_pick_on_the_laptop_whats_next_on_the_phone(self):
        r = web(self, "campus visits at Yale on October 14 for my son")
        self.assertIn("Campus Tour", r["response"])
        r = web(self, "1")                                                     # a Yale session picked on the laptop
        nxt = r["response"]
        self.say("what's next for the Yale visit?")
        self.assertTrue(self.bodies()[-1].startswith("Back to your campus visits."))
        self.assertTrue(self.bodies()[-1].endswith(nxt.split("\n\n")[-1]))
        self.assertEqual(wa_pend(self)["product"], "campus")                   # the phone can answer it now


class Espana(TG.Base):
    def setUp(self):
        super().setUp()
        self.saved = ST.STORE
        ST.STORE = ST.MemoryCaseStore()
        self.link()

    def tearDown(self):
        ST.STORE = self.saved
        super().tearDown()

    def test_health_starts_on_the_phone_and_continues_on_the_laptop(self):
        self.say("españa")
        self.say("1")
        self.assertIn("never why you need a doctor", GW.SENDER.contents[-1][0])
        r = web(self, mode="espana")                                          # the laptop: the same consent question
        self.assertTrue(r["response"].startswith("Back to your health appointment."))
        self.assertEqual([q["payload"] for q in r["quick_replies"]], ["hx:consent:yes", "hx:consent:no"])
        r = web(self, payload="hx:consent:yes")
        self.assertIn("A private clinic", r["response"])
        self.say("", payload="hx:new")                                         # back on the phone: the next step
        self.assertIn("Padrón (town hall)", "\n".join(self.bodies() + [b for b, _ in GW.SENDER.contents]))


class ItineraryIsSashas(TR.Flow):
    def test_an_itinerary_question_mid_file_goes_to_sasha(self):
        self.start()
        self.say("what do I have on 12 November?")
        self.assertNotIn("Your passport number?", self.bodies()[-1])             # not re-asked: Sasha's own flow answered
        self.say("relocation")
        self.assertTrue(self.bodies()[-1].startswith("Back to your EX-01."))


class BookingInsideAProduct(TR.Flow):
    """CR 20 (5): "book me a 60-minute massage near my hotel on arrival" inside a product → Sasha's booking flow WITH the
    product's context, then back to the product."""

    def setUp(self):
        super().setUp()
        self.found, self.saved_find = [], GW._find

        async def find(ctx, f, draft):
            self.found.append((f, draft, (ctx.get("p") or {}).get("Body") if isinstance(ctx.get("p"), dict) else None))
            ctx["out"].text(f"[venue cards: {f.get('what')} in {f.get('where')} near {f.get('near')}]")
        GW._find = find

    def tearDown(self):
        GW._find = self.saved_find
        super().tearDown()

    def to_entry(self):
        for t in ("relocation", "first", "me", "myself", "DEMO", "SIGNED", "UK", "SKIP", "1 March 2027"):
            self.say(t)

    def test_relocation_whatsapp_then_back_to_the_file(self):
        self.to_entry()
        self.say("book me a 60-minute massage near my hotel on arrival")
        said = "\n".join(self.bodies()[-3:])
        self.assertIn("in Madrid, near Calle de Ejemplo 12, on Mon 1 Mar 2027 (your entry date)", said)
        self.assertIn("say “relocation” to come back", said)
        (f, draft, _), = self.found                                               # Sasha's OWN booking flow, with the context
        self.assertEqual((f["where"], f.get("country"), f.get("near")), ("Madrid", "ES", "Calle de Ejemplo 12"))
        self.say("relocation")
        self.assertTrue(self.bodies()[-1].startswith("Back to your EX-01."))

    @unittest.skip('Sasha 194 · STRICT SPACES: a space is entered/left only by its word — this pinned the automatic switching the founder removed; CR to rewrite to the strict rule')

    def test_the_same_on_the_web_tab(self):
        self.to_entry()
        r = web(self, "book me a 60-minute massage near my hotel on arrival")
        self.assertEqual(r["handoff"], "book me a 60-minute massage in Madrid near Calle de Ejemplo 12 on 2027-03-01")
        self.assertIn("(your entry date)", r["response"])

    @unittest.skip('Sasha 194 · STRICT SPACES: a space is entered/left only by its word — this pinned the automatic switching the founder removed; CR to rewrite to the strict rule')

    def test_a_booked_hotel_is_the_place(self):
        from products import itinerary as IT
        saved = IT.hotel_on

        async def hotel(account, on):
            return "Hotel Ejemplo Gran Vía"
        IT.hotel_on = hotel
        try:
            self.to_entry()
            r = web(self, "book me a 60-minute massage near my hotel on arrival")
            self.assertEqual(r["handoff"], "book me a 60-minute massage in Madrid near Hotel Ejemplo Gran Vía on 2027-03-01")
            self.assertIn("near your hotel, Hotel Ejemplo Gran Vía", r["response"])
        finally:
            IT.hotel_on = saved

    @unittest.skip('Sasha 194 · STRICT SPACES: a space is entered/left only by its word — this pinned the automatic switching the founder removed; CR to rewrite to the strict rule')

    def test_espana_has_no_date_to_invent(self):
        self.say("españa")
        self.say("1")
        r = web(self, "book me a 60-minute massage near my hotel on arrival")
        self.assertEqual(r["handoff"], "book me a 60-minute massage in Madrid")


class ConductHook(BookingInsideAProduct):
    def test_in_context_for_conduct_before_her_handoff(self):
        self.to_entry()
        r = run(PWEB.in_context(TG.ACCOUNT, "book me a 60-minute massage near my hotel on arrival", signed_in=True, now=self.now))
        self.assertEqual(r["sentence"], "book me a 60-minute massage in Madrid near Calle de Ejemplo 12 on 2027-03-01")
        self.assertEqual(r["product"], "relocation")
        self.assertIsNone(run(PWEB.in_context(TG.ACCOUNT, "book me a 60-minute massage near my hotel on arrival", signed_in=None)))
        self.assertIsNone(run(PWEB.in_context(TG.ACCOUNT, "book me a massage in Madrid tomorrow at 10", signed_in=True, now=self.now)))
