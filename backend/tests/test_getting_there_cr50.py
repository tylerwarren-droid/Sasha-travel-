"""CR 50 · RelocateMe suggests Sasha for travel, like CampusMe: once the consulate step is clear, "✈️ Getting there" with one
button; tapped (or "book my flights" said), Sasha plans the flights to the new town on the entry date and the first nights
near the new address — the move's own dates and place pre-filled; each booking lands on the "Move to Madrid" trip. The tab
shows the same block. Same on WhatsApp and the platform.

    cd backend && python -m unittest tests.test_getting_there_cr50 -v
"""
from __future__ import annotations

from products import store as ST
from products.relocation import package_status
from tests import test_guest_whatsapp_s75 as TG
from tests.test_forms_cr44 import demo
from tests.test_three_cr37 import Base

run = TG.run


class Card(Base):
    def said(self):
        return "\n".join(self.bodies() + [c for c, _ in TG.GW.SENDER.contents])

    def test_after_the_consulate_one_tap_plans_the_move(self):
        for t in ("relocation", "DEMO", "SIGNED", "United States", "New York"):
            self.say(t)
        self.say("", payload="rx:go:travel")                                         # CR 52 · its own step in the walk
        said = self.said()
        self.assertIn("✈️ Getting there: Sasha books your flights to Madrid and your first nights", said)
        self.assertIn("tp:go:relocation", [p for _, bs in TG.GW.SENDER.contents for _, p in bs])
        self.say("", payload="tp:go:relocation")
        self.assertIn("When do you plan to enter Spain?", self.said())                 # the plan's own first question
        self.say("1 March 2027")
        self.assertIn("Which city will you fly from?", self.said())
        self.say("New York")
        said = self.said()
        self.assertIn("Your move, in order", said)
        self.assertIn("Madrid", said)


class Tab(TG.unittest.TestCase):
    def test_the_move_tab_block(self):
        saved = ST.STORE
        ST.STORE = ST.MemoryCaseStore()
        try:
            run(ST.STORE.put("relocation", "acct-1", "w", {"facts": demo(), "rows": [{}],
                                                          "after": {"entry_date": "2027-03-01", "consulate": {"three": "newyork"}}}))
            g = run(package_status("acct-1"))["getting_there"]
            self.assertEqual((g["title"], g["say"], g["to"], g["entry_date"]), ("Getting there", "book my flights", "Madrid", "2027-03-01"))
            self.assertIn("Flights to Madrid for 2027-03-01 and your first nights near Calle de Ejemplo 12", g["text"])
        finally:
            ST.STORE = saved


def load_tests(loader, tests, pattern):
    suite = TG.unittest.TestSuite()
    suite.addTest(Card("test_after_the_consulate_one_tap_plans_the_move"))
    suite.addTests(loader.loadTestsFromTestCase(Tab))
    return suite


if __name__ == "__main__":
    TG.unittest.main()
