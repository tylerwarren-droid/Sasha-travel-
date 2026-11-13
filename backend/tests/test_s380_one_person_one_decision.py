"""Sasha 380 · a live person is booked by Sasha herself; no account is ever told "I can't contact venues for you yet". NO PATCHES.

Found (Tyler, 12 Nov 16:38–16:39 UTC, WhatsApp, "Book La Taberna de Peñalver, Cava Baja, for 2…"): agapi-live answered venue.submit_booking
with status not_allowed, and Sasha said "I can't contact venues for you yet on this account. Here's their page to book it yourself." — that
sentence is Sasha's (the vendored no_real_sends phrase, agapi/venues.py:1545 and :2058), put over EVERY not_allowed whatever AgAPI's reason
was, and the reason was never kept. Tyler's WhatsApp is linked to his one account (11111111…, tyler@kanoe.ai) — the same person record
S2 reads (one end user, external_ref "sasha:<account>"; AgAPI's access.get and its live gate read the same effective record).

Now: AgAPI's refusal hands over the page AgAPI prepared (voice.FINISH_IT — never "can't", Sasha 288) and its reason is logged; the same person gets the same decision on WhatsApp and
on S2 — AgAPI's request, read back for the ONE yes — never the hand-over. Why AgAPI refused at 16:39 is AgAPI's to read on its record
(mailbox: the CR half).

    cd backend && python -m unittest tests.test_s380_one_person_one_decision -v
"""
from __future__ import annotations

import pathlib
import re
import unittest

from agapi import venues as VN
from tests.test_s254_one_decider import ALL4, Base

BACKEND = pathlib.Path(__file__).resolve().parents[1]


class OnePersonOneDecision(Base):
    def setUp(self):
        super().setUp()
        from tests.test_s254_handle_it_live import use_fake_agapi
        self.agapi = use_fake_agapi(self)

    def test_whatsapp_and_s2_the_same_decision_never_the_hand_over(self):
        seen = {}
        for surface in ("wa", "s2"):
            VN._HELD.pop("00000000-0000-4000-8000-000000000254", None)
            self.surface = surface
            out = self.hold({"email": ALL4["email"], "phone": ALL4["phone"]})       # AgAPI's decision: their email, Kanoe sends it
            seen[surface] = (out["status"], out["route"], out["rules"]["action"])
        self.assertEqual(seen["wa"], seen["s2"])
        self.assertEqual(seen["s2"], ("requested", "agapi", "request_email"))          # Sasha 381 · AgAPI's request, sent on the instruction

    def test_a_refusal_hands_over_their_page_and_keeps_agapis_reason(self):
        why = "I can't send this one for you (this person is a test person — a real venue is never contacted for them). The link I prepared is yours to finish — open it and confirm."
        self.agapi.submit.update(status="not_allowed", submitted=False, act_id=None, say=why)
        with self.assertLogs("agapi.venues", "WARNING") as logs:
            got = self.hold({"email": ALL4["email"]})
        self.assertIn(got["status"], ("page_link", "page_on_phone", "not_contacted", "not_allowed"), got)   # handed over (Sasha 288), nothing sent
        self.assertNotIn("on this account", str(got))
        self.assertNotIn("can't", (got.get("line") or got.get("say") or "").lower())
        self.assertTrue(any("test person" in l for l in logs.output), logs.output)      # the reason, kept


class TheRatchet(unittest.TestCase):
    def test_no_booking_path_says_a_reason_of_sashas_own(self):
        for rel in ("agapi/venues.py", "agapi/venue_submit.py", "booking_signer/guest_whatsapp.py", "app/agent/sasha.py"):
            src = (BACKEND / rel).read_text()
            code = "\n".join(l for l in src.splitlines() if not l.lstrip().startswith("#"))
            self.assertIsNone(re.search(r"PHRASES\[[\"']no_real_sends[\"']\]", code), rel)


if __name__ == "__main__":
    unittest.main()
