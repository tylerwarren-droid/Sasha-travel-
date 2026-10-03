"""CR 1 · CampusMe: the schools' own calendars read (Yale's and Penn's real pages, saved 3 Oct 2026), cards, one yes on
the exact read-back, the hand-over — and NOTHING submitted, no statement ticked, the model never called. Offline: the
fake fetch serves docs/campusme/reads/ copies (tests/fixtures/campusme/); the WhatsApp turn is the real one.

    cd backend && python -m unittest tests.test_campusme_cr1 -v
"""
from __future__ import annotations

import base64
import json
import os
import pathlib
import re
import tempfile
import uuid
from datetime import date, datetime, timezone
from unittest import mock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from booking_signer import guest_whatsapp as GW
from booking_signer.vault import crypto as VC, kms as VK
from booking_signer.vault.store import MemoryVaultStore
from products import routes as PR, store as ST, whatsapp as PW
from products.campus import handover as HV, request as RQ, schools as SC, slate as SL, turn as CT, visits as VS, watch as WT
from tests import test_guest_whatsapp_s75 as TG

run = TG.run
FX = pathlib.Path(__file__).parent / "fixtures" / "campusme"
TODAY = datetime(2026, 10, 3, 12, 0, tzinfo=timezone.utc)
# Penn's own capacity answer for 14 Oct, as its page asks it: the morning tour full, the rest open
PENN_COUNTS = {"results": {"results": [{"id": "59cec248-9619-46f4-8698-20c0c12815b9", "exceed": "1", "waitlist": "1"},
                                       {"id": "b07aac08-1090-40e7-aa5d-813a4276d14a", "exceed": "0", "waitlist": "1"},
                                       {"id": "5202ff52-f6ee-43b4-91b9-b2e3dac3db39", "exceed": "0", "waitlist": "1"},
                                       {"id": "be0d9d6b-e918-42ae-8391-c46b49c82ecf", "exceed": "0", "waitlist": "1"}]}}


class FakeWeb:
    """The two schools' hosts, from the saved reads. Records every request; a submit would be recorded too."""

    def __init__(self):
        self.calls = []
        self.robots = "User-agent: gsa-crawler\nDisallow: /\n\nUser-agent: GPTBot\nDisallow: /\n\nUser-agent: *\nDisallow:\n"
        self.yale_list = (FX / "yale-list-2026-10-14.html").read_text()

    async def __call__(self, method, url, form):
        self.calls.append((method, url, form))
        if url.endswith("/robots.txt"):
            return 200, self.robots
        if "apps.admissions.yale.edu" in url:
            if "cmd=event_dates" in url:
                return 200, (FX / ("yale-dates-2027-04.json" if "dtstart=2027-04" in url else "yale-dates-2026-10.json")).read_text()
            if "cmd=event_list" in url:
                return 200, self.yale_list
            if "/register/?id=" in url:
                return 200, (FX / "yale-register-df1cf083.html").read_text()
        if "key.admissions.upenn.edu" in url:
            if "cmd=getDates" in url:
                return 200, (FX / "penn-dates-2026-10_12.json").read_text()
            if "cmd=getEvents" in url:
                return 200, (FX / "penn-events-2026-10-14.html").read_text()
            if "cmd=counts" in url and method == "POST":
                return 200, json.dumps(PENN_COUNTS)
            if "?id=" in url:
                return 200, (FX / "penn-event-dbda7b29.html").read_text()
        return 404, "not found"

    def posts(self):
        return [(u, f) for m, u, f in self.calls if m == "POST"]


class Fixtures(TG.Base):
    def setUp(self):
        super().setUp()
        self.web = FakeWeb()
        self.saved = (SL.READER, ST.STORE, ST.BASE)
        SL.READER = SL.Reader(self.web, pace=0)
        ST.STORE, ST.BASE = ST.MemoryCaseStore(), None
        self.now = datetime.now(timezone.utc).replace(year=2026, month=10, day=3)   # vault windows run on the real clock

    def tearDown(self):
        SL.READER, ST.STORE, ST.BASE = self.saved
        super().tearDown()


class Reading(Fixtures):
    def test_yale_sessions_with_the_schools_own_spaces(self):
        got = run(SL.sessions(SC.SCHOOLS["yale"], "2026-10-14"))
        self.assertEqual([(x.start, x.title, x.spaces) for x in got],
                         [("09:00", "Campus Tour", 51), ("11:30", "Campus Tour", 57), ("14:00", "Campus Tour", 1),
                          ("15:30", "Science and Engineering Tour", 2)])
        self.assertTrue(all(x.form_url == "https://apps.admissions.yale.edu/register/?id=df1cf083-3180-4fb0-b77b-97730c543ef0" for x in got))
        self.assertTrue(all(x.read["sha256"] and x.read["status"] == 200 for x in got))

    def test_penn_full_is_the_schools_own_answer_not_its_hidden_template(self):
        got = {x.title.split(" · ")[0]: x.status for x in run(SL.sessions(SC.SCHOOLS["penn"], "2026-10-14", attendees=2))}
        self.assertEqual(got, {"Morning Information Session": "open", "Morning Tour": "full",
                               "Afternoon Information Session": "open", "Afternoon Tour": "open"})
        (url, form), = self.web.posts()
        self.assertIn("/register/form?cmd=counts", url)           # the only POST: Slate's own capacity read
        self.assertEqual(form["attendees"], "2")

    def test_robots_read_first_and_obeyed(self):
        run(SL.sessions(SC.SCHOOLS["yale"], "2026-10-14"))
        self.assertTrue(self.web.calls[0][1].endswith("/robots.txt"))
        self.web.robots = "User-agent: KanoeCampusMe\nDisallow: /\n"
        SL.READER = SL.Reader(self.web, pace=0)
        with self.assertRaises(SL.ReadRefused):
            run(SL.sessions(SC.SCHOOLS["yale"], "2026-10-14"))

    def test_unreadable_robots_means_unread(self):
        async def broken(method, url, form):
            return (503, "") if url.endswith("robots.txt") else (200, "{}")
        SL.READER = SL.Reader(broken, pace=0)
        with self.assertRaises(SL.ReadRefused):
            run(SL.dates(SC.SCHOOLS["yale"], date(2026, 10, 1), date(2026, 10, 31)))

    def test_the_ask_in_words(self):
        a = RQ.parse("campus visits at Yale and Penn in April for my son", date(2026, 10, 3))
        self.assertEqual(([s["key"] for s in a.schools], a.month, a.who, a.guests), (["yale", "penn"], (2027, 4), "son", 1))
        self.assertIsNone(RQ.parse("may we see Penn in may", date(2026, 10, 3)).day)
        self.assertEqual(RQ.parse("may we see Penn in may", date(2026, 10, 3)).month, (2027, 5))
        self.assertIn("503", RQ.parse("harvard", date(2026, 10, 3)).unreadable[0])


class HandOver(Fixtures):
    PROFILE = {"first": "Sam", "last": "Ejemplo", "email": "sam@example.com", "birthdate": "2009-03-14",
               "high_school": "Hopkins School", "grad_year": "2028"}

    def rows(self, school, day="2026-10-14"):
        s = SC.SCHOOLS[school]
        sess = [x for x in run(SL.sessions(s, day, 2)) if x.status == "open"][0]
        qs, challenge, _, pages = run(SL.form(sess.form_url))
        return HV.plan(qs, self.PROFILE, sess, 2, "your vault"), challenge, pages

    def test_yale_form_filled_from_the_profile_by_slates_own_keys(self):
        rows, challenge, pages = self.rows("yale")
        by = {r["label"]: r for r in rows}
        self.assertEqual(by["Student Email Address"]["answer"], "sam@example.com")
        self.assertEqual(by["Birthdate"]["answer"], "14 March 2009")
        self.assertEqual(by["Intended Enrollment"]["answer"], "Fall 2028")
        self.assertEqual(by["I am a visiting:"]["answer"], "Prospective Student")
        self.assertEqual(by["Number of guests (in addition to registrant). Limit 3."]["answer"], "1")
        self.assertEqual(by["Educator Email Address"]["action"], HV.NOT_YOU)
        self.assertFalse(challenge)
        self.assertEqual(pages, 2)

    def test_a_statement_is_always_theirs_to_tick(self):
        rows, _, _ = self.rows("penn")
        stmts = [r for r in rows if r["type"] == "checkbox" and r["required"] and r["action"] != HV.NOT_YOU]
        self.assertTrue(stmts)
        self.assertTrue(all(r["action"] == HV.YOU and r["answer"] is None for r in stmts))
        sms = [r for r in rows if "text message" in r["label"].lower()]
        self.assertTrue(sms and all(r["action"] == HV.YOU for r in sms))
        self.assertEqual({r["answer"] for r in rows if r["label"].startswith("Total Attendees")}, {"2"})


    def test_only_the_matching_session_question_is_chosen_and_a_statement_keeps_its_words(self):
        rows, _, _ = self.rows("penn")
        chosen = [r["label"] for r in rows if r["action"] == HV.CHOOSE]
        self.assertEqual(len(chosen), 1)                                    # not "Wharton School: … information sessions …"
        self.assertTrue(chosen[0].startswith("Information Session"))
        stmt = [r for r in rows if r["type"] == "checkbox" and r["required"] and r["action"] == HV.YOU]
        self.assertTrue(any("you understand" in r["label"] for r in stmt))   # its words come from the paragraph above it


class OnWhatsApp(Fixtures):
    def setUp(self):
        super().setUp()
        fd, self.kek = tempfile.mkstemp(); os.write(fd, base64.b64encode(os.urandom(32))); os.close(fd)
        self.venv = mock.patch.dict(os.environ, {"SASHA_VAULT_LOCAL_KEK_FILE": self.kek, "SASHA_VAULT_KMS_KEY": "",
                                                 "SASHA_VAULT_GCP_SA_JSON": "", "ENV": "", "RAILWAY_ENVIRONMENT_NAME": ""})
        self.venv.start()
        VK.reset()
        self.saved_v = VC.STORE
        VC.STORE = MemoryVaultStore()
        self.link()

    def tearDown(self):
        VC.STORE = self.saved_v
        self.venv.stop()
        super().tearDown()

    def said(self):
        return "\n".join(self.bodies() + [b for b, _ in GW.SENDER.contents])

    def last_buttons(self):
        return GW.SENDER.contents[-1][1]

    def save_profile(self, profile):
        item = str(uuid.uuid4())
        sealed = run(VC.seal(TG.ACCOUNT, item, "identifier", json.dumps({"value": json.dumps(profile)}).encode()))
        now = datetime.now(timezone.utc)
        run(VC.STORE.create({"id": item, "account_id": TG.ACCOUNT, "provider": "kanoe.ai", "label": "CampusMe student details (Sam)",
                             "kind": "identifier", **sealed, "special_category": False, "created_at": now, "updated_at": now}))
        return item

    def test_cards_to_hand_over_with_the_vault_and_nothing_submitted(self):
        self.save_profile(HandOver.PROFILE)
        self.say("campus visits at Yale on October 14 for my son")
        said = self.said()
        self.assertIn("Reading Yale's own visit calendar for Wednesday 14 October…", said)
        self.assertIn("1. *Yale* — Campus Tour\nWed 14 Oct, 9:00 AM · Visitor Center · 51 spaces left", said)
        self.assertIn("apps.admissions.yale.edu — the schools' own calendars", said)
        self.say("", payload=self.last_buttons()[0][1])
        rb = self.said()
        self.assertIn("• I'll use your saved CampusMe student details (Sam) from your vault.", rb)
        self.assertIn("stop before its Register button: you press it. I send nothing to Yale.", rb)
        self.assertIn("creates a record for the student in Yale's admissions system", rb)
        self.assertNotIn("sam@example.com", rb)                        # the vault opens only under the yes
        self.say("", payload=self.last_buttons()[0][1])
        done = self.said()
        cid = re.search(r"https://sasha\.test/campus-handover/([\w-]{22})", done).group(1)
        case = run(ST.STORE.get(cid))["state"]
        self.assertEqual(case["status"], "handed_over")
        self.assertTrue(any(r["answer"] == "sam@example.com" for r in case["rows"]))
        self.assertIn("Reply REGISTERED", done)
        self.assertEqual([u for u, _ in self.web.posts()], [])          # ⛔ no POST to Yale at all
        self.assertFalse(any("cmd=submit" in u for _, u, _ in self.web.calls))
        uses = run(VC.STORE.uses_of(TG.ACCOUNT))
        self.assertEqual([(u["action_kind"], u["status"]) for u in uses], [("campusme_prepare", "done")])   # opened once, logged

    def test_intake_once_then_the_read_back_names_every_detail(self):
        self.say("campus Yale October 14 for my daughter")
        self.say("", payload=self.last_buttons()[0][1])
        self.assertIn("What's your daughter's full name", self.said())
        for a in ("Ana Ejemplo", "ana@example", "ana@example.com", "14 March 2009", "Hopkins School", "2028"):
            self.say(a)
        self.assertIn("That doesn't look like an email address", self.said())
        self.say("", payload="cm:save:no")
        self.assertIn("• Student: Ana Ejemplo · ana@example.com · born 14 March 2009 · Hopkins School · graduating 2028.", self.said())
        self.say("yes")
        self.assertIn("filled from what you told me on WhatsApp", self.said())

    def test_keep_in_vault_goes_through_the_real_vault_route(self):
        """CR 2 · the rehearsal found "I couldn't keep them in your vault": the vault names a provider by its ADDRESS.
        Here the turn reaches the real POST /api/booking/vault (in process, as the guest), not a fake."""
        GW.api = self.gw_saved[2]
        self.venv2 = mock.patch.dict(os.environ, {"SASHA_BOOKING_KEY": "k"}); self.venv2.start()
        try:
            self.say("campus Yale October 14 for my son")
            self.say("1")
            for a in ("Sam Ejemplo", "sam@example.com", "14 March 2009", "Hopkins School", "2028"):
                self.say(a)
            self.say("", payload="cm:save:yes")
            self.assertIn("Kept in your vault as “CampusMe student details (Sam)”", self.said())
            items = run(VC.STORE.list(TG.ACCOUNT))
            self.assertEqual([(i["provider"], i["kind"]) for i in items], [("kanoe.ai", "identifier")])
            self.assertIn("• I'll use your saved CampusMe student details (Sam) from your vault.", self.said())
            self.say("", payload=self.last_buttons()[0][1])
            self.assertIn("filled from your vault", self.said())
        finally:
            self.venv2.stop()

    def test_april_not_published_is_said_and_watched(self):
        self.say("campus visits at Yale and Penn in April for my son")
        said = self.said()
        self.assertIn("*Yale* hasn't published April 2027 yet", said)
        self.assertIn("*Penn* hasn't published April 2027 yet", said)
        self.assertIn("I'll check daily and message you the day April opens", said)
        watching = run(ST.STORE.watching())
        self.assertEqual(watching[0]["state"]["watch"]["schools"], ["yale", "penn"])
        self.web.yale_list = self.web.yale_list   # April opens at Yale:
        orig = self.web.__call__

        async def april(method, url, form):
            if "apps.admissions.yale.edu" in url and "dtstart=2027-04-01" in url:
                return 200, '{"dates":[["2027-04-06","0"]]}'
            return await orig(method, url, form)
        SL.READER = SL.Reader(april, pace=0)
        GW.SENDER.sent.clear()
        run(GW.STORE.put_state(GW.wa_key(TG.GUEST), {**run(GW.STORE.get_state(GW.wa_key(TG.GUEST))),
                                                    "last_inbound_at": datetime.now(timezone.utc)}))
        self.assertEqual(run(WT.tick()), 1)
        self.assertIn("Yale just published April 2027 visit dates", self.bodies()[-1])

    def test_registered_then_the_schools_own_words_confirm_it(self):
        self.save_profile(HandOver.PROFILE)
        self.say("campus Yale October 14 for my son")
        self.say("", payload=self.last_buttons()[0][1])
        self.say("", payload=self.last_buttons()[0][1])
        self.say("REGISTERED")
        said = self.said()
        self.assertIn("registered on your word", said)
        self.assertIn("calendar.google.com/calendar/render?action=TEMPLATE", said)
        self.assertRegex(said, r"https://sasha\.test/api/products/campus/[\w-]{22}/visit\.ics")
        self.say("Thank you for registering for a campus visit. We look forward to seeing you soon — see you then!")
        self.assertIn("doesn't name Yale and 14 October", self.said())
        self.say("Yale Undergraduate Admissions: your registration is confirmed for Wednesday, October 14 at 9:00 AM.")
        self.assertIn("✅ Confirmed in Yale's own words", self.said())

    def test_modes_switch_and_sasha_is_untouched_outside_them(self):
        self.say("hello")
        self.assertIn("Tell me what to book", self.bodies()[-1])
        self.say("campus")
        self.assertIn("CampusMe here", self.bodies()[-1])
        self.say("exit")
        self.assertEqual(self.bodies()[-1], "OK.")
        self.say("hello")
        self.assertIn("Tell me what to book", self.bodies()[-1])
        self.assertEqual(self.api_paths(), [])                          # Sasha's booking routes never called by CampusMe

    def test_a_password_typed_in_a_mode_is_refused_and_not_kept(self):
        self.say("campus")
        self.say("my password is hunter2hunter2")
        st = run(GW.STORE.get_state(GW.wa_key(TG.GUEST)))
        self.assertNotIn("hunter2", json.dumps(st, default=str))


class Pages(Fixtures):
    def test_the_hand_over_page_and_its_calendar_file(self):
        s, x = SC.SCHOOLS["yale"], run(SL.sessions(SC.SCHOOLS["yale"], "2026-10-14"))[0].as_dict()
        cid = run(ST.STORE.put("campus", TG.ACCOUNT, "k", {"school": "yale", "session": x, "form_url": x["form_url"],
                                                          "rows": [{"label": "Student Email Address", "action": "fill",
                                                                    "answer": "a@b.co", "source": "your vault"}],
                                                          "status": "handed_over"}))
        app = FastAPI(); app.include_router(PR.router)
        c = TestClient(app)
        j = c.get(f"/products/campus/{cid}").json()
        self.assertEqual((j["school"]["name"], j["submits"], j["counts"]), ("Yale", False, {"fill": 1}))
        self.assertEqual(c.get("/products/campus/nope").status_code, 404)
        ics = c.get(f"/products/campus/{cid}/visit.ics").text
        self.assertIn("DTSTART:20261014T130000Z", ics)                # 9:00 in New Haven = 13:00 UTC in October
        self.assertIn("STATUS:TENTATIVE", ics)
        self.assertIn("dates=20261014T130000Z%2F20261014T140000Z", VS.google_link(s, x))
