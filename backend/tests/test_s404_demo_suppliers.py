"""Sasha 404 · A DEMO SUPPLIER ALWAYS SHOWS IT IS ONE (root test: mailbox row 2145; KANOE "THE DMC SPACE" 20 Nov, "DEMO CONTACTS" 25 Nov).

Measured: what a supplier IS was decided by name in many modules, and the founder demo's stand-in mark was STRIPPED per screen
(itinerary_q ×3, guest_whatsapp ×2, plan_store, TripPanel, ChatBooking, no-test-label) — a demo booking showed as the real venue. The demo
venue carried an invented number (+1 500 555 0193) as a literal.

THE CLASS: every demo supplier (Kanoe's test venues and hotel, the stand-in, the test carriers) × every door (S2 and /next through the REAL
cardsOf + no-test-label; WhatsApp through the REAL renderer) → its mark, on the card, from ONE source (booking_signer/supplier.py); a real
supplier in test mode keeps today's (no word on the card); no screen decides the kind itself; no contact is a literal.

    cd backend && python -m unittest tests.test_s404_demo_suppliers -v
"""
from __future__ import annotations

import asyncio
import json
import os
import pathlib
import re
import shutil
import subprocess
import unittest
from unittest import mock

from booking_signer import supplier as SP

BACKEND = pathlib.Path(__file__).resolve().parents[1]
FE = BACKEND.parent / "frontend"


def run(c):
    return asyncio.run(c)


def node(js: str):
    out = subprocess.run(["node", "--no-warnings", "-e", js], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def drawn_on_s2(ev: dict):
    """The REAL page: cardsOf (lib/cards-of.ts), then no-test-label's untagDeep — what S2 and /next draw."""
    return node(f"Promise.all([import('{(FE / 'lib/cards-of.ts').as_posix()}'), import('{(FE / 'lib/no-test-label.mjs').as_posix()}')])"
                f".then(([c, u]) => process.stdout.write(JSON.stringify(u.untagDeep(c.cardsOf({json.dumps(ev)})))))")


def stream(tool: str, result: dict, args: dict):
    """THE STREAM's own render events for one scripted turn."""
    import app.services.llm as LLM
    from agapi import v0 as API
    from app.agent import sasha as AG
    from app.agent.fakes import Block, client
    steps = [[Block(type="tool_use", id="t1", name=tool, input=args)], [Block(type="text", text="Here you are.")]]

    async def call(ctx, name, a):
        ctx.calls.append({"tool": name, "ok": True})
        return result

    async def go():
        return [e async for e in AG.turn("00000000-0000-4000-8000-000000000404", "Show me", [], f"s404-{tool}", surface="s2")]
    with mock.patch.object(LLM, "client", client(steps)), mock.patch.object(API, "call", call), \
            mock.patch.dict(os.environ, {"SASHA_S1_PARITY": "on"}):
        return [e for e in run(go()) if e.get("type") == "render"]


def whatsapp(ev: dict) -> str:
    from booking_signer import guest_whatsapp as GW, wa_agent as WA
    out = GW.Out()
    WA.render(ev, out, {}, None)
    return json.dumps(out.items, ensure_ascii=False)


class TheOneSource(unittest.TestCase):
    def test_every_demo_supplier_is_named_with_its_mark(self):
        from agapi import s2_hotel as H, test_venues as TV
        names = [v["name"] for v in TV.TEST_VENUES()] + [H.TEST_HOTEL, SP.standin_name("Casa Lucio")] + \
                [SP.shown(n) for n in SP.DEMO_CARRIERS.values()]
        for n in names:
            self.assertEqual(SP.kind_of(n), "demo", n)
            self.assertIn(f"· {SP.DEMO_MARK}", n, n)
            self.assertEqual(SP.shown(n), n, n)                                                  # exactly once

    def test_old_rows_are_shown_with_the_mark(self):
        self.assertEqual(SP.shown("Casa Lucio (TEST stand-in)"), "Casa Lucio · Demo stand-in")
        self.assertEqual(SP.shown("Sasha Test Venue"), "Sasha Test Venue · Demo")
        self.assertEqual(SP.shown("Lhardy"), "Lhardy")                                          # a real supplier: as it is
        self.assertEqual(SP.kind_of({"name": "Lhardy", "test": True}), "real_test")             # real, in test mode: no mark

    def test_contacts_are_configuration(self):
        with mock.patch.dict(os.environ, {"SASHA_DEMO_VENUE_PHONE": ""}):
            self.assertIsNone(SP.demo_venue_phone())
        with mock.patch.dict(os.environ, {"SASHA_DEMO_VENUE_PHONE": "+34000000404"}):              # a fictional value in the test
            from agapi import test_venues as TV
            self.assertEqual(next(v for v in TV.TEST_VENUES() if v["place_id"] == "kanoe-taverna-sandbox")["phone"], "+34000000404")


@unittest.skipUnless(shutil.which("node"), "node runs the page's own cardsOf and no-test-label")
class EveryDoorShowsTheMark(unittest.TestCase):
    def test_a_demo_venue_card_on_s2_next_and_whatsapp(self):
        from agapi import test_venues as TV
        card = next(v for v in TV.TEST_VENUES() if v["place_id"] == "kanoe-test-venue")
        evs = stream("search_venues", {"ok": True, "result": {"find": {"what": "dinner"}, "preset": {"cards": [card], "show": 1}}},
                     {"what": "dinner", "where": "Madrid"})
        self.assertTrue(evs)
        for ev in evs:
            self.assertIn("Sasha Test Venue · Demo", json.dumps(drawn_on_s2(ev), ensure_ascii=False))
            self.assertIn("Sasha Test Venue · Demo", whatsapp(ev))

    def test_a_test_carrier_on_s2_next_and_whatsapp(self):
        res = {"ok": True, "result": {"party": 1, "leg": "out", "flights": [
            {"offer_id": "off_zz", "airline": "Duffel Airways", "departs": "2037-12-01T08:00", "duration_minutes": 150, "from": "MAD",
             "to": "LHR", "stops": 0, "flights": "ZZ1", "price_eur": 99.0}]}}
        for ev in stream("search_flights", res, {"origin": "Madrid", "destination": "London", "date": "2037-12-01"}):
            self.assertIn("Duffel Airways · Demo", json.dumps(drawn_on_s2(ev), ensure_ascii=False))
            self.assertIn("Duffel Airways · Demo", whatsapp(ev))

    def test_no_test_label_can_never_remove_the_mark(self):
        for s in ["Sasha Test Venue · Demo", "Casa Lucio · Demo stand-in (TEST)", "TEST · booked Taverna Correo · Demo"]:
            got = node(f"import('{(FE / 'lib/no-test-label.mjs').as_posix()}').then(m => process.stdout.write(JSON.stringify(m.untag({json.dumps(s)}))))")
            self.assertIn("· Demo", got, s)


#: the only modules that may hold a demo supplier's NAME: where it is defined, found by the person's words, or drawn as its own page
NAMES_OK = {"booking_signer/supplier.py", "agapi/test_venues.py", "booking_signer/form_rung.py", "booking_signer/handover.py",
            "booking_signer/demo_ops.py", "booking_signer/test_deposit.py", "booking_signer/captcha_test.py", "booking_signer/hotel_test.py",
            "booking_signer/guest_whatsapp.py", "booking_signer/ladder_routes.py", "agapi/agapi_route.py", "agapi/s2_keep.py",
            "app/agent/sasha.py", "agapi/venues.py", "booking_signer/journeys.py"}


class Ratchet(unittest.TestCase):
    def sources(self):
        for d in ("agapi", "app", "booking_signer", "products"):
            for p in (BACKEND / d).rglob("*.py"):
                yield p.relative_to(BACKEND).as_posix(), p.read_text()
        for p in list((FE / "app").rglob("*.tsx")) + list((FE / "lib").rglob("*.ts")) + list((FE / "lib").rglob("*.mjs")):
            if "node_modules" not in p.parts:
                yield p.relative_to(FE.parent).as_posix(), p.read_text()

    def test_no_screen_strips_or_decides_a_demo_supplier(self):
        for rel, src in self.sources():
            if rel == "backend/booking_signer/supplier.py" or rel.endswith("booking_signer/supplier.py"):
                continue
            code = "\n".join(l.split("#", 1)[0] for l in src.splitlines()) if rel.endswith(".py") else src
            self.assertNotRegex(code, r"stand-in\)?['\"]?,\s*['\"]{2}\)|replace\(/ \\\(TEST stand-in", rel)   # a per-screen strip
            self.assertNotRegex(code, r"test venue stood in", rel)
            self.assertNotIn("TEST_VENUE_MARKS", code, rel)
            if rel.endswith((".tsx", ".ts")) or rel.endswith("no-test-label.mjs"):
                self.assertNotRegex(code, r"\\\(TEST stand-in\\\)|Sasha Test Venue|Kanoe Test Hotel", rel)   # a page decides nothing by name

    def test_no_contact_is_a_literal(self):
        for rel, src in self.sources():
            self.assertNotRegex(src, r"\+?1\s?500\s?555\s?0193|\+15005550193", rel)                 # the invented number is gone
            self.assertNotRegex(src, r"\+34\s?606\s?72\s?64\s?53|\+34606726453", rel)              # the demo number is configuration

    def test_the_kind_is_read_from_the_one_source(self):
        for rel in ("agapi/booking_decide.py", "agapi/test_venues.py", "booking_signer/venue_notice.py", "booking_signer/wa_brain.py",
                    "booking_signer/plan_store.py", "booking_signer/itinerary_q.py", "agapi/itinerary.py", "booking_signer/routes.py"):
            self.assertIn("supplier", (BACKEND / rel).read_text(), rel)


if __name__ == "__main__":
    unittest.main()
