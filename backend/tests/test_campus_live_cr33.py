"""CR 33 · CampusMe's live hand-over on a school's real Slate form (Penn's, one page): filled from the student's details, the
session ticked IN the form, every value read back; the statement box and SUBMIT left for the parent (two taps); a CAPTCHA,
a second page, a ticked statement or an SMS opt-in → no link; only the founder (or a signed DPA); read-only stops the press.
Offline: a fake cloud page, a fake Browserbase.

    cd backend && python -m unittest tests.test_campus_live_cr33 -v
"""
from __future__ import annotations

import asyncio
import os
import unittest
from unittest import mock

from booking_signer import handover as HO
from products import store as ST
from products.campus import live as LV, turn as CT
from products.campus.slate import Session
from tests.test_handover_cr23 import FakeBB

FOUNDER = "11111111-2222-3333-4444-555555555555"
EVENT = "76e86e3b-5ee8-418a-b8e8-c093d315c24d"
SESSION = Session(school="penn", day="2026-10-07", start="10:15", end=None, title="Morning Tour · Campus Tours (1 hr 30 mins)",
                  location=None, status="open", spaces=None, form_url="https://key.admissions.upenn.edu/portal/campus-visit?id=x",
                  event_id=EVENT, read={})
PROFILE = {"first": "Sam", "last": "Warren", "email": "sam@example.com", "birthdate": "2009-03-14", "high_school": "Madrid HS",
           "grad_year": "2027"}
OPTS = {"RegistrantType": ["Prospective Student/Parent", "School Counselor"], "sys:attendees": ["1", "2", "3"],
        "sys:field:prospect_type": ["First-year", "Transfer Student"], "sys:field:term": ["Fall 2027", "Fall 2028"]}
REQUIRED = ("RegistrantType", "sys:attendees", "sys:field:prospect_type", "sys:field:term", "sys:first", "sys:last", "sys:email",
            "sys:email2", "sys:birthdate", "understand")


class FakeSlate:
    captcha = False
    pages = 1
    tick_understand = False
    after_submit = "Thank you for registering! A confirmation email is on its way."

    def __init__(self):
        self.v, self.session, self.read_only, self.pressed, self.closed = {}, None, None, None, False

    async def connect(self, url): pass
    async def guard(self, read_only): self.read_only = read_only
    async def goto(self, url): self.url = url
    async def settle(self): pass

    async def choose(self, export, want):
        pick = next((o for o in OPTS[export] if o.lower() == want.lower()), None)
        if not pick:
            raise HO.Refused("not_all_prefilled", "no option")
        self.v[export] = pick
        return pick

    async def type_in(self, export, value): self.v[export] = value
    async def birthdate(self, iso): self.v["sys:birthdate"] = iso
    async def tick_session(self, eid): self.session = eid

    async def read_slate(self):
        qs = [{"export": e, "type": "x", "required": e in REQUIRED, "visible": True, "label": e, "value": self.v.get(e, "")}
              for e in REQUIRED + ("schoolname", "sys:field:text_opt_in")]
        qs.append({"export": "related_campustour", "type": "plugin:event", "required": False, "visible": True, "label": "Tours",
                   "value": f"id={self.session}&summary=x" if self.session else ""})
        if self.tick_understand:
            next(q for q in qs if q["export"] == "understand")["value"] = "Yes, I understand"
        return {"url": self.url, "qs": qs, "frames": [], "pay": False, "pages": self.pages, "next": self.pages > 1,
                "submit": "SUBMIT", "captcha": self.captcha, "text": ""}

    async def point_at_book(self): return "SUBMIT"

    async def watch(self, on_tap, on_press, read_only, on_nav):
        self.on_press = on_press

    async def answer(self):
        return {"text": self.after_submit, "qs": [], "submit": ""}

    async def screenshot(self): return b"png"
    async def close(self): self.closed = True


class Base(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.bb = FakeBB()
        self.saved = (HO.BB, LV.PAGE_FACTORY, dict(HO.HANDOVERS), ST.STORE)
        self.pages = []

        def factory():
            p = FakeSlate()
            self.pages.append(p)
            return p
        HO.BB, LV.PAGE_FACTORY = self.bb, factory
        ST.STORE = ST.MemoryCaseStore()
        FakeSlate.captcha, FakeSlate.pages, FakeSlate.tick_understand = False, 1, False
        self.env = mock.patch.dict(os.environ, {"BROWSERBASE_API_KEY": "k", "FOUNDER_ACCOUNT_ID": FOUNDER, "BROWSERBASE_DPA": ""})
        self.env.start()

    def tearDown(self):
        for r in HO.HANDOVERS.values():
            if r.get("_watch"):
                r["_watch"].cancel()
        HO.BB, LV.PAGE_FACTORY, ST.STORE = self.saved[0], self.saved[1], self.saved[3]
        HO.HANDOVERS.clear(), HO.HANDOVERS.update(self.saved[2])
        self.env.stop()

    async def open(self, account=FOUNDER, read_only=False, fictional=False, session=SESSION, profile=PROFILE):
        return await LV.open_campus_handover(session=session, profile=dict(profile), attendees=2, account=account,
                                             read_only=read_only, fictional=fictional)


class Rules(Base):
    async def test_a_real_student_only_for_the_founder(self):
        with self.assertRaises(HO.Refused) as e:
            await self.open(account="99999999-0000-0000-0000-000000000000")
        self.assertEqual((e.exception.rule, self.bb.created), ("no_dpa", []))

    async def test_two_page_forms_are_refused_before_any_session(self):
        yale = Session(**{**SESSION.__dict__, "school": "yale", "event_id": None})
        with self.assertRaises(HO.Refused) as e:
            await self.open(session=yale)
        self.assertEqual((e.exception.rule, self.bb.created), ("two_pages", []))

    async def test_missing_details_are_asked_before_any_session(self):
        with self.assertRaises(HO.Refused) as e:
            await self.open(profile={**PROFILE, "birthdate": ""})
        self.assertIn("birthdate", e.exception.say)
        self.assertEqual(self.bb.created, [])

    async def test_a_captcha_a_second_page_or_a_ticked_statement_means_no_link(self):
        for attr, val, rule in (("captcha", True, "captcha"), ("pages", 2, "two_pages"), ("tick_understand", True, "consent_box")):
            FakeSlate.captcha, FakeSlate.pages, FakeSlate.tick_understand = False, 1, False
            setattr(FakeSlate, attr, val)
            with self.assertRaises(HO.Refused) as e:
                await self.open()
            self.assertEqual(e.exception.rule, rule)
            self.assertTrue(self.pages[-1].closed)
        self.assertEqual(len(self.bb.released), 3)                      # every refusal releases its session


class Filled(Base):
    async def test_filled_from_the_details_two_taps_left_session_in_the_form(self):
        rec = await self.open()
        p = self.pages[-1]
        self.assertEqual(rec["state"], "ready")
        self.assertEqual((rec["taps_left"], rec["book_label"], rec["box_label"]), (2, "SUBMIT", "Yes, I understand"))
        self.assertEqual(p.session, EVENT)
        self.assertEqual((p.v["sys:first"], p.v["sys:email2"], p.v["sys:field:term"], p.v["RegistrantType"]),
                         ("Sam", "sam@example.com", "Fall 2027", "Prospective Student/Parent"))
        self.assertNotIn("understand", p.v)                             # the statement: never touched
        self.assertNotIn("sys:field:text_opt_in", p.v)                  # the SMS opt-in: never touched
        self.assertFalse(p.read_only)
        self.assertEqual(rec["summary"]["name"], "Sam Warren")
        self.assertIn(rec["id"], HO.HANDOVERS)

    async def test_read_only_stops_the_press(self):
        rec = await self.open(account=None, read_only=True, fictional=True, profile=LV.FICTIONAL)
        self.assertTrue(self.pages[-1].read_only)
        self.pages[-1].on_press("SUBMIT")
        await asyncio.wait_for(rec["_watch"], 2)
        self.assertEqual(rec["state"], "read_only_stopped")

    async def test_his_press_then_the_schools_own_words_and_the_case(self):
        cid = await ST.STORE.put("campus", FOUNDER, "wa", {"status": "handed_over"})
        rec = await self.open()
        case = await ST.STORE.get(cid)
        case["state"]["live_handover"] = {"id": rec["id"]}
        await ST.STORE.update(cid, case["state"])
        self.pages[-1].on_press("SUBMIT")
        await asyncio.wait_for(rec["_watch"], 2)
        self.assertEqual(rec["state"], "booked")
        self.assertIn("Thank you for registering", rec["say"])
        st = (await ST.STORE.get(cid))["state"]
        self.assertEqual(st["status"], "registered_by_you_on_their_page")
        self.assertEqual(st["live_handover"]["state"], "booked")

    async def test_no_confirmation_words_is_never_a_tick(self):
        FakeSlate.after_submit = "Please correct the errors below."
        try:
            rec = await self.open()
            self.pages[-1].on_press("SUBMIT")
            await asyncio.wait_for(rec["_watch"], 2)
            self.assertEqual(rec["state"], "answered")
            self.assertNotIn("✅", rec["say"])
        finally:
            FakeSlate.after_submit = "Thank you for registering! A confirmation email is on its way."


class Hook(unittest.TestCase):
    def test_the_case_hook_is_registered_once(self):
        CT._hook()
        self.assertEqual(LV.CAMPUS_DONE.count(CT._live_done), 1)


if __name__ == "__main__":
    unittest.main()
