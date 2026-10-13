"""Sasha 130 (2) · once the decision workflow (booking_signer/decide.py). Sasha 254 · RETIRED as a decider: every venue booking is
decided by the vendored booking rules (agapi/booking_rules) through agapi.booking_decide — pinned in tests/test_s254_one_decider.py.
What stays here: the words parser (decide.preference), the no-reply sweep's gates on the rules' timing, the Gmail filing, and the
platform hand-over said without naming it.

    cd backend && python -m unittest tests.test_decide_s130 -v
"""
from __future__ import annotations

import os
import unittest
from unittest import mock

from booking_signer.decide import preference


class Decide(unittest.TestCase):
    def test_the_decider_is_retired_only_the_words_parser_stays(self):
        from booking_signer import decide as D
        for gone in ("decide", "ladder", "line", "Venue", "urgent_hours", "reply_hours", "tap_window_min"):
            self.assertFalse(hasattr(D, gone), gone)

    def test_preference_words(self):
        self.assertEqual(preference("call them instead"), "call")
        self.assertEqual(preference("llámales"), "call")
        self.assertEqual(preference("just email them"), "email")
        self.assertEqual(preference("call and email them"), "call_email")
        self.assertEqual(preference("send me the link, I'll book it myself"), "one_tap")
        self.assertIsNone(preference("yes"))


from booking_signer import guest_whatsapp as GW  # noqa: E402
from tests import test_guest_whatsapp_s75 as TG  # noqa: E402


class NoReplyCall(TG.Base):
    """Email, then — no reply, and they've just opened — ONE question on WhatsApp; its yes leads to the call's own read-back."""

    def setUp(self):
        super().setUp()
        import os
        from datetime import datetime, timezone
        from unittest import mock
        from booking_signer import ladder_routes as LR, ladder_store as LS, proactive as PR
        self.link()
        self.addCleanup(setattr, LR, "LADDER_STORE", LR.LADDER_STORE)
        self.addCleanup(setattr, PR, "STORE", PR.STORE)
        LR.LADDER_STORE, PR.STORE = LS.MemoryLadderStore(), PR.MemoryProactiveStore()
        week = {str(d): [["13:00", "16:00"], ["20:00", "23:30"]] for d in range(7)}
        TG.run(LR.LADDER_STORE.put_read({"read_id": "r-9", "account_id": TG.ACCOUNT, "created_at": TG.NOW,
                                         "read": {"name": "Botavara Chamberí", "country": "ES", "facts": [
                                             {"kind": "phone", "value": "+34910000000", "source_label": "their website"},
                                             {"kind": "hours", "source_kind": "site", "source_label": "their website", "evidence": {"week": week}}]}}))
        self.row = {"id": "t-77777777", "venue": "Botavara Chamberí", "date": "2026-10-03", "time": "21:30", "timezone": "Europe/Madrid",
                    "status": "requested", "channel": "email", "read_id": "r-9", "requested_at": "2026-10-02T12:00:00+00:00", "what": "a table", "category": "restaurant", "count": 2}
        self.p = [mock.patch.object(GW, "_upcoming", side_effect=lambda a, **kw: [self.row]), mock.patch.dict(os.environ, {"SASHA_NO_REPLY_CALL": "1"})]
        for x in self.p:
            x.start()
            self.addCleanup(x.stop)
        self.dt = datetime

    def test_not_while_they_are_closed_nor_while_the_rules_say_wait(self):
        from booking_signer import proactive as PR
        from datetime import datetime, timezone
        from agapi import booking_decide as BD
        live = {"mode": "live", "calls": "on", "real_venue_sends": "on"}
        with mock.patch.object(BD, "access_of", mock.AsyncMock(return_value=live)):
            self.now = datetime(2026, 10, 3, 17, 0, tzinfo=timezone.utc)                  # 19:00 Madrid: closed
            TG.run(GW.STORE.put_state(GW.wa_key(TG.GUEST), {"history": [], "pending": None, "last_inbound_at": self.now, "link_tries": []}))
            self.assertEqual(TG.run(PR.no_reply_offers(self.now)), [])
            # Sasha 254 · the TIMING is the booking rules': a restaurant five days away is still a request (R3) — never a call
            self.now = datetime(2026, 10, 3, 18, 10, tzinfo=timezone.utc)
            self.row.update(date="2026-10-08", requested_at="2026-10-01T16:10:00+00:00")
            self.assertEqual(TG.run(PR.no_reply_offers(self.now)), [])


class OneTapFiling(unittest.TestCase):
    def test_a_one_tap_booking_the_guest_pressed_is_confirmed_by_the_venues_email(self):
        """Rehearsal, 3 Oct: matched by venue and time, but 'guest_booked' wasn't offered — the confirmation was never filed."""
        from booking_signer import mailbox as MB
        off = MB.offer("confirmation", {"venue": "Sasha Test Venue", "at": "2026-10-07T21:00", "party": 2, "reference": "TV-30D27C"},
                       {"venue": "Sasha Test Venue", "status": "guest_booked"})
        self.assertEqual(off[0], "confirm")
        self.assertIn("(ref TV-30D27C). Mark it confirmed?", off[1])

    def test_the_platform_is_handed_over_never_named(self):   # Sasha 254 · R14 + her voice
        from agapi.booking_rules import booking_rules as BR
        d = GW.decision_of({"rungs": {"link": {"fact_index": 1, "value": "CoverManager"}}, "country": "ES"})
        self.assertEqual(d.route, "one_tap")
        self.assertTrue(d.reason.startswith(BR.PHRASES["platform"].format(platform="a booking platform")), d.reason)
        self.assertNotIn("CoverManager", d.reason)


class TapExpired(unittest.TestCase):
    """Sasha 254 · RETIRED: the booking rules have no "page not pressed in N minutes → email them" step (R14 hands the page over;
    R11 — they can take it over at any point). tap_offers offers nothing, whatever the flag."""

    def test_it_offers_nothing(self):
        from booking_signer import proactive as PR
        from datetime import datetime, timezone
        for flag in ("1", ""):
            with mock.patch.dict(os.environ, {"SASHA_TAP_ESCALATION": flag}):
                self.assertEqual(TG.run(PR.tap_offers(datetime(2026, 10, 3, 12, 0, tzinfo=timezone.utc))), [])


if __name__ == "__main__":
    unittest.main()
