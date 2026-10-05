"""CR 20 · back and forth between WhatsApp and the web tab: ONE account, ONE case, ONE state, wherever the guest types.
A file started on the phone continues on the laptop at the same question with the same answers (and the reverse); a
Yale session picked on the laptop is "what's next?" on the phone; EspañaMe's health flow crosses with its own buttons.
Offline: the real WhatsApp turn and the real web turn (products.web.web_turn), the model and the schools faked.

    cd backend && python -m unittest tests.test_cross_channel_cr20 -v
"""
from __future__ import annotations

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
