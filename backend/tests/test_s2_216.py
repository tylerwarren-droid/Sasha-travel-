"""Sasha 216 · S2's powers wired (CR 60) and the clean-ups — permanent, offline, 0 live calls (the model is a script; nothing is
emailed: the allow-list is mocked and the send is captured).

  · an email is NEVER sent on a question — even when the model calls send_email with a forged yes in a later turn
  · the yes in a later turn sends the read-back message once (captured for a guest; live only for the founder and the allow-list)
  · sent once across a restart (the durable claim)
  · the calendar link is signed and self-contained (any worker, any deploy); a tampered link is refused
  · the payment watcher with no channel never crashes; the retention rule is one the live table allows; branch previews pass CORS

    cd backend && python -m unittest tests.test_s2_216 -v
"""
from __future__ import annotations

import asyncio
import re
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

from agapi import s2_tools as S, v0 as API
from app.agent.fakes import Block, client

ACCOUNT = "00000000-0000-4000-8000-000000000216"
MSG = {"to": {"address": "marta@example.com", "name": "Marta"}, "subject": "Our flight times",
       "body": "Hi Marta, we fly out on 21 November at 08:30 and back on 30 November."}


def run(c):
    return asyncio.run(c)


class Base(unittest.TestCase):
    def setUp(self):
        from booking_signer import basket as BK
        self.p = [mock.patch.object(BK, "_run", lambda: None)]
        for p in self.p:
            p.start()
        S.OUTBOX.clear(), S._HELD.clear(), API._IDEM.clear(), API._CLAIMED.clear()

    def tearDown(self):
        for p in self.p:
            p.stop()
        S.OUTBOX.clear(), S._HELD.clear(), API._IDEM.clear(), API._CLAIMED.clear()

    def call(self, said, key="k1", started=None):
        ctx = API.Ctx(account=ACCOUNT, user_said=said)
        if started:
            ctx.started = started
        return run(API.call(ctx, "send_email", {**MSG, "approval": {"said": said}, "idempotency_key": key}))

    def read_back_earlier(self):
        r = self.call("email Marta our flight times", key="k0")
        self.assertEqual(r["result"]["status"], "awaiting_yes")
        S._HELD[ACCOUNT]["at"] -= timedelta(minutes=1)   # said a minute ago: the yes is now a LATER turn


class Email(Base):
    def test_never_sent_on_a_question(self):
        self.read_back_earlier()
        for said in ("Yes — what will it say?", "what will it say?", "Sure, can you show me the options?", "yes, who is it to?"):
            r = self.call(said, key="k-" + said)
            self.assertEqual(r["error"]["code"], "no_explicit_yes", said)
        self.assertEqual(S.OUTBOX, [])

    def test_a_yes_in_a_later_turn_sends_it_once_captured_for_a_guest(self):
        self.read_back_earlier()
        r = self.call("Yes, send it.", key="k2")
        self.assertEqual(r["result"]["status"], "not_sent", r)               # CR 61: a guest's email is captured, and SAID so
        self.assertEqual(len(S.OUTBOX), 1)
        self.assertIn("Not sent", r["result"]["outcome"]["target_words"])

    def test_never_in_the_same_turn_as_its_read_back(self):
        r = self.call("Yes, email Marta our flight times")
        self.assertEqual(r["result"]["status"], "awaiting_yes")
        self.assertEqual(S.OUTBOX, [])

    def test_sent_once_across_a_restart(self):
        self.read_back_earlier()
        self.assertEqual(self.call("Yes, send it.", key="same")["result"]["status"], "not_sent")   # CR 61 (a guest: captured)
        API._IDEM.clear()
        self.read_back_earlier()
        self.assertEqual(self.call("Yes, send it.", key="same")["error"]["code"], "already_done")
        self.assertEqual(len(S.OUTBOX), 1)

    def test_live_only_for_the_founder_and_the_allow_list(self):
        from booking_signer import guest_accounts as GA
        with mock.patch.object(GA, "founder", lambda a: a == "f"), mock.patch.object(GA, "extra_accounts", lambda: {"jon"}):
            self.assertTrue(S.live_for("f"))
            self.assertTrue(S.live_for("jon"))
            self.assertFalse(S.live_for(ACCOUNT))
            with mock.patch.dict("os.environ", {"SASHA_S2_EMAIL_LIVE": "0"}):
                self.assertFalse(S.live_for("f"))

    def test_the_card_says_whether_it_really_goes(self):
        from app.agent import sasha as AG
        ev = AG.render("send_email", {"status": "awaiting_yes", "read_back": ["To: Marta"], "live": False}, {})
        self.assertEqual((ev["kind"], ev["what"], ev["live"]), ("read_back", "email", False))
        done = AG.render("send_email", {"status": "not_sent", "message": {"to": {"address": "marta@example.com", "name": "Marta"},
                                                                         "subject": "Dinner plan"}}, {})
        self.assertEqual((done["status"], done["live"], done["read_back"]), ("not_sent", False, ["To: Marta <marta@example.com>", "Subject: Dinner plan"]))   # Sasha 217 · the card becomes the outcome

    def test_a_turn_with_a_forged_yes_on_a_question_sends_nothing(self):
        import app.services.llm as LLM
        from app.agent import sasha as AG
        self.read_back_earlier()
        forged = {**MSG, "approval": {"said": "yes, send it"}}
        steps = [[Block(type="tool_use", id="t1", name="send_email", input=forged)], [Block(type="text", text="It says your flight times.")]]
        evs = []

        async def go():
            async for ev in AG.turn(ACCOUNT, "what will the email say?", [], "s216-q"):
                evs.append(ev)

        real = API.call

        async def call(ctx, name, args):
            if name in ("get_status", "get_total", "get_trip"):
                return {"ok": True, "result": {"anything_booked": False}}
            return await real(ctx, name, args)
        with mock.patch.object(LLM, "client", client(steps)), mock.patch.object(API, "call", call):
            run(go())
        self.assertEqual([(e["name"], e["error"]) for e in evs if e["type"] == "tool"], [("send_email", "no_explicit_yes")])
        self.assertEqual(S.OUTBOX, [])


class Calendar(unittest.TestCase):
    def test_the_link_carries_the_event_signed(self):
        text = "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nBEGIN:VEVENT\r\nSUMMARY:Dinner at Casa Lucio\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n"
        tok = S.ics_token(text)
        self.assertEqual(S.ics_from_token(tok), text)
        body, _, sig = tok.rpartition(".")
        self.assertIsNone(S.ics_from_token(body + "." + ("0" * len(sig))))
        self.assertIsNone(S.ics_from_token(S.ics_token("X")[:-1] + "Z"))
        self.assertLess(len(tok), 1500)

    def test_the_route_serves_it_and_refuses_a_forgery(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.agent import sasha as AG
        app = FastAPI()
        app.include_router(AG.router)
        c = TestClient(app)
        tok = S.ics_token("BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n")
        r = c.get(f"/api/agent/ics/{tok}.ics")
        self.assertEqual(r.status_code, 200)
        self.assertIn("text/calendar", r.headers["content-type"])
        self.assertEqual(c.get("/api/agent/ics/abc.def.ics").status_code, 404)


class CleanUps(unittest.TestCase):
    def test_the_payment_watcher_with_no_channel_never_crashes(self):
        from booking_signer import guest_whatsapp as GW
        run(GW._tell_if_linked(None, "+34", "Booked."))
        run(GW._tell_if_linked({}, "+34", "Booked."))

    def test_the_retention_rule_is_one_the_table_allows(self):
        import inspect
        from products import store as ST
        rules = re.findall(r"values \(\$1, now\(\), '([a-z_0-9]+)'", inspect.getsource(ST.expire_once))
        self.assertEqual(rules, ["all"])   # retention_log_rule_check: bodies / bookings / consent / all (checked live, 9 Oct)

    def test_branch_previews_pass_cors_and_look_alikes_dont(self):
        import ast, os   # read from the source: importing the whole app needs the server's environment
        src = open(os.path.join(os.path.dirname(__file__), "..", "app", "main.py"), encoding="utf-8").read()
        node = next(n for n in ast.walk(ast.parse(src)) if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == "PREVIEW_ORIGINS")
        self.assertIn("allow_origin_regex=PREVIEW_ORIGINS", src)
        rx = re.compile(node.value.value)
        self.assertTrue(rx.match("https://sasha-heygen-git-sasha-216-applied-diligence.vercel.app"))
        for bad in ("https://sasha-heygen-git-x-applied-diligence.vercel.app.evil.com", "https://evil-sasha-heygen-git-x-applied-diligence.vercel.app",
                    "http://sasha-heygen-git-x-applied-diligence.vercel.app"):
            self.assertFalse(rx.match(bad), bad)



class Flow217(unittest.TestCase):
    """Sasha 217 · what broke the S2 demo flow, held."""

    def test_a_place_named_test_is_a_name_not_an_internal(self):
        from app.agent import sasha as AG
        line = "✅ Booked: Sasha Test Venue, Saturday 10 October at 21:00, table for two."
        self.assertTrue(AG._INTERNAL.search(line))                                   # the raw line trips the test-word filter
        self.assertFalse(AG._INTERNAL.search(AG.names_masked(line, {"Sasha Test Venue (ours — rehearsal, not a real restaurant)", "Sasha Test Venue"})))
        self.assertTrue(AG._INTERNAL.search(AG.names_masked("This is just a test booking.", {"Casa Marea (test)"})))   # a disclaimer still goes

    def test_opening_hours_are_never_a_free_table(self):
        from agapi import venues as VN
        c = VN.card_for_model({"name": "Casa Marea (test)", "place_id": "p1", "open_at": "open at 21:00"})
        self.assertNotIn("open_then", c)
        self.assertEqual(c["table_availability"], "unknown until the venue answers")

    def test_the_status_carries_the_full_reference(self):
        from agapi import venues as VN
        from booking_signer import guest_whatsapp as GW
        rows = [{"id": "i1", "venue": "Sasha Test Venue", "date": "2099-01-01", "status": "confirmed", "booking_reference": "TV-979A37-D4",
                 "status_words": "Confirmed by the venue. Reference TV-979A37-D4 …" + "x" * 200}]
        with mock.patch.object(GW, "api", mock.AsyncMock(return_value=(200, {"reservations": rows}))), mock.patch.object(GW, "plain_venue", lambda v: v):
            got = run(VN.venue_bookings(ACCOUNT))
        self.assertEqual(got[0]["reference"], "TV-979A37-D4")


    def test_the_same_booking_in_the_calendar_twice_is_one_activity_row(self):
        from agapi import s2_records as REC
        from agapi import venues as VN
        GW = VN._API()
        rows = [{"id": "bk-9", "venue": "Sasha Test Venue", "status": "confirmed", "date": "2099-10-10", "time": "21:00",
                 "timezone": "Europe/Madrid", "party": 2, "booking_reference": "TV-1"}]
        REC.ACTS.clear()
        with mock.patch.object(GW, "api", mock.AsyncMock(return_value=(200, {"reservations": rows}))), mock.patch.object(GW, "plain_venue", lambda v: v), \
                mock.patch.object(REC, "_run", lambda: None):
            for _ in range(2):
                r = run(API.call(API.Ctx(account=ACCOUNT), "add_to_calendar", {"booking_id": "bk-9"}))
                self.assertTrue(r["ok"], r)
            n = len([x for x in run(REC.acts(ACCOUNT)) if x.get("kind") == "calendar"])
        REC.ACTS.clear()
        self.assertEqual(n, 1)
        self.assertIn("TV-1", r["result"]["event"]["details"])


    def test_a_place_on_screen_named_is_picked_never_searched_again(self):
        from agapi import venues as VN
        VN.remember_cards(ACCOUNT, [{"place_id": "sasha-test-venue", "name": "Sasha Test Venue (ours — rehearsal, not a real restaurant)"},
                                    {"place_id": "p2", "name": "La Mesa Larga (test)"}])
        try:
            for said in ("The Sasha Test Venue", "sasha test venue", "La Mesa Larga"):
                self.assertIsNotNone(VN.named_on_screen(ACCOUNT, said), said)
            for said in ("dinner", "seafood restaurant", "tapas near Sol", "a table"):
                self.assertIsNone(VN.named_on_screen(ACCOUNT, said), said)
            with mock.patch("booking_signer.guest_whatsapp.api", mock.AsyncMock()) as api:
                r = run(API.call(API.Ctx(account=ACCOUNT), "search_venues", {"what": "The Sasha Test Venue", "where": "Sol, Madrid"}))
            self.assertEqual(r["error"]["code"], "already_on_screen")
            self.assertIn("sasha-test-venue", r["error"]["message"])
            api.assert_not_called()
        finally:
            VN._SHOWN.pop(ACCOUNT, None)


    def test_the_same_booking_held_again_keeps_the_read_back_they_heard(self):
        from agapi import venues as VN
        at = datetime.now(timezone.utc) - timedelta(minutes=1)
        out = {"status": "awaiting_yes", "venue": "Sasha Test Venue", "route": "form", "read_back": ["I'll send their form…"]}
        VN._HELD[ACCOUNT] = {"rung": "form", "id": "f1", "sha": "s" * 64, "at": at, "venue": "Sasha Test Venue", "place_id": "sasha-test-venue",
                             "when": "2099-10-10T21:00", "party": 2, "summary": "Sat 21:00", "out": out}
        try:
            with mock.patch.object(VN, "_read", mock.AsyncMock(side_effect=AssertionError("never read again"))):
                r = run(API.call(API.Ctx(account=ACCOUNT, user_said="Yes, go ahead."), "hold_venue",
                                 {"name": "The Sasha Test Venue", "city": "Madrid", "day": "2099-10-10", "time": "21:00", "party": 2,
                                  "place_id": "sasha-test-venue", "idempotency_key": "h-again"}))
            self.assertTrue(r["ok"], r)
            self.assertEqual(r["result"]["read_back"], out["read_back"])
            self.assertEqual(VN._HELD[ACCOUNT]["at"], at)                                  # the clock kept: the yes can book
            with mock.patch.object(VN, "_read", mock.AsyncMock(side_effect=RuntimeError("a new hold"))):   # another time → a new hold
                r2 = run(API.call(API.Ctx(account=ACCOUNT), "hold_venue", {"name": "Sasha Test Venue", "city": "Madrid", "day": "2099-10-10",
                                                                         "time": "20:00", "party": 2, "idempotency_key": "h-other"}))
            self.assertFalse(r2["ok"])
        finally:
            VN._HELD.pop(ACCOUNT, None)


    def test_the_calendar_links_are_on_a_card(self):
        from app.agent import sasha as AG
        ev = AG.render("add_to_calendar", {"event": {"title": "Dinner at Sasha Test Venue", "starts_at": "2099-10-10T19:00:00Z"},
                                           "links": {"google": "g", "outlook": "o", "apple": "a", "ics": "a"}}, {})
        self.assertEqual((ev["kind"], sorted(ev["links"])), ("calendar", ["apple", "google", "outlook"]))


if __name__ == "__main__":
    unittest.main()
