"""DIVE's settings — its OWN database, its OWN sandbox key, its OWN public URL. Nothing here is the sandbox's or Sasha's."""
from __future__ import annotations

import os
import re
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

# CR 67 · the switch-on paths (docs/agapi/dive/switch-on-list.md). Each is OFF unless ALL its variables are present; with none set,
# DIVE behaves exactly as before (the sandbox captures; the test drawer plays the supplier). Values are never printed.
TWILIO_SID = os.getenv("DIVE_TWILIO_ACCOUNT_SID", "").strip()       # DIVE's OWN Twilio account — never Sasha's
TWILIO_TOKEN = os.getenv("DIVE_TWILIO_AUTH_TOKEN", "").strip()       # also signs Twilio's webhooks to /hooks/twilio/whatsapp
WHATSAPP_FROM = os.getenv("DIVE_WHATSAPP_FROM", "+14155238886").strip()   # Twilio's WhatsApp Sandbox number unless a sender is set
RESEND_READ_KEY = os.getenv("DIVE_RESEND_READ_KEY", "").strip()      # reads a received email's text; without it, the sending key
RESEND_WEBHOOK_SECRET = os.getenv("DIVE_RESEND_WEBHOOK_SECRET", "").strip()   # signs Resend's email.received to /hooks/resend/inbound
BOAT_WHATSAPP = os.getenv("DIVE_BOAT_WHATSAPP", "").strip()         # the fake site's boat number (default: the one allow-listed number)
GEAR_EMAIL = os.getenv("DIVE_GEAR_EMAIL", "").strip()               # the fake site's gear address (default: the one allow-listed inbox)

# CR 68 · the AI reader for a real operator's website: DIVE's OWN Anthropic key (off without it; the pages are still read and said so)
ANTHROPIC_KEY = os.getenv("DIVE_ANTHROPIC_API_KEY", "").strip()
READER_MODEL = os.getenv("DIVE_READER_MODEL", "claude-opus-5-5").strip()


def norm_number(n: str) -> str:
    return re.sub(r"[^\d+]", "", n or "")


WHATSAPP_ALLOW = {norm_number(a) for a in os.getenv("DIVE_WHATSAPP_ALLOW", "").split(",") if norm_number(a)}


def whatsapp_real_on() -> bool:
    """Real WhatsApp needs every piece: the on switch, DIVE's own Twilio keys, a sender and at least one allow-listed number."""
    return bool(REAL_WHATSAPP and TWILIO_SID and TWILIO_TOKEN and WHATSAPP_FROM and WHATSAPP_ALLOW)


def whatsapp_real_to(number: str) -> bool:
    return whatsapp_real_on() and norm_number(number) in WHATSAPP_ALLOW


def email_real_on() -> bool:
    return bool(RESEND_KEY and EMAIL_FROM and EMAIL_ALLOW)


def email_domain() -> str:
    """DIVE's own mail domain: the part after @ in DIVE_EMAIL_FROM (inbound mail to any other domain is not DIVE's)."""
    m = re.search(r"@([A-Za-z0-9.-]+)", EMAIL_FROM or "")
    return m.group(1).lower() if m else ""


def switches() -> dict:
    """What is switched on — booleans only, never a value."""
    return {"whatsapp_real": whatsapp_real_on(), "whatsapp_hook": bool(TWILIO_TOKEN and WHATSAPP_ALLOW),
            "email_real": email_real_on(), "email_hook": bool(RESEND_WEBHOOK_SECRET and EMAIL_ALLOW and email_domain()),
            "whatsapp_allow_count": len(WHATSAPP_ALLOW), "email_allow_count": len(EMAIL_ALLOW)}


def deployed() -> bool:
    return bool(os.getenv("RAILWAY_ENVIRONMENT_NAME"))


def pepper() -> bytes:
    if KEY_PEPPER:
        return KEY_PEPPER.encode()
    if deployed():
        raise RuntimeError("DIVE_KEY_PEPPER must be set on a deployed service")
    return b"dive-local-pepper"
