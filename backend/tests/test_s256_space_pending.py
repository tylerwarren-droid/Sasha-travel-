"""Sasha 256 · T36 — A PENDING QUESTION BELONGS TO ITS SPACE. Found on Tyler's WhatsApp (13 Oct 2026, 11:03–11:04 Madrid): "Sasha" →
"You're in Sasha (travel)", then "Can you make a reservation for me in Madrid" → CampusMe's old "Which universities? …". The web's
own product state (webstate) still held CampusMe's question; the WhatsApp brain asked products.web.current_space — the web's
state, not the one space — and handed the message to CampusMe, which then wrote "campus" back as the space.

Now (products/whatsapp.product_turn, the one place WhatsApp and the web pass through; products/web.current_space): only the CURRENT
space's pending question may answer a message; any other is parked (kept, said once) and the message goes on; the space changes
only by the person's own word. Fictional number; the brain is a stand-in (no model).

    cd backend && python -m unittest tests.test_s256_space_pending -v
"""
from __future__ import annotations

from unittest import mock

from booking_signer import guest_whatsapp as GW, wa_agent as WA
from products import space as SPC, store as ST, web as PWEB
from tests import test_guest_whatsapp_s75 as TG

run = TG.run
U = TG.ACCOUNT


class Base(TG.Base):
    def setUp(self):
        super().setUp()
        self.saved = ST.STORE
        ST.STORE = ST.MemoryCaseStore()
        SPC._SPACE.pop(U, None)
        self.brain = []

        async def agent(ch, body, payload, st, out, now, button_text="", voice_in=False):
            self.brain.append(body)
            out.text("brain: " + body)
            return "x"
        self.p = mock.patch.object(WA, "agent_turn", agent)
        self.p.start()
        self.env = mock.patch.dict("os.environ", {"SASHA_SWITCHING": "all"})   # the space switching Tyler's own number has
        self.env.start()
        self.link()

    def tearDown(self):
        self.env.stop()
        self.p.stop()
        ST.STORE = self.saved
        SPC._SPACE.pop(U, None)
        super().tearDown()

    def web(self, message="", mode=None):
        return run(PWEB.web_turn(U, message, mode=mode, now=self.now, signed_in=True))

    def wa(self, body):
        n = len(self.bodies())
        self.say(body)
        return "\n".join(self.bodies()[n:])


class TylersCase(Base):
    def test_switch_then_a_travel_request_reaches_the_brain_never_the_old_question(self):
        r = self.web(mode="campus")                                   # CampusMe asks on the web
        self.assertIn("I'll read their own visit calendars", r["response"])
        self.assertEqual(run(SPC.current_space(U)), "campus")
        switched = self.wa("Sasha")                                   # the person's own word: back to travel
        self.assertNotIn("Which universities", switched)
        said = self.wa("Can you make a reservation for me in Madrid")
        self.assertNotIn("Which universities", said)
        self.assertIn("Can you make a reservation for me in Madrid", self.brain)
        self.assertEqual(run(SPC.current_space(U)), "sasha")         # a product never moves the space by itself

    def test_the_webs_question_answers_only_in_its_own_space(self):
        self.web(mode="campus")
        self.assertEqual(run(PWEB.current_space(U)), "campus")
        run(SPC.set_space(U, "sasha", "whatsapp"))
        self.assertIsNone(run(PWEB.current_space(U)))                # not the current space: it doesn't capture anything

    def test_the_parked_question_is_kept_said_once_and_its_word_brings_it_back(self):
        self.web(mode="campus")
        run(SPC.set_space(U, "sasha", "whatsapp"))
        r = self.web("Can you make a reservation for me in Madrid")   # on the web too: parked, said once, not CampusMe's
        said = (r or {}).get("response") or ""
        self.assertNotIn("Which universities", said)
        r2 = self.web("a table for two tonight")
        self.assertNotIn("saved for later", (r2 or {}).get("response") or "")   # once
        r3 = self.web("campus")                                       # its own word: back where it was
        self.assertIn("campus", ((r3 or {}).get("response") or "").lower())

    def test_inside_its_own_space_it_still_answers(self):
        self.web(mode="campus")
        r = self.web("Yale and Brown")
        self.assertIsNotNone(r)
        self.assertEqual(run(SPC.current_space(U)), "campus")


if __name__ == "__main__":
    import unittest
    unittest.main()
