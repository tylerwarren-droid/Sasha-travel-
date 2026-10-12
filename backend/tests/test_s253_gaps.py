"""Sasha 253 · item 4 (part 1) — the WhatsApp old flow's capabilities, built IN THE ONE BRAIN (docs/sasha/S252-whatsapp-capabilities.md
GAPS), each capability test MOVED to the brain's path (the old-flow tests were removed when the old flow was retired, Sasha 253 · item 5):

    G1   a forwarded / pasted venue confirmation filed on its booking   — tool file_confirmation   (written_s118 OnWhatsApp test_3)
    G2   a call's result / a written cancellation pushed to WhatsApp    — VN → GW.watch_for_brain  (guest_whatsapp_s75 Progress)
    G4   a space set on the laptop, "what's next?" on the phone          — GW._space_resume          (web_media_cr30 / opener_cr36 /
                                                                                                       cross_channel_cr20 Campus)
    G9   "do I have time to drive / fly to X between A and B?"           — tool time_between        (travel_s132 Rehearsal2)
    G10  a place added to a trip day, not booked                        — tool add_to_trip
    G13  "save it for later"                                            — tool save_for_later
    G15  the founder's WhatsApp words on the ops console                — booking_signer/demo_ops   (hotel_ladder_s138 EngineCheck)
    G16  the reminders offer on the brain's replies too                 — GW._brain_tail

Offline: a scripted model (app/agent/fakes) through the REAL wa_agent.agent_turn → sasha.turn_with_quiver, or the brain stood in
at wa_agent.agent_turn; no network, no live model, no Twilio, no Places, no database.

    cd backend && python -m unittest tests.test_s253_gaps -v
"""
from __future__ import annotations

import asyncio
import json
import os
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

import app.services.llm as LLM
from agapi import s2_home as HOME, s2_manage as MG, v0 as API, venues as VN
from app.agent import s2 as S2, sasha as AG, voice as V
from app.agent.fakes import Block, client
from booking_signer import call_store as CS, guest_whatsapp as GW, inbound_phone as IP, itinerary_q as IQ, wa_agent as WA
from booking_signer import wa_brain as WB
from tests import test_guest_whatsapp_s75 as TG

run, ACCOUNT, GUEST, NOW = TG.run, TG.ACCOUNT, TG.GUEST, TG.NOW
BRAIN: dict = {}   # Sasha 253 · item 5: no switch any more (SASHA_WA_BRAIN retired) — every account is on the one brain
NEW_TOOLS = ("file_confirmation", "time_between", "add_to_trip", "save_for_later")


async def _nothing(*a, **k):
    return None


class ScriptedBrain(TG.Base):
    """The REAL brain on WhatsApp (GW.turn → wa_agent.agent_turn → sasha.turn_with_quiver, surface "wa") with a scripted model:
    each step's blocks are what the model 'says'; `self.seen` holds every model call (its tools and messages)."""

    def brain(self, steps):
        self.seen = []
        self.patches = [mock.patch.dict(os.environ, BRAIN), mock.patch.object(LLM, "client", client(steps, seen=self.seen)),
                        mock.patch("app.agent.sasha.over_budget", _nothing), mock.patch("agapi.s2_memory.remember", _nothing),
                        mock.patch("agapi.s2_memory.recall", mock.AsyncMock(return_value={}))]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in reversed(getattr(self, "patches", [])):
            p.stop()
        super().tearDown()

    def tool_results(self) -> str:
        """Everything the tools gave back to the model this turn (the tool_result blocks it was sent)."""
        return json.dumps([m for s in self.seen for m in s["messages"]], ensure_ascii=False, default=str)


# ── the four tools: one brain, every surface (S2_TOOLS · the parity list · the capability card · voice) ─────────────────────

class TheToolsAreTheBrains(unittest.TestCase):
    def test_the_web_voice_avatars_turn_has_no_channel(self):   # found by deploy e3334ba5's gate: every voice turn crashed
        import asyncio as _a
        from booking_signer import guest_whatsapp as _GW
        ctx = {"account": "a", "ch": None, "now": _GW.NOW(), "out": _GW.Out()}
        self.assertFalse(_a.run(_GW._forwarded_confirmation(ctx, "Book me a table for two tonight at 9 in Sol")))

    def test_registered_once_everywhere_a_tool_is(self):
        caps = {t for g in HOME.CAPABILITIES for _, t in g["items"]}
        for name in NEW_TOOLS:
            self.assertIn(name, S2.S2_TOOLS, name)                                  # /s2 and WhatsApp (surface "wa" is S2's tools)
            self.assertIn(name, [t["name"] for t in API.MANAGE_TOOLS], name)        # /next under parity (HOME + MANAGE tools)
            self.assertNotIn(name, [t["name"] for t in API.TOOLS], name)            # S1's own list untouched (parity off)
            self.assertIn(name, caps, name)                                         # on the one capability list
            self.assertIn(name, V.SAYS, name)                                       # said, no card (honest results)
            self.assertEqual(AG.RENDER[name], "inline", name)
        gen_path = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "lib", "capabilities.generated.mjs")
        if not os.path.exists(gen_path):   # the Railway image is the backend only
            return
        with open(gen_path, encoding="utf-8") as f:
            gen = f.read()
        self.assertEqual(gen, HOME.frontend_module())                                # regenerated (python -m scripts.capabilities_out)

    def test_the_model_is_given_them_on_whatsapp_and_on_next_with_parity_only(self):
        def tools_for(surface, parity):
            seen = []

            async def go():
                async for _ in AG.turn("00000000-0000-4000-8000-000000000253", "hi", [], f"s253-{surface}-{parity}", surface=surface):
                    pass
            with mock.patch.object(LLM, "client", client([[Block(type="text", text="Hello.")]], seen=seen)), \
                    mock.patch.dict(os.environ, {"SASHA_S1_PARITY": parity}):
                asyncio.run(go())
            return {t["name"] for t in seen[0]["tools"]}
        for surface, parity, want in (("wa", "on", True), ("s2", "off", True), ("s1", "on", True), ("s1", "off", False)):
            got = tools_for(surface, parity)
            for name in NEW_TOOLS:
                self.assertEqual(name in got, want, (surface, parity, name))


# ── G1 · a forwarded confirmation, filed on its booking — on the brain ──────────────────────────────────────────────────────

class G1ForwardedConfirmation(ScriptedBrain):
    """written_s118 OnWhatsApp.test_3_a_forwarded_confirmation_on_whatsapp_is_filed_and_answered, on the one brain."""

    def setUp(self):
        super().setUp()
        from tests import test_written_s118 as W
        self.link()
        run(GW.STORE.put_state(GW.wa_key(GUEST), {"history": [], "pending": None, "last_inbound_at": NOW, "link_tries": []}))
        self.ip = IP.STORE
        calls = CS.MemoryCallStore()
        calls.trip_items = {"t-hana": {"id": "t-hana", "status": "requested"}}
        IP.STORE = IP.MemoryInboundStore(calls)
        IP.STORE.candidates = [{**W.HANAKURA, "account_id": ACCOUNT}]

    def tearDown(self):
        IP.STORE = self.ip
        super().tearDown()

    TEXT = "Reenviado: Hanakura — Su reserva está confirmada para el sábado 3 de octubre a las 21:00, 2 personas. ¡Le esperamos!"
    LINE = "✅ Confirmed in writing: Hanakura, Saturday 3 October. I've filed their confirmation on it (forwarded by you)."

    def test_3_a_forwarded_confirmation_on_whatsapp_is_filed_and_answered(self):
        self.brain([[Block(type="tool_use", id="t1", name="file_confirmation", input={"text": "Hanakura confirmed"})],   # a model's
                    [Block(type="text", text=self.LINE)]])                                                       # paraphrase: unused
        self.say(self.TEXT)
        self.assertIn(self.LINE, self.tool_results())                                  # the old flow's own line, from the tool
        self.assertEqual(self.bodies()[-1], self.LINE)
        self.assertEqual(IP.STORE.calls.trip_items["t-hana"]["status"], "confirmed")    # filed on THE booking, confirmed in writing
        row = next(iter(IP.STORE.rows.values()))
        self.assertEqual((row["channel"], row["trip_item_id"], row["reading"]["forwarded_by"]), ("whatsapp", "t-hana", "guest"))
        self.assertTrue(next(iter(IP.STORE.rows)).startswith("wa-fwd-"))              # the same id as the old flow's: filed once
        self.assertEqual(GW.api.calls, [])                                             # no search, nothing booked

    def test_not_a_confirmation_files_nothing(self):
        r = run(API.call(API.Ctx(account=ACCOUNT, user_said="what's on this weekend in Madrid?", surface="s2"), "file_confirmation", {}))
        self.assertFalse(r["result"]["filed"])
        self.assertEqual(IP.STORE.rows, {})


# ── G2 · the result pushed to WhatsApp after the turn ───────────────────────────────────────────────────────────────────────

class G2ResultsPushed(TG.Base):
    """guest_whatsapp_s75 Progress.test_one_message_per_state_never_two (+ cancel-by-email's later push), started by the brain's
    own tools (book_venue's call, cancel_venue's written cancellation) — whatever screen the booking was made on."""

    def setUp(self):
        super().setUp()
        self.coros = []
        GW._spawn = lambda coro: self.coros.append(coro)                # captured, then run here
        self.ch = self.link()
        run(GW.STORE.put_state(GW.wa_key(GUEST), {"history": [], "pending": None, "last_inbound_at": NOW, "link_tries": []}))

    def tearDown(self):
        for c in self.coros:
            c.close()
        VN._CANCEL.pop(ACCOUNT, None)
        super().tearDown()

    def book_by_call(self):
        held = {"id": "call-1", "sha": "a" * 64, "when": "2026-10-03T21:00", "summary": "Saturday 3 October at 21:00, 2 people"}
        return run(VN._book_inner(API.Ctx(account=ACCOUNT, surface="s2"), held, {"how": "voice", "said": "yes"}, "Botavara", "call"))

    def test_one_message_per_state_never_two(self):
        out = self.book_by_call()
        self.assertEqual(out["status"], "placed")
        self.assertEqual([c.__name__ for c in self.coros], ["watch_call"])            # the old flow's own watcher, started
        seq = iter([(200, {"status": "placed"}), (200, {"status": "placed"}),
                    (200, {"status": "answered", "outcome": "yes", "say": "Booked: Botavara confirmed it.", "venue_words": "Sí, perfecto."})])

        async def fake(account, method, path, body=None, timeout=90.0):
            self.assertEqual(path, "/api/booking/calls/call-1")
            return next(seq)
        with mock.patch.object(GW, "WATCH_CALL", (0, 5)), mock.patch.object(GW, "api", fake):
            run(self.coros.pop())
        self.assertEqual(self.bodies()[:2], ["✅ Booked: Botavara, Saturday 3 October at 21:00, 2 people.", "Their words: “Sí, perfecto.”"])
        self.assertEqual(len([b for b in self.bodies() if b.startswith("✅")]), 1)

    def test_a_scheduled_call_is_pushed_from_where_it_is_recorded_not_watched(self):
        GW.api.place = {"status": "scheduled", "scheduled_for": "2026-10-02T19:40:00"}
        self.book_by_call()
        self.assertEqual(self.coros, [])                                               # push_confirmation_result tells that one

    def test_a_written_cancellation_is_pushed_on_their_words(self):
        VN._CANCEL[ACCOUNT] = {"id": "t-1", "sha": "e" * 64, "at": datetime.now(timezone.utc) - timedelta(minutes=1), "venue": "Botavara Chamberí"}
        r = run(VN.cancel_venue(API.Ctx(account=ACCOUNT, surface="s2"), {"approval": {"said": "yes, cancel it"}}))
        self.assertEqual(r["status"], "requested")                                     # asked, never "cancelled" yet
        self.assertEqual([c.__name__ for c in self.coros], ["watch_cancel"])
        GW.api.reservations = [{**GW.api.reservations[0], "status": "cancelled", "venue_words": "Cancelada, gracias."}]
        with mock.patch.object(GW, "WATCH_CANCEL", (0, 3)):
            run(self.coros.pop())
        self.assertEqual(self.bodies(), ["Botavara Chamberí has cancelled your booking.", "Their words: “Cancelada, gracias.”"])

    def test_no_whatsapp_linked_nothing_is_watched(self):
        run(GW.STORE.unlink(ACCOUNT)) if hasattr(GW.STORE, "unlink") else GW.STORE.channels.clear()
        self.assertTrue(run(GW.watch_for_brain(ACCOUNT, call_id="call-1", venue="Botavara")).startswith("not watched"))
        self.assertEqual(self.coros, [])


# ── G4 · a space set on the laptop, continued on the phone ──────────────────────────────────────────────────────────────────

class BrainStandIn:
    """The brain stood in at wa_agent.agent_turn: anything it is handed is recorded (a product's answer must never reach it)."""

    def setUp(self):
        super().setUp()
        self.brain_saw = []

        async def brain(ch, body, payload, st, out, now, button_text="", voice_in=False):
            self.brain_saw.append(body or payload)
            out.text(f"agent: {body or payload}")
            return "x"
        self.g4 = [mock.patch.object(WA, "agent_turn", brain), mock.patch.dict(os.environ, BRAIN)]
        for p in self.g4:
            p.start()

    def tearDown(self):
        for p in reversed(self.g4):
            p.stop()
        super().tearDown()


from tests import test_campusme_cr1 as TC, test_relocation_m3_cr1 as TR, test_web_media_cr30 as WM   # noqa: E402
from products import web as PWEB   # noqa: E402


def _only_its_own(cls):
    """A fixture's own tests are not run again here: only the brain-path tests this class writes."""
    for n in dir(cls):
        if n.startswith("test") and n not in cls.__dict__:
            setattr(cls, n, None)
    return cls


@_only_its_own
class G4RelocationOnTheBrain(BrainStandIn, TR.Flow):
    """web_media_cr30 WebPhoto (and opener_cr36 Opener).test_web_and_whatsapp_hold_the_same_file, on the one brain."""

    def test_web_and_whatsapp_hold_the_same_file(self):
        for t in ("relocation", "first", "me", "myself"):
            WM.web(self, t)
        WM.web(self, media=[{"bytes": WM.JPEG, "content_type": "image/jpeg"}])
        WM.web(self, payload="rx:doc:yes")
        self.say("what's next for my application?")                       # the phone: the passport is not asked again
        self.assertNotIn("passport number", GW.SENDER.contents[-1][0].lower() if GW.SENDER.contents else "")
        self.assertIn("Back to your EX-01.", self.bodies()[-1])
        self.assertEqual(self.brain_saw, [])                                # the product answered it, not the brain

    def test_opened_on_the_tab_then_whats_next_on_the_phone(self):
        run(PWEB.web_turn(ACCOUNT, "", mode="relocation", now=self.now, signed_in=True))   # CR 36 · the tab's opener
        WM.web(self, "first")
        self.say("what's next for my application?")
        self.assertIn("Back to your EX-01.", self.bodies()[-1])
        self.assertEqual(self.brain_saw, [])

    def test_outside_a_space_the_brain_answers(self):
        self.say("what's next for my application?")
        self.assertEqual(self.brain_saw, ["what's next for my application?"])


@_only_its_own
class G4CampusOnTheBrain(BrainStandIn, TC.Fixtures):
    """cross_channel_cr20 Campus.test_pick_on_the_laptop_whats_next_on_the_phone, on the one brain."""

    def setUp(self):
        super().setUp()
        self.link()

    def test_pick_on_the_laptop_whats_next_on_the_phone(self):
        WM.web(self, "campus")
        r = WM.web(self, "campus visits at Yale on October 14 for my son")
        self.assertIn("Campus Tour", r["response"])
        nxt = WM.web(self, "1")["response"]
        self.say("what's next for the Yale visit?")
        self.assertTrue(self.bodies()[-1].startswith("Back to your campus visits."))
        self.assertTrue(self.bodies()[-1].endswith(nxt.split("\n\n")[-1]))
        self.assertEqual(run(PWEB.current_space(ACCOUNT)), "campus")
        self.assertEqual(self.brain_saw, [])


# ── G9 · "do I have time to …?" — a question, answered on the brain ─────────────────────────────────────────────────────────

class G9TimeQuestion(ScriptedBrain):
    """travel_s132 Rehearsal2.test_a_time_question_is_a_question, on the one brain."""

    ASKED = "do I have time to fly from Madrid to Lisbon between 9 and 14 on 12 November?"

    def test_a_time_question_is_a_question(self):
        self.link()
        called = []

        async def answer(account, text, now):
            called.append(text)
            return ["answered"]
        self.brain([[Block(type="tool_use", id="t1", name="time_between", input={"question": "time to fly MAD-LIS?"})],
                    [Block(type="text", text="answered")]])
        with mock.patch.object(IQ, "answer", answer):
            self.say(self.ASKED)
        self.assertEqual(called, [self.ASKED])                                   # their own words, to the old flow's own answer
        self.assertIn('"answered"', self.tool_results())
        self.assertTrue(self.bodies()[-1].startswith("answered"), self.bodies())
        self.assertNotIn("/api/booking/venues/find", self.api_paths())          # never taken for a search

    def test_the_models_words_when_theirs_dont_carry_the_question(self):
        got = []

        async def answer(account, text, now):
            got.append(text)
            return ["ok"]
        with mock.patch.object(IQ, "answer", answer):
            run(API.call(API.Ctx(account=ACCOUNT, user_said="and Toledo?", surface="s2"), "time_between",
                         {"question": "to drive to Toledo between 13:00 and 18:00 on the 5th"}))
        self.assertEqual(got, ["do I have time to drive to Toledo between 13:00 and 18:00 on the 5th"])


# ── G10 · a found place on a trip day, not booked · G13 · saved for later ───────────────────────────────────────────────────

class G10AddToTrip(unittest.TestCase):
    TRIP = {"trip_id": "trip-1", "title": "Vietnam, Nov", "day": 3, "date": "2026-11-14", "city": "Hoi An"}

    def call(self, args, said="add Morning Glory to our Hoi An day"):
        return run(API.call(API.Ctx(account=ACCOUNT, user_said=said, surface="s2"), "add_to_trip", args))

    def setUp(self):
        asyncio.set_event_loop(asyncio.new_event_loop())
        self.added = []

        async def add_place(account, trip_id, day, activity):
            self.added.append((trip_id, day, activity))
            return True
        self.p = [mock.patch("booking_signer.plan_store.add_place", add_place),
                  mock.patch.object(WB, "context", mock.AsyncMock(return_value={"where": "Hoi An", "country": "VN", "trip": self.TRIP}))]
        for p in self.p:
            p.start()

    def tearDown(self):
        for p in self.p:
            p.stop()

    def test_added_to_its_day_and_not_booked(self):
        r = self.call({"name": "Morning Glory", "place_id": "ChIJmg", "what": "restaurant", "day": "2026-11-14"})
        self.assertTrue(r["ok"], r)
        self.assertTrue(r["result"]["added"])
        (trip_id, day, act), = self.added
        self.assertEqual((trip_id, day, act["place_id"], act["added"]), ("trip-1", 3, "ChIJmg", True))
        self.assertIn("not booked yet", act["blurb"])
        self.assertTrue(r["result"]["say"].startswith("Added Morning Glory to Day 3 · "))
        self.assertIn("Nothing is booked yet", r["result"]["say"])
        self.assertIn("hold_venue", r["result"]["how"])                          # booking it later is the venue's own route

    def test_a_day_not_on_the_trip_and_no_trip(self):
        r = self.call({"name": "Morning Glory", "day": "2026-12-01"})
        self.assertEqual(r["error"]["code"], "day_not_on_trip")
        with mock.patch.object(WB, "context", mock.AsyncMock(return_value={"where": "Madrid", "country": "ES", "home": True})):
            self.assertEqual(self.call({"name": "Morning Glory"})["error"]["code"], "no_trip")
        self.assertEqual(self.added, [])


class G13SaveForLater(unittest.TestCase):
    def setUp(self):
        asyncio.set_event_loop(asyncio.new_event_loop())

    def test_saved_unbooked_in_its_tab_with_the_old_flows_words(self):
        saved = []

        async def save_item(account, name, at, city):
            saved.append((name, at, city))
            return "tid-1"
        with mock.patch.object(WB, "save_item", save_item), mock.patch.object(WB, "tab_of", mock.AsyncMock(return_value="Vietnam, Nov")):
            r = run(API.call(API.Ctx(account=ACCOUNT, user_said="save it for later", surface="s2"), "save_for_later",
                             {"name": "Morning Glory", "when": "2026-11-14", "city": "Hoi An"}))
            parked = run(WB.park({"account": ACCOUNT, "st": {"pending": {}}}, {"venue": "Morning Glory", "find": {"where": "Hoi An"}}))
        self.assertEqual(r["result"]["say"], "Saved, not booked: Morning Glory — it's in your Vietnam, Nov tab and in Requests.")
        self.assertEqual(parked, r["result"]["say"])                              # one place: the old flow's park says the same
        self.assertEqual(saved[0], ("Morning Glory (saved)", "2026-11-14", "Hoi An"))

    def test_not_saved_is_said(self):
        with mock.patch.object(WB, "save_item", mock.AsyncMock(return_value=None)):
            r = run(API.call(API.Ctx(account=ACCOUNT, surface="s2"), "save_for_later", {"name": "Morning Glory"}))
        self.assertEqual(r["result"], {"saved": False, "say": "I couldn't save it just now — nothing was booked.", "how": "Say this line as it is."})


# ── G16 · the reminders offer, once, on the brain's replies too ─────────────────────────────────────────────────────────────

class G16RemindersOffer(BrainStandIn, TG.Base):
    def setUp(self):
        super().setUp()
        from booking_signer import proactive as PR
        self.pr = PR.STORE
        PR.STORE = PR.MemoryProactiveStore()
        self.link()                                                            # a v2-consent guest

    def tearDown(self):
        from booking_signer import proactive as PR
        PR.STORE = self.pr
        super().tearDown()

    def test_offered_once_after_the_brains_answer(self):
        self.say("find me sushi in Chamberí")
        self.assertEqual(self.bodies()[-2:], ["agent: find me sushi in Chamberí", GW.REMINDERS_OFFER])
        self.say("and for Saturday?")
        self.assertEqual(self.bodies()[-1], "agent: and for Saturday?")       # never again
        self.assertEqual(self.bodies().count(GW.REMINDERS_OFFER), 1)


# ── G15 · the founder's words on the ops console ────────────────────────────────────────────────────────────────────────────

class G15OpsConsole(TG.Base):
    """hotel_ladder_s138 EngineCheck (the founder's answers recorded) and the other words, through the founder-only ops routes."""

    HOTELS = [{"n": 1, "name": "UMusic", "engine": "Neobookings"}, {"n": 2, "name": "The Hat", "engine": "Mews"},
              {"n": 3, "name": "The Signature", "engine": "D-Edge"}]

    def setUp(self):
        super().setUp()
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from booking_signer import demo_ops as DO
        app = FastAPI()
        app.include_router(DO.router, prefix="/api/booking")
        self.who = ACCOUNT
        self.p = [mock.patch("booking_signer.account.account_for", lambda r: self.who),
                  mock.patch("app.services.accounts.is_founder", lambda a: a == ACCOUNT)]
        for p in self.p:
            p.start()
        self.c = TestClient(app)
        self.link()

    def tearDown(self):
        for p in reversed(self.p):
            p.stop()
        super().tearDown()

    def test_engine_check_answers_are_recorded_in_order_or_by_number(self):
        run(GW.STORE.put_state(GW.wa_key(GUEST), {"history": [], "pending": {"kind": "engine_check", "at": NOW.isoformat(), "hotels": self.HOTELS},
                                                  "last_inbound_at": NOW, "link_tries": []}))
        self.assertEqual([h["answer"] for h in self.c.get("/api/booking/ops/demo/engine-check").json()["hotels"]], [None] * 3)
        self.assertEqual(self.c.post("/api/booking/ops/demo/engine-check", json={"n": 1, "answer": "not filled"}).json()["say"],
                         "Noted — UMusic (Neobookings): not filled. 2 to go.")
        self.c.post("/api/booking/ops/demo/engine-check", json={"n": 3, "answer": "filled"})
        r = self.c.post("/api/booking/ops/demo/engine-check", json={"n": 2, "answer": "not filled"}).json()
        self.assertEqual((r["say"], r["done"]), ("Noted — The Hat (Mews): not filled. That's all 3 — thank you.", True))
        p = run(GW.STORE.get_state(GW.wa_key(GUEST)))["pending"]
        self.assertEqual(p["kind"], "engine_check_done")
        self.assertEqual({k: v["answer"] for k, v in p["answers"].items()}, {"1": "not filled", "3": "filled", "2": "not filled"})
        self.assertEqual(self.c.post("/api/booking/ops/demo/engine-check", json={"n": 2, "answer": "filled"}).status_code, 409)

    def test_captcha_test_space_and_deposit(self):
        from booking_signer import captcha_test as CT, test_deposit as TD
        with mock.patch.object(CT, "send", mock.AsyncMock(return_value="Sent — tap it on your phone.")):
            self.assertEqual(self.c.post("/api/booking/ops/demo/captcha-test", json={}).json()["say"], "Sent — tap it on your phone.")
        from products import space as SPC
        with mock.patch.object(SPC, "current", mock.AsyncMock(return_value={"space": "campus"})):
            self.assertEqual(self.c.get("/api/booking/ops/demo/space").json()["say"], "You're in CampusMe — say “sasha” for travel")
        run(GW.STORE.put_state(GW.wa_key(GUEST), {"history": [], "pending": None, "last_inbound_at": NOW, "link_tries": []}))
        with mock.patch.object(TD, "link", mock.AsyncMock(return_value={"id": "plink_1", "url": "https://buy.stripe.test/x"})):
            r = self.c.post("/api/booking/ops/demo/test-deposit", json={}).json()
        self.assertIn("https://buy.stripe.test/x", r["say"])
        self.assertIn("TEST payment", self.bodies()[-1])                         # on his WhatsApp, as the word sent it
        self.assertIn("watch_deposit", self.spawned)                             # and watched, as the word watched it

    def test_founder_only(self):
        self.who = "33333333-3333-4333-8333-333333333333"
        for path in ("/api/booking/ops/demo/captcha-test", "/api/booking/ops/demo/test-deposit", "/api/booking/ops/demo/engine-check"):
            self.assertEqual(self.c.post(path, json={"n": 1, "answer": "filled"}).status_code, 403, path)
        self.assertEqual(self.c.get("/api/booking/ops/demo/space").status_code, 403)


if __name__ == "__main__":
    unittest.main()


class BookIsNeverParked(unittest.TestCase):
    """Sasha 253 · found by EU's scoreboard rerun: "the first one please — book it, but don't send anything to them" was parked
    (save_for_later) instead of booked — "book it" is hold_venue (it sends nothing without their yes)."""
    def ctx(self, said):
        from agapi import v0 as API
        return API.Ctx(account="00000000-0000-4000-8000-0000000002b3", mode="test", user_said=said, session="s253", surface="s2")

    def test_book_it_is_not_parked(self):
        import asyncio as _a
        from agapi import s2_manage as MG
        from agapi.v0 import ToolError
        for said in ("EU251 check: the first one please — book it, but don't send anything to them.", "Book La Mi Venta for Thursday"):
            for fn in (MG.save_for_later, MG.add_to_trip):
                with self.assertRaises(ToolError) as e:
                    _a.run(fn(self.ctx(said), {"name": "La Mi Venta"}))
                self.assertEqual(e.exception.code, "book_not_park")

    def test_their_own_words_to_park_still_park(self):
        from agapi import s2_manage as MG
        for said in ("Save it for later", "add it to Saturday, don't book it yet", "I'm not ready to book yet, keep it"):
            self.assertFalse(MG._asked_to_book(self.ctx(said)), said)
