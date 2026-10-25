"""Sasha 253 · THE BOOKING CONTACT (G5) — offline (the booking API is a recorder; Sasha's read is given; no model, no database).

  EU's S2 items 7/8, found live: "book La Mi Venta" → "their booking page needs a name and a mobile number" — and she stopped:
  the brain had no way to take one. Now hold_venue's contact_missing tells her to ask ONCE, with the consent sentence word for
  word; save_contact saves what the person said through PUT /api/booking/contact (the one person record /you edits), with that
  consent; the next hold uses it. Never a name or number they didn't give; on WhatsApp "this number" is their linked number.
  Old S1 (SASHA_S1_PARITY=off) is untouched: no tool, its own words.

    cd backend && python -m unittest tests.test_s253_contact -v
"""
from __future__ import annotations

import asyncio
import json
import os
import unittest
import uuid
from unittest import mock

from agapi import v0 as API, venues as VN
from booking_signer import contacts as CT, guest_accounts as GA, guest_receipt as GR, guest_whatsapp as GW
from tests.test_venue_pick_230 import FormApi, reader

ACCT = "00000000-0000-4000-8000-000000000253"
LATER = (__import__("datetime").date.today() + __import__("datetime").timedelta(days=6)).isoformat()
VENUE = {"name": "La Mi Venta", "city": "Madrid", "country": "ES", "what": "dinner", "party": 2, "day": LATER, "time": "21:00"}
SENT = ("/api/booking/forms", "/api/booking/emails", "/api/booking/calls", "/api/booking/links")


class ContactApi(FormApi):
    """The booking API with the real contact route's rules: none saved until a PUT under the current consent."""
    def __init__(self):
        super().__init__()
        self.contact = None

    async def __call__(self, account, method, path, body=None, timeout=90.0):
        if path == "/api/booking/contact":
            self.calls.append((method, path, body))
            c = CT.consent()
            if method == "GET":
                return 200, {"contact": self.contact, "consent": c}
            if method == "PUT":
                if (body or {}).get("consent_version") != c["version"] or body.get("consent_sha256") != c["sha256"]:
                    return 422, {"rule": "consent_not_current", "message": "nothing was saved"}
                mobile = CT.e164(body.get("mobile"))
                if not mobile:
                    return 422, {"rule": "mobile_invalid", "message": "a mobile is written with its country code"}
                self.contact = {"name": CT.name_case(body["name"]), "mobile_e164": mobile}
                return 200, {"ok": True, "contact": self.contact}
        return await super().__call__(account, method, path, body, timeout)


class _Store(GW.MemoryGuestStore):   # Sasha 288 · the real store's shape (get_state too): a fake never lacks a method it has
    def __init__(self, number=None):
        super().__init__()
        self.number = number

    async def channel_of_account(self, account):
        return {"account_id": account, "number_e164": self.number} if self.number else None


class Base(unittest.TestCase):
    session = "s253"

    def setUp(self):
        from tests.test_s254_one_decider import live_access   # Sasha 254 · the executors behind the booking rules: a person who may reach real venues
        live_access(self)
        VN._HELD.pop(ACCT, None)
        VN._ASKED.pop(ACCT, None)
        self.api = ContactApi()
        for p in (mock.patch.object(GW, "api", self.api), mock.patch.object(GA, "founder", lambda a: False),
                  mock.patch.object(GR, "address_of", mock.AsyncMock(return_value="alex@example.test")),
                  # Sasha 270 · MOVED (CR 101): their form is the engine's read on the one path; "Handle it" is AgAPI's send (faked)
                  mock.patch.object(VN, "engine_channel", __import__("tests.test_s254_one_decider", fromlist=["x"]).engine_from({"form": {}})),
                  mock.patch.object(VN, "_known_name", mock.AsyncMock(return_value=None)),
                  mock.patch.object(VN, "_read", reader({"form": {}})),
                  mock.patch.object(GW, "STORE", _Store("+447700900333"))):
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(VN._HELD.pop, ACCT, None)
        self.addCleanup(VN._ASKED.pop, ACCT, None)
        from tests.test_s254_handle_it_live import use_fake_agapi
        self.agapi = use_fake_agapi(self)

    def booked_for(self):
        """Sasha 270 · MOVED: who the booking is for, as AgAPI's venue.prepare_booking got it (was Sasha's own /api/booking/forms)."""
        return [b["person"] for o, b, _a in self.agapi.calls if o == "venue.prepare_booking"][-1]

    def ctx(self, said, surface="s2"):
        return API.Ctx(account=ACCT, mode="test", user_said=said, session=self.session, surface=surface)

    def hold(self, said="Book La Mi Venta for two on Saturday at nine.", surface="s2", **extra):
        VN._HELD.pop(ACCT, None)
        key = uuid.uuid4().hex   # a fresh call each time (never the process's replay of an earlier test's)
        # Sasha 254 · "Handle it" (route form): the booking rules' fill_form_zero_touch — the form's read-back, the contact in it
        return asyncio.run(API.call(self.ctx(said, surface), "hold_venue", {**VENUE, "route": "form", **extra, "idempotency_key": key}))

    def save(self, said, **args):
        return asyncio.run(API.call(self.ctx(said), "save_contact", args))

    def puts(self):
        return [b for m, p, b in self.api.calls if p == "/api/booking/contact" and m == "PUT"]

    def sent(self):
        return [p for m, p, b in self.api.calls if p in SENT]


class AskedOnceAndKept(Base):
    def test_no_contact_is_contact_missing_with_the_consent_sentence(self):
        r = self.hold()
        self.assertEqual(r["error"]["code"], "contact_missing")
        self.assertIn(CT.consent()["text"], r["error"]["message"])          # said word for word when she asks
        self.assertIn("ONCE", r["error"]["message"])
        self.assertIn("save_contact", r["error"]["message"])
        self.assertEqual(self.sent(), [])                                    # nothing reaches the venue

    def test_their_words_are_saved_with_the_consent_then_the_hold_goes_on(self):
        self.hold()
        r = self.save("Tyler Warren, +34 600 111 222", name="Tyler Warren", mobile="+34 600 111 222")
        self.assertTrue(r["ok"], r)
        c = CT.consent()
        self.assertEqual(self.puts(), [{"name": "Tyler Warren", "mobile": "+34600111222", "consent_version": c["version"],
                                        "consent_sha256": c["sha256"]}])
        out = self.hold("Tyler Warren, +34 600 111 222")
        self.assertTrue(out["ok"], out)
        self.assertEqual(out["result"]["status"], "awaiting_yes")
        who = self.booked_for()
        self.assertEqual(who["name"], "Tyler Warren")                           # the read-back's booking, under that name
        self.assertEqual(who["phone"], "+34600111222")

    def test_a_number_without_its_code_takes_the_venues_country(self):
        self.hold()
        self.assertTrue(self.save("Tyler Warren 600 111 222", name="Tyler Warren", mobile="600 111 222")["ok"])
        self.assertEqual(self.puts()[0]["mobile"], "+34600111222")

    def test_never_a_name_or_number_they_didnt_give(self):
        self.hold()
        r = self.save("yes please", name="Tyler Warren", mobile="+34 600 111 222")
        self.assertEqual(r["error"]["code"], "not_their_words")
        r = self.save("Tyler Warren", name="Tyler Warren", mobile="+34 699 999 999")
        self.assertEqual(r["error"]["code"], "not_their_words")
        r = self.save("+34 600 111 222", name="Tyler Warren", mobile="+34 600 111 222")
        self.assertEqual(r["error"]["code"], "not_their_words")
        self.assertEqual(self.puts(), [])                                    # nothing saved

    def test_a_name_given_in_the_ask_turn_needs_only_the_mobile(self):
        self.hold("Book La Mi Venta for Tyler Warren, two people, Saturday at nine.")
        r = self.save("+34 600 111 222", name="Tyler Warren", mobile="+34 600 111 222")
        self.assertTrue(r["ok"], r)

    def test_asked_once(self):
        self.hold()
        again = self.hold("hmm")
        self.assertEqual(again["error"]["code"], "contact_missing")
        self.assertIn("never ask again", again["error"]["message"])
        self.assertNotIn(CT.consent()["text"], again["error"]["message"])   # not the question a second time
        self.save("Tyler Warren, +34 600 111 222", name="Tyler Warren", mobile="+34 600 111 222")
        for said in ("Book La Mi Venta for two.", "And the same again."):     # kept: never asked again
            self.assertTrue(self.hold(said)["ok"])
        self.assertEqual(len(self.puts()), 1)

    def test_under_another_name_keeps_their_own_contact(self):
        r = self.hold("Book La Mi Venta under Alex Gate.", under="Alex Gate")
        self.assertIn("under", r["error"]["message"])
        self.save("Tyler Warren, +34 600 111 222", name="Tyler Warren", mobile="+34 600 111 222")
        self.assertTrue(self.hold("Book La Mi Venta under Alex Gate.", under="Alex Gate")["ok"])
        self.assertEqual(self.booked_for()["name"], "Alex Gate")
        self.assertEqual(self.api.contact["name"], "Tyler Warren")


class WhatsAppThisNumber(Base):
    session = "wa:" + "k" * 64

    def test_this_number_is_their_linked_whatsapp_number(self):
        r = self.hold()
        self.assertIn("WhatsApp number", r["error"]["message"])
        self.assertTrue(self.save("Tyler Warren, this number", name="Tyler Warren", this_number=True)["ok"])
        self.assertEqual(self.puts()[0]["mobile"], "+447700900333")

    def test_only_the_name_and_the_number_defaults(self):
        self.hold()
        self.assertTrue(self.save("Tyler Warren", name="Tyler Warren")["ok"])
        self.assertEqual(self.puts()[0]["mobile"], "+447700900333")

    def test_not_on_the_web(self):
        self.session = "s253-web"
        self.hold()
        self.assertEqual(self.save("Tyler Warren, this number", name="Tyler Warren", this_number=True)["error"]["code"], "mobile_missing")


class OnlyWhereTheBrainIs(Base):
    def test_old_s1_is_untouched(self):
        with mock.patch.dict(os.environ, {"SASHA_S1_PARITY": "off"}):
            r = self.hold(surface="s1")
        self.assertEqual(r["error"]["message"], "the venue needs the person's name and mobile — ask them, once")
        self.assertNotIn("save_contact", [t["name"] for t in API.TOOLS])   # S1's list

    def test_on_s2_whatsapp_and_next_under_parity(self):
        from app.agent import s2 as S2
        self.assertIn("save_contact", S2.S2_TOOLS)
        self.assertIn("save_contact", [t["name"] for t in API.HOME_TOOLS])
        self.assertIn(CT.consent()["text"], self.hold(surface="s1")["error"]["message"])   # /next under parity: the same ask

    def test_on_the_capability_list(self):
        from agapi import s2_home as HOME
        self.assertIn(("Keep your booking name and mobile — asked once", "save_contact"),
                      [i for g in HOME.CAPABILITIES for i in g["items"]])


class BrainPath(Base):
    """The old flow's capability test (test_guest_whatsapp_s75 test_no_contact_saved_means_no_booking), on the one brain: no
    contact saved → no booking is placed, and what she's told carries the ask for the name and mobile."""
    session = "wa:" + "b" * 64

    def turn(self, steps, message):
        import app.services.llm as LLM
        from agapi import s2_home as HOME
        from app.agent import sasha as AG
        from app.agent.fakes import client
        seen = []

        async def go():
            async for _ in AG.turn_with_quiver(ACCT, message, [], self.session, surface="wa"):
                pass
        with mock.patch.object(LLM, "client", client(steps, seen=seen)), mock.patch.object(HOME, "RUN", None), \
                mock.patch("booking_signer.plan_store._run", lambda: None):
            asyncio.run(go())
        return seen

    def test_no_contact_saved_means_no_booking(self):
        from app.agent.fakes import Block
        seen = self.turn([[Block(type="tool_use", id="t1", name="hold_venue", input=dict(VENUE))],
                          [Block(type="text", text="Whose name should I book under?")]], "book La Mi Venta for two on Saturday at 9")
        self.assertIn("save_contact", [t["name"] for t in seen[0]["tools"]])
        result = json.dumps(seen[1]["messages"], default=str)
        self.assertIn("contact_missing", result)
        self.assertIn("name and mobile", result)
        self.assertEqual(self.sent(), [])                                    # nothing booked, nothing placed


if __name__ == "__main__":
    unittest.main()
