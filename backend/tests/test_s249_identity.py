"""Sasha 249 · ONE IDENTITY (EU 245 step 2; one-truth-spec §1.1–1.3, consistency tests T1–T3). Offline: the keys are made here.

  T1 · one resolver: chat_account() and booking_signer.identity.resolve() give the SAME account for the same request (a
       verified token, the founder's proxied session, the named demo); only "nobody" differs (chat: the demo; booking: None).
  T2 · no demo leak: a bearer token never resolves to the demo id or to 11111111; with FOUNDER_ACCOUNT_ID unset the
       founder's session is REFUSED on both paths (never the demo); there is ONE demo id, defined once.
  T3 · trips belong to the actor: /api/booking/journeys acts for the verified account only — no client-sent id is read —
       and its plans are read `where owner_id = <that account>`.
  + the five founder/test rules and the founder-only routes all decide "is this the founder" in app/services/accounts.py.

    cd backend && python -m unittest tests.test_s249_identity -v
"""
from __future__ import annotations
import tests.founder_fixture  # noqa: F401,E402  (Sasha 249 · the fixtures name the founder; no fallback any more)

import asyncio
import os
import pathlib
import re
import unittest
import uuid
from unittest import mock

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request

from app.services import accounts as AC, chat_account as CA, chat_store
from booking_signer import identity as I, routes
from booking_signer import account as BA
from tests.test_identity import GUEST, JWK, PROJECT, token

BACKEND = pathlib.Path(__file__).resolve().parents[1]
OLD_DEMO = "11111111-1111-4111-8111-111111111111"
FOUNDER = "33333333-3333-4333-8333-333333333249"
KEY = "k-s249"


def req(headers: dict) -> Request:
    return Request({"type": "http", "method": "GET", "path": "/", "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()]})


def run(c):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(c)
    finally:
        loop.close()


class Keys(unittest.TestCase):
    def setUp(self):
        self.env = mock.patch.dict(os.environ, {"SASHA_BOOKING_KEY": KEY, "FOUNDER_ACCOUNT_ID": FOUNDER, "SASHA_SUPABASE_URL": PROJECT,
                                               "SASHA_CALL_SWEEP": "0"})
        self.env.start()

        async def fetch():
            return {"keys": [JWK]}
        self.saved, I.FETCH = I.FETCH, fetch
        I.reset_cache()

    def tearDown(self):
        I.FETCH = self.saved
        I.reset_cache()
        self.env.stop()

    def both(self, headers):
        """(chat_account, identity.resolve) for the same request — each an account, None, or (status, rule) if refused."""
        out = []
        for f in (lambda r: CA.chat_account(r), lambda r: I.resolve(r)):
            try:
                out.append(run(f(req(headers))))
            except HTTPException as e:
                out.append((e.status_code, (e.detail or {}).get("rule")))
        return tuple(out)


class T1OneResolver(Keys):
    def test_the_same_request_is_the_same_account_on_both_paths(self):
        founder = {"x-sasha-session": "founder", "x-sasha-booking-key": KEY}
        self.assertEqual(self.both({"authorization": f"Bearer {token()}"}), (GUEST, GUEST))
        self.assertEqual(self.both(founder), (FOUNDER, FOUNDER))
        self.assertEqual(self.both({"x-sasha-session": "demo"}), (AC.DEMO_ACCOUNT_ID, AC.DEMO_ACCOUNT_ID))
        self.assertEqual(self.both({"x-sasha-session": "anyone"}), ((401, "account_session_unknown"),) * 2)
        self.assertEqual(self.both({"authorization": "Basic abc"}), ((401, "account_token_invalid"),) * 2)
        # nobody: a chat is the demo, a booking route has no account (→ account_required) — the one difference, by argument
        self.assertEqual(self.both({}), (AC.DEMO_ACCOUNT_ID, None))
        self.assertEqual(self.both({"x-sasha-session": "founder"}), (AC.DEMO_ACCOUNT_ID, None))   # the header alone names nobody

    def test_resolve_is_a_thin_wrapper(self):
        seen = []

        async def one(request, anonymous="unset"):
            seen.append(anonymous)
            return "acct"
        with mock.patch.object(CA, "chat_account", one):
            self.assertEqual(run(I.resolve(req({}))), "acct")
        self.assertEqual(seen, [None])

    def test_a_token_wins_over_a_founder_session_on_both_paths(self):
        h = {"authorization": f"Bearer {token()}", "x-sasha-session": "founder", "x-sasha-booking-key": KEY}
        self.assertEqual(self.both(h), (GUEST, GUEST))


class T2NoDemoLeak(Keys):
    def test_a_bearer_token_is_never_the_demo(self):
        a, b = self.both({"authorization": f"Bearer {token()}"})
        for got in (a, b):
            self.assertNotIn(got, (AC.DEMO_ACCOUNT_ID, OLD_DEMO))
            self.assertTrue(AC.signed_in(got))

    def test_an_unset_founder_is_refused_never_the_demo(self):
        founder = {"x-sasha-session": "founder", "x-sasha-booking-key": KEY}
        for unset in ("", "not-a-uuid"):
            with mock.patch.dict(os.environ, {"FOUNDER_ACCOUNT_ID": unset}):
                self.assertIsNone(AC.founder_account())
                self.assertIsNone(I.founder_account())
                self.assertEqual(self.both(founder), ((503, "founder_account_not_configured"),) * 2)
                for who in (None, "", AC.DEMO_ACCOUNT_ID, OLD_DEMO):
                    self.assertFalse(AC.is_founder(who), who)

    def test_an_unset_founder_through_the_gate_is_a_503_never_a_booking_as_the_demo(self):
        app = FastAPI()
        app.include_router(routes.router)
        with mock.patch.dict(os.environ, {"FOUNDER_ACCOUNT_ID": ""}):
            r = TestClient(app).get("/api/booking/reservations", headers={"x-sasha-booking-key": KEY, "x-sasha-session": "founder"})
        self.assertEqual((r.status_code, r.json()["detail"]["rule"]), (503, "founder_account_not_configured"))

    def test_one_demo_id_defined_once(self):
        self.assertIs(chat_store.DEMO_USER_ID, AC.DEMO_ACCOUNT_ID)
        self.assertIs(BA.DEMO_ACCOUNT_ID, AC.DEMO_ACCOUNT_ID)
        self.assertIs(CA.DEMO_ACCOUNT_ID, AC.DEMO_ACCOUNT_ID)
        self.assertFalse(hasattr(CA, "PUBLIC_DEMO_ID"))
        literal = re.compile(re.escape(AC.DEMO_ACCOUNT_ID) + "|" + re.escape(OLD_DEMO))
        where = [str(p.relative_to(BACKEND)) for d in ("app", "agapi", "booking_signer", "products")
                 for p in sorted((BACKEND / d).rglob("*.py")) if literal.search(p.read_text(encoding="utf-8"))]
        self.assertEqual(where, ["app/services/accounts.py"])   # 11111111 nowhere in the code; the demo id only here

    def test_unowned_rows_belong_to_nobody(self):
        legacy = {"user_id": None}
        with mock.patch.object(chat_store, "get_itinerary", mock.AsyncMock(return_value=legacy)), \
             mock.patch.object(chat_store, "get_offer", mock.AsyncMock(return_value=legacy)):
            for who in (AC.DEMO_ACCOUNT_ID, OLD_DEMO, FOUNDER, GUEST):
                self.assertIsNone(run(CA.own_itinerary("it-1", who)), who)
                self.assertIsNone(run(CA.own_offer("of-1", who)), who)
        mine = {"user_id": GUEST}
        with mock.patch.object(chat_store, "get_itinerary", mock.AsyncMock(return_value=mine)):
            self.assertEqual(run(CA.own_itinerary("it-1", GUEST)), mine)
            self.assertIsNone(run(CA.own_itinerary("it-1", FOUNDER)))

    def test_the_demo_has_no_persons_name(self):
        self.assertNotEqual(chat_store.DEMO_USER_NAME, "Jon Peters")


class T3TripsBelongToTheActor(Keys):
    def test_journeys_act_for_the_verified_account_whatever_the_client_sends(self):
        from booking_signer import guest_whatsapp as GW, journeys as JN, paid_watch as PWT
        seen = []

        def note(tag):
            async def f(account, *a, **k):
                seen.append((tag, account))
                return (200, {"reservations": []}) if tag == "api" else ({"journeys": [], "for": account} if tag == "view" else 0)
            return f
        app = FastAPI()
        app.include_router(routes.router)
        other = "44444444-4444-4444-8444-444444444249"
        with mock.patch.object(PWT, "sweep", note("sweep")), mock.patch.object(JN, "file", note("file")), \
             mock.patch.object(GW, "api", note("api")), mock.patch.object(JN, "journeys", note("view")):
            c = TestClient(app, headers={"x-sasha-booking-key": KEY})
            for headers in ({"authorization": f"Bearer {token()}", "x-sasha-account": other, "x-account-id": other},
                            {"x-sasha-session": "founder", "x-sasha-account": other}):
                seen.clear()
                r = c.get(f"/api/booking/journeys?account={other}&account_id={other}&owner_id={other}", headers=headers)
                self.assertEqual(r.status_code, 200, r.text)
                want = GUEST if "authorization" in headers else FOUNDER
                self.assertEqual(r.json()["for"], want)
                self.assertEqual({a for _, a in seen}, {want})

    def test_plans_are_read_by_owner(self):
        from booking_signer import journeys as JN
        got = []

        class Conn:
            async def fetch(self, sql, *args):
                got.append((sql, args))
                return []
        run(JN._plans(Conn(), GUEST))
        sql, args = got[0]
        self.assertIn("owner_id = $1", sql)
        self.assertEqual(args, (uuid.UUID(GUEST),))


class OneFounderDecision(unittest.TestCase):
    """The five founder/test rules keep their own switch; the founder test itself is accounts.is_founder_test."""
    GUESTX = "55555555-5555-4555-8555-555555555249"

    def test_each_rule_keeps_its_behaviour(self):
        from booking_signer import guest_accounts as GA, guest_whatsapp as GW, ladder_routes as LR, switching as SW
        base = {"FOUNDER_ACCOUNT_ID": FOUNDER, "SASHA_DEMO_STANDIN": "", "SASHA_REHEARSAL": "", "SASHA_SWITCHING": "",
                "SASHA_S2_DEMO_ACCOUNTS": ""}
        with mock.patch.dict(os.environ, base):
            self.assertTrue(GA.founder(FOUNDER))
            self.assertTrue(GA.founder(FOUNDER.upper()))
            self.assertFalse(GA.founder(self.GUESTX))
            self.assertFalse(GA.founder(None))
            self.assertFalse(LR.standin(FOUNDER))                                    # off without its flag
            self.assertFalse(GW.rehearsal(FOUNDER))
            self.assertTrue(SW.on(FOUNDER))
            self.assertFalse(SW.on(self.GUESTX))
            self.assertFalse(LR._s2_demo_account(FOUNDER))                           # the founder only if listed (Sasha 232)
        with mock.patch.dict(os.environ, {**base, "SASHA_DEMO_STANDIN": "1", "SASHA_REHEARSAL": "1", "SASHA_SWITCHING": "all",
                                          "SASHA_S2_DEMO_ACCOUNTS": f" {self.GUESTX} "}):
            self.assertTrue(LR.standin(FOUNDER))
            self.assertFalse(LR.standin(self.GUESTX))
            self.assertTrue(GW.rehearsal(FOUNDER))
            self.assertFalse(GW.rehearsal(self.GUESTX))                              # never to a guest (Sasha 175)
            self.assertTrue(SW.on(self.GUESTX))                                      # everyone with SASHA_SWITCHING=all
            self.assertFalse(SW.on(None))
            self.assertTrue(LR._s2_demo_account(self.GUESTX))
            self.assertFalse(LR._s2_demo_account(FOUNDER))
        with mock.patch.dict(os.environ, {**base, "FOUNDER_ACCOUNT_ID": "", "SASHA_DEMO_STANDIN": "1", "SASHA_REHEARSAL": "1"}):
            for rule in (GA.founder, LR.standin, GW.rehearsal, SW.on):
                self.assertFalse(rule(OLD_DEMO), rule.__name__)                      # unset: nobody — never 11111111
                self.assertFalse(rule(AC.DEMO_ACCOUNT_ID), rule.__name__)

    def test_the_founder_decision_is_made_in_one_place(self):
        """Every founder/test rule calls accounts.is_founder_test (or is_founder): one switch flips them all."""
        from booking_signer import guest_accounts as GA, guest_whatsapp as GW, ladder_routes as LR, limits as LM, mailbox as MB, switching as SW
        from booking_signer import handover as HO
        env = {"FOUNDER_ACCOUNT_ID": FOUNDER, "SASHA_DEMO_STANDIN": "1", "SASHA_REHEARSAL": "1", "SASHA_SWITCHING": "",
               "SASHA_CALLS_ACCOUNTS": "", "SASHA_GMAIL_ACCOUNTS": ""}
        rules = (GA.founder, LR.standin, GW.rehearsal, SW.on, LM.exempt, LM.calls_on, MB.invited, HO.founder_override)
        with mock.patch.dict(os.environ, env):
            self.assertTrue(all(r(FOUNDER) for r in rules))
            with mock.patch.object(AC, "founder_account", lambda: None):
                self.assertFalse(any(r(FOUNDER) for r in rules), [r.__name__ for r in rules if r(FOUNDER)])


if __name__ == "__main__":
    unittest.main()
