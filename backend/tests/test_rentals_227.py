"""Sasha 227 · "day before pickup" — CR 75's fine-print moment on the proactive loop, for car rentals the person told her about.
Founder only, behind SASHA_PROACTIVE_RENTALS, at most ONE per rental. Offline: AgAPI, WhatsApp and the page are stand-ins.

    cd backend && python -m unittest tests.test_rentals_227 -v
"""
from __future__ import annotations

import asyncio
import unittest
from datetime import date, datetime, timedelta, timezone
from unittest import mock

from booking_signer import rental_moments as RM

FOUNDER = "11111111-1111-4111-8111-111111111111"
GUEST = "00000000-0000-4000-8000-000000000227"
run = asyncio.run
TOMORROW = (date.today() + timedelta(days=1)).isoformat()


def evening(hour=18, minute=30):   # this evening in Lisbon (PT), as UTC
    from zoneinfo import ZoneInfo
    return datetime.combine(date.today(), datetime.min.time().replace(hour=hour, minute=minute), ZoneInfo("Europe/Lisbon")).astimezone(timezone.utc)


class Moments(unittest.TestCase):
    def setUp(self):
        RM._MEM.clear()
        self.published, self.asked = [], []

        async def moment(account, event):
            self.asked.append(event)
            return {"speak": True, "line": "Tomorrow at the counter: decline the CDW — your Travel Visa's terms cover it (quoted).",
                    "card": {"card": {"card": "Example Bank Travel Visa", "counter": {"decline": [{"say": "Decline CDW"}]}}}}
        from agapi import s2_fine_print as FP
        from booking_signer import live_events as LE
        for p in (mock.patch.object(RM, "RUN", None), mock.patch("booking_signer.identity.founder_account", lambda: FOUNDER),
                  mock.patch.object(FP, "moment", moment), mock.patch.object(LE, "publish", lambda a, ev: self.published.append((a, ev))),
                  mock.patch.object(RM, "_whatsapp", mock.AsyncMock(return_value="not sent: outside the 24-hour window"))):
            p.start()
            self.addCleanup(p.stop)
        run(RM.note(FOUNDER, {"rental_company": "Example Rentals", "country": "PT", "place": "Lisbon airport", "pickup_date": TOMORROW,
                              "pickup_time": "10:00"}))

    def test_off_by_default(self):
        with mock.patch.dict("os.environ", {"SASHA_PROACTIVE_RENTALS": ""}):
            self.assertEqual(run(RM.tick(evening())), [])
        self.assertEqual(self.asked, [])

    def test_the_evening_before_once(self):
        with mock.patch.dict("os.environ", {"SASHA_PROACTIVE_RENTALS": "1"}):
            first = run(RM.tick(evening()))
            again = run(RM.tick(evening(19, 30)))
        self.assertEqual(len(first), 1)
        self.assertEqual(again, [])                                  # one per rental, ever
        self.assertEqual(self.asked[0]["kind"], "pickup_tomorrow")
        self.assertEqual(self.published[0][1]["render"]["kind"], "counter_card")

    def test_not_in_the_morning_nor_in_quiet_hours(self):
        with mock.patch.dict("os.environ", {"SASHA_PROACTIVE_RENTALS": "1"}):
            self.assertEqual(run(RM.tick(evening(9, 0))), [])
            self.assertEqual(run(RM.tick(evening(22, 30))), [])
        self.assertEqual(self.asked, [])

    def test_founder_only(self):
        RM._MEM.clear()
        run(RM.note(GUEST, {"rental_company": "Example Rentals", "country": "PT", "pickup_date": TOMORROW}))
        with mock.patch.dict("os.environ", {"SASHA_PROACTIVE_RENTALS": "1"}):
            self.assertEqual(run(RM.tick(evening())), [])

    def test_silent_when_agapi_says_so(self):
        from agapi import s2_fine_print as FP
        with mock.patch.dict("os.environ", {"SASHA_PROACTIVE_RENTALS": "1"}), \
                mock.patch.object(FP, "moment", mock.AsyncMock(return_value={"speak": False, "why_silent": "turned off"})):
            done = run(RM.tick(evening()))
        self.assertTrue(done[0]["outcome"].startswith("silent"))
        self.assertEqual(self.published, [])

    def test_a_bad_date_is_refused(self):
        with self.assertRaises(ValueError):
            RM.clean({"rental_company": "X", "country": "PT", "pickup_date": "tomorrow"})


class InMyPlans(unittest.TestCase):
    def test_a_noted_rental_is_in_my_plans_and_s1_has_no_tool(self):
        from agapi import s2_manage as M, v0 as API, venues as VN
        from booking_signer import plan_store as PS
        RM._MEM.clear()
        with mock.patch.object(RM, "RUN", None):
            run(M.note_rental(API.Ctx(account=GUEST, surface="s2"), {"rental_company": "Example Rentals", "country": "PT", "pickup_date": TOMORROW}))
            with mock.patch.object(VN, "venue_bookings", mock.AsyncMock(return_value=[])), mock.patch.object(PS, "plans", mock.AsyncMock(return_value=[])):
                r = run(M.my_plans(API.Ctx(account=GUEST, surface="s2"), {}))
        self.assertEqual(r["items"][0]["kind"], "car")
        self.assertNotIn("note_rental", [t["name"] for t in API.TOOLS])


if __name__ == "__main__":
    unittest.main()
