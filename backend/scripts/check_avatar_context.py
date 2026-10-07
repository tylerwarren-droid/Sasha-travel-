"""Sasha 200 · THE AVATAR'S OPENING, CHECKED — does the live LiveAvatar context say what we expect?

Asks the web app (the HeyGen key lives only on Vercel) — GET {SASHA_WEB_URL}/api/heygen/context with the booking key — and
passes when its opening_text and prompt equal frontend/lib/avatar-context.mjs. Run on its own, or every 6 h inside the live
suite (scripts/live_suite.py), which emails a failure. `--apply` sets the context to the expected text (ops), then checks.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request

WEB = os.getenv("SASHA_WEB_URL", "https://project.kanoe.ai").rstrip("/")


def _call(method: str, body: dict | None = None) -> dict:
    req = urllib.request.Request(f"{WEB}/api/heygen/context", method=method, data=json.dumps(body).encode() if body else None,
                                 headers={"x-sasha-booking-key": os.environ.get("SASHA_BOOKING_KEY", ""), "content-type": "application/json",
                                          "user-agent": "sasha-ops/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return {"ok": False, "status": e.code, "body": e.read()[:300].decode("utf-8", "replace")}


def check() -> dict:
    """{ok, opening_text, why}."""
    j = _call("GET")
    if not j.get("ok"):
        return {"ok": False, "why": f"the context could not be read: {j}"}
    m = j.get("matches") or {}
    why = [w for w, good in (("the opening text differs", m.get("opening")), ("the prompt differs", m.get("prompt"))) if not good]
    return {"ok": not why, "opening_text": j.get("opening_text"), "why": "; ".join(why)}


if __name__ == "__main__":
    if "--apply" in sys.argv:
        r = _call("POST", {"apply": True})
        print("applied:", r.get("ok"), "| before:", json.dumps((r.get("before") or {}), ensure_ascii=False)[:2000])
    c = check()
    print(f"{'PASS' if c['ok'] else 'FAIL'} · the avatar's context — opening: {c.get('opening_text')!r}{(' — ' + c['why']) if c.get('why') else ''}")
    sys.exit(0 if c["ok"] else 1)
