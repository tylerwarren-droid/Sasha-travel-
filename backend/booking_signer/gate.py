"""S-41 · THE GATE — no anonymous caller can prepare or place a call, send an email, or sign a booking.

Every /api/booking/* route requires the header `x-sasha-booking-key` equal to SASHA_BOOKING_KEY (compared in constant
time). The browser never holds it: the booking page calls the frontend's own server route (Vercel), which checks the
founder's session cookie and only then adds this header (frontend/app/api/booking-proxy/[...path]/route.ts).

Two routes are exempt, each with its own protection:
  · GET  /api/booking/health         reports configuration only — never a value, never a number
  · POST /api/booking/email/inbound  Resend's webhook — svix-signed (emailing.verify_svix)

⛔ Fails CLOSED: if SASHA_BOOKING_KEY is not set on the server, every gated route answers 503 — a missing key never
opens the door.
"""
from __future__ import annotations

import hmac
import os

from fastapi import HTTPException, Request

HEADER = "x-sasha-booking-key"
ENV = "SASHA_BOOKING_KEY"
EXEMPT = {("GET", "/api/booking/health"), ("POST", "/api/booking/email/inbound"),
          # S-70 · Twilio's webhooks to Sasha's own number: each is Twilio-signed and verified (inbound_phone.signature_ok)
          ("POST", "/api/booking/twilio/sms"), ("POST", "/api/booking/twilio/voice"), ("POST", "/api/booking/twilio/recording")}
# Sasha 89 · the TEST VENUE is a public web page with a booking form, like any venue's: its page and its form post are
# open (it books nothing real); its book of submissions is not (GET …/test-venue/submissions needs the key)
EXEMPT |= {(m, f"/api/booking/test-venue/{v}") for m in ("GET", "POST") for v in ("plain", "consent", "captcha", "hotel")}   # Sasha 155 · + our test hotel
EXEMPT |= {("GET", "/api/booking/test-venue/email")}   # Sasha 157 · the email-only test page (read like any site)
EXEMPT |= {("GET", "/api/booking/test-venue/wizard"), ("POST", "/api/booking/test-venue/wizard/step2"),
           ("POST", "/api/booking/test-venue/wizard/confirm")}   # Sasha 94 · the two-step variant
# Sasha 121 (F) · Kanoe Demo Market — ours, a public shop page with a login (it sells and charges nothing)
EXEMPT |= {("GET", "/api/booking/demo-shop"), ("POST", "/api/booking/demo-shop/login"), ("POST", "/api/booking/demo-shop/order")}
EXEMPT |= {("GET", "/api/booking/test-pay/done"), ("GET", "/api/booking/test-pay/back")}   # Sasha 136 · Stripe's return, no sign-in
EXEMPT |= {("GET", "/api/booking/demo-spa"), ("POST", "/api/booking/demo-spa/login"), ("POST", "/api/booking/demo-spa/book")}   # Sasha 126
# S-79 · Google's OAuth redirect: no key can ride on it; its signed, 10-minute `state` names the account (calendar_sync)
EXEMPT |= {("GET", "/api/booking/google/callback")}
# Sasha 198 R8 · Duffel's webhook: no key can ride on it; each event is HMAC-signed and verified (duffel_webhook.verify)
EXEMPT |= {("POST", "/api/booking/travel/duffel/webhook")}


async def require_booking_key(request: Request) -> None:
    if (request.method, request.url.path.rstrip("/")) in EXEMPT:
        return
    if request.method == "GET" and request.url.path.startswith("/api/booking/test-venue/cancel/"):
        return   # Sasha 99 · the test venue's own cancel links — a public page, like any venue's
    if request.url.path.startswith("/api/booking/invite/") and (request.method == "GET" or request.url.path.endswith("/choose")):
        return   # S-80 · the invited guest's page: no account; the 8-character code is the key, rate-limited per address
    if request.method == "GET" and request.url.path.startswith("/api/booking/handover/"):
        return   # CR 23 · the guest's live hand-over page: a 32-byte token in the URL is the key (Sasha 150, the founder's yes;
                 # real guests stay refused until BROWSERBASE_DPA=signed — fictional details only)
    want = os.getenv(ENV, "").strip()
    if not want:
        raise HTTPException(503, {"ok": False, "rule": "booking_key_not_configured",
                                  "message": f"{ENV} is not set on this server, so no booking route is open"})
    got = request.headers.get(HEADER, "")
    if not got or not hmac.compare_digest(got.encode(), want.encode()):
        raise HTTPException(401, {"ok": False, "rule": "booking_key_required",
                                  "message": "this route needs the booking key — it is reached through the founder's signed-in booking page"})
    # S-62 step 1 · the key proves the proxy; WHO is a verified token or the founder's session (identity.py)
    from .identity import resolve
    request.state.account = await resolve(request)
