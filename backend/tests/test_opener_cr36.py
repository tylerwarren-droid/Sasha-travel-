"""CR 36 · the product preview opens on its opener for tomorrow: a tab opened with nothing answered yet starts on the opener
(never the bare first question); once something is answered it says where it was ("Back to your EX-01. …"), and the
product's own name while it's asking never re-asks the same question (which the never-ask-twice line turned into a lecture).

    cd backend && python -m unittest tests.test_opener_cr36 -v
"""
from __future__ import annotations

from products import web as PWEB
from tests import test_guest_whatsapp_s75 as TG
from tests import test_web_media_cr30 as W

run = TG.run


class Opener(W.WebPhoto):
    def tab(self):
        return run(PWEB.web_turn(TG.ACCOUNT, "", mode="relocation", now=self.now, signed_in=True))["response"]

    def test_opened_twice_with_nothing_answered_it_is_the_opener_both_times(self):
        first = self.tab()
        self.assertTrue(first.startswith("Let's get your Spanish residence file ready"))
        self.assertEqual(self.tab(), first)

    def test_once_answered_it_says_where_it_was_never_the_lecture(self):
        self.tab()
        W.web(self, "first")
        again = self.tab()
        self.assertTrue(again.startswith("Back to your EX-01."), again)
        self.assertNotIn("I asked that a moment ago", again)
        self.assertIn("economic resources", again)

    def test_its_own_name_typed_while_it_asks(self):
        W.web(self, "relocation")
        W.web(self, "first")
        r = W.web(self, "relocation")["response"]
        self.assertTrue(r.startswith("Back to your EX-01."), r)


if __name__ == "__main__":
    TG.unittest.main()
