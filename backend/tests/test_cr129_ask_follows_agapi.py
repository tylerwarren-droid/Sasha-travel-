"""CR 129 · "I'll book it" (the ONE question) follows the route AgAPI decided. Sasha 298, live: La Mi Venta (CoverManager, an email beside it)
heard "I'll book it. Want a prefilled form…" while AgAPI's decision said "you press Book there". venue_truth.channel counted a platform's
widget as a form Kanoe fills."""
from __future__ import annotations

import unittest

from agapi import venue_truth as VT
from agapi.booking_rules import booking_rules as BR

WIDGET = {"kind": "widget", "name": "CoverManager booking widget",
          "url": "https://www.covermanager.com/reservation/module_restaurant/restaurante-meson-la-mi-venta/spanish"}
EMAIL = {"kind": "email", "value": "reservas@lamiventa.example"}


class TheAskFollowsAgapi(unittest.TestCase):
    def test_a_platform_route_never_asks(self):
        ch = VT.channel({"channels": [WIDGET, EMAIL], "decision": {"route": "platform"}})
        self.assertIsNone(ch["ask"])
        self.assertEqual(ch["alternative"]["kind"], "email")   # the alternative is still there, only the question isn't

    def test_b_no_decision_kept_a_channel_naming_a_platform_never_asks(self):
        self.assertIsNone(VT.channel({"channels": [WIDGET, EMAIL]})["ask"])
        self.assertIsNone(VT.channel({"channels": [{"kind": "form", "name": "their own booking form",
                                                    "url": "https://www.thefork.es/restaurant/x"}, EMAIL]})["ask"])

    def test_c_their_own_form_kanoe_fills_still_asks(self):
        own = {"kind": "form", "name": "their own booking form", "url": "https://www.lamiventa.example/reserva/"}
        self.assertEqual(VT.channel({"channels": [own, EMAIL], "decision": {"route": "send_form"}})["ask"], VT.ASK_FILL)
        self.assertEqual(VT.channel({"channels": [own, EMAIL]})["ask"], VT.ASK_FILL)
        self.assertIsNone(VT.channel({"channels": [own, EMAIL], "decision": {"route": "prefilled_page"}})["ask"])

    def test_d_the_rules_r14_reads_every_field(self):
        """booking-rules/2.4 (AgAPI v1.40.0, vendored): a form whose LINK is the platform's is handed over, never 'I'll book it'."""
        d = BR.decide({"venue": {"type": "restaurant", "test": False, "channels": [{"kind": "form", "value": "their own booking form",
                                                                                     "url": WIDGET["url"]}]},
                       "when": {"now": "2026-10-27T10:00:00Z", "booking_at": "2026-10-30T20:00:00Z"},
                       "person": {"access": {"mode": "live", "calls": "on", "real_venue_sends": "on"}}, "state": {}})
        self.assertEqual(d["action"], "hand_over_platform_link")
        self.assertNotIn("I'll book it", d["say_text"])


if __name__ == "__main__":
    unittest.main()
