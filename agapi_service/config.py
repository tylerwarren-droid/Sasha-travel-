"""Settings, from the environment. There is no live mode in this service: every key it issues is agp_test_."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:          # Sasha's search engines (booking_signer) on recorded fixtures — never the agent loop
    sys.path.insert(0, str(BACKEND))

CONTRACT = "1.2"                           # what a response says when the caller doesn't ask (AgAPI-Version) — CR 66: EU 213's 1.2
SPEC_DRAFT = "1.2"                         # EU 213's v1.2 (additive: the Keep), vendored in spec/v1 (SHA256SUMS)
SUPPORTED = ("1.2", "1.1", "1.0", "1.0-draft.1", "1.0-draft.2", "1.0-draft.3", "1.0-draft.4")   # additive: older callers still served
MODE = "test"

DB_PATH = os.getenv("AGAPI_DB", str(ROOT / "agapi_service" / "sandbox.db"))
DATABASE_URL = os.getenv("AGAPI_DATABASE_URL", "").strip()   # CR 69 · a Railway Postgres; unset = SQLite (as before)
IMPORT_SQLITE = os.getenv("AGAPI_IMPORT_SQLITE", "") == "1"
# CR 70 · the LIVE service (agapi-live): the same image, live keys only, real providers behind the adapters; its own Postgres schema
LIVE_SERVICE = os.getenv("AGAPI_SERVICE", "").strip() == "live"
DB_SCHEMA = os.getenv("AGAPI_DB_SCHEMA", "").strip()            # agapi-live: "live" (the sandbox keeps the default schema)
CONNECTED_LIVE = {k.strip() for k in os.getenv("AGAPI_CONNECTED_LIVE", "").split(",") if k.strip()}   # only on agapi-live
PLACES_DAILY_CAP = int(os.getenv("AGAPI_PLACES_DAILY_CAP", "100"))   # AgAPI live's own cap: Sasha shares Google's daily Text Search quota
# the only hosts the live service may reach (every other outbound call stays refused); magellan's marked reads as before
# CR 70 · live sends go ONLY to these (comma-separated; empty = nothing is sent live). Tyler's own addresses / numbers.
EMAIL_ALLOW = {a.strip().lower() for a in os.getenv("AGAPI_EMAIL_ALLOW", "").split(",") if a.strip()}
WHATSAPP_ALLOW = {"".join(ch for ch in a if ch.isdigit() or ch == "+") for a in os.getenv("AGAPI_WHATSAPP_ALLOW", "").split(",") if a.strip()}
WA_ONBEHALF_SID = os.getenv("AGAPI_WA_ONBEHALF_SID", "").strip()   # CR 70 · Meta's approved first-contact template (live); unset = refused
LIVE_HOSTS = {"places.googleapis.com", "api.duffel.com", "api.stripe.com", "api.resend.com", "api.twilio.com", "api.bland.ai", "api.anthropic.com"}    # CR 69 · once, on Railway: copy AGAPI_DB's rows into the empty Postgres
# CR 69 · magellan.read_site's AI reader: AgAPI's own key (without it the operation says so) and the price it's logged at (USD/Mtok in, out)
ANTHROPIC_KEY = os.getenv("AGAPI_ANTHROPIC_API_KEY", "").strip()
READER_MODEL = os.getenv("AGAPI_READER_MODEL", "claude-opus-5-5").strip()
READER_PRICE = tuple(float(x) for x in (os.getenv("AGAPI_READER_PRICE", "4,20").split(",") + ["0"])[:2])   # Opus 5.5's published price   # CR 69 · a Railway Postgres; unset = SQLite (as before)
PUBLIC_URL = os.getenv("AGAPI_PUBLIC_URL", "http://127.0.0.1:8787").rstrip("/")
KEY_PEPPER = os.getenv("AGAPI_KEY_PEPPER", "")

# Tyler (CR 58): a read-back is approvable 30 min after it was presented; an Approval is usable 15 min after the yes.
# Part 1 AP4: irreversible acts — both at most 15 min (products may shorten, never lengthen).
READ_BACK_TTL_MIN = 30
READ_BACK_TTL_IRREVERSIBLE_MIN = 15
APPROVAL_TTL_MIN = 15
LINK_TTL_MIN = 15                          # Part 4 §3.1: the approval link is single-use, 15 minutes
HOLD_TTL_MIN = 30
OTP_TTL_MIN = 10
IDEMPOTENCY_RETENTION_H = 24               # Part 1 I10

COST_UNITS = {"free": 0, "read": 0, "search": 1, "message": 1, "act_prepare": 2, "act": 5, "site_read": 10}   # CR 69 · site_read: magellan.read_site   # Part 4 M2 — placeholders (Tyler prices)
DEFAULT_BUDGET_UNITS = int(os.getenv("AGAPI_DEFAULT_BUDGET_UNITS", "5000"))   # per key per month (M4)
DEFAULT_RATE_PER_MIN = int(os.getenv("AGAPI_DEFAULT_RATE_PER_MIN", "120"))   # per key per minute (M5)
# CR 69 · one account per product (plus the partners'); test and live keys separate (agp_test_ / agp_live_)
PRODUCTS = ("sasha", "ad", "dive", "campusme")
METRICS_SCOPE = "metrics.*"                # /metrics (p50/p95 per operation) — only a key that holds this scope (Falguni's)
DEFAULT_SCOPES = ["travel.*", "venues.*", "trip.*", "approvals.*", "acts.*", "evidence.*", "users.*", "usage.*", "sandbox.*", "webhooks.*",
                  "messages.*", "calendar.*", "activity.*", "keep.*", "magellan.*", "subscriptions.*", "registry.*", "cards.*"]
SCOPES_ADDED = {"webhooks.*": "CR 59", "messages.*": "CR 60", "calendar.*": "CR 60", "activity.*": "CR 62", "keep.*": "CR 63", "magellan.*": "CR 69", "subscriptions.*": "CR 72", "registry.*": "CR 73", "cards.*": "CR 74"}   # keys issued earlier gain these (additive)

# CR 60 · Sasha's own sending address (never the user's mailbox). TYLER DECIDES the real one; in test mode nothing is sent.
EMAIL_FROM = os.getenv("AGAPI_EMAIL_FROM", "Sasha (sandbox) <sasha@sandbox.agapi.kanoe.ai>")
REPLY_DOMAIN = os.getenv("AGAPI_REPLY_DOMAIN", "sandbox.agapi.kanoe.ai")
# CR 62 · Sasha's WhatsApp number in the sandbox (a reserved test number: nothing is ever sent from it)
WA_FROM = os.getenv("AGAPI_WA_FROM", "+15005550100")


def pepper() -> bytes:
    if KEY_PEPPER:
        return KEY_PEPPER.encode()
    if os.getenv("RAILWAY_ENVIRONMENT_NAME"):
        raise RuntimeError("AGAPI_KEY_PEPPER must be set on a deployed service")
    return b"agapi-sandbox-local-pepper"   # a local sandbox only
