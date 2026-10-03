"""CR 10 · ONE SASHA, NOT ROOMS: CampusMe, relocation and health are skills inside one conversation. A message that isn't
the product's goes to Sasha's own flow, in the same chat, with the product's context; the product resumes where it was.
No "Say EXIT" anywhere. Offline; the real WhatsApp turn; the model is never called.

    cd backend && python -m unittest tests.test_one_sasha_cr10 -v
"""
from __future__ import annotations

import json

from booking_signer import guest_whatsapp as GW
from products import store as ST
from tests import test_guest_whatsapp_s75 as TG

run = TG.run


class OneSasha(TG.Base):
    def setUp(self):
        super().setUp()
        self.saved = ST.STORE
        ST.STORE = ST.MemoryCaseStore()
        self.link()

    def tearDown(self):
        ST.STORE = self.saved
        super().tearDown()

    def said(self):
        return "\n".join(self.bodies() + [b for b, _ in GW.SENDER.contents])

    def st(self):
        return run(GW.STORE.get_state(GW.wa_key(TG.GUEST)))

    def to_passport(self):
        for t in ("relocation", "first", "me", "myself"):
            self.say(t)
        self.assertEqual(self.bodies()[-1], "Your passport number?")

    def test_relocation_then_flights_then_back_to_relocation(self):
        self.to_passport()
        n = len(GW.SENDER.sent)
        self.say("book me flights to Madrid on 1 March")
        sasha = "\n".join(s["body"] for s in GW.SENDER.sent[n:])
        self.assertEqual(sasha, GW.ASK_ONE)                                   # Sasha's own flow answered, in the same chat
        self.assertIsNone(self.st()["pending"])                               # her pending is hers again
        self.assertIn("[Relocation: moving to Madrid, Spain]", json.dumps(self.st()["history"], ensure_ascii=False))
        self.say("EXAMPLE000")                                                # an answer to relocation's own question
        self.assertEqual(self.bodies()[-1], "Your first surname, exactly as on your passport?")
        self.assertEqual(self.st()["pending"]["facts"]["applicant"]["passport_number"]["value"], "EXAMPLE000")

    def test_the_keyword_alone_says_where_we_were(self):
        self.to_passport()
        self.say("I need a flight from London to Madrid on 1 March")
        self.say("relocation")
        self.assertEqual(self.bodies()[-1], "Back to your EX-01. Your passport number?")

    def test_sashas_own_question_keeps_its_answers(self):
        self.to_passport()
        self.say("dinner for 2 in Chamberí on Saturday at 21:00")            # Sasha: cards, her own pending
        self.assertEqual(self.st()["pending"]["kind"], "cards")
        self.say("1")                                                         # her card, not a passport number
        self.assertNotIn("first surname", self.bodies()[-1])
        self.assertIn("/api/booking/venues/read", self.api_paths())
        self.say("relocation")                                                # and relocation is exactly where it was
        self.assertEqual(self.bodies()[-1], "Back to your EX-01. Your passport number?")

    def test_a_product_answer_is_never_taken_by_sasha(self):
        self.to_passport()
        self.say("not a passport!")                                           # not a passport number: relocation re-asks
        self.assertIn("letters and digits", self.bodies()[-1])
        self.assertNotIn("/api/booking/venues/find", self.api_paths())

    def test_context_is_minimum_necessary(self):
        self.to_passport()
        for a in ("EXAMPLE000", "Ejemplo", "NONE", "Ana"):
            self.say(a)
        self.say("book me flights")
        hist = json.dumps(self.st()["history"], ensure_ascii=False)
        self.assertIn("[Relocation: moving to Madrid, Spain; applicant Ana Ejemplo]", hist)
        self.assertNotIn("EXAMPLE000", hist)                                  # never a passport fact

    def test_no_wall_anywhere(self):
        self.to_passport()
        self.say("what's the weather like")                                   # neither relocation's nor a booking: re-asked
        self.say("campus")
        self.say("salud")
        self.assertNotRegex(self.said(), r"(?i)say exit|go back to sasha")

    def test_health_hands_sasha_only_the_city(self):
        self.say("health I need a doctor this week")
        self.say("", payload="hx:consent:yes")
        self.say("", payload="hx:priv")
        self.say("cancel my dinner at Botavara")                              # Sasha's: a cancellation
        hist = json.dumps(self.st()["history"], ensure_ascii=False)
        self.assertIn("[Health: in Madrid, Spain]", hist)
        self.assertNotRegex(hist, r"(?i)doctor|médico|gp")
