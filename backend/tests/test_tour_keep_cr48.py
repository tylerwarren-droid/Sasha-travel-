"""CR 48 · the stage beat: a fresh "campus" tour offers "I'll use your kept details", and the family's ONE yes opens them.
Before: the yes failed ("❌ Your kept details couldn't be opened (UseRefused)") — the tour's approval was a 16-character plan
fingerprint, while the vault checks the full sha256 of the approved lines, which must include the kept item's access line.

    cd backend && python -m unittest tests.test_tour_keep_cr48 -v
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from unittest import mock

from booking_signer import guest_whatsapp as GW, plan_store as PS
from booking_signer.vault import crypto as VC
from products.campus import live as LV, slate as SL, tour as TR
from tests import test_campusme_cr1 as TC, test_guest_whatsapp_s75 as TG
from tests.test_tour_cr38 import Web

run = TG.run


class KeptDetails(TC.OnWhatsApp):
    def keep(self):
        item = str(uuid.uuid4())
        sealed = run(VC.seal(TG.ACCOUNT, item, "identifier", json.dumps({"value": json.dumps(LV.FICTIONAL_FAMILY)}).encode()))
        now = datetime.now(timezone.utc)
        run(VC.STORE.create({"id": item, "account_id": TG.ACCOUNT, "provider": "kanoe.ai", "label": TR.LABEL, "kind": "identifier",
                             **sealed, "special_category": False, "created_at": now, "updated_at": now}))

    def test_offered_then_one_yes_opens_them(self):
        self.keep()
        SL.READER = SL.Reader(Web(), pace=0)

        async def travel(o, d, depart, mode):
            return 3600
        with mock.patch("booking_signer.proactive.travel", travel), mock.patch.object(GW, "_spawn", lambda c: c.close()), \
                mock.patch.object(PS, "save", mock.AsyncMock(return_value="trip-tour")):
            self.say("campus Ivy tour week of 15 Nov: Yale, Brown")
            said = self.said()
            self.assertIn("I'll use your kept details (“CampusMe tour details”) — opened only under your yes.", said)
            self.assertIn("I'll use your saved CampusMe tour details from your vault.", said)     # the yes names what it opens
            pend = run(GW.STORE.get_state(GW.wa_key(TG.GUEST)))["pending"]
            self.say("", payload=f"cm:tyes:{pend['tour']['sha']}")
        said = self.said()
        self.assertNotIn("couldn't be opened", said)
        self.say("", payload="cm:more:details")                                                    # CR 52 · behind a tap
        self.assertIn("prueba@example.com", self.bodies())                                        # its details, to copy
        uses = run(VC.STORE.uses_of(TG.ACCOUNT))
        self.assertEqual([(u["action_kind"], u["status"]) for u in uses], [("campusme_tour", "done")])  # opened once, logged


def load_tests(loader, tests, pattern):
    suite = TG.unittest.TestSuite()
    suite.addTest(KeptDetails("test_offered_then_one_yes_opens_them"))
    return suite


if __name__ == "__main__":
    TG.unittest.main()
