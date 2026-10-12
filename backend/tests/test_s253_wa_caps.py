"""Sasha 253 · item 5 — the old WhatsApp flow is retired; its CAPABILITY tests (docs/sasha/S252-whatsapp-capabilities.md, "The
listed failing tests — MECHANIC or CAPABILITY") are MOVED here, onto the one brain, before the old ones go. Each class names the
old test(s) it replaces. Twins that already existed are named in the report (and below), not written twice:

    test_a_yes_after_fifteen_minutes_places_nothing         → test_safety_215 TheYes.test_a_booking_prepared_over_15_minutes_ago_is_never_sent
    test_no_contact_saved_means_no_booking                  → test_s253_contact BrainPath.test_no_contact_saved_means_no_booking
    test_sasha104_luxury_puts_three_euro_signs_first        → test_s253_venue_gaps G14Luxury
    test_3_a_forwarded_confirmation_on_whatsapp_is_…        → test_s253_gaps G1ForwardedConfirmation
    Progress / cancel-by-email's later push                 → test_s253_gaps G2ResultsPushed
    hotel_ladder_s138 / hotel_test_s135 / travel_s132 Hotels → test_s253_venue_gaps G8*
    hotel_ladder_s138 EngineCheck                           → test_s253_gaps G15OpsConsole
    travel_s132 Rehearsal2 (a time question)                → test_s253_gaps G9TimeQuestion
    modes_cr15 test_sashas_open_question_wins_over_a_bare_ad → test_s252_g3 ProductsSeeNoQuestionAfterABrainTurn

Offline: the REAL GW.turn → wa_agent.agent_turn → sasha.turn_with_quiver with a scripted model (ScriptedBrain), the booking API
faked in process (test_guest_whatsapp_s75.FakeApi); no network, no live model, no Twilio, no Places, no database.

    cd backend && python -m unittest tests.test_s253_wa_caps -v
"""
from __future__ import annotations

import json
import os
import unittest
from datetime import date, datetime, timedelta, timezone
from unittest import mock

from agapi import s2_manage as MG, venues as VN
from app.agent.fakes import Block
from booking_signer import guest_whatsapp as GW
from tests import test_guest_whatsapp_s75 as TG
from tests.test_s253_gaps import ScriptedBrain

run, ACCOUNT, GUEST, NOW = TG.run, TG.ACCOUNT, TG.GUEST, TG.NOW
TODAY = date.today()
SOON = (TODAY + timedelta(days=2)).isoformat()
BASE = {"party": 2, "status": "confirmed", "status_words": "confirmed by the restaurant", "receipt": None, "time": "21:00"}


def tool(tool_name, **inp):
    return [Block(type="tool_use", id=f"t-{tool_name}", name=tool_name, input=inp)]


def says(text):
    return [Block(type="text", text=text)]


class OnTheBrain(ScriptedBrain):
    def setUp(self):
        super().setUp()
        self.link()
        run(GW.STORE.put_state(GW.wa_key(GUEST), {"history": [], "pending": None, "last_inbound_at": NOW, "link_tries": []}))
        GW.api.reservations = [{**BASE, "id": "t-1", "venue": "Botavara Chamberí", "date": SOON}]
        for d in (VN._CANCEL, VN._HELD, VN._READS):
            d.pop(ACCOUNT, None)
            self.addCleanup(d.pop, ACCOUNT, None)
        self.old = mock.patch.object(GW, "_cancel_find", mock.AsyncMock(side_effect=AssertionError("the old cancel flow ran")))
        self.old.start()
        self.addCleanup(self.old.stop)

    def posted_cancels(self):
        return [c for c in GW.api.calls if c[1] == "POST" and c[2].endswith("/cancel")]


# ── cancelling (guest_whatsapp_s75 Turns: cancel by email, the founder's cancels, cancel wins over search / while cards show) ──

class Cancel(OnTheBrain):
    def test_cancel_by_email_says_cancelling_never_cancelled_until_their_words(self):
        claim = mock.patch("agapi.v0.claim", mock.AsyncMock())   # the durable once-only claim (its own tests: test_safety_215)
        claim.start()
        self.addCleanup(claim.stop)
        self.brain([tool("cancel_venue", venue="Botavara", idempotency_key="k1"), says("Cancel Botavara Chamberí on Saturday? I'll email them."),
                    tool("cancel_venue", approval={"said": "yes, cancel it"}, idempotency_key="k2"), says("Cancelling with Botavara Chamberí now.")])
        self.say("cancel Botavara")
        self.assertIn("awaiting_yes", self.tool_results())                     # the read-back first …
        self.assertIn("I'll email them to cancel.", self.tool_results())
        self.assertEqual(self.posted_cancels(), [])                               # … nothing sent before the yes
        self.say("yes, cancel it")
        (post,) = self.posted_cancels()
        self.assertEqual(post[2], "/api/booking/reservations/t-1/cancel")
        self.assertEqual(post[3]["read_back_sha256"], "e" * 64)                  # bound to what was read back
        self.assertIn('status\\": \\"requested', self.tool_results())                        # asked — never "cancelled" on our word
        self.assertFalse(any("has cancelled" in b for b in self.bodies()))
        self.assertIn("watch_cancel", self.spawned)                              # their written words are watched for (G2)

    def test_the_founders_cancels_and_a_no_cancels_nothing(self):
        GW.api.reservations = [{**BASE, "id": "t-2", "venue": "Restaurante Yatri", "date": SOON, "status": "unclear"}]
        self.brain([tool("cancel_venue", trip_item_id="t-2", idempotency_key="k3"), says("Cancel Restaurante Yatri?"),
                    tool("cancel_venue", approval={"said": "No"}, idempotency_key="k4"), says("OK — nothing was cancelled."),   # a model that tries anyway
                    tool("cancel_venue", venue="Yatri", idempotency_key="k5"), says("Cancel Restaurante Yatri?")])
        self.say("Please cancel")
        self.say("No")
        self.assertIn("no_explicit_yes", self.tool_results())                    # a No is never a yes, whatever the model does
        self.assertEqual(self.bodies()[-1], "OK — nothing was cancelled.")
        self.say("No Please Cancel Yatri")
        self.assertIn("Restaurante Yatri", self.tool_results())
        self.assertEqual(self.posted_cancels(), [])                               # nothing until a yes

    def cancel_wins(self, pend, key):
        run(GW.STORE.put_state(GW.wa_key(GUEST), {"history": [], "pending": pend, "last_inbound_at": NOW, "link_tries": []}))
        self.brain([tool("cancel_venue", venue="Botavara", idempotency_key=key), says("Cancel Botavara Chamberí?")])
        self.say("Cancel the Botavara dinner.")
        paths = [c[2] for c in GW.api.calls]
        self.assertNotIn("/api/booking/venues/find", paths)                      # never a search
        self.assertIn("/api/booking/reservations/t-1/cancel", paths)             # its cancellation, read back
        self.assertEqual(self.posted_cancels(), [])
        self.assertEqual(self.bodies()[-1], "Cancel Botavara Chamberí?")

    def test_cancel_wins_over_search_without_cards(self):
        self.cancel_wins(None, "k6")

    def test_cancel_wins_over_search_with_cards_left_from_before_the_switch(self):
        self.cancel_wins({"kind": "cards", "at": NOW.isoformat(), "nonce": "a1b2c3", "find": {"what": "dinner", "where": "Chamberí, Madrid"},
                          "cards": [{"name": "Casa Lucio", "place_id": "p2"}]}, "k7")


class TheList(unittest.TestCase):
    """guest_whatsapp_s75 test_sasha109_several_bookings_get_a_numbered_list + test_sasha117_the_cancel_list_is_upcoming_only_and_
    tells_twins_apart: what the brain is given to list — upcoming only, each twin with its own reference and id."""

    def test_upcoming_only_and_twins_told_apart(self):
        rows = [{**BASE, "id": "t-1", "venue": "La Contra", "date": (TODAY - timedelta(days=1)).isoformat()},
                {**BASE, "id": "t-2", "venue": "Sasha Test Venue", "date": SOON, "booking_reference": "TV-62BB32"},
                {**BASE, "id": "t-3", "venue": "Sasha Test Venue", "date": SOON, "booking_reference": "TV-FE41E1"}]

        async def api(account, method, path, body=None, timeout=90.0):
            return 200, {"reservations": rows}
        with mock.patch.object(GW, "api", api), mock.patch("agapi.s2_outcomes.sync", mock.AsyncMock()):
            got = run(VN.venue_bookings(ACCOUNT))
        self.assertEqual([(b["trip_item_id"], b.get("reference")) for b in got], [("t-2", "TV-62BB32"), ("t-3", "TV-FE41E1")])

    def test_no_booking_found_is_asked_which(self):
        from agapi import v0 as API

        async def api(account, method, path, body=None, timeout=90.0):
            return 200, {"reservations": []}
        with mock.patch.object(GW, "api", api), mock.patch("agapi.s2_outcomes.sync", mock.AsyncMock()):
            r = run(API.call(API.Ctx(account=ACCOUNT, surface="s2"), "cancel_venue", {"venue": "Nowhere", "idempotency_key": "k-none"}))
        self.assertEqual(r["error"]["code"], "booking_unknown")                  # "which booking?" — never a guess


class Tonight(unittest.TestCase):
    """guest_whatsapp_s75 test_sasha121_tonights_dinner_is_todays_booking_not_a_name: "tonight" is a day, never a name — the words
    (GW.cancel_intent / cancel_day, shared with the products) and the brain's day filter (my_plans on=today)."""

    def test_the_words(self):
        self.assertEqual((GW.cancel_intent("cancel tonight's dinner"), GW.cancel_day("cancel tonight's dinner")), ("", "today"))
        self.assertEqual((GW.cancel_intent("cancela la cena de esta noche"), GW.cancel_day("cancela la cena de esta noche")), ("", "today"))
        self.assertEqual(GW.cancel_day("cancel tomorrow's lunch at Botavara"), "tomorrow")

    def test_todays_booking_only(self):
        from booking_signer import basket as BK, plan_store as PS
        venues = [{"trip_item_id": "t-1", "venue": "Botavara Chamberí", "date": TODAY.isoformat(), "time": "21:00", "party": 2},
                  {"trip_item_id": "t-2", "venue": "Casa Lucio", "date": (TODAY + timedelta(days=1)).isoformat(), "time": "21:00", "party": 2}]
        from agapi import v0 as API
        with mock.patch.object(VN, "venue_bookings", mock.AsyncMock(return_value=venues)), \
                mock.patch.object(PS, "plans", mock.AsyncMock(return_value=[])), mock.patch.object(BK, "items", mock.AsyncMock(return_value=[])):
            r = run(MG.my_plans(API.Ctx(account=ACCOUNT, surface="s2"), {"on": TODAY.isoformat()}))
        self.assertEqual([(i["title"], i["id"]) for i in r["items"]], [("Botavara Chamberí", "t-1")])


# ── a cuisine is a table (guest_whatsapp_s75 test_sasha121_a_cuisine_is_a_table_not_a_question) ──────────────────────────────

class Cuisine(unittest.TestCase):
    def test_a_cuisine_is_a_table_not_a_question(self):
        from agapi import v0 as API
        drafts = []

        async def api(account, method, path, body=None, timeout=90.0):
            if path == "/api/booking/draft":
                drafts.append(body["text"])
                return 200, {"parts": {"what": {"activity": "a table", "activity_venue_lang": "una mesa", "category": "restaurant"}}
                             if "restaurant" in body["text"] else {}}
            if path == "/api/booking/contact":
                return 200, {"contact": {"name": "Tyler Warren", "mobile_e164": GUEST}}
            return 404, {}
        with mock.patch.object(GW, "api", api):
            r = run(VN._reservation(API.Ctx(account=ACCOUNT, surface="s2"), {"what": "Japanese", "day": SOON, "time": "21:30", "party": 2},
                                    {"country": "ES"}))
        self.assertEqual(drafts, ["Japanese", "Japanese restaurant"])
        self.assertEqual(r["what"]["category"], "restaurant")                    # a table — no "what should I book there?"


# ── receipts, a voice note not made out, the rehearsal venue ──────────────────────────────────────────────────────────────────

class Receipts(OnTheBrain):
    """guest_whatsapp_s75 test_receipts: "my bookings" → the brain's my_plans, drawn on WhatsApp."""

    def test_receipts(self):
        from booking_signer import basket as BK, plan_store as PS
        self.brain([tool("my_plans"), says("You have Botavara Chamberí coming up.")])
        with mock.patch.object(PS, "plans", mock.AsyncMock(return_value=[])), mock.patch.object(BK, "items", mock.AsyncMock(return_value=[])), \
                mock.patch("agapi.s2_outcomes.sync", mock.AsyncMock()):
            self.say("my bookings")
        self.assertIn("Botavara Chamberí", self.tool_results())
        self.assertIn("Botavara Chamberí", "\n".join(self.bodies()))


class VoiceNote(TG.Base):
    """guest_whatsapp_s75 test_sasha104_a_voice_note_not_made_out_is_asked_again: the brain is told it couldn't be made out (and
    asks again in its own words); nothing is searched or booked."""

    def test_a_voice_note_not_made_out_is_asked_again(self):
        TG.stand_in_brain(self)
        ch = self.link()
        run(GW.turn(ch, TG.SANDBOX, {"From": f"whatsapp:{GUEST}", "Body": "", "NumMedia": "1", "MediaContentType0": "audio/ogg"}))
        self.assertEqual(self.brain_saw, ["[they sent a voice note that couldn't be made out]"])
        self.assertEqual(GW.api.calls, [])


class Rehearsal(OnTheBrain):
    """guest_whatsapp_s75 test_sasha117_the_rehearsal_books_our_test_venue_never_a_real_one — covered differently on the brain: a
    WhatsApp venue read carries the S2 demo setting, and the server stands our test venue in for the accounts that have it
    (test_s2_221 DemoSetting / test_who_has_the_demo_setting pin that side)."""

    def test_a_whatsapp_read_carries_the_demo_setting(self):
        hold = {"name": "Botavara Chamberí", "city": "Madrid", "country": "ES", "what": "dinner", "party": 2, "day": SOON, "time": "21:00"}
        self.brain([tool("hold_venue", **hold), says("Shall I?")])
        self.say("book Botavara for 2 at 9")
        read = next(c[3] for c in GW.api.calls if c[2] == "/api/booking/venues/read")
        self.assertTrue(read.get("s2_demo"))


if __name__ == "__main__":
    unittest.main()
