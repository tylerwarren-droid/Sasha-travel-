"""Settings, from the environment. TEST MODE is not a setting: this service has no live mode at all."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:          # Sasha's engines (agapi, booking_signer) — imported, never the agent loop
    sys.path.insert(0, str(BACKEND))

VERSION = "v1-draft"                       # becomes "v1" when EU 201's parts are implemented
DB_PATH = os.getenv("AGAPI_DB", str(ROOT / "agapi_service" / "sandbox.db"))
PUBLIC_URL = os.getenv("AGAPI_PUBLIC_URL", "http://127.0.0.1:8787").rstrip("/")
KEY_PEPPER = os.getenv("AGAPI_KEY_PEPPER", "")       # mixed into every key hash; set on the service, never in the repo
APPROVAL_TTL_S = int(os.getenv("AGAPI_APPROVAL_TTL_S", "900"))      # 15 min — the same window as Sasha's vault approvals
HOLD_TTL_S = int(os.getenv("AGAPI_HOLD_TTL_S", "1800"))
DAILY_CALLS = int(os.getenv("AGAPI_DAILY_CALLS", "1000"))           # per key per UTC day
DAILY_FINDS = int(os.getenv("AGAPI_DAILY_FINDS", "200"))            # the metered (paid-in-live) calls


def pepper() -> bytes:
    if not KEY_PEPPER:
        # a local sandbox may run without one; a deployed service refuses to start without it (app.startup)
        return b"agapi-sandbox-local-pepper"
    return KEY_PEPPER.encode()
