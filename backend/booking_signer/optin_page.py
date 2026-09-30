"""S-55 · "WORK WITH SASHA" — the page a venue opts in on (S-49 §2 method 3, S-50 §3). The server half.

    GET  /api/booking/optin/status         is the page open? (SASHA_OPTIN_PAGE_ENABLED, the mail key, the public URL)
    GET  /api/booking/optin/wordings       the three v2 wordings a venue is shown, in en or es (wordings.py)
    POST /api/booking/optin/requests       the form → a pending request + ONE email with the confirmation link
    POST /api/booking/optin/preview        {t} → what confirming would record (writes nothing)
    POST /api/booking/optin/confirm        {t} → one venue_optins row per ticked channel, with its full evidence
    POST /api/booking/optin/withdraw       {t} → a withdrawn row for every channel of that venue

The page reaches these through frontend/app/api/work-with-sasha (no founder session: a venue has none), which adds
SASHA_BOOKING_KEY server-side; the browser never sees it.

What makes a row count (S-49 §2):
  · ⛔ nothing is ticked for the venue — a channel is recorded only if its box was ticked, and the wording it records is
    the one the page SHOWED: the page sends the sha256 of each text it displayed and a mismatch is refused;
  · ⛔ "I am authorised to agree for this venue" must be ticked — and the record says the authority is STATED, not verified;
  · ⛔ double opt-in: the row is written only when the link emailed to the address given is opened AND "Confirm" is
    pressed. Opening the link writes nothing, because mail scanners open links on their own;
  · ⛔ an old link never undoes a withdrawal: a venue that withdrew after the request was made is refused (S-49 §5).

Withdrawing needs no confirmation: the same link's withdraw page records a withdrawal for every channel of the venue,
which the refusal check (optins.py) then applies to phone and email as well — any stop ends every channel.

Abuse: a public form that sends email. At most OPTIN_PER_EMAIL_PER_DAY requests to one address, and OPTIN_PER_DAY in
all, in any 24 hours; the link lives LINK_VALID. SQL: sql/009_venue_optin_requests.sql.
"""
from __future__ import annotations

import functools
import hashlib
import os
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urlsplit

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from . import emailing as E
from . import ladder_routes
from . import optins as O
from .calls import _E164
from .store import AlreadyRecorded, StorageUnavailable
from .wordings import CURRENT_OPTIN_VERSION, OPTIN_WORDINGS, optin_wording

router = APIRouter(prefix="/optin")

CHANNELS = ("whatsapp", "web_submit", "email_confirm")
LANGS = ("en", "es")
LINK_VALID = timedelta(hours=48)
OPTIN_PER_EMAIL_PER_DAY = 3
OPTIN_PER_DAY = 30
PAGE_STORE: Any = None     # set by routes.py
HTTP: Any = None           # None = the email rung's own client (ladder_routes.HTTP); tests set a fake
NOW = lambda: datetime.now(timezone.utc)   # noqa: E731


def _env(n: str) -> str:
    return os.getenv(n, "").strip()


def public_url() -> str:
    return _env("SASHA_PUBLIC_URL").rstrip("/")


def page_ready() -> Optional[str]:
    """None when the page may take requests; else what it waits for, in words."""
    missing = [v for v in ("SASHA_RESEND_API_KEY", "SASHA_EMAIL_FROM", "SASHA_PUBLIC_URL") if not _env(v)]
    if _env("SASHA_OPTIN_PAGE_ENABLED") != "1":
        missing.insert(0, "SASHA_OPTIN_PAGE_ENABLED=1")
    return f"the page waits for {', '.join(missing)} on the server" if missing else None


def token_sha(t: str) -> str:
    return hashlib.sha256(t.encode("utf-8")).hexdigest()


class Refused(Exception):
    def __init__(self, status: int, rule: str, message: str) -> None:
        super().__init__(message)
        self.status, self.rule, self.message = status, rule, message


def _refuse(status: int, rule: str, message: str) -> JSONResponse:
    return JSONResponse({"ok": False, "rule": rule, "message": message}, status_code=status)


def _text(body: dict, key: str, lo: int, hi: int, what: str) -> str:
    v = re.sub(r"\s+", " ", str(body.get(key) or "")).strip()
    if not (lo <= len(v) <= hi):
        raise Refused(422, f"{key}_invalid", f"{what} must be {lo}–{hi} characters")
    return v


def _url(v: Any, what: str) -> str:
    s = str(v or "").strip()
    parts = urlsplit(s)
    if len(s) > 500 or parts.scheme not in ("http", "https") or not parts.hostname or "." not in parts.hostname:
        raise Refused(422, "url_invalid", f"{what} must be a full web address starting with https://")
    return s


def parse_request(body: dict) -> dict:
    """The form → what would be recorded. Every wording is worked out HERE and checked against what the page showed."""
    lang = body.get("lang") if body.get("lang") in LANGS else None
    if not lang:
        raise Refused(422, "lang_invalid", "lang is en or es")
    venue_name = _text(body, "venue_name", 2, 120, "The venue's name")
    country = str(body.get("country") or "ES").strip().upper()
    if not re.fullmatch(r"[A-Z]{2}", country):
        raise Refused(422, "country_invalid", "country is a two-letter code")
    website = _url(body["website"], "The venue's website") if str(body.get("website") or "").strip() else None
    contact_name = _text(body, "contact_name", 2, 80, "Your name")
    contact_role = _text(body, "contact_role", 2, 60, "Your role")
    email = str(body.get("email") or "").strip()
    if len(email) > 254 or not E._EMAIL.fullmatch(email):
        raise Refused(422, "email_invalid", "The email address is not a valid address")
    if body.get("authorised") is not True:
        raise Refused(422, "not_authorised", "Only someone authorised to agree for the venue can opt it in; the box was not ticked")
    ticked = body.get("channels") if isinstance(body.get("channels"), dict) else {}
    unknown = set(ticked) - set(CHANNELS)
    if unknown:
        raise Refused(422, "channel_unknown", f"not a channel: {sorted(unknown)}")
    if not ticked:
        raise Refused(422, "nothing_ticked", "Tick at least one channel; nothing is ticked for you")
    shown = body.get("shown") if isinstance(body.get("shown"), dict) else {}
    channels = []
    for ch in CHANNELS:
        if ch not in ticked:
            continue
        v = ticked[ch] if isinstance(ticked[ch], dict) else {}
        if ch == "whatsapp":
            scope = re.sub(r"[\s().-]", "", str(v.get("number") or ""))
            if not _E164.fullmatch(scope):
                raise Refused(422, "number_invalid", "The WhatsApp number must be in international form, e.g. +34 600 111 222")
            w = optin_wording(ch, lang)
        elif ch == "web_submit":
            scope = _url(v.get("url"), "The booking form's address")
            w = optin_wording(ch, lang, url=scope)
        else:
            scope = email.lower()
            w = optin_wording(ch, lang)
        if shown.get(ch) != w["sha256"]:
            raise Refused(409, "wording_changed", f"The {ch} wording the page showed is not the wording that would be recorded; reload the page")
        channels.append({"channel": ch, "scope": scope, "wording_version": w["version"], "wording_lang": w["lang"],
                         "wording_sha256": w["sha256"], "wording_text": w["text"]})
    venue_id = O.host_id(website) if website else O.name_id(venue_name, country)
    submitted = {k: body.get(k) for k in ("lang", "venue_name", "country", "website", "contact_name", "contact_role",
                                          "email", "authorised", "channels", "shown")}
    return {"lang": lang, "venue_id": venue_id, "venue_name": venue_name, "contact_name": contact_name,
            "contact_role": contact_role, "email": email, "channels": channels, "submitted": submitted}


_LABEL = {"en": {"whatsapp": "WhatsApp", "web_submit": "Your booking form", "email_confirm": "Email confirmation"},
          "es": {"whatsapp": "WhatsApp", "web_submit": "Vuestro formulario de reservas", "email_confirm": "Confirmación por email"}}


def confirmation_email(req: dict, token: str) -> dict:
    base = public_url()
    q = f"?t={token}&lang={req['lang']}"
    confirm, withdraw = f"{base}/work-with-sasha/confirm{q}", f"{base}/work-with-sasha/withdraw{q}"
    privacy = f"{base}/sasha-privacy?lang={req['lang']}"
    items = "\n".join(f"- {_LABEL[req['lang']][c['channel']]} ({c['scope']}): \"{c['wording_text']}\"" for c in req["channels"])
    if req["lang"] == "es":
        subject = f"Confirmad: Sasha para {req['venue_name']}"
        text = (f"Hola, {req['contact_name']}:\n\n"
                f"Se ha pedido en {base} que Sasha, una concierge de inteligencia artificial operada por Kanoe Technologies SL, "
                f"trabaje con {req['venue_name']}. No empieza nada hasta que lo confirméis aquí:\n\n{confirm}\n\n"
                f"Estaríais aceptando:\n{items}\n\n"
                f"El enlace vale 48 horas. Si no lo habéis pedido vosotros, ignorad este email y no se registrará nada.\n\n"
                f"Después podéis retirarlo cuando queráis aquí (se paran todos los canales de Sasha con vuestro establecimiento):\n{withdraw}\n\n"
                f"Cómo usamos vuestros datos (borrador, pendiente de revisión legal): {privacy}\n\n"
                f"Kanoe Technologies SL · tyler@kanoe.ai")
    else:
        subject = f"Confirm: Sasha for {req['venue_name']}"
        text = (f"Hello {req['contact_name']},\n\n"
                f"Someone asked on {base} for Sasha, an AI concierge operated by Kanoe Technologies SL, to work with "
                f"{req['venue_name']}. Nothing starts until you confirm here:\n\n{confirm}\n\n"
                f"You would be agreeing to:\n{items}\n\n"
                f"The link works for 48 hours. If this wasn't you, ignore this email and nothing will be recorded.\n\n"
                f"Afterwards you can withdraw at any time here (every one of Sasha's channels to your venue stops):\n{withdraw}\n\n"
                f"How we use your details (a draft, under legal review): {privacy}\n\n"
                f"Kanoe Technologies SL · tyler@kanoe.ai")
    return {"from": _env("SASHA_EMAIL_FROM"), "to": req["email"], "subject": subject, "text": text}


def view(req: dict) -> dict:
    """What a confirm or withdraw page shows — no token, no hash of one."""
    return {"venue_name": req["venue_name"], "contact_name": req["contact_name"], "contact_role": req["contact_role"],
            "email": req["email"], "lang": req["lang"],
            "channels": [{k: c[k] for k in ("channel", "scope", "wording_text")} for c in req["channels"]],
            "expires_at": req["expires_at"].isoformat(), "confirmed_at": req["confirmed_at"].isoformat() if req.get("confirmed_at") else None,
            "withdrawn_at": req["withdrawn_at"].isoformat() if req.get("withdrawn_at") else None}


def active_row(req: dict, c: dict, now: datetime) -> dict:
    return {"venue_id": req["venue_id"], "channel": c["channel"], "scope": c["scope"], "status": "active", "recorded_at": now,
            "agreed_by_name": req["contact_name"], "agreed_by_role": req["contact_role"], "agreed_at": now, "method": "form",
            "wording_version": c["wording_version"], "wording_sha256": c["wording_sha256"], "wording_text": c["wording_text"],
            "evidence": {"request_id": str(req["request_id"]), "submitted_at": req["created_at"].isoformat(),
                         "submitted": req["submitted"], "wording_lang": c.get("wording_lang"),
                         "confirmation_email": {"to": req["email"], "provider_id": req["email_provider_id"]},
                         "confirmed_at": now.isoformat(),
                         "confirmed_how": "the link emailed to that address was opened and Confirm was pressed",
                         "authority": "stated by the person who ticked the box, not verified"}}


def withdrawn_rows(req: dict, active_chains: List[tuple], now: datetime) -> List[dict]:
    """A withdrawal for every chain the venue has live, and for each channel this request named: any stop ends every channel."""
    chains = list(dict.fromkeys([*active_chains, *[(c["channel"], c["scope"]) for c in req["channels"]]]))
    return [{"venue_id": req["venue_id"], "channel": ch, "scope": sc, "status": "withdrawn", "recorded_at": now,
             "withdrawn_at": now, "withdrawn_how": "form_link",
             "withdrawn_evidence": {"request_id": str(req["request_id"]), "at": now.isoformat(),
                                    "how": "the withdraw link emailed for this request was opened and Withdraw was pressed"}}
            for ch, sc in chains]


# ── stores ─────────────────────────────────────────────────────────────────────────────────────

class MemoryPageStore:
    def __init__(self, optins: O.MemoryOptinStore) -> None:
        self.requests: Dict[str, dict] = {}
        self.optins = optins

    async def counts(self, email: str, since: datetime) -> tuple:
        recent = [r for r in self.requests.values() if r["created_at"] >= since]
        return sum(1 for r in recent if r["email"].lower() == email.lower()), len(recent)

    async def put(self, rec: dict) -> None:
        self.requests[rec["token_sha256"]] = dict(rec)

    async def mark_email(self, tsha: str, status: str, provider_id: Optional[str], why: Optional[str]) -> None:
        self.requests[tsha].update(email_status=status, email_provider_id=provider_id, email_why=why)

    async def get(self, tsha: str) -> Optional[dict]:
        r = self.requests.get(tsha)
        return dict(r) if r else None

    async def confirm(self, tsha: str, now: datetime) -> dict:
        req = self.requests.get(tsha)
        _confirmable(req, now, req is not None and any(
            r["venue_id"] == req["venue_id"] and r["status"] == "withdrawn" and r["recorded_at"] > req["created_at"] for r in self.optins.rows))
        if req["confirmed_at"]:
            return {"already": True, "req": dict(req)}
        for c in req["channels"]:
            await self.optins.add(active_row(req, c, now))
        req["confirmed_at"] = now
        return {"already": False, "req": dict(req)}

    async def withdraw(self, tsha: str, now: datetime) -> dict:
        req = self.requests.get(tsha)
        if req is None:
            raise Refused(404, "link_unknown", "This link is not one we sent, or it has been deleted")
        latest: Dict[tuple, dict] = {}
        for r in sorted((r for r in self.optins.rows if r["venue_id"] == req["venue_id"]), key=lambda r: (r["recorded_at"], r["id"])):
            latest[(r["channel"], r["scope"])] = r
        rows = withdrawn_rows(req, [k for k, r in latest.items() if r["status"] == "active"], now)
        for row in rows:
            await self.optins.add(row)
        req["withdrawn_at"] = req.get("withdrawn_at") or now
        return {"req": dict(req), "rows": len(rows)}


def _confirmable(req: Optional[dict], now: datetime, withdrawn_since: bool) -> None:
    if req is None:
        raise Refused(404, "link_unknown", "This link is not one we sent, or it has been deleted")
    if req["confirmed_at"]:
        return
    if req["email_status"] != "sent":
        raise Refused(409, "link_never_sent", "The email with this link was never accepted for delivery, so it cannot confirm anything")
    if req.get("withdrawn_at") or withdrawn_since:
        raise Refused(409, "withdrawn_since", "This venue withdrew after this request was made; an old link never undoes a withdrawal. Please ask again on the page")
    if now > req["expires_at"]:
        raise Refused(410, "link_expired", "This link has expired (48 hours); please ask again on the page")


_REQ_COLS = ("request_id, token_sha256, created_at, expires_at, lang, venue_id, venue_name, contact_name, contact_role, "
             "email, channels, submitted, email_status, email_provider_id, email_why, confirmed_at, withdrawn_at")


class PostgresPageStore:
    def __init__(self, base) -> None:
        self._base = base

    async def _run(self, fn):
        try:
            return await self._base._run(fn)
        except StorageUnavailable as e:
            raise e.rehint("009_venue_optin_requests.sql") from None

    @staticmethod
    def _req(r) -> Optional[dict]:
        import json
        if r is None:
            return None
        d = dict(r)
        for k in ("channels", "submitted"):
            d[k] = json.loads(d[k]) if isinstance(d[k], str) else d[k]
        return d

    async def counts(self, email: str, since: datetime) -> tuple:
        r = await self._run(lambda c: c.fetchrow(
            "select count(*) filter (where lower(email) = lower($1)) as mine, count(*) as total "
            "from venue_optin_requests where created_at >= $2", email, since))
        return r["mine"], r["total"]

    async def put(self, rec: dict) -> None:   # jsonb: the pool's codec (store.py) encodes, so dicts go in as dicts
        await self._run(lambda c: c.execute(
            "insert into venue_optin_requests (request_id, token_sha256, created_at, expires_at, lang, venue_id, venue_name, "
            "contact_name, contact_role, email, channels, submitted) values ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11::jsonb,$12::jsonb)",
            rec["request_id"], rec["token_sha256"], rec["created_at"], rec["expires_at"], rec["lang"], rec["venue_id"],
            rec["venue_name"], rec["contact_name"], rec["contact_role"], rec["email"], rec["channels"], rec["submitted"]))

    async def mark_email(self, tsha: str, status: str, provider_id: Optional[str], why: Optional[str]) -> None:
        await self._run(lambda c: c.execute(
            "update venue_optin_requests set email_status = $2, email_provider_id = $3, email_why = $4 where token_sha256 = $1",
            tsha, status, provider_id, why))

    async def get(self, tsha: str) -> Optional[dict]:
        return self._req(await self._run(lambda c: c.fetchrow(f"select {_REQ_COLS} from venue_optin_requests where token_sha256 = $1", tsha)))

    async def confirm(self, tsha: str, now: datetime) -> dict:
        async def tx(c):
            async with c.transaction():
                req = self._req(await c.fetchrow(f"select {_REQ_COLS} from venue_optin_requests where token_sha256 = $1 for update", tsha))
                since = req is not None and await c.fetchval(
                    "select exists (select 1 from venue_optins where venue_id = $1 and status = 'withdrawn' and recorded_at > $2)",
                    req["venue_id"], req["created_at"])
                _confirmable(req, now, bool(since))
                if req["confirmed_at"]:
                    return {"already": True, "req": req}
                for ch in req["channels"]:
                    row = active_row(req, ch, now)
                    await c.execute(
                        "insert into venue_optins (venue_id, channel, scope, status, recorded_at, agreed_by_name, agreed_by_role, "
                        "agreed_at, method, wording_version, wording_sha256, wording_text, evidence) "
                        "values ($1,$2,$3,'active',$4,$5,$6,$7,'form',$8,$9,$10,$11::jsonb)",
                        row["venue_id"], row["channel"], row["scope"], now, row["agreed_by_name"], row["agreed_by_role"], now,
                        row["wording_version"], row["wording_sha256"], row["wording_text"], row["evidence"])
                await c.execute("update venue_optin_requests set confirmed_at = $2 where token_sha256 = $1", tsha, now)
                req["confirmed_at"] = now
                return {"already": False, "req": req}
        return await self._run(tx)

    async def withdraw(self, tsha: str, now: datetime) -> dict:
        async def tx(c):
            async with c.transaction():
                req = self._req(await c.fetchrow(f"select {_REQ_COLS} from venue_optin_requests where token_sha256 = $1 for update", tsha))
                if req is None:
                    raise Refused(404, "link_unknown", "This link is not one we sent, or it has been deleted")
                live = await c.fetch(
                    "select channel, scope from (select distinct on (channel, scope) channel, scope, status from venue_optins "
                    "where venue_id = $1 order by channel, scope, recorded_at desc, id desc) l where l.status = 'active'", req["venue_id"])
                rows = withdrawn_rows(req, [(r["channel"], r["scope"]) for r in live], now)
                for row in rows:
                    await c.execute(
                        "insert into venue_optins (venue_id, channel, scope, status, recorded_at, withdrawn_at, withdrawn_how, withdrawn_evidence) "
                        "values ($1,$2,$3,'withdrawn',$4,$4,$5,$6::jsonb)",
                        row["venue_id"], row["channel"], row["scope"], now, row["withdrawn_how"], row["withdrawn_evidence"])
                await c.execute("update venue_optin_requests set withdrawn_at = coalesce(withdrawn_at, $2) where token_sha256 = $1", tsha, now)
                req["withdrawn_at"] = req.get("withdrawn_at") or now
                return {"req": req, "rows": len(rows)}
        return await self._run(tx)


# ── routes ─────────────────────────────────────────────────────────────────────────────────────

async def _body(request: Request) -> dict:
    try:
        b = await request.json()
    except Exception:
        b = None
    if not isinstance(b, dict):
        raise Refused(400, "malformed", "send a JSON object")
    return b


def _token(b: dict) -> str:
    t = b.get("t")
    if not isinstance(t, str) or not re.fullmatch(r"[A-Za-z0-9_-]{32,64}", t):
        raise Refused(404, "link_unknown", "This link is not one we sent")
    return t


def _handled(fn):
    @functools.wraps(fn)   # keeps fn's signature, which FastAPI reads for its parameters
    async def wrapped(*a, **k):
        try:
            return await fn(*a, **k)
        except Refused as e:
            return _refuse(e.status, e.rule, e.message)
        except StorageUnavailable as e:
            return _refuse(503, e.rule, e.detail)
    return wrapped


@router.get("/status")
async def status():
    why = page_ready()
    return {"open": why is None, "why": why}


@router.get("/wordings")
async def wordings(lang: str = "en"):
    lang = lang if lang in LANGS else "en"
    return {"version": CURRENT_OPTIN_VERSION, "lang": lang,
            "wordings": {ch: OPTIN_WORDINGS[ch][CURRENT_OPTIN_VERSION].get(lang) or OPTIN_WORDINGS[ch][CURRENT_OPTIN_VERSION]["en"]
                         for ch in CHANNELS}}


@router.post("/requests")
@_handled
async def make_request(request: Request):
    why = page_ready()
    if why:
        raise Refused(503, "page_closed", f"{why}; nothing was recorded or sent")
    req = parse_request(await _body(request))
    now = NOW()
    mine, total = await PAGE_STORE.counts(req["email"], now - timedelta(days=1))
    if mine >= OPTIN_PER_EMAIL_PER_DAY:
        raise Refused(429, "too_many_for_address", f"{OPTIN_PER_EMAIL_PER_DAY} confirmation emails have gone to this address today; please use the last one, or try tomorrow")
    if total >= OPTIN_PER_DAY:
        raise Refused(429, "too_many_today", "The page has taken as many requests as it allows today; please try tomorrow")
    token = secrets.token_urlsafe(32)
    rec = {**req, "request_id": uuid.uuid4(), "token_sha256": token_sha(token), "created_at": now, "expires_at": now + LINK_VALID,
           "email_status": "pending", "email_provider_id": None, "email_why": None, "confirmed_at": None, "withdrawn_at": None}
    await PAGE_STORE.put(rec)
    mail = confirmation_email(rec, token)
    sent = await E.send(HTTP if HTTP is not None else ladder_routes.HTTP, mail)
    try:
        await PAGE_STORE.mark_email(rec["token_sha256"], "sent" if sent.sent else "not_sent", sent.provider_id, sent.why)
    except (StorageUnavailable, AlreadyRecorded) as e:
        raise Refused(503, "not_recorded", f"the mail service answered {'accepted' if sent.sent else 'not accepted'}, but it could not be recorded: {e}")
    if not sent.sent:
        return _refuse(502, "email_not_sent", f"We couldn't send the confirmation email: {sent.why}. Nothing was recorded as consent.")
    return {"ok": True, "status": "sent", "email": req["email"], "channels": [c["channel"] for c in req["channels"]]}


@router.post("/preview")
@_handled
async def preview(request: Request):
    req = await PAGE_STORE.get(token_sha(_token(await _body(request))))
    if req is None:
        raise Refused(404, "link_unknown", "This link is not one we sent, or it has been deleted")
    return {"ok": True, "request": view(req)}


@router.post("/confirm")
@_handled
async def confirm(request: Request):
    out = await PAGE_STORE.confirm(token_sha(_token(await _body(request))), NOW())
    return {"ok": True, "status": "already_confirmed" if out["already"] else "confirmed", "request": view(out["req"])}


@router.post("/withdraw")
@_handled
async def withdraw(request: Request):
    out = await PAGE_STORE.withdraw(token_sha(_token(await _body(request))), NOW())
    return {"ok": True, "status": "withdrawn", "rows": out["rows"], "request": view(out["req"])}
