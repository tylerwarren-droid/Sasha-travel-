"""S-75 steps 4–9 · Sasha on WhatsApp for guests, in the sandbox: who wrote decides everything, a venue is never answered,
the model is never called, a yes binds only to its own question, STOP is silence. Offline (the booking routes are faked
at the in-process boundary; the webhook is the real one).

    cd backend && python -m unittest tests.test_guest_whatsapp_s75 -v
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

from booking_signer import guest_whatsapp as GW, inbound_phone as IP
from booking_signer.vault import guard as G
from tests import test_booking_ladder as TBL, test_inbound_phone as TIP   # modules: their tests are not collected twice

SANDBOX = "+14155238886"
GUEST = "+447700900123"
ACCOUNT = "22222222-2222-4222-8222-222222222222"
NOW = datetime(2026, 10, 2, 12, 0, tzinfo=timezone.utc)


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def stand_in_brain(case) -> list:
    """Sasha 253 · item 5 — the ONE brain stood in at wa_agent.agent_turn (every account's WhatsApp reaches it now): what it is
    handed is recorded in case.brain_saw and answered "agent: <it>". For tests of what stays IN FRONT of the brain (products,
    spaces, the handed sentence) — the brain's own behaviour is tested with a scripted model (test_s253_gaps.ScriptedBrain)."""
    from booking_signer import wa_agent as WA
    case.brain_saw = []

    async def brain(ch, body, payload, st, out, now, button_text="", voice_in=False):
        case.brain_saw.append(body or payload)
        out.text(f"agent: {body or payload}")
        return "x"
    p = mock.patch.object(WA, "agent_turn", brain)
    p.start()
    case.addCleanup(p.stop)
    return case.brain_saw


class FakeSender:
    def __init__(self):
        self.sent, self.contents = [], []

    async def quick_reply(self, body, buttons):
        self.contents.append((body, buttons))
        return f"HX{len(self.contents)}"

    async def send(self, frm, to, *, body="", media=None, content_sid=None):
        self.sent.append({"from": frm, "to": to, "body": body, "media": media, "content": content_sid})
        return "sent"


CANDS = [{"place_id": f"p{i}", "name": n, "country": "ES", "rating": r, "rating_count": 200, "distance_m": d, "website": None}
         for i, (n, r, d) in enumerate((("Botavara Chamberí", 4.6, 300), ("A Very Long Restaurant Name In Madrid", 4.8, 900),
                                        ("Casa Lucio", 4.4, 1200), ("Fourth Place", 4.1, 50)))]


class FakeApi:
    def __init__(self):
        self.calls = []
        self.contact = {"name": "Tyler Warren", "mobile_e164": GUEST}
        self.place = {"status": "placed", "say": "I'm on the phone to Botavara Chamberí now."}
        self.cancel_post = {"status": "requested", "say": "I've emailed them to cancel it."}
        self.reservations = [{"id": "t-1", "venue": "Botavara Chamberí", "date": "2026-10-03", "time": "21:00", "party": 2,
                              "status": "confirmed", "status_words": "confirmed by the restaurant", "receipt": None}]

    async def __call__(self, account, method, path, body=None, timeout=90.0):
        self.calls.append((account, method, path, body))
        if path == "/api/booking/venues/find":
            return 200, {"candidates": CANDS, "ranking": {"default": "rated", "orders": {"rated": ["p1", "p0", "p2", "p3"]},
                                                          "picks": {"rated": "p1"}, "count": "4 places found"}}
        if path == "/api/booking/venues/read":
            return 200, {"read_id": "r-1", "venue": "Botavara", "country": "ES", "listing": {"name": "Botavara Chamberí"},
                         "rungs": [{"rung": "phone", "available": True, "fact_index": 2, "value": "+34 91 000"}], "say": "x"}
        if path == "/api/booking/contact":
            return 200, {"contact": self.contact}
        if path == "/api/booking/calls" and method == "POST":
            if body.get("cancels_call_id"):
                return 200, {"call_id": "cancel-call-1", "read_back": {"lines": ["I'll ask them to cancel."], "sha256": "c" * 64}}
            return 200, {"call_id": "call-12345678", "read_back": {"lines": ["Hola, quería reservar…"], "sha256": "a" * 64},
                         "sentence": "Book Botavara Chamberí for 2, Saturday 3 October at 21:00, under Warren?"}
        if path.endswith("/place"):
            return 200, self.place
        if path == "/api/booking/reservations":
            return 200, {"reservations": self.reservations}
        m = re.fullmatch(r"/api/booking/reservations/(t-\d)/cancel", path)
        if m and method == "GET":
            r = next(x for x in self.reservations if x["id"] == m[1])
            return 200, {"route": "email", "venue": r["venue"], "call_id": None,
                         "read_back": {"lines": ["I'll email them to cancel."], "sha256": "e" * 64},
                         "sentence": f"Cancel {r['venue']}, Saturday 3 October at 21:00, for 2, under Tyler Warren?"}
        if path == "/api/booking/reservations/t-1/cancel" and method == "POST":
            return 200, self.cancel_post
        return 404, {"message": f"no fake for {method} {path}"}


class Base(unittest.TestCase):
    def setUp(self):
        GW._SEEN_SIDS.clear()   # Sasha 206 · each test's MessageSids are its own
        from products import space as _SPC   # Sasha 256 · each test starts with no space set (the one record's process copy)
        _SPC._SPACE.clear()
        self.addCleanup(_SPC._SPACE.clear)
        asyncio.set_event_loop(asyncio.new_event_loop())
        self.env = mock.patch.dict(os.environ, {"SASHA_GUEST_WHATSAPP_TO": SANDBOX, "SASHA_EMAILS": "", "SASHA_WEB_URL": "https://sasha.test"})
        self.env.start()
        self.gw_saved = (GW.STORE, GW.SENDER, GW.api, GW.NOW, GW._spawn)
        GW.STORE, GW.SENDER, GW.api = GW.MemoryGuestStore(), FakeSender(), FakeApi()
        self.spawned = []
        GW._spawn = lambda coro: (self.spawned.append(coro.__name__), coro.close())   # watchers are tested on their own
        self.now = NOW
        GW.NOW = lambda: self.now
        self.model = mock.patch("app.services.llm.client.messages.create", side_effect=AssertionError("the model was called"))
        self.model.start()
        # Sasha 253 · item 5 — every account's WhatsApp reaches the one brain now: its live model is never called from a test
        # either (a test that means the brain scripts it — test_s253_gaps.ScriptedBrain — or stands it in — stand_in_brain)
        from app.services import llm as _LLM
        real = _LLM.client   # sasha.turn takes client.with_options(…): a copy — kept to this guarded client
        self.stream = [mock.patch("app.services.llm.client.messages.stream", side_effect=AssertionError("the live model was called")),
                       mock.patch.object(real, "with_options", lambda **k: real)]
        for g in self.stream:
            g.start()

    def tearDown(self):
        for g in reversed(self.stream):
            g.stop()
        self.model.stop()
        GW.STORE, GW.SENDER, GW.api, GW.NOW, GW._spawn = self.gw_saved
        self.env.stop()

    def link(self, opted_out=None):
        run(GW.STORE.link({"account_id": ACCOUNT, "wa_id_sha256": GW.wa_key(GUEST), "number_e164": GUEST, "linked_at": NOW,
                           "consent_at": NOW, "consent_wording_version": "v2", "consent_text_sha256": GW.consent()["sha256"],
                           "opted_out_at": opted_out}))
        return run(GW.STORE.channel_for(GW.wa_key(GUEST)))

    def say(self, body, payload="", text=""):
        ch = run(GW.STORE.channel_for(GW.wa_key(GUEST)))
        return run(GW.turn(ch, SANDBOX, {"From": f"whatsapp:{GUEST}", "To": f"whatsapp:{SANDBOX}", "Body": body,
                                         "ButtonPayload": payload, "ButtonText": text}))

    def bodies(self):
        return [s["body"] for s in GW.SENDER.sent]

    def api_paths(self):
        return [c[2] for c in GW.api.calls]


class Webhook(Base):
    """Through the real webhook: who wrote, on which number."""

    def setUp(self):
        super().setUp()
        TIP.InboundPhone.setUp(self)

    def tearDown(self):
        TIP.InboundPhone.tearDown(self)
        super().tearDown()

    def wa(self, sid, sender, body, to):
        form = {"MessageSid": sid, "From": f"whatsapp:{sender}", "To": f"whatsapp:{to}", "Body": body}
        return self.c.post("/api/booking/twilio/sms", data=form, headers={"X-Twilio-Signature": TIP.sign("sms", form)})

    def test_on_sashas_own_number_a_venue_is_filed_exactly_as_before_and_never_answered(self):
        r = self.wa("SM1", TIP.SITE_NUMBER, "Confirmado: mesa para 4 personas el jueves 8 de octubre a las 20:00.", "+447915914215")
        self.assertTrue(r.text.endswith("<Response></Response>"))
        self.assertEqual(IP.STORE.rows["SM1"]["trip_item_id"], "t-site")
        self.assertEqual(GW.SENDER.sent, [])

    def test_on_the_guest_number_a_venue_still_takes_the_venue_path(self):
        r = self.wa("SM2", TIP.SITE_NUMBER, "Confirmado", SANDBOX)
        self.assertTrue(r.text.endswith("<Response></Response>"))
        self.assertIn("SM2", IP.STORE.rows)

    def test_an_unknown_sender_gets_one_sentence_and_only_their_hash_is_kept(self):
        r = self.wa("SM3", GUEST, "hello?", SANDBOX)
        self.assertIn("link this number once at https://sasha.test/you", r.text)   # Sasha 253 · the one short /you line
        self.assertNotIn("SM3", IP.STORE.rows)                                    # not filed as a venue's message
        self.assertNotIn(GUEST, json.dumps(GW.STORE.state, default=str))          # never the digits
        self.assertNotIn("hello", json.dumps(GW.STORE.state, default=str))        # nor the words
        self.assertFalse(self.wa("SM4", GUEST, "anyone?", SANDBOX).text.count("<Message>"))   # not again within ten minutes

    # Sasha 269 (CR 100 §E/§F) · MOVED: a link is VERIFIED by AgAPI (users.confirm_whatsapp, Sasha-signed, from that number) before
    # anything is sent to it — a used, stale or wrong code, or too many tries, now sends NOTHING (was "didn't work" / "Too many tries")
    def test_a_link_code_works_once_and_expires(self):
        c = GW.consent()
        seen = []

        async def confirm(account, wa_id, message_id, text, t=None, nonce=None):
            seen.append((account, wa_id, message_id, text))
            return {"ok": True, "state": "verified", "number": "+" + wa_id}
        run(GW.STORE.put_code({"code": "123456", "account_id": ACCOUNT, "consent_at": NOW,
                               "consent_wording_version": "v2", "consent_text_sha256": c["sha256"], "created_at": NOW}))
        with mock.patch("agapi.venue_submit.confirm_whatsapp", confirm):
            self.assertIn("Linked.", self.wa("SM5", GUEST, "Kanoe link 123456", SANDBOX).text)   # AgAPI's text
            self.assertEqual(seen, [(ACCOUNT, GUEST, "SM5", "Kanoe link 123456")])
            ch = run(GW.STORE.channel_for(GW.wa_key(GUEST)))
            self.assertEqual((ch["account_id"], ch["consent_wording_version"]), (ACCOUNT, "v2"))
            other = "+447700900999"
            self.assertNotIn("<Message>", self.wa("SM6", other, "LINK 123456", SANDBOX).text)       # used: once only — nothing sent
            run(GW.STORE.put_code({"code": "654321", "account_id": ACCOUNT, "consent_at": NOW, "consent_wording_version": "v2",
                                   "consent_text_sha256": c["sha256"], "created_at": NOW - timedelta(minutes=11)}))
            self.assertNotIn("<Message>", self.wa("SM7", other, "LINK 654321", SANDBOX).text)       # ten minutes, then gone
        self.assertEqual(len(seen), 1)

    def test_not_verified_by_agapi_links_nothing_and_sends_nothing(self):
        run(GW.STORE.put_code({"code": "222222", "account_id": ACCOUNT, "consent_at": NOW, "consent_wording_version": "v2",
                               "consent_text_sha256": GW.consent()["sha256"], "created_at": NOW}))
        with mock.patch("agapi.venue_submit.confirm_whatsapp",
                        mock.AsyncMock(return_value={"ok": False, "error": {"code": "approval_untrusted_origin"}})):
            self.assertNotIn("<Message>", self.wa("SM9", GUEST, "Kanoe link 222222", SANDBOX).text)
        self.assertIsNone(run(GW.STORE.channel_for(GW.wa_key(GUEST))))
        self.assertEqual(GW.SENDER.sent, [])

    def test_link_tries_are_limited(self):
        for i in range(6):
            self.assertNotIn("<Message>", self.wa(f"SMx{i}", GUEST, "LINK 000000", SANDBOX).text)   # nothing sent, ever
        st = run(GW.STORE.get_state(GW.wa_key(GUEST)))
        self.assertEqual(len(st["link_tries"]), 5)                                               # counted, then refused

    def test_a_linked_guest_is_answered_in_the_background_not_in_the_webhook(self):
        self.link()
        r = self.wa("SM8", GUEST, "dinner for 2 in Chamberí on Saturday at 9", SANDBOX)
        self.assertTrue(r.text.endswith("<Response></Response>"))
        self.assertEqual(self.spawned, ["_turn"])
        self.assertNotIn("SM8", IP.STORE.rows)


class Turns(Base):
    def setUp(self):
        super().setUp()
        self.link()
        run(GW.STORE.put_state(GW.wa_key(GUEST), {"history": [], "pending": None, "last_inbound_at": NOW, "link_tries": []}))

    def test_stop_is_said_once_then_silence_and_start_resumes(self):
        self.say("STOP")
        self.assertEqual(self.bodies(), [GW.STOPPED])
        self.say("dinner for 2 in Chamberí on Saturday at 9")
        self.assertEqual(self.bodies(), [GW.STOPPED])                              # nothing at all
        self.assertEqual(GW.api.calls, [])
        self.say("START")
        self.assertEqual(self.bodies()[-1], GW.STARTED)

    def test_a_password_is_never_kept(self):
        self.say("my Mercadona password is hunter2!")
        self.assertEqual(self.bodies(), [G.SECRET_REPLY])
        self.assertNotIn("hunter2", json.dumps(GW.STORE.state, default=str))

    def test_outside_twenty_four_hours_nothing_is_sent(self):
        ch = run(GW.STORE.channel_for(GW.wa_key(GUEST)))
        self.assertEqual(run(GW.deliver(ch, SANDBOX, GW.Out().text("hi"), NOW - timedelta(hours=25))), ["not sent: outside the 24-hour window"])
        self.assertEqual(GW.SENDER.sent, [])

    def test_sasha109_what_is_a_cancel(self):
        cases = {"Please cancel": "", "No Please Cancel Yatri": "Yatri", "cancela": "", "anula la reserva de Yatri": "Yatri",
                 "cancel my booking at Botavara please": "Botavara", "don't cancel it": None, "dinner for 2 tomorrow": None}
        for msg, want in cases.items():
            self.assertEqual(GW.cancel_intent(msg), want, msg)

    def test_sasha117_the_dinner_and_the_day_are_not_the_venues_name(self):
        cases = {"cancel the dinner at Hanakura": "Hanakura", "cancel my Hanakura booking": "Hanakura",
                 "Cancel the Hanakura dinner.": "Hanakura", "cancel lunch at Botavara tomorrow": "Botavara",
                 "cancela la cena en Hanakura": "Hanakura", "anula mi reserva de Hanakura": "Hanakura",
                 "Cancel the Retiro dinner.": "Retiro", "cancel my dinner": ""}
        for msg, want in cases.items():
            self.assertEqual(GW.cancel_intent(msg), want, msg)


class Progress(Base):
    def test_one_message_per_state_never_two(self):
        ch = self.link()
        run(GW.STORE.put_state(GW.wa_key(GUEST), {"history": [], "pending": None, "last_inbound_at": NOW, "link_tries": []}))
        seq = iter([(200, {"status": "placed"}), (200, {"status": "placed"}),
                    (200, {"status": "answered", "outcome": "yes", "say": "Booked: Botavara confirmed it.", "venue_words": "Sí, perfecto."})])

        async def fake(account, method, path, body=None, timeout=90.0):
            return next(seq)
        with mock.patch.object(GW, "WATCH_CALL", (0, 5)), mock.patch.object(GW, "api", fake):
            run(GW.watch_call(ch, SANDBOX, ACCOUNT, "call-1", "Botavara", "book"))
        self.assertEqual(self.bodies()[:2], ["✅ Booked: Botavara.", "Their words: “Sí, perfecto.”"])
        self.assertEqual(len([b for b in self.bodies() if b.startswith("✅")]), 1)

    def test_sasha108_the_confirmation_result_is_pushed_from_where_it_is_recorded(self):
        """The confirmation call may run at 19:40, hours after anyone watched: its result is sent when it is recorded."""
        self.link()
        run(GW.STORE.put_state(GW.wa_key(GUEST), {"history": [], "pending": None, "last_inbound_at": NOW, "link_tries": []}))
        call = {"account_id": ACCOUNT, "brief": {"date": "2026-10-03", "time": "21:00", "party": 2, "venue_name": "Indian dinner in Chamberí, Madrid"}}

        class R:
            state, outcome, venue_words = "not_reached", None, None

        async def name(c):
            return "Restaurante Yatri"
        with mock.patch.object(GW, "venue_display", name):
            run(GW.push_confirmation_result(call, R, "scheduled for 19:40"))
            R.state, R.outcome, R.venue_words = "answered", "yes", "Sí, apuntado: sábado, dos, Warren."
            run(GW.push_confirmation_result(call, R, None))
        self.assertEqual(self.bodies(), [
            "⚠ Not confirmed yet: Restaurante Yatri didn't pick up.",
            "I'll call Restaurante Yatri once more at 19:40 — your yes covers it.",
            "✅ Booked: Restaurante Yatri, Saturday 3 October at 21:00, 2 people.",
            "Their words: “Sí, apuntado: sábado, dos, Warren.”"])
        self.assertNotIn("Indian dinner", " ".join(self.bodies()))

    def test_sasha108_an_unclear_call_is_followed_by_its_confirmation_call_in_plain_words(self):
        """2 Oct, live: Yatri said "Sí, sí" and hung up before the recap. Plain status lines, the VENUE's name, never the
        search words ("Indian dinner in Chamberí"), never "closing recap" / "who pressed it"."""
        ch = self.link()
        run(GW.STORE.put_state(GW.wa_key(GUEST), {"history": [], "pending": None, "last_inbound_at": NOW, "link_tries": []}))
        seq = {"call-1": iter([(200, {"status": "placed"}),
                                (200, {"status": "answered", "outcome": "unclear", "venue_words": "Hola, muy buenas. / Hola. / Sí, sí. / Ok.",
                                       "say": "Not confirmed with Indian dinner in Chamberí, Madrid: closing recap…", "confirmation_call_id": "call-2"})]),
               "call-2": iter([(200, {"status": "answered", "outcome": "yes", "venue_words": "Sí, sábado a las nueve, dos, Warren. Correcto."})])}

        async def fake(account, method, path, body=None, timeout=90.0):
            return next(seq[path.rsplit("/", 1)[1]])
        with mock.patch.object(GW, "WATCH_CALL", (0, 5)), mock.patch.object(GW, "api", fake):
            run(GW.watch_call(ch, SANDBOX, ACCOUNT, "call-1", "Restaurante Yatri", "book", "Saturday 3 October at 21:00, 2 people"))
        self.assertEqual(self.bodies(), [
            "⚠ Not confirmed yet: Restaurante Yatri didn't clearly confirm it.",
            "Their words: “Hola, muy buenas. / Hola. / Sí, sí. / Ok.”",
            "I'm calling Restaurante Yatri back once now to confirm it — I'll tell you here."])
        joined = " ".join(self.bodies())
        for jargon in ("Indian dinner", "recap", "pressed", "Bland"):
            self.assertNotIn(jargon, joined)


@unittest.skipUnless(TBL.PG_URL, "BOOKING_TEST_DATABASE_URL is not set — the Postgres half did NOT run")
class OnPostgresStore(unittest.TestCase):
    """sql/020 + 034 as written: a code once, a link replacing the account's old one, STOP, the state round trip (with last_to),
    one turn per MessageSid in guest_inbound_sids."""

    @classmethod
    def setUpClass(cls):
        TBL.OnPostgres.setUpClass.__func__(cls)
        import asyncpg
        import pathlib

        async def apply():
            c = await asyncpg.connect(TBL.PG_URL)
            try:
                sql = (pathlib.Path(__file__).resolve().parents[1] / "booking_signer" / "sql" / "020_guest_channels.sql").read_text()
                await c.execute("drop table if exists guest_channels, guest_link_codes, guest_wa_state, guest_inbound_sids")
                await c.execute(sql[sql.index("begin;"):sql.index("-- VERIFY")])
                # a plain Postgres has no Supabase roles; 034 revokes from them by name (CR found it on a real Postgres)
                for role in ("anon", "authenticated"):
                    await c.execute(f"do $$ begin if not exists (select 1 from pg_roles where rolname = '{role}') then "
                                    f"create role {role} nologin; end if; end $$")
                sql034 = (pathlib.Path(__file__).resolve().parents[1] / "booking_signer" / "sql" / "034_guest_wa_last_to_and_sids.sql").read_text()
                await c.execute(sql034[sql034.index("begin;"):sql034.index("commit;") + len("commit;")])
            finally:
                await c.close()
        asyncio.run(apply())

    def test_the_store(self):
        from booking_signer.store import PostgresStore
        asyncio.set_event_loop(asyncio.new_event_loop())
        base = PostgresStore(TBL.PG_URL)
        st = GW.PostgresGuestStore(base)
        acct = TBL.FOUNDER_ACCOUNT
        c = GW.consent()

        async def go():
            try:
                row = {"code": "111111", "account_id": acct, "consent_at": NOW, "consent_wording_version": "v2",
                       "consent_text_sha256": c["sha256"], "created_at": NOW}
                self.assertTrue(await st.put_code(row))
                self.assertFalse(await st.put_code(row))                                   # one code, one row
                self.assertIsNone(await st.take_code("111111", NOW + timedelta(minutes=11)))   # expired
                got = await st.take_code("111111", NOW + timedelta(minutes=1))
                self.assertEqual(got["account_id"], acct)
                self.assertIsNone(await st.take_code("111111", NOW + timedelta(minutes=2)))   # used
                link = {"account_id": acct, "wa_id_sha256": GW.wa_key(GUEST), "number_e164": GUEST, "linked_at": NOW,
                        "consent_at": NOW, "consent_wording_version": "v2", "consent_text_sha256": c["sha256"]}
                await st.link(link)
                await st.link({**link, "wa_id_sha256": GW.wa_key("+447700900999"), "number_e164": "+447700900999"})
                self.assertIsNone(await st.channel_for(GW.wa_key(GUEST)))                 # one WhatsApp per account
                self.assertEqual((await st.channel_of_account(acct))["number_e164"], "+447700900999")
                await st.set_opted_out(GW.wa_key("+447700900999"), NOW)
                self.assertEqual((await st.channel_for(GW.wa_key("+447700900999")))["opted_out_at"], NOW)
                state = {"history": [{"role": "user", "content": "dinner"}], "pending": {"kind": "cards", "nonce": "ab"},
                         "last_inbound_at": NOW, "link_tries": ["2026-10-02T12:00:00+00:00"]}
                # Sasha 206/207 (R1) · the number the guest last wrote to is kept (034)
                await st.put_state("a" * 64, {**state, "last_to": "+14155238886"})
                self.assertEqual(await st.get_state("a" * 64), {**state, "last_to": "+14155238886"})
                await st.put_state("a" * 64, {**state, "last_to": None})            # a later save without it never erases it
                self.assertEqual((await st.get_state("a" * 64))["last_to"], "+14155238886")
                # Sasha 207 (R2) · one turn per MessageSid, in guest_inbound_sids — across processes, not in memory
                old = GW.STORE
                GW.STORE = st
                try:
                    sid = "SM" + "c" * 32
                    self.assertTrue(await GW.first_time(sid))
                    GW._SEEN_SIDS.clear()                                         # a restart: memory is gone, the table is not
                    self.assertFalse(await GW.first_time(sid))
                    self.assertTrue(await GW.first_time("SM" + "d" * 32))
                finally:
                    GW.STORE = old
                self.assertEqual((await st.unlink(acct))["account_id"], acct)
                self.assertIsNone(await st.channel_of_account(acct))
            finally:
                await base.close()
        asyncio.get_event_loop().run_until_complete(go())


if __name__ == "__main__":
    unittest.main()
