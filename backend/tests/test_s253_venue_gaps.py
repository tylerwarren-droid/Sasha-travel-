"""Sasha 253 · item 4 (part 2) — the VENUE gaps of the WhatsApp old flow, built in the ONE engine path (agapi/venues.py
`_engine_route` → the executors), each capability test MOVED to the brain's path (docs/sasha/S252-whatsapp-capabilities.md rows
38, 54, 55, 57, 64; GAPS G7, G8, G14). The old-flow tests went with the old flow (Sasha 253 · item 5).

    G7   a request with NO slot: an email asking for a date and a quote (a tattoo, custom work); "whenever they have space"
         (the old flow's venue_proposes) — hold_venue's `open_slot`, day/time optional on /s2, WhatsApp and /next under parity
    G8   a REAL request to a hotel for N nights: its own booking engine with the stay in the link, an email asking for a room, a
         call that says the stay (in Spanish in Spain) — hold_venue's `nights`, the same ladder        (hotel_ladder_s138 OnWhatsApp
         ×2, hotel_test_s135 test_request_from_the_hotel_is_the_real_path + EmailOnlyVenue, travel_s132 Hotels ×2)
    G14  (a) a matching loyalty number from the Keep goes into the form / the prepared page (masked in what she says)
         (b) "luxury": €€€ and up first in a venue search                     (guest_whatsapp_s75 test_sasha104_luxury_…)

Old S1 (SASHA_S1_PARITY=off) keeps its schema and its day + time byte-identical (the S1 fingerprint, and OldS1Untouched here).
Offline: the booking API is a recorder (nothing leaves the process); no model except the scripted one; no Places, no database.

    cd backend && python -m unittest tests.test_s253_venue_gaps -v
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import os
import unittest
from datetime import date, time, timedelta
from unittest import mock

from agapi import s2_outcomes as OC, v0 as API, venues as VN
from app.agent import sasha as AG
from app.agent.fakes import Block
from booking_signer import emailing as E, guest_accounts as GA, guest_receipt as GR, guest_whatsapp as GW, loyalty as LY
from booking_signer import wa_brain as WB
from booking_signer.vault import crypto as VC
from scripts.venue_suite import FakeApi
from tests import test_guest_whatsapp_s75 as TG
from tests.test_s253_gaps import ScriptedBrain

ACCT = "00000000-0000-4000-8000-000000000254"
run = asyncio.run
LATER = (date.today() + timedelta(days=9)).isoformat()
OUT_DAY = (date.today() + timedelta(days=11)).isoformat()
PARITY_OFF = {"SASHA_S1_PARITY": "off"}


class Api(FakeApi):
    """The venue suite's booking API, plus the hotel engine's link (SynXis, the stay in it) — every call recorded."""

    def __init__(self):
        super().__init__()
        self.read = None

    async def __call__(self, account, method, path, body=None, timeout=90.0):
        if path == "/api/booking/venues/read" and self.read:
            self.calls.append((method, path, body))
            return 200, self.read
        if path == "/api/booking/links" and (body or {}).get("nights"):
            self.calls.append((method, path, body))
            return 200, {"link_id": "l-1", "platform": "SynXis", "slot_filled": False, "trip_item_id": "t-h",
                         "url": f"https://be.synxis.com/?hotel=1&arrive={LATER}&depart={OUT_DAY}&adult=2&rooms=1",
                         "read_back": {"lines": ["Hotel Test books rooms through its own booking engine (SynXis)."], "sha256": "h" * 64}}
        if path == "/api/booking/links/l-1/opened":
            self.calls.append((method, path, body))
            return 200, {"url": f"https://be.synxis.com/?hotel=1&arrive={LATER}&depart={OUT_DAY}&adult=2&rooms=1", "status": "link_sent"}
        if path == "/api/booking/forms" and not (body or {}).get("handover"):
            self.calls.append((method, path, body))
            return 200, {"form_id": "f-9", "trip_item_id": "t-9", "read_back": {"lines": ["Casa Gate · 2 people"], "sha256": "f" * 64}}
        return await super().__call__(account, method, path, body, timeout)

    def bodies(self, path):
        return [b for _m, p, b in self.calls if p == path]


def reader(rungs, venue="Casa Gate", country="ES"):
    async def rd(ctx, a):
        return {"read_id": "r-1", "country": country, "venue": venue, "facts": [], "rungs": rungs, "open_now": True,
                "opens_at": None, "say": "", "place_id": a.get("place_id")}
    return rd


class Base(unittest.TestCase):
    surface, session = "s2", "s254"

    def setUp(self):
        from tests.test_s254_one_decider import live_access   # Sasha 254 · the executors behind the booking rules: a person who may reach real venues
        live_access(self)
        VN._HELD.pop(ACCT, None)
        self.api = Api()
        self.taps, self.told = [], []

        async def tap(account, text, url, link_id=None, venue=None, when=None):
            self.taps.append((text, url))
            return "sent (captured)"

        async def tell(ch, text, template=None):
            self.told.append(text)
            return "sent (captured)"

        class _Store:
            async def channel_of_account(self, acct):
                return {"wa_id_sha256": "x" * 64}
        for p in (mock.patch.object(GW, "api", self.api), mock.patch.object(GA, "founder", lambda a: False),
                  mock.patch.object(GR, "address_of", mock.AsyncMock(return_value="alex@example.test")),
                  mock.patch.object(VN, "engine_channel", mock.AsyncMock(return_value=None)),
                  mock.patch.object(GW, "tap_platform", tap), mock.patch.object(GW, "_tell", tell),
                  mock.patch.object(GW, "STORE", _Store()),
                  mock.patch.object(WB, "trip_day_words", mock.AsyncMock(return_value="It's in your bookings")),
                  mock.patch.object(OC, "booked", mock.AsyncMock()), mock.patch("agapi.v0.claim", mock.AsyncMock()),
                  mock.patch.object(LY, "find_for", mock.AsyncMock(return_value=None))):
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(VN._HELD.pop, ACCT, None)

    def ctx(self, said="", surface=None, later=False):
        c = API.Ctx(account=ACCT, mode="test", user_said=said, session=self.session, surface=surface or self.surface)
        if later:
            c.started = VN._HELD[ACCT]["at"] + timedelta(minutes=1)
        return c

    def hold(self, rungs, venue="Casa Gate", country="ES", said="", surface=None, **a):
        args = {"name": venue, "city": "Madrid", "country": country, "what": "dinner", "party": 2, **a}
        with mock.patch.object(VN, "_read", reader(rungs, venue, country)):
            return run(VN.hold_venue(self.ctx(said, surface), args))

    def yes(self):
        return run(VN.book_venue(self.ctx("yes, go ahead", later=True), {"approval": {"said": "yes, go ahead"}}))


# ── the schema: the new fields on the one path only ────────────────────────────────────────────────────────────────────────

class TheSchemaOnTheOnePath(unittest.TestCase):
    def test_open_slot_and_nights_on_the_one_path_and_day_time_optional_there(self):
        t = VN.with_under(API.BY_NAME["hold_venue"])
        self.assertIn("open_slot", t["input_schema"]["properties"])
        self.assertIn("nights", t["input_schema"]["properties"])
        self.assertNotIn("day", t["input_schema"]["required"])
        self.assertNotIn("time", t["input_schema"]["required"])
        base = API.BY_NAME["hold_venue"]["input_schema"]                   # old S1's own schema: untouched
        self.assertNotIn("open_slot", base["properties"])
        self.assertNotIn("nights", base["properties"])
        self.assertIn("time", base["required"])

    def test_the_model_is_given_them_on_whatsapp_s2_and_next_with_parity_only(self):
        from app.agent.fakes import client
        import app.services.llm as LLM

        def props(surface, parity):
            seen = []

            async def go():
                async for _ in AG.turn("00000000-0000-4000-8000-000000000254", "hi", [], f"s254-{surface}-{parity}", surface=surface):
                    pass
            with mock.patch.object(LLM, "client", client([[Block(type="text", text="Hello.")]], seen=seen)), \
                    mock.patch.dict(os.environ, {"SASHA_S1_PARITY": parity}):
                asyncio.run(go())
            return next(t for t in seen[0]["tools"] if t["name"] == "hold_venue")["input_schema"]
        for surface, parity, want in (("wa", "on", True), ("s2", "off", True), ("s1", "on", True), ("s1", "off", False)):
            sch = props(surface, parity)
            self.assertEqual("nights" in sch["properties"], want, (surface, parity))
            self.assertEqual("open_slot" in sch["properties"], want, (surface, parity))
            self.assertEqual("time" in sch["required"], not want, (surface, parity))

    def test_api_call_asks_no_time_on_the_one_path_only(self):
        s2 = API.Ctx(account=ACCT, mode="test", surface="s2")
        self.assertEqual(VN.required_of(s2, "hold_venue", ["name", "day", "time"]), ["name"])
        with mock.patch.dict(os.environ, PARITY_OFF):
            s1 = API.Ctx(account=ACCT, mode="test", surface="s1")
            r = run(API.call(s1, "hold_venue", {"name": "Casa Gate", "city": "Madrid", "party": 2, "idempotency_key": "k1"}))
        self.assertEqual(r["error"], {"code": "missing_input", "message": "missing: day, time"})   # old S1: exactly as it was


# ── G7 · a request with no slot ────────────────────────────────────────────────────────────────────────────────────────────

class G7NoSlot(Base):
    def test_custom_work_is_an_email_asking_for_a_date_and_a_quote_read_back_then_the_yes(self):
        out = self.hold({"email": {"value": "ink@studio.es"}, "phone": {"fact_index": 0}}, venue="Tinta Studio",
                        what="a forearm tattoo, black and grey", open_slot="quote", day=LATER)
        self.assertEqual((out["status"], out["route"]), ("awaiting_yes", "email"))
        body = self.api.bodies("/api/booking/emails")[0]
        self.assertEqual(body, GW.quote_email("r-1", "Alex Gate", "alex@example.test", "a forearm tattoo, black and grey", LATER))
        self.assertNotIn("time", body)                                                           # no slot in it
        self.assertEqual(out["say"], GW.quote_sentence("Tinta Studio", LATER))                    # the old flow's own sentence
        self.assertIn("a date and a quote", out["what_happens"])
        self.assertEqual(self.api.bodies("/api/booking/calls"), [])                               # the email, not a call
        got = self.yes()
        self.assertEqual(got["status"], "requested")                                             # never "booked"
        self.assertEqual(self.api.bodies("/api/booking/emails/e-1/send")[0]["read_back_sha256"], "c" * 64)

    def test_a_one_word_want_asks_what_they_can_offer(self):
        self.hold({"email": {}}, what="tattoo", open_slot="quote")
        self.assertEqual(self.api.bodies("/api/booking/emails")[0]["quote"],
                         {"what": "tattoo — please tell me what you can offer", "dates": ""})

    def test_whenever_they_have_space_by_phone_only_the_rules_wait(self):
        # Sasha 254 · the booking rules (R3): no form and no time (so not within 48 h) → no call now — a call closer to the day,
        # and with no day there is nothing to call closer to: she asks for one (the old flow's instant availability call is retired)
        out = self.hold({"phone": {"fact_index": 2}}, what="a 60-minute massage", open_slot="whenever")
        self.assertEqual((out["status"], out["rules"]["action"]), ("need_day", "wait"))
        self.assertEqual(self.api.bodies("/api/booking/calls"), [])
        # Sasha 269 · MOVED (CR 100): with a day but no time ("whenever they have space") the act has no slot to ask for — no call of
        # Sasha's own (the old availability call was /api/booking/calls, never placed without an act): said, with the take-over
        with self.assertRaises(API.ToolError) as e:
            self.hold({"phone": {"fact_index": 2}}, what="a 60-minute massage", open_slot="whenever", day=LATER)
        self.assertEqual(e.exception.code, "no_route")
        self.assertEqual(self.api.bodies("/api/booking/calls"), [])

    def test_the_venue_engines_own_page_never_takes_a_request_with_no_slot(self):
        eng = {"kind": "own_engine", "url": "https://casagate.es/reservas", "from": "engine", "ask": True,
               "alternative": {"kind": "email"}}
        with mock.patch.object(VN, "engine_channel", mock.AsyncMock(return_value=eng)):
            out = self.hold({"email": {}, "own_page": {"value": "https://casagate.es/reservas"}}, open_slot="whenever")
        self.assertEqual((out["status"], out["route"]), ("awaiting_yes", "email"))                 # no choose_route, no prefilled page
        self.assertEqual(self.api.bodies("/api/booking/links"), [])

    def test_no_time_and_no_open_slot_says_how(self):
        with self.assertRaises(API.ToolError) as e:
            self.hold({"email": {}}, day=LATER)
        self.assertEqual(e.exception.code, "when_invalid")
        self.assertIn("open_slot", e.exception.message)

    def test_a_given_time_wins_over_open_slot(self):
        out = self.hold({"email": {}}, open_slot="quote", day=LATER, time="11:00", route="email")
        body = self.api.bodies("/api/booking/emails")[0]
        self.assertEqual((body["date"], body["time"]), (LATER, "11:00"))
        self.assertNotIn("quote", body)
        self.assertEqual(out["route"], "email")


# ── G8 · a real request to a hotel, on the same ladder ─────────────────────────────────────────────────────────────────────

class G8HotelOnTheLadder(Base):
    HOTEL = {"link": {"fact_index": 1, "value": "SynXis"}, "email": {"fact_index": 2, "value": "res@hoteltest.es"}}

    def test_book_with_hotel_sends_its_own_engine_with_the_stay(self):
        """hotel_ladder_s138 OnWhatsApp.test_book_with_hotel_sends_its_own_engine_with_the_stay, on the brain's path."""
        self.session = "wa:s254"
        # Sasha 254 · the booking rules: SynXis is a booking platform (R14) — its page handed over; with the hotel's OWN email too,
        # the email comes first (R1: own channels before a platform)
        out = self.hold(self.HOTEL, venue="Hotel Test Madrid", what="hotel", day=LATER, nights=2)
        self.assertEqual((out["status"], out["route"], out["rules"]["action"]), ("awaiting_yes", "email", "request_email"))
        VN._HELD.pop(ACCT, None)
        out = self.hold({"link": self.HOTEL["link"]}, venue="Hotel Test Madrid", what="hotel", day=LATER, nights=2)
        self.assertEqual((out["status"], out["route"]), ("awaiting_yes", "page"))                  # no "email or book now?"
        link = self.api.bodies("/api/booking/links")[0]
        self.assertEqual((link["nights"], link["date"], link["party"]), (2, LATER, 2))
        self.assertEqual(link["time"], "15:00")                                                     # check-in, as the old flow
        got = self.yes()
        text, url = self.taps[-1]
        self.assertIn("One tap: Hotel Test Madrid's own booking engine (SynXis).", text)
        self.assertIn(f"https://be.synxis.com/?hotel=1&arrive={LATER}", text)
        self.assertEqual(got["status"], "page_on_phone")
        self.assertFalse(any(p in ("/api/booking/forms",) for _m, p, _b in self.api.calls))

    # Sasha 269 · MOVED (CR 100): a hotel STAY by phone was Sasha's own call (/api/booking/calls) — a call no act opened, never placed.
    # Every call is an AgAPI act now, and a stay (nights) has none: said plainly, with the take-over — never a call of Sasha's own
    def test_a_call_says_the_stay_in_spanish_in_spain(self):
        with self.assertRaises(API.ToolError) as e:
            self.hold({"phone": {"fact_index": 0}}, venue="Hotel Test Madrid", what="hotel", day=LATER, nights=2, route="call")
        self.assertEqual(e.exception.code, "no_route")
        self.assertIn("take it over", e.exception.message)
        self.assertEqual(self.api.bodies("/api/booking/calls"), [])

    def test_outside_spain_the_call_says_it_in_english(self):
        with self.assertRaises(API.ToolError):
            self.hold({"phone": {"fact_index": 0}}, venue="Anantara", country="VN", what="hotel", day=LATER, nights=2, route="call")
        self.assertEqual(self.api.bodies("/api/booking/calls"), [])

    def test_request_from_the_hotel_is_the_real_path(self):
        """hotel_test_s135 OnWhatsApp.test_request_from_the_hotel_is_the_real_path: the hotel is READ, as any real booking — never
        the TEST stay (search_stays / hold_booking stay as they are)."""
        self.api.read = {"read_id": "r-h", "venue": "Hotel Test", "country": "ES", "listing": {"name": "Hotel Test Madrid"}, "say": "x",
                         "facts": [], "rungs": [{"rung": "link", "available": True, "fact_index": 1, "value": "SynXis"}]}
        VN._READS.pop(ACCT, None)
        self.addCleanup(VN._READS.pop, ACCT, None)
        run(VN.hold_venue(self.ctx(), {"name": "Hotel Test", "city": "Madrid", "country": "ES", "what": "hotel", "party": 2,
                                       "day": LATER, "nights": 2}))
        self.assertEqual(len(self.api.bodies("/api/booking/venues/read")), 1)
        self.assertEqual(self.api.bodies("/api/booking/links")[0]["read_id"], "r-h")
        self.assertNotIn(ACCT, API._HELD)                                                            # no TEST stay held

    def test_an_email_only_hotel_gets_the_email_route(self):
        """hotel_test_s135 EmailOnlyVenue.test_an_email_only_hotel_gets_the_email_route, on the brain's path."""
        out = self.hold({"email": {"fact_index": 1, "value": "res@artiem.es"}}, venue="ARTIEM Madrid", what="hotel", day=LATER, nights=2)
        body = self.api.bodies("/api/booking/emails")[0]
        self.assertEqual((body["nights"], body["date"], body["party"]), (2, LATER, 2))
        self.assertEqual(out["route"], "email")
        self.assertEqual(out["say"], GW.room_email_sentence("ARTIEM Madrid", 2, LATER, 2))

    def test_a_hotel_is_requested_from_the_hotel_and_says_so(self):
        """travel_s132 Hotels.test_a_hotel_is_requested_from_the_hotel_and_says_so: a request, said as one — never booked."""
        out = self.hold({"email": {}}, venue="Anantara", country="VN", what="hotel", day=LATER, nights=2)
        self.assertIn("asking for a room for 2 nights", out["what_happens"])
        self.assertIn("It's a request — nothing is booked until they reply.", out["say"])
        self.assertEqual(self.yes()["status"], "requested")

    def test_the_room_email(self):
        """travel_s132 Hotels.test_the_room_email: the brain's email body is the room email's particulars (N nights)."""
        self.hold({"email": {}}, venue="Anantara", country="VN", what="hotel", day=LATER, nights=2)
        b = self.api.bodies("/api/booking/emails")[0]
        p = E.EmailParticulars(on=date.fromisoformat(b["date"]), at=time.fromisoformat(b["time"]), party=b["party"], name=b["name"],
                               guest_email=b["email"], nights=b["nights"])
        m = E.compose("vi", "Anantara", "res@x.com", p, "id1")
        self.assertEqual(m["subject"], f"Room request — 2, {LATER} for 2 nights")
        self.assertIn(f"(check-in {LATER}, check-out {OUT_DAY})", m["text"])

    def test_the_same_stay_held_again_is_the_same_read_back(self):
        hotel = {"link": self.HOTEL["link"]}
        self.hold(hotel, venue="Hotel Test Madrid", what="hotel", day=LATER, nights=2)
        VN._HELD[ACCT]["at"] -= timedelta(minutes=1)
        with mock.patch.object(VN, "_read", reader(hotel, "Hotel Test Madrid")):
            again = run(VN.hold_venue(self.ctx(), {"name": "Hotel Test Madrid", "city": "Madrid", "country": "ES", "what": "hotel",
                                                   "party": 2, "day": LATER, "nights": 2}))
        self.assertIn("same_read_back", again)
        self.assertEqual(len(self.api.bodies("/api/booking/links")), 1)


class G8OnWhatsApp(ScriptedBrain):
    """The real brain on WhatsApp (GW.turn → wa_agent → sasha.turn_with_quiver) with a scripted model: a hotel stay goes to the
    hotel's own engine with the stay, read back first, sent on the yes — the old flow's OnWhatsApp test, on the one brain."""

    def setUp(self):
        from tests.test_s254_one_decider import live_access   # Sasha 254 · the executors behind the booking rules: a person who may reach real venues
        live_access(self)
        super().setUp()
        self.link()
        TG.run(GW.STORE.put_state(GW.wa_key(TG.GUEST), {"history": [], "pending": None, "last_inbound_at": TG.NOW, "link_tries": []}))
        VN._HELD.pop(TG.ACCOUNT, None)
        VN._READS.pop(TG.ACCOUNT, None)
        self.links = []
        inner = GW.api

        async def fake(account, method, path, body=None, timeout=90.0):
            if path == "/api/booking/venues/read":
                return 200, {"read_id": "r-h", "venue": "Hotel Test", "country": "ES", "listing": {"name": "Hotel Test Madrid"}, "say": "x",
                             # Sasha 254 · its engine only: with its own email too, the booking rules ask by email first (R1)
                             "facts": [], "rungs": [{"rung": "link", "available": True, "fact_index": 1, "value": "SynXis"}]}
            if path == "/api/booking/links":
                self.links.append(body)
                return 200, {"link_id": "l-h", "platform": "SynXis", "slot_filled": False,
                             "url": "https://be.synxis.com/?hotel=1&arrive=2026-10-20&depart=2026-10-22&adult=2&rooms=1",
                             "read_back": {"lines": ["Hotel Test books rooms through its own booking engine (SynXis)."], "sha256": "h" * 64}}
            return await inner(account, method, path, body, timeout)
        fake.calls = inner.calls
        GW.api = fake
        self.addCleanup(VN._HELD.pop, TG.ACCOUNT, None)
        self.addCleanup(VN._READS.pop, TG.ACCOUNT, None)

    def test_a_stay_on_whatsapp_goes_to_the_hotels_own_engine_read_back_first(self):
        hold = {"name": "Hotel Test", "city": "Madrid", "country": "ES", "what": "hotel", "party": 2, "day": "2026-10-20", "nights": 2,
                "idempotency_key": "h1"}
        self.brain([[Block(type="tool_use", id="t1", name="hold_venue", input=hold)],
                    [Block(type="text", text="I'll send Hotel Test Madrid's own booking page to your phone, with your stay. Shall I?")]])
        self.say("Book the Hotel Test in Madrid from 20 to 22 October for 2, with the hotel itself")
        self.assertEqual(self.links[0]["nights"], 2)                                         # the stay in the engine's link
        self.assertEqual((self.links[0]["date"], self.links[0]["time"]), ("2026-10-20", "15:00"))
        got = json.loads(json.dumps(VN._HELD[TG.ACCOUNT]["out"], default=str))
        self.assertEqual((got["status"], got["route"]), ("awaiting_yes", "page"))           # read back; nothing sent yet
        self.assertIn("One tap: Hotel Test Madrid's own booking engine (SynXis).", VN._HELD[TG.ACCOUNT]["hotel_text"])
        self.assertNotIn("/api/booking/links/l-h/opened", [c[2] for c in GW.api.calls])


# ── G14 · a loyalty number from the Keep; "luxury" €€€ first ─────────────────────────────────────────────────────────────────

ITEM = {"id": "v-1", "kind": "identifier", "provider": "club.kanoe.ai", "label": "Kanoe Test Club number"}


class G14Loyalty(Base):
    def setUp(self):   # Sasha 256 · Kanoe's test venue is held by a TEST person only (agapi/test_venues)
        super().setUp()
        from agapi import test_venues as TV
        p = mock.patch.object(TV, "mode_of", mock.AsyncMock(return_value="test"))
        p.start()
        self.addCleanup(p.stop)

    def test_a_matching_number_goes_into_the_form_by_its_keep_id_never_its_value(self):
        LY.find_for.return_value = ITEM
        self.hold({"form": {}}, venue="Sasha Test Venue", day=LATER, time="21:00", route="form")   # Sasha 254 · "Handle it"
        body = self.api.bodies("/api/booking/forms")[0]
        self.assertEqual(body["loyalty_item_id"], "v-1")                    # the booking API names it in the read-back, opens it at the send
        LY.find_for.assert_awaited_with(ACCT, "Sasha Test Venue", "restaurant")

    def test_no_match_no_number(self):
        self.hold({"form": {}}, day=LATER, time="21:00", route="form")
        self.assertNotIn("loyalty_item_id", self.api.bodies("/api/booking/forms")[0])

    def test_the_prepared_page_names_it_masks_it_and_puts_the_value_only_on_their_phone(self):
        LY.find_for.return_value = ITEM
        opened = []

        class Secret:
            def get(self, k):
                return "KTC-778899" if k == "value" else None

        @contextlib.asynccontextmanager
        async def use(account, item_id, *, approval, approved_lines, action_kind, action_ref):
            opened.append((item_id, action_kind, approval["read_back_sha256"], list(approved_lines)))
            yield Secret()
        eng = {"kind": "own_engine", "url": "https://sashatest.es/reservar", "from": "engine"}
        with mock.patch.object(VN, "engine_channel", mock.AsyncMock(return_value=eng)), mock.patch.object(VC, "use", use), \
                mock.patch("agapi.venue_truth.prepare", mock.AsyncMock(return_value=None)):
            out = self.hold({"own_page": {"value": "https://sashatest.es/reservar"}}, venue="Sasha Test Venue", day=LATER, time="21:00",
                            route="page")   # Sasha 254 · "Prefilled form" — the answer to the rules' one question
        said = json.dumps(out, ensure_ascii=False)
        self.assertNotIn("KTC-778899", said)                                                  # never in what she's given / says
        self.assertIn(LY.TOKEN, said)                                                         # the mask in the fields
        self.assertIn("I'll use your saved Kanoe Test Club number from your vault.", opened[0][3])   # named in the read-back
        self.assertEqual(opened[0][:2], ("v-1", "loyalty_number"))                            # opened once, logged as its use
        self.assertIn("Kanoe Test Club: KTC-778899", self.told[-1])                           # the value: only on THEIR phone

    def test_a_number_that_cannot_be_opened_is_left_out_and_said(self):
        LY.find_for.return_value = ITEM

        @contextlib.asynccontextmanager
        async def refused(*a, **k):
            raise VC.UseRefused("vault_item_unavailable", "gone")
            yield
        eng = {"kind": "own_engine", "url": "https://sashatest.es/reservar", "from": "engine"}
        with mock.patch.object(VN, "engine_channel", mock.AsyncMock(return_value=eng)), mock.patch.object(VC, "use", refused), \
                mock.patch("agapi.venue_truth.prepare", mock.AsyncMock(return_value=None)):
            self.hold({"own_page": {}}, venue="Sasha Test Venue", day=LATER, time="21:00", route="page")
        self.assertIn("Kanoe Test Club: (not added — it's in your Keep)", self.told[-1])


CANDS = [{"place_id": f"p{i}", "name": n, "rating": 4.5, "price_level": lvl}
         for i, (n, lvl) in enumerate((("Casa Lucio", 3), ("Botavara", 2), ("Cheap Eats", 1), ("Fourth Place", 4)))]


class G14Luxury(unittest.TestCase):
    """guest_whatsapp_s75 test_sasha104_luxury_puts_three_euro_signs_first, on the brain's venue search."""

    def setUp(self):
        from tests.test_s254_one_decider import live_access   # Sasha 254 · the executors behind the booking rules: a person who may reach real venues
        live_access(self)
        async def api(account, method, path, body=None, timeout=90.0):
            return 200, {"candidates": CANDS, "ranking": {"default": "rated", "orders": {"rated": ["p1", "p0", "p2", "p3"]}}, "show": 3}
        for p in (mock.patch.object(GW, "api", api), mock.patch.object(VN, "photos_for", mock.AsyncMock())):
            p.start()
            self.addCleanup(p.stop)

    def search(self, what, surface="s2"):
        ctx = API.Ctx(account=ACCT, mode="test", user_said=what, session="s254-lux", surface=surface)
        return run(API._search_venues(ctx, {"what": what, "where": "Madrid"}))

    def test_luxury_puts_three_euro_signs_and_up_first(self):
        r = self.search("Indian food, luxury")
        self.assertEqual([v["name"] for v in r["venues"]], ["Casa Lucio", "Fourth Place", "Botavara"])   # €€€ (rated first), €€€€, rest
        self.assertEqual([c["name"] for c in r["preset"]["cards"]], ["Casa Lucio", "Fourth Place", "Botavara"])   # the same cards
        self.assertIn("€€€ and up first", r["ribbon"])

    def test_a_plain_search_keeps_the_ranking(self):
        r = self.search("Indian food")
        self.assertEqual([v["name"] for v in r["venues"]], ["Botavara", "Casa Lucio", "Cheap Eats"])
        self.assertNotIn("€€€", r["ribbon"])

    def test_old_s1_keeps_the_ranking(self):
        with mock.patch.dict(os.environ, PARITY_OFF):
            r = self.search("Indian food, luxury", surface="s1")
        self.assertEqual([v["name"] for v in r["venues"]], ["Botavara", "Casa Lucio", "Cheap Eats"])


# ── old S1 (parity off): none of it ─────────────────────────────────────────────────────────────────────────────────────────

class OldS1Untouched(Base):
    surface = "s1"

    def setUp(self):
        from tests.test_s254_one_decider import live_access   # Sasha 254 · the executors behind the booking rules: a person who may reach real venues
        live_access(self)
        super().setUp()
        p = mock.patch.dict(os.environ, PARITY_OFF)
        p.start()
        self.addCleanup(p.stop)

    def test_no_time_is_when_invalid_as_before(self):
        with self.assertRaises(API.ToolError) as e:
            self.hold({"email": {}}, open_slot="quote", day=LATER)
        self.assertEqual((e.exception.code, e.exception.message), ("when_invalid", "day is YYYY-MM-DD and time HH:MM"))

    def test_nights_and_loyalty_are_not_added(self):
        LY.find_for.return_value = ITEM
        self.hold({"email": {}}, day=LATER, time="21:00", nights=2, route="email")
        self.assertNotIn("nights", self.api.bodies("/api/booking/emails")[0])
        self.assertEqual(len(self.api.bodies("/api/booking/draft")), 1)                     # a table, as before
        self.hold({"form": {}}, day=LATER, time="21:00", route="form")
        self.assertNotIn("loyalty_item_id", self.api.bodies("/api/booking/forms")[0])
        LY.find_for.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
