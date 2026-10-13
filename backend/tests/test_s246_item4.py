"""Sasha 246 item 4 (EU 241's walk) · two fixes, offline (fixture pages and fakes only — no venue site, no booking platform, no
Google Places, no Duffel is contacted).

  A · RUNG 2: a venue whose OWN site books (an unmapped form, or its own engine linked from its site) is offered as their own
      booking page, prepared with the day, time and number — BEFORE email, a call, WhatsApp or Instagram. Live: Hammam Al
      Ándalus (madrid.hammamalandalus.com, its own engine) got email/Instagram; La Mi Venta (its own form) got phone/email.
  B · A FLIGHT CHANGE has one source of truth: the times she offers are the options the change accepts. Live: she offered a
      17:48 flight, then said she "couldn't find 17:48" (each call made a fresh Duffel change request — fresh offers).

    cd backend && python -m unittest tests.test_s246_item4 -v
"""
from __future__ import annotations
import tests.founder_fixture  # noqa: F401,E402  (Sasha 249 · the fixtures name the founder; no fallback any more)

import asyncio
import os
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

from booking_signer import decide as D, guest_whatsapp as GW, ladder as L, venue_read as V
from tests import test_booking_ladder as TBL   # a module: its own tests are not collected twice

run = asyncio.run
NOW = datetime(2026, 10, 12, 10, 0, tzinfo=timezone.utc)

# Fixture pages SHAPED like the walk's two venues (written here, never fetched): the hammam's own site links its own booking
# engine on a subdomain; the restaurant's own page carries a booking form no one has mapped.
HAMMAM_SITE = """<html><body>
<a href="https://madrid.hammamalandalus.com/reservas/">Reservar</a>
<a href="https://madrid.hammamalandalus.com/tarjeta-regalo/">Tarjeta regalo</a>
<a href="https://www.instagram.com/hammamalandalus/">Instagram</a>
<a href="mailto:madrid@hammamalandalus.com">Escríbenos</a> <a href="tel:+34914299020">Llámanos</a>
<script src="https://www.google.com/recaptcha/api.js"></script></body></html>"""
MI_VENTA_SITE = """<html><body><form action="/reservas/enviar"><input type="date" name="fecha"><input name="hora">
<input name="personas"><input name="nombre"><input type="email" name="email"></form>
<a href="tel:+34915550101">Tel</a> <a href="mailto:reservas@lamiventa.test">Email</a></body></html>"""
ENV = {**TBL.ENV}


def read_of(html: str, url: str, name: str) -> dict:
    return {"name": name, "country": "ES", "facts": [f.__dict__ for f in V.facts_from_html(html, url, "ES", NOW.isoformat())]}


def rd_of(read: dict) -> dict:
    """The read as the WhatsApp flow and the agent keep it: its AVAILABLE rungs only."""
    rungs = {r["rung"]: {"fact_index": r["fact_index"], "value": r["value"]} for r in L.choose(read)["rungs"] if r["available"]}
    return {"read_id": "r1", "venue": read["name"], "country": "ES", "facts": read["facts"], "rungs": rungs}


class Rung2Read(unittest.TestCase):
    def test_their_own_engine_linked_from_their_site_is_a_booking_page(self):
        facts = V.facts_from_html(HAMMAM_SITE, "https://www.hammamalandalus.com/madrid/", "ES", "t")
        pages = [f.value for f in facts if f.kind == "booking_page"]
        self.assertEqual(pages, ["https://madrid.hammamalandalus.com/reservas/"])   # the gift-voucher shop is never one

    def test_another_site_or_a_plain_page_is_no_booking_page(self):
        other = '<a href="https://booking.someone-else.test/reservas">Reservar</a> <a href="/menu">Menú</a>'
        self.assertFalse([f for f in V.facts_from_html(other, "https://www.hammamalandalus.com/", "ES", "t") if f.kind == "booking_page"])
        self.assertTrue(V.same_site("madrid.hammamalandalus.com", "www.hammamalandalus.com"))
        self.assertFalse(V.same_site("a.co.uk", "b.co.uk"))


class Rung2Ladder(unittest.TestCase):
    def setUp(self):
        from tests.test_s254_one_decider import live_access   # Sasha 254 · the executors behind the booking rules: a person who may reach real venues
        live_access(self)
        self.env = mock.patch.dict(os.environ, ENV)
        self.env.start()

    def tearDown(self):
        self.env.stop()

    def test_hammam_their_own_page_first_before_email_and_instagram(self):
        read = read_of(HAMMAM_SITE, "https://www.hammamalandalus.com/madrid/", "Hammam Al Ándalus")
        c = L.choose(read)
        order = [r["rung"] for r in c["rungs"] if r["available"]]
        self.assertEqual(order[0], "own_page")
        self.assertLess(order.index("own_page"), order.index("email"))
        self.assertEqual(c["rungs"][0]["value"], "https://madrid.hammamalandalus.com/reservas/")
        self.assertTrue(c["say"].startswith("They take bookings on their own website. I'll send you their own booking page"))

    def test_la_mi_venta_unmapped_form_its_page_first_before_phone_and_email(self):
        read = read_of(MI_VENTA_SITE, "https://www.lamiventa.test/reservas", "La Mi Venta")
        c = L.choose(read)
        by = {r["rung"]: r for r in c["rungs"]}
        self.assertFalse(by["form"]["available"])   # still never SENT unmapped (S-17, Sasha 89)
        self.assertTrue(by["own_page"]["available"])
        self.assertEqual(by["own_page"]["value"], "https://www.lamiventa.test/reservas")
        self.assertTrue(c["say"].startswith("They have a booking form, but I can't fill it yet. I'll send you their own booking page"))
        avail = [r["rung"] for r in c["rungs"] if r["available"]]
        self.assertLess(avail.index("own_page"), min(avail.index("phone"), avail.index("email")))

    def test_a_platform_they_use_never_gets_their_own_page_in_its_place(self):   # Sasha 195, unchanged
        read = read_of(MI_VENTA_SITE + '<iframe src="https://widget.thefork.com/abc"></iframe>', "https://www.lamiventa.test/reservas", "X")
        self.assertNotIn("own_page", {r["rung"] for r in L.choose(read)["rungs"]})

    def test_a_captcha_on_their_booking_page_is_their_own_page_but_not_on_the_home_page(self):
        f = {"kind": "challenge", "value": "captcha", "source_kind": "site", "source_label": "their website, h.test"}
        self.assertEqual(L.own_page({"facts": [{**f, "source_url": "https://h.test/reservar"}]})[1], "https://h.test/reservar")
        self.assertIsNone(L.own_page({"facts": [{**f, "source_url": "https://h.test/"}]}))

    def test_whatsapp_and_web_their_page_first_by_the_booking_rules(self):
        # Sasha 254 · the old flow's / web card's ladder is the booking rules' answer (agapi.booking_decide.legacy_*): their own page
        # behind a CAPTCHA is theirs to confirm (R13) — prepared, never zero-touch, no question; soon or not; a preference doesn't
        # route around the rules
        from agapi.booking_rules import booking_rules as BR
        rd = rd_of(read_of(HAMMAM_SITE, "https://www.hammamalandalus.com/madrid/", "Hammam Al Ándalus"))
        res = {"when": {"mode": "at", "at": "2026-10-20T17:00"}, "how_many": {"count": 2}}   # > 48 h
        self.assertIsNone(GW.ladder_of(rd, res, NOW))
        for at in ("2026-10-20T17:00", "2026-10-12T20:00"):
            dv = GW.decision_of(rd, None, at, NOW)
            self.assertEqual((dv.route, dv.decision["say"]), ("one_tap", "prepared_link_captcha"))
            self.assertTrue(GW.route_line_of(rd, dv).startswith(BR.PHRASES["prepared_link_captcha"]))
        self.assertEqual(GW.decision_of(rd, "email", "2026-10-12T20:00", NOW).route, "one_tap")

    def test_a_platform_with_their_own_email_the_email_first(self):   # Sasha 254 · R1 / R14 (was decide.ladder's "email or page")
        rd = {"venue": "X", "country": "ES", "rungs": {"link": {"value": "CoverManager"}, "email": {"value": "x@x.es"}, "phone": {"value": "+34910"}}}
        with mock.patch("agapi.booking_decide.access_cached", lambda a: {"mode": "live", "calls": "on", "real_venue_sends": "on"}):
            self.assertEqual(GW.decision_of(rd, None, "2026-10-20T17:00", NOW).route, "email")
            self.assertIsNone(GW.ladder_of(rd, {"when": {"mode": "at", "at": "2026-10-20T17:00"}}, NOW))


class Rung2Agent(unittest.TestCase):
    """The agent's tools (read_booking_route / hold_venue): their page is a route, offered first, and prepared via /links."""

    def setUp(self):
        from tests.test_s254_one_decider import live_access   # Sasha 254 · the executors behind the booking rules: a person who may reach real venues
        live_access(self)
        self.env = mock.patch.dict(os.environ, ENV)
        self.env.start()

    def tearDown(self):
        self.env.stop()

    def test_routes_and_the_hold_prepare_their_page(self):
        from agapi import v0 as API, venues as VN
        rd = rd_of(read_of(HAMMAM_SITE, "https://www.hammamalandalus.com/madrid/", "Hammam Al Ándalus"))
        self.assertEqual(VN._routes_of(rd)[0], "page")
        self.assertLess(VN._routes_of(rd).index("page"), VN._routes_of(rd).index("instagram"))
        calls = []

        async def api(account, method, path, body=None, timeout=None):
            calls.append(path)
            if path == "/api/booking/links":
                return 200, {"link_id": "l1", "url": "https://madrid.hammamalandalus.com/reservas/", "platform": "their own booking page",
                             "slot_filled": False, "read_back": {"lines": ["I'll send you their own booking page."], "sha256": "a" * 64}}
            return 404, {"rule": "no"}
        ctx = API.Ctx(account="00000000-0000-4000-8000-000000000246", surface="s2")
        res = {"who": {"name": "Ana", "contact": {"mobile_e164": "+34600000000"}}, "when": {"mode": "at", "at": "2026-10-20T17:00"},
               "how_many": {"count": 2}, "what": {"category": "spa"}}
        a = {"what": "Arab baths"}
        # Sasha 254 · the booking rules decide (R13: their page behind a CAPTCHA is theirs) — prepared on their screen at once, nothing
        # sent to the venue, no question first
        from agapi.booking_rules import booking_rules as BR
        from booking_signer import guest_receipt as GR, wa_brain as WB
        from agapi import s2_outcomes as OC
        with mock.patch.object(GW, "api", api), mock.patch("agapi.venue_truth.prepare", mock.AsyncMock(return_value=None)), \
                mock.patch.object(GR, "address_of", mock.AsyncMock(return_value=None)), mock.patch.object(OC, "booked", mock.AsyncMock()), \
                mock.patch.object(WB, "trip_day_words", mock.AsyncMock(return_value="")), mock.patch.object(GW, "STORE", None):
            eng = VN.read_channel(rd, {"website": "https://www.hammamalandalus.com/madrid/"})
            d = run(VN.rules_for(ctx, a, rd, res, "2026-10-20T17:00", eng, None, None, NOW))
            self.assertEqual((d["action"], d["say"]), ("prepared_link", "prepared_link_captcha"))
            got = run(VN._execute(ctx, a, rd, res, "2026-10-20T17:00", NOW, d, eng, None))
        self.assertEqual(got["status"], "page_link")
        self.assertTrue(got["say"].startswith(BR.PHRASES["prepared_link_captcha"]))
        self.assertEqual(calls, [])                                    # nothing reached the venue
        VN._HELD.pop(ctx.account, None)


class Rung2LinkRoute(unittest.TestCase):
    """/links: their own engine's page, read on their own site, is the page sent — nothing else is contacted. (The ladder
    tests' harness, borrowed — not its tests.)"""
    BOOKING = TBL.LadderRoutes.BOOKING

    def make_stores(self):
        return TBL.MemoryCallStore(), TBL.MemoryLadderStore()

    def setUp(self):
        from tests.test_s254_one_decider import live_access   # Sasha 254 · the executors behind the booking rules: a person who may reach real venues
        live_access(self)
        TBL.LadderRoutes.setUp(self)

    def tearDown(self):
        TBL.LadderRoutes.tearDown(self)

    def test_their_own_engine_page_is_the_link(self):
        self.web.pages["https://www.lacontra.test/"] = TBL.R(200, text='<a href="https://reservas.lacontra.test/book">Reservar mesa</a>'
                                                                         '<a href="tel:+34915001122">Tel</a>')
        v = TBL.LadderRoutes.read(self)
        self.assertEqual(v["rungs"][0]["rung"], "own_page")
        self.assertTrue(v["say"].startswith("They take bookings on their own website."))
        p = self.c.post("/api/booking/links", json={"read_id": v["read_id"], **self.BOOKING}).json()
        self.assertEqual((p["platform"], p["url"]), ("their own booking page", "https://reservas.lacontra.test/book"))
        self.assertNotIn("https://reservas.lacontra.test/book", [u for _m, u, _b in self.web.requests])   # never fetched


# ── B · the flight change ───────────────────────────────────────────────────────────────────────────────────────────────

class ChangeOptionsAreOneSource(unittest.TestCase):
    def setUp(self):
        from tests.test_s254_one_decider import live_access   # Sasha 254 · the executors behind the booking rules: a person who may reach real venues
        live_access(self)
        from booking_signer import flight_manage as FM
        from tests import test_flight_manage_226 as TF
        self.FM, self.TF = FM, TF
        self.env = mock.patch.dict(os.environ, {"DUFFEL_ACCESS_TOKEN": "duffel_test_x"})
        self.env.start()
        self.saved = FM.HTTP

    def tearDown(self):
        self.FM.HTTP = self.saved
        self.env.stop()

    def offers(self):   # three times that day; the 17:48 is NOT the cheapest
        o, TF = self.TF.order(), self.TF
        def at(oid, total, hhmm, fn):
            x = TF.change_offer(oid, total, fn=fn)
            x["slices"]["add"][0]["segments"][0] = {**x["slices"]["add"][0]["segments"][0], "departing_at": f"2026-11-27T{hhmm}:00",
                                                    "arriving_at": f"2026-11-27T{hhmm}:00"}
            return x
        return o, [at("oco_0715", "60.50", "07:15", "7650"), at("oco_1748", "90.00", "17:48", "7654"), at("oco_2010", "120.00", "20:10", "7652")]

    def fake(self, rounds):
        """A Duffel whose EVERY change request returns a fresh set (as Duffel's test mode does): rounds[i] for request i."""
        TF, o = self.TF, self.offers()[0]
        seen = {"n": 0}

        async def http(method, path, body=None, params=None):
            if path == "/air/orders/ord_1":
                return 200, {"data": o}
            if path == "/air/order_change_requests":
                got = rounds[min(seen["n"], len(rounds) - 1)]
                seen["n"] += 1
                return 201, {"data": {"id": f"ocr_{seen['n']}", "live_mode": False, "order_change_offers": got}}
            if path == "/air/order_changes":
                return 201, {"data": {"id": "oce_1", "order_id": "ord_1", "live_mode": False, "change_total_amount": "90.00",
                                      "change_total_currency": "EUR", "confirmed_at": None, "selected": body["data"]["selected_order_change_offer"]}}
            if path == "/air/order_changes/oce_1/actions/confirm":
                return 200, {"data": {"id": "oce_1", "order_id": "ord_1", "live_mode": False, "confirmed_at": "2026-10-12T10:01:00Z"}}
            return 404, {"errors": [{"message": "no fake"}]}
        self.FM.HTTP = http
        return seen

    def test_the_quote_carries_every_option_with_its_own_id_and_words(self):
        _o, offers = self.offers()
        self.fake([offers])
        q = run(self.FM.change_quote("ord_1", "2026-11-27", "out"))
        self.assertEqual(q["change_offer_id"], "oco_0715")   # the cheapest is still the one read back (Sasha 226)
        self.assertEqual([(x["change_offer_id"], x["departs"][11:16]) for x in q["options"]],
                         [("oco_0715", "07:15"), ("oco_1748", "17:48"), ("oco_2010", "20:10")])
        self.assertIn("17:48", q["options"][1]["lines"][0])

    def test_she_offers_1748_and_the_change_accepts_1748(self):
        from agapi import s2_manage as M, v0 as API
        from tests import test_s2_226 as T
        _o, offers = self.offers()
        seen = self.fake([offers, [offers[0]]])   # a SECOND request would no longer have the 17:48
        M._HELD.clear()
        M._CHANGE.clear()
        pats = T.plans_patches() + [mock.patch.object(API, "claim", mock.AsyncMock()),
                                    mock.patch.object(M, "_record", mock.AsyncMock())]
        for p in pats:
            p.start()
            self.addCleanup(p.stop)
        first = run(M.change_booking(T.ctx(), {"what": "flight", "new_date": "2026-11-27", "approval": {"said": "move my flight to the 27th"}}))
        self.assertEqual(first["status"], "awaiting_yes")
        self.assertIn("17:48", " ".join(first["read_back"]))   # what she says lists the 17:48 …
        self.assertIn("17:48", [x["time"] for x in first["options"]])
        later = datetime.now(timezone.utc) + timedelta(seconds=5)
        pick = run(M.change_booking(T.ctx(started=later), {"what": "flight", "new_time": "17:48", "approval": {"said": "the 17:48 one"}}))
        self.assertEqual(pick["status"], "awaiting_yes")   # … and the change accepts it, from the SAME options
        self.assertIn("17:48", pick["read_back"][0])
        self.assertEqual(seen["n"], 1)   # never searched again
        self.assertEqual(M._HELD[T.ACCOUNT]["change_offer_id"], "oco_1748")
        later2 = later + timedelta(seconds=5)
        done = run(M.change_booking(T.ctx(started=later2), {"what": "flight", "approval": {"said": "Yes, go ahead."}}))
        self.assertEqual(done["status"], "changed")
        self.assertEqual(seen["n"], 1)

    def test_a_yes_naming_another_offered_time_reads_that_one_back_first(self):
        from agapi import s2_manage as M, v0 as API
        from tests import test_s2_226 as T
        _o, offers = self.offers()
        self.fake([offers])
        M._HELD.clear()
        M._CHANGE.clear()
        confirm = mock.AsyncMock()
        for p in T.plans_patches() + [mock.patch.object(API, "claim", mock.AsyncMock()), mock.patch.object(self.FM, "change_confirm", confirm)]:
            p.start()
            self.addCleanup(p.stop)
        run(M.change_booking(T.ctx(), {"what": "flight", "new_date": "2026-11-27"}))   # the 07:15 read back
        later = datetime.now(timezone.utc) + timedelta(seconds=5)
        r = run(M.change_booking(T.ctx(started=later), {"what": "flight", "approval": {"said": "Yes, the 17:48 please"}}))
        self.assertEqual(r["status"], "awaiting_yes")
        self.assertIn("17:48", r["read_back"][0])
        confirm.assert_not_awaited()   # the yes was to the 07:15's words: nothing changed

    def test_a_time_not_offered_lists_the_offered_ones(self):
        from agapi import s2_manage as M
        from tests import test_s2_226 as T
        _o, offers = self.offers()
        seen = self.fake([offers])
        M._HELD.clear()
        M._CHANGE.clear()
        for p in T.plans_patches():
            p.start()
            self.addCleanup(p.stop)
        run(M.change_booking(T.ctx(), {"what": "flight", "new_date": "2026-11-27"}))
        r = run(M.change_booking(T.ctx(), {"what": "flight", "new_time": "12:00"}))
        self.assertEqual(r["status"], "not_offered")
        self.assertEqual([x["time"] for x in r["options"]], ["07:15", "17:48", "20:10"])
        self.assertEqual(seen["n"], 1)

    def test_another_day_is_a_new_quote(self):
        from agapi import s2_manage as M
        from tests import test_s2_226 as T
        _o, offers = self.offers()
        seen = self.fake([offers])
        M._HELD.clear()
        M._CHANGE.clear()
        for p in T.plans_patches():
            p.start()
            self.addCleanup(p.stop)
        run(M.change_booking(T.ctx(), {"what": "flight", "new_date": "2026-11-27"}))
        run(M.change_booking(T.ctx(), {"what": "flight", "new_date": "2026-11-28"}))
        self.assertEqual(seen["n"], 2)


if __name__ == "__main__":
    unittest.main()
