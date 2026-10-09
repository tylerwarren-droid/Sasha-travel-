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


def Base_sign(body: str) -> str:
    import hashlib, hmac, secrets, time
    t, n = int(time.time()), secrets.token_urlsafe(16)
    return f"t={t},n={n},v1=" + hmac.new(config.pepper(), f"{t}.{n}.{body}".encode(), hashlib.sha256).hexdigest()


if __name__ == "__main__":
    import unittest
    unittest.main()
