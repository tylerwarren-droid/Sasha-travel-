"""S-41 · the gate: no anonymous caller reaches a booking route.

    cd backend && python -m unittest tests.test_booking_gate -v
"""
import os
import unittest
from unittest import mock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from booking_signer import routes


class Gate(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        app.include_router(routes.router)
        self.anon = TestClient(app)
        self.wrong = TestClient(app, headers={"x-sasha-booking-key": "nope"})
        self.right = TestClient(app, headers={"x-sasha-booking-key": "k-test"})
        self.env = mock.patch.dict(os.environ, {"SASHA_BOOKING_KEY": "k-test", "SASHA_CALL_SWEEP": "0", "SASHA_CALLS_ENABLED": "1",
                                               "BLAND_API_KEY": "b", "SASHA_TEST_CALL_NUMBER": "+351912000000"})
        self.env.start()

    def tearDown(self):
        self.env.stop()

    ROUTES = [("POST", "/api/booking/calls"), ("POST", "/api/booking/calls/x/place"), ("GET", "/api/booking/calls/x"),
              ("POST", "/api/booking/intents"), ("POST", "/api/booking/intents/x/issue"), ("POST", "/api/booking/reports"),
              ("GET", "/api/booking/reservations"), ("POST", "/api/booking/venues/read"), ("POST", "/api/booking/emails"),
              ("POST", "/api/booking/emails/x/send"), ("POST", "/api/booking/links"), ("POST", "/api/booking/pairing/challenge")]

    def test_no_route_answers_without_the_key(self):
        for m, path in self.ROUTES:
            for c in (self.anon, self.wrong):
                r = c.request(m, path, json={})
                self.assertEqual((r.status_code, r.json()["detail"]["rule"]), (401, "booking_key_required"), (m, path))

    def test_a_missing_server_key_closes_every_route(self):
        with mock.patch.dict(os.environ, {"SASHA_BOOKING_KEY": ""}):
            r = self.right.post("/api/booking/calls", json={})
        self.assertEqual((r.status_code, r.json()["detail"]["rule"]), (503, "booking_key_not_configured"))

    def test_the_right_key_passes_the_gate_but_names_nobody(self):
        """S-62 step 1 · the key proves the proxy, not a person: without an account, every booking route refuses."""
        r = self.right.post("/api/booking/calls", json={"venue": "nowhere"})
        self.assertEqual((r.status_code, r.json()["detail"]["rule"]), (401, "account_required"))
        r = self.right.post("/api/booking/calls", json={"venue": "nowhere"}, headers={"x-sasha-session": "founder"})
        self.assertEqual(r.json()["rule"], "venue_not_callable")   # past the gate, refused by the route itself

    def test_health_and_the_signed_webhook_are_exempt(self):
        self.assertEqual(self.anon.get("/api/booking/health").status_code, 200)
        r = self.anon.post("/api/booking/email/inbound", content=b"{}")
        self.assertEqual(r.json()["rule"], "signature_invalid")   # its own svix check, not the gate


if __name__ == "__main__":
    unittest.main()
