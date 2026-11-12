"""CR 129 · how they book follows the route AgAPI decided. Sasha 298, live: La Mi Venta (CoverManager, an email beside it) heard "I'll book
it. Want a prefilled form…" while AgAPI's decision said "you press Book there" — venue_truth.channel counted a platform's widget as a
form Kanoe fills. Sasha 378 · CR 188: venue_truth.channel IS AgAPI's decision (its route, channel and words); the ONE question of
Sasha's own (ASK_FILL) is gone, and with no decision Sasha shows none of her own."""
from __future__ import annotations

import unittest

from agapi import venue_truth as VT
from agapi.booking_rules import booking_rules as BR

WIDGET = {"kind": "widget", "name": "CoverManager booking widget",
          "url": "https://www.covermanager.com/reservation/module_restaurant/restaurante-meson-la-mi-venta/spanish"}
EMAIL = {"kind": "email", "value": "reservas@lamiventa.example"}
OWN = {"kind": "form", "name": "their own booking form", "url": "https://www.lamiventa.example/reserva/"}


class TheChannelIsAgapisDecision(unittest.TestCase):
    def test_a_platform_route_is_the_platform_never_a_question(self):
        ch = VT.channel({"channels": [WIDGET, EMAIL], "decision": {"route": "platform", "channel": "CoverManager", "say_text": "You press Book there."}})
        self.assertEqual((ch["route"], ch["channel"], ch["say_text"]), ("platform", "CoverManager", "You press Book there."))
        self.assertNotIn("ask", ch)

    def test_no_decision_no_channel_of_sashas_own(self):
        self.assertIsNone(VT.channel({"channels": [WIDGET, EMAIL]}))
        self.assertIsNone(VT.channel({"channels": [OWN, EMAIL]}))
        self.assertIsNone(VT.channel({"channels": [OWN], "decision": {"route": "none"}}))

    def test_their_own_form_is_agapis_send_form(self):
        ch = VT.channel({"channels": [OWN, EMAIL], "decision": {"route": "send_form", "channel": "their own booking form"}})
        self.assertEqual(ch["route"], "send_form")
        self.assertFalse(hasattr(VT, "ASK_FILL"))

    def test_d_the_vendored_rules_r14_reads_every_field(self):
        """booking-rules (vendored from AgAPI, its words and vectors): a form whose LINK is the platform's is never "I'll book it" from a
        form Kanoe fills — AgAPI's own rules, run here only to keep the vendored copy honest."""
        d = BR.decide({"venue": {"type": "restaurant", "test": False, "channels": [{"kind": "form", "value": "their own booking form",
                                                                                     "url": WIDGET["url"]}]},
                       "when": {"now": "2026-10-27T10:00:00Z", "booking_at": "2026-10-30T20:00:00Z"},
                       "person": {"access": {"mode": "live"}}, "state": {}})
        self.assertNotEqual(d["action"], "fill_form_zero_touch")


if __name__ == "__main__":
    unittest.main()
