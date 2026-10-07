"""CR 39 · "start over" / "reset" inside CampusMe, RelocateMe or EspañaMe asks once — "Start <product> from the beginning? Your old
file is kept, not deleted." — yes restarts at its first question, no carries on where it was; the files (cases) are never
deleted. reset_modes (called by Sasha's "reset the demo", founder only) closes all three.

    cd backend && python -m unittest tests.test_restart_cr39 -v
"""
from __future__ import annotations

import unittest

from products import store as ST, whatsapp as PW
from tests import test_guest_whatsapp_s75 as TG
from tests import test_relocation_m3_cr1 as TR

run = TG.run


class Restart(TR.Flow):
    def test_asked_once_no_carries_on_yes_restarts_and_the_file_stays(self):
        self.start()                                          # RelocateMe under way: asking the passport number
        cases = len(ST.STORE.rows)
        self.say("start over")
        self.assertIn("Start RelocateMe from the beginning? Your old file is kept, not deleted.", "\n".join(
            [b for b, _ in TG.GW.SENDER.contents] + self.bodies()))
        self.say("", payload="so:no:relocation")
        self.assertTrue(self.bodies()[-1].startswith("Back to your EX-01."))
        self.say("reset relocation")
        self.say("", payload="so:yes:relocation")
        self.assertIn("first* application", "\n".join(self.bodies()[-3:] + [c for c, _ in TG.GW.SENDER.contents[-2:]]))   # its first question again
        self.assertEqual(len(ST.STORE.rows), cases)                             # nothing deleted

    def test_nothing_open_enters_directly(self):
        self.say("start over campus")
        self.assertIn("CampusMe here", "\n".join(self.bodies()))

    def test_reset_modes_closes_all_three(self):
        self.start()
        self.say("campus")
        n = run(PW.reset_modes(TG.ACCOUNT))
        self.assertGreaterEqual(n, 2)
        self.assertEqual(run(ST.STORE.conversations(f"acct:{TG.ACCOUNT}")), [])


if __name__ == "__main__":
    TG.unittest.main()


class SayBackCap(unittest.TestCase):
    """CR 41 · live: the say-back after a long turn began mid-way through a school's details."""

    def test_whole_messages_from_the_end(self):
        from products.whatsapp import _last_said
        parts = ["P" * 600, "Y" * 600, "B" * 600, "When you've registered somewhere, tell me."]
        got = _last_said(parts)
        self.assertTrue(got.startswith("Y"))
        self.assertTrue(got.endswith("tell me."))
        self.assertNotIn("P", got)

    def test_one_long_message_keeps_whole_paragraphs(self):
        from products.whatsapp import _last_said
        got = _last_said(["\n\n".join(["x" * 400] * 6) + "\n\nYour question?"])
        self.assertTrue(got.endswith("Your question?"))
        self.assertLessEqual(len(got), 1500)
        self.assertTrue(got.startswith("x"))
