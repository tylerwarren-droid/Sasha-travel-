"""CR 39 · "start over" / "reset" inside CampusMe, RelocateMe or EspañaMe asks once — "Start <product> from the beginning? Your old
file is kept, not deleted." — yes restarts at its first question, no carries on where it was; the files (cases) are never
deleted. reset_modes (called by Sasha's "reset the demo", founder only) closes all three.

    cd backend && python -m unittest tests.test_restart_cr39 -v
"""
from __future__ import annotations

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
        self.assertIn("first* application", "\n".join(self.bodies()[-3:]))      # its first question again
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
