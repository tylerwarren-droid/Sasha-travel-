"""CR 38 · CampusMe, a four-school tour ("Ivy tour week of 15 Nov: Yale, Harvard, Princeton, Brown"): the family's details asked
once; Yale and Brown read from their own calendars (saved reads of 6 Oct 2026), Princeton and Harvard never read — their
published pattern, "check on their page", their exact link; drives checked (a fixed Google answer here); a night near each next
morning's campus; Yale and Brown filled for the family's press (founder) or linked (everyone else), Princeton and Harvard linked
with each detail its own message; ONE itinerary — card, PDF, and the same trip on the account. Nothing is submitted.

    cd backend && python -m unittest tests.test_tour_cr38 -v
"""
from __future__ import annotations

import os
from pathlib import Path
from unittest import mock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from booking_signer import guest_whatsapp as GW, handover as HO, plan_store as PS
from products import routes as PR, store as ST
from products.campus import live as LV, slate as SL, tour as TR
from tests import test_guest_whatsapp_s75 as TG

run = TG.run
FX = Path(__file__).parent / "fixtures" / "cr38"
ASK = "campus Ivy tour week of 15 Nov: Yale, Harvard, Princeton, Brown"
FAMILY = ["Padre Ejemplo", "Prueba Sasha", "prueba@example.com", "202 555 0123", "Kanoe Test High School", "2027", "Engineering",
          "14 March 2009", "100 Example Street, Princeton, NJ 08540", "3"]


class Web:
    def __init__(self):
        self.calls = []

    async def __call__(self, method, url, form):
        self.calls.append((method, url))
        if url.endswith("/robots.txt"):
            return 200, "User-agent: *\nDisallow:\n"
        for school, host in (("yale", "apps.admissions.yale.edu"), ("brown", "apply.college.brown.edu")):
            if host in url and "cmd=event_list" in url:
                day = url.split("date=")[1][:10]
                f = FX / f"{school}-list-{day}.html"
                return 200, f.read_text() if f.exists() else "<html></html>"
        return 404, "not found"


class Base(TG.Base):
    def setUp(self):
        super().setUp()
        self.web = Web()
        self.saved = (SL.READER, ST.STORE, ST.BASE, PS.save, GW._spawn)
        SL.READER = SL.Reader(self.web, pace=0)
        ST.STORE, ST.BASE = ST.MemoryCaseStore(), None
        self.trips = []

        async def save(account, itinerary, message, now):
            self.trips.append((itinerary, message))
            return "trip-tour"
        PS.save = save

        async def travel(o, d, depart, mode):
            return {("Princeton", "Yale"): 3 * 3600 + 13 * 60, ("Yale", "Manning"): 6300}.get((o.split()[0] if "Princeton" in o else o.split()[0], d.split()[0]), 4300)
        self.p_travel = mock.patch("booking_signer.proactive.travel", travel)
        self.p_travel.start()
        self.spawned = []
        GW._spawn = lambda coro: self.spawned.append(coro)
        self.link()

    def tearDown(self):
        for c in self.spawned:
            c.close()
        self.p_travel.stop()
        SL.READER, ST.STORE, ST.BASE, PS.save, GW._spawn = self.saved
        super().tearDown()

    def said(self):
        return "\n".join(self.bodies() + [b for b, _ in GW.SENDER.contents])

    def pend(self):
        return run(GW.STORE.get_state(GW.wa_key(TG.GUEST)))["pending"]

    def through_intake(self):
        self.say(ASK)
        for a in FAMILY:
            self.say(a)
        self.say("", payload="cm:tkeep:no")


class Tour(Base):
    def test_the_week_from_what_is_really_published(self):
        self.through_intake()
        self.assertIn("Sun 15 Nov: Princeton (check its page) · night near Yale", self.said())   # CR 52 · one line per day
        self.say("", payload="cm:more:plan")                                            # the full plan, behind a tap
        said = self.said()
        self.assertIn("■ Sunday 15 November", said)
        self.assertIn("Princeton — weekdays: an information session", said)
        self.assertIn("check on their page: https://apply.princeton.edu/portal/tours_info", said)
        self.assertIn("Yale — Campus Tour · 9:00 AM (from its own calendar)", said)
        self.assertIn("Brown — Information Session and Campus Tour · 1:30 PM (from its own calendar)", said)
        self.assertIn("■ Tuesday 17 November", said)
        self.assertIn("check on their page: https://apply.college.harvard.edu/portal/campus-visit", said)
        self.assertIn("🏨 Night near Yale — New Haven", said)
        self.assertNotIn("princeton.edu", " ".join(u for _, u in self.web.calls))       # never fetched
        self.assertNotIn("harvard.edu", " ".join(u for _, u in self.web.calls))
        self.assertEqual([m for m, _ in self.web.calls if m != "GET"], [])              # only reads

    def test_everyone_gets_links_and_copy_messages_one_itinerary_and_the_trip(self):
        self.through_intake()
        self.say("", payload=f"cm:tyes:{self.pend()['tour']['sha']}")
        said = self.said()
        for link in ("apply.princeton.edu/portal/tours_info", "apply.college.harvard.edu/portal/campus-visit",
                     "apps.admissions.yale.edu/register/?id=", "apply.college.brown.edu/register/?id="):
            self.assertIn(link, said)
        self.say("", payload="cm:more:details")                                         # CR 52 · behind "Copy my details"
        self.assertIn("prueba@example.com", self.bodies())                               # each detail its own message
        self.assertIn("03/14/2009", self.bodies())
        (itin, msg), = self.trips
        self.assertEqual([d["date"] for d in itin["days"]], ["2026-11-15", "2026-11-16", "2026-11-17"])
        self.assertTrue(msg.startswith("from 15 Nov"))
        cid = self.pend()["tour"]["case_id"]
        app = FastAPI(); app.include_router(PR.router)
        c = TestClient(app)
        self.assertEqual(c.get(f"/products/campus/{cid}/tour.pdf").headers["content-type"], "application/pdf")
        self.assertEqual(c.get(f"/products/campus/{cid}/tour-card.jpg").headers["content-type"], "image/jpeg")
        self.say("registered Princeton")
        st = run(ST.STORE.get(cid))["state"]
        self.assertTrue(next(v for v in st["plan"]["visits"] if v["school"] == "princeton")["status"].startswith(
            "Registration not confirmed"))                                              # CR 45 · its confirmation decides
        self.assertEqual(self.spawned, [])                                              # no hand-over for a guest

    def test_the_founder_gets_yale_and_brown_filled(self):
        with mock.patch.dict(os.environ, {"FOUNDER_ACCOUNT_ID": TG.ACCOUNT, "BROWSERBASE_API_KEY": "k"}):
            self.through_intake()
            self.say("", payload=f"cm:tyes:{self.pend()['tour']['sha']}")
        self.assertEqual(len(self.spawned), 2)                                          # Yale and Brown, in the background
        self.assertIn("apply.princeton.edu/portal/tours_info", self.said())
        self.assertNotIn("apps.admissions.yale.edu/register/?id=", self.said())


class Values(TG.unittest.TestCase):
    def test_what_goes_in_and_what_stays_the_familys(self):
        y = {v["export"]: v["value"] for v in LV.tour_values("yale", dict(LV.FICTIONAL_FAMILY))}
        b = {v["export"]: v["value"] for v in LV.tour_values("brown", dict(LV.FICTIONAL_FAMILY))}
        self.assertEqual((y["sys:guests"], y["sys:field:term"], b["sys:attendees"], b["sys:preferred"]), ("2", "Fall 2027", "3", "Prueba"))
        self.assertNotIn("sys:mobile", b)                         # Brown's mobile box carries a consent to texts: theirs
        self.assertNotIn("additional_questions_student", b)


if __name__ == "__main__":
    TG.unittest.main()
