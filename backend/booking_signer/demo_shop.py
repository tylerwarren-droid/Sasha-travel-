"""Sasha 121 (F) · KANOE DEMO MARKET — ours, a demo shop (like the test venue): it sells nothing, charges nothing, delivers
nothing. It exists to show the VAULT doing its job on stage: a login the guest saved is opened ONLY inside the one action
they said yes to, used once, logged, and revocable in one tap.

The shop (public pages, like any shop's):
  GET  /api/booking/demo-shop               its page: what it is, its catalogue
  POST /api/booking/demo-shop/login         {username, password} → a session (a signed token, valid 30 minutes)
  POST /api/booking/demo-shop/order         {session, basket: "usual"} → its order page: "Pedido confirmado nº KDM-…"
It has ONE customer — the demo customer — whose password is derived from this server's key (stateless: a redeploy
keeps it). The founder reads it on his ops page (founder only) and saves it in HIS vault himself; no session handles it.

Sasha's side (WhatsApp): "reorder my usual from Kanoe Demo Market" → the read-back names the saved login (the vault's
own access line) and the basket → one yes → vault.use(…) opens the login inside that action → the shop's login and
order pages, over HTTPS like any shop → their order page's words back to the guest. The vault records the use.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
import re
import secrets
import time
from html import escape
from typing import Dict, List, Optional

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

log = logging.getLogger("booking_signer.demo_shop")
router = APIRouter(prefix="/demo-shop", tags=["demo-shop"])
PROVIDER = "Kanoe Demo Market"
USERNAME = "demo@kanoe-demo.market"
USUAL = [("Café de Colombia, 250 g", 2, 690), ("Pan de masa madre", 1, 420), ("Aceite de oliva virgen extra, 500 ml", 1, 940)]
SESSION_S = 30 * 60
ORDERS: List[dict] = []   # this server's memory — the demo's own book of orders


def _key() -> bytes:
    return hashlib.sha256(("kanoe-demo-market:" + (os.getenv("SASHA_BOOKING_KEY", "") or "dev")).encode()).digest()


def demo_password() -> str:
    """The demo customer's password — derived, never stored; the founder reads it on his ops page."""
    return "kdm-" + hmac.new(_key(), b"password", hashlib.sha256).hexdigest()[:12]


def euros(minor: int) -> str:
    return f"€{minor // 100},{minor % 100:02d}"


def total() -> int:
    return sum(q * p for _, q, p in USUAL)


def usual_words() -> str:
    return ", ".join(f"{q} × {n}" for n, q, _ in USUAL) + f" — {euros(total())}"


def _session(username: str, now: float) -> str:
    exp = str(int(now) + SESSION_S)
    sig = hmac.new(_key(), f"{username}|{exp}".encode(), hashlib.sha256).hexdigest()[:24]
    return f"{exp}.{sig}"


def _session_ok(token: str, now: float) -> bool:
    m = re.fullmatch(r"(\d{10})\.([0-9a-f]{24})", token or "")
    if not m or int(m[1]) < now:
        return False
    return hmac.compare_digest(m[2], hmac.new(_key(), f"{USERNAME}|{m[1]}".encode(), hashlib.sha256).hexdigest()[:24])


_PAGE = """<!doctype html><html lang="es"><head><meta charset="utf-8"><title>Kanoe Demo Market</title>
<meta property="og:site_name" content="Kanoe Demo Market"></head><body><h1>Kanoe Demo Market</h1>
<p>Tienda de demostración de Kanoe. No es una tienda real: no vende, no cobra y no envía nada. Existe para enseñar cómo Sasha
usa un acceso guardado en tu bóveda, solo dentro de la acción que apruebas.</p>
<h2>Tu pedido habitual</h2><ul>{items}</ul><p>Total: {total}</p></body></html>"""


@router.get("", response_class=HTMLResponse)
async def page():
    items = "".join(f"<li>{q} × {escape(n)} — {euros(p)}</li>" for n, q, p in USUAL)
    return HTMLResponse(_PAGE.format(items=items, total=euros(total())))


async def _form(request: Request) -> Dict[str, str]:
    try:
        j = await request.json()
        return {k: str(v) for k, v in (j or {}).items()}
    except Exception:
        return {k: str(v) for k, v in (await request.form()).items()}


@router.post("/login")
async def login(request: Request):
    f = await _form(request)
    if f.get("username") != USERNAME or not hmac.compare_digest(f.get("password", ""), demo_password()):
        return JSONResponse({"ok": False, "message": "Usuario o contraseña incorrectos."}, status_code=401)
    return {"ok": True, "session": _session(USERNAME, time.time()), "message": "Sesión iniciada."}


@router.post("/order", response_class=HTMLResponse)
async def order(request: Request):
    f = await _form(request)
    if not _session_ok(f.get("session", ""), time.time()):
        return HTMLResponse("<p>Inicia sesión primero.</p>", status_code=401)
    if f.get("basket") != "usual":
        return HTMLResponse("<p>Esa cesta no existe.</p>", status_code=422)
    ref = "KDM-" + secrets.token_hex(3).upper()
    ORDERS.append({"ref": ref, "at": time.time(), "total": total()})
    del ORDERS[:-50]
    items = "".join(f"<li>{q} × {escape(n)}</li>" for n, q, _ in USUAL)
    return HTMLResponse(f"<html><body><h1>Pedido confirmado</h1><p>Pedido nº {ref}: tu pedido habitual.</p><ul>{items}</ul>"
                        f"<p>Total: {euros(total())} (demostración: no se cobra nada).</p></body></html>")


# ── the founder's ops side ─────────────────────────────────────────────────────────────────────────────────────────

ops = APIRouter(prefix="/ops", tags=["booking-ops"])


@ops.get("/demo-shop-login")
async def demo_login_for_founder(request: Request):
    """The demo customer's login, for the founder to save in HIS vault himself (founder only)."""
    from .ops import founder_only
    no = founder_only(request)
    if no:
        return no
    return {"provider": PROVIDER, "username": USERNAME, "password": demo_password(), "shop": f"{_base()}/api/booking/demo-shop",
            "say": "Save it in You → My accounts (the vault): site 'Kanoe Demo Market', kind 'Password'."}


def _base() -> str:
    from .form_rung import public_base
    return public_base()


# ── Sasha's side: the reorder, on WhatsApp ────────────────────────────────────────────────────────────────────────

REORDER = re.compile(r"\b(re-?order|order again|pide (otra vez|de nuevo)|repite)\b.*\b(kanoe demo market|demo market)\b"
                     r"|\b(kanoe demo market|demo market)\b.*\b(re-?order|my usual|lo de siempre)\b", re.I)


def read_back(label: str) -> List[str]:
    from .vault.crypto import access_line
    return [access_line(PROVIDER, label), f"I'll reorder your usual there: {usual_words()}.",
            "It's Kanoe's demo shop: nothing is paid and nothing is delivered. I place the order once."]


async def find_item(account: str) -> Optional[dict]:
    from .vault import crypto as VC
    rows = await VC.STORE.list(account)
    return next((r for r in rows if not r.get("revoked_at") and str(r.get("provider") or "").strip().lower() == PROVIDER.lower()
                 and r.get("kind") in ("password", "app_password")), None)


async def _post(url: str, body: dict):
    """(status, text) — the shop over HTTPS, like any shop."""
    import httpx
    async with httpx.AsyncClient(timeout=httpx.Timeout(20.0)) as c:
        r = await c.post(url, json=body)
    return r.status_code, r.text


POST = _post   # tests replace it


async def place(account: str, item_id: str, lines: List[str], sha: str, approved_at: str, action_ref: str) -> Dict[str, str]:
    """Inside ONE vault use: the shop's login, then its order. Returns their order page's words (secrets scrubbed)."""
    import json as _json
    from .vault import crypto as VC
    from .form_rung import _LiveForm_text
    approval = {"read_back_sha256": sha, "at": approved_at}
    async with VC.use(account, item_id, approval=approval, approved_lines=lines, action_kind="demo_shop_order", action_ref=action_ref) as secret:
        s, t = await POST(f"{_base()}/api/booking/demo-shop/login",
                          {"username": secret.get("username") or "", "password": secret.get("password") or ""})
        if s != 200:
            raise RuntimeError(f"the shop refused the login: HTTP {s}")
        session = _json.loads(t).get("session")
        s2, page = await POST(f"{_base()}/api/booking/demo-shop/order", {"session": session, "basket": "usual"})
        text = " ".join(" ".join(_LiveForm_text(page or "")).split())[:1500]
        return {"status": "ordered" if s2 == 200 and "Pedido confirmado" in text else "not_ordered",
                "their_page": secret.scrub(text), "ref": (re.search(r"KDM-[0-9A-F]{6}", text) or [None])[0] or ""}


__all__ = ["router", "ops", "REORDER", "read_back", "find_item", "place", "demo_password", "USERNAME", "PROVIDER"]
