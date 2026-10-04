"""Sasha 121 · the INVESTOR DEMO v2 in one command (docs/business/investor-demo-v2.md). Founder's account only; every
action goes through the live server's founder-only ops routes, exactly as the ops page's buttons do.

    railway run -- python backend/scripts/demo.py reset        # before each run: the demo back to the start
    railway run -- python backend/scripts/demo.py status       # what's set up: WhatsApp, Calendar, Gmail, place, vault, calls
    railway run -- python backend/scripts/demo.py leave-now    # beat E: the "time to leave" on his phone, now
    railway run -- python backend/scripts/demo.py gmail        # beat G: our test venue emails his Gmail; Sasha offers it
    railway run -- python backend/scripts/demo.py shop-login   # beat F setup: the demo shop's login, to save in his vault
    railway run -- python backend/scripts/demo.py spa-login    # Sasha 126 setup: the demo spa's membership, to save in his vault
    railway run -- python backend/scripts/demo.py prewarm      # Sasha 140 · the night before: venues' photos and reads warmed

Needs SASHA_BOOKING_KEY (railway run provides it). Prints no secret but the demo shop's own demo password.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request

API = os.getenv("SASHA_API", "https://sasha-travel-production.up.railway.app").rstrip("/")
H = {"x-sasha-booking-key": os.environ.get("SASHA_BOOKING_KEY", "").strip(), "x-sasha-session": "founder", "content-type": "application/json"}


def call(method: str, path: str, body=None):
    req = urllib.request.Request(API + path, method=method, headers=H, data=json.dumps(body).encode() if body is not None else None)
    t = time.time()
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            out = json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        out = json.loads(e.read() or b"{}")
    return round(time.time() - t, 1), out


def status() -> None:
    for name, path in (("health", "/api/booking/health"), ("WhatsApp", "/api/booking/whatsapp"), ("Calendar", "/api/booking/google"),
                       ("Gmail", "/api/booking/mailbox"), ("reminders", "/api/booking/proactive"), ("vault", "/api/booking/vault")):
        s, j = call("GET", path)
        if name == "health":
            print(f"calls: {'ON' if (j.get('calls') or {}).get('enabled') else 'off'} · rehearsal card: see SASHA_REHEARSAL · "
                  f"vault: {(j.get('vault') or {}).get('backend')}")
        elif name == "WhatsApp":
            print(f"WhatsApp linked: {j.get('linked')}")
        elif name == "Calendar":
            print(f"Calendar connected: {j.get('connected')}")
        elif name == "Gmail":
            print(f"Gmail connected: {j.get('connected')} · waiting finds: {sum(1 for f in j.get('finds', []) if f.get('status') == 'offered')}")
        elif name == "reminders":
            print(f"reminders: {'off' if (j.get('prefs') or {}).get('all_off') else 'on'} · starting point: {(j.get('place') or {}).get('label')}")
        elif name == "vault":
            for site, addr in (("Kanoe Demo Market", "demo-market.kanoe.ai"), ("Kanoe Demo Spa", "demo-spa.kanoe.ai")):
                have = [i for i in j.get("items", []) if i.get("provider") in (site, addr) and not i.get("revoked_at")]
                print(f"vault: {site} login saved ({addr}): {bool(have)}")


def main(cmd: str) -> None:
    if cmd == "status":
        return status()
    path = {"reset": ("POST", "/api/booking/ops/demo/reset"), "leave-now": ("POST", "/api/booking/ops/demo/leave-now"),
            "gmail": ("POST", "/api/booking/ops/demo/gmail-seed"), "shop-login": ("GET", "/api/booking/ops/demo-shop-login"),
            "spa-login": ("GET", "/api/booking/ops/demo-spa-login"), "prewarm": ("POST", "/api/booking/ops/demo/prewarm")}.get(cmd)
    if path is None:
        sys.exit(__doc__)
    secs, out = call(*path)
    print(f"{cmd} ({secs}s): {json.dumps(out, ensure_ascii=False, indent=1)}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "")
