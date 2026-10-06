"""CR 43 · live: on the founder's account a tour of Yale, Brown and Penn filled Yale and Brown in Kanoe's browser but gave Penn as
a bare link — the tour sent only ("yale", "brown") to the hand-over. Now every school whose own form the hand-over fills (Yale and
Brown's, and Penn's one-page register form) is filled; a hand-over that can't open SAYS so, with the link and the details; and
what "yes" promises, and the PDF's footer, name THIS tour's schools.

    cd backend && python -m unittest tests.test_tour_penn_cr43 -v
"""
from __future__ import annotations

import os
from unittest import mock

from booking_signer import guest_whatsapp as GW, handover as HO
from products.campus import live as LV, slate as SL, tour as TR
from products.campus.slate import Session
from tests import test_guest_whatsapp_s75 as TG
from tests.test_tour_cr38 import Base, FAMILY

run = TG.run
ASK = "campus Ivy tour week of 15 Nov: Yale, Brown, Penn"
PENN = Session(school="penn", day="2026-11-16", start="15:00", end=None, title="Afternoon Tour · Campus Tours (1 hr 30 mins)",
               location=None, status="open", spaces=None, form_url="https://key.admissions.upenn.edu/portal/campus-visit?id=x",
               event_id="dbda7b29", read={"url": "https://key.admissions.upenn.edu/portal/campus-visit", "read_at": "2026-10-06"})
FOUNDER = {"FOUNDER_ACCOUNT_ID": TG.ACCOUNT, "BROWSERBASE_API_KEY": "k"}


class PennTour(Base):
    def setUp(self):
        super().setUp()
        real = SL.sessions

        async def sessions(s, day, attendees, reader=None):
            if s["key"] == "penn":
                return [PENN] if day == "2026-11-16" else []
            return await real(s, day, attendees, reader)
        self.p_sessions = mock.patch.object(SL, "sessions", sessions)
        self.p_sessions.start()

    def tearDown(self):
        self.p_sessions.stop()
        super().tearDown()

    def intake(self):
        self.say(ASK)
        for a in FAMILY:
            self.say(a)
        self.say("", payload="cm:tkeep:no")

    def test_the_founder_gets_penn_filled_too(self):
        with mock.patch.dict(os.environ, FOUNDER):
            self.intake()
            said = self.said()
            self.assertIn("I fill Yale's, Brown's and Penn's own registration forms in Kanoe's browser", said)
            self.assertNotIn("Princeton", said.split("Prepare it?")[0].split("If you say yes")[-1])
            self.say("", payload=f"cm:tyes:{self.pend()['tour']['sha']}")
        self.assertEqual(len(self.spawned), 3)                                          # Yale, Brown AND Penn
        said = self.said()
        self.assertIn("🎓 Penn: I'm filling its own form in Kanoe's browser", said)
        self.assertNotIn("key.admissions.upenn.edu", said)                              # no bare link

    def test_a_guest_still_gets_the_links(self):
        self.intake()
        self.assertIn("I give you Yale's, Brown's and Penn's own registration pages", self.said())
        self.say("", payload=f"cm:tyes:{self.pend()['tour']['sha']}")
        self.assertEqual(self.spawned, [])
        self.assertIn("🎓 Penn: register on its own page — https://key.admissions.upenn.edu", self.said())

    def test_no_cloud_browser_is_said_never_a_silent_link(self):
        with mock.patch.dict(os.environ, {**FOUNDER, "BROWSERBASE_API_KEY": ""}):
            self.intake()
            self.say("", payload=f"cm:tyes:{self.pend()['tour']['sha']}")
        self.assertIn("🎓 Penn: I couldn't open the filled page (the cloud browser isn't set up on this server) — here's the link "
                      "and your details: https://key.admissions.upenn.edu", self.said())
        self.assertIn("prueba@example.com", self.bodies())


class Live(TG.unittest.TestCase):
    def setUp(self):
        self.sent = []

        async def reach(wa, frm, account):
            return {"wa_id_sha256": "w"}, None, "+1"

        async def deliver(ch, number, out, last):
            self.sent += [str(it[1]) for it in out.items]

        class Store:
            async def get_state(self, k):
                return {}
        self.ps = [mock.patch("products.whatsapp.reach", reach), mock.patch.object(GW, "deliver", deliver),
                   mock.patch.object(GW, "STORE", Store()), mock.patch.object(TR, "_status", mock.AsyncMock())]
        for p in self.ps:
            p.start()

    def tearDown(self):
        for p in self.ps:
            p.stop()

    def visit(self):
        return {"school": "penn", "name": "Penn", "link": PENN.form_url, "session": PENN.as_dict(), "read": True}

    def fam(self):
        return {"student_first": "Prueba", "student_last": "Sasha", "email": "prueba@example.com", "birthdate": "2009-03-14",
                "grad_year": "2027", "mobile": "2025550123", "high_school": "Kanoe Test High School", "party": "3"}

    def test_penn_goes_through_its_one_page_hand_over(self):
        got = {}

        async def open_campus_handover(**kw):
            got.update(kw)
            return {"id": "h1", "venue": "Penn — Afternoon Tour"}
        with mock.patch.object(LV, "open_campus_handover", open_campus_handover), \
                mock.patch.object(HO, "tap_phone", mock.AsyncMock(return_value={"sent": True})):
            run(TR._live("acct", "w", "+1", "cid", self.visit(), self.fam()))
        self.assertEqual(got["profile"]["first"], "Prueba")
        self.assertEqual(got["profile"]["grad_year"], "2027")
        self.assertEqual(got["attendees"], 3)
        self.assertFalse(got["read_only"])
        self.assertEqual(self.sent, [])                                                 # the tap went; nothing else said

    def test_a_failure_is_said_with_the_link_and_the_details(self):
        for boom in (HO.Refused("two_pages", "Penn's form has more than one page — no link"), RuntimeError("cdp")):
            self.sent.clear()
            with mock.patch.object(TR, "open_live", mock.AsyncMock(side_effect=boom)):
                run(TR._live("acct", "w", "+1", "cid", self.visit(), self.fam()))
            self.assertTrue(self.sent[0].startswith("🎓 Penn: I couldn't open the filled page — "))
            self.assertIn(PENN.form_url, self.sent[0])
            self.assertIn("prueba@example.com", self.sent)
            self.assertIn("03/14/2009", self.sent)


class Words(TG.unittest.TestCase):
    def test_live_schools(self):
        self.assertEqual([TR.live_school(k) for k in ("yale", "brown", "penn", "princeton", "harvard")],
                         [True, True, True, False, False])

    def test_the_pdf_names_this_tours_schools(self):
        plan = {"visits": [{"name": "Yale", "read": True}, {"name": "Penn", "read": True}, {"name": "Princeton", "read": False}]}
        line = TR.sources_line(plan)
        self.assertTrue(line.startswith("Times from Yale's and Penn's own calendars, read today; Princeton: its published pattern only"))
        self.assertNotIn("Harvard", line)
        self.assertNotIn("Brown", line)


if __name__ == "__main__":
    TG.unittest.main()


from tests import test_campusme_cr1 as TC  # noqa: E402


class OneSchool(TC.OnWhatsApp):
    """CR 43 · "Yale on October 14" on the founder's account: the live hand-over too (before: Penn only)."""

    def test_yale_on_the_founders_account_is_filled_live(self):
        spawned = []
        with mock.patch.dict(os.environ, FOUNDER), mock.patch.object(GW, "_spawn", lambda c: (spawned.append(c), c.close())):
            self.save_profile(TC.HandOver.PROFILE)
            self.say("campus visits at Yale on October 14 for my son")
            self.say("", payload=self.last_buttons()[0][1])
            self.say("", payload=self.last_buttons()[0][1])
        self.assertIn("I'm also filling Yale's own form for you in Sasha's browser — “Tap to finish” comes to your phone", self.said())
        self.assertEqual(len(spawned), 1)

    def test_no_cloud_browser_is_said(self):
        with mock.patch.dict(os.environ, {**FOUNDER, "BROWSERBASE_API_KEY": ""}), mock.patch.object(GW, "_spawn", lambda c: c.close()):
            self.save_profile(TC.HandOver.PROFILE)
            self.say("campus visits at Yale on October 14 for my son")
            self.say("", payload=self.last_buttons()[0][1])
            self.say("", payload=self.last_buttons()[0][1])
        self.assertIn("I couldn't open Yale's filled page (the cloud browser isn't set up on this server)", self.said())


def load_tests(loader, tests, pattern):
    """Only this file's own tests (OneSchool inherits test_campusme_cr1's, which run there)."""
    suite = TG.unittest.TestSuite()
    for cls in (PennTour, Live, Words):
        suite.addTests(loader.loadTestsFromTestCase(cls))
    for name in ("test_yale_on_the_founders_account_is_filled_live", "test_no_cloud_browser_is_said"):
        suite.addTest(OneSchool(name))
    return suite
