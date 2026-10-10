"""CR 70 · AgAPI phase 2: Sasha's real providers behind the adapters, on agapi-live only. Every test runs on RECORDED data or fakes —
no test calls Google, Duffel, Stripe, Resend, Twilio or a venue.

  Places   the live adapter = Sasha's own venue_read.find_venues with the real HTTP (here: the recorded replay), the sandbox's exact shape;
           AgAPI's own daily cap (Sasha shares Google's daily Text Search quota); Google's 429 → upstream_rate_limited; stays never
           connected; the smoke check is the free IDs-only search; the live service serves live keys only and reaches only listed hosts.

    python -m unittest agapi_service.tests.test_cr70 -v      (from the repo root)
"""
from __future__ import annotations

import asyncio
import json
from unittest import mock

from agapi_service import adapters as AD, config, providers as PV
from agapi_service import adapters_live as AL
from agapi_service.adapters_live import places as LP
from agapi_service.tests.test_service import Base
from agapi_service import app as A

VENUES = {"what": "restaurant", "where": {"query": "Madrid", "country": "ES"}}


class Recorded:
    """Sasha's recorded Places answers (scripts/places_fake.replay), every request kept."""

    def __init__(self, status=None):
        self.calls, self.status = [], status

    async def __call__(self, method, url, headers=None, json=None, **kw):
        from scripts import places_fake
        self.calls.append({"url": url, "headers": dict(headers or {}), "json": json})
        if self.status:
            return places_fake._R(self.status, {"error": {"code": self.status, "status": "RESOURCE_EXHAUSTED",
                                                          "message": "Quota exceeded for quota metric 'SearchTextRequest per day'"}})
        return await places_fake.replay(method, url, headers=headers, json=json, **kw)


class Live(Base):
    """agapi-live, in-process: LIVE_SERVICE on, the given kinds connected, the real HTTP replaced by recorded data."""
    connected = {"places"}

    def setUp(self):
        super().setUp()
        self.sandbox_answer = self.ok("venues.find_venues", VENUES)                              # the same question, test mode, first
        self.rec = Recorded()
        for p in (mock.patch.object(config, "LIVE_SERVICE", True), mock.patch.object(AD, "CONNECTED_LIVE", set(self.connected)),
                  mock.patch.object(AL, "http", self.rec), mock.patch.object(AL, "STORE", lambda: self.store),
                  mock.patch.dict(AD._LIVE, AL.ADAPTERS)):
            p.start()
            self.addCleanup(p.stop)
        self.live = A.create_key(self.store, self.account, "live", mode="live")


class Places(Live):
    def test_a_live_search_is_sashas_own_code_on_the_real_http_with_the_sandboxs_shape(self):
        got = self.ok("venues.find_venues", VENUES, key=self.live)
        self.assertEqual(len(self.rec.calls), 1)
        c = self.rec.calls[0]
        self.assertEqual(c["url"], "https://places.googleapis.com/v1/places:searchText")
        self.assertIn("places.websiteUri", c["headers"]["X-Goog-FieldMask"])                      # Sasha's own field mask
        self.assertEqual(c["json"]["textQuery"], "restaurant in Madrid, Spain")
        strip = lambda vs: [(v["venue_ref"], v["name"]["text"]) for v in vs]
        self.assertEqual(strip(got["venues"]), strip(self.sandbox_answer["venues"]))             # exactly the sandbox's answer, live
        u = self.store.q("select mode, cost_units from usage_records where operation = 'venues.find_venues' order by at")
        self.assertEqual((u[-1]["mode"], u[-1]["cost_units"]), ("live", 1))

    def test_the_live_service_serves_live_keys_only(self):
        r, b = self.call("venues.find_venues", VENUES, expect="mode_not_available")              # the test key
        self.assertIn("This is AgAPI live", b["error"]["message"])
        self.assertEqual(self.rec.calls, [])

    def test_agapis_own_daily_cap_keeps_sashas_quota_safe(self):
        with mock.patch.object(config, "PLACES_DAILY_CAP", 2):
            self.store.x("create table if not exists provider_calls (provider text not null, kind text not null, at text not null)")
            self.store.x("insert into provider_calls (provider, kind, at) values ('google_places', 'search', '2026-01-01T00:00:00.000000Z')")   # another day
            self.ok("venues.find_venues", VENUES, key=self.live)
            self.ok("venues.find_venues", VENUES, key=self.live)
            r, b = self.call("venues.find_venues", VENUES, key=self.live, expect="upstream_rate_limited")
        self.assertIn("own daily cap for Google Places (2 searches)", b["error"]["message"])
        self.assertEqual(len(self.rec.calls), 2)                                                 # the third never reached Google
        self.assertEqual(LP.calls_today(self.store), 2)

    def test_googles_own_daily_quota_is_a_rate_limit_not_a_refusal(self):
        with mock.patch.object(AL, "http", Recorded(status=429)):
            r, b = self.call("venues.find_venues", VENUES, key=self.live, expect="upstream_rate_limited")
        self.assertTrue(b["error"]["retryable"])

    def test_stays_and_bookings_stay_refused(self):
        r, b = self.call("travel.find_stays", {"city": {"query": "Madrid", "country": "ES"}, "check_in": "2026-11-12", "nights": 1, "guests": 2},
                         key=self.live, expect="mode_not_available")
        self.assertEqual(b["error"]["details"]["provider"], "stays")
        v = self.sandbox_answer["venues"][0]
        r, b = self.call("trip.hold", {"end_user": "usr_" + "0" * 26, "items": [{"kind": "venue", "ref": v["venue_ref"], "at": "2026-11-20T20:30:00+01:00", "party": 2}]},
                         key=self.live, expect="mode_not_available")
        self.assertIn(b["error"]["details"]["provider"], ("flights", "venue_ladder"))
        self.assertEqual(self.rec.calls, [])

    def test_the_smoke_check_spends_nothing_and_returns_no_names(self):
        with mock.patch.dict("os.environ", {"GOOGLE_PLACES_API_KEY": "places-recorded"}):
            out = asyncio.run(AL.ADAPTERS["places"].smoke())
        c = self.rec.calls[-1]
        self.assertEqual((c["headers"]["X-Goog-FieldMask"], c["json"]["maxResultCount"]), ("places.id", 1))   # IDs only: no charge
        self.assertTrue(out["ok"])
        self.assertNotIn("name", json.dumps(out).replace("names", ""))
        self.assertEqual(out["calls_today"], 1)                                                  # counted against AgAPI's cap

    def test_the_signed_smoke_action_only_on_the_live_service(self):
        body = json.dumps({"provider": "places"})
        with mock.patch.dict("os.environ", {"GOOGLE_PLACES_API_KEY": "places-recorded"}):
            r = self.client.post("/admin/smoke", content=body, headers={"AgAPI-Admin-Signature": Base_sign(body)})
        self.assertEqual((r.status_code, r.json()["smoke"]["ok"], r.json()["connected"]), (200, True, True))
        self.assertEqual(self.client.post("/admin/smoke", content=body).status_code, 401)
        with mock.patch.object(config, "LIVE_SERVICE", False):
            r = self.client.post("/admin/smoke", content=body, headers={"AgAPI-Admin-Signature": Base_sign(body)})
        self.assertEqual(r.status_code, 404)
        self.assertEqual(self.client.get("/health").json()["connected"], ["places"])

    def test_the_live_network_reaches_only_the_listed_providers(self):
        import httpx
        PV.block_network()
        seen = []
        tr = httpx.MockTransport(lambda req: (seen.append(req.url.host), httpx.Response(200, json={}))[1])

        async def get(url):
            async with httpx.AsyncClient(transport=tr) as c:
                return await c.get(url)
        with mock.patch.object(PV, "ALLOWED_HOSTS", set(PV.ALLOWED_HOSTS) | config.LIVE_HOSTS):
            asyncio.run(get("https://places.googleapis.com/v1/x"))
            with self.assertRaises(httpx.ConnectError):
                asyncio.run(get("https://www.booking.com/"))
            with self.assertRaises(httpx.ConnectError):
                asyncio.run(get("https://some-venue.example/"))
        self.assertEqual(seen, ["places.googleapis.com"])

    def test_the_sandbox_still_refuses_every_live_key(self):
        with mock.patch.object(config, "LIVE_SERVICE", False), mock.patch.object(AD, "CONNECTED_LIVE", set()):
            r, b = self.call("venues.find_venues", VENUES, key=self.live, expect="mode_not_available")
        self.assertEqual(self.rec.calls, [])



FLIGHTS = {"origin": {"query": "Madrid"}, "destination": {"query": "London"}, "date": "2026-11-12", "passengers": 1}
TRAVELLER = {"title": "ms", "given_name": "Ana", "family_name": "Ruiz", "born_on": "1990-04-02", "gender": "f"}


class Flights(Live):
    """Duffel, live = the sandbox's own flight functions on the real transport (here: Sasha's recorded Duffel TEST answers)."""
    connected = {"places", "flights"}

    def test_a_live_search_has_the_sandboxs_shape(self):
        sb = None
        with mock.patch.object(config, "LIVE_SERVICE", False):
            sb = self.ok("travel.find_flights", FLIGHTS)
        got = self.ok("travel.find_flights", FLIGHTS, key=self.live)
        stable = lambda os_: [(o["flight_numbers"], o["from"], o["to"], o["price"]) for o in os_]   # offer ids are fresh per search
        self.assertEqual(stable(got["offers"]), stable(sb["offers"]))
        self.assertTrue(got["offers"])

    def test_a_flight_hold_needs_flights_only_and_a_venue_hold_still_waits_for_the_ladder(self):
        uid = self.ok("users.register", {"external_ref": "live-1"}, key=self.live)["end_user_id"]    # no destinations: nothing sent
        self.call("users.register", {"external_ref": "live-2", "destinations": [{"channel": "sms", "value": "+15005550006"}]},
                  key=self.live, expect="mode_not_available")                                     # a code would be sent: not yet
        ref = self.ok("travel.find_flights", FLIGHTS, key=self.live)["offers"][0]["offer_ref"]
        h = self.ok("trip.hold", {"end_user": uid, "items": [{"kind": "flight", "ref": ref}], "travellers": [TRAVELLER]}, key=self.live)
        self.assertTrue(h["read_back"]["lines"])
        v = self.sandbox_answer["venues"][0]
        r, b = self.call("trip.hold", {"end_user": uid, "items": [{"kind": "venue", "ref": v["venue_ref"], "at": "2026-11-20T20:30:00+01:00", "party": 2}]},
                         key=self.live, expect="mode_not_available")
        self.assertEqual(b["error"]["details"]["provider"], "venue_ladder")
        # completing it needs payments (not connected yet): refused BEFORE the yes is used
        r, b = self.call("trip.complete", {"hold_id": h["hold_id"]}, key=self.live, expect="mode_not_available")
        self.assertEqual(b["error"]["details"]["provider"], "payments")
        self.assertEqual(self.store.one("select count(*) as n from acts")["n"], 0)

    def test_no_real_money_and_no_pretend_cancel(self):
        ad = AL.ADAPTERS["flights"]
        with mock.patch("booking_signer.travel.token", lambda: "duffel_live_xxx"):
            with self.assertRaises(Exception) as x:
                asyncio.run(ad.order({"offer_ref": "off_x", "_card": {}}, [TRAVELLER], PV.Upstream()))
        self.assertEqual((x.exception.code, x.exception.details["reason"]), ("upstream_refused", "test_mode_only"))
        with self.assertRaises(Exception) as x:
            asyncio.run(ad.cancel("duffel", "act_x", PV.Upstream()))
        self.assertEqual(x.exception.code, "not_cancellable")

    def test_the_smoke_check_reads_reference_data_only(self):
        seen = []

        async def http(method, path, body=None, params=None):
            seen.append((method, path, params))
            return 200, {"data": [{"id": "arl_x", "name": "X"}]}
        with mock.patch("booking_signer.travel.HTTP", http), mock.patch("booking_signer.travel.token", lambda: "duffel_test_abc"):
            out = asyncio.run(AL.ADAPTERS["flights"].smoke())
        self.assertEqual(seen, [("GET", "/air/airlines", {"limit": 1})])                       # no offer request, no order
        self.assertEqual((out["ok"], out["token"]), (True, "test"))



class FakeStripe:
    """Stripe TEST: Checkout sessions made, read back; `paid` flips a session to complete/paid. Every request kept."""

    def __init__(self, livemode=False):
        self.calls, self.sessions, self.livemode = [], {}, livemode

    async def __call__(self, method, path, data=None):
        self.calls.append((method, path, dict(data or {})))
        if method == "POST" and path == "/checkout/sessions":
            sid = f"cs_test_{len(self.sessions) + 1:020d}"
            self.sessions[sid] = {"id": sid, "url": f"https://checkout.stripe.com/c/pay/{sid}", "livemode": self.livemode, "status": "open",
                                  "payment_status": "unpaid", "amount_total": data["line_items[0][price_data][unit_amount]"],
                                  "currency": data["line_items[0][price_data][currency]"], "metadata": {k: v for k, v in data.items() if k.startswith("metadata")}}
            return 200, self.sessions[sid]
        if method == "GET" and path.startswith("/checkout/sessions/"):
            return 200, self.sessions[path.rsplit("/", 1)[1]]
        if method == "GET" and path == "/balance":
            return 200, {"object": "balance", "livemode": self.livemode}
        raise AssertionError((method, path))

    def pay(self, sid):
        self.sessions[sid].update(status="complete", payment_status="paid", payment_intent="pi_test_x")


class PaymentsLive(Live):
    """Stripe in TEST mode: a live flight booking pays on Stripe's TEST page and settles only from Stripe's own record."""
    connected = {"places", "flights", "payments"}

    def setUp(self):
        super().setUp()
        self.stripe = FakeStripe()
        for p in (mock.patch("booking_signer.test_deposit.HTTP", self.stripe), mock.patch.dict("os.environ", {"STRIPE_TEST_SECRET_KEY": "sk_test_recorded"})):
            p.start()
            self.addCleanup(p.stop)

    def approve(self, read_back_id):
        from agapi_service import engine as E
        key = self.store.one("select * from api_keys where mode = 'live'")
        ctx = E.Ctx(self.store, key, "req_" + "1" * 26, None, None)
        return asyncio.run(E.sandbox_simulate_approval(ctx, {"read_back_id": read_back_id, "said": "Yes, book it."}))[0]["approval_id"]

    def booked(self):
        uid = self.ok("users.register", {"external_ref": "pay-1"}, key=self.live)["end_user_id"]
        ref = self.ok("travel.find_flights", FLIGHTS, key=self.live)["offers"][0]["offer_ref"]
        h = self.ok("trip.hold", {"end_user": uid, "items": [{"kind": "flight", "ref": ref}], "travellers": [TRAVELLER]}, key=self.live)
        apv = self.approve(h["read_back"]["read_back_id"])
        return self.ok("trip.complete", {"hold_id": h["hold_id"], "payment": {"method": "payment_link"}}, key=self.live, approval=apv)

    def test_a_live_booking_pays_on_stripes_test_page_and_settles_from_stripes_record(self):
        out = self.booked()
        self.assertEqual(out["outcome"]["kind"], "AWAITING_PAYMENT")
        url = out["outcome"]["payment_url"]
        self.assertTrue(url.startswith("https://checkout.stripe.com/c/pay/cs_test_"))              # Stripe's page, test mode
        sid = url.rsplit("/", 1)[1]
        made = [c for c in self.stripe.calls if c[1] == "/checkout/sessions"][0][2]
        self.assertEqual(made["metadata[test_payment]"], "true")
        self.assertIn("/pay/return/", made["success_url"])                                         # back to AgAPI, not to Sasha
        row = self.store.one("select * from pay_sessions")
        token_path = "/" + made["success_url"].split("://", 1)[1].split("/", 1)[1].split("?")[0]
        # the sandbox's simulated pay page does nothing on the live service
        self.assertEqual(self.client.post(token_path.replace("/pay/return/", "/pay/")).status_code, 404)
        self.assertIn("Checking the payment", self.client.get(token_path + f"?s={sid}").text)      # not paid yet: nothing happens
        self.assertEqual(self.ok("acts.status", {"act_id": out["act_id"]}, key=self.live)["acts"][0]["outcome"]["kind"], "AWAITING_PAYMENT")
        self.stripe.pay(sid)
        page = self.client.get(token_path + f"?s={sid}").text
        self.assertIn("Booked — reference", page)                                                  # Duffel TEST order (recorded)
        st = self.ok("acts.status", {"act_id": out["act_id"]}, key=self.live)["acts"][0]
        self.assertEqual(st["outcome"]["kind"], "CONFIRMED")
        self.assertIsNotNone(self.store.one("select settled_at from pay_sessions")["settled_at"])
        from agapi_service.adapters_live import payments as LP
        self.assertIsNone(asyncio.run(LP.settle(self.store, row["token_hash"])))                  # once only (the poller can't book twice)

    def test_a_live_stripe_key_or_a_livemode_answer_is_refused(self):
        with mock.patch.dict("os.environ", {"STRIPE_TEST_SECRET_KEY": "sk_live_xxx"}):
            r = self.booked_refusal()
        self.assertEqual(r["error"]["code"], "upstream_unreachable")
        with mock.patch("booking_signer.test_deposit.HTTP", FakeStripe(livemode=True)):
            r = self.booked_refusal()
        self.assertEqual(r["error"]["code"], "upstream_failed")

    def booked_refusal(self):
        uid = self.ok("users.register", {"external_ref": "pay-r"}, key=self.live)["end_user_id"]
        ref = self.ok("travel.find_flights", FLIGHTS, key=self.live)["offers"][0]["offer_ref"]
        h = self.ok("trip.hold", {"end_user": uid, "items": [{"kind": "flight", "ref": ref}], "travellers": [TRAVELLER]}, key=self.live)
        apv = self.approve(h["read_back"]["read_back_id"])
        r, b = self.call("trip.complete", {"hold_id": h["hold_id"], "payment": {"method": "payment_link"}}, key=self.live, approval=apv)
        self.assertFalse(b["ok"])
        return b

    def test_the_smoke_check_reads_the_test_balance_only(self):
        out = asyncio.run(AL.ADAPTERS["payments"].smoke())
        self.assertEqual(self.stripe.calls, [("GET", "/balance", {})])
        self.assertEqual((out["ok"], out["livemode"]), (True, False))



class FakeResend:
    """Resend: POST /emails → an id (or `status`); every request kept."""

    def __init__(self, status=200):
        self.calls, self.status = [], status

    async def __call__(self, method, url, headers=None, json=None, **kw):
        from scripts import places_fake
        self.calls.append({"url": url, "json": json, "auth": (headers or {}).get("authorization", "")[:7]})
        if not json:
            return places_fake._R(422, {"name": "validation_error", "message": "Missing `to` field."})
        if self.status != 200:
            return places_fake._R(self.status, {"name": "internal_server_error", "message": "boom"})
        return places_fake._R(200, {"id": f"re_{len(self.calls):06d}"})


OURS, THEIRS = "tyler-test@kanoe.example", "someone@else.example"


class EmailAndCalendarLive(Live):
    connected = {"places", "flights", "payments", "calendar", "email"}

    def setUp(self):
        super().setUp()
        self.resend = FakeResend()
        for p in (mock.patch.object(AL, "http", self.resend), mock.patch.object(config, "EMAIL_ALLOW", {OURS}),
                  mock.patch.object(config, "EMAIL_FROM", "Sasha <sasha@booking.kanoe.example>"),
                  mock.patch.dict("os.environ", {"SASHA_RESEND_API_KEY": "re_recorded"})):
            p.start()
            self.addCleanup(p.stop)
        self.uid = self.ok("users.register", {"external_ref": "mail-1"}, key=self.live)["end_user_id"]

    def approve(self, read_back_id):
        return PaymentsLive.approve(self, read_back_id)

    def email(self, to):
        return {"end_user": self.uid, "to": {"address": to, "name": "Tyler"}, "subject": "Our trip", "body": "Hi,\nWe land at 09:00.\nAna"}

    def test_an_address_not_on_the_allow_list_is_refused_before_anything(self):
        r, b = self.call("messages.send_email", self.email(THEIRS), key=self.live, expect="upstream_refused")
        self.assertEqual(b["error"]["details"]["reason"], "not_allow_listed")
        self.assertEqual(self.store.one("select count(*) as n from read_backs")["n"], 0)          # no read-back, nothing to approve
        self.assertEqual(self.resend.calls, [])

    def test_an_allow_listed_email_is_sent_by_resend_only_after_the_yes(self):
        r, b = self.call("messages.send_email", self.email(OURS), key=self.live, expect="approval_required")
        self.assertEqual(self.resend.calls, [])                                                  # nothing before the yes
        apv = self.approve(b["error"]["details"]["read_back_id"])
        out = self.ok("messages.send_email", self.email(OURS), key=self.live, approval=apv)
        sent = self.resend.calls[-1]
        self.assertEqual(sent["url"], "https://api.resend.com/emails")
        self.assertEqual((sent["json"]["to"], sent["json"]["from"], sent["json"]["subject"]), ([OURS], "Sasha <sasha@booking.kanoe.example>", "Our trip"))
        self.assertEqual(sent["json"]["text"], "Hi,\nWe land at 09:00.\nAna")                     # the headers aren't in the body
        self.assertEqual(out["outcome"]["reference"], "re_000001")                               # Resend's own id
        self.assertIn("Resend id re_000001", out["outcome"]["target_words"]["text"])
        self.assertNotIn("captured, never sent", out["outcome"]["target_words"]["text"])

    def test_resend_refusing_is_said_and_nothing_is_claimed(self):
        r, b = self.call("messages.send_email", self.email(OURS), key=self.live, expect="approval_required")
        apv = self.approve(b["error"]["details"]["read_back_id"])
        with mock.patch.object(AL, "http", FakeResend(status=500)):
            r, b = self.call("messages.send_email", self.email(OURS), key=self.live, approval=apv, expect="upstream_failed")
        self.assertEqual(self.store.one("select count(*) as n from acts")["n"], 0)

    def test_a_verification_code_goes_only_to_an_allow_listed_address(self):
        self.call("users.register", {"external_ref": "mail-2", "destinations": [{"channel": "email", "value": THEIRS}]}, key=self.live,
                  expect="upstream_refused")
        self.assertIsNone(self.store.one("select id from end_users where external_ref = 'mail-2'"))
        self.ok("users.register", {"external_ref": "mail-3", "destinations": [{"channel": "email", "value": OURS}]}, key=self.live)
        self.assertEqual(self.resend.calls[-1]["json"]["subject"], "Your Kanoe verification code")
        self.assertIn("verification code is", self.resend.calls[-1]["json"]["text"])

    def test_the_smoke_checks_send_nothing(self):
        out = asyncio.run(AL.ADAPTERS["email"].smoke())
        self.assertEqual((out["ok"], out["sent"], out["status"]), (True, False, 422))
        self.assertEqual(self.resend.calls[-1]["json"], {})                                      # an EMPTY request: Resend can't send it
        cal = asyncio.run(AL.ADAPTERS["calendar"].smoke())
        self.assertTrue(cal["ok"])
        self.assertTrue(isinstance(AL.ADAPTERS["calendar"], AD.SimCalendar))                     # the same .ics code as the sandbox



JON, STRANGER, SENDER = "+447700900123", "+447700900999", "+14155238886"


class FakeTwilio:
    """Twilio's REST reads: the account, and the messages a number sent us (`inbound_hours_ago` None = none)."""

    def __init__(self, inbound_hours_ago=1):
        self.calls, self.inbound_hours_ago = [], inbound_hours_ago

    async def __call__(self, method, url, headers=None, json=None, **kw):
        from datetime import datetime, timedelta, timezone
        from scripts import places_fake
        self.calls.append((method, url))
        assert method == "GET", "the adapter's own reads are GETs; sends go through Sasha's senders"
        if url.endswith(".json") and "/Messages.json" not in url:
            return places_fake._R(200, {"status": "active"})
        msgs = []
        if self.inbound_hours_ago is not None:
            when = datetime.now(timezone.utc) - timedelta(hours=self.inbound_hours_ago)
            msgs = [{"direction": "inbound", "date_sent": when.strftime("%a, %d %b %Y %H:%M:%S +0000")}]
        return places_fake._R(200, {"messages": msgs})


class WhatsAppLive(Live):
    connected = {"places", "flights", "payments", "calendar", "email", "whatsapp"}

    def setUp(self):
        super().setUp()
        self.twilio, self.wa_sent, self.sms_sent = FakeTwilio(), [], []

        async def wa_send(_self, frm, to, *, body="", media=None, content_sid=None, variables=None):
            self.wa_sent.append((frm, to, body))
            return "sent"

        async def sms(to, body, switch="SASHA_SMS_TO_GUEST"):
            self.sms_sent.append((to, body))
            return "sms sent"
        for p in (mock.patch.object(AL, "http", self.twilio), mock.patch.object(config, "WHATSAPP_ALLOW", {JON}),
                  mock.patch("booking_signer.guest_whatsapp.Sender.send", wa_send), mock.patch("booking_signer.guest_receipt.send_sms", sms),
                  mock.patch.dict("os.environ", {"SASHA_GUEST_WHATSAPP_TO": SENDER, "TWILIO_ACCOUNT_SID": "AC" + "0" * 32, "TWILIO_AUTH_TOKEN": "t" * 32})):
            p.start()
            self.addCleanup(p.stop)
        self.uid = self.ok("users.register", {"external_ref": "wa-1"}, key=self.live)["end_user_id"]

    def approve(self, read_back_id):
        return PaymentsLive.approve(self, read_back_id)

    def wa(self, number, text="Hi Jon, the boat is at 09:00."):
        return {"end_user": self.uid, "to": {"number": number, "name": "Jon"}, "text": text}

    def test_a_number_not_on_the_allow_list_is_refused_before_anything(self):
        r, b = self.call("messages.send_whatsapp", self.wa(STRANGER), key=self.live, expect="upstream_refused")
        self.assertEqual(b["error"]["details"]["reason"], "not_allow_listed")
        self.assertEqual((self.store.one("select count(*) as n from read_backs")["n"], self.wa_sent), (0, []))

    def test_inside_the_window_sashas_sender_sends_only_after_the_yes(self):
        r, b = self.call("messages.send_whatsapp", self.wa(JON), key=self.live, expect="approval_required")
        self.assertEqual(self.wa_sent, [])
        self.assertTrue(any("/Messages.json?From=whatsapp:" + JON in c[1] for c in self.twilio.calls))   # the window: Twilio's record
        out = self.ok("messages.send_whatsapp", self.wa(JON), key=self.live, approval=self.approve(b["error"]["details"]["read_back_id"]))
        self.assertEqual(self.wa_sent, [(SENDER, JON, "Hi Jon, the boat is at 09:00.")])
        self.assertTrue(out["outcome"]["reference"].startswith("twilio_"))
        self.assertNotIn("captured, never sent", out["outcome"]["target_words"]["text"])

    def test_outside_the_window_without_the_template_nothing_is_read_back(self):
        with mock.patch.object(AL, "http", FakeTwilio(inbound_hours_ago=30)):
            r, b = self.call("messages.send_whatsapp", self.wa(JON), key=self.live, expect="upstream_refused")
        self.assertEqual(b["error"]["details"]["reason"], "template_not_configured")
        self.assertEqual((self.store.one("select count(*) as n from read_backs")["n"], self.wa_sent), (0, []))

    def test_a_code_by_sms_goes_only_to_an_allow_listed_number(self):
        self.call("users.register", {"external_ref": "wa-2", "destinations": [{"channel": "sms", "value": STRANGER}]}, key=self.live,
                  expect="upstream_refused")
        self.ok("users.register", {"external_ref": "wa-3", "destinations": [{"channel": "sms", "value": JON}]}, key=self.live)
        self.assertEqual(len(self.sms_sent), 1)
        self.assertEqual(self.sms_sent[0][0], JON)
        self.assertIn("verification code is", self.sms_sent[0][1])

    def test_the_smoke_check_sends_nothing(self):
        out = asyncio.run(AL.ADAPTERS["whatsapp"].smoke())
        self.assertEqual((out["ok"], out["sent"], out["template"]), (True, False, False))
        self.assertEqual((self.wa_sent, self.sms_sent), ([], []))
        self.assertTrue(all(m == "GET" for m, _ in self.twilio.calls))



SASHA = "https://sasha-travel-production.up.railway.app"
TEST_FORM = SASHA + "/api/booking/test-venue/plain"


class FakeSasha:
    """Sasha's deployed booking routes (over HTTPS), as fakes: a venue read with the given rungs, prepare, send, cancel. Every call kept."""

    def __init__(self, rungs, plan="form", send=None):
        self.rungs, self.plan, self.calls = rungs, plan, []
        self.send = send or {"status": "sent", "reading": {"result": "confirmed"}, "booking_reference": "TV-123"}

    async def __call__(self, method, url, headers=None, json=None, **kw):
        from scripts import places_fake
        path = url.replace(SASHA, "")
        self.calls.append((method, path, json, dict(headers or {})))
        R = lambda st, body: places_fake._R(st, body)
        if path == "/api/booking/health":
            return R(200, {"ok": True})
        if (headers or {}).get("x-sasha-booking-key") != "booking-key-recorded" or (headers or {}).get("x-sasha-session") != "demo":
            return R(401, {"detail": {"message": "booking key required"}})
        if path == "/api/booking/venues/read":
            return R(200, {"read_id": "rd_1", "venue": "Casa Marea", "country": "ES", "plan": {"route": self.plan},
                           "rungs": [{"rung": k, "available": True, "value": v} for k, v in self.rungs.items()]})
        if path == "/api/booking/draft":
            return R(200, {"parts": {"what": {"category": "restaurant", "activity": "table"}}})
        if path == "/api/booking/contact":
            return R(200, {"contact": {"name": "Demo Guest", "mobile_e164": "+34600000001"}})
        if method == "POST" and path in ("/api/booking/forms", "/api/booking/emails", "/api/booking/calls"):
            kind = path.rsplit("/", 1)[1][:-1]
            return R(200, {f"{kind}_id": f"{kind}_1", "trip_item_id": "ti_1", "read_back": {"sha256": "sha_" + kind,
                     "lines": [f"Sasha will book Casa Marea by {kind} for 2, 20 Nov 20:30.", "Name: Demo Guest."]}})
        if method == "POST" and path.endswith(("/send", "/place")):
            return R(200, self.send)
        if path == "/api/booking/reservations/ti_1/cancel":
            if method == "GET":
                return R(200, {"read_back": {"sha256": "sha_cancel", "lines": ["Cancel Casa Marea, 20 Nov 20:30."]}, "venue": "Casa Marea"})
            return R(200, {"status": "cancelled", "say": "Casa Marea cancelled it."})
        raise AssertionError((method, path))

    def paths(self):
        return [p for _, p, _, _ in self.calls]


class LadderLive(Live):
    connected = {"places", "flights", "payments", "calendar", "email", "whatsapp", "venue_ladder"}
    rungs = {"form": TEST_FORM, "email": "info@casa-marea.example", "phone": "+34911111111"}

    def setUp(self):
        super().setUp()
        self.sasha = FakeSasha(self.rungs)
        for p in (mock.patch.object(AL, "http", self.sasha), mock.patch.object(config, "EMAIL_ALLOW", {"tyler-test@kanoe.example"}),
                  mock.patch.object(config, "WHATSAPP_ALLOW", {JON}), mock.patch.dict("os.environ", {"SASHA_BOOKING_KEY": "booking-key-recorded"})):
            p.start()
            self.addCleanup(p.stop)
        self.uid = self.ok("users.register", {"external_ref": "ven-1"}, key=self.live)["end_user_id"]
        self.venue = self.sandbox_answer["venues"][0]
        self.offer_live()

    def offer_live(self):
        """The venue found live (its ref in this account's offers) — Places' answer recorded by the sandbox's search."""
        with mock.patch.object(AL, "http", Recorded()):
            self.ok("venues.find_venues", VENUES, key=self.live)

    def approve(self, read_back_id):
        return PaymentsLive.approve(self, read_back_id)

    def hold(self):
        return self.call("trip.hold", {"end_user": self.uid, "items": [{"kind": "venue", "ref": self.venue["venue_ref"], "at": "2026-11-20T20:30:00+01:00",
                                                                       "party": 2}]}, key=self.live)

    def test_a_form_booking_at_sashas_test_venue_end_to_end(self):
        r, b = self.hold()
        self.assertTrue(b["ok"], b)
        lines = b["result"]["read_back"]["lines"]
        self.assertIn("Sasha will book Casa Marea by form for 2, 20 Nov 20:30.", lines)          # Sasha's own read-back, approved as is
        self.assertTrue(any("by their booking form" in l for l in lines))
        self.assertNotIn("/api/booking/forms/form_1/send", self.sasha.paths())                    # nothing sent before the yes
        out = self.ok("trip.complete", {"hold_id": b["result"]["hold_id"]}, key=self.live, approval=self.approve(b["result"]["read_back"]["read_back_id"]))
        sent = [c for c in self.sasha.calls if c[1] == "/api/booking/forms/form_1/send"][0][2]
        self.assertEqual(sent, {"read_back_sha256": "sha_form", "approval": {"how": "chat", "said": "Yes, book it."}})   # their own words
        self.assertEqual((out["outcome"]["kind"], out["outcome"]["reference"]), ("CONFIRMED", "TV-123"))
        # cancelling it: Sasha's own cancellation, under the cancellation's yes
        r, b2 = self.call("trip.cancel", {"act_id": out["act_id"]}, key=self.live, expect="approval_required")
        c = self.ok("trip.cancel", {"act_id": out["act_id"]}, key=self.live, approval=self.approve(b2["error"]["details"]["read_back_id"]))
        self.assertEqual(c["outcome"]["kind"], "CONFIRMED")
        self.assertIn("/api/booking/reservations/ti_1/cancel", self.sasha.paths())

    def test_an_email_route_only_to_an_allow_listed_address_and_it_is_requested(self):
        self.sasha.rungs = {"form": "https://www.real-venue.example/book", "email": "tyler-test@kanoe.example"}
        self.sasha.send = {"status": "sent"}
        r, b = self.hold()
        self.assertTrue(b["ok"], b)
        self.assertIn("/api/booking/emails", self.sasha.paths())
        self.assertNotIn("/api/booking/forms", self.sasha.paths())                                 # a real venue's form: never
        out = self.ok("trip.complete", {"hold_id": b["result"]["hold_id"]}, key=self.live, approval=self.approve(b["result"]["read_back"]["read_back_id"]))
        self.assertEqual(out["outcome"]["kind"], "REQUESTED")                                     # booked only when they reply
        self.assertIn("requested until they reply", out["outcome"]["target_words"]["text"])

    def test_a_real_venue_with_no_allowed_route_is_refused_before_anything_is_prepared(self):
        self.sasha.rungs = {"form": "https://www.real-venue.example/book", "email": "info@real-venue.example", "phone": "+34911111111"}
        r, b = self.hold()
        self.assertEqual((b["error"]["code"], b["error"]["details"]["reason"]), ("upstream_refused", "not_allow_listed"))
        self.assertEqual([p for p in self.sasha.paths() if p in ("/api/booking/forms", "/api/booking/emails", "/api/booking/calls")], [])
        self.assertEqual(self.store.one("select count(*) as n from read_backs")["n"], 0)

    def test_never_a_booking_platform(self):
        self.sasha.rungs = {"form": "https://www.opentable.com/r/casa-marea?ref=" + SASHA}
        r, b = self.hold()
        self.assertEqual(b["error"]["details"]["reason"], "not_allow_listed")

    def test_a_lost_preparation_means_holding_again(self):
        r, b = self.hold()
        self.store.x("delete from ladder_preps")
        r, b2 = self.call("trip.complete", {"hold_id": b["result"]["hold_id"]}, key=self.live,
                          approval=self.approve(b["result"]["read_back"]["read_back_id"]), expect="hold_expired")

    def test_the_live_network_guard_lets_sasha_through_and_nothing_else_new(self):
        hosts = PV.live_hosts()
        self.assertIn("sasha-travel-production.up.railway.app", hosts)                             # (the live smoke caught its absence)
        self.assertTrue(hosts >= config.LIVE_HOSTS)
        self.assertFalse(any(p in h for h in hosts for p in ("opentable", "thefork", "booking.com", "resy")))

    def test_a_tap_is_sashas_button_and_the_smoke_check_prepares_nothing(self):
        out = asyncio.run(AL.ADAPTERS["venue_ladder"].book("venue", {"_ladder": {"rung": "form", "id": "form_9", "sha256": "s", "venue": "X"}}, PV.Upstream(),
                                                           approval={"method": "tap", "said": None}))
        self.assertEqual(self.sasha.calls[-1][2]["approval"], {"how": "button"})
        n = len(self.sasha.calls)
        sm = asyncio.run(AL.ADAPTERS["venue_ladder"].smoke())
        self.assertEqual((sm["ok"], sm["sent"], sm["demo_contact"]), (True, False, True))
        self.assertEqual([m for m, *_ in self.sasha.calls[n:]], ["GET", "GET"])                    # reads only



import pathlib as _pl
RECORDED = json.loads((_pl.Path(__file__).parent / "fixtures" / "duffel_cancel_recorded.json").read_text())


class FlightCancelLive(PaymentsLive):
    """CR 71 · the Duffel cancel on RECORDED Duffel TEST answers (fixtures/duffel_cancel_recorded.json, from agapi-live's own smoke)."""

    def setUp(self):
        super().setUp()
        from booking_signer import travel as T
        self.replay, self.duffel_calls, self.mode = T.HTTP, [], "ok"

        async def http(method, path, body=None, params=None):
            if "/air/order_cancellations" in path:
                self.duffel_calls.append((method, path, body))
                if self.mode == "refused":
                    return 422, {"errors": RECORDED["refused"]["errors"]}
                if path == "/air/order_cancellations":
                    d = dict(RECORDED["quote"]["data"], order_id=body["data"]["order_id"])
                    if self.mode == "expired":
                        d["expires_at"] = "2026-01-01T00:00:00Z"
                    return RECORDED["quote"]["status"], {"data": d}
                return RECORDED["confirm"]["status"], {"data": RECORDED["confirm"]["data"]}
            return await self.replay(method, path, body, params) if params is not None or body is not None else await self.replay(method, path)
        p = mock.patch("booking_signer.travel.HTTP", http)
        p.start()
        self.addCleanup(p.stop)

    def confirmed_flight(self):
        out = self.booked()
        sid = out["outcome"]["payment_url"].rsplit("/", 1)[1]
        made = [c for c in self.stripe.calls if c[1] == "/checkout/sessions"][0][2]
        path = "/" + made["success_url"].split("://", 1)[1].split("/", 1)[1].split("?")[0]
        self.stripe.pay(sid)
        self.assertIn("Booked — reference", self.client.get(path + f"?s={sid}").text)
        self.assertTrue(self.store.one("select order_id from flight_orders")["order_id"])
        return out["act_id"]

    def test_the_refund_is_the_airlines_own_quote_and_it_cancels_only_after_the_yes(self):
        act = self.confirmed_flight()
        r, b = self.call("trip.cancel", {"act_id": act}, key=self.live, expect="approval_required")
        lines = b["error"]["details"]["read_back"]["lines"]
        self.assertIn("Refund EUR 74.74 — the airline's own quote (Duffel TEST), to balance.", lines)   # Duffel's recorded answer
        self.assertEqual([c[1] for c in self.duffel_calls], ["/air/order_cancellations"])           # quoted, NOT cancelled
        apv = self.approve(b["error"]["details"]["read_back_id"])
        c = self.ok("trip.cancel", {"act_id": act}, key=self.live, approval=apv)
        self.assertEqual(c["outcome"]["kind"], "CONFIRMED")
        self.assertEqual(c["outcome"]["reference"], RECORDED["confirm"]["data"]["id"])
        self.assertIn("refund EUR 74.74 to balance", c["outcome"]["target_words"]["text"])
        self.assertEqual([c_[1] for c_ in self.duffel_calls], ["/air/order_cancellations",
                                                              f"/air/order_cancellations/{RECORDED['quote']['data']['id']}/actions/confirm"])
        self.call("trip.cancel", {"act_id": act}, key=self.live, expect="already_completed")

    def test_an_expired_quote_is_quoted_again_and_asked_again(self):
        act = self.confirmed_flight()
        self.mode = "expired"
        self.call("trip.cancel", {"act_id": act}, key=self.live, expect="approval_required")
        self.call("trip.cancel", {"act_id": act}, key=self.live, expect="approval_required")
        self.assertEqual([c[1] for c in self.duffel_calls].count("/air/order_cancellations"), 2)    # never confirmed on a stale quote

    def test_an_airline_that_cant_cancel_by_api_is_said(self):
        act = self.confirmed_flight()
        self.mode = "refused"
        r, b = self.call("trip.cancel", {"act_id": act}, key=self.live, expect="not_cancellable")
        self.assertIn("cannot be cancelled through the API", b["error"]["message"])

    def test_a_live_token_is_refused(self):
        with mock.patch("booking_signer.travel.token", lambda: "duffel_live_x"):
            with self.assertRaises(Exception) as x:
                asyncio.run(AL.ADAPTERS["flights"].cancel_quote("ord_x"))
        self.assertEqual(x.exception.details["reason"], "test_mode_only")


def Base_sign(body: str) -> str:
    import hashlib, hmac, secrets, time
    t, n = int(time.time()), secrets.token_urlsafe(16)
    return f"t={t},n={n},v1=" + hmac.new(config.pepper(), f"{t}.{n}.{body}".encode(), hashlib.sha256).hexdigest()


if __name__ == "__main__":
    import unittest
    unittest.main()
