"""Sasha 249 · EU 245 steps 5–7 — "no patches: each change removes a second place where a fact is decided". Offline (no network,
no database, no model).

  T8   ONE STATUS        agapi/s2_status.status_of is the one place a booking's status is decided; get_status (chat), the /s2
                         "Booked" card (the `booked` event only — the regex card is gone), the Trip banner (/api/booking/plan →
                         trip_status, not a client prop) and the WhatsApp line after a payment all carry ITS line. Basket
                         bookings go in the outcomes ledger too (rung api; never the person's details).
  T13  NO FIXED EXAMPLES the model sees keep_list's masks only — no "ES ••••456" in what /s2, WhatsApp or /next (parity on) is given.
                         A source scan holds the few that remain (S1 with SASHA_S1_PARITY=off, byte-identical: Tyler's OK needed).
                         hotel_web uses the one hotel_name(); world_itinerary's hotels keep their address and rating.
  T10  ONE CAPABILITY    s2_home.CAPABILITIES generates SAY, the S1/S2 prompt section, the chips (/s2 and /next, via the generated
       LIST              frontend module) and WhatsApp's HELP / LINKED / ONBOARD under the one brain; every item and chip maps to a
                         live tool.

    cd backend && python -m unittest tests.test_s249_status_keep_caps -v
"""
from __future__ import annotations

import asyncio
import glob
import io
import json
import os
import re
import tokenize
import unittest
from unittest import mock

from agapi import s2_status as ST, v0 as API

ACCT = "00000000-0000-4000-8000-000000000249"
run = asyncio.run
HERE = os.path.dirname(os.path.abspath(__file__))
BACK = os.path.dirname(HERE)
FRONT = os.path.join(os.path.dirname(BACK), "frontend")


def _read(*p: str) -> str:
    with open(os.path.join(*p), encoding="utf-8") as f:
        return f.read()


# ── T8 · one status ──────────────────────────────────────────────────────────────────────────────────────────────────────────

BOOKED_ROW = "✈️ Iberia IB3100 MAD→LIS · 2026-11-02 · booked · ref ABC123 (TEST)"
STAY_ROW = "🏨 Tings Lisbon · 2026-11-02 · NOT booked: sold out (TEST)"


class Decide(unittest.TestCase):
    def test_each_state_and_its_line(self):
        base = {"venues": [], "booked": [], "failed": [], "cancelled": [], "awaiting_payment": 0}
        self.assertEqual(ST.decide(base), {"state": "nothing", "line": "Nothing is booked yet."})
        self.assertEqual(ST.decide(base, held=True)["state"], "held")
        self.assertEqual(ST.decide({**base, "awaiting_payment": 2})["line"], ST.WORDS["awaiting_payment"])
        self.assertEqual(ST.decide({**base, "booked": [BOOKED_ROW]}), {"state": "booked", "line": f"Booked: {BOOKED_ROW}."})
        self.assertEqual(ST.decide({**base, "booked": [BOOKED_ROW], "failed": [STAY_ROW]})["state"], "partly_booked")
        self.assertEqual(ST.decide({**base, "failed": [STAY_ROW]}), {"state": "failed", "line": f"Not booked: {STAY_ROW}."})
        self.assertEqual(ST.decide(base, ledger_open=1)["state"], "requested")

    def test_awaiting_payment_is_never_booked(self):   # the "✓ Paid · not booked yet" class: one state, one line
        d = ST.decide({"venues": [], "booked": [BOOKED_ROW], "failed": [], "awaiting_payment": 1})
        self.assertEqual(d["state"], "awaiting_payment")
        self.assertNotIn("Booked", d["line"])

    def test_a_basket_booking_also_in_the_reservations_is_said_once(self):
        d = ST.decide({"booked": [BOOKED_ROW], "failed": [], "awaiting_payment": 0,
                       "venues": [{"venue": "Iberia IB3100", "status": "confirmed", "reference": "ABC123"},
                                  {"venue": "Casa Gate", "date": "2026-11-02", "time": "21:00", "status": "confirmed"}]})
        self.assertEqual(d["line"], f"Booked: {BOOKED_ROW}; Casa Gate — 2026-11-02 21:00.")


FIXED = {"venues": [], "anything_booked": True, "booked": [BOOKED_ROW], "failed": [], "cancelled": [], "awaiting_payment": 0,
         "state": "booked", "line": f"Booked: {BOOKED_ROW}.", "refs": ["ABC123"], "ledger_open": 0}


class EverySurfaceReadsIt(unittest.TestCase):
    """T8 · after a booking: the chat's get_status, the /s2 card, the Trip banner and the WhatsApp line all carry status_of's line."""

    def setUp(self):
        p = mock.patch.object(ST, "status_of", mock.AsyncMock(return_value=dict(FIXED)))
        self.status_of = p.start()
        self.addCleanup(p.stop)

    def test_all_four_say_the_same(self):
        from app.agent import sasha as AG
        from booking_signer import ladder_routes as LR, live_events as LE, paid_watch as PW
        chat = run(API.get_status(API.Ctx(account=ACCT), {}))["line"]
        card = run(AG.booked_event(ACCT))["status"]["line"]
        banner = run(LR.trip_status(ACCT, "t-1"))["line"]
        wa = run(PW.wa_line(ACCT, {"status": "booked", "say": "✅ Booked: something composed elsewhere"}))
        page = run(LE.status_now(ACCT))["line"]
        self.assertEqual({chat, card, banner, wa, page}, {FIXED["line"]})

    def test_the_whatsapp_line_keeps_what_only_the_payment_knows(self):
        from booking_signer import paid_watch as PW
        wa = run(PW.wa_line(ACCT, {"status": "booked", "say": "✅ Booked: x (the offer priced had expired; booked the same route "
                                                             "and day at EUR 120, TEST). y", "loyalty": ["I've added your Iberia Plus to this booking."]}))
        self.assertEqual(wa.split("\n"), [FIXED["line"], "(the offer priced had expired; booked the same route and day at EUR 120, TEST)",
                                          "I've added your Iberia Plus to this booking."])

    def test_no_status_no_guessed_card(self):
        from app.agent import sasha as AG
        self.status_of.return_value = {**FIXED, "state": "awaiting_payment", "line": ST.WORDS["awaiting_payment"]}
        self.assertIsNone(run(AG.booked_event(ACCT)))
        self.status_of.side_effect = RuntimeError("records down")
        self.assertIsNone(run(AG.booked_event(ACCT)))

    def test_the_settled_event_carries_it(self):
        from booking_signer import live_events as LE
        got = run(LE.on_settled(ACCT, {"status": "failed", "failed": ["x"]}))   # failed: no email is tried
        self.assertEqual(got["event"]["status"], ST.public(FIXED))


class GetStatusIsTheOneSource(unittest.TestCase):
    def test_get_status_keeps_its_keys_and_adds_the_state(self):
        from agapi import venues as VN

        async def vb(account, include_cancelled=False):
            return [{"venue": "Casa Gate", "date": "2099-01-01", "time": "21:00", "status": "requested"}]
        with mock.patch.object(VN, "venue_bookings", vb), mock.patch.object(API, "_latest", mock.AsyncMock(return_value=None)):
            r = run(API.get_status(API.Ctx(account=ACCT), {}))
        for k in ("venues", "anything_booked", "booked", "failed", "cancelled", "awaiting_payment", "state", "line", "refs"):
            self.assertIn(k, r)
        self.assertEqual((r["state"], r["line"]), ("requested", "Requested — not confirmed yet: Casa Gate — 2099-01-01 21:00."))

    def test_the_read_back_status_is_the_one_status_word(self):
        self.assertIn('"status": _ST_HELD', _read(BACK, "agapi", "v0.py"))
        self.assertEqual(ST.HELD, "not booked — waiting for the yes")   # the words it always said


@unittest.skipUnless(os.path.isdir(FRONT), "no frontend checkout (the Railway image is the backend only)")
class TheFrontReadsIt(unittest.TestCase):
    def test_s2_has_no_regex_booked_card(self):   # it pinned the very double decision removed here
        src = _read(FRONT, "app", "s2", "S2App.tsx")
        self.assertNotIn(r"/^✅\s*Booked/m.test(reply)", src)
        self.assertNotIn("reply.match(/✅", src)
        self.assertIn("ev.type === 'booked'", src)
        self.assertIn("bookedLine(ev)", src)

    def test_the_trip_banner_reads_the_server_status(self):
        src = _read(FRONT, "app", "components", "workspace", "TripPanel.tsx")
        self.assertNotIn("not booked yet · Ref", src)
        self.assertNotIn("Boolean(bookingRef)", src)
        self.assertIn("r.json.trip_status", src)
        self.assertIn("{ts!.line}", src)
        self.assertIn('"trip_status"', _read(BACK, "booking_signer", "ladder_routes.py"))


class BasketBookingsInTheLedger(unittest.TestCase):
    def test_recorded_once_with_rung_api_and_never_the_persons_details(self):
        from agapi import s2_outcomes as OC
        sent = []

        async def call(op, body):
            sent.append((op, body))
            return {"ok": True, "result": {"id": "o1"}}
        rows = [{"id": "b-1", "kind": "flight", "state": "booked", "booking_reference": "ABC123",
                 "snapshot": {"owner": "Iberia", "flights": "IB3100", "from": "MAD", "to": "LIS", "passengers": [{"name": "Ana"}]}},
                {"id": "b-2", "kind": "stay", "state": "failed", "failed_why": "sold out", "snapshot": {"name": "Tings Lisbon", "city": "Lisbon"}},
                {"id": "b-3", "kind": "stay", "state": "pending_payment", "snapshot": {"name": "X"}}]
        with mock.patch.object(OC, "CALL", call), mock.patch.object(OC, "_DONE", set()):
            self.assertEqual(run(OC.basket_booked(ACCT, rows)), 2)
            self.assertEqual(run(OC.basket_booked(ACCT, rows)), 0)   # once per row
        self.assertEqual([op for op, _ in sent], ["outcomes.record", "outcomes.record"])
        f, h = sent[0][1], sent[1][1]
        self.assertEqual((f["rung"], f["channel"], f["state"], f["sector"], f["venue"], f["city"], f["confirmation_quote"]),
                         ("api", "api", "confirmed", "flight", "Iberia IB3100", "LIS", "Their reference: ABC123"))
        self.assertEqual((h["state"], h["sector"], h["venue"], h["city"], h["failure_reason"]), ("failed", "hotel", "Tings Lisbon", "Lisbon", "sold out"))
        blob = json.dumps(sent)
        for personal in ("Ana", "passengers", "email", "phone"):
            self.assertNotIn(personal, blob)

    def test_book_paid_records_them_awaited(self):
        src = _read(BACK, "booking_signer", "basket_book.py")
        self.assertIn("await asyncio.wait_for(OC.basket_booked(account, done + bad)", src)


# ── T13 · no fixed examples ──────────────────────────────────────────────────────────────────────────────────────────────────

MASK = re.compile(r"••••\s?\d")


def seen_by_model(surface: str):
    import app.services.llm as LLM
    from app.agent import sasha as AG
    from app.agent.fakes import Block, client
    seen = []

    async def go():
        async for _ in AG.turn(ACCT, "hello", [], f"s249-{surface}", None, surface):
            pass
    with mock.patch.object(LLM, "client", client([[Block(type="text", text="Hi.")]], seen=seen)), \
            mock.patch("app.services.chat_account.signed_in", lambda a: True):
        run(go())
    return seen[0]


class NoFixedExamples(unittest.TestCase):
    def test_the_model_sees_no_fixed_mask_on_s2_whatsapp_or_next(self):
        env = {k: v for k, v in os.environ.items() if k != "SASHA_S1_PARITY"}
        with mock.patch.dict(os.environ, env, clear=True):
            for surface in ("s2", "wa", "s1"):
                s = seen_by_model(surface)
                text = "".join(x["text"] for x in s["system"]) + json.dumps([t.get("description") for t in s["tools"]], ensure_ascii=False)
                self.assertIn("keep_list", text, surface)          # the Keep is on for this account …
                self.assertIsNone(MASK.search(text), surface)      # … and no fixed example is in what the model is given

    def test_source_scan_holds_the_few_left(self):
        """Every string literal (not a docstring) with a fixed mask or a demo name, in the backend's prompt-bearing code. The ones
        allowed are S1 with SASHA_S1_PARITY=off (byte-identical — they go with Tyler's OK) and chat_store's demo user (EU 245
        step 2, identity). A new one fails here."""
        pat = re.compile(r"••••\s?\d|Jon Peters")
        found: dict = {}
        files = [p for d in ("app", "agapi", "booking_signer", "products") for p in glob.glob(os.path.join(BACK, d, "**", "*.py"), recursive=True)]
        for f in files:
            toks = list(tokenize.generate_tokens(io.StringIO(_read(f)).readline))
            for i, t in enumerate(toks):
                if t.type != tokenize.STRING or not pat.search(t.string):
                    continue
                prev = [x for x in toks[:i] if x.type not in (tokenize.NL, tokenize.COMMENT)]
                nxt = toks[i + 1].type if i + 1 < len(toks) else None
                if (not prev or prev[-1].type in (tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT)) and nxt == tokenize.NEWLINE:
                    continue   # a docstring: documentation, never sent to the model
                k = os.path.relpath(f, BACK)
                found[k] = found.get(k, 0) + 1
        self.assertEqual(found, {"app/agent/sasha.py": 2,            # S1's Keep lines with parity off (byte-identical)
                                 "agapi/s2_keep.py": 1})             # S1's keep_list words with parity off (KEEP_LIST_S1)
        # (chat_store's demo user "Jon Peters" is gone — step 2, one identity — so the ratchet tightened)

    def test_the_parity_off_words_are_the_only_branch_that_keeps_them(self):
        from agapi import s2_keep as K
        self.assertIsNotNone(MASK.search(K.KEEP_LIST_S1))
        self.assertIsNone(MASK.search(K.KEEP_LIST_DESC))
        from app.agent import sasha as AG, s2 as S2
        self.assertIsNone(MASK.search(AG.KEEP_S1_LINES))
        self.assertIsNone(MASK.search(S2.S2_WHO + S2.S1_CAN + S2.s2_system()))

    def test_frontend_has_no_fixed_mask_outside_comments(self):
        for f in glob.glob(os.path.join(FRONT, "app", "**", "*.tsx"), recursive=True) + glob.glob(os.path.join(FRONT, "lib", "*.*s")):
            for n, line in enumerate(_read(f).splitlines(), 1):
                s = line.strip()
                if MASK.search(s) and not s.startswith(("//", "*", "/*")):
                    self.fail(f"{f}:{n} {s[:80]}")


class OneHotelName(unittest.TestCase):
    def test_hotel_web_uses_hotel_name(self):
        self.assertIn('hotel_name(c["name"]) or c["name"]', _read(BACK, "booking_signer", "hotel_web.py"))

    def test_hotels_keep_their_address_and_rating(self):   # the inline-# comment used to swallow both keys
        from app.services import world_itinerary as WI
        from booking_signer import guest_whatsapp as GW
        cands = [{"name": "Tings Lisbon - better rates and service when you book direct", "place_id": "p1", "address": "Rua X 1",
                  "rating": 4.6, "rating_count": 300, "types": ["lodging"]}]
        with mock.patch.object(GW, "api", mock.AsyncMock(return_value=(200, {"candidates": cands}))):
            out = run(WI.hotels_in(ACCT, "Lisbon", "Portugal", "PT"))
        self.assertEqual((out[0]["name"], out[0]["address"], out[0]["rating"]), ("Tings Lisbon", "Rua X 1", 4.6))


# ── T10 · one capability list ───────────────────────────────────────────────────────────────────────────────────────────────

class OneCapabilityList(unittest.TestCase):
    def _live(self, tool: str) -> bool:
        from app.agent import s2 as S2
        from agapi import s2_fine_print as FP, s2_subscriptions as SUBS
        own = set(FP.TOOL_NAMES) | {t["name"] for t in SUBS.TOOLS}
        return tool in own or (tool in S2.S2_TOOLS and tool in API.BY_NAME)

    def test_every_item_and_every_chip_maps_to_a_live_tool(self):
        from agapi import s2_home as H
        for g in H.CAPABILITIES:
            self.assertTrue(g.get("say"), g["group"])
            for line, tool in g["items"]:
                self.assertTrue(self._live(tool), line)
        for chip in H.CHIPS:
            self.assertTrue(self._live(H.CHIP_TOOLS[chip]), chip)
            self.assertIn(H.CHIP_TOOLS[chip], {t for g in H.CAPABILITIES for _, t in g["items"]} | {"what_i_can_do"}, chip)

    def test_say_is_generated(self):
        from agapi import s2_home as H
        for g in H.CAPABILITIES:
            self.assertIn(g["say"], H.SAY)
        self.assertEqual(run(H.what_i_can_do(API.Ctx(account=ACCT), {}))["say"], H.SAY)

    def test_s1_and_s2_prompts_carry_the_generated_section(self):
        from agapi import s2_home as H
        from app.agent import s2 as S2
        self.assertIn(H.prose(), S2.s2_system())
        self.assertIn(H.prose(), S2.S1_CAN)
        for g in H.CAPABILITIES:
            self.assertIn(g["group"], H.prose())
        env = {k: v for k, v in os.environ.items() if k != "SASHA_S1_PARITY"}
        with mock.patch.dict(os.environ, env, clear=True):
            for surface in ("s2", "s1"):
                self.assertIn(H.prose(), seen_by_model(surface)["system"][0]["text"], surface)

    def test_the_chips_are_generated_on_s2_and_next(self):
        from scripts import capabilities_out as CO
        path = CO.OUT
        if not os.path.exists(path):
            self.skipTest("no frontend checkout")
        self.assertEqual(_read(path), CO.render(), "regenerate: cd backend && python -m scripts.capabilities_out")
        s2 = _read(FRONT, "app", "s2", "S2App.tsx")
        nxt = _read(FRONT, "app", "next", "page.tsx")
        for src in (s2, nxt):
            self.assertIn("import { CHIPS } from '@/lib/capabilities.generated.mjs'", src)
        self.assertNotIn("const CHIPS = [", s2)
        self.assertIn("const PRESET_PROMPTS = CHIPS", nxt)

    def test_whatsapp_words_under_the_one_brain_come_from_the_list(self):
        from agapi import s2_home as H
        from booking_signer import guest_whatsapp as GW
        with mock.patch.dict(os.environ, {"SASHA_WA_BRAIN": "agent"}):
            self.assertEqual((GW.help_words(ACCT), GW.linked_words(ACCT), GW.onboard_words()), (H.wa_help(), H.wa_linked(), H.wa_onboard()))
            for w in (GW.help_words(ACCT), GW.linked_words(ACCT), GW.onboard_words()):
                self.assertIn(H.SAY, w)
            self.assertIn("{web}", GW.onboard_words())
        with mock.patch.dict(os.environ, {"SASHA_WA_BRAIN": "old"}):   # the old brain keeps its own words (they go with it)
            self.assertEqual((GW.help_words(ACCT), GW.linked_words(ACCT), GW.onboard_words()), (GW.HELP, GW.LINKED, GW.ONBOARD))

    def test_the_old_conductors_lists_feed_nothing_else(self):
        """CAPABILITY_FACTS / ABILITIES stay only in the old conductor's own prompt (retired with it): no other surface reads them."""
        users = set()
        for d in ("app", "agapi", "booking_signer", "products"):
            for f in glob.glob(os.path.join(BACK, d, "**", "*.py"), recursive=True):
                src = _read(f)
                if re.search(r"\bCAPABILITY_FACTS\b|import ABILITIES\b|abilities import", src):
                    users.add(os.path.relpath(f, BACK))
        self.assertEqual(users - {"booking_signer/abilities.py"}, {"app/services/conductor.py", "booking_signer/routes.py"})


if __name__ == "__main__":
    unittest.main()
