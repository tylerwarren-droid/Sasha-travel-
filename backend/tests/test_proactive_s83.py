"""S-83 · proactive Sasha (§6 tests 1–9): honest status, quiet hours, the cap, once per kind, opt-outs, the status
re-read at the send, written confirmations, leave_now only on a computed route, templates outside the window, and the
consent v3 gate. A fake clock, fake bookings and fake delivery. Offline.

    cd backend && python -m unittest tests.test_proactive_s83 -v
"""
from __future__ import annotations

import asyncio
import os
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock
from zoneinfo import ZoneInfo

from booking_signer import guest_whatsapp as GW, proactive as PR

ACCOUNT = "55555555-5555-4555-8555-555555555555"
GUEST = "+34600000001"
MAD = ZoneInfo("Europe/Madrid")


def run(c):
    return asyncio.get_event_loop().run_until_complete(c)


def at(y, mo, d, h, mi=0, tz=MAD):
    return datetime(y, mo, d, h, mi, tzinfo=tz)


def booking(i="t-1", status="confirmed", date="2026-10-03", time="21:00", venue="Casa Lucio", tz="Europe/Madrid", ref="AB12"):
    return {"id": i, "venue": venue, "date": date, "time": time, "timezone": tz, "party": 2, "status": status,
            "booking_reference": ref, "sasha_reference": "K-MCFA"}


class FakeSender:
    def __init__(self):
        self.sent = []

    async def send(self, frm, to, *, body="", media=None, content_sid=None, variables=None):
        self.sent.append({"body": body, "content": content_sid, "vars": variables})
        return "sent"

    async def quick_reply(self, body, buttons):
        return None


class Base(unittest.TestCase):
    consent = "v3"

    def setUp(self):
        asyncio.set_event_loop(asyncio.new_event_loop())
        self.env = mock.patch.dict(os.environ, {"SASHA_GUEST_WHATSAPP_TO": "+14155238886", "SASHA_WA_TEMPLATES": "",
                                                "GOOGLE_PLACES_API_KEY": "k", "SASHA_PROACTIVE_DAILY_MAX": "4"})
        self.env.start()
        self.saved = (GW.STORE, GW.SENDER, PR.STORE, GW._upcoming, PR.NOW, GW.NOW, PR.ROUTES_HTTP)
        GW.STORE, GW.SENDER, PR.STORE = GW.MemoryGuestStore(), FakeSender(), PR.MemoryProactiveStore()
        self.rows = [booking()]
        self.reread = None

        async def upcoming(account, names=True):
            return [dict(r) for r in (self.reread if self.reread is not None else self.rows)]
        GW._upcoming = upcoming
        self.now = at(2026, 10, 2, 18, 1)
        PR.NOW = GW.NOW = lambda: self.now
        run(GW.STORE.link({"account_id": ACCOUNT, "wa_id_sha256": GW.wa_key(GUEST), "number_e164": GUEST, "linked_at": self.now,
                           "consent_at": self.now, "consent_wording_version": self.consent, "consent_text_sha256": "x" * 64}))
        self.inbound(self.now - timedelta(hours=1))

    def tearDown(self):
        GW.STORE, GW.SENDER, PR.STORE, GW._upcoming, PR.NOW, GW.NOW, PR.ROUTES_HTTP = self.saved
        self.env.stop()

    def inbound(self, when):
        run(GW.STORE.put_state(GW.wa_key(GUEST), {"history": [], "pending": None, "last_inbound_at": when, "link_tries": []}))

    def tick(self, now=None):
        if now:
            self.now = now
        return run(PR.tick(self.now))

    def bodies(self):
        return [s["body"] for s in GW.SENDER.sent]


class Rules(Base):
    def test_1_honest_status(self):
        for status in ("confirmed", "guest_booked", "requested", "attempting", "unclear", "proposed", "quoted", "waitlisted", "link_sent"):
            text = PR.render("day_before", booking(status=status))
            if status in PR.CONFIRMED:
                self.assertTrue(text.startswith("Tomorrow: Casa Lucio, 21:00, 2 people, ref AB12."), text)
            else:
                self.assertTrue("not confirmed yet" in text or "not booked until you say yes" in text, text)
                self.assertFalse(text.startswith("Tomorrow:"), text)

    def test_the_day_before_at_18(self):
        self.assertEqual(self.tick(at(2026, 10, 2, 17, 59)), [])
        done = self.tick(at(2026, 10, 2, 18, 1))
        self.assertEqual([d["kind"] for d in done], ["day_before"])
        self.assertEqual(self.bodies(), ["Tomorrow: Casa Lucio, 21:00, 2 people, ref AB12. Reply CANCEL Casa to cancel."])

    def test_2_quiet_hours_defer_and_time_zones(self):
        self.rows = [booking(date="2026-10-03", time="09:30")]
        self.tick(at(2026, 10, 2, 23, 30))                             # 23:30 Madrid: quiet → nothing yet
        self.assertEqual(self.bodies(), [])
        self.tick(at(2026, 10, 3, 8, 1))                               # 08:01: the deferred one goes
        self.assertEqual(len(self.bodies()), 1)
        lisbon = booking(i="t-2", tz="Europe/Lisbon", date="2026-10-04")
        self.assertTrue(PR.quiet(at(2026, 10, 2, 23, 5, MAD), ZoneInfo("Europe/Madrid")))
        self.assertFalse(PR.quiet(at(2026, 10, 2, 22, 30, MAD), ZoneInfo("Europe/Lisbon")))   # 21:30 in Lisbon
        self.assertEqual(PR.starts_at(lisbon).utcoffset(), timedelta(hours=1))

    def test_3_the_cap_keeps_the_most_important(self):
        self.rows = [booking(i=f"t-{i}", date="2026-10-03", time=f"{18 + i}:00") for i in range(6)]
        done = self.tick()
        self.assertEqual(len([d for d in done if d["outcome"] == "sent"]), 4)
        self.assertEqual(len([d for d in done if d["outcome"] == "dropped: the daily cap"]), 2)

    def test_4_once(self):
        self.tick()
        self.tick(self.now + timedelta(minutes=5))
        self.assertEqual(len(self.bodies()), 1)

    def test_5_opt_outs(self):
        run(PR.STORE.set_prefs(ACCOUNT, all_off=True))
        self.assertEqual(self.tick(), [])
        run(PR.STORE.set_prefs(ACCOUNT, all_off=False, off_kinds=["day_before"]))
        self.assertEqual(self.tick(), [])
        run(GW.STORE.set_opted_out(GW.wa_key(GUEST), self.now))        # S-75 STOP: no channel at all
        run(PR.STORE.set_prefs(ACCOUNT, all_off=False, off_kinds=[]))
        self.assertEqual(self.tick(), [])

    def test_6_cancelled_between_the_selection_and_the_send(self):
        self.reread = None

        async def upcoming(account, names=True, _n=[0]):
            _n[0] += 1
            return [booking()] if _n[0] == 1 else []                    # cancelled by the time it is re-read
        GW._upcoming = upcoming
        done = self.tick()
        self.assertEqual(done[0]["outcome"], "skipped: no longer an active booking")
        self.assertEqual(self.bodies(), [])

    def test_7_written_confirmation(self):
        PR.STORE.inbound = [{"trip_item_id": "t-1", "channel": "email", "result": "confirmed", "account_id": ACCOUNT}]
        self.now = at(2026, 10, 2, 12, 0)
        done = self.tick()
        self.assertEqual(self.bodies(), ["Casa Lucio confirmed in writing ✅: 21:00 Saturday 3 October, 2 people, ref AB12."])
        self.assertEqual(done[0]["kind"], "written_confirmation")
        PR.STORE.inbound = [{"trip_item_id": "t-1", "channel": "email", "result": "proposed", "account_id": ACCOUNT}]
        self.assertTrue(PR.render("written_confirmation", booking(), {"result": "proposed"}).endswith("Not booked until you say yes."))

    def test_8_leave_now_only_on_a_computed_route(self):
        self.rows = [booking(date="2026-10-02", time="21:00")]
        self.assertEqual([d for d in self.tick(at(2026, 10, 2, 20, 15)) if d["kind"] == "leave_now"], [])   # no place saved
        run(PR.STORE.save_place(ACCOUNT, "my hotel", "Calle de Alcalá 66, Madrid"))

        async def routes(url, headers, body):
            return 200, {"routes": [{"duration": "1800s"}]}
        PR.ROUTES_HTTP = routes
        self.assertEqual([d for d in self.tick(at(2026, 10, 2, 20, 15)) if d["kind"] == "leave_now"], [])   # not yet (20:20)
        done = self.tick(at(2026, 10, 2, 20, 21))
        self.assertIn("Time to leave for Casa Lucio: 30 min by public transport from my hotel, for 21:00.", [d.get("text") for d in done])

    def test_8b_a_route_error_never_becomes_an_estimate(self):
        self.rows = [booking(date="2026-10-02", time="21:00")]
        run(PR.STORE.save_place(ACCOUNT, "my hotel", "Calle de Alcalá 66, Madrid"))

        async def routes(url, headers, body):
            return 403, {"error": {"message": "Routes API has not been used in project"}}
        PR.ROUTES_HTTP = routes
        done = self.tick(at(2026, 10, 2, 20, 25))
        self.assertFalse(any(d["kind"] == "leave_now" for d in done))
        self.assertFalse(any("min" in b for b in self.bodies()))

    def test_9_templates_outside_the_window(self):
        self.inbound(self.now - timedelta(hours=30))
        done = self.tick()
        self.assertEqual(done[0]["outcome"], "not sent: outside the 24-hour window")          # the sandbox: no template
        PR.STORE.sent.clear()
        with mock.patch.dict(os.environ, {"SASHA_WA_TEMPLATES": '{"day_before": {"en": "HXday"}}'}):
            self.rows = [booking(ref=None)]
            self.tick()
        s = GW.SENDER.sent[-1]
        self.assertEqual((s["content"], s["vars"][4]), ("HXday", "K-MCFA"))
        self.assertEqual(PR.template_vars("day_before", {**booking(ref=None), "sasha_reference": None})[4], "none given")

    def test_11_erasure_empties_all_three(self):
        self.tick()
        run(PR.STORE.save_place(ACCOUNT, "home", "Calle Mayor 1"))
        run(PR.STORE.set_prefs(ACCOUNT, all_off=True))
        self.assertEqual(run(PR.STORE.delete_account(ACCOUNT)), {"proactive_sent": 1, "proactive_prefs": 1, "guest_places": 1})


class ConsentGate(Base):
    consent = "v2"

    def test_12_a_v2_guest_gets_only_written_confirmations_until_yes_reminders(self):
        self.assertEqual(self.tick(), [])                                   # no day_before for v2
        PR.STORE.inbound = [{"trip_item_id": "t-1", "channel": "sms", "result": "confirmed", "account_id": ACCOUNT}]
        self.assertEqual([d["kind"] for d in self.tick(self.now + timedelta(minutes=1))], ["written_confirmation"])
        ch = run(GW.STORE.channel_for(GW.wa_key(GUEST)))
        self.assertEqual(run(GW._reminders_words(ch, "YES REMINDERS", self.now)).split(" —")[0], "Done")
        ch = run(GW.STORE.channel_for(GW.wa_key(GUEST)))
        self.assertEqual((ch["consent_wording_version"], ch["consent_text_sha256"]), ("v3", GW.consent("v3")["sha256"]))
        self.assertEqual([d["kind"] for d in self.tick(self.now + timedelta(minutes=2)) if d["outcome"] == "sent"], ["day_before"])
        v3 = GW.CONSENT["v3"]
        self.assertIn(f"{PR.QUIET[0]}:00", v3); self.assertIn(f"at most {PR.daily_max()}", v3)
        self.assertTrue(GW.consent_at_least("v10", 3)); self.assertFalse(GW.consent_at_least("v2", 3))

    def test_the_offer_is_made_once(self):
        ch = run(GW.STORE.channel_for(GW.wa_key(GUEST)))
        self.assertEqual(run(GW._reminders_offer(ch)), GW.REMINDERS_OFFER)
        self.assertIsNone(run(GW._reminders_offer(ch)))
        self.assertEqual(run(PR.STORE.get_prefs(ACCOUNT))["all_off"], True)   # asked, not answered: off


class DayWord(unittest.TestCase):
    """Sasha 119 · live, Sat 3 Oct 08:38: "Tomorrow, 21:00 at Hanakura: not confirmed yet" — about that same evening."""

    def test_held_by_the_quiet_hours_it_says_tonight(self):
        b = {"venue": "Hanakura", "date": "2026-10-03", "time": "21:00", "timezone": "Europe/Madrid", "status": "requested", "party": 2}
        sat_morning = datetime(2026, 10, 3, 6, 38, tzinfo=timezone.utc)
        self.assertTrue(PR.render("day_before", b, None, sat_morning).startswith("Tonight, 21:00 at Hanakura: not confirmed yet."))
        fri_evening = datetime(2026, 10, 2, 16, 0, tzinfo=timezone.utc)
        self.assertTrue(PR.render("day_before", b, None, fri_evening).startswith("Tomorrow, 21:00 at Hanakura"))
        self.assertTrue(PR.render("day_before", {**b, "time": "13:00"}, None, sat_morning).startswith("Today, 13:00"))


class OnPostgresPrefs(unittest.TestCase):
    """Sasha 117 · live, 2 Oct: set_prefs(all_off=True) with no off_kinds failed in Postgres ("off_kinds is of type text[]
    but expression is of type text"), and with it every WhatsApp turn of a v2 guest. The memory store hid it."""

    @classmethod
    def setUpClass(cls):
        from tests import test_booking_ladder as TBL
        TBL.OnPostgres.setUpClass.__func__(cls)
        import asyncpg, pathlib
        cls.url = TBL.PG_URL

        async def apply():
            c = await asyncpg.connect(cls.url)
            try:
                await c.execute("drop table if exists proactive_sent, proactive_prefs, guest_places cascade")
                sql = (pathlib.Path(__file__).resolve().parents[1] / "booking_signer" / "sql" / "026_proactive.sql").read_text()
                await c.execute(sql[sql.index("begin;"):sql.index("-- VERIFY")])
            finally:
                await c.close()
        asyncio.run(apply())

    def test_set_prefs_with_and_without_kinds(self):
        from booking_signer.store import PostgresStore

        async def go():
            st = PR.PostgresProactiveStore(PostgresStore(self.url))
            from tests.test_booking_ladder import DEMO_ACCOUNT_ID as a
            first = await st.set_prefs(a, all_off=True)                       # the reminders offer's write
            second = await st.set_prefs(a, off_kinds=["day_before"])            # all_off kept
            third = await st.set_prefs(a, all_off=False)                        # off_kinds kept
            return first, second, third
        first, second, third = asyncio.run(go())
        self.assertEqual((first["all_off"], first["off_kinds"]), (True, []))
        self.assertEqual((second["all_off"], second["off_kinds"]), (True, ["day_before"]))
        self.assertEqual((third["all_off"], third["off_kinds"]), (False, ["day_before"]))


if __name__ == "__main__":
    unittest.main()
