"""Settings, from the environment. There is no live mode in this service: every key it issues is agp_test_."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:          # Sasha's search engines (booking_signer) on recorded fixtures — never the agent loop
    sys.path.insert(0, str(BACKEND))

CONTRACT = "1.0"                           # what a response says when the caller doesn't ask (AgAPI-Version)
SPEC_DRAFT = "1.0"                         # EU 201 Parts 1–4, FROZEN v1.0 (EU 205), vendored in spec/v1 (SHA256SUMS)
SUPPORTED = ("1.0", "1.0-draft.1", "1.0-draft.2", "1.0-draft.3", "1.0-draft.4")
MODE = "test"

DB_PATH = os.getenv("AGAPI_DB", str(ROOT / "agapi_service" / "sandbox.db"))
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

COST_UNITS = {"free": 0, "read": 0, "search": 1, "message": 1, "act_prepare": 2, "act": 5}   # Part 4 M2 — placeholders (Tyler prices)
DEFAULT_BUDGET_UNITS = int(os.getenv("AGAPI_DEFAULT_BUDGET_UNITS", "5000"))   # per key per month (M4)
DEFAULT_RATE_PER_MIN = int(os.getenv("AGAPI_DEFAULT_RATE_PER_MIN", "120"))   # per key per minute (M5)
DEFAULT_SCOPES = ["travel.*", "venues.*", "trip.*", "approvals.*", "acts.*", "evidence.*", "users.*", "usage.*", "sandbox.*", "webhooks.*",
                  "messages.*", "calendar.*", "activity.*"]
SCOPES_ADDED = {"webhooks.*": "CR 59", "messages.*": "CR 60", "calendar.*": "CR 60", "activity.*": "CR 62"}   # keys issued earlier gain these (additive)

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
