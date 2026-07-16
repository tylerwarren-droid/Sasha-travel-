"""
Rate-limiting + lightweight auth for the public, LLM-backed endpoints.

The Conductor (`/api/agents/*`) and the voice pipeline (`/api/voice/*`) each spend money on
every call (Claude + Deepgram). Left open, a script — or a curious investor's network — can
rack up cost or knock the demo over. This middleware adds three opt-in protections, all
env-driven so local dev and the existing demo keep working with nothing set:

1. Per-IP token bucket           → RATE_LIMIT_RPM   (requests/min/IP; 0 disables)
2. Global token bucket           → GLOBAL_RATE_LIMIT_RPM (requests/min, all callers; 0 disables)
3. Shared-secret gate            → CONDUCTOR_API_SECRET (require X-Client-Key on POSTs)
4. Daily request cost ceiling    → DAILY_REQUEST_CAP + COST_ALERT_WEBHOOK (alert when hit)

Two honest caveats, so nobody mistakes this for more than it is:

* The shared secret is a speed bump, not authentication. This is a PUBLIC demo with no login,
  so the frontend must be able to call these endpoints from a browser — which means the key
  ships in the JS bundle and anyone determined can read it. It stops drive-by scripts hitting
  the API directly; it does not stop someone who opens devtools. The real cost protection is
  the GLOBAL bucket, which is why that one defaults to ON.
* In-memory state is per-process. The Dockerfile runs `--workers ${WEB_CONCURRENCY:-2}`, so
  with the default 2 workers every limit here is effectively DOUBLE what it says, and all of
  it resets on redeploy. For a single-instance demo that's an acceptable margin; before this
  faces real traffic, back the buckets with Redis (see DEPLOYMENT.md).
"""

import logging
import os
import time
from typing import Optional

import httpx
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

logger = logging.getLogger("kanoe.ratelimit")

RATE_LIMIT_RPM = int(os.getenv("RATE_LIMIT_RPM", "30"))          # per IP per minute; 0 = off
# Ceiling across ALL callers combined. The per-IP bucket is keyed on the client's IP, which
# behind a proxy has to come from X-Forwarded-For — a header the client itself sends. Anyone
# can rotate it (`X-Forwarded-For: $RANDOM`) and mint a fresh per-IP bucket on every request,
# so per-IP alone is worth nothing against a script. This global bucket is not keyed on
# anything the caller controls, so it holds regardless: it's the actual cost ceiling. Set
# generously — it should only ever bite an attacker or a runaway loop, never a room full of
# investors sharing an office IP.
GLOBAL_RATE_LIMIT_RPM = int(os.getenv("GLOBAL_RATE_LIMIT_RPM", "120"))   # 0 = off
CONDUCTOR_API_SECRET = os.getenv("CONDUCTOR_API_SECRET", "").strip()
DAILY_REQUEST_CAP = int(os.getenv("DAILY_REQUEST_CAP", "0"))     # 0 = off
COST_ALERT_WEBHOOK = os.getenv("COST_ALERT_WEBHOOK", "").strip()

# Every public surface that spends money on someone else's meter.
#
# This list used to be just ("/api/agents", "/api/voice"), which left the two widest LLM
# doors wide open: /api/heygen/chat/completions and /conversation/chat both run full
# Claude calls (the conductor even fans out into PAID web_search), and neither started with
# a protected prefix — so they skipped the secret, the bucket and the counter entirely.
# A loop against either billed us with no friction at all.
#
# The rule for adding to this list: if a request can cause an outbound call to a metered
# third party (Anthropic, Deepgram, Unsplash, RateHawk), it belongs here.
_PROTECTED_PREFIXES = (
    "/api/agents",        # conductor, ideas, golf, booking-confirmation — Claude
    "/api/voice",         # Deepgram key minting + voice conductor — Deepgram + Claude
    "/api/heygen",        # chat/completions shim — full conductor pipeline
    "/conversation",      # /conversation/chat — Sonnet, uncapped history
    "/api/photos",        # Unsplash — metered quota, exhaustible
    "/search",            # RateHawk — partner credential, throttleable
    "/bookings",          # RateHawk booking writes
    "/api/cards",         # writes attacker input to disk
)
# Warm-up is a cheap 1-token ping the frontend fires before the user authenticates anything;
# it must not require the secret (but it IS still rate-limited).
_AUTH_EXEMPT = {"/api/agents/warmup"}


class _Bucket:
    __slots__ = ("tokens", "updated")

    def __init__(self, tokens: float, updated: float):
        self.tokens = tokens
        self.updated = updated


_buckets: dict[str, _Bucket] = {}
_daily_count = 0
_daily_day = -1
_daily_alerted = False


def _client_ip(request: Request) -> str:
    """Best-effort client IP, honoring the first hop of X-Forwarded-For (proxy/CDN)."""
    fwd = request.headers.get("x-forwarded-for", "")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _take_token(ip: str, rpm: Optional[int] = None) -> tuple[bool, int]:
    """Token bucket: capacity = rpm (default RATE_LIMIT_RPM), refilled continuously over 60s."""
    now = time.monotonic()
    cap = float(RATE_LIMIT_RPM if rpm is None else rpm)
    refill_per_sec = cap / 60.0
    b = _buckets.get(ip)
    if b is None:
        b = _buckets[ip] = _Bucket(cap, now)
    # Refill based on elapsed time, clamp to capacity.
    b.tokens = min(cap, b.tokens + (now - b.updated) * refill_per_sec)
    b.updated = now
    if b.tokens >= 1.0:
        b.tokens -= 1.0
        return True, 0
    # Seconds until one token is available.
    retry = max(1, int((1.0 - b.tokens) / refill_per_sec))
    return False, retry


async def _note_daily_request() -> None:
    """Count requests/day; log + webhook once when the soft cap is crossed."""
    global _daily_count, _daily_day, _daily_alerted
    day = int(time.time() // 86400)
    if day != _daily_day:
        _daily_day, _daily_count, _daily_alerted = day, 0, False
    _daily_count += 1
    if DAILY_REQUEST_CAP and _daily_count == DAILY_REQUEST_CAP and not _daily_alerted:
        _daily_alerted = True
        logger.warning("Daily request cap reached: %d requests", _daily_count)
        if COST_ALERT_WEBHOOK:
            try:
                async with httpx.AsyncClient(timeout=4) as http:
                    await http.post(COST_ALERT_WEBHOOK, json={
                        "text": f"⚠️ Sasha backend hit DAILY_REQUEST_CAP ({DAILY_REQUEST_CAP}) — possible abuse or runaway cost.",
                    })
            except Exception:
                logger.exception("cost-alert webhook failed")


class RateLimitAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path
        if not path.startswith(_PROTECTED_PREFIXES) or request.method == "OPTIONS":
            return await call_next(request)

        # 1. Shared-secret gate (only when configured, only on writes, warmup exempt).
        if CONDUCTOR_API_SECRET and request.method == "POST" and path not in _AUTH_EXEMPT:
            if request.headers.get("x-client-key", "").strip() != CONDUCTOR_API_SECRET:
                return JSONResponse({"detail": "Unauthorized"}, status_code=401)

        # 2. Per-IP rate limit (fairness between callers).
        if RATE_LIMIT_RPM > 0:
            allowed, retry = _take_token(_client_ip(request))
            if not allowed:
                return JSONResponse(
                    {"detail": "Rate limit exceeded — slow down."},
                    status_code=429,
                    headers={"Retry-After": str(retry)},
                )

        # 3. Global ceiling (cost control). Keyed on a constant, so unlike the per-IP bucket
        #    above it cannot be reset by rotating X-Forwarded-For. This is the limit that
        #    actually bounds the bill.
        if GLOBAL_RATE_LIMIT_RPM > 0:
            allowed, retry = _take_token("__global__", GLOBAL_RATE_LIMIT_RPM)
            if not allowed:
                logger.warning("GLOBAL rate limit hit (%d rpm) — path=%s", GLOBAL_RATE_LIMIT_RPM, path)
                return JSONResponse(
                    {"detail": "The demo is busy right now — please try again in a moment."},
                    status_code=429,
                    headers={"Retry-After": str(retry)},
                )

        # 4. Daily cost ceiling (alert-only; never blocks the demo).
        if DAILY_REQUEST_CAP > 0:
            await _note_daily_request()

        return await call_next(request)
