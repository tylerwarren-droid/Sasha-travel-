"""Sasha 270 · T52 — A BOOKING LINK THE PERSON HANDS OVER (CR 101, mailbox row 1000) + "they take reservations" + THE PLATFORM-READ LOCK
(incident row 1002). Tyler, 15 Oct (Mandrake Greek Street Food: "Reserve a table" on its listing goes to a form; Sasha said "no online
booking form"). ONE source of truth: AgAPI venue.profile — Sasha passes what she has and READS its answer. Offline.

  A  a link they send (chat, a voice transcript, WhatsApp) → venue.profile link {url} (+ place.place_id) → channels[].owner:
     kanoe → the booking rules (handle it) → venue.prepare_booking on THAT link → the read-back → ONE yes; the person → their link + its say
  B  reservable.say said as fact ("They take reservations."); no own form → voice.NO_LINK — never "no online booking form"
  C  every line through voice.py, short ("OK, I'm on it.")
  ✗  no second copy on the one path: no form, no CAPTCHA of Sasha's own reading (old S1, parity off: unchanged)
  🔒 booking_signer.platform_read refuses anywhere but Railway's DEPLOYED server — loudly; `railway run` is not Railway

    cd backend && python -m unittest tests.test_s270 -v
"""
from __future__ import annotations

import asyncio
import os
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

from agapi import booking_decide as BD, v0 as API, venue_submit as VS, venue_truth as VT, venues as VN
from app.agent import voice as V
from booking_signer import guest_receipt as GR, platform_read as PR

ACCT = "00000000-0000-4000-8000-000000000270"
FORM = "https://docs.google.com/forms/d/e/scratch-open/viewform"
SIGN_IN = "https://docs.google.com/forms/d/e/scratch-sign-in/viewform"
FORK = "https://www.thefork.es/restaurante/mandrake-r1"
RESERVABLE = {"value": True, "source": "their Google listing (Places API: reservable)", "say": "They take reservations."}
run = asyncio.run


def profile_answer(kind: str, owner: str, url: str, say: str = "") -> dict:
    """venue.profile's answer (CR 101's shape) for a listing with no website + the person's link."""
    return {"ok": True, "result": {"venue_id": "ven_1", "facts": {}, "booking": {"rung": 2 if kind == "own_form" else None},
                                   "reservable": RESERVABLE, "listing": {"place_id": "fixture_place_no_site", "read": True},
                                   "channels": [{"kind": kind, "source": "person", "url": url, "host": "docs.google.com", "owner": owner,
                                                 "say": say or f"Their booking form ({'docs.google.com'}) …"}]}}


class TheOneClassifier(unittest.TestCase):
    """A · venue.profile link {url}: Sasha passes what she has and reads channels[] — she never loads the link herself."""

    def test_gate_link_profile_passes_link_place_and_reads_the_persons_channel(self):
        sent = []

        async def call(op, body):
            sent.append((op, body))
            return profile_answer("own_form", "kanoe", FORM)
        with mock.patch.object(VT, "CALL", call):
            got = run(VT.link_profile({"place_id": "fixture_place_no_site", "name": "Mandrake"}, FORM))
        self.assertEqual(sent, [("venue.profile", {"link": {"url": FORM}, "place": {"place_id": "fixture_place_no_site", "name": "Mandrake"}})])
        self.assertEqual((got["channel"]["kind"], got["channel"]["owner"], got["channel"]["source"]), ("own_form", "kanoe", "person"))
        self.assertEqual(got["reservable"]["say"], "They take reservations.")

    def test_the_engine_not_answering_is_said_never_guessed(self):
        async def call(op, body):
            return {"ok": False, "error": {"code": "upstream_unreachable", "message": "down"}}
        with mock.patch.object(VT, "CALL", call):
            got = run(VT.link_profile({"name": "Mandrake"}, FORM))
        self.assertFalse(got["ok"])

    def test_the_link_is_theirs_from_the_tool_or_their_own_words_on_the_one_path_only(self):
        s2 = type("C", (), {"surface": "s2", "user_said": f"here you go: {FORM}."})()
        self.assertEqual(VN._link_of(s2, {}), FORM)                                         # their words (punctuation trimmed)
        self.assertEqual(VN._link_of(s2, {"link": SIGN_IN}), SIGN_IN)                       # the tool's, first
        self.assertIsNone(VN._link_of(type("C", (), {"surface": "s2", "user_said": "Friday at 8"})(), {}))
        with mock.patch("app.agent.sasha.s1_parity", lambda: False):
            self.assertIsNone(VN._link_of(type("C", (), {"surface": "s1", "user_said": FORM})(), {"link": FORM}))   # old S1: no link
        self.assertIn("link", VN.with_under({"input_schema": {"properties": {}, "required": []}})["input_schema"]["properties"])

    def test_prepare_carries_the_link(self):
        seen = []

        async def call(account, op, body, approval=None):
            seen.append(body)
            return {"ok": True, "result": {"prepared_id": "vpr_" + "a" * 32}}
        with mock.patch.object(VS, "_call", call):
            run(VS.prepare(ACCT, {"name": "Mandrake", "place_id": "p1"}, {"name": "Alex"}, "2026-10-20", "21:00", 2, link=FORM))
            run(VS.prepare(ACCT, {"name": "Mandrake"}, {"name": "Alex"}, "2026-10-20", "21:00", 2))
        self.assertEqual(seen[0]["link"], {"url": FORM})
        self.assertNotIn("link", seen[1])


class PersonLink(unittest.TestCase):
    """A · hold_venue with the link: owner kanoe → the ONE ladder (read-back, one yes); owner the person → their link, its say."""

    def setUp(self):
        VN._HELD.pop(ACCT, None)
        self.addCleanup(VN._HELD.pop, ACCT, None)
        self.prepared, self.ruled = [], []

        async def via(ctx, a, rd, res, at, now, d, card, r6=False, link=None):
            self.prepared.append(link)
            VN._HELD[ACCT] = {"out": {}}
            return {"status": "awaiting_yes", "route": "agapi", "ask": V.READ_BACK_ASK.format(venue="Mandrake"), "read_back": ["…"]}

        async def rules(ctx, a, rd, res, at, eng, card, route, now=None):
            self.ruled.append((eng, route))
            return {"action": self.action, "say": "sent", "takeover": {"link": None, "say": "You can take it over at any point."},
                    "say_text": "Sent.", "channels": [eng]}
        self.action = "fill_form_zero_touch"
        for p in (mock.patch.object(VN, "_via_agapi", via), mock.patch.object(VN, "rules_for", rules),
                  mock.patch.object(VN, "_API", lambda: type("G", (), {"plain_venue": staticmethod(lambda v: v)}))):
            p.start()
            self.addCleanup(p.stop)

    def go(self, kind, owner, url, say=""):
        ctx = type("C", (), {"account": ACCT, "surface": "s2", "user_said": url})()
        rd = {"venue": "Mandrake", "place_id": "fixture_place_no_site", "rungs": {}}
        res = {"how_many": {"count": 2}}

        async def call(op, body):
            return profile_answer(kind, owner, url, say)
        with mock.patch.object(VT, "CALL", call), mock.patch.object(VN, "_nights", lambda c, a: None), \
                mock.patch.object(VN, "_open_slot", lambda c, a: None), mock.patch.object(VN, "one_path", lambda c: True):
            return run(VN._person_link(ctx, {"name": "Mandrake"}, rd, res, "2026-10-20T21:00", datetime.now(timezone.utc), None, url))

    def test_gate_our_form_is_the_read_back_and_one_yes_said_short(self):
        out = self.go("own_form", "kanoe", FORM)
        self.assertEqual(self.prepared, [FORM])                                                   # prepared on THAT link
        self.assertEqual(self.ruled[0], ({"kind": "form", "url": FORM, "from": "person"}, "form"))   # the rules decide (handle it)
        self.assertEqual(out["status"], "awaiting_yes")
        self.assertTrue(out["ask"].startswith(V.LINK_ON_IT + " "))                                # "OK, I'm on it."
        self.assertEqual(V.LINK_ON_IT, "OK, I'm on it.")

    def test_gate_sign_in_and_platform_are_handed_over_with_what_they_are(self):
        out = self.go("needs_sign_in", "the person", SIGN_IN, "Their booking form (docs.google.com) needs you to sign in, so it's yours to fill.")
        self.assertEqual((out["status"], out["page_url"], out["booked"]), ("page_link", SIGN_IN, False))
        self.assertEqual(out["say"], V.LINK_THEIRS["needs_sign_in"])
        fork = self.go("platform", "the person", FORK, "They book through www.thefork.es. Here's their page — you finish it there.")
        self.assertEqual((fork["page_url"], fork["say"]), (FORK, "Here's their page — you finish it there."))
        self.assertNotIn("thefork", fork["say"].lower())                                          # her voice never names it
        self.assertEqual(self.prepared, [])                                                       # never prepared, never sent

    def test_the_rules_saying_no_hands_the_link_over_in_their_words(self):
        self.action = "prepared_link"
        out = self.go("own_form", "kanoe", FORM)
        self.assertEqual((out["status"], out["page_url"]), ("page_link", FORM))
        self.assertEqual(self.prepared, [])

    def test_a_new_link_is_never_the_same_held_booking(self):
        VN._HELD[ACCT] = {"out": {"x": 1}, "at": datetime.now(timezone.utc) - timedelta(minutes=1), "rung": "agapi", "link_handed": FORM}
        ctx = type("C", (), {"account": ACCT, "surface": "s2", "user_said": SIGN_IN})()
        with mock.patch.object(VN, "one_path", lambda c: True):
            self.assertEqual(VN._link_of(ctx, {}), SIGN_IN)
            self.assertNotIn(VN._link_of(ctx, {}), (None, VN._HELD[ACCT]["link_handed"]))


class TheirListingSays(unittest.TestCase):
    """B · reservable.say said as fact; no own form → voice.NO_LINK, never "no online booking form"."""

    def test_gate_reservable_is_the_engines_words(self):
        VT._CACHE["place:fixture_place_no_site"] = {"at": __import__("time").time(), "profile": VT._from_profile(
            {"facts": {}, "booking": {"rung": None}, "reservable": RESERVABLE, "channels": []})}
        self.addCleanup(VT._CACHE.pop, "place:fixture_place_no_site", None)
        said = VT.reservable_say({"place_id": "fixture_place_no_site"})
        self.assertEqual(said, "They take reservations.")
        self.assertEqual(V.no_link_line(said), "I can't see their booking link from here — if you can, send it to me and I'll fill it in. "
                                               "They take reservations.")
        self.assertIsNone(VT.reservable_say({"place_id": "unknown"}))

    def test_a_listing_with_no_website_is_read_by_the_engine_on_the_one_path_only(self):
        sent = []

        async def call(op, body):
            sent.append(body)
            return {"ok": True, "result": {"facts": {}, "booking": {"rung": None}, "reservable": RESERVABLE, "channels": []}}
        card = {"place_id": "fixture_place_no_site_2", "name": "Mandrake"}
        self.addCleanup(VT._CACHE.pop, "place:fixture_place_no_site_2", None)
        with mock.patch.object(VT, "CALL", call):
            self.assertIsNone(run(VN.engine_channel(card)))                                  # a search card / old S1: not read
            self.assertEqual(sent, [])
            run(VN.engine_channel(card, listing=True))
        self.assertEqual(sent, [{"place": {"place_id": "fixture_place_no_site_2", "name": "Mandrake"}}])
        self.assertEqual(VT.reservable_say(card), "They take reservations.")

    def test_no_way_found_says_send_me_the_link_never_no_form(self):
        for kind, line in V.LINK_THEIRS.items():
            self.assertNotIn("no booking form", line.lower())
            self.assertNotIn("no online booking form", line.lower())
            self.assertNotIn("(", line)                                                          # never a host
        self.assertEqual(V.link_line({"kind": "own_form", "say": "Their own booking form (docs.google.com): I can fill it in."}),
                         "Their own booking form: I can fill it in.")
        self.assertIn("call hold_venue with that booking and `link`", V.RULES)


class NoSecondCopy(unittest.TestCase):
    """✗ On the one path, whether a place has a FORM (or a CAPTCHA) is the venue engine's — never Sasha's own reading."""

    RD = {"rungs": {"form": {"value": ""}, "own_page": {"value": "https://casagate.es/reservas"}, "email": {"value": "r@casagate.es"},
                    "link": {"value": "https://widget.example/book"}, "phone": {"value": "+34910000000"}},
          "facts": [{"kind": "challenge", "source_kind": "site"}]}

    def test_gate_sashas_form_and_captcha_reading_is_off_the_one_path(self):
        kinds = [c["kind"] for c in BD.channels_of(None, self.RD, None, one_path=True)]
        self.assertNotIn("form", kinds)
        self.assertEqual(kinds, ["email", "phone"])
        old = BD.channels_of(None, self.RD, None)                                                # old S1: as it was
        self.assertTrue(any(c["kind"] == "form" and c.get("captcha") for c in old))
        self.assertEqual(VN.read_channel(self.RD, None, one_path=True)["kind"], "email")
        self.assertEqual(VN.read_channel(self.RD, None)["kind"], "form")
        fork = {"rungs": {"link": {"value": "https://www.thefork.es/r/x"}}}
        self.assertEqual([c["kind"] for c in BD.channels_of(None, fork, None, one_path=True)], ["platform"])   # a platform: handed over

    def test_the_captcha_is_the_engines(self):
        eng = {"kind": "form", "url": "https://casagate.es/reservas", "engine_captcha": True}
        self.assertTrue(BD.channels_of(eng, {"facts": []}, None, one_path=True)[0].get("captcha"))
        no = {"kind": "form", "url": "https://casagate.es/reservas", "engine_captcha": False}
        self.assertFalse(BD.channels_of(no, self.RD, None, one_path=True)[0].get("captcha"))     # Sasha's "challenge" fact: ignored
        self.assertTrue(BD.channels_of(no, self.RD, None)[0].get("captcha"))                     # old S1: as it was
        p = VT._from_profile({"facts": {}, "booking": {"rung": 2, "channel": "their own booking form", "evidence": "https://x.es/r"},
                              "form": {"captcha": True}})
        self.assertTrue(p["channels"][0]["engine_captcha"])


class PlatformReadLock(unittest.TestCase):
    """🔒 row 1002: platform_read refuses anywhere but Railway's deployed server — loudly. `railway run` sets RAILWAY_ENVIRONMENT but no
    deployment id, so it is refused too."""

    def env(self, **kv):
        keys = ("RAILWAY_ENVIRONMENT", "RAILWAY_DEPLOYMENT_ID", "RAILWAY_REPLICA_ID")
        return mock.patch.dict(os.environ, {**{k: "" for k in keys}, **kv})

    def test_gate_railway_run_is_not_railway(self):
        with self.env():
            self.assertFalse(PR.on_railway())
        with self.env(RAILWAY_ENVIRONMENT="production"):                                          # what `railway run` injects
            self.assertFalse(PR.on_railway())
        with self.env(RAILWAY_ENVIRONMENT="production", RAILWAY_DEPLOYMENT_ID="dep_1"):           # a deployment
            self.assertTrue(PR.on_railway())
        with self.env(RAILWAY_ENVIRONMENT="production", RAILWAY_REPLICA_ID="rep_1"):
            self.assertTrue(PR.on_railway())

    def test_gate_a_local_read_refuses_loudly_before_any_request(self):
        opened = []
        import httpx
        with self.env(RAILWAY_ENVIRONMENT="production"), mock.patch.object(httpx, "AsyncClient", lambda *a, **k: opened.append(1)), \
                self.assertLogs("booking_signer.platform_read", "ERROR"):
            PR._ROBOTS.clear()
            with self.assertRaises(PR.NotOnRailway):
                run(PR.HTTP("GET", "https://www.fresha.com/robots.txt", {}))
            with self.assertRaises(PR.NotOnRailway):                                              # never "robots.txt unreadable"
                run(PR.robots(None, "https://www.treatwell.es/establecimiento/x/"))
            with self.assertRaises(PR.NotOnRailway):                                              # never a quiet "no offer"
                run(PR.offer(None, "https://www.treatwell.es/establecimiento/x/", "a massage"))
        self.assertEqual(opened, [])
        self.assertNotIn("treatwell.es", PR._ROBOTS)

    def test_the_check_route_refuses_and_health_reports_it(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from booking_signer import ladder_routes as LR
        app = FastAPI()
        app.include_router(LR.router, prefix="/api/booking")
        with self.env(), mock.patch.object(LR, "PLATFORM_CHECK_ACCOUNTS", {ACCT}), mock.patch.object(LR, "account_for", lambda r: ACCT), \
                mock.patch.object(PR, "robots", mock.AsyncMock(side_effect=AssertionError("never reached"))):
            r = TestClient(app).get("/api/booking/platform/check", params={"url": "https://www.fresha.com/a/x"})
        self.assertEqual((r.status_code, r.json().get("rule")), (503, "not_on_railway"))
        with self.env():
            self.assertEqual(PR.status(), {"reads_allowed_here": False})


if __name__ == "__main__":
    unittest.main()
