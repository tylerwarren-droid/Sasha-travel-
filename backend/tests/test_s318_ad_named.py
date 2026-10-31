"""Sasha 318 · CR 148: "what's the status of Prada?" in travel goes to Applied Diligence. Found by the router proof against AgAPI's deployed
sandbox (31 Oct 11:05): AgAPI's messages.ad_cases returned the case, AD's real name for it — "PRADA RETAIL UK LIMITED" — and Sasha's own
named() needed every word of that name ("retail" too), so the message stayed in travel. Root test: (1) ONE reading of which case a message
names — AD's door's (AgAPI ad_door.names_in), asked with the message (messages.ad_cases {from, text} → named); (2) Sasha never matches a
case name itself when AgAPI has read the message (its word match is only the fallback for an AgAPI without the reading); (3) the whole class:
every routing question about AD's cases reads that one answer."""
import unittest

from tests import test_s315 as T
from products import router as RT

REAL = [{"case_id": "af68eb09-0000-4000-8000-000000000318", "name": "PRADA RETAIL UK LIMITED", "status": "open", "opened_at": "2026-10-30T06:00:00Z"}]


class AgapiReadsTheMessage(T.Base):
    def test_a_ads_real_name_routes_when_agapi_says_the_message_names_it(self):
        self.cases.side_effect = lambda number, text=None: [{**REAL[0], "named": "prada" in (text or "").lower()}]
        self.say("what's the status of Prada?")
        self.assertEqual(self.sent_to_ad(), [("what's the status of Prada?", "diligence", True)])
        self.assertEqual(self.brain_saw, [])
        self.assertEqual(self.cases.call_args.args[1], "what's the status of Prada?")    # asked WITH the message

    def test_b_agapis_no_is_final_sasha_never_matches_names_itself(self):
        self.cases.side_effect = lambda number, text=None: [{**T.PRADA[1], "named": False}]   # its words would match "Lehman Brothers…"
        self.say("Lehman Brothers Holdings Inc")
        self.assertEqual(self.sent_to_ad(), [])

    def test_c_an_agapi_without_the_reading_keeps_the_old_word_match(self):
        self.cases.side_effect = lambda number, text=None: list(T.PRADA)
        self.say("what's the status of Prada?")
        self.assertEqual([t for t, _, _ in self.sent_to_ad()], ["what's the status of Prada?"])

    def test_d_the_cache_is_per_message(self):
        n = []
        self.cases.side_effect = lambda number, text=None: n.append(text) or [{**REAL[0], "named": "prada" in (text or "").lower()}]
        self.say("what's the status of Prada?")
        self.say("book dinner at Taverna Correo on Friday at 21:00 for 2")
        self.assertIn("what's the status of Prada?", n)
        self.assertEqual(len(self.sent_to_ad()), 1)


if __name__ == "__main__":
    unittest.main()
