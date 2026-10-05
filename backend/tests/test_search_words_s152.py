"""Sasha 152 · the founder's live test: "help me find a tattoo parlor… top rated ones in Madrid" went to the model (which
asked his name and re-asked what he had said), and the follow-up searched for "tattoo parlor top rated ones". A stated
priority is the PRIORITY, never part of what is searched for; a comma before it doesn't end the request. Offline.

    cd backend && python -m unittest tests.test_search_words_s152 -v
"""
from __future__ import annotations

import unittest

from booking_signer import handoff as H


class TheFoundersWords(unittest.TestCase):
    def test_one_message(self):
        for m in ("help me find a tattoo parlor, top rated ones in Madrid", "help me find a tattoo parlor top rated ones in Madrid",
                  "find me the best tattoo parlor in Madrid"):
            self.assertEqual(H.find_request(m), {"what": "tattoo parlor", "where": "Madrid", "country": "ES", "priority": "rated"}, m)

    def test_in_two_spoken_pieces(self):
        r = H.booking_handoff("top rated ones in Madrid", [{"role": "user", "content": "help me find a tattoo parlor"},
                                                            {"role": "assistant", "content": "Where?"}])
        self.assertEqual(r["booking_find"]["what"], "tattoo parlor")
        self.assertEqual(r["booking_find"]["priority"], "rated")
        self.assertNotIn("top rated ones", r["response"])

    def test_qualities_are_still_kept(self):
        self.assertEqual(H.find_request("find a luxury dinner for 2 in Chamberí on Saturday at 9")["what"], "luxury dinner")
        self.assertEqual(H.find_request("help me find a tattoo parlor in Madrid"), {"what": "tattoo parlor", "where": "Madrid", "country": "ES"})


class SignedOut(unittest.TestCase):
    def test_signed_out_never_promises_cards_it_cannot_show(self):
        import asyncio
        from app.services import conductor as CD
        out = asyncio.new_event_loop().run_until_complete(CD.conduct("help me find a tattoo parlor, top rated ones in Madrid", [],
                                                                     user_id="00000000-0000-4000-8000-0000000d3e00", signed_in=False))
        self.assertIsNone(out.get("booking_find"))
        self.assertTrue(out["response"].startswith("Sign in and I'll find tattoo parlor in Madrid"))
        self.assertNotIn("Let me look for", out["response"])


if __name__ == "__main__":
    unittest.main()
