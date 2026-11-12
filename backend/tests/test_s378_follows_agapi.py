"""Sasha 378 · CR 188's Sasha half — Sasha FOLLOWS AgAPI's ONE booking decision; its own decider is gone. NO PATCHES.

ROOT TEST: ONE source — venue.profile's `decision` (AgAPI's handoff.decide over its own read), then venue.prepare_booking for this
person. Every reader of a booking route reads that decision: hold_venue (venues.one_decision), read_booking_route, the web card's plan
(ladder_routes._plan_for), the place card and its sheet (venue_truth.channel), WhatsApp (guest_whatsapp.one_path → hold_venue). Any
Sasha-side channel choice is a PATCH, and these ratchets fail on one:
  · no BR.decide( / booking_rules.decide( / decide_for( anywhere in Sasha (booking_rules is vendored for its words and its vectors);
  · no "one_tap" route outside words; no ladder, no ONE question of Sasha's own (ASK_FILL / CHOICES / chosen_route), no "prefer";
  · no booking path reads platform_submit, real_venue_sends or a person's beta;
  · the deleted deciders stay deleted (booking_signer/decide.py, rules_for / _execute / read_channel, GW decision_of / ladder_of /
    route_line_of / _send_link / dv_platform, booking_decide's decide_for / ctx_for / channels_of / legacy_*).

    cd backend && python -m unittest tests.test_s378_follows_agapi -v
"""
from __future__ import annotations

import asyncio
import pathlib
import re
import unittest
from unittest import mock

from agapi import booking_decide as BD, venue_truth as VT, venues as VN
from booking_signer import guest_whatsapp as GW
from scripts import agapi_decides as AD

run = asyncio.run
BACKEND = pathlib.Path(__file__).resolve().parents[1]

#: the booking paths: every module that holds, reads back, sends, shows or says how a venue books
BOOKING_PATHS = ("agapi/venues.py", "agapi/venue_truth.py", "agapi/venue_submit.py", "agapi/venue_calls.py", "agapi/booking_decide.py",
                 "agapi/v0.py", "agapi/s2_tools.py", "agapi/itinerary.py", "agapi/test_venues.py", "app/agent/sasha.py", "app/agent/s2.py",
                 "app/agent/voice.py", "booking_signer/guest_whatsapp.py", "booking_signer/wa_agent.py", "booking_signer/ladder_routes.py",
                 "booking_signer/call_routes.py", "booking_signer/calls.py", "booking_signer/handoff.py", "booking_signer/chat_request.py",
                 "booking_signer/voice_turn.py", "booking_signer/proactive.py")


def sources():
    for p in BACKEND.rglob("*.py"):
        rel = p.relative_to(BACKEND).as_posix()
        if rel.startswith(("tests/", "agapi/booking_rules/", "kanoe_contract/", "venv", ".venv")) or "/." in rel:
            continue
        yield rel, p.read_text(encoding="utf-8", errors="ignore")


def code_of(src: str) -> str:
    """The code only: comments and docstrings dropped — a ratchet reads what runs, never the history written beside it."""
    out = re.sub(r'(?s)"""(.*?)"""', '""', src)
    return "\n".join(line.split("  #")[0] if not line.lstrip().startswith("#") else "" for line in out.splitlines())


class TheRatchets(unittest.TestCase):
    def test_no_decider_of_sashas_own(self):
        hits = [rel for rel, src in sources() if re.search(r"\bBR\.decide\(|booking_rules\.decide\(|\bdecide_for\(|\bredecide\(", code_of(src))]
        self.assertEqual(hits, [])

    def test_no_one_tap_route_no_ladder_no_question_of_her_own(self):
        for rel, src in sources():
            code = code_of(src)
            self.assertNotRegex(code, r"[\"']one_tap[\"']", rel)
            if rel != "agapi/measure.py":   # measure.decision_of reads AgAPI's own answer (prepare_booking's decision) for the record
                self.assertNotIn("decision_of(", code, rel)
            for gone in ("ladder_of(", "legacy_ladder(", "legacy_decision(", "route_line_of(", "chosen_route(",
                         "VT.ASK_FILL", "as ASK_FILL", "BD.CHOICES", "BD.CALL_CHOICES", "BD.PREFERENCE", "D.preference("):
                self.assertNotIn(gone, code, f"{rel}: {gone}")
        # the web card's half is pinned by frontend/scripts/follows-agapi-378.test.mjs (npm test) — gate tests never read frontend/

    def test_no_booking_path_reads_a_persons_switch(self):
        for rel in BOOKING_PATHS:
            p = BACKEND / rel
            if not p.exists():
                continue
            code = code_of(p.read_text())
            if rel == "agapi/s2_tools.py":   # send_email's live switch: a person's own email to an address they give — not a booking
                code = code.replace("GA.real_venue_sends(account)", "")
            for w in ("platform_submit", "real_venue_sends", "permitted_beta", "platform_beta", "access_of(", "access_cached("):
                self.assertNotIn(w, code, f"{rel} reads {w}")

    def test_the_deleted_deciders_stay_deleted(self):
        with self.assertRaises(ImportError):
            __import__("booking_signer.decide")
        for mod, names in ((VN, ("rules_for", "_execute", "read_channel", "chosen_route", "REFUSED", "follows", "_routes_of", "_how_words")),
                           (GW, ("decision_of", "ladder_of", "route_line_of", "_send_link", "dv_platform", "OWN_PAGE")),
                           (BD, ("decide_for", "redecide", "ctx_for", "channels_of", "page_of", "access_of", "access_cached", "state_of",
                                 "legacy_decision", "legacy_ladder", "as_v1", "CHOICES", "CALL_CHOICES", "PREFERENCE")),
                           (VT, ("ASK_FILL",))):
            for n in names:
                self.assertFalse(hasattr(mod, n), f"{mod.__name__}.{n}")


class EveryReaderReadsAgapisDecision(unittest.TestCase):
    """The seam: AgAPI's venue.profile WRITES the decision (cached by venue_truth); these READ it — and only it."""

    def test_hold_venue_and_read_booking_route(self):
        src = (BACKEND / "agapi" / "venues.py").read_text()
        hv = src[src.index("async def hold_venue(ctx, a: dict)"):src.index("#: Sasha 377 · CR 188 · the routes AgAPI ACTS on")]
        rbr = src[src.index("async def read_booking_route(ctx, a: dict)"):src.index("from app.agent.voice import READ_BACK_ASK")]
        for block in (hv, rbr):
            self.assertIn("VT.decision(place)", block)
            self.assertNotIn("rungs", code_of(block).replace('"rungs": {}', ""))   # never Sasha's own read of their channels

    def test_the_place_card_says_agapis_decision(self):
        d = AD.decision("email", "Casa Gate")
        ch = VT.channel({"decision": d, "channels": [{"kind": "form", "value": "https://casagate.example/reservas"}]})
        self.assertEqual((ch["route"], ch["channel"], ch["say_text"]), ("message", "email", d["say_text"]))   # never the form it read
        self.assertNotIn("ask", ch)
        self.assertIsNone(VT.channel({"channels": [{"kind": "form", "value": "https://x.example"}]}))         # no decision: none of hers
        self.assertIn("Books: by email", VT.text({"name": "Casa Gate", "channel": ch}))

    def test_the_web_cards_plan_is_agapis_decision(self):
        from booking_signer import ladder_routes as LR
        dec = AD.decision("platform", "Casa Gate")

        async def eng(card, budget_s=30.0, listing=False):
            AD.seed(card, dec)
            return VT.channel({"decision": dec})
        with mock.patch.object(VN, "engine_channel", eng):
            plan = run(LR._plan_for({"name": "Casa Gate", "listing": {"place_id": "ChIJweb378"}}, {"query": {"place_id": "ChIJweb378"}}))
        self.assertEqual(plan, {"route": "platform", "line": dec["say_text"], "channel": "OpenTable", "link": AD.OT, "label": "Book on OpenTable"})
        with mock.patch.object(VN, "engine_channel", mock.AsyncMock(return_value=None)):
            none = run(LR._plan_for({"name": "No Read"}, {"query": {"place_id": "ChIJnone378"}}))
        self.assertEqual((none["route"], none["line"]), (None, None))                                       # nothing of Sasha's own

    def test_whatsapp_books_by_the_one_path(self):
        src = (BACKEND / "booking_signer" / "guest_whatsapp.py").read_text()
        body = src[src.index("async def _prepare_or_ask(ctx: dict, pend: dict)"):src.index("def room_email_sentence(")]
        self.assertIn('API.call(c, "hold_venue", args)', body)
        for gone in ("decision_of", "ladder_of", "_send_link", "one_tap", "prefer"):
            self.assertNotIn(gone, code_of(body), gone)


class AVenueNamedByItsWebsite(unittest.TestCase):
    """Found by the deploy gate (VENUE 1–7, 12 Nov): "Sasha Test Venue" held by its website alone — no card on screen, no listing — had
    no decision (the place asked about was card or listing only) and fell to the floor. ONE place (venues.place_of): the card, else the
    venue by its listing AND the website the booking names — the same place venue.prepare_booking is given."""

    def test_the_gates_test_venue_by_its_website(self):
        from scripts import venue_engine_fake as F
        from booking_signer.form_rung import test_venue_url
        from agapi import v0 as API, venue_submit as VS
        from booking_signer import guest_receipt as GR
        acct = "00000000-0000-4000-8000-000000000378"
        real_vt, real_vs = VT.CALL, VS.CALL

        async def rd(ctx, a):   # the read through the booking API: no listing (a website only)
            return {"read_id": "r-g", "venue": "Sasha Test Venue", "country": "ES", "facts": [], "rungs": {"form": {}}, "open_now": True,
                    "opens_at": None, "say": ""}
        res = {"who": {"name": "Alex Gate", "contact": {"mobile_e164": "+447700900211"}}, "how_many": {"count": 2},
               "when": {"mode": "at", "at": "2099-11-16T21:00"}, "what": {"category": "restaurant"}}
        F.install(submit=True)
        try:
            with mock.patch.object(VN, "_read", rd), mock.patch.object(VN, "_reservation", mock.AsyncMock(return_value=res)), \
                    mock.patch.object(GR, "address_of", mock.AsyncMock(return_value="g@example.test")), \
                    mock.patch("agapi.test_venues.vet", mock.AsyncMock(side_effect=lambda c, a: a)), \
                    mock.patch.object(VS, "target", mock.AsyncMock(return_value="sandbox")), \
                    mock.patch("agapi.s2_memory.put_kind", mock.AsyncMock(return_value=True)), \
                    mock.patch("agapi.s2_memory.kind", mock.AsyncMock(return_value=None)):
                v = {"name": "Sasha Test Venue", "city": "Madrid", "country": "ES", "website": test_venue_url("plain"), "what": "dinner"}
                ctx = API.Ctx(account=acct, mode="test", user_said="Book it", surface="s1")
                r = run(VN.read_booking_route(ctx, dict(v)))
                h = run(VN.hold_venue(ctx, {**v, "day": "2099-11-16", "time": "21:00", "party": 2}))
        finally:
            VT.CALL, VS.CALL = real_vt, real_vs
            VT._CACHE.clear()
            VN._HELD.pop(acct, None)
        self.assertEqual((r["routes"], r["decision"]["route"]), (["send_form"], "send_form"))     # AgAPI's decision, by the website
        self.assertEqual((h["status"], h["route"]), ("awaiting_yes", "agapi"))                    # its read-back, held for the yes

    def test_one_place_for_the_decision_and_the_prepare(self):
        self.assertEqual(VN.place_of({"venue": "X"}, None, {"website": "https://x.example"}), {"name": "X", "website": "https://x.example"})
        self.assertEqual(VN.place_of({"venue": "X", "place_id": "p"}, None, {}), {"name": "X", "place_id": "p"})
        self.assertIsNone(VN.place_of({"venue": "X"}, None, {}))
        self.assertEqual(VN.place_of({}, {"name": "C"}, {"website": "https://x"}), {"name": "C"})


class EachRouteFollowed(unittest.TestCase):
    """one_decision over each of AgAPI's routes: an act → its read-back for the ONE yes; the call → its card; a hand-over (their WhatsApp,
    a closed platform, a step only they may do) → AgAPI's own button; none → the floor. Never a channel of Sasha's choosing."""

    def test_the_act_routes_are_agapis(self):
        self.assertEqual(VN.ACT_ROUTES, ("send_form", "ask_then_send", "message"))
        self.assertEqual(VN.CALL_ROUTES, ("call", "call_at_opening", "call_no_voice"))
        for kind, action in (("send_form", "fill_form_zero_touch"), ("email", "request_email"), ("call", "call"),
                             ("platform_book", "fill_platform_form")):
            d = VN.agapi_d(AD.decision(kind))
            self.assertEqual(d["action"], action, kind)
            self.assertEqual(d["decision_say"], AD.decision(kind)["say_text"])                             # AgAPI's words, as given
            if kind in ("send_form", "email"):   # an act's after-the-yes words: the send's own (the vendored phrase)
                from agapi.booking_rules import booking_rules as BR
                self.assertEqual(d["say_text"], BR.PHRASES["sent"])

    def test_a_hand_over_is_never_an_act(self):
        hits = []

        async def act(*a, **k):
            hits.append("act")
            return {"status": "awaiting_yes"}

        async def follow(ctx, a, rd, res, at, now, card, dec, refused=False):
            return {"status": "followed", "route": dec["route"]}
        ctx = type("C", (), {"account": "00000000-0000-4000-8000-000000000378", "surface": "s2"})()
        rd = {"venue": "Casa Gate"}
        res = {"how_many": {"count": 2}}
        with mock.patch.object(VN, "_via_agapi", act), mock.patch.object(VN, "_call_question", act), mock.patch.object(VN, "follow", follow):
            for kind in ("whatsapp", "platform", "platform_book", "none"):
                out = run(VN.one_decision(ctx, {}, rd, res, "2026-12-01T21:00", None, None, AD.decision(kind)))
                self.assertEqual(out["status"], "followed", kind)
        self.assertEqual(hits, [])


if __name__ == "__main__":
    unittest.main()
