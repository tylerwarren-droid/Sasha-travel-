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
import sys
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

from booking_signer import guest_whatsapp as GW, inbound_phone as IP, places_terms as PT
from booking_signer.vault import guard as G
from tests import test_booking_ladder as TBL, test_inbound_phone as TIP   # modules: their tests are not collected twice

SANDBOX = "+14155238886"
GUEST = "+447700900123"
ACCOUNT = "22222222-2222-4222-8222-222222222222"
NOW = datetime(2026, 10, 2, 12, 0, tzinfo=timezone.utc)


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


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

    def tearDown(self):
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
        self.assertIn("link your account first", r.text)
        self.assertNotIn("SM3", IP.STORE.rows)                                    # not filed as a venue's message
        self.assertNotIn(GUEST, json.dumps(GW.STORE.state, default=str))          # never the digits
        self.assertNotIn("hello", json.dumps(GW.STORE.state, default=str))        # nor the words
        self.assertFalse(self.wa("SM4", GUEST, "anyone?", SANDBOX).text.count("<Message>"))   # not again within ten minutes

    def test_a_link_code_works_once_and_expires(self):
        c = GW.consent()
        run(GW.STORE.put_code({"code": "123456", "account_id": ACCOUNT, "consent_at": NOW,
                               "consent_wording_version": "v2", "consent_text_sha256": c["sha256"], "created_at": NOW}))
        self.assertIn("Linked.", self.wa("SM5", GUEST, "LINK 123456", SANDBOX).text)
        ch = run(GW.STORE.channel_for(GW.wa_key(GUEST)))
        self.assertEqual((ch["account_id"], ch["consent_wording_version"]), (ACCOUNT, "v2"))
        other = "+447700900999"
        self.assertIn("didn't work", self.wa("SM6", other, "LINK 123456", SANDBOX).text)            # used: once only
        run(GW.STORE.put_code({"code": "654321", "account_id": ACCOUNT, "consent_at": NOW, "consent_wording_version": "v2",
                               "consent_text_sha256": c["sha256"], "created_at": NOW - timedelta(minutes=11)}))
        self.assertIn("didn't work", self.wa("SM7", other, "LINK 654321", SANDBOX).text)            # ten minutes, then gone

    def test_link_tries_are_limited(self):
        for i in range(5):
            self.assertIn("didn't work", self.wa(f"SMx{i}", GUEST, "LINK 000000", SANDBOX).text)
        self.assertIn("Too many tries", self.wa("SMx5", GUEST, "LINK 000000", SANDBOX).text)

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

    def test_anything_but_booking_gets_the_fixed_sentence_and_no_model(self):
        self.say("write me a poem about Madrid")
        self.assertEqual(self.bodies(), [GW.OUT_OF_SCOPE.format(web=GW.web_url())])
        self.assertEqual(GW.api.calls, [])

    def test_a_spoken_style_request_shows_three_cards_and_one_question(self):
        self.say("Book a luxury dinner for two in Chamberí on Saturday at nine.")
        find = GW.api.calls[0][3]
        self.assertEqual((find["where"], find["country"], find["open_at"]), ("Chamberí, Madrid", "ES", "2026-10-03T21:00"))
        medias = [s for s in GW.SENDER.sent if s["content"] is None][1:]
        self.assertEqual(len(medias), 3)
        self.assertTrue(medias[0]["body"].startswith("Sasha's pick · A Very Long Restaurant"))
        body, buttons = GW.SENDER.contents[0]
        self.assertEqual(body, "Which one?")
        self.assertTrue(all(len(GW.title(t)) <= 20 for t, _ in buttons))   # Sasha 117 · 25 failed live (63013)
        self.assertEqual(len(buttons), 3)

    def test_sasha117_the_rehearsal_books_our_test_venue_never_a_real_one(self):
        """The dress rehearsal (calls off): the third card is our test venue, on the founder's account only."""
        from booking_signer.form_rung import test_venue_url
        with mock.patch.dict(os.environ, {"SASHA_REHEARSAL": "1", "FOUNDER_ACCOUNT_ID": ACCOUNT}):
            self.say("dinner for 2 in Chamberí on Saturday at 9")
            _, buttons = GW.SENDER.contents[-1]
            self.assertEqual([t for t, _ in buttons][2], "Sasha Test Venue")
            self.assertIn("Rehearsal · Sasha Test Venue — ours, not a real restaurant: booking it contacts no one", self.bodies())
            self.say("Sasha Test Venue", payload=buttons[2][1])
        read = next(c for c in GW.api.calls if c[2] == "/api/booking/venues/read")[3]
        self.assertEqual(read, {"name": "Sasha Test Venue", "city": "Chamberí, Madrid", "country": "ES", "website": test_venue_url()})
        self.assertNotIn("place_id", read)                                   # never looked up on Google
        GW.SENDER.contents.clear()
        with mock.patch.dict(os.environ, {"SASHA_REHEARSAL": "", "FOUNDER_ACCOUNT_ID": ACCOUNT}):
            self.say("dinner for 2 in Chamberí on Saturday at 9")
        self.assertNotIn("Sasha Test Venue", [t for t, _ in GW.SENDER.contents[-1][1]])   # off unless asked for

    def test_sasha117_a_form_gets_the_accounts_own_email_and_a_refusal_says_why(self):
        """Live, 2 Oct: the test venue's form needs an email; WhatsApp sent only the mobile → "I can't book … right now"."""
        from booking_signer import ladder_routes as LR, ladder_store as LS
        saved = LR.LADDER_STORE
        LR.LADDER_STORE = LS.MemoryLadderStore()
        LR.LADDER_STORE.account_emails = {ACCOUNT: "guest@example.com"}
        api = GW.api

        async def fake(account, method, path, body=None, timeout=90.0):
            if path == "/api/booking/venues/read":
                return 200, {"read_id": "r-1", "venue": "Sasha Test Venue", "country": "ES", "listing": None, "say": "x",
                             "rungs": [{"rung": "form", "available": True, "fact_index": 1, "value": "https://x/form"}]}
            if path == "/api/booking/forms":
                fake.forms.append(body)
                if not body["reservation"]["who"]["contact"].get("email"):
                    return 422, {"rule": "form_email_missing", "message": "the form needs your email address — which one should they have?"}
                return 200, {"form_id": "form-1234", "read_back": {"lines": ["I'll send the booking form:", "· Email: guest@example.com"],
                                                                     "sha256": "f" * 64}}
            if path == "/api/booking/forms/form-1234/send":   # the live answer of 2 Oct: status "sent", the verdict in reading
                return 200, {"status": "sent", "reading": {"result": "confirmed"}, "booking_reference": "TV-FE41E1",
                             "their_page": "Reserva confirmada Confirmado: mesa para 2 personas… Localizador: TV-FE41E1"}
            return await api(account, method, path, body, timeout)
        fake.forms = []
        GW.api = fake
        try:
            self.pick_first()
            self.assertEqual(fake.forms[-1]["reservation"]["who"]["contact"], {"mobile_e164": GUEST, "email": "guest@example.com"})
            self.assertEqual(GW.SENDER.contents[-1][1][0][0], "Yes, book it")
            self.assertIn("Exactly what I'll send:\n• I'll send the booking form:\n• Email: guest@example.com", self.bodies())   # one bullet
            self.say("Yes, book it", payload=GW.SENDER.contents[-1][1][0][1])
            self.assertIn("✅ Booked: A Very Long Restaurant Name In Madrid, Saturday 3 October at 21:00, 2 people. Their reference: TV-FE41E1.",
                          self.bodies())                                   # was "⚠ Not confirmed yet" over a confirmed booking
            LR.LADDER_STORE.account_emails = {}
            with mock.patch.dict(os.environ, {"SASHA_FOUNDER_EMAIL": ""}):
                self.pick_first()
            self.assertEqual(self.bodies()[-1], "I can't book A Very Long Restaurant Name In Madrid from here right now — the form needs your email address — "
                                                "which one should they have? Nothing was sent.")
        finally:
            GW.api, LR.LADDER_STORE = api, saved

    def pick_first(self):
        self.say("dinner for 2 in Chamberí on Saturday at 9")
        _, buttons = GW.SENDER.contents[-1]
        self.say("A Very Long…", payload=buttons[0][1])

    def test_a_pick_reads_the_place_and_asks_one_sentence_bound_to_its_read_back(self):
        self.pick_first()
        body, buttons = GW.SENDER.contents[-1]
        self.assertEqual(body, "Book Botavara Chamberí for 2, Saturday 3 October at 21:00, under Warren?")
        self.assertEqual(buttons[0], ("Yes, book it", "yes:call-123:" + "a" * 16))
        self.assertIn("Exactly what I'll say:\n• Hola, quería reservar…", self.bodies())
        prep = next(c for c in GW.api.calls if c[2] == "/api/booking/calls")[3]
        self.assertEqual(prep["reservation"]["who"], {"name": "Tyler Warren", "contact": {"mobile_e164": GUEST}})
        self.assertEqual(prep["fact_index"], 2)

    def test_a_typed_vale_binds_to_the_newest_question_with_its_words(self):
        self.pick_first()
        self.say("vale")
        place = next(c for c in GW.api.calls if c[2].endswith("/place"))
        self.assertEqual(place[2], "/api/booking/calls/call-12345678/place")
        self.assertEqual(place[3], {"read_back_sha256": "a" * 64, "approval": {"how": "whatsapp_text", "said": "vale"}})

    def test_the_button_yes_and_a_stale_button(self):
        self.pick_first()
        self.say("Yes, book it", payload="yes:call-123:" + "b" * 16, text="Yes, book it")        # an older card's hash
        self.assertFalse(any(c[2].endswith("/place") for c in GW.api.calls))
        self.assertIn("earlier question", self.bodies()[-1])

    def test_a_yes_after_fifteen_minutes_places_nothing(self):
        self.pick_first()
        self.now = NOW + timedelta(minutes=16)
        self.say("yes")
        self.assertFalse(any(c[2].endswith("/place") for c in GW.api.calls))
        self.assertIn("expired", self.bodies()[-1])

    def test_no_contact_saved_means_no_booking(self):
        GW.api.contact = None
        self.pick_first()
        self.assertFalse(any(c[2] == "/api/booking/calls" for c in GW.api.calls))
        self.assertIn("name and mobile", self.bodies()[-1])

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

    def test_cancel_by_email_says_cancelling_never_cancelled_until_their_words(self):
        self.say("cancel Botavara")
        body, buttons = GW.SENDER.contents[-1]
        self.assertEqual(body, "Cancel Botavara Chamberí, Saturday 3 October at 21:00, for 2, under Tyler Warren?")
        self.say("Yes, cancel", payload=buttons[0][1], text="Yes, cancel")
        post = next(c for c in GW.api.calls if c[1] == "POST" and c[2].endswith("/cancel"))
        self.assertEqual(post[3]["approval"], {"how": "whatsapp_button", "said": "Yes, cancel"})
        self.assertTrue(self.bodies()[-1].startswith("Cancelling with Botavara Chamberí now."))
        self.assertFalse(any("has cancelled" in b for b in self.bodies()))
        self.assertEqual(self.spawned, ["watch_cancel"])                            # watching for their written words

    def test_sasha104_the_founders_live_message_shows_cards(self):
        """2 Oct, live in the sandbox: this exact message got the out-of-scope sentence."""
        self.say("Dinner for 2 on Saturday at 2100 in Chamberi. Something luxurious and romantic")
        find = GW.api.calls[0][3]
        self.assertEqual((find["what"], find["where"], find["open_at"]), ("luxurious and romantic Dinner", "Chamberí, Madrid", "2026-10-03T21:00"))
        self.assertEqual(GW.SENDER.contents[-1][0], "Which one?")

    def seed_live_state(self):
        """The founder's guest_wa_state as stored on sasha-prod at 11:37 UTC, 2 Oct (cards pending, find.what "Dinner")."""
        run(GW.STORE.put_state(GW.wa_key(GUEST), {
            "history": [{"role": "user", "content": "Dinner for 2 on Saturday at 2100 in Chamberi. Something luxurious and romantic"},
                        {"role": "assistant", "content": GW.OUT_OF_SCOPE.format(web=GW.web_url())}],
            "pending": {"kind": "cards", "at": NOW.isoformat(), "nonce": "a1b2c3",
                        "find": {"what": "Dinner", "where": "Chamberí, Madrid", "country": "ES", "open_at": "2026-10-03T21:00"},
                        "draft": {"when": {"mode": "at", "at": "2026-10-03T21:00"}, "how_many": {"count": 2, "unit": "people"}},
                        "cards": [{"name": "DUM DUM | Chamberí", "country": "ES", "place_id": "ChIJUeGquRkpQg0R7oY8og3UkYE"},
                                  {"name": "La Taberna de Paula", "country": "ES", "place_id": "ChIJi0x5BFwoQg0RLv9wFoCDvMo"},
                                  {"name": "IN Ristolab Chamberí | Restaurante italiano y Carnes Madrid", "country": "ES",
                                   "place_id": "ChIJX1WWcgApQg0R7rNhhOsakC8"}]},
            "last_inbound_at": NOW, "link_tries": []}))

    def finds(self):
        return [c[3] for c in GW.api.calls if c[2] == "/api/booking/venues/find"]

    def test_sasha104_the_founders_refinements_replayed_against_the_stored_state(self):
        """2 Oct, live: "How about Indian food?" and "So, actually my wife likes Indian food…" both got "Which one?"."""
        self.seed_live_state()
        self.say("How about Indian food?")
        self.say("So, actually my wife likes Indian food. Can you find me an Indian food spot? Luxury please")
        self.say("Indian food, luxury please")
        f = self.finds()
        self.assertEqual([x["what"] for x in f], ["Indian dinner", "luxury Indian dinner", "luxury Indian dinner"])
        for x in f:   # the area, the day and the time are kept
            self.assertEqual((x["where"], x["country"], x["open_at"]), ("Chamberí, Madrid", "ES", "2026-10-03T21:00"))
        st = run(GW.STORE.get_state(GW.wa_key(GUEST)))
        self.assertEqual(st["pending"]["draft"]["how_many"], {"count": 2, "unit": "people"})   # the party too
        self.assertEqual(st["pending"]["kind"], "cards")
        self.assertNotIn("Which one? Tap a name", " ".join(self.bodies()))

    def test_sasha104_luxury_puts_three_euro_signs_first(self):
        self.seed_live_state()
        priced = [{**c, "price_level": p} for c, p in zip(CANDS, (2, 1, 3, 4))]
        with mock.patch.object(sys.modules[__name__], "CANDS", priced):
            self.say("Indian food, luxury please")
        medias = [s["body"] for s in GW.SENDER.sent if s["content"] is None][1:]
        self.assertTrue(medias[0].startswith("Sasha's pick · Casa Lucio"), medias)   # €€€ (rated before €€€€ in the order)
        self.assertTrue(medias[1].startswith("Fourth Place"), medias)
        self.assertIn("€€€ and up first", self.bodies()[0])

    def test_sasha104_a_plain_yes_while_choosing_asks_again(self):
        self.seed_live_state()
        self.say("ok thanks")
        self.assertEqual(GW.api.calls, [])
        self.assertTrue(self.bodies()[-1].startswith("Which one?"))

    def test_sasha104_a_new_area_while_choosing_moves_the_search(self):
        self.seed_live_state()
        self.say("how about Indian in Malasaña")
        f = self.finds()[0]
        self.assertEqual((f["what"], f["where"], f["open_at"]), ("Indian dinner", "Malasaña, Madrid", "2026-10-03T21:00"))

    def test_sasha108_calling_names_the_venue_not_the_search(self):
        GW.api.place = {"status": "placed", "say": "Calling Indian dinner in Chamberí, Madrid now."}
        self.pick_first()
        self.say("vale")
        self.assertIn("📞 Calling Botavara Chamberí now.", self.bodies())
        self.assertNotIn("Indian dinner", " ".join(self.bodies()))
        self.assertEqual(self.spawned, ["watch_call"])

    def test_sasha104_unsure_asks_one_question(self):
        self.say("can you sort out Saturday night for 2?")
        self.assertEqual(self.bodies(), [GW.ASK_ONE])

    def test_sasha104_a_voice_note_is_asked_to_be_typed(self):
        ch = run(GW.STORE.channel_for(GW.wa_key(GUEST)))
        run(GW.turn(ch, SANDBOX, {"From": f"whatsapp:{GUEST}", "Body": "", "NumMedia": "1", "MediaContentType0": "audio/ogg"}))
        self.assertIn("voice notes", self.bodies()[-1])
        self.assertEqual(GW.api.calls, [])

    YATRI = {"id": "t-2", "venue": "Restaurante Yatri", "date": "2026-10-03", "time": "21:00", "party": 2, "status": "unclear",
             "status_words": "not confirmed yet", "receipt": None}

    def test_sasha109_the_founders_cancels(self):
        """2 Oct, live: "Please cancel" and "No Please Cancel Yatri" both got "Shall I book that?"."""
        GW.api.reservations = [self.YATRI]
        self.say("Please cancel")                                     # no name: his one active booking
        self.assertEqual(GW.SENDER.contents[-1][0], "Cancel Restaurante Yatri, Saturday 3 October at 21:00, for 2, under Tyler Warren?")
        self.say("No")                                                 # the No answers the question; nothing is cancelled
        self.assertEqual(self.bodies()[-1], "OK — nothing was cancelled.")
        self.say("No Please Cancel Yatri")
        body, buttons = GW.SENDER.contents[-1]
        self.assertTrue(body.startswith("Cancel Restaurante Yatri"))
        self.assertEqual(buttons[0][0], "Yes, cancel")
        self.assertNotIn(GW.ASK_ONE, self.bodies())
        self.assertFalse(any(c[1] == "POST" and c[2].endswith("/cancel") for c in GW.api.calls))   # nothing until the yes

    def test_sasha109_several_bookings_get_a_numbered_list(self):
        GW.api.reservations = [GW.api.reservations[0], self.YATRI]
        self.say("cancela")
        self.assertTrue(self.bodies()[-1].startswith("Which one should I cancel?\n1. Botavara Chamberí"))
        self.say("2")
        self.assertTrue(GW.SENDER.contents[-1][0].startswith("Cancel Restaurante Yatri"))

    def test_sasha109_what_is_a_cancel(self):
        cases = {"Please cancel": "", "No Please Cancel Yatri": "Yatri", "cancela": "", "anula la reserva de Yatri": "Yatri",
                 "cancel my booking at Botavara please": "Botavara", "don't cancel it": None, "dinner for 2 tomorrow": None}
        for msg, want in cases.items():
            self.assertEqual(GW.cancel_intent(msg), want, msg)

    def test_receipts(self):
        self.say("my bookings")
        self.assertIn("• Botavara Chamberí — Saturday 3 October at 21:00, 2 — confirmed by the restaurant", self.bodies()[-1])


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
    """sql/020 as written: a code once, a link replacing the account's old one, STOP, the state round trip."""

    @classmethod
    def setUpClass(cls):
        TBL.OnPostgres.setUpClass.__func__(cls)
        import asyncpg
        import pathlib

        async def apply():
            c = await asyncpg.connect(TBL.PG_URL)
            try:
                sql = (pathlib.Path(__file__).resolve().parents[1] / "booking_signer" / "sql" / "020_guest_channels.sql").read_text()
                await c.execute("drop table if exists guest_channels, guest_link_codes, guest_wa_state")
                await c.execute(sql[sql.index("begin;"):sql.index("-- VERIFY")])
            finally:
                await c.close()
        asyncio.run(apply())

    def test_the_store(self):
        from booking_signer.store import PostgresStore
        asyncio.set_event_loop(asyncio.new_event_loop())
        base = PostgresStore(TBL.PG_URL)
        st = GW.PostgresGuestStore(base)
        acct = TBL.DEMO_ACCOUNT_ID
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
                await st.put_state("a" * 64, state)
                self.assertEqual(await st.get_state("a" * 64), state)
                self.assertEqual((await st.unlink(acct))["account_id"], acct)
                self.assertIsNone(await st.channel_of_account(acct))
            finally:
                await base.close()
        asyncio.get_event_loop().run_until_complete(go())


if __name__ == "__main__":
    unittest.main()
