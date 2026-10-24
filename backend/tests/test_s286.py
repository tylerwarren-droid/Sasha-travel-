"""Sasha 286 · T66 — THE FLOOR: Sasha never asks for a link (Tyler, 24 Oct 08:06, standing rule: "what she can never say is: you can
paste the website here for further assistance… that's horrible"). The worst case is ALWAYS a hand-over, never a request.

ROOT TEST (written before the code):
  (1) ONE place S2's last resort lives: agapi.venues.floor (and floor_out, its hand-over). Before: voice.NO_LINK / no_link_line
      ("…if you can, send it to me and I'll fill it in.") in read_booking_route and _prepared_now's no_channel, and 284b's NO_WAY_YET in
      follow() — all three now call floor().
  (2) One floor, not a string per reason, venue or language: AgAPI's own floor when it gives one (route none, CR 118c) unless it asks
      for a link; else their website (the place card S2 holds) as the button, else their listing; the listing's WhatsApp / number beside
      it; the way back (283's row). The line is ONE template by what the button is (voice.floor_line).
  (3) Ratchet: no string S2 can say or show asks for a link / URL / website — every string literal on the one path (backend; the
      frontend's own run holds its half), every AgAPI say_text S2 passes through (refused at the read and the hand-over), and anything
      the model writes (sasha.turn drops it on /s2).
Offline: fakes only.
    cd backend && python -m unittest tests.test_s286 -v
"""
from __future__ import annotations

import ast
import asyncio
import inspect
import pathlib
import unittest
from unittest import mock

from agapi import venue_truth as VT, venues as VN
from app.agent import voice as V

run = asyncio.run
BACKEND = pathlib.Path(__file__).resolve().parents[1]
ACCT = "00000000-0000-4000-8000-000000000286"
OPULENCE = {"name": "Opulence Thai Spa", "place_id": "ChIJ286", "website": "https://opulencethaispa.co.uk/"}
RD = {"venue": "Opulence Thai Spa", "place_id": "ChIJ286", "rungs": {"phone": {"value": "+442071234567"}, "whatsapp": {"value": "+447700900286"}}}
NONE = {"route": "none", "how_far": "link", "say_text": "I couldn't find a way to book Opulence online or by message. You can take it over — "
                                                        "here's what I found.",
        "button": {"label": "See what I found", "link": "https://maps.google.com/?cid=286", "sends": False}}


class TheOneFloor(unittest.TestCase):
    def test_their_website_is_the_button_with_the_listings_ways_beside_it(self):
        f = VN.floor(OPULENCE, RD)
        self.assertEqual(f["say"], V.FLOOR)
        self.assertEqual(f["button"], {"label": V.OPEN_WEBSITE, "link": OPULENCE["website"]})
        self.assertEqual([a["link"] for a in f["alternatives"]], ["https://wa.me/447700900286", "tel:+442071234567"])

    def test_discovers_own_link_counts_as_their_website(self):
        f = VN.floor({"name": "X", "link": "http://www.x.example/"}, {"venue": "X"})
        self.assertEqual(f["button"]["link"], "http://www.x.example/")

    def test_no_website_their_listing_never_empty(self):
        f = VN.floor({"name": "Made Ink Tattoo", "place_id": "ChIJmi"}, {"venue": "Made Ink Tattoo", "rungs": {}})
        self.assertEqual(f["say"], V.floor_line("listing"))
        self.assertTrue(f["button"]["link"].startswith("https://www.google.com/maps/search/?api=1&query=Made%20Ink%20Tattoo"))
        self.assertIn("query_place_id=ChIJmi", f["button"]["link"])
        self.assertTrue(VN.floor(None, {"venue": "Y"})["button"]["link"].startswith("https://"))   # not even a card: still a button

    def test_agapis_own_floor_when_it_gives_one(self):
        f = VN.floor(OPULENCE, RD, NONE)
        self.assertEqual((f["say"], f["button"]["link"], f["from"]), (NONE["say_text"], NONE["button"]["link"], "agapi"))

    def test_agapis_words_that_ask_for_a_link_are_never_said(self):
        asking = {**NONE, "say_text": "I couldn't find a way to book them — if you have their booking link, send it to me."}
        f = VN.floor(OPULENCE, RD, asking)
        self.assertEqual((f["say"], f["from"]), (V.FLOOR, "sasha"))

    def test_one_template_never_a_string_per_reason(self):
        self.assertEqual({V.floor_line(w) for w in ("website", "listing", "anything")}, {V.FLOOR, V.floor_line("listing")})
        for n in ("NO_LINK", "no_link_line", "NO_WAY_YET"):
            self.assertFalse(hasattr(V, n), n)   # retired


class Memory:
    def __init__(self):
        self.kinds = {}

    async def kind(self, _a, name):
        return self.kinds.get(name)

    async def put_kind(self, _a, name, value):
        self.kinds[name] = [dict(r) for r in value]
        return True


class EveryLastResortEndsInTheFloor(unittest.TestCase):
    def setUp(self):
        VN._PREPARED.pop(ACCT, None)
        self.mem = Memory()
        from agapi import s2_memory as M
        self.p = [mock.patch.object(M, "kind", self.mem.kind), mock.patch.object(M, "put_kind", self.mem.put_kind)]
        for p in self.p:
            p.start()

    def tearDown(self):
        for p in self.p:
            p.stop()

    def _read(self, eng=None, dec=None):
        ctx = type("Ctx", (), {"account": ACCT, "surface": "s2"})()
        with mock.patch("agapi.test_venues.vet", mock.AsyncMock(side_effect=lambda c, a: a)), \
                mock.patch.object(VN, "_read", mock.AsyncMock(return_value=dict(RD))), mock.patch.object(VN, "card_of", lambda *a: OPULENCE), \
                mock.patch.object(VN, "engine_channel", mock.AsyncMock(return_value=eng)), mock.patch.object(VN, "read_channel", lambda r, c, **k: eng), \
                mock.patch.object(VT, "decision", lambda p: dec):
            return run(VN.read_booking_route(ctx, {"name": "Opulence Thai Spa", "city": "London", "day": "2099-11-01"}))

    def test_agapi_unreachable_ends_in_their_website_with_the_way_back(self):
        got = self._read()   # no channel read, no decision: AgAPI down / unreadable / blocked
        self.assertEqual(got["how"], V.FLOOR)
        self.assertEqual(got["page_url"], OPULENCE["website"])
        from app.agent import sasha as SA
        ev = SA.render("read_booking_route", got, {})
        self.assertEqual((ev["kind"], ev["url"], ev["label"]), ("handover", OPULENCE["website"], V.OPEN_WEBSITE))
        self.assertEqual(len(ev["alternatives"]), 2)
        self.assertEqual(self.mem.kinds[VN.PREPARED_KIND][-1]["url"], OPULENCE["website"])   # the row "Did it go through?" reads

    def test_agapis_none_is_said_in_agapis_words(self):
        got = self._read(dec=NONE)
        self.assertEqual((got["how"], got["page_url"]), (NONE["say_text"], NONE["button"]["link"]))

    def test_the_hold_with_no_channel_hands_over_the_floor(self):
        ctx = type("Ctx", (), {"account": ACCT, "surface": "s2"})()
        d = {"action": "prepared_link", "say": "no_channel", "takeover": {"say": "You can take it over.", "link": None}}
        with mock.patch.object(VT, "decision", lambda p: None), mock.patch.object(VN, "_rules", lambda d: {"say_key": "no_channel"}):
            out = run(VN._prepared_now(ctx, {"name": "Opulence"}, dict(RD), {"how_many": {"count": 2}}, "2099-11-01T19:00", None, None,
                                       OPULENCE, d))
        self.assertEqual(out["status"], "page_link")
        self.assertTrue(out["say"].startswith(V.FLOOR))
        self.assertEqual(out["button"]["link"], OPULENCE["website"])

    def test_every_last_resort_calls_the_one_floor(self):
        for fn in (VN.read_booking_route, VN._prepared_now, VN.follow):
            self.assertIn("floor_out(", inspect.getsource(fn), fn.__name__)


class NothingSheSaysAsksForALink(unittest.TestCase):
    """THE RATCHET (3)."""
    ASKS = ["I can't see their booking link from here — if you can, send it to me and I'll fill it in.",
            "You can paste the website here for further assistance.", "Send me their link and I'll book it.",
            "Could you share their booking page?", "If you have their booking link, send it over.", "Envíame el enlace y lo hago.",
            "Pásame la web de la reserva.", "Share their link with me."]
    FINE = [V.FLOOR, V.floor_line("listing"), "I'll send their page to your phone.", "Their page is on your screen.",
            "The link is on your screen — tap it.", "I'll tell you when their page confirms.", V.OPEN_WEBSITE, V.OPEN_LISTING]
    # words that are NOT hers to the person: the person's own yes, an SMS to a venue, this detector's own docstring
    ALLOWED = {("agapi/v0.py", "send me the link"), ("booking_signer/payments_t0.py", ", could you send the deposit payment link")}

    def test_the_detector(self):
        for t in self.ASKS:
            self.assertTrue(V.asks_for_link(t), t)
        for t in self.FINE:
            self.assertFalse(V.asks_for_link(t), t)

    def test_no_string_on_the_one_path_asks(self):
        bad = []
        files = [f for d in ("agapi", "app/agent", "app/services", "booking_signer") for f in (BACKEND / d).glob("*.py")]
        for f in files:
            rel = str(f.relative_to(BACKEND))
            tree = ast.parse(f.read_text(encoding="utf-8"))
            docs = {id(n.body[0].value) for n in ast.walk(tree) if isinstance(n, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                    and n.body and isinstance(n.body[0], ast.Expr) and isinstance(getattr(n.body[0], "value", None), ast.Constant)}
            for n in ast.walk(tree):
                if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docs and V.asks_for_link(n.value) \
                        and (rel, n.value) not in self.ALLOWED:
                    bad.append(f"{rel}:{n.lineno}: {n.value[:80]!r}")
        self.assertEqual(bad, [])

    def test_her_rules_and_every_line_of_her_voice(self):
        for n in dir(V):
            v = getattr(V, n)
            for s in ([v] if isinstance(v, str) else list(v.values()) if isinstance(v, dict) else []):
                if isinstance(s, str):
                    self.assertFalse(V.asks_for_link(s), n)

    def test_agapis_words_never_pass_through_asking(self):
        asking = {"route": "platform", "how_far": "hand_over", "say_text": "Paste their booking link here and I'll fill it in.",
                  "button": {"label": "Book", "link": "https://x.example", "sends": False}}
        ctx = type("Ctx", (), {"account": ACCT, "surface": "s2"})()
        with mock.patch("agapi.test_venues.vet", mock.AsyncMock(side_effect=lambda c, a: a)), \
                mock.patch.object(VN, "_read", mock.AsyncMock(return_value=dict(RD))), mock.patch.object(VN, "card_of", lambda *a: None), \
                mock.patch.object(VN, "engine_channel", mock.AsyncMock(return_value=None)), mock.patch.object(VN, "read_channel", lambda r, c, **k: None), \
                mock.patch.object(VT, "decision", lambda p: asking), mock.patch.object(VN, "note_prepared", mock.AsyncMock()):
            got = run(VN.read_booking_route(ctx, {"name": "X"}))
        self.assertFalse(V.asks_for_link(got["how"]))
        self.assertIn('not V.asks_for_link(x)', inspect.getsource(VN._book_inner))   # the hand-over's words too

    def test_the_model_writing_one_is_dropped_on_s2(self):
        from app.agent import sasha as SA
        src = inspect.getsource(SA)
        self.assertIn("if honest and _V.asks_for_link(x):", src)
        self.assertTrue(any("asks for a link" in f for f in V.faults([("assistant", self.ASKS[1])])))   # the gate's voice check


if __name__ == "__main__":
    unittest.main()
