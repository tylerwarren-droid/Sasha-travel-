"""Sasha 126 (3) · KANOE DEMO SPA — ours, a demo member portal (like Kanoe Demo Market): it takes no money and no real
appointment. It shows the VAULT inside the booking story: a membership login the guest saved is opened ONLY inside the one
booking they said yes to, used once, logged, and revocable in one tap.

⛔ It is NOT named after any real spa. (The founder's storyline said "my Calma membership": Calma Madrid is a real
business, and a fake portal in its name would impersonate it. The real Calma is asked separately to be the friendly
spa for a live booking — docs/business/investor-demo-v2.md.)

The portal (public pages, like any member portal):
  GET  /api/booking/demo-spa          what it is, its treatments
  POST /api/booking/demo-spa/login    {username, password} → a session (30 minutes)
  POST /api/booking/demo-spa/book     {session, treatment, date, time} → "Reserva confirmada nº KDS-…"
ONE member, whose password is derived from the server key; the founder reads it on his ops page and saves it in HIS vault.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import time
import uuid
from datetime import date, datetime
from html import escape
from typing import Dict, List, Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

log = logging.getLogger("booking_signer.demo_spa")
router = APIRouter(prefix="/demo-spa", tags=["demo-spa"])
ops = APIRouter(prefix="/ops", tags=["booking-ops"])
PROVIDER = "Kanoe Demo Spa"
USERNAME = "member@kanoe-demo.spa"
TREATMENT = ("relaxing-60", "Masaje relajante, 60 min", "a 60-minute relaxing massage")
SESSION_S = 30 * 60
BOOKINGS: List[dict] = []   # this server's memory — the demo portal's own book


def _key() -> bytes:
    return hashlib.sha256(("kanoe-demo-spa:" + (os.getenv("SASHA_BOOKING_KEY", "") or "dev")).encode()).digest()


def demo_password() -> str:
    return "kds-" + hmac.new(_key(), b"password", hashlib.sha256).hexdigest()[:12]


def _session(now: float) -> str:
    exp = str(int(now) + SESSION_S)
    return f"{exp}.{hmac.new(_key(), f'{USERNAME}|{exp}'.encode(), hashlib.sha256).hexdigest()[:24]}"


def _session_ok(token: str, now: float) -> bool:
    m = re.fullmatch(r"(\d{10})\.([0-9a-f]{24})", token or "")
    return bool(m) and int(m[1]) >= now and hmac.compare_digest(m[2], hmac.new(_key(), f"{USERNAME}|{m[1]}".encode(), hashlib.sha256).hexdigest()[:24])


_PAGE = """<!doctype html><html lang="es"><head><meta charset="utf-8"><title>Kanoe Demo Spa — socios</title>
<meta property="og:site_name" content="Kanoe Demo Spa"></head><body><h1>Kanoe Demo Spa</h1>
<p>Portal de socios de demostración de Kanoe. No es un spa real: no cobra y no da citas reales. Existe para enseñar cómo
Sasha usa un acceso guardado en tu bóveda, solo dentro de la reserva que apruebas.</p>
<h2>Tratamientos</h2><ul><li>{t}</li></ul></body></html>"""


@router.get("", response_class=HTMLResponse)
async def page():
    return HTMLResponse(_PAGE.format(t=escape(TREATMENT[1])))


async def _form(request: Request) -> Dict[str, str]:
    try:
        return {k: str(v) for k, v in ((await request.json()) or {}).items()}
    except Exception:
        return {k: str(v) for k, v in (await request.form()).items()}


@router.post("/login")
async def login(request: Request):
    f = await _form(request)
    if f.get("username") != USERNAME or not hmac.compare_digest(f.get("password", ""), demo_password()):
        return JSONResponse({"ok": False, "message": "Usuario o contraseña incorrectos."}, status_code=401)
    return {"ok": True, "session": _session(time.time())}


_DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
_MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


@router.post("/book", response_class=HTMLResponse)
async def book(request: Request):
    f = await _form(request)
    if not _session_ok(f.get("session", ""), time.time()):
        return HTMLResponse("<p>Inicia sesión primero.</p>", status_code=401)
    if f.get("treatment") != TREATMENT[0]:
        return HTMLResponse("<p>Ese tratamiento no existe.</p>", status_code=422)
    try:
        d = date.fromisoformat(f.get("date", ""))
        t = f.get("time", "")
        assert re.fullmatch(r"\d{2}:\d{2}", t)
    except Exception:
        return HTMLResponse("<p>Elige día y hora.</p>", status_code=422)
    ref = "KDS-" + secrets.token_hex(3).upper()
    BOOKINGS.append({"ref": ref, "date": d.isoformat(), "time": t, "at": time.time()})
    del BOOKINGS[:-50]
    return HTMLResponse(f"<html><body><h1>Reserva confirmada</h1><p>Cita nº {ref}: {escape(TREATMENT[1])}, {_DIAS[d.weekday()]} "
                        f"{d.day} de {_MESES[d.month - 1]} a las {escape(t)}.</p><p>(Demostración: no se cobra nada.)</p></body></html>")


@ops.get("/demo-spa-login")
async def demo_login_for_founder(request: Request):
    from .ops import founder_only
    no = founder_only(request)
    if no:
        return no
    return {"provider": PROVIDER, "username": USERNAME, "password": demo_password(), "portal": f"{_base()}/api/booking/demo-spa",
            "say": "Save it in You → My accounts (the vault): site 'Kanoe Demo Spa', kind 'Password'."}


def _base() -> str:
    from .form_rung import public_base
    return public_base()


# ── Sasha's side ────────────────────────────────────────────────────────────────────────────────────────────────────

INTENT = re.compile(r"\b(spa|massage|masaje)\b.*\b(membership|member|socio|membres[ií]a)\b|\b(membership|socio)\b.*\b(spa|massage|masaje)\b"
                    r"|\bkanoe demo spa\b", re.I)


def read_back(label: str, at: str) -> List[str]:
    from .vault.crypto import access_line
    from . import sentences as SN
    return [access_line(PROVIDER, label), f"I'll book {TREATMENT[2]} there: {SN.day_words(at[:10])} at {at[11:16]}.",
            "It's Kanoe's demo spa: nothing is paid, and it's not a real appointment. I book once."]


async def find_item(account: str) -> Optional[dict]:
    from .vault import crypto as VC
    rows = await VC.STORE.list(account)
    return next((r for r in rows if not r.get("revoked_at") and str(r.get("provider") or "").strip().lower() == PROVIDER.lower()
                 and r.get("kind") in ("password", "app_password")), None)


async def _post(url: str, body: dict):
    import httpx
    async with httpx.AsyncClient(timeout=httpx.Timeout(20.0)) as c:
        r = await c.post(url, json=body)
    return r.status_code, r.text


POST = _post   # tests replace it


async def _record(account: str, at: str, ref: str) -> Optional[str]:
    """The booking on the guest's own list (and so their calendar): inserted as requested, then confirmed — the
    calendar's trigger fires on the change."""
    from . import ladder_routes as LR
    from .store import BOOKINGS_TRIP_TITLE
    if not hasattr(LR.LADDER_STORE, "_run"):
        return None
    dt = datetime.fromisoformat(at).replace(tzinfo=ZoneInfo("Europe/Madrid"))

    async def go(c):
        async with c.transaction():
            a = uuid.UUID(account)
            trip = await c.fetchval("select id from trips where owner_id = $1 and title = $2 limit 1", a, BOOKINGS_TRIP_TITLE)
            if trip is None:
                trip = await c.fetchval("insert into trips (owner_id, title) values ($1,$2) returning id", a, BOOKINGS_TRIP_TITLE)
            tid = await c.fetchval("insert into trip_items (trip_id, type, status, provider_name, date_time, party_size, local_timezone) "
                                   "values ($1,'beauty','requested',$2,$3,1,'Europe/Madrid') returning id", trip, PROVIDER, dt)
            await c.execute("update trip_items set status = 'confirmed', booking_reference = $2, updated_at = now() where id = $1", tid, ref)
            return str(tid)
    return await LR.LADDER_STORE._run(go)


RECORD = _record   # tests replace it


async def place(account: str, item_id: str, lines: List[str], sha: str, approved_at: str, at: str, action_ref: str) -> Dict[str, str]:
    from .vault import crypto as VC
    from .form_rung import _LiveForm_text
    approval = {"read_back_sha256": sha, "at": approved_at}
    async with VC.use(account, item_id, approval=approval, approved_lines=lines, action_kind="demo_spa_booking", action_ref=action_ref) as secret:
        s, t = await POST(f"{_base()}/api/booking/demo-spa/login", {"username": secret.get("username") or "", "password": secret.get("password") or ""})
        if s != 200:
            raise RuntimeError(f"the portal refused the login: HTTP {s}")
        s2, page_ = await POST(f"{_base()}/api/booking/demo-spa/book",
                               {"session": json.loads(t).get("session"), "treatment": TREATMENT[0], "date": at[:10], "time": at[11:16]})
        text = secret.scrub(" ".join(" ".join(_LiveForm_text(page_ or "")).split())[:1200])
    ok = s2 == 200 and "Reserva confirmada" in text
    ref = (re.search(r"KDS-[0-9A-F]{6}", text) or [None])[0] or ""
    tid = await RECORD(account, at, ref) if ok else None
    return {"status": "booked" if ok else "not_booked", "their_page": text, "ref": ref, "trip_item_id": tid or ""}


__all__ = ["router", "ops", "INTENT", "read_back", "find_item", "place", "demo_password", "USERNAME", "PROVIDER", "TREATMENT"]
