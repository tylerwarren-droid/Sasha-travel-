"""CR 142 · STOP-SHIP (Tyler's WhatsApp, 29 Oct 16:55): in Applied Diligence's space "What is the status of the Prada case?" got AD's
greeting twice and never reached AD. Its words matched the products' resume shortcut (products/whatsapp._STATUS: "status of", "next
step", "what's next", "where was i" — CR 20's "where was I?" for a set-aside product), which answered with the space's say-back, and
AD's say-back IS its greeting (diligence.RESUME_LINE). Now, in AD's space, every message goes to AD's door to be routed by its meaning
(status / next steps / do N / questionnaire / interview / evidence / open); the greeting answers only the word on its own.

    cd backend && python -m unittest tests.test_cr142_ad_meaning -v
"""
from __future__ import annotations

from products import diligence as DG
from tests import test_cr128_diligence as T128

ASKS = ("What is the status of the Prada case?", "what's the status of Prada", "status of Lehman", "what's next on Prada",
        "next steps", "what now", "where was I", "do 2", "send the questionnaire", "interview Jon Tester",
        "add this to Prada: https://ft.com/x", "do a DD investigation on Prada Retail UK Limited", "hi")


class EveryMessageByItsMeaning(T128.Base):
    def test_a_tylers_two_messages_reach_ad(self):
        self.say("diligence")
        n = len(self.bodies())
        self.say("What is the status of the Prada case?")
        self.say("What is the status of the Prada case?")
        self.assertEqual(self.sent_to_ad(), [("What is the status of the Prada case?", "diligence", True)] * 2)
        self.assertEqual(len(self.bodies()), n)                                   # no greeting: AgAPI sends AD's answer

    def test_b_the_whole_class(self):
        self.say("diligence")
        n = len(self.bodies())
        for t in ASKS:
            self.say(t)
        self.assertEqual(self.sent_to_ad(), [(t, "diligence", True) for t in ASKS])
        self.assertEqual(len(self.bodies()), n)
        self.assertEqual(self.space(), "diligence")

    def test_c_the_word_alone_is_the_only_greeting(self):
        self.say("diligence")
        self.say("what's the status of Prada")
        self.say("diligence")
        self.assertTrue(self.bodies()[-1].endswith(DG.LINE))
        self.assertEqual(len(self.sent_to_ad()), 1)

    def test_d_the_word_with_a_status_question_goes_straight_in(self):
        self.say("diligence what's the status of the Prada case?")
        self.assertEqual(self.sent_to_ad(), [("what's the status of the Prada case?", "diligence", True)])
