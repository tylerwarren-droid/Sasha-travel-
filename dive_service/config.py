"""DIVE's settings — its OWN database, its OWN sandbox key, its OWN public URL. Nothing here is the sandbox's or Sasha's."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DB_PATH = os.getenv("DIVE_DB", str(ROOT / "dive.db"))
PUBLIC_URL = os.getenv("DIVE_PUBLIC_URL", "http://127.0.0.1:8899").rstrip("/")
SANDBOX_URL = os.getenv("DIVE_SANDBOX_URL", "https://agapi-sandbox-production.up.railway.app").rstrip("/")
SANDBOX_KEY = os.getenv("DIVE_SANDBOX_KEY", "")            # DIVE's own agp_test_ key on the sandbox — a partner like any other
CONSOLE_TOKEN = os.getenv("DIVE_CONSOLE_TOKEN", "")        # the console's door (generated on Railway, never printed)
KEY_PEPPER = os.getenv("DIVE_KEY_PEPPER", "")              # opk_ keys are stored as HMAC(pepper)
MODE = "test"

# Tyler's decisions (CR 64 Part B)
ANSWER_TIMEOUT_S = 2 * 3600                                # suppliers get 2 h to answer
QUIET_HOURS = ("22:00", "08:00")                           # no message to a supplier between these, Mykonos time
TIMEZONE = "Europe/Athens"                                 # Mykonos
FOOTER = "Blue Kyma API · powered by AgAPI"
# the gear email: a REAL send in test mode, ONLY to our own allow-listed addresses (and only with a sending key set)
EMAIL_ALLOW = {a.strip().lower() for a in os.getenv("DIVE_EMAIL_ALLOW", "").split(",") if a.strip()}
EMAIL_FROM = os.getenv("DIVE_EMAIL_FROM", "")
RESEND_KEY = os.getenv("DIVE_RESEND_API_KEY", "")
# Jon's WhatsApp: NO real message until Tyler names the rehearsal day — until then the sandbox captures (it never sends)
REAL_WHATSAPP = os.getenv("DIVE_REAL_WHATSAPP", "") == "1"


def deployed() -> bool:
    return bool(os.getenv("RAILWAY_ENVIRONMENT_NAME"))


def pepper() -> bytes:
    if KEY_PEPPER:
        return KEY_PEPPER.encode()
    if deployed():
        raise RuntimeError("DIVE_KEY_PEPPER must be set on a deployed service")
    return b"dive-local-pepper"
