"""S-75 · SASHA ON WHATSAPP FOR GUESTS — the sandbox phase (docs/sasha/S-75-whatsapp-interface.md, steps 1–10).

A linked guest books, cancels and gets receipts entirely in WhatsApp, on the SAME booking routes the web chat uses,
called in process (no HTTP to ourselves) as that guest's own account. What is never done:
  · ⛔ THE MODEL IS NEVER CALLED. Anything that is not a booking, a cancellation, a receipt or help gets one fixed
    sentence (Meta's AI policy, S-75 §0: a booking service, not a general assistant). Stricter than the spec's
    "scope gate, then conduct()": the scope gate's own booking functions (handoff, chat_request) do the whole turn.
  · ⛔ A VENUE IS NEVER ANSWERED. Only numbers named in SASHA_GUEST_WHATSAPP_TO (the sandbox's) serve guests; on every
    other number — Sasha's own +44, where venues write — the venue path runs byte for byte as before. On a guest
    number a sender matching a venue call still takes the venue path.
  · No booking without the bound yes: a button names the call and its read-back hash; a typed yes binds only to the
    newest pending question, within the approval window, and goes to the route with its words.
  · No first message to anyone who has not linked; nothing at all to a guest who sent STOP (email receipts go on).
  · A password or card number typed here is never stored and never sent anywhere (S-78 input guard).

Steps 11–12 (the production sender, templates outside 24 hours, voice notes) wait for counsel (F-1) and are not here.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import os
import re
import secrets
import time
import unicodedata
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from xml.sax.saxutils import escape

from . import handoff as HO
from . import places_terms as PT
from . import sentences as SN
from . import yes as YS
from .store import StorageUnavailable
from .vault import guard as G

log = logging.getLogger("booking_signer.guest_whatsapp")
NOW = lambda: datetime.now(timezone.utc)

CONSENT = {"v2": ("Sasha by Kanoe will message you on WhatsApp about the bookings you ask for: confirmations, progress "
                  "and receipts. Reply STOP at any time to stop.")}
CURRENT = "v2"
CODE_LIFE = timedelta(minutes=10)
LINK_TRIES_PER_HOUR = 5
CARDS_LIFE = timedelta(minutes=60)
APPROVAL_WINDOW = timedelta(minutes=15)       # = call_routes.APPROVAL_WINDOW
SESSION_WINDOW = timedelta(hours=24)          # WhatsApp's customer-service window
SEND_GAP = 3.1                                # the sandbox sends one message every three seconds
HISTORY_KEEP = 20
TITLE_MAX = 25                                # WhatsApp's button-title limit
WATCH_CALL = (10, 48)                         # every 10 s, up to 8 minutes (as the web chat)
WATCH_CANCEL = (30, 60)                       # every 30 s, up to 30 minutes, for a written cancellation


def web_url() -> str:
    return os.getenv("SASHA_WEB_URL", "https://project.kanoe.ai").rstrip("/") + "/booking-helper#whatsapp"


OUT_OF_SCOPE = "On WhatsApp I can book, change or cancel things for you, and send your receipts. For anything else, open Sasha at {web}."
ONBOARD = "Hi, I'm Sasha by Kanoe. To book on WhatsApp, link your account first: {web}"
LINKED = "Linked. You can book with me here now — for example: dinner for 2 on Saturday at 21:00 in Chamberí."
BAD_CODE = "That code didn't work. Get a new one at {web}"
TOO_MANY = "Too many tries for now. Get a new code at {web} and try again in an hour."
STOPPED = "OK, no more WhatsApp messages. Your receipts still come by email."
STARTED = "Welcome back — I'll message you here again."
HELP = ("Tell me what to book in one message — the kind of place, the area, the day, the time and how many, e.g. "
        "\"dinner for 2 in Chamberí on Saturday at 21:00\". I'll show you places, read back exactly what I'll say, and "
        "only contact them after your yes. \"Cancel <name>\" cancels a booking; \"my bookings\" lists them.")
NO_CONTACT = ("I need the name and mobile to book under first. Add them once at {web} (kept with your consent), then ask me "
              "again.")

_STOP = re.compile(r"^\s*(stop|parar|baja|arr[eê]t|unsubscribe|cancelar suscripci[oó]n)\s*[.!]?\s*$", re.I)
_START = re.compile(r"^\s*(start|unstop|alta)\s*[.!]?\s*$", re.I)
_LINK = re.compile(r"^\s*link\s+(\d{6})\s*$", re.I)
_RECEIPTS = re.compile(r"\b(receipts?|my bookings?|my reservations?|itinerary|what have i booked)\b", re.I)
_HELP = re.compile(r"^\s*(help|ayuda|\?|hi|hello|hola)\s*[.!?]?\s*$", re.I)
_NO = re.compile(r"^\s*(no|nope|not now|don'?t|cancel that|stop that)\b", re.I)
_ORDINAL = {"1": 0, "one": 0, "first": 0, "2": 1, "two": 1, "second": 1, "3": 2, "three": 2, "third": 2}


def consent(version: str = CURRENT) -> dict:
    text = CONSENT[version]
    return {"version": version, "text": text, "sha256": hashlib.sha256(text.encode()).hexdigest()}


def wa_key(number: str) -> str:
    """The hash a WhatsApp number is kept as — the same as booking_inbound.from_key (places_terms.number_key), bare hex."""
    return PT.number_key(number).split(":", 1)[1]


def guest_numbers() -> set:
    """The numbers that serve GUESTS (the sandbox's, in phase 1). Empty: the guest pipeline is off everywhere."""
    return {n.strip() for n in os.getenv("SASHA_GUEST_WHATSAPP_TO", "").split(",") if n.strip()}


def title(s: str) -> str:
    s = re.sub(r"\s+", " ", s or "").strip()
    return s if len(s) <= TITLE_MAX else s[:TITLE_MAX - 1].rstrip() + "…"


def _fold(s: str) -> str:
    return "".join(ch for ch in unicodedata.normalize("NFD", s or "") if unicodedata.category(ch) != "Mn").lower()


# ── the store: Memory for tests, Postgres (sql/020) for real ────────────────────────────────────────────────────────

class MemoryGuestStore:
    def __init__(self) -> None:
        self.channels: Dict[str, dict] = {}
        self.codes: Dict[str, dict] = {}
        self.state: Dict[str, dict] = {}

    async def channel_for(self, key: str) -> Optional[dict]:
        return dict(self.channels[key]) if key in self.channels else None

    async def channel_of_account(self, account: str) -> Optional[dict]:
        return next((dict(c) for c in self.channels.values() if c["account_id"] == account), None)

    async def put_code(self, row: dict) -> bool:
        if row["code"] in self.codes:
            return False
        self.codes[row["code"]] = dict(row)
        return True

    async def take_code(self, code: str, now: datetime) -> Optional[dict]:
        r = self.codes.get(code)
        if not r or r.get("used_at") or r["created_at"] < now - CODE_LIFE:
            return None
        r["used_at"] = now
        return dict(r)

    async def link(self, row: dict) -> None:
        for k in [k for k, c in self.channels.items() if c["account_id"] == row["account_id"]]:
            del self.channels[k]
        self.channels[row["wa_id_sha256"]] = dict(row)

    async def unlink(self, account: str) -> Optional[dict]:
        k = next((k for k, c in self.channels.items() if c["account_id"] == account), None)
        return self.channels.pop(k) if k else None

    async def set_opted_out(self, key: str, at: Optional[datetime]) -> None:
        if key in self.channels:
            self.channels[key]["opted_out_at"] = at

    async def get_state(self, key: str) -> dict:
        return dict(self.state.get(key) or {"history": [], "pending": None, "last_inbound_at": None, "link_tries": []})

    async def put_state(self, key: str, st: dict) -> None:
        self.state[key] = dict(st)

    async def delete_account(self, account: str) -> Dict[str, int]:
        keys = [k for k, c in self.channels.items() if c["account_id"] == account]
        for k in keys:
            del self.channels[k]
            self.state.pop(k, None)
        codes = [k for k, c in self.codes.items() if c["account_id"] == account]
        for k in codes:
            del self.codes[k]
        return {"guest_channels": len(keys), "guest_wa_state": len(keys), "guest_link_codes": len(codes)}


class PostgresGuestStore:
    def __init__(self, base) -> None:
        self._base = base

    async def _run(self, fn):
        try:
            return await self._base._run(fn)
        except StorageUnavailable as e:
            raise e.rehint("020_guest_channels.sql") from None

    @staticmethod
    def _ch(r) -> Optional[dict]:
        return {**dict(r), "account_id": str(r["account_id"])} if r else None

    async def channel_for(self, key):
        return self._ch(await self._run(lambda c: c.fetchrow("select * from guest_channels where channel = 'whatsapp' and wa_id_sha256 = $1", key)))

    async def channel_of_account(self, account):
        return self._ch(await self._run(lambda c: c.fetchrow(
            "select * from guest_channels where channel = 'whatsapp' and account_id = $1", uuid.UUID(account))))

    async def put_code(self, row):
        r = await self._run(lambda c: c.execute(
            "insert into guest_link_codes (code, account_id, consent_at, consent_wording_version, consent_text_sha256, created_at) "
            "values ($1,$2,$3,$4,$5,$6) on conflict (code) do nothing",
            row["code"], uuid.UUID(row["account_id"]), row["consent_at"], row["consent_wording_version"], row["consent_text_sha256"],
            row["created_at"]))
        return r.endswith(" 1")

    async def take_code(self, code, now):
        r = await self._run(lambda c: c.fetchrow(
            "update guest_link_codes set used_at = $2 where code = $1 and used_at is null and created_at >= $3 returning *",
            code, now, now - CODE_LIFE))
        return {**dict(r), "account_id": str(r["account_id"])} if r else None

    async def link(self, row):
        async def go(c):
            async with c.transaction():
                await c.execute("delete from guest_channels where channel = 'whatsapp' and (account_id = $1 or wa_id_sha256 = $2)",
                                uuid.UUID(row["account_id"]), row["wa_id_sha256"])
                await c.execute(
                    "insert into guest_channels (account_id, channel, wa_id_sha256, number_e164, linked_at, consent_at, "
                    "consent_wording_version, consent_text_sha256) values ($1,'whatsapp',$2,$3,$4,$5,$6,$7)",
                    uuid.UUID(row["account_id"]), row["wa_id_sha256"], row["number_e164"], row["linked_at"], row["consent_at"],
                    row["consent_wording_version"], row["consent_text_sha256"])
        await self._run(go)

    async def unlink(self, account):
        return self._ch(await self._run(lambda c: c.fetchrow(
            "delete from guest_channels where channel = 'whatsapp' and account_id = $1 returning *", uuid.UUID(account))))

    async def set_opted_out(self, key, at):
        await self._run(lambda c: c.execute(
            "update guest_channels set opted_out_at = $2 where channel = 'whatsapp' and wa_id_sha256 = $1", key, at))

    async def get_state(self, key):
        r = await self._run(lambda c: c.fetchrow("select * from guest_wa_state where wa_id_sha256 = $1", key))
        if not r:
            return {"history": [], "pending": None, "last_inbound_at": None, "link_tries": []}
        d = dict(r)
        return {"history": json.loads(d["history"]) if isinstance(d["history"], str) else d["history"],
                "pending": json.loads(d["pending"]) if isinstance(d["pending"], str) else d["pending"],
                "last_inbound_at": d["last_inbound_at"],
                "link_tries": json.loads(d["link_tries"]) if isinstance(d["link_tries"], str) else d["link_tries"]}

    async def put_state(self, key, st):
        await self._run(lambda c: c.execute(
            "insert into guest_wa_state (wa_id_sha256, history, pending, last_inbound_at, link_tries, updated_at) "
            "values ($1, $2, $3, $4, $5, now()) on conflict (wa_id_sha256) do update set history = excluded.history, "
            "pending = excluded.pending, last_inbound_at = excluded.last_inbound_at, link_tries = excluded.link_tries, updated_at = now()",
            # the pool's jsonb codec encodes: pass the values themselves (Sasha 104 · a json.dumps here stored a JSON string)
            key, st.get("history") or [], st.get("pending"), st.get("last_inbound_at"), st.get("link_tries") or []))

    async def delete_account(self, account):
        async def go(c):
            async with c.transaction():
                a = uuid.UUID(account)
                st = await c.execute("delete from guest_wa_state where wa_id_sha256 in (select wa_id_sha256 from guest_channels where account_id = $1)", a)
                ch = await c.execute("delete from guest_channels where account_id = $1", a)
                co = await c.execute("delete from guest_link_codes where account_id = $1", a)
                return {"guest_channels": int(ch.split()[-1]), "guest_wa_state": int(st.split()[-1]), "guest_link_codes": int(co.split()[-1])}
        return await self._run(go)


STORE: Any = None   # routes.py sets the Postgres store; tests set a memory one


# ── sending: Twilio, spaced, only inside the 24-hour window, never to an opted-out guest ────────────────────────────

class Sender:
    """Every outgoing WhatsApp message. Tests replace it (SENDER) and read `.sent`."""

    def __init__(self) -> None:
        self._locks: Dict[str, asyncio.Lock] = {}
        self._last: Dict[str, float] = {}

    def _auth(self) -> Optional[Tuple[str, str]]:
        sid, token = os.getenv("TWILIO_ACCOUNT_SID", "").strip(), os.getenv("TWILIO_AUTH_TOKEN", "").strip()
        return (sid, base64.b64encode(f"{sid}:{token}".encode()).decode()) if sid and token else None

    async def quick_reply(self, body: str, buttons: List[Tuple[str, str]]) -> Optional[str]:
        """A twilio/quick-reply content made for THIS question (its buttons carry this question's ids), or None."""
        auth = self._auth()
        if not auth:
            return None
        spec = {"friendly_name": f"sasha_wa_{uuid.uuid4().hex[:12]}", "language": "en",
                "types": {"twilio/quick-reply": {"body": body[:1024], "actions": [{"title": title(t), "id": i[:200]} for t, i in buttons]},
                          "twilio/text": {"body": body[:1024]}}}
        try:
            import httpx
            async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
                r = await client.post("https://content.twilio.com/v1/Content", json=spec,
                                      headers={"authorization": f"Basic {auth[1]}", "user-agent": "sasha-booking/1"})
            if r.status_code in (200, 201) and (r.json() or {}).get("sid"):
                return r.json()["sid"]
            log.error("[guest_whatsapp] quick-reply content not created: HTTP %s %s", r.status_code, r.text[:200])
        except Exception as e:
            log.error("[guest_whatsapp] quick-reply content failed: %s: %s", type(e).__name__, e)
        return None

    async def send(self, frm: str, to: str, *, body: str = "", media: Optional[str] = None, content_sid: Optional[str] = None) -> str:
        auth = self._auth()
        if not auth:
            return "not sent: no Twilio account"
        data = {"From": f"whatsapp:{frm}", "To": f"whatsapp:{to}"}
        if content_sid:
            data["ContentSid"] = content_sid
        else:
            data["Body"] = body[:1500]
            if media:
                data["MediaUrl"] = media
        lock = self._locks.setdefault(frm, asyncio.Lock())
        async with lock:
            wait = self._last.get(frm, 0) + SEND_GAP - time.monotonic()
            if wait > 0:
                await asyncio.sleep(wait)
            try:
                import httpx
                async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
                    r = await client.post(f"https://api.twilio.com/2010-04-01/Accounts/{auth[0]}/Messages.json",
                                          headers={"authorization": f"Basic {auth[1]}"}, data=data)
                self._last[frm] = time.monotonic()
                if r.status_code in (200, 201) and (r.json() or {}).get("sid"):
                    return "sent"
                log.error("[guest_whatsapp] message not accepted: HTTP %s %s", r.status_code, r.text[:200])
                return f"not sent: Twilio answered HTTP {r.status_code}"
            except Exception as e:
                log.error("[guest_whatsapp] message failed: %s: %s", type(e).__name__, e)
                return f"not sent: {type(e).__name__}"


SENDER: Any = Sender()


class Out:
    """What one turn says, in order. Each item: ('text', body) · ('media', body, url) · ('ask', body, [(title, id)])."""

    def __init__(self) -> None:
        self.items: List[tuple] = []

    def text(self, s: str) -> "Out":
        self.items.append(("text", s))
        return self

    def media(self, s: str, url: Optional[str]) -> "Out":
        self.items.append(("media", s, url) if url else ("text", s))
        return self

    def ask(self, s: str, buttons: List[Tuple[str, str]]) -> "Out":
        self.items.append(("ask", s, buttons))
        return self

    def said(self) -> str:
        return "\n".join(i[1] for i in self.items)


async def deliver(ch: dict, frm: str, out: Out, last_inbound_at: Optional[datetime]) -> List[str]:
    """Sends a turn's messages — or nothing, with the reason logged: opted out, or outside the 24-hour window (the sandbox
    has no templates; the email receipt still goes)."""
    if ch.get("opted_out_at"):
        log.info("[guest_whatsapp] not sent: the guest has opted out (STOP)")
        return ["not sent: opted out"]
    if not last_inbound_at or NOW() - last_inbound_at > SESSION_WINDOW:
        log.info("[guest_whatsapp] not sent: outside the 24-hour window and no template is approved (sandbox)")
        return ["not sent: outside the 24-hour window"]
    results = []
    for it in out.items:
        if it[0] == "text":
            results.append(await SENDER.send(frm, ch["number_e164"], body=it[1]))
        elif it[0] == "media":
            results.append(await SENDER.send(frm, ch["number_e164"], body=it[1], media=it[2]))
        else:
            sid = await SENDER.quick_reply(it[1], it[2])
            if sid:
                results.append(await SENDER.send(frm, ch["number_e164"], content_sid=sid))
            else:   # no buttons: the same question, answered by typing
                opts = " · ".join(f"{t}" for t, _ in it[2])
                results.append(await SENDER.send(frm, ch["number_e164"], body=f"{it[1]}\n(Reply: {opts})"))
    return results


# ── the booking routes, in process, as the guest's own account ──────────────────────────────────────────────────────

_INNER = None
_HEADER = "x-sasha-wa-account"


def _inner_app():
    """The booking router in a private app: its gate is replaced by "the account this WhatsApp number is linked to".
    Reachable only from this module — it is never mounted on the public app."""
    global _INNER
    if _INNER is None:
        from fastapi import FastAPI, Request
        from . import gate, routes
        app = FastAPI()
        app.include_router(routes.router)

        async def as_linked_account(request: Request) -> None:
            request.state.account = request.headers.get(_HEADER)

        app.dependency_overrides[gate.require_booking_key] = as_linked_account
        _INNER = app
    return _INNER


async def api(account: str, method: str, path: str, body: Any = None, timeout: float = 90.0) -> Tuple[int, dict]:
    import httpx
    transport = httpx.ASGITransport(app=_inner_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://sasha.internal", timeout=timeout) as client:
        r = await client.request(method, path, json=body, headers={_HEADER: account})
    try:
        j = r.json()
    except Exception:
        j = {"message": r.text[:300]}
    return r.status_code, (j if isinstance(j, dict) else {"value": j})


def refusal_words(j: dict, status: int) -> str:
    """The guest's words for a refusal — never a rule code or a setting's name (as the web's guestRefusal)."""
    d = j.get("detail") if isinstance(j.get("detail"), dict) else j
    msg = str((d or {}).get("message") or "").strip()
    if status in (401, 403):
        return "booking isn't open to this account yet"
    if status == 503:
        return "that part of Sasha is unavailable right now"
    msg = re.sub(r"\b[A-Z][A-Z0-9_]{3,}\b", "a setting", msg)
    return msg or f"it didn't go through (HTTP {status})"


# ── the webhook's entry: who wrote? ─────────────────────────────────────────────────────────────────────────────────

_TASKS: set = set()
_TURN_LOCKS: Dict[str, asyncio.Lock] = {}


def _spawn(coro) -> None:
    t = asyncio.ensure_future(coro)
    _TASKS.add(t)
    t.add_done_callback(_TASKS.discard)


def _twiml_message(text: str) -> str:
    return f"<Message>{escape(text)}</Message>"


async def dispatch(p: Dict[str, str], venue_call_for) -> Optional[str]:
    """None: not ours — the venue path runs exactly as before. A string: the TwiML inside <Response> (often empty: the
    guest's turn runs in the background and answers through the API, a message every three seconds)."""
    to = (p.get("To") or "").split(":", 1)[-1].strip()
    sender = (p.get("From") or "").split(":", 1)[-1].strip()
    if not (p.get("From") or "").lower().startswith("whatsapp:") or to not in guest_numbers() or not sender or STORE is None:
        return None
    key = wa_key(sender)
    ch = await STORE.channel_for(key)
    if ch:
        _spawn(_turn(ch, to, p))
        return ""
    if await venue_call_for(sender):
        return None                        # a venue that is not a linked guest: the venue path, never a reply
    now = NOW()
    st = await STORE.get_state(key)
    m = _LINK.match(p.get("Body") or "")
    if m:
        tries = [t for t in st.get("link_tries") or [] if _dt(t) > now - timedelta(hours=1)]
        if len(tries) >= LINK_TRIES_PER_HOUR:
            await STORE.put_state(key, {**st, "link_tries": tries})
            return _twiml_message(TOO_MANY.format(web=web_url()))
        code = await STORE.take_code(m[1], now)
        if code is None:
            await STORE.put_state(key, {**st, "link_tries": tries + [now.isoformat()]})
            return _twiml_message(BAD_CODE.format(web=web_url()))
        await STORE.link({"account_id": code["account_id"], "wa_id_sha256": key, "number_e164": sender, "linked_at": now,
                          "consent_at": code["consent_at"], "consent_wording_version": code["consent_wording_version"],
                          "consent_text_sha256": code["consent_text_sha256"]})
        await STORE.put_state(key, {"history": [], "pending": None, "last_inbound_at": now, "link_tries": []})
        log.info("[guest_whatsapp] a WhatsApp number was linked to an account")
        return _twiml_message(LINKED)
    # an unknown sender: one fixed sentence, at most every ten minutes; only the hash and the time are kept
    tries = [t for t in st.get("link_tries") or [] if _dt(t) > now - timedelta(hours=1)]
    onboarded = [t for t in tries if t.startswith("onboard:")]
    if onboarded and _dt(onboarded[-1]) > now - timedelta(minutes=10):
        return ""
    await STORE.put_state(key, {**st, "link_tries": tries + [f"onboard:{now.isoformat()}"]})
    return _twiml_message(ONBOARD.format(web=web_url()))


def _dt(s: str) -> datetime:
    try:
        return datetime.fromisoformat(s.split("onboard:", 1)[-1])
    except ValueError:
        return datetime.min.replace(tzinfo=timezone.utc)


# ── one guest turn ──────────────────────────────────────────────────────────────────────────────────────────────────

async def _turn(ch: dict, frm: str, p: Dict[str, str]) -> None:
    lock = _TURN_LOCKS.setdefault(ch["wa_id_sha256"], asyncio.Lock())
    async with lock:
        try:
            await turn(ch, frm, p)
        except Exception as e:   # every failure is logged, and the guest is told plainly
            log.exception("[guest_whatsapp] a turn failed: %s", type(e).__name__)
            st = await STORE.get_state(ch["wa_id_sha256"])
            await deliver(ch, frm, Out().text("Something went wrong on my side — nothing was sent to any venue. Please try "
                                              "again in a minute."), st.get("last_inbound_at"))


async def turn(ch: dict, frm: str, p: Dict[str, str]) -> Out:
    key, account = ch["wa_id_sha256"], ch["account_id"]
    body = (p.get("Body") or "").strip()
    payload = (p.get("ButtonPayload") or "").strip()
    now = NOW()
    st = await STORE.get_state(key)
    st["last_inbound_at"] = now
    out = Out()
    if ch.get("opted_out_at"):
        if _START.match(body):
            await STORE.set_opted_out(key, None)
            ch = {**ch, "opted_out_at": None}
            out.text(STARTED)
        await STORE.put_state(key, st)
        await deliver(ch, frm, out, now)
        return out
    if _STOP.match(body):
        await STORE.set_opted_out(key, now)
        st["pending"] = None
        await STORE.put_state(key, st)
        await deliver({**ch, "opted_out_at": None}, frm, out.text(STOPPED), now)   # said once, then silence
        return out
    if not body and not payload:
        # Sasha 104 · a voice note or a picture arrives with no words: voice notes are phase 3 (F-3), so say so plainly
        has_media = int(p.get("NumMedia") or 0) > 0
        out.text("I can't listen to voice notes or read pictures here yet — please type it in one message, e.g. \"dinner "
                 "for 2 in Chamberí on Saturday at 21:00\"." if has_media else HELP)
        await STORE.put_state(key, st)
        await deliver(ch, frm, out, now)
        return out
    if G.looks_like_secret(body):
        # S-78 · never stored (not in the history either), never passed on
        out.text(G.CARD_REPLY if G.looks_like_secret(body) == "card" else G.SECRET_REPLY)
        await STORE.put_state(key, st)
        await deliver(ch, frm, out, now)
        return out
    ctx = {"account": account, "ch": ch, "frm": frm, "st": st, "now": now, "out": out, "button_text": (p.get("ButtonText") or "").strip()}
    handled = await _answer_pending(ctx, body, payload)
    if not handled:
        await _new_request(ctx, body)
    st["history"] = (st.get("history") or []) + [{"role": "user", "content": body}] + \
                    ([{"role": "assistant", "content": out.said()}] if out.items else [])
    st["history"] = st["history"][-HISTORY_KEEP:]
    await STORE.put_state(key, st)
    await deliver(ch, frm, out, now)
    return out


async def _new_request(ctx: dict, body: str) -> None:
    """The scope gate: a booking, a cancellation, receipts or help — anything else is the one fixed sentence."""
    out, st = ctx["out"], ctx["st"]
    history = st.get("history") or []
    if _HELP.match(body):
        out.text(HELP)
        return
    if _RECEIPTS.search(body):
        await _receipts(ctx)
        return
    h = HO.booking_handoff(body, history)
    if h is not None:
        if h.get("booking_cancel"):
            await _cancel_find(ctx, h["booking_cancel"]["venue"])
        elif h.get("booking_find"):
            await _find(ctx, h["booking_find"], h.get("reservation_draft") or {})
        else:
            out.text(h["response"])
        return
    from .chat_request import booking_turn
    t = booking_turn(body, history)
    if t is not None:
        out.text(t["response"])
        return
    # Sasha 104 · out of scope ONLY when there is clearly no booking, change or cancel in it; unsure → one question
    if maybe_booking(body):
        out.text(ASK_ONE)
        return
    out.text(OUT_OF_SCOPE.format(web=web_url()))


ASK_ONE = ("Shall I book that? Tell me in one message — the kind of place, the area, the day, the time and how many, e.g. "
           "\"dinner for 2 in Chamberí on Saturday at 21:00\".")
_HINT = re.compile(r"\b(book|booking|reserv\w*|res[eé]rv\w*|cancel\w*|anul\w*|change|move|table|mesa|dinner|cena|lunch|comida|"
                   r"almuerzo|breakfast|desayuno|brunch|restaurant\w*|bar|tapas|spa|massage|masaje|tour|hotel|tonight|tomorrow|"
                   r"ma[nñ]ana|hoy|esta noche|for \d+|para \d+|people|personas|"
                   r"monday|tuesday|wednesday|thursday|friday|saturday|sunday|lunes|martes|mi[eé]rcoles|jueves|viernes|s[aá]bado|domingo)\b"
                   r"|\b\d{1,2}(?::\d{2})?\s*(?:am|pm|h)\b|\b\d{1,2}:\d{2}\b|\b(?:at|a las)\s+\d{3,4}\b", re.I)


def maybe_booking(body: str) -> bool:
    """Anything that MIGHT be a booking, a change or a cancellation — a place to book, a day, a time, a party."""
    return bool(_HINT.search(body or ""))


# ── find → cards ────────────────────────────────────────────────────────────────────────────────────────────────────

async def _find(ctx: dict, f: dict, draft: dict) -> None:
    from .ranking import rating_words
    from .venue_read import distance_words
    out, account = ctx["out"], ctx["account"]
    status, j = await api(account, "POST", "/api/booking/venues/find",
                          {k: v for k, v in {"what": f.get("what"), "where": f.get("where"), "country": f.get("country"),
                                             "open_at": f.get("open_at")}.items() if v})
    if status != 200:
        out.text(f"I can't search for places right now — {refusal_words(j, status)}.")
        return
    cands = {c["place_id"]: c for c in j.get("candidates") or []}
    ranking = j.get("ranking") or {}
    chip = f.get("priority") if f.get("priority") in (ranking.get("orders") or {}) else ranking.get("default", "rated")
    order = (ranking.get("orders") or {}).get(chip) or list(cands)
    shown = [cands[i] for i in order if i in cands][:3]
    if not shown:
        out.text(f"I found no {f.get('what')} in {f.get('where')}. Try another area or kind of place.")
        return
    pick = (ranking.get("picks") or {}).get(chip)
    photos = await _photos(account, f.get("what") or "", shown)
    out.text(f"{f.get('what')} in {f.get('where')} — {ranking.get('count') or f'{len(cands)} found'}. From Google Maps; "
             f"nobody has been contacted.")
    for c in shown:
        line = " · ".join(x for x in (c.get("name") or "no name listed", rating_words(c), distance_words(c.get("distance_m"))) if x)
        out.media(("Sasha's pick · " if c["place_id"] == pick else "") + line, photos.get(c["place_id"]))
    nonce = secrets.token_hex(3)
    out.ask("Which one?", [(c.get("name") or f"Option {i + 1}", f"pick:{nonce}:{i}") for i, c in enumerate(shown)])
    ctx["st"]["pending"] = {"kind": "cards", "at": ctx["now"].isoformat(), "nonce": nonce, "find": f,
                            "draft": draft.get("parts") or {},
                            "cards": [{"place_id": c["place_id"], "name": c.get("name"), "country": c.get("country")} for c in shown]}


async def _photos(account: str, what: str, shown: List[dict]) -> Dict[str, str]:
    """The venue's OWN share picture from its own site (og:image, robots first — style.page_text), never a Google one.
    Read WITHOUT the style summary: that is a model call, and on WhatsApp the model is never called."""
    from . import ladder_routes as LR, style as ST

    async def one(c):
        try:
            page = await ST.page_text(LR.HTTP, c["website"], LR.RESOLVE)
            return c["place_id"], page.get("image")
        except Exception as e:
            log.info("[guest_whatsapp] no photo: %s", type(e).__name__)
            return c["place_id"], None
    got = await asyncio.gather(*(one(c) for c in shown if c.get("website")))
    return {pid: url for pid, url in got if url}


# ── pending questions ───────────────────────────────────────────────────────────────────────────────────────────────

async def _answer_pending(ctx: dict, body: str, payload: str) -> bool:
    out, st, now = ctx["out"], ctx["st"], ctx["now"]
    pend = st.get("pending")
    if payload and (not pend or not _payload_ok(pend, payload)):
        out.text("That button was for an earlier question — nothing was sent. Ask me again and I'll start afresh.")
        return True
    if not pend:
        return False
    at = _dt(pend.get("at") or "")
    kind = pend["kind"]
    if kind == "cards":
        if now - at > CARDS_LIFE:
            st["pending"] = None
            return False
        i = _picked(pend, body, payload)
        if i is None:
            other = refinement(body)
            if not other and HO.booking_handoff(body, st.get("history") or []) is not None:
                st["pending"] = None
                return False                               # a new request: start afresh
            if other:
                # Sasha 104 · "How about Indian food?" while choosing: the same area, day, time and party, another kind
                st["pending"] = None
                await _find(ctx, {**pend["find"], "what": other}, {"parts": pend.get("draft") or {}})
                return True
            out.text("Which one? Tap a name, or send its number (1, 2 or 3) — or tell me what else to look for.")
            return True
        await _picked_card(ctx, pend, pend["cards"][i])
        return True
    if kind == "need":
        return await _answer_need(ctx, pend, body)
    if kind in ("confirm", "cancel_confirm"):
        fresh = now - at <= APPROVAL_WINDOW
        if payload.startswith("no:") or (not payload and _NO.match(body)):
            st["pending"] = None
            out.text("OK — nothing was sent." if kind == "confirm" else "OK — nothing was cancelled.")
            return True
        yes_button = payload.startswith("yes:")
        if yes_button or YS.is_yes(body):
            if not fresh:
                st["pending"] = None
                out.text("That question has expired (15 minutes) — nothing was sent. Ask me again and I'll read it back afresh.")
                return True
            how = {"how": "whatsapp_button", "said": ctx.get("button_text") or None} if yes_button else {"how": "whatsapp_text", "said": body}
            st["pending"] = None
            await (_approve(ctx, pend, how) if kind == "confirm" else _cancel_approve(ctx, pend, how))
            return True
        if HO.booking_handoff(body, st.get("history") or []) is not None:
            st["pending"] = None
            return False
        out.text("Tap Yes or No — or say \"yes\". Nothing happens until you do.")
        return True
    if kind == "link":
        if re.match(r"^\s*booked\b", body, re.I):
            st["pending"] = None
            status, j = await api(ctx["account"], "POST", f"/api/booking/links/{pend['link_id']}/booked", {"how": "whatsapp_text", "said": body})
            out.text("Noted — booked on their page, by you. It's in your bookings as you told me; their confirmation email is the proof."
                     if status == 200 else f"I couldn't record it — {refusal_words(j, status)}.")
            return True
        return False
    return False


_REFINE = re.compile(r"^\s*¿?\s*(?:how about|what about|maybe|or|rather|instead|actually|y|qu[eé] tal|mejor|o)\s+(?:some\s+|an?\s+|algo de\s+|un\s+|una\s+)?"
                     r"(?P<what>[^?.!]{2,60}?)\s*(?:instead|then|please|por favor|mejor)?\s*[?.!]*\s*$", re.I)


def refinement(body: str) -> Optional[str]:
    """Another kind of place, said while the cards are showing ("How about Indian food?", "¿Y comida india?") — or None."""
    m = _REFINE.match(body or "")
    if not m:
        return None
    what = m["what"].strip()
    if re.search(r"\b(?:in|near|around|en|cerca)\b", what, re.I):
        return None                                        # a new area is a new request (the hand-off reads it)
    return what if 1 <= len(what.split()) <= 5 and not re.search(r"\d", what) else None


def _payload_ok(pend: dict, payload: str) -> bool:
    """A button answers ONLY the question it was sent with: its id names this card set, or this call and its hash."""
    if pend["kind"] == "cards":
        return payload.startswith(f"pick:{pend['nonce']}:")
    tag = f"{str(pend.get('id', ''))[:8]}:{str(pend.get('sha', ''))[:16]}"
    return payload in (f"yes:{tag}", f"no:{tag}")


def _picked(pend: dict, body: str, payload: str) -> Optional[int]:
    if payload.startswith(f"pick:{pend['nonce']}:"):
        try:
            i = int(payload.rsplit(":", 1)[1])
            return i if 0 <= i < len(pend["cards"]) else None
        except ValueError:
            return None
    t = _fold(body).strip(" .!")
    for w in re.findall(r"[a-z0-9]+", t):
        if w in _ORDINAL and _ORDINAL[w] < len(pend["cards"]) and len(t.split()) <= 4:
            return _ORDINAL[w]
    words = [w for w in re.findall(r"[a-z0-9]+", t) if len(w) > 2 and w not in ("the", "one", "that", "please")]
    hits = [i for i, c in enumerate(pend["cards"]) if words and all(w in _fold(c.get("name") or "") for w in words)]
    return hits[0] if len(hits) == 1 else None


# ── a card picked → read → the details → the read-back and the ONE sentence ─────────────────────────────────────────

async def _picked_card(ctx: dict, pend: dict, card: dict) -> None:
    out, account, f = ctx["out"], ctx["account"], pend["find"]
    status, read = await api(account, "POST", "/api/booking/venues/read",
                             {"name": card.get("name") or f.get("what"), "city": f.get("where"), "country": card.get("country") or f.get("country"),
                              "place_id": card["place_id"], "asked_for": f.get("what")})
    if status != 200:
        ctx["st"]["pending"] = None
        out.text(f"I couldn't read how {card.get('name') or 'they'} take bookings — {refusal_words(read, status)}.")
        return
    venue = (read.get("listing") or {}).get("name") or card.get("name") or read.get("venue")
    rungs = {r["rung"]: r for r in read.get("rungs") or [] if r.get("available")}
    if not any(k in rungs for k in ("form", "link", "phone")):
        ctx["st"]["pending"] = None
        out.text(f"{read.get('say') or 'I found no way to book them that I may use.'} Nothing was sent.")
        return
    draft = dict(pend.get("draft") or {})
    if "what" not in draft:
        _s, d = await api(account, "POST", "/api/booking/draft", {"text": f.get("what"), "country": read.get("country") or f.get("country")})
        if (d.get("parts") or {}).get("what"):
            draft["what"] = d["parts"]["what"]
    if f.get("open_at") and (draft.get("when") or {}).get("mode") != "at":
        draft["when"] = {"mode": "at", "at": f["open_at"]}
    nxt = {"kind": "need", "at": ctx["now"].isoformat(), "read": {"read_id": read["read_id"], "country": read.get("country"),
           "venue": venue, "rungs": {k: {"fact_index": r.get("fact_index"), "value": r.get("value")} for k, r in rungs.items()}},
           "draft": draft}
    await _prepare_or_ask(ctx, nxt)


_NEED_Q = {"what": "What should I book there — a table, a massage, a class…?", "when": "Which day and time?",
           "count": "For how many?"}


def _missing(draft: dict) -> Optional[str]:
    if not draft.get("what"):
        return "what"
    w = draft.get("when") or {}
    if w.get("mode") not in ("at", "venue_proposes"):
        return "when"
    if not (draft.get("how_many") or {}).get("count"):
        return "count"
    return None


async def _answer_need(ctx: dict, pend: dict, body: str) -> bool:
    from .chat_request import draft as draft_of
    if HO.booking_handoff(body, []) is not None:
        ctx["st"]["pending"] = None
        return False
    d = draft_of(body, ctx["now"])["parts"]
    draft = dict(pend["draft"])
    need = pend.get("need")
    if need == "when":
        day, hhmm = (draft.get("when") or {}).get("at", "")[:10] or None, None
        from .chat_request import plain_day, _time
        day = plain_day(body, ctx["now"]) or day
        hhmm = _time(body.lower()) or HO.context_time(body) or HO.plain_time(body)
        if (d.get("when") or {}).get("mode") in ("at", "venue_proposes"):
            draft["when"] = d["when"]
        elif day and hhmm:
            draft["when"] = {"mode": "at", "at": f"{day}T{hhmm}"}
    elif need == "count":
        n = (d.get("how_many") or {}).get("count") or HO.plain_party(body)
        if not n and re.fullmatch(r"\s*\d{1,2}\s*", body):
            n = int(body)
        if n:
            draft["how_many"] = {"count": n, "unit": (d.get("how_many") or {}).get("unit") or "people"}
    elif need == "what" and d.get("what"):
        draft["what"] = d["what"]
    await _prepare_or_ask(ctx, {**pend, "draft": draft})
    return True


async def _prepare_or_ask(ctx: dict, pend: dict) -> None:
    out, st = ctx["out"], ctx["st"]
    need = _missing(pend["draft"])
    if need:
        st["pending"] = {**pend, "need": need, "at": ctx["now"].isoformat()}
        out.text(_NEED_Q[need])
        return
    status, cj = await api(ctx["account"], "GET", "/api/booking/contact")
    contact = cj.get("contact") if status == 200 else None
    if not contact:
        st["pending"] = None
        out.text(NO_CONTACT.format(web=web_url()))
        return
    d, rd = pend["draft"], pend["read"]
    reservation = {"schema": "reservation/1",
                   "flow": "availability" if d["when"]["mode"] == "venue_proposes" else (d.get("flow") or "book"),
                   "who": {"name": contact["name"], "contact": {"mobile_e164": contact["mobile_e164"]}},
                   "what": d["what"], "where": {}, "when": d["when"], "how_many": d["how_many"]}
    if reservation["flow"] == "quote_first":
        reservation["flow"] = "book"
    rungs = rd["rungs"]
    if "form" in rungs:
        status, j = await api(ctx["account"], "POST", "/api/booking/forms", {"read_id": rd["read_id"], "reservation": reservation})
        if status == 200:
            await _ask_yes(ctx, "form", j["form_id"], j["read_back"], SN.confirm_sentence(reservation, rd["venue"]), rd["venue"])
            return
        log.info("[guest_whatsapp] form rung refused (%s); trying the next rung", status)
    if "link" in rungs and reservation["when"]["mode"] == "at":
        at = reservation["when"]["at"]
        status, j = await api(ctx["account"], "POST", "/api/booking/links", {"read_id": rd["read_id"], "date": at[:10], "time": at[11:16],
                                                                              "party": reservation["how_many"]["count"], "name": contact["name"]})
        if status == 200:
            st["pending"] = {"kind": "link", "at": ctx["now"].isoformat(), "link_id": j["link_id"]}
            out.text(f"{rd['venue']} takes bookings on {j.get('platform') or 'their booking page'}, so you press the final button "
                     f"there — I can't. {'The day, time and party are filled in' if j.get('slot_filled') else 'Choose the day, time and party there'}: "
                     f"{j['url']}\nReply BOOKED once it's done.")
            return
        log.info("[guest_whatsapp] link rung refused (%s); trying the phone", status)
    if "phone" in rungs:
        fi = rungs["phone"].get("fact_index")
        status, j = await api(ctx["account"], "POST", "/api/booking/calls",
                              {"reservation": reservation, "read_id": rd["read_id"], **({"fact_index": fi} if fi is not None else {})})
        if status == 200:
            await _ask_yes(ctx, "call", j["call_id"], j["read_back"], j.get("sentence") or SN.confirm_sentence(reservation, rd["venue"]), rd["venue"])
            return
        st["pending"] = None
        out.text(f"Not prepared — {refusal_words(j, status)}. Nothing was dialled.")
        return
    st["pending"] = None
    out.text(f"I can't book {rd['venue']} from here right now. Nothing was sent.")


async def _ask_yes(ctx: dict, rung: str, rid: str, read_back: dict, sentence: str, venue: str, kind: str = "confirm",
                   extra: Optional[dict] = None) -> None:
    out = ctx["out"]
    sha = read_back["sha256"]
    out.text("Exactly what I'll " + ("say" if rung == "call" else "send") + ":\n" + "\n".join(f"• {ln}" for ln in read_back["lines"]))
    tag = f"{rid[:8]}:{sha[:16]}"
    yes_title = "Yes, book it" if kind == "confirm" else "Yes, cancel"
    out.ask(sentence, [(yes_title, f"yes:{tag}"), ("No", f"no:{tag}")])
    ctx["st"]["pending"] = {"kind": kind, "at": ctx["now"].isoformat(), "rung": rung, "id": rid, "sha": sha, "venue": venue,
                            **(extra or {})}


# ── the yes → placed → progress → the result ────────────────────────────────────────────────────────────────────────

async def _approve(ctx: dict, pend: dict, how: dict) -> None:
    out, account = ctx["out"], ctx["account"]
    if pend["rung"] == "form":
        status, j = await api(account, "POST", f"/api/booking/forms/{pend['id']}/send", {"read_back_sha256": pend["sha"], "approval": how}, timeout=120)
        if status != 200:
            out.text(f"Not sent — {refusal_words(j, status)}.")
            return
        out.text(str(j.get("say") or "Sent."))
        if j.get("their_page"):
            out.text(f"Their page answered, word for word: “{str(j['their_page'])[:600]}”")
        out.text("Who pressed it: Sasha, on their booking form." + _receipt_note())
        return
    status, j = await api(account, "POST", f"/api/booking/calls/{pend['id']}/place", {"read_back_sha256": pend["sha"], "approval": how}, timeout=120)
    if status != 200:
        out.text(f"Not called — {refusal_words(j, status)}. Nothing was dialled.")
        return
    out.text(str(j.get("say") or f"Calling {pend['venue']} now."))
    if j.get("status") in ("placed", "uncertain"):
        _spawn(watch_call(ctx["ch"], ctx["frm"], account, pend["id"], pend["venue"], "book"))


def _receipt_note() -> str:
    from .ladder import emails_ready
    return "" if emails_ready() else " Your receipt goes to your email."


async def watch_call(ch: dict, frm: str, account: str, call_id: str, venue: str, purpose: str) -> None:
    """Progress and the result, sent only when the call's state CHANGES — never two messages for one state."""
    every, times = WATCH_CALL
    seen = None
    for _ in range(times):
        await asyncio.sleep(every)
        status, v = await api(account, "GET", f"/api/booking/calls/{call_id}")
        if status != 200:
            continue
        state = v.get("status")
        if state == seen:
            continue
        seen = state
        st = await STORE.get_state(ch["wa_id_sha256"])
        if state in ("placed", "placing"):
            continue
        out = Out()
        if purpose == "cancel":
            done = v.get("outcome") == "yes"
            out.text(f"{venue} has cancelled your booking." if done else str(v.get("say") or "It is not cancelled yet."))
        else:
            out.text(str(v.get("say") or "The call has finished."))
        if v.get("venue_words"):
            out.text(f"What they said, word for word: “{v['venue_words']}”")
        out.text("Who pressed it: Sasha, by phone." + _receipt_note())
        await deliver(ch, frm, out, st.get("last_inbound_at"))
        return
    st = await STORE.get_state(ch["wa_id_sha256"])
    await deliver(ch, frm, Out().text("The call hasn't finished after 8 minutes; its result is kept, and the receipt will "
                                      "follow by email."), st.get("last_inbound_at"))


# ── receipts and cancelling ─────────────────────────────────────────────────────────────────────────────────────────

async def _upcoming(account: str) -> List[dict]:
    status, j = await api(account, "GET", "/api/booking/reservations")
    if status != 200:
        return []
    today = NOW().date().isoformat()
    rows = [r for r in j.get("reservations") or [] if r.get("status") not in ("cancelled", "declined", "failed")
            and (not r.get("date") or r["date"] >= today)]
    for r in rows:   # a phone booking's real name is on its receipt (the stored row keeps a marker, Sasha 64)
        if r.get("receipt"):
            s, rc = await api(account, "GET", r["receipt"])
            if s == 200 and (rc.get("venue") or {}).get("name"):
                r["venue"] = rc["venue"]["name"]
    return rows


async def _receipts(ctx: dict) -> None:
    rows = await _upcoming(ctx["account"])
    if not rows:
        ctx["out"].text("You have no upcoming bookings with me.")
        return
    lines = [f"• {r['venue']} — {SN.day_words(r.get('date')) or 'no day set'}{' at ' + r['time'] if r.get('time') else ''}, "
             f"{r.get('party') or '—'} — {r.get('status_words') or r.get('status')}" for r in rows[:8]]
    ctx["out"].text("Your upcoming bookings:\n" + "\n".join(lines) + "\nEach receipt is in your email.")


async def _cancel_find(ctx: dict, asked: str) -> None:
    out, account = ctx["out"], ctx["account"]
    words = [w for w in re.findall(r"[a-z0-9]+", _fold(asked)) if len(w) > 2]
    hits = [r for r in await _upcoming(account)
            if words and all(any(x.startswith(w) or w.startswith(x) for x in re.findall(r"[a-z0-9]+", _fold(r["venue"]))) for w in words)]
    if not hits:
        out.text(f"I can't find an upcoming booking of yours at {asked}.")
        return
    if len(hits) > 1:
        out.text("You have more than one booking there — tell me the day, e.g. \"cancel " + asked + " on Saturday\".")
        return
    r = hits[0]
    status, plan = await api(account, "GET", f"/api/booking/reservations/{r['id']}/cancel")
    if status != 200:
        out.text(f"I can't cancel it right now — {refusal_words(plan, status)}.")
        return
    if plan.get("route") is None:
        out.text(plan["read_back"]["lines"][0])
        return
    sentence = plan.get("sentence") or f"Cancel {plan.get('venue') or r['venue']}?"
    if plan["route"] == "call":
        s2, j = await api(account, "POST", "/api/booking/calls", {"cancels_call_id": plan["call_id"]})
        if s2 != 200:
            out.text(f"I can't cancel it by phone right now — {refusal_words(j, s2)}. Nothing was dialled.")
            return
        await _ask_yes(ctx, "call", j["call_id"], j["read_back"], sentence, plan.get("venue") or r["venue"], kind="cancel_confirm",
                       extra={"trip_item_id": r["id"]})
        return
    await _ask_yes(ctx, plan["route"], r["id"], plan["read_back"], sentence, plan.get("venue") or r["venue"], kind="cancel_confirm",
                   extra={"trip_item_id": r["id"]})


async def _cancel_approve(ctx: dict, pend: dict, how: dict) -> None:
    out, account, venue = ctx["out"], ctx["account"], pend["venue"]
    if pend["rung"] == "call":
        status, j = await api(account, "POST", f"/api/booking/calls/{pend['id']}/place", {"read_back_sha256": pend["sha"], "approval": how}, timeout=120)
        if status != 200:
            out.text(f"Not cancelled — {refusal_words(j, status)}. Nothing was dialled.")
            return
        out.text(f"Cancelling with {venue} now — by phone.")
        _spawn(watch_call(ctx["ch"], ctx["frm"], account, pend["id"], venue, "cancel"))
        return
    status, j = await api(account, "POST", f"/api/booking/reservations/{pend['trip_item_id']}/cancel",
                          {"read_back_sha256": pend["sha"], "approval": how}, timeout=120)
    if status != 200:
        out.text(f"Not cancelled — {refusal_words(j, status)}.")
        return
    if j.get("status") == "guest_presses" and j.get("url"):
        out.text(f"Their cancel link is on a booking platform, so you press it: {j['url']}\nIt's cancelled once their page or "
                 f"their email says so.")
        return
    if j.get("status") == "cancelled":   # ONLY on their words (cancel_routes)
        out.text(f"{venue} has cancelled your booking.")
        if j.get("their_words"):
            out.text(f"Their words: “{j['their_words']}”")
        return
    out.text(f"Cancelling with {venue} now. {j.get('say') or ''}".strip() + " I'll tell you here once they confirm it in writing.")
    _spawn(watch_cancel(ctx["ch"], ctx["frm"], account, pend["trip_item_id"], venue))


async def watch_cancel(ch: dict, frm: str, account: str, trip_item_id: str, venue: str) -> None:
    """A written cancellation: "cancelled" is said ONLY once the reservation reads cancelled (their words, cancel_routes)."""
    every, times = WATCH_CANCEL
    for _ in range(times):
        await asyncio.sleep(every)
        status, j = await api(account, "GET", "/api/booking/reservations")
        row = next((r for r in j.get("reservations") or [] if r.get("id") == trip_item_id), None) if status == 200 else None
        if row and row.get("status") == "cancelled":
            st = await STORE.get_state(ch["wa_id_sha256"])
            out = Out().text(f"{venue} has cancelled your booking.")
            if row.get("venue_words"):
                out.text(f"Their words: “{row['venue_words']}”")
            await deliver(ch, frm, out, st.get("last_inbound_at"))
            return


# ── the web side: link, see, unlink (the caller's own account; behind the booking gate) ──────────────────────────────

from fastapi import APIRouter, Request   # noqa: E402
from fastapi.responses import JSONResponse   # noqa: E402

router = APIRouter(tags=["booking-whatsapp"])


def _refuse(status: int, rule: str, message: str) -> JSONResponse:
    return JSONResponse({"ok": False, "rule": rule, "message": message}, status_code=status)


def status() -> dict:
    """For /health: whether guests are served on WhatsApp, and on which number(s) — never a guest's."""
    return {"guest_numbers": sorted(guest_numbers()), "phase": "sandbox" if "+14155238886" in guest_numbers() else
            ("off" if not guest_numbers() else "production"), "store": STORE is not None}


def _number() -> Optional[str]:
    ns = sorted(guest_numbers())
    return ns[0] if ns else None


@router.get("/whatsapp")
async def whatsapp_view(request: Request):
    from .account import account_for
    account = account_for(request)
    if STORE is None:
        return _refuse(503, "storage_not_provisioned", "WhatsApp linking is not set up on this server")
    try:
        ch = await STORE.channel_of_account(account)
    except StorageUnavailable as e:
        return _refuse(503, e.rule, e.detail)
    return {"linked": bool(ch), "opted_out": bool(ch and ch.get("opted_out_at")), "number": _number(),
            "join": os.getenv("SASHA_WA_SANDBOX_JOIN", "").strip() or None, "consent": consent()}


@router.post("/whatsapp/link")
async def whatsapp_link(request: Request):
    """The guest ticked consent v2 (its version and hash prove these exact words were shown): a six-digit code, ten
    minutes, one use, and the wa.me link that opens their WhatsApp with "LINK 123456" ready to send."""
    from .account import account_for
    account = account_for(request)
    try:
        body = await request.json()
    except Exception:
        body = None
    c = consent()
    if not isinstance(body, dict) or body.get("consent_version") != c["version"] or body.get("consent_sha256") != c["sha256"]:
        return _refuse(422, "consent_stale", "tick the sentence shown — it must be the current one")
    number = _number()
    if not number:
        return _refuse(503, "whatsapp_off", "Sasha isn't on WhatsApp for guests on this server yet")
    if STORE is None:
        return _refuse(503, "storage_not_provisioned", "WhatsApp linking is not set up on this server")
    now = NOW()
    for _ in range(5):
        code = f"{secrets.randbelow(10 ** 6):06d}"
        try:
            ok = await STORE.put_code({"code": code, "account_id": account, "consent_at": now, "consent_wording_version": c["version"],
                                       "consent_text_sha256": c["sha256"], "created_at": now})
        except StorageUnavailable as e:
            return _refuse(503, e.rule, e.detail)
        if ok:
            from urllib.parse import quote
            return {"code": code, "expires_at": (now + CODE_LIFE).isoformat(), "number": number,
                    "wa_link": f"https://wa.me/{number.lstrip('+')}?text={quote('LINK ' + code)}",
                    "join": os.getenv("SASHA_WA_SANDBOX_JOIN", "").strip() or None}
    return _refuse(503, "code_unavailable", "no code could be made just now; try again")


@router.delete("/whatsapp")
async def whatsapp_unlink(request: Request):
    from .account import account_for
    account = account_for(request)
    if STORE is None:
        return _refuse(503, "storage_not_provisioned", "WhatsApp linking is not set up on this server")
    try:
        ch = await STORE.unlink(account)
    except StorageUnavailable as e:
        return _refuse(503, e.rule, e.detail)
    if ch and _number():
        st = await STORE.get_state(ch["wa_id_sha256"])
        await deliver(ch, _number(), Out().text("Unlinked. I won't message you here again."), st.get("last_inbound_at"))
        await STORE.put_state(ch["wa_id_sha256"], {"history": [], "pending": None, "last_inbound_at": None, "link_tries": []})
    return {"unlinked": bool(ch)}


__all__ = ["dispatch", "turn", "deliver", "consent", "wa_key", "guest_numbers", "MemoryGuestStore", "PostgresGuestStore",
           "Sender", "Out", "api", "OUT_OF_SCOPE", "ONBOARD", "LINKED", "BAD_CODE", "STOPPED", "STARTED", "HELP", "title"]
