"""S-79 · GOOGLE CALENDAR — every booking in a "Sasha bookings" calendar, and a free/busy check before booking.

  GET    /api/booking/google            → {configured, connected, expired, consent}
  POST   /api/booking/google/connect    {consent_version, consent_sha256} → {url}: Google's consent page (G-1 scopes only)
  GET    /api/booking/google/callback   Google's redirect (no booking key: the signed, 10-minute `state` names the account)
  DELETE /api/booking/google            → revoked at Google, the token crypto-shredded, the link deleted

  · Scopes (G-1): calendar.app.created + calendar.freebusy. Sasha writes only into the secondary calendar she creates,
    and reads only busy RANGES, never an event's title.
  · The refresh token is a vault item (kind 'oauth', provider google.com), opened only by vault.use_connection for the
    calendar purposes; every use is logged and shown (G-2, the connection consent).
  · One outbox, fed by a database trigger on trip_items (sql/022): every status change, whichever of the eleven writers
    made it. A drainer maps §4: confirmed/guest_booked → event; proposed/quoted/waitlisted → tentative; cancelled/
    declined/failed → deleted (G-4); anything else → nothing (never an event for a booking that isn't one).
  · The 7-day testing expiry: invalid_grant → "Expired, reconnect", the guest told ONCE, the outbox kept until reconnect.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlencode

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, RedirectResponse

from .store import StorageUnavailable

log = logging.getLogger("booking_signer.calendar")
NOW = lambda: datetime.now(timezone.utc)
SCOPES = ["https://www.googleapis.com/auth/calendar.app.created", "https://www.googleapis.com/auth/calendar.freebusy"]
CALENDAR_NAME = "Sasha bookings"
CONSENT = {"v1": ("Sasha will add your bookings to a \"Sasha bookings\" calendar, keep them up to date, and check when "
                  "you're free before booking. She won't read your events.")}
CURRENT = "v1"
STATE_LIFE = 600
DRAIN_EVERY_S = 20
MAX_ATTEMPTS = 10
CAL = "https://www.googleapis.com/calendar/v3"


def consent(version: str = CURRENT) -> dict:
    t = CONSENT[version]
    return {"version": version, "text": t, "sha256": hashlib.sha256(t.encode()).hexdigest()}


def configured() -> bool:
    return all(os.getenv(k, "").strip() for k in ("SASHA_GOOGLE_OAUTH_CLIENT_ID", "SASHA_GOOGLE_OAUTH_CLIENT_SECRET",
                                                  "SASHA_GOOGLE_OAUTH_REDIRECT"))


def web_url(q: str = "") -> str:
    return os.getenv("SASHA_WEB_URL", "https://project.kanoe.ai").rstrip("/") + "/you" + (f"?{q}" if q else "") + "#calendar"


# ── the signed state: which account, which consent, for ten minutes ────────────────────────────────────────────────

def _key() -> bytes:
    k = os.getenv("SASHA_GOOGLE_OAUTH_CLIENT_SECRET", "").strip() or os.getenv("SASHA_BOOKING_KEY", "").strip()
    return hashlib.sha256(("sasha-calendar-state:" + k).encode()).digest()


def make_state(account: str, version: str, now: Optional[float] = None, product: str = "calendar") -> str:
    body = json.dumps({"a": account, "v": version, "p": product, "n": secrets.token_hex(8), "e": int((now or time.time()) + STATE_LIFE)},
                      separators=(",", ":")).encode()
    sig = hmac.new(_key(), body, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(body).decode().rstrip("=") + "." + base64.urlsafe_b64encode(sig).decode().rstrip("=")


def read_state(state: str, now: Optional[float] = None) -> Optional[dict]:
    try:
        b64, s64 = state.split(".")
        pad = lambda x: x + "=" * (-len(x) % 4)
        body, sig = base64.urlsafe_b64decode(pad(b64)), base64.urlsafe_b64decode(pad(s64))
    except Exception:
        return None
    if not hmac.compare_digest(sig, hmac.new(_key(), body, hashlib.sha256).digest()):
        return None
    d = json.loads(body)
    return d if d.get("e", 0) >= (now or time.time()) else None


# ── §4 · what a status means in the calendar ────────────────────────────────────────────────────────────────────────

def calendar_action(status: str) -> str:
    if status in ("confirmed", "guest_booked"):
        return "event"
    if status in ("proposed", "quoted", "waitlisted"):
        return "tentative"
    if status in ("requested", "attempting"):   # Sasha 157 · asked, not yet answered: in the calendar, marked as such
        return "requested"
    if status in ("cancelled", "declined", "failed"):
        return "delete"
    return "none"


def event_body(item: dict, action: str) -> dict:
    start = item["date_time"]
    if isinstance(start, str):
        start = datetime.fromisoformat(start)
    minutes = item.get("duration_minutes") or (120 if (item.get("category") or "restaurant") == "restaurant" else 60)
    tz = item.get("local_timezone") or "Europe/Madrid"
    name = item.get("provider_name") or "Booking"
    if action == "tentative":
        title, desc, status = f"(proposed) {name}", "The venue offered this; not booked until you say yes.", "tentative"
    elif action == "requested":
        title, desc, status = (f"(requested) {name}", f"Requested by Sasha — waiting for {name} to confirm. Not booked yet. {web_url()}",
                               "tentative")
    else:
        ref = item.get("booking_reference")
        title, status = name, "confirmed"
        desc = f"Booked by Sasha · {item.get('party_size') or '—'} people" + (f" · ref {ref}" if ref else "") + f" · {web_url()}"
        if (ref or "").startswith("TEST-") or "(TEST booking" in name:   # Sasha 135 · a TEST booking says so, here too
            desc = f"TEST booking — no hotel or provider was contacted; nothing is reserved." + (f" Ref {ref}." if ref else "") + f" {web_url()}"
    body = {"summary": title, "description": desc, "status": status, "transparency": "opaque",
            "start": {"dateTime": start.isoformat(), "timeZone": tz},
            "end": {"dateTime": (start + timedelta(minutes=minutes)).isoformat(), "timeZone": tz}}
    if item.get("address"):
        body["location"] = item["address"]
    return body


# ── the store: Memory for tests, Postgres (sql/022) for real ────────────────────────────────────────────────────────

class MemoryCalendarStore:
    def __init__(self) -> None:
        self.links: Dict[str, dict] = {}
        self.events: Dict[str, dict] = {}
        self.outbox: List[dict] = []
        self.items: Dict[str, dict] = {}

    async def get_link(self, account):
        return dict(self.links[account]) if account in self.links else None

    async def put_link(self, row):
        self.links[row["account_id"]] = dict(row)

    async def delete_link(self, account):
        return self.links.pop(account, None) is not None

    async def set_link(self, account, **kw):
        if account in self.links:
            self.links[account].update(kw)

    async def item(self, trip_item_id):
        return dict(self.items[trip_item_id]) if trip_item_id in self.items else None

    async def take(self, limit=50):
        return [dict(r) for r in self.outbox if r.get("done_at") is None and r.get("attempts", 0) < MAX_ATTEMPTS][:limit]

    async def done(self, oid, now):
        next(r for r in self.outbox if r["id"] == oid)["done_at"] = now

    async def fail(self, oid, error):
        r = next(r for r in self.outbox if r["id"] == oid)
        r["attempts"] = r.get("attempts", 0) + 1
        r["last_error"] = error

    async def get_event(self, trip_item_id):
        return dict(self.events[trip_item_id]) if trip_item_id in self.events else None

    async def put_event(self, row):
        self.events[row["trip_item_id"]] = dict(row)

    async def delete_event(self, trip_item_id):
        self.events.pop(trip_item_id, None)


class PostgresCalendarStore:
    def __init__(self, base) -> None:
        self._base = base

    async def _run(self, fn):
        try:
            return await self._base._run(fn)
        except StorageUnavailable as e:
            raise e.rehint("022_calendar.sql") from None

    @staticmethod
    def _l(r):
        return {**dict(r), "account_id": str(r["account_id"]), "vault_item_id": str(r["vault_item_id"])} if r else None

    async def get_link(self, account):
        return self._l(await self._run(lambda c: c.fetchrow("select * from calendar_links where account_id = $1", uuid.UUID(account))))

    async def put_link(self, row):
        await self._run(lambda c: c.execute(
            "insert into calendar_links (account_id, vault_item_id, google_calendar_id, scopes, consent_at, consent_wording_version, "
            "consent_text_sha256, last_ok_at) values ($1,$2,$3,$4,$5,$6,$7,$5) on conflict (account_id) do update set "
            "vault_item_id = excluded.vault_item_id, google_calendar_id = excluded.google_calendar_id, scopes = excluded.scopes, "
            "consent_at = excluded.consent_at, consent_wording_version = excluded.consent_wording_version, "
            "consent_text_sha256 = excluded.consent_text_sha256, last_ok_at = excluded.last_ok_at, needs_reconnect_at = null, "
            "told_reconnect_at = null",
            uuid.UUID(row["account_id"]), uuid.UUID(row["vault_item_id"]), row.get("google_calendar_id"), row["scopes"],
            row["consent_at"], row["consent_wording_version"], row["consent_text_sha256"]))

    async def delete_link(self, account):
        n = await self._run(lambda c: c.execute("delete from calendar_links where account_id = $1", uuid.UUID(account)))
        return n.endswith(" 1")

    async def set_link(self, account, **kw):
        cols = [k for k in kw if k in ("last_ok_at", "needs_reconnect_at", "told_reconnect_at")]
        if cols:
            sets = ", ".join(f"{k} = ${i + 2}" for i, k in enumerate(cols))
            await self._run(lambda c: c.execute(f"update calendar_links set {sets} where account_id = $1", uuid.UUID(account),
                                                *[kw[k] for k in cols]))

    async def item(self, trip_item_id):
        r = await self._run(lambda c: c.fetchrow(
            "select ti.id, ti.status, ti.date_time, ti.duration_minutes, ti.provider_name, ti.booking_reference, ti.party_size, "
            "ti.local_timezone, t.owner_id as account_id from trip_items ti join trips t on t.id = ti.trip_id where ti.id = $1",
            uuid.UUID(trip_item_id)))
        return {**dict(r), "id": str(r["id"]), "account_id": str(r["account_id"])} if r else None

    async def take(self, limit=50):
        rows = await self._run(lambda c: c.fetch(
            "select * from calendar_outbox where done_at is null and attempts < $1 order by created_at limit $2", MAX_ATTEMPTS, limit))
        return [{**dict(r), "trip_item_id": str(r["trip_item_id"])} for r in rows]

    async def done(self, oid, now):
        await self._run(lambda c: c.execute("update calendar_outbox set done_at = $2 where id = $1", oid, now))

    async def fail(self, oid, error):
        await self._run(lambda c: c.execute("update calendar_outbox set attempts = attempts + 1, last_error = $2 where id = $1", oid, error[:500]))

    async def get_event(self, trip_item_id):
        r = await self._run(lambda c: c.fetchrow("select * from booking_calendar_events where trip_item_id = $1", uuid.UUID(trip_item_id)))
        return {**dict(r), "trip_item_id": str(r["trip_item_id"]), "account_id": str(r["account_id"])} if r else None

    async def put_event(self, row):
        await self._run(lambda c: c.execute(
            "insert into booking_calendar_events (trip_item_id, account_id, google_event_id, etag, synced_status, synced_at) "
            "values ($1,$2,$3,$4,$5,now()) on conflict (trip_item_id) do update set google_event_id = excluded.google_event_id, "
            "etag = excluded.etag, synced_status = excluded.synced_status, synced_at = now()",
            uuid.UUID(row["trip_item_id"]), uuid.UUID(row["account_id"]), row["google_event_id"], row.get("etag"), row["synced_status"]))

    async def delete_event(self, trip_item_id):
        await self._run(lambda c: c.execute("delete from booking_calendar_events where trip_item_id = $1", uuid.UUID(trip_item_id)))


STORE: Any = None   # routes.py sets the Postgres store; tests a memory one


# ── Google, over its REST API (no new library) ──────────────────────────────────────────────────────────────────────

async def _http(method: str, url: str, token: Optional[str] = None, json_body: Any = None, data: Optional[dict] = None):
    import httpx
    headers = {"authorization": f"Bearer {token}"} if token else {}
    async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as c:
        r = await c.request(method, url, headers=headers, json=json_body, data=data)
    try:
        j = r.json()
    except Exception:
        j = {}
    return r.status_code, j

GOOGLE_HTTP = _http   # tests replace it


async def _token(account: str, link: dict, purpose: str) -> str:
    from .vault import crypto as VC
    return await VC.use_connection(account, link["vault_item_id"], purpose=purpose)


# ── the drainer ─────────────────────────────────────────────────────────────────────────────────────────────────────

async def _expired(account: str, link: dict) -> None:
    """invalid_grant: 'Expired, reconnect' — and the guest is told ONCE (WhatsApp if linked)."""
    now = NOW()
    await STORE.set_link(account, needs_reconnect_at=now)
    if link.get("told_reconnect_at"):
        return
    await STORE.set_link(account, told_reconnect_at=now)
    try:
        from . import guest_whatsapp as GW
        ch = await GW.STORE.channel_of_account(account) if GW.STORE else None
        if ch and GW.guest_numbers():
            st = await GW.STORE.get_state(ch["wa_id_sha256"])
            await GW.deliver(ch, sorted(GW.guest_numbers())[0], GW.Out().text(
                f"Your Google Calendar connection has expired (a limit while we're in testing). Reconnect: {web_url()}"),
                st.get("last_inbound_at"))
    except Exception as e:
        log.warning("[calendar] the reconnect message failed: %s", type(e).__name__)


async def sync_one(row: dict) -> str:
    """One outbox row. Returns what happened, in words."""
    from .vault.crypto import UseRefused
    item = await STORE.item(row["trip_item_id"])
    if item is None:
        await STORE.done(row["id"], NOW())
        return "done: no such booking"
    account = item["account_id"]
    link = await STORE.get_link(account)
    if link is None:
        await STORE.done(row["id"], NOW())
        return "done: no calendar connected"
    if link.get("needs_reconnect_at"):
        return "kept: the connection needs reconnecting"
    action = calendar_action(item["status"])
    existing = await STORE.get_event(item["id"])
    if action == "none" and not existing:
        await STORE.done(row["id"], NOW())
        return "done: nothing to show"
    try:
        token = await _token(account, link, "calendar_sync")
    except UseRefused as e:
        if e.rule == "connection_invalid_grant":
            await _expired(account, link)
            return "kept: expired (invalid_grant)"
        await STORE.fail(row["id"], e.rule)
        return f"failed: {e.rule}"
    cal = link.get("google_calendar_id") or "primary"
    try:
        if action in ("delete", "none"):
            if existing:
                st, _ = await GOOGLE_HTTP("DELETE", f"{CAL}/calendars/{cal}/events/{existing['google_event_id']}", token)
                if st not in (200, 204, 404, 410):
                    raise RuntimeError(f"delete answered HTTP {st}")
                await STORE.delete_event(item["id"])
            await STORE.done(row["id"], NOW())
            return "done: deleted" if existing else "done: nothing to show"
        body = event_body(item, action)
        if existing:
            st, j = await GOOGLE_HTTP("PATCH", f"{CAL}/calendars/{cal}/events/{existing['google_event_id']}", token, body)
        else:
            st, j = await GOOGLE_HTTP("POST", f"{CAL}/calendars/{cal}/events", token, body)
        if st not in (200, 201) or not j.get("id"):
            raise RuntimeError(f"Google answered HTTP {st}")
        await STORE.put_event({"trip_item_id": item["id"], "account_id": account, "google_event_id": j["id"], "etag": j.get("etag"),
                               "synced_status": item["status"]})
        await STORE.set_link(account, last_ok_at=NOW())
        await STORE.done(row["id"], NOW())
        return f"done: {'updated' if existing else 'created'} ({action})"
    except Exception as e:
        await STORE.fail(row["id"], f"{type(e).__name__}: {e}")
        return f"failed: {e}"


async def drain_once() -> List[str]:
    if STORE is None:
        return []
    return [await sync_one(r) for r in await STORE.take()]


_task: Optional[asyncio.Task] = None


async def _forever() -> None:
    while True:
        try:
            for what in await drain_once():
                log.info("[calendar] %s", what)
        except StorageUnavailable as e:
            log.error("[calendar] not running: %s", e.detail)
            await asyncio.sleep(600)
            continue
        except Exception as e:
            log.error("[calendar] drain failed: %s: %s", type(e).__name__, e)
        await asyncio.sleep(DRAIN_EVERY_S)


def start() -> None:
    global _task
    if _task is None and os.getenv("SASHA_CALENDAR_LOOP", "1") == "1" and os.getenv("DATABASE_URL", "").strip() and configured():
        _task = asyncio.create_task(_forever())


# ── §5.4 · free/busy before booking: one read-back line, never a block ──────────────────────────────────────────────

async def busy(account: str, start: datetime, end: datetime) -> Optional[List[Tuple[str, str]]]:
    """Busy RANGES on the guest's primary calendar (and Sasha's), or None (no connection, or it couldn't say)."""
    from .vault.crypto import UseRefused
    if STORE is None or not configured():
        return None
    try:
        link = await STORE.get_link(account)
        if not link or link.get("needs_reconnect_at"):
            return None
        token = await _token(account, link, "calendar_freebusy")
        items = [{"id": "primary"}] + ([{"id": link["google_calendar_id"]}] if link.get("google_calendar_id") else [])
        st, j = await GOOGLE_HTTP("POST", f"{CAL}/freeBusy", token, {"timeMin": start.isoformat(), "timeMax": end.isoformat(), "items": items})
    except (UseRefused, StorageUnavailable) as e:
        log.info("[calendar] free/busy skipped: %s", getattr(e, "rule", type(e).__name__))
        return None
    except Exception as e:
        log.info("[calendar] free/busy failed: %s", type(e).__name__)
        return None
    if st != 200:
        return None
    out = []
    for cal in (j.get("calendars") or {}).values():
        for b in cal.get("busy") or []:
            out.append((b.get("start"), b.get("end")))
    return out


def busy_line(ranges: List[Tuple[str, str]], tz: str) -> Optional[str]:
    if not ranges:
        return None
    from zoneinfo import ZoneInfo
    z = ZoneInfo(tz or "Europe/Madrid")
    a, b = ranges[0]
    try:
        s = datetime.fromisoformat(a.replace("Z", "+00:00")).astimezone(z).strftime("%H:%M")
        e = datetime.fromisoformat(b.replace("Z", "+00:00")).astimezone(z).strftime("%H:%M")
    except Exception:
        return "Your calendar shows something at that time."
    return f"Your calendar shows something at that time ({s}–{e})."


async def with_busy_line(account: str, built: dict, start: Optional[datetime], minutes: int, tz: str) -> dict:
    """The read-back gains the line, INSIDE the hash, so the guest approves knowing it. No link → unchanged."""
    if start is None:
        return built
    ranges = await busy(account, start, start + timedelta(minutes=minutes))
    line = busy_line(ranges or [], tz)
    if not line:
        return built
    from . import calls as C
    lines = list(built["read_back_lines"]) + [line]
    return {**built, "read_back_lines": lines, "read_back_sha256": C._sha256hex("\n".join(lines))}


# ── the routes ──────────────────────────────────────────────────────────────────────────────────────────────────────

router = APIRouter(prefix="/google", tags=["booking-calendar"])


def _refuse(status: int, rule: str, message: str) -> JSONResponse:
    return JSONResponse({"ok": False, "rule": rule, "message": message}, status_code=status)


def status() -> dict:
    return {"configured": configured(), "loop": _task is not None}


@router.get("")
async def calendar_view(request: Request):
    from .account import account_for
    account = account_for(request)
    link = None
    if STORE is not None:
        try:
            link = await STORE.get_link(account)
        except StorageUnavailable as e:
            return _refuse(503, e.rule, e.detail)
    return {"configured": configured(), "connected": bool(link and not link.get("needs_reconnect_at")),
            "expired": bool(link and link.get("needs_reconnect_at")), "consent": consent(),
            "last_ok_at": link["last_ok_at"].isoformat() if link and link.get("last_ok_at") else None}


@router.post("/connect")
async def calendar_connect(request: Request):
    from .account import account_for
    account = account_for(request)
    try:
        body = await request.json()
    except Exception:
        body = {}
    c = consent()
    if body.get("consent_version") != c["version"] or body.get("consent_sha256") != c["sha256"]:
        return _refuse(422, "consent_stale", "tick the sentence shown — it must be the current one")
    if not configured():
        return _refuse(503, "google_not_configured", "Google sign-in isn't set up on this server yet")
    q = {"client_id": os.getenv("SASHA_GOOGLE_OAUTH_CLIENT_ID", "").strip(), "redirect_uri": os.getenv("SASHA_GOOGLE_OAUTH_REDIRECT", "").strip(),
         "response_type": "code", "scope": " ".join(SCOPES), "access_type": "offline", "prompt": "consent",
         "include_granted_scopes": "false", "state": make_state(account, c["version"])}
    return {"url": "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(q)}


@router.get("/callback")
async def calendar_callback(request: Request):
    """Google's redirect. The account is the one the signed state names — never anything else in the request."""
    from .vault import crypto as VC, kms
    st = read_state(request.query_params.get("state", ""))
    if st is None:
        return _refuse(400, "state_invalid", "that sign-in link is not valid or has expired; start again from Sasha")
    if request.query_params.get("error"):
        return RedirectResponse(web_url("google=declined"), status_code=303)
    code = request.query_params.get("code", "")
    s, tok = await GOOGLE_HTTP("POST", "https://oauth2.googleapis.com/token", data={
        "code": code, "client_id": os.getenv("SASHA_GOOGLE_OAUTH_CLIENT_ID", "").strip(),
        "client_secret": os.getenv("SASHA_GOOGLE_OAUTH_CLIENT_SECRET", "").strip(),
        "redirect_uri": os.getenv("SASHA_GOOGLE_OAUTH_REDIRECT", "").strip(), "grant_type": "authorization_code"})
    if s != 200 or not tok.get("refresh_token") or not tok.get("access_token"):
        log.error("[calendar] the code exchange failed: HTTP %s %s", s, tok.get("error"))
        if st.get("p") == "gmail":   # the Gmail block's failure, not the calendar's
            return RedirectResponse(web_url("gmail=failed").replace("#calendar", "#gmail"), status_code=303)
        return RedirectResponse(web_url("google=failed"), status_code=303)
    account, now = st["a"], NOW()
    granted = (tok.get("scope") or "").split()
    if st.get("p") == "gmail":   # S-82 · the same Google sign-in, for read-only mail: its own token, its own consent
        from . import mailbox as MB
        if MB.SCOPE not in granted:
            return RedirectResponse(web_url("gmail=scopes_missing").replace("#calendar", "#gmail"), status_code=303)
        try:
            await MB.on_connected(account, tok["refresh_token"], st["v"], now)
        except kms.VaultClosed:
            return RedirectResponse(web_url("gmail=vault_closed").replace("#calendar", "#gmail"), status_code=303)
        return RedirectResponse(web_url("gmail=connected").replace("#calendar", "#gmail"), status_code=303)
    if not all(sc in granted for sc in SCOPES):
        return RedirectResponse(web_url("google=scopes_missing"), status_code=303)
    item_id = str(uuid.uuid4())
    try:
        sealed = await VC.seal(account, item_id, "oauth", json.dumps({"refresh_token": tok["refresh_token"]}).encode())
    except kms.VaultClosed as e:
        log.error("[calendar] not connected: the vault is closed (%s)", e)
        return RedirectResponse(web_url("google=vault_closed"), status_code=303)
    await VC.STORE.create({"id": item_id, "account_id": account, "provider": "google.com", "label": "Google Calendar", "kind": "oauth",
                           **sealed, "special_category": False, "created_at": now, "updated_at": now})
    await VC.STORE.event(account, item_id, "created", {"kind": "oauth", "provider": "google.com", "scopes": granted}, now)
    s2, cal = await GOOGLE_HTTP("POST", f"{CAL}/calendars", tok["access_token"], {"summary": CALENDAR_NAME})
    if s2 not in (200, 201) or not cal.get("id"):
        log.error("[calendar] the 'Sasha bookings' calendar could not be created: HTTP %s", s2)
    c = consent(st["v"])
    old = await STORE.get_link(account)
    await STORE.put_link({"account_id": account, "vault_item_id": item_id, "google_calendar_id": cal.get("id"), "scopes": granted,
                          "consent_at": now, "consent_wording_version": c["version"], "consent_text_sha256": c["sha256"]})
    if old and old.get("vault_item_id") != item_id:   # a reconnect: the old token shredded
        await VC.STORE.revoke(account, old["vault_item_id"], now)
    return RedirectResponse(web_url("google=connected"), status_code=303)


@router.delete("")
async def calendar_disconnect(request: Request):
    from .account import account_for
    from .vault import crypto as VC
    account = account_for(request)
    link = await STORE.get_link(account) if STORE else None
    if not link:
        return {"disconnected": False}
    revoked = "not revoked"
    try:
        revoked = await VC.use_connection(account, link["vault_item_id"], purpose="calendar_revoke", revoke=True)
    except Exception as e:
        log.warning("[calendar] revoke at Google failed: %s", type(e).__name__)
    await VC.STORE.revoke(account, link["vault_item_id"], NOW())
    await VC.STORE.event(account, link["vault_item_id"], "revoked", {"provider": "google.com"}, NOW())
    await STORE.delete_link(account)
    return {"disconnected": True, "at_google": revoked,
            "say": "Disconnected. Sasha's copy of the access is deleted" + (" and Google has revoked it." if revoked == "revoked" else
                   "; to be sure, remove \"Sasha by Kanoe\" at myaccount.google.com → Security → Third-party access.")}


__all__ = ["router", "calendar_action", "drain_once", "sync_one", "busy", "with_busy_line", "make_state", "read_state", "start",
           "status", "MemoryCalendarStore", "PostgresCalendarStore", "consent"]
