"""Sasha 228 · "ADD FROM YOUR PHONE" — S1 (/next) has nothing in the Keep and a booking that needs a passport: the page shows a
QR code + a short link (/h/<code>) that opens /s2 straight to "Add my passport" for the SAME account. The phone is never signed
in: the code IS its permission, and it permits exactly one thing — reading one passport photo into this account's Keep (the
same keep_scan read → masked card → Confirm). One-time (spent on Confirm), 10 minutes, a handful of photos at most. On Confirm
the account's open pages hear `keep_added` (live_events) and /next carries on: "Got it — Passport ES ••••456. I'll apply it."

    mint(account, kind)          → {code, expires_at}   (an open code for the same account and kind is reused)
    GET  /keep/handoff/{code}                 → {ok, kind, expires_at}   nothing about the account
    POST /keep/handoff/{code}/scan            {image, media_type} → the masked card (keep_scan.scan), nothing saved
    POST /keep/handoff/{code}/{token}/confirm → saved in the Keep, the code spent → {item: masked}
    POST /keep/handoff/{code}/{token}/discard → that reading dropped (the code stays open)
In this process only, like keep_scan's readings (one worker, R3): a restart forgets an open code — the page offers a new one.
"""
from __future__ import annotations

import base64
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional

log = logging.getLogger("agapi.keep_handoff")
NOW = lambda: datetime.now(timezone.utc)   # noqa: E731
TTL = timedelta(minutes=10)
MAX_SCANS = 6
ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"   # no 0/o, 1/l/i: typed from a screen if the camera won't
_CODES: Dict[str, dict] = {}                 # code → {account, kind, at, scans, state: open | spent}


class HandoffRefused(Exception):
    def __init__(self, rule: str, message: str) -> None:
        super().__init__(message)
        self.rule, self.message = rule, message


def _sweep() -> None:
    now = NOW()
    for c in [c for c, h in _CODES.items() if now - h["at"] > TTL]:
        _CODES.pop(c, None)


def mint(account: str, kind: str = "passport") -> dict:
    _sweep()
    for c, h in _CODES.items():
        if h["account"] == account and h["kind"] == kind and h["state"] == "open":
            return {"code": c, "kind": kind, "expires_at": (h["at"] + TTL).isoformat(timespec="seconds")}
    code = "".join(secrets.choice(ALPHABET) for _ in range(10))
    _CODES[code] = {"account": account, "kind": kind, "at": NOW(), "scans": 0, "state": "open"}
    return {"code": code, "kind": kind, "expires_at": (NOW() + TTL).isoformat(timespec="seconds")}


def _open(code: str) -> dict:
    _sweep()
    h = _CODES.get(code or "")
    if not h or h["state"] != "open":
        raise HandoffRefused("handoff_expired", "This link has expired or was already used — ask Sasha on your computer for a new one.")
    return h


def peek(code: str) -> dict:
    h = _open(code)
    return {"kind": h["kind"], "expires_at": (h["at"] + TTL).isoformat(timespec="seconds")}


async def scan(code: str, image: bytes, media_type: str) -> dict:
    from agapi import keep_scan as SCAN
    h = _open(code)
    if h["scans"] >= MAX_SCANS:
        raise HandoffRefused("handoff_spent", "That's too many photos for one link — ask Sasha on your computer for a new one.")
    h["scans"] += 1
    return await SCAN.scan(h["account"], h["kind"], image, media_type)


async def confirm(code: str, token: str) -> dict:
    from agapi import keep_scan as SCAN
    h = _open(code)
    out = await SCAN.confirm(h["account"], token)   # keep_scan.confirm tells the account's open pages (keep_added)
    h["state"] = "spent"
    return out


def discard(code: str, token: str) -> None:
    from agapi import keep_scan as SCAN
    h = _CODES.get(code or "")
    if h:
        SCAN.discard(h["account"], token)


def added_line(masked: str) -> str:
    """ "Passport ES ••••456" → "Got it — Passport ES ••••456. I'll apply it." (the mask only, ever)."""
    return f"Got it — {masked}. I'll apply it."


# ── routes (mounted under the agent router → /api/agent/keep/handoff…) ─────────────────────────────────────────────────────

from fastapi import APIRouter, Request                       # noqa: E402
from fastapi.responses import JSONResponse                   # noqa: E402

router = APIRouter()
_NS = {"Cache-Control": "no-store"}


def _no(e) -> JSONResponse:
    code = 410 if e.rule in ("handoff_expired", "handoff_spent", "scan_expired") else 503 if e.rule in ("keep_closed", "keep_unreachable") else 422
    return JSONResponse({"ok": False, "rule": e.rule, "message": e.message}, status_code=code, headers=_NS)


@router.get("/keep/handoff/{code}")
async def peek_route(code: str):
    try:
        return JSONResponse({"ok": True, **peek(code)}, headers=_NS)
    except HandoffRefused as e:
        return _no(e)


@router.post("/keep/handoff/{code}/scan")
async def scan_route(code: str, request: Request):
    from agapi.keep_scan import ScanRefused
    try:
        body = await request.json()
        image = base64.b64decode(str(body.get("image") or ""), validate=False)
    except Exception:
        return JSONResponse({"ok": False, "rule": "image_invalid", "message": "That photo couldn't be read."}, status_code=400, headers=_NS)
    try:
        out = await scan(code, image, str(body.get("media_type") or "image/jpeg"))
    except (HandoffRefused, ScanRefused) as e:
        return _no(e)
    finally:
        image, body = b"", None
    return JSONResponse({"ok": True, **out}, headers=_NS)


@router.post("/keep/handoff/{code}/{token}/{action}")
async def act_route(code: str, token: str, action: str):
    from agapi.keep_scan import ScanRefused
    from agapi.s2_keep import KeepError
    if action == "discard":
        discard(code, token)
        return JSONResponse({"ok": True}, headers=_NS)
    if action != "confirm":
        return JSONResponse({"ok": False, "rule": "unknown_action"}, status_code=404, headers=_NS)
    try:
        return JSONResponse({"ok": True, **(await confirm(code, token))}, headers=_NS)
    except (HandoffRefused, ScanRefused, KeepError) as e:
        return _no(e)


__all__ = ["mint", "peek", "scan", "confirm", "discard", "added_line", "router", "HandoffRefused", "TTL"]
