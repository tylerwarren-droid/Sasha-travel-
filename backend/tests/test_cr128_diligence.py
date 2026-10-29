"""CR 128 · "DILIGENCE": Applied Diligence gets its WORD in the ONE switch, like "campus" / "relocate" / "espana" (Tyler, 27 Oct).
On entry ONE line; inside, every message goes to AgAPI's door (space: "diligence"); leaving works as for the others; outside the space
nothing goes to AD. Offline: AgAPI's op is stood in (agapi/venue_submit.whatsapp_inbound), the real WhatsApp turn runs.

    cd backend && python -m unittest tests.test_cr128_diligence -v
"""
from __future__ import annotations

import pathlib
import re
from unittest import mock

from agapi import venue_submit as VS
from products import diligence as DG, space as SPC, store as ST, whatsapp as PW
from tests import test_guest_whatsapp_s75 as TG

run = TG.run
ROOT = pathlib.Path(__file__).resolve().parents[1]


class Base(TG.Base):
    def setUp(self):
        super().setUp()
        self.saved_st = ST.STORE
        ST.STORE = ST.MemoryCaseStore()
        self.addCleanup(lambda: setattr(ST, "STORE", self.saved_st))
        self.answer = {"matched": True, "kept": True, "ad": "door", "replied": True}
        self.ad = mock.AsyncMock(side_effect=lambda *a, **k: dict(self.answer))
        p = mock.patch.object(VS, "whatsapp_inbound", self.ad)
        p.start()
        self.addCleanup(p.stop)
        self.link()

    def sent_to_ad(self):
        return [(c.args[1], c.kwargs.get("space"), c.kwargs.get("guest")) for c in self.ad.call_args_list]

    def space(self):
        return run(SPC.current_space(TG.ACCOUNT))


class TheWord(Base):
    def test_a_the_word_enters_with_one_line_any_case(self):
        for w in ("diligence", "Diligence", "DILIGENCE", "diligense"):   # the word, mistyped too — as "relocaton" / "campsu"
            self.say("sasha")
            n = len(self.bodies())
            self.say(w)
            self.assertEqual(len(self.bodies()), n + 1, w)
            self.assertTrue(self.bodies()[-1].endswith(DG.LINE), (w, self.bodies()[-1]))
            self.assertEqual(self.space(), "diligence", w)
        self.assertEqual(self.sent_to_ad(), [])                                   # entering says the line; nothing reaches AD

    def test_b_inside_every_message_goes_to_ads_door(self):
        self.say("diligence")
        n = len(self.bodies())
        for t in ("link tyler@example.com", "123456", "investigate Lehman Brothers", "yes", "book a table for two tonight"):
            self.say(t)
        self.assertEqual(self.sent_to_ad(), [(t, "diligence", True) for t in
                                             ("link tyler@example.com", "123456", "investigate Lehman Brothers", "yes", "book a table for two tonight")])
        self.assertEqual(len(self.bodies()), n)                                   # AgAPI sent AD's replies; Sasha adds nothing

    def test_c_the_word_with_an_ask_goes_straight_in(self):
        self.say("diligence investigate Lehman Brothers")
        self.assertEqual(self.sent_to_ad(), [("investigate Lehman Brothers", "diligence", True)])


class Leaving(Base):
    def test_a_campus_and_back(self):
        self.say("diligence")
        self.say("campus")
        self.assertEqual(self.space(), "campus")
        self.assertNotIn(DG.LINE, self.bodies()[-1])
        self.say("diligence")
        self.assertTrue(self.bodies()[-1].endswith(DG.LINE))
        self.assertEqual(self.space(), "diligence")
        self.say("investigate Lehman Brothers")
        self.assertEqual(self.sent_to_ad(), [("investigate Lehman Brothers", "diligence", True)])

    def test_b_sasha_leaves_and_nothing_goes_to_ad_after(self):
        TG.stand_in_brain(self)
        self.say("diligence")
        self.say("sasha")
        self.assertEqual(self.bodies()[-1].split("\n")[-1], "Back to Sasha — ask me anything: a booking, a flight, your plans.")
        self.say("book a table for two tonight")
        self.assertEqual(self.sent_to_ad(), [])   # Sasha 315 MOVED: after "sasha", travel is Sasha's; an AD question goes by meaning
        self.assertEqual(self.brain_saw, ["book a table for two tonight"])
        self.assertEqual(self.space(), "sasha")


class WhatAgAPISays(Base):
    def test_a_outside_the_beta_said_here(self):
        self.answer = {"matched": True, "ad": "closed", "replied": False}
        self.say("diligence")
        self.say("investigate Lehman Brothers")
        self.assertTrue(self.bodies()[-1].endswith(DG.CLOSED))

    def test_b_agapi_down_never_silent(self):
        self.answer = {"matched": False, "why": "upstream_unreachable"}
        self.say("diligence")
        self.say("investigate Lehman Brothers")
        self.assertTrue(self.bodies()[-1].endswith(DG.DOWN))


class OutsideNothingGoesToAD(Base):
    def test_a_never_from_sasha(self):   # Sasha 315 MOVED (Tyler: "the agent should know what I'm talking about"): from travel, only
        TG.stand_in_brain(self)          # what MEANS AD reaches AD (products/router.py, tests/test_s315.py); nothing else, the space unchanged
        for t in ("ad hoc meeting tomorrow", "book a table for two tonight"):
            self.say(t)
        self.assertEqual(self.sent_to_ad(), [])
        self.say("due diligence on Acme")
        self.assertEqual(self.sent_to_ad(), [("due diligence on Acme", "diligence", True)])
        self.assertEqual(self.space(), "sasha")


class RootTest(TG.unittest.TestCase):
    def test_a_one_switch(self):
        """(1)/(2): the word is read in ONE place — products/whatsapp.py's keyword switch, beside campus/relocate/españa; AD's door is
        reached only from its space (products/diligence.turn); the webhook's first call carries no space."""
        self.assertIn('("diligence", _DILIGENCE)', (ROOT / "products" / "whatsapp.py").read_text())
        users = sorted(str(f.relative_to(ROOT)) for f in ROOT.rglob("*.py")
                       if "tests" not in f.parts and re.search(r'space\s*=\s*"diligence"', f.read_text()))
        self.assertEqual(users, ["products/diligence.py"])
        self.assertNotRegex((ROOT / "booking_signer" / "inbound_phone.py").read_text(), r"space\s*=")

    def test_b_a_space_like_the_others(self):
        self.assertIn("diligence", SPC.SPACES)
        self.assertEqual((SPC.normalize("diligence"), SPC.NAME["diligence"]), ("diligence", "Applied Diligence"))
        self.assertEqual(PW.typo_keyword("diligense"), "diligence")
