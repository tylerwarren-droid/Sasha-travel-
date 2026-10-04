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
import copy
import hashlib
import json
import logging
import os
import re
import secrets
import time
import unicodedata
import uuid
from datetime import date, datetime, timedelta, timezone
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
                  "and receipts. Reply STOP at any time to stop."),
           # S-83 §3a · reminders get their own line (EU 122); v2 links keep citing v2
           "v3": ("Sasha by Kanoe will message you on WhatsApp about the bookings you ask for: confirmations, progress "
                  "and receipts. Reply STOP at any time to stop.\n"
                  "She will also send you reminders about those bookings: the day before, when it's time to leave, and a "
                  "morning summary — never between 22:00 and 08:00, at most 4 a day. Reply STOP REMINDERS to stop just these.")}
CURRENT = "v3"


def consent_at_least(version: str, n: int) -> bool:
    """'v10' ≥ 'v3' — versions compared as numbers, never as strings."""
    try:
        return int(str(version)[1:]) >= n
    except ValueError:
        return False
CODE_LIFE = timedelta(minutes=10)
LINK_TRIES_PER_HOUR = 5
CARDS_LIFE = timedelta(minutes=60)
APPROVAL_WINDOW = timedelta(minutes=15)       # = call_routes.APPROVAL_WINDOW
SESSION_WINDOW = timedelta(hours=24)          # WhatsApp's customer-service window
SEND_GAP = 3.1                                # the sandbox sends one message every three seconds
HISTORY_KEEP = 20
TITLE_MAX = 20                                # WhatsApp's reply-button title limit (Sasha 117: 25 failed, Twilio 63013)
WATCH_CALL = (10, 48)                         # every 10 s, up to 8 minutes (as the web chat)
WATCH_CANCEL = (30, 60)                       # every 30 s, up to 30 minutes, for a written cancellation


def web_url() -> str:
    return os.getenv("SASHA_WEB_URL", "https://project.kanoe.ai").rstrip("/") + "/you#whatsapp"   # Sasha 120 · the guest's own page


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

    async def all_channels(self) -> List[dict]:
        return [dict(c) for c in self.channels.values() if not c.get("opted_out_at")]

    async def set_consent(self, key: str, version: str, sha: str, at: datetime) -> None:
        if key in self.channels:
            self.channels[key].update(consent_wording_version=version, consent_text_sha256=sha, consent_at=at)

    async def get_state(self, key: str) -> dict:
        return dict(self.state.get(key) or {"history": [], "pending": None, "last_inbound_at": None, "link_tries": []})

    async def put_state(self, key: str, st: dict) -> None:
        # only what guest_wa_state's columns hold: anything else is lost in production, so it is lost here too
        self.state[key] = copy.deepcopy({k: st.get(k) for k in ("history", "pending", "last_inbound_at", "link_tries")})

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

    async def all_channels(self):
        rows = await self._run(lambda c: c.fetch("select * from guest_channels where channel = 'whatsapp' and opted_out_at is null"))
        return [self._ch(r) for r in rows]

    async def set_consent(self, key, version, sha, at):
        await self._run(lambda c: c.execute(
            "update guest_channels set consent_wording_version = $2, consent_text_sha256 = $3, consent_at = $4 "
            "where channel = 'whatsapp' and wa_id_sha256 = $1", key, version, sha, at))

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

    async def send(self, frm: str, to: str, *, body: str = "", media: Optional[str] = None, content_sid: Optional[str] = None,
                   variables: Optional[dict] = None) -> str:
        auth = self._auth()
        if not auth:
            return "not sent: no Twilio account"
        data = {"From": f"whatsapp:{frm}", "To": f"whatsapp:{to}"}
        if content_sid:
            data["ContentSid"] = content_sid
            if variables:   # S-83 §2 · an approved template's numbered variables
                data["ContentVariables"] = json.dumps({str(k): str(v) for k, v in variables.items()})
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
    from . import invitations as IV   # S-80 · Jon opting in to ONE invitation, or stopping it
    joined = await IV.on_invite_message(sender, p.get("Body") or "")
    if joined:
        return _twiml_message(joined)
    stopped = await IV.on_invitee_stop(sender, p.get("Body") or "")
    if stopped:
        return _twiml_message(stopped)
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
    reminders = await _reminders_words(ch, body, now)   # S-83 §3a · STOP REMINDERS / YES REMINDERS
    if reminders:
        out.text(reminders)
        await STORE.put_state(key, st)
        await deliver(ch, frm, out, now)
        return out
    if _STOP.match(body):
        await STORE.set_opted_out(key, now)
        st["pending"] = None
        await STORE.put_state(key, st)
        await deliver({**ch, "opted_out_at": None}, frm, out.text(STOPPED), now)   # said once, then silence
        return out
    # CR 1 products (backend/products/whatsapp.py): CampusMe / relocation by MODE on this one sandbox number. Not in a
    # mode and no "campus…"/"relocation…" keyword → returns False at once and everything below runs as before.
    from products import whatsapp as PW

    async def _early(text: str) -> None:   # "Reading Yale's calendar…" goes out before a slow read, not after it
        await deliver(ch, frm, Out().text(text), now)
    if await PW.product_turn(ch, frm, p, st, out, now, early=_early):
        await STORE.put_state(key, st)   # never into Sasha's history: a product's answers (passport facts) aren't hers
        await deliver(ch, frm, out, now)
        return out
    # CR 13 products: a product may hand Sasha a sentence ("flights from London to Madrid on 2027-03-01 for 1") — answered exactly
    # as if typed; every booking still needs its own read-back and yes. Never a button's answer: a payload is never rewritten.
    handed = (p.get("Body") or "").strip()
    if handed and handed != body and not payload:
        body = handed
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
    # Sasha 126 · the two-booking plan rides INSIDE the open question (guest_wa_state stores only its four columns):
    # it lives exactly as long as a question is open, and goes with it
    st["combo"] = (st.get("pending") or {}).pop("combo", None)
    ctx = {"account": account, "ch": ch, "frm": frm, "st": st, "now": now, "out": out, "button_text": (p.get("ButtonText") or "").strip()}
    handled = await _answer_pending(ctx, body, payload)
    if not handled:
        await _new_request(ctx, body)
    offer = await _reminders_offer(ch)
    if offer:
        out.text(offer)
    st["history"] = (st.get("history") or []) + [{"role": "user", "content": body}] + \
                    ([{"role": "assistant", "content": out.said()}] if out.items else [])
    st["history"] = st["history"][-HISTORY_KEEP:]
    combo = st.pop("combo", None)
    if combo and st.get("pending"):
        st["pending"]["combo"] = combo
    await STORE.put_state(key, st)
    await deliver(ch, frm, out, now)
    return out


_CANCEL_WORD = re.compile(r"\b(cancel|cancell?ation|cancela|cancelar|cancelad|cancele|anula|anular|anulad|anule)\b", re.I)
_NOT_CANCEL = re.compile(r"\b(?:don'?t|do not|no\s+(?:lo\s+)?(?:canceles|anules)|never mind)\b.*\b(?:cancel|cancela|anula)", re.I)
_CANCEL_FILLER = re.compile(r"\b(no|please|pls|por favor|can you|could you|you|i want to|i'd like to|want to|to|cancel|cancell?ation|cancela|"
                           r"cancelar|cancelad|cancele|anula|anular|anulad|anule|my|the|a|booking|reservation|table|reserva|"
                           r"mesa|la|el|mi|de|en|at|for|it|that|this|one|lo|esa|esta|ese|now|ahora|thanks|gracias|"
                           # Sasha 117 · the meal and the day are not the venue's name: "the dinner at Hanakura" → Hanakura
                           r"dinner|lunch|breakfast|brunch|meal|cena|comida|almuerzo|desayuno|appointment|cita|"
                           r"tonight|today|tomorrow|hoy|ma[nñ]ana|esta noche|noche|on|del|al|con|with)\b", re.I)


def cancel_intent(body: str) -> Optional[str]:
    """Sasha 109 · None: not a cancellation. "": cancel, no place named. Else the place's name as said."""
    t = body or ""
    if not _CANCEL_WORD.search(t) or _NOT_CANCEL.search(t):
        return None
    t = re.sub(r"['’]s\b", "", t)                                   # Sasha 121 · "tonight's dinner" → "tonight dinner"
    rest = _CANCEL_FILLER.sub(" ", re.sub(r"[^\wáéíóúñü' -]", " ", t))
    words = [w for w in rest.split() if len(w.strip("'")) >= 2]
    return " ".join(words) if any(len(w) >= 3 for w in words) else ""


_DAY_HINT = re.compile(r"\b(tonight|today|esta noche|hoy|tomorrow|ma[nñ]ana)\b", re.I)


def cancel_day(body: str) -> Optional[str]:
    """Sasha 121 · "cancel tonight's dinner": the day said is a FILTER on their bookings — "today" or "tomorrow" — never a name."""
    m = _DAY_HINT.search(body or "")
    if not m:
        return None
    return "tomorrow" if _fold(m[1]).startswith(("tomorrow", "manana")) else "today"


_STOP_REM = re.compile(r"^\s*(stop|parar|baja)\s+(reminders?|recordatorios?)\s*[.!]?\s*$", re.I)
_YES_REM = re.compile(r"^\s*(yes|s[ií]|start)\s+(reminders?|recordatorios?)\s*[.!]?\s*$", re.I)
REMINDERS_OFFER = ("Want reminders about your bookings (the day before, when it's time to leave, a morning summary)? "
                   "Reply YES REMINDERS.")


async def _reminders_words(ch: dict, body: str, now) -> Optional[str]:
    from . import proactive as PR
    if PR.STORE is None:
        return None
    if _STOP_REM.match(body or ""):
        await PR.STORE.set_prefs(ch["account_id"], all_off=True)
        return "OK — no more reminders. Confirmations and receipts still come."
    if _YES_REM.match(body or ""):
        c = consent("v3")
        await STORE.set_consent(ch["wa_id_sha256"], c["version"], c["sha256"], now)
        await PR.STORE.set_prefs(ch["account_id"], all_off=False)
        return ("Done — reminders are on: the day before, when it's time to leave and a morning summary, never between "
                "22:00 and 08:00, at most 4 a day. Reply STOP REMINDERS to stop just these.")
    return None


async def _reminders_offer(ch: dict) -> Optional[str]:
    """S-83 §3a · a v2 guest is asked ONCE, in reply to their next message; ignored or declined, never again."""
    from . import proactive as PR
    if PR.STORE is None or consent_at_least(ch.get("consent_wording_version") or "v0", 3):
        return None
    try:
        if await PR.STORE.get_prefs(ch["account_id"]) is not None:
            return None
        await PR.STORE.set_prefs(ch["account_id"], all_off=True)   # recorded as asked: off until they say YES
    except StorageUnavailable as e:
        log.info("[guest_whatsapp] reminders offer skipped: %s", e.detail)
        return None
    except Exception as e:   # Sasha 117 · an offer is never worth the guest's whole turn (it was: a SQL type error)
        log.error("[guest_whatsapp] reminders offer failed, skipped: %s: %s", type(e).__name__, e)
        return None
    return REMINDERS_OFFER


async def _new_request(ctx: dict, body: str) -> None:
    """The scope gate: a booking, a cancellation, receipts or help — anything else is the one fixed sentence."""
    out, st = ctx["out"], ctx["st"]
    history = st.get("history") or []
    if _HELP.match(body):
        out.text(HELP)
        return
    # Sasha 109 · CANCEL before anything else: "Please cancel", "No Please Cancel Yatri", "cancela", "anula la de Yatri"
    ci = cancel_intent(body)
    if ci is not None:
        ctx["cancel_day"] = cancel_day(body)
        await _cancel_find(ctx, ci or None)
        return
    if _RECEIPTS.search(body):
        await _receipts(ctx)
        return
    if await _forwarded_confirmation(ctx, body):   # Sasha 118 · the venue's confirmation, forwarded by the guest
        return
    from . import demo_spa as DSP
    if ITINERARY_Q.search(body or ""):   # Sasha 132 · ask your itinerary — first: "do I have time to fly…" is a question, not a search
        from . import itinerary_q as IQ
        for line in await IQ.answer(ctx["account"], body, ctx["now"]):
            ctx["out"].text(line)
        return
    if FLIGHT.search(body or ""):   # Sasha 132 · flights, Duffel TEST mode
        await _flights(ctx, body)
        return
    if HOTEL.search(body or ""):   # Sasha 132 · a hotel: found as cards, requested from the hotel itself
        await _hotels(ctx, body)
        return
    if COMBO.search(body or ""):   # Sasha 126 (2) · two bookings from one sentence
        await _combo_start(ctx, body)
        return
    if DSP.INTENT.search(body or ""):   # Sasha 126 (3) · the spa membership, used inside ONE yes
        await _spa_start(ctx, body)
        return
    from . import demo_shop as DS
    if DS.REORDER.search(body or ""):   # Sasha 121 (F) · the vault, used inside ONE yes
        await _reorder(ctx)
        return
    from . import invitations as IV   # S-80 · "book dinner with Jon this week"
    inv_req = IV.invite_request(body, ctx["now"])
    if inv_req is not None and IV.STORE is not None:
        await _invite(ctx, inv_req)
        return
    h = HO.booking_handoff(body, history, ctx["now"])   # Sasha 138 · the turn's own clock: "Saturday" and urgency agree
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


# ── Sasha 132 · flights in Duffel TEST mode: cards → Book it → one-touch test payment → the test order → the itinerary ──

FLIGHT = re.compile(r"\b(flights?|fly|vuelos?|volar)\b.*\bfrom\s+\S.*\bto\s+\S|\b(flights?|vuelos?)\s+(?:from\s+)?[A-Z][\w .'-]+\s+to\s+[A-Z]", re.I)
_FROM_TO = re.compile(r"\b(?:from\s+)?(?P<o>[A-ZÁÉÍÓÚ][\wáéíóúñ .'-]*?)\s+to\s+(?P<d>[A-ZÁÉÍÓÚ][\wáéíóúñ .'-]*?)"
                      r"(?=\s+(?:on|for|next|this|tomorrow|today|el|para)\b|\s*[,.?!]|\s*$)")
from .itinerary_q import QUESTION as ITINERARY_Q   # noqa: E402 — the same question, on the web and WhatsApp


HOTEL = re.compile(r"\b(hotel|room|stay|alojamiento|habitaci[oó]n)\b.*\bin\s+[A-ZÁÉÍÓÚ]", re.I)
_DATES = re.compile(r"\bfrom\s+(?P<a>.+?)\s+(?:to|until|till)\s+(?P<b>[^,.?!]+)", re.I)
_NIGHTS = re.compile(r"\b(\d{1,2})\s+nights?\b", re.I)


async def _hotels(ctx: dict, body: str) -> None:
    """Duffel Stays isn't enabled on this account and RateHawk has no credentials, so a hotel is NOT booked instantly: it is
    found (Google, with its own photo), and the room is requested from the hotel itself — its form, page or email — said so."""
    out = ctx["out"]
    m = re.search(r"\bin\s+(?P<w>[A-ZÁÉÍÓÚ][\wáéíóúñ ,'-]*?)(?=\s+(?:from|for|on|next|this)\b|[.?!]|$)", body or "")
    dm, nm = _DATES.search(body or ""), _NIGHTS.search(body or "")
    a = HO.plain_date(dm["a"], ctx["now"]) if dm else HO.plain_date(body or "", ctx["now"])
    b = HO.plain_date(dm["b"], ctx["now"]) if dm else None
    if dm and a and not b and re.fullmatch(r"\s*\d{1,2}\s*", dm["a"] or ""):   # "from 14 to 16 November": the month is said once
        b = HO.plain_date(dm["b"], ctx["now"])
    if dm and not a and b and re.fullmatch(r"\s*\d{1,2}(?:st|nd|rd|th)?\s*", dm["a"]):
        a = b[:8] + "%02d" % int(re.sub(r"\D", "", dm["a"]))
    nights = (date.fromisoformat(b) - date.fromisoformat(a)).days if a and b else (int(nm[1]) if nm else 0)
    if not m or not a or not 1 <= nights <= 30:
        out.text("Tell me where and the dates, e.g. “a hotel in Hoi An from 14 to 16 November for 2”.")
        return
    f = HO.find_request(f"hotel in {m['w'].strip()}", ctx["now"]) or {"what": "hotel", "where": m["w"].strip()}
    if not f.get("country"):   # Sasha 138 · "Madrid" is Spain: the country decides the call's language and the hotel's time zone
        w = m["w"].strip()
        cn = re.fullmatch(r"(.+?),\s*([^,]+)", w)
        f["country"] = (HO.COUNTRY_NAMES.get(cn[2].strip().lower()) if cn else None) or (HO.known_place(w) or (None, None, None))[2]
    party = HO.plain_party(body or "") or 2
    out.text(f"Hotels for {nights} night{'s' if nights != 1 else ''} from {SN.day_words(a)}, {party} {'person' if party == 1 else 'people'}. "
             f"For the one you pick: a TEST booking (no hotel contacted), or a real request to the hotel.")
    ctx["no_test_card"] = True
    out_day = (date.fromisoformat(a) + timedelta(days=nights)).isoformat()
    en = f"a room for {nights} night{'s' if nights != 1 else ''} (check-out {out_day})"   # Sasha 138 · a call or a form says the stay
    es = f"una habitación para {nights} noche{'s' if nights != 1 else ''} (salida el {out_day})"
    await _find(ctx, {"what": "hotel", "where": f.get("where") or m["w"].strip(), "country": f.get("country")},
                {"parts": {"what": {"activity": en, "activity_venue_lang": es if (f.get("country") or "") == "ES" else en, "category": "other"},
                           "when": {"mode": "at", "at": f"{a}T15:00"}, "how_many": {"count": party, "unit": "people"}, "nights": nights}})


async def _hotel_choice(ctx: dict, pend: dict, card: dict) -> None:
    """Sasha 135 · two honest options for a hotel card: a TEST booking (no hotel contacted), or the REAL request to the hotel."""
    from . import hotel_test as HT
    name = card.get("name") or "this hotel"
    tag_id = hashlib.sha256((card.get("place_id") or name).encode()).hexdigest()[:8]
    sha = hashlib.sha256(f"{tag_id}|{pend.get('at')}".encode()).hexdigest()
    ctx["out"].ask(f"{name}: make a TEST booking ({HT.LABEL.lower()}; nothing reserved or charged), or book with the hotel for real "
                   f"(their own booking page, or a request to them)?",
                   [("Test booking", f"test:{tag_id}:{sha[:16]}"), ("Book with hotel", f"req:{tag_id}:{sha[:16]}")])
    ctx["st"]["pending"] = {"kind": "hotel_choice", "at": ctx["now"].isoformat(), "id": tag_id, "sha": sha, "card": card,
                            "cards_pend": {k: v for k, v in pend.items() if k != "kind"} | {"kind": "cards"}}


async def _hotel_test_ask(ctx: dict, pend: dict) -> None:
    from . import hotel_test as HT
    d = pend["cards_pend"].get("draft") or {}
    f = pend["cards_pend"].get("find") or {}
    hotel, city = pend["card"].get("name") or "the hotel", f.get("where") or ""
    checkin, nights, party = (d.get("when") or {}).get("at", "")[:10], int(d.get("nights") or 1), int((d.get("how_many") or {}).get("count") or 2)
    q = HT.quote(hotel, city, checkin, nights, party)
    ctx["out"].text("Exactly what I'll do:\n" + "\n".join("• " + ln for ln in q["lines"]))
    rid = hashlib.sha256(hotel.encode()).hexdigest()[:8]
    ctx["out"].ask(f"Make the TEST booking at {hotel}? (No hotel contacted.)", [("Yes, test-book it", f"yes:{rid}:{q['sha256'][:16]}"),
                                                                              ("No", f"no:{rid}:{q['sha256'][:16]}")])
    ctx["st"]["pending"] = {"kind": "hotel_test_confirm", "at": ctx["now"].isoformat(), "id": rid, "sha": q["sha256"], "hotel": hotel,
                            "city": city, "country": f.get("country"), "checkin": checkin, "nights": nights, "party": party, "eur": q["eur"]}


async def _hotel_test_pay(ctx: dict, pend: dict) -> None:
    from . import hotel_test as HT, test_deposit as TD
    got = await TD.checkout(f"{pend['eur']:.2f}", "EUR", f"{HT.LABEL} — {pend['hotel']} {pend['checkin']} ({pend['nights']} nights)", pend["sha"][:16])
    if "why" in got:
        ctx["out"].text(f"I can't take the test payment yet — {got['why']}. No test booking was made.")
        return
    ctx["out"].text(f"One touch: pay the TEST price (€{pend['eur']:.2f}) on Stripe's test page — Apple Pay or your phone's saved card; nothing "
                    f"is charged and no hotel is contacted.\n{got['url']}\nI'll add the TEST booking the moment it's paid.")
    _spawn(watch_hotel_payment(ctx["ch"], ctx["frm"], ctx["account"], pend, got["id"]))


async def watch_hotel_payment(ch: dict, frm: str, account: str, p: dict, session_id: str) -> None:
    from . import hotel_test as HT, test_deposit as TD
    every, times = WATCH_PAY
    for _ in range(times):
        await asyncio.sleep(every)
        if not await TD.session_paid(session_id):
            continue
        ref = HT.new_ref()
        await HT.RECORD(account, p["hotel"], p["city"], HT.tz_of(p.get("country")), p["checkin"], p["nights"], p["party"], ref)
        TD.note(session_id, True, f"🧪 {HT.LABEL}: {p['hotel']}, {p['checkin']}, {p['nights']} night{'s' if p['nights'] != 1 else ''}. "
                                  f"Reference {ref} — in your itinerary and calendar, marked TEST.")
        st = await STORE.get_state(ch["wa_id_sha256"])
        await deliver(ch, frm, Out().text(f"🧪 {HT.LABEL}: {p['hotel']}, {SN.day_words(p['checkin'])}, {p['nights']} night"
                                          f"{'s' if p['nights'] != 1 else ''}. Reference {ref}. It's in your itinerary and calendar marked TEST — "
                                          f"nothing was reserved or charged. For a real room, ask for the hotel again and choose “Request from hotel”."),
                      st.get("last_inbound_at"))
        return
    st = await STORE.get_state(ch["wa_id_sha256"])
    await deliver(ch, frm, Out().text("The test payment wasn't completed within 10 minutes, so no test booking was made."), st.get("last_inbound_at"))


async def _flights(ctx: dict, body: str) -> None:
    from . import travel as TR
    out = ctx["out"]
    m = _FROM_TO.search(re.sub(r"^.*?\b(?:flights?|fly|vuelos?|volar)\b\s*(?:me\s+)?(?:for\s+\w+\s+)?", "", body or "", flags=re.I))
    day = HO.plain_date(body or "", ctx["now"])
    if not m or not day:
        out.text("Tell me from where, to where and the day, e.g. “flights from Madrid to Hanoi on 12 November for 2”.")
        return
    adults = HO.plain_party(body or "") or 1
    got = await TR.search(m["o"].strip(), m["d"].strip(), day, adults)
    if "why" in got:
        out.text(f"I can't search flights right now — {got['why']}. Nothing was booked.")
        return
    out.text(f"Flights {got['from']['name']} → {got['to']['name']}, {SN.day_words(day)}, {adults} {'adult' if adults == 1 else 'adults'} — "
             f"from Duffel in TEST mode (a test booking issues no ticket and charges nothing). The three cheapest:")
    for i, c in enumerate(got["cards"]):
        out.text(f"{i + 1}. {TR.card_line(c)}")
    nonce = secrets.token_hex(3)
    out.ask("Which one?", [(f"{c['flights'].split(' + ')[0]} {c['currency'].replace('EUR', '€')}{c['amount']}"[:20], f"pick:{nonce}:{i}")
                           for i, c in enumerate(got["cards"])])
    ctx["st"]["pending"] = {"kind": "flight_cards", "at": ctx["now"].isoformat(), "nonce": nonce, "cards": got["cards"], "adults": adults}


async def _flight_pick(ctx: dict, pend: dict, card: dict) -> None:
    from . import travel as TR, guest_receipt as GR
    _s, cj = await api(ctx["account"], "GET", "/api/booking/contact")
    contact = (cj or {}).get("contact") or {}
    try:
        email = await GR.address_of(ctx["account"])
    except Exception as e:   # the read-back then says "your account email" — never a guessed address
        log.info("[guest_whatsapp] no account email for the flight: %s", type(e).__name__)
        email = None
    lines = TR.read_back(card, contact.get("name") or "you", email or "")
    sha = hashlib.sha256("\n".join(lines).encode()).hexdigest()
    ctx["out"].text("Exactly what I'll do:\n" + "\n".join("• " + ln for ln in lines))
    rid = card["id"][-8:]
    ctx["out"].ask(f"Book it? {card['owner']} {card['flights']}, {card['currency']} {card['amount']} — TEST booking.",
                   [("Yes, book it", f"yes:{rid}:{sha[:16]}"), ("No", f"no:{rid}:{sha[:16]}")])
    ctx["st"]["pending"] = {"kind": "flight_confirm", "at": ctx["now"].isoformat(), "id": rid, "sha": sha, "card": card,
                            "name": contact.get("name") or "", "phone": contact.get("mobile_e164"), "email": email or ""}


async def _flight_approve(ctx: dict, pend: dict) -> None:
    from . import test_deposit as TD
    c = pend["card"]
    got = await TD.checkout(c["amount"], c["currency"], f"{c['owner']} {c['flights']} {c['from']}→{c['to']}", pend["sha"][:16])
    if "why" in got:
        ctx["out"].text(f"I can't take the test payment yet — {got['why']}. Nothing was booked.")
        return
    ctx["out"].text(f"One touch: pay the TEST fare ({c['currency']} {c['amount']}) on Stripe's test page — Apple Pay or your phone's saved card; "
                    f"nothing is charged, and I never see your card.\n{got['url']}\nI'll book the test flight the moment it's paid, and tell you here.")
    _spawn(watch_flight_payment(ctx["ch"], ctx["frm"], ctx["account"], c, got["id"], pend["name"], pend["email"], pend.get("phone")))


WATCH_PAY = (10, 60)   # every 10 s for 10 minutes


async def watch_flight_payment(ch: dict, frm: str, account: str, c: dict, session_id: str, name: str, email: str, phone: Optional[str]) -> None:
    from . import test_deposit as TD, travel as TR
    every, times = WATCH_PAY
    for _ in range(times):
        await asyncio.sleep(every)
        paid = await TD.session_paid(session_id)
        if not paid:
            continue
        o = await TR.order(c, name, email, phone)
        st = await STORE.get_state(ch["wa_id_sha256"])
        if "why" in o:
            TD.note(session_id, False, f"Your test payment went through, but the test flight wasn't booked: {o['why']}.")
            await deliver(ch, frm, Out().text(f"Your test payment went through, but the test flight wasn't booked: {o['why']}."), st.get("last_inbound_at"))
            return
        await TR.RECORD(account, c, o["booking_reference"] or "")
        TD.note(session_id, True, f"✅ Booked (TEST): {TR.card_line(c)}. Reference {o['booking_reference']}. In your itinerary and calendar.")
        await deliver(ch, frm, Out().text(f"✅ Booked (TEST): {TR.card_line(c)}. Reference {o['booking_reference']}. "
                                          f"It's in your itinerary and on your calendar — {TR.LABEL}."), st.get("last_inbound_at"))
        return
    st = await STORE.get_state(ch["wa_id_sha256"])
    await deliver(ch, frm, Out().text("The test payment wasn't completed within 10 minutes, so nothing was booked. Ask me again any time."),
                  st.get("last_inbound_at"))


# ── Sasha 126 · the spa membership (Kanoe Demo Spa, ours) and two bookings from one sentence ───────────────────────

SPA_CARD = {"place_id": "kanoe-demo-spa", "name": "Kanoe Demo Spa", "country": "ES"}
COMBO = re.compile(r"\b(restaurant|dinner|lunch|table|cena|comida|restaurante|mesa)\b.*\b(and|y)\b.*\b(spa|massage|masaje)\b"
                   r"|\b(spa|massage|masaje)\b.*\b(and|y)\b.*\b(restaurant|dinner|lunch|table|cena|restaurante|mesa)\b", re.I)
_SPA_T = re.compile(r"\b(?:spa|massage|masaje)\b\D{0,20}?(\d{1,2}(?:[:.h]\d{2})?\s*(?:am|pm|h)?)", re.I)
_EAT_T = re.compile(r"\b(?:dinner|lunch|restaurant|table|cena|comida|restaurante|mesa)\b\D{0,20}?(\d{1,2}(?:[:.h]\d{2})?\s*(?:am|pm|h)?)", re.I)


def _hhmm(s: str) -> Optional[str]:
    from .chat_request import _time
    s = (s or "").strip().lower()
    return _time(s) or HO.plain_time(f"at {s}") or (f"{int(s):02d}:00" if re.fullmatch(r"\d{1,2}", s) and 0 <= int(s) <= 23 else None)


def _at_time(text: str) -> Optional[str]:
    """"on Tuesday at 18:00", "at 6pm": the time said after "at"/"a las"."""
    m = re.search(r"\b(?:at|a las|a la)\s+(\d{1,2}(?:[:.h]\d{2})?\s*(?:am|pm|h)?)", text or "", re.I)
    return HO.context_time(text or "") or HO.plain_time(text or "") or (_hhmm(m[1]) if m else None)


def combo_times(text: str) -> dict:
    """{"spa": "18:00", "dinner": "21:00"} — each time said next to its own kind."""
    out = {}
    m = _SPA_T.search(text or "")
    if m and _hhmm(m[1]):
        out["spa"] = _hhmm(m[1])
    m = _EAT_T.search(text or "")
    if m and _hhmm(m[1]):
        out["dinner"] = _hhmm(m[1])
    return out


async def _combo_start(ctx: dict, body: str) -> None:
    from .chat_request import plain_day
    m = re.search(r"\bin ([A-ZÁÉÍÓÚ][\wáéíóúñ]+(?: [A-ZÁÉÍÓÚ][\wáéíóúñ]+)?)", body or "")
    combo = {"stage": "when", "where": f"{m[1]}" if m else "Madrid", "party": HO.plain_party(body or "") or 2,
             "day": plain_day(body or "", ctx["now"]), "times": combo_times(body or "")}
    ctx["st"]["combo"] = combo
    if combo["day"] and len(combo["times"]) == 2:
        await _combo_restaurant(ctx)
        return
    ctx["out"].text("Two bookings — a restaurant and a spa. Which day, and what time for each? For example: "
                    "“Tuesday — spa at 18:00, dinner at 21:00”.")
    ctx["st"]["pending"] = {"kind": "combo_when", "at": ctx["now"].isoformat()}


async def _combo_when(ctx: dict, pend: dict, body: str) -> bool:
    from .chat_request import plain_day
    combo = ctx["st"].get("combo") or {}
    combo["day"] = plain_day(body, ctx["now"]) or combo.get("day")
    combo["times"] = {**(combo.get("times") or {}), **combo_times(body)}
    ctx["st"]["combo"] = combo
    if combo.get("day") and len(combo["times"]) == 2:
        ctx["st"]["pending"] = None
        await _combo_restaurant(ctx)
        return True
    ctx["out"].text("I need the day and both times, e.g. “Tuesday — spa at 18:00, dinner at 21:00”.")
    return True


async def _combo_restaurant(ctx: dict) -> None:
    c = ctx["st"]["combo"]
    c["stage"] = "restaurant"
    at = f"{c['day']}T{c['times']['dinner']}"
    ctx["out"].text(f"First, the restaurant — {SN.day_words(c['day'])} at {c['times']['dinner']}, {c['party']} people:")
    await _find(ctx, {"what": "dinner", "where": c["where"], "country": "ES", "open_at": at},
                {"parts": {"what": {"activity": "a table", "activity_venue_lang": "una mesa", "category": "restaurant"},
                           "when": {"mode": "at", "at": at}, "how_many": {"count": c["party"], "unit": "people"}}})


async def _combo_spa(ctx: dict) -> None:
    from . import demo_spa as DSP
    c = ctx["st"]["combo"]
    c["stage"] = "spa"
    at = f"{c['day']}T{c['times']['spa']}"
    ctx["out"].text(f"Then the spa — {SN.day_words(c['day'])} at {c['times']['spa']}:")
    if await DSP.find_item(ctx["account"]):
        ctx["third_card"] = SPA_CARD
    await _find(ctx, {"what": "spa", "where": c["where"], "country": "ES", "open_at": at}, {"parts": {}})
    ctx.pop("third_card", None)


async def _combo_final(ctx: dict) -> None:
    from . import demo_spa as DSP
    c, out = ctx["st"]["combo"], ctx["out"]
    item = await DSP.find_item(ctx["account"])
    r = c.get("restaurant")
    if not item or not r:
        ctx["st"]["combo"] = None
        out.text("I don't have a saved Kanoe Demo Spa login in your vault. Add it in You → My accounts. Nothing was sent.")
        return
    spa_at = f"{c['day']}T{c['times']['spa']}"
    spa_lines = DSP.read_back(item["label"], spa_at, item["provider"])
    spa_sha = hashlib.sha256("\n".join(spa_lines).encode()).hexdigest()
    c.update({"stage": "confirm", "spa": {"id": str(item["id"]), "lines": spa_lines, "sha": spa_sha, "at": spa_at}})
    out.text("Exactly what I'll do — both, on one yes:\n1) " + r["venue"] + ":\n" + "\n".join("• " + _BULLET.sub("", ln) for ln in r["lines"])
             + "\n2) Kanoe Demo Spa:\n" + "\n".join("• " + ln for ln in spa_lines))
    both = hashlib.sha256(f"{r['sha']}|{spa_sha}".encode()).hexdigest()
    tag = f"{r['id'][:8]}:{both[:16]}"
    out.ask(f"Book both? {r['venue']}, {r['summary']}; and {DSP.TREATMENT[2]} at Kanoe Demo Spa, {SN.day_words(c['day'])} at "
            f"{c['times']['spa']}, with your saved membership.", [("Yes, book both", f"yes:{tag}"), ("No", f"no:{tag}")])
    ctx["st"]["pending"] = {"kind": "combo_confirm", "at": ctx["now"].isoformat(), "id": r["id"], "sha": both}


async def _combo_approve(ctx: dict, pend: dict, how: dict) -> None:
    from . import demo_spa as DSP, guest_receipt as GR
    from .vault.crypto import UseRefused
    c, out, account = ctx["st"].get("combo") or {}, ctx["out"], ctx["account"]
    ctx["st"]["combo"] = None
    r, spa = c.get("restaurant") or {}, c.get("spa") or {}
    s, j = await api(account, "POST", f"/api/booking/forms/{r['id']}/send", {"read_back_sha256": r["sha"], "approval": how}, timeout=120)
    result = (j.get("reading") or {}).get("result") if s == 200 and j.get("status") == "sent" else None
    ref = f" Their reference: {j['booking_reference']}." if result == "confirmed" and j.get("booking_reference") else ""
    out.text(f"✅ 1) Booked: {r['venue']}, {r['summary']}.{ref}" if result == "confirmed" else
             f"⚠ 1) Not confirmed yet: {r['venue']} — {j.get('say') or refusal_words(j, s)}")
    try:
        got = await DSP.place(account, spa["id"], spa["lines"], spa["sha"], ctx["now"].isoformat(), spa["at"], f"wa-{spa['sha'][:12]}")
    except UseRefused as e:
        out.text(f"❌ 2) Not booked at Kanoe Demo Spa: {e}.")
        return
    except Exception as e:
        out.text(f"❌ 2) Not booked at Kanoe Demo Spa — the portal didn't take it ({type(e).__name__}). Your login was used once and is logged.")
        return
    if got["status"] == "booked":
        out.text(f"✅ 2) Booked: {DSP.TREATMENT[2]} at Kanoe Demo Spa, {SN.day_words(spa['at'][:10])} at {spa['at'][11:16]}. "
                 f"Ref {got['ref']}. I used your saved membership once, for this booking — it's in your vault's log.")
        await GR.send_for_route(account, DSP.PROVIDER, "its own member portal, signed in with your saved login after your yes",
                                "Confirmed by the venue", {"what": DSP.TREATMENT[2], "when": spa["at"].replace("T", " at "), "party": 1,
                                                           "venue_reference": got["ref"], "their_words": got["their_page"]})
    else:
        out.text("⚠ 2) Not confirmed: Kanoe Demo Spa's page didn't say it's booked.")
    if _receipt_note():
        out.text("Both receipts are in your email; both bookings go on your calendar.")


async def _spa_start(ctx: dict, body: str) -> None:
    from . import demo_spa as DSP
    from .chat_request import plain_day
    item = await DSP.find_item(ctx["account"])
    if item is None:
        ctx["out"].text(f"I don't have a saved {DSP.PROVIDER} login in your vault. Add it in You → My accounts, then ask me again.")
        return
    day = plain_day(body or "", ctx["now"])
    t = _at_time(body)
    if not (day and t):
        ctx["out"].text("Which day and time for the massage?")
        ctx["st"]["pending"] = {"kind": "spa_when", "at": ctx["now"].isoformat(), "day": day, "t": t}
        return
    await _spa_ask(ctx, item, f"{day}T{t}")


async def _spa_when(ctx: dict, pend: dict, body: str) -> bool:
    from . import demo_spa as DSP
    from .chat_request import plain_day
    day = plain_day(body, ctx["now"]) or pend.get("day")
    t = _at_time(body) or _hhmm(body) or pend.get("t")
    if not (day and t):
        ctx["out"].text("I need the day and the time, e.g. “Tuesday at 18:00”.")
        return True
    ctx["st"]["pending"] = None
    await _spa_ask(ctx, await DSP.find_item(ctx["account"]), f"{day}T{t}")
    return True


async def _spa_ask(ctx: dict, item: dict, at: str) -> None:
    from . import demo_spa as DSP
    lines = DSP.read_back(item["label"], at, item["provider"])
    sha = hashlib.sha256("\n".join(lines).encode()).hexdigest()
    ctx["out"].text("Exactly what I'll do:\n" + "\n".join("• " + ln for ln in lines))
    rid = str(item["id"])
    ctx["out"].ask(f"Book {DSP.TREATMENT[2]} at {DSP.PROVIDER}, {SN.day_words(at[:10])} at {at[11:16]}, with your saved membership?",
                   [("Yes, book it", f"yes:{rid[:8]}:{sha[:16]}"), ("No", f"no:{rid[:8]}:{sha[:16]}")])
    ctx["st"]["pending"] = {"kind": "vault_spa", "at": ctx["now"].isoformat(), "id": rid, "sha": sha, "lines": lines, "when": at}


async def _spa_approve(ctx: dict, pend: dict) -> None:
    from . import demo_spa as DSP, guest_receipt as GR
    from .vault.crypto import UseRefused
    out = ctx["out"]
    try:
        got = await DSP.place(ctx["account"], pend["id"], pend["lines"], pend["sha"], ctx["now"].isoformat(), pend["when"], f"wa-{pend['sha'][:12]}")
    except UseRefused as e:
        out.text(f"❌ Not booked: {e}.")
        return
    except Exception as e:
        out.text(f"❌ Not booked — {DSP.PROVIDER} didn't take it ({type(e).__name__}). Your login was used once and is logged in your vault.")
        return
    if got["status"] != "booked":
        out.text(f"⚠ Not confirmed: {DSP.PROVIDER}'s page didn't say it's booked.")
        return
    out.text(f"✅ Booked: {DSP.TREATMENT[2]} at {DSP.PROVIDER}, {SN.day_words(pend['when'][:10])} at {pend['when'][11:16]}. Ref {got['ref']}. "
             f"I used your saved membership once, for this booking — it's in your vault's log.")
    out.text(f"Their page said: “{got['their_page'][:300]}”")
    await GR.send_for_route(ctx["account"], DSP.PROVIDER, "its own member portal, signed in with your saved login after your yes",
                            "Confirmed by the venue", {"what": DSP.TREATMENT[2], "when": pend["when"].replace("T", " at "), "party": 1,
                                                       "venue_reference": got["ref"], "their_words": got["their_page"]})


async def _reorder(ctx: dict) -> None:
    """Sasha 121 (F) · "reorder my usual from Kanoe Demo Market": the read-back names the saved login and the basket."""
    from . import demo_shop as DS
    out = ctx["out"]
    item = await DS.find_item(ctx["account"])
    if item is None:
        out.text(f"I don't have a saved login for {DS.PROVIDER} in your vault. Add it in You → My accounts, then ask me again.")
        return
    lines = DS.read_back(item["label"], item["provider"])
    sha = hashlib.sha256("\n".join(lines).encode()).hexdigest()
    out.text("Exactly what I'll do:\n" + "\n".join("• " + ln for ln in lines))
    rid = str(item["id"])
    out.ask(f"Reorder your usual from {DS.PROVIDER}?", [("Yes, order it", f"yes:{rid[:8]}:{sha[:16]}"), ("No", f"no:{rid[:8]}:{sha[:16]}")])
    ctx["st"]["pending"] = {"kind": "vault_order", "at": ctx["now"].isoformat(), "id": rid, "sha": sha, "lines": lines}


async def _reorder_approve(ctx: dict, pend: dict) -> None:
    from . import demo_shop as DS
    from .vault.crypto import UseRefused
    out = ctx["out"]
    try:
        got = await DS.place(ctx["account"], pend["id"], pend["lines"], pend["sha"], ctx["now"].isoformat(), f"wa-{pend['sha'][:12]}")
    except UseRefused as e:
        out.text(f"❌ Not ordered: {e}.")
        return
    except Exception as e:
        out.text(f"❌ Not ordered — {DS.PROVIDER} didn't take it ({type(e).__name__}). Your login was used once and is logged in your vault.")
        return
    if got["status"] == "ordered":
        out.text(f"✅ Ordered from {DS.PROVIDER}: order {got['ref']}. I used your saved login once, for this order — it's in your vault's log.")
    else:
        out.text(f"⚠ Not confirmed: {DS.PROVIDER}'s page didn't say the order went through.")
    if got.get("their_page"):
        out.text(f"Their page said: “{got['their_page'][:400]}”")


async def _forwarded_confirmation(ctx: dict, body: str) -> bool:
    """Sasha 118 (3) · a guest forwards (or pastes) a venue's confirmation: filed on the ONE booking it names (written.py),
    read with the field checks, and answered here. Not a confirmation → False (the turn goes on)."""
    from . import mailbox as MB, written as W
    if len(body or "") < 40 or not MB._CONFIRM.search(body or "") or not MB._when(body, ctx["now"]):
        return False
    if HO.booking_handoff(body, []) is not None:   # a new request that happens to say "your booking" is a request
        return False
    now, out = ctx["now"], ctx["out"]
    sid = "wa-fwd-" + hashlib.sha256(f"{ctx['account']}|{body}".encode()).hexdigest()[:24]
    try:
        got = await W.file(sid, "whatsapp", ctx["ch"].get("number_e164"), None, body, now, account=ctx["account"], forwarded=True)
    except Exception as e:
        log.error("[guest_whatsapp] a forwarded confirmation was not filed: %s: %s", type(e).__name__, e)
        got = None
    if got is None:
        out.text("That reads like a booking confirmation, but I can't tell which of your bookings it's for — it needs their "
                 "reference, or the venue's name and the day. Nothing was changed.")
        return True
    when = SN.day_words(got.get("day")) if got.get("day") else ""
    if got["result"] == "confirmed":
        out.text(f"✅ Confirmed in writing: {got['venue']}{', ' + when if when else ''}. I've filed their confirmation on it (forwarded by you).")
    elif got["result"] == "already filed":
        out.text(f"I already have that confirmation on {got['venue']}.")
    elif got["result"] == "proposed":
        out.text(f"⚠ {got['venue']}'s message offers something different — {got['why']}. I've filed it on the booking; nothing else changed.")
    else:
        out.text(f"I've filed it on {got['venue']}{', ' + when if when else ''}, but it doesn't confirm the day, time and number "
                 f"together, so I haven't marked it confirmed.")
    return True


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


async def _invite(ctx: dict, req: dict) -> None:
    """S-80 path I · the invitation, sent by the INVITER from their own WhatsApp (Sasha writes to no one new)."""
    from . import invitations as IV
    out = ctx["out"]
    if req["window"] is None:
        out.text(f"Which days for {req['activity']} with {req['invitee']} — this week, next week, or a day?")
        ctx["st"]["pending"] = {"kind": "invite_window", "at": ctx["now"].isoformat(), "req": {**req, "window": None}}
        return
    s, cj = await api(ctx["account"], "GET", "/api/booking/contact")
    first = (((cj.get("contact") or {}).get("name") or "").split() or [""])[0] if s == 200 else ""
    if not first:
        out.text(NO_CONTACT.format(web=web_url()))
        return
    inv = await IV.create(ctx["account"], first, req, ctx["now"])   # Sasha 118 · as typed
    if not inv["slots"]:
        out.text(f"I couldn't find a time you're free for {req['activity']} then. Tell me other days.")
        return
    lines = "\n".join(f"• {IV.slot_words(x)}" for x in inv["slots"])
    seen = "I can't see your calendar, so these are suggestions:" if inv["unseen"] else "Times you're free:"
    out.text(f"{seen}\n{lines}")
    out.text(f"Send {req['invitee']} this invitation from your own WhatsApp — it opens a page where they pick a time; I don't "
             f"message them unless they ask me to:\n{IV.share_link(first, req['activity'], inv['code'])}")
    out.text("When they pick, I'll tell you here — and the booking stays yours: nothing is booked until your yes.")


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
    luxe = any(q in HO.LUXURY for q in HO.qualities(f.get("what") or ""))
    if luxe:   # Sasha 104 · "luxury": Google's €€€ and €€€€ first, best rated within; the rest after, never dropped
        order = sorted(order, key=lambda pid: not ((cands.get(pid) or {}).get("price_level") or 0) >= 3)
    shown = [cands[i] for i in order if i in cands][:3]
    if not shown:
        out.text(f"I found no {f.get('what')} in {f.get('where')}. Try another area or kind of place.")
        return
    pick = shown[0]["place_id"] if luxe else (ranking.get("picks") or {}).get(chip)
    photos = await _photos(account, f.get("what") or "", shown)
    if ctx.get("third_card"):   # Sasha 126 · the combo's spa set: OUR demo spa as the third card
        shown = shown[:2] + [ctx["third_card"]]
    elif rehearsal(account) and not ctx.get("no_test_card"):   # Sasha 117 · the dress rehearsal books OUR test venue; the card says so
        shown = shown[:2] + [TEST_CARD]                   # still three: WhatsApp shows at most three reply buttons
    what = f.get("what") or ""
    out.text(f"{what[:1].upper() + what[1:]} in {f.get('where')} — {ranking.get('count') or f'{len(cands)} found'}"
             f"{' · €€€ and up first' if luxe else ''}. From Google Maps; nobody has been contacted.")
    for c in shown:
        line = " · ".join(x for x in (c.get("name") or "no name listed", rating_words(c),
                                       distance_words(c["distance_m"]) if c.get("distance_m") is not None else None) if x)
        if c is TEST_CARD:
            line = "Rehearsal · Sasha Test Venue — ours, not a real restaurant: booking it contacts no one"
        elif c is SPA_CARD:
            line = "Kanoe Demo Spa — ours, a demo member portal: Sasha books it with your saved membership"
        out.media(("Sasha's pick · " if c["place_id"] == pick else "") + line, photos.get(c["place_id"]))
    nonce = secrets.token_hex(3)
    out.ask("Which one?", [(c.get("name") or f"Option {i + 1}", f"pick:{nonce}:{i}") for i, c in enumerate(shown)])
    ctx["st"]["pending"] = {"kind": "cards", "at": ctx["now"].isoformat(), "nonce": nonce, "find": f,
                            "draft": draft.get("parts") or {},
                            "cards": [{"place_id": c["place_id"], "name": c.get("name"), "country": c.get("country")} for c in shown]}


TEST_CARD = {"place_id": "sasha-test-venue", "name": "Sasha Test Venue", "country": "ES"}


def rehearsal(account: str) -> bool:
    """SASHA_REHEARSAL=1, and only on the founder's own account: the cards end with our test venue."""
    from .identity import founder_account
    return os.getenv("SASHA_REHEARSAL", "") == "1" and account == founder_account()


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
    # Sasha 117 · "Cancel the Retiro dinner" while cards (or another open question) show is a CANCELLATION, never a
    # refinement or an answer — live, it searched for "Cancel Retiro dinner dinner". Not for a yes/no on a booking or a
    # cancel ("No, cancel" there means "don't"). A new cancel while the which-one list shows starts a fresh list.
    if not payload and kind not in ("confirm", "cancel_confirm") and cancel_intent(body) is not None \
            and not (kind == "cancel_pick" and re.fullmatch(r"\D*\d{1,2}\D*", body or "")):
        st["pending"] = None
        return False
    if kind == "cards":
        if now - at > CARDS_LIFE:
            st["pending"] = None
            return False
        i = _picked(pend, body, payload)
        if i is None:
            # Sasha 104 · while the cards show, anything that is not a pick is a REFINEMENT of this search: the area,
            # day, time and party are kept unless the message changes them; the kind of place is replaced; every
            # quality asked for is kept. A plain yes/no/thanks gets the question again.
            merged = refine(pend, body, ctx["now"])
            if merged is None:
                out.text("Which one? Tap a name, or send its number (1, 2 or 3) — or tell me what else to look for.")
                return True
            st["pending"] = None
            await _find(ctx, merged[0], {"parts": merged[1]})
            return True
        await _picked_card(ctx, pend, pend["cards"][i])
        return True
    if kind == "need":
        return await _answer_need(ctx, pend, body)
    if kind == "invite_window":   # S-80 · the days, asked once
        from . import invitations as IV
        w = IV.window(body, now)
        st["pending"] = None
        if w is None:
            return False
        await _invite(ctx, {**pend["req"], "window": w})
        return True
    if kind == "invite_where":   # S-80 · the inviter names the area for the slot their guest picked
        from . import invitations as IV
        area = re.sub(r"^\s*(?:in|en|near|around)\s+", "", body or "", flags=re.I).strip(" .!?")
        if not area or cancel_intent(body) is not None:
            st["pending"] = None
            return False
        st["pending"] = None
        await _find(ctx, IV.HO_find(pend["activity"], area, pend["open_at"]), {"parts": pend["draft"]})
        if st.get("pending"):
            st["pending"]["invite_code"] = pend["invite_code"]
        return True
    if kind == "cancel_pick":
        m = re.fullmatch(r"\s*(\d)\s*[.)]?\s*", body or "")
        i = int(m[1]) - 1 if m else next((k for k, r in enumerate(pend["rows"]) if body and _fold(body).strip() in _fold(r["venue"])), None)
        if i is None or not 0 <= i < len(pend["rows"]):
            if cancel_intent(body) is None and HO.booking_handoff(body, []) is not None:
                st["pending"] = None
                return False
            out.text("Reply with the number of the booking to cancel.")
            return True
        st["pending"] = None
        await _cancel_row(ctx, pend["rows"][i])
        return True
    if kind == "mailbox":   # S-82 · ONE find from their inbox, one yes
        if payload.startswith(("yes:", "no:")) or YS.is_yes(body) or _NO.match(body or ""):
            st["pending"] = None
            yes = payload.startswith("yes:") or (not payload and YS.is_yes(body))
            status, j = await api(ctx["account"], "POST", f"/api/booking/mailbox/finds/{pend['id']}", {"offer_sha256": pend["sha"], "yes": yes})
            out.text(str(j.get("say")) if status == 200 else f"Not changed — {refusal_words(j, status)}.")
            return True
        return False
    if kind == "payment":   # S-81 tier 0 · the deposit: one yes asks the venue for ITS link; the guest pays them directly
        if payload.startswith("no:") or (not payload and _NO.match(body)):
            st["pending"] = None
            out.text(f"OK — I haven't asked {pend['venue']} for anything. The booking isn't confirmed without their deposit.")
            return True
        if payload.startswith("yes:") or YS.is_yes(body):
            if now - at > APPROVAL_WINDOW:
                st["pending"] = None
                out.text("That question has expired (15 minutes) — nothing was asked. Tell me if you still want the link.")
                return True
            st["pending"] = None
            how = {"how": "whatsapp_button", "said": ctx.get("button_text") or None} if payload else {"how": "whatsapp_text", "said": body}
            status, j = await api(ctx["account"], "POST", f"/api/booking/payments/{pend['id']}/approve", {"read_back_sha256": pend["sha"], "approval": how})
            out.text(str(j.get("say")) if status == 200 else f"Not asked — {refusal_words(j, status)}.")
            return True
        return False
    if kind == "engine_check":   # Sasha 139 · the founder checks each hotel engine link: "filled" / "not filled" (+ "wrong page")
        m = re.match(r"^\s*(?:(?P<n>[1-9])\s*[:.)-]?\s*)?(?P<a>not\s+filled|filled|wrong(?:\s+page)?|right(?:\s+page)?)\b", body or "", re.I)
        if not m:
            return False
        todo = [h for h in pend["hotels"] if str(h["n"]) not in pend.get("answers", {})]   # str keys: the state is stored as JSON
        h = next((x for x in pend["hotels"] if m["n"] and x["n"] == int(m["n"])), todo[0] if todo else None)
        if h is None:
            st["pending"] = None
            return False
        ans = re.sub(r"\s+", " ", m["a"].lower())
        pend.setdefault("answers", {})[str(h["n"])] = {"answer": ans, "said": body, "at": now.isoformat()}
        left = len([x for x in pend["hotels"] if str(x["n"]) not in pend["answers"]])
        out.text(f"Noted — {h['name']} ({h['engine']}): {ans}." + (f" {left} to go." if left else " That's all three — thank you."))
        st["pending"] = pend if left else {**pend, "kind": "engine_check_done"}
        log.info("[guest_whatsapp] engine check: %s %s → %s", h["name"], h["engine"], ans)
        return True
    if kind == "engine_check_done":
        return False
    if kind == "hotel_choice":   # Sasha 135 · TEST booking, or the real request to the hotel
        st["pending"] = None
        if payload.startswith("test:") or re.search(r"\btest\b", body or "", re.I):
            await _hotel_test_ask(ctx, pend)
            return True
        if payload.startswith("req:") or re.search(r"\b(request|ask|real|book with)\b", body or "", re.I):
            await _picked_card(ctx, {**pend["cards_pend"], "real": True}, pend["card"])
            return True
        out.text("Tap “Test booking” or “Request from hotel”.")
        st["pending"] = pend
        return True
    if kind == "hotel_test_confirm":
        if payload.startswith("no:") or (not payload and _NO.match(body)):
            st["pending"] = None
            out.text("OK — no test booking made.")
            return True
        if payload.startswith("yes:") or YS.is_yes(body):
            st["pending"] = None
            await _hotel_test_pay(ctx, pend)
            return True
        out.text("Tap Yes or No.")
        return True
    if kind == "flight_cards":   # Sasha 132
        i = _picked(pend, body, payload)
        if i is None and re.fullmatch(r"\s*[123]\s*", body or ""):
            i = int(body.strip()) - 1
        if i is None or i >= len(pend["cards"]):
            st["pending"] = None
            return False
        await _flight_pick(ctx, pend, pend["cards"][i])
        return True
    if kind == "flight_confirm":
        if payload.startswith("no:") or (not payload and _NO.match(body)):
            st["pending"] = None
            out.text("OK — nothing booked.")
            return True
        if payload.startswith("yes:") or YS.is_yes(body):
            st["pending"] = None
            if now - at > APPROVAL_WINDOW:
                out.text("That question has expired (15 minutes) — nothing was booked. Ask me again.")
                return True
            await _flight_approve(ctx, pend)
            return True
        out.text("Tap Yes or No — nothing is booked until you do.")
        return True
    if kind == "plan_link":   # Sasha 132 · the one yes to the whole plan → the page, made with the plan in its read-back
        if payload.startswith("no:") or (not payload and _NO.match(body)):
            st["pending"] = None
            out.text("OK — nothing sent.")
            return True
        if payload.startswith("yes:") or YS.is_yes(body):
            st["pending"] = None
            if not await _send_link(ctx, pend["read"], pend["reservation"], pend["contact_name"], pend["plan"],
                                    {"read": pend["read"], "draft": pend["draft"], "invite_code": pend.get("invite_code")}):
                out.text("I couldn't make their booking page just now. Nothing was sent.")
            return True
        return False
    if kind == "no_reply_call":   # Sasha 130 · yes → the call's OWN read-back and yes; no → nothing
        if payload.startswith("no:") or (not payload and _NO.match(body)):
            st["pending"] = None
            out.text("OK — nothing more. I'll show you their reply if one arrives.")
            return True
        if payload.startswith("yes:") or YS.is_yes(body):
            st["pending"] = None
            await _prepare_or_ask(ctx, {"kind": "need", "at": now.isoformat(), "read": pend["read"], "draft": pend["draft"],
                                        "prefer": pend.get("prefer") or "call"})
            return True
        return False
    if kind in ("combo_when", "spa_when"):   # Sasha 126 · the day and the time(s), asked once
        if kind == "combo_when":
            return await _combo_when(ctx, pend, body)
        return await _spa_when(ctx, pend, body)
    if kind in ("vault_spa", "combo_confirm"):   # Sasha 126 · one yes
        if payload.startswith("no:") or (not payload and _NO.match(body)):
            st["pending"] = None
            st.pop("combo", None)
            out.text("OK — nothing was booked, and your membership login wasn't opened.")
            return True
        if payload.startswith("yes:") or YS.is_yes(body):
            st["pending"] = None
            if now - at > APPROVAL_WINDOW:
                out.text("That question has expired (15 minutes) — nothing was booked. Ask me again.")
                return True
            how = {"how": "whatsapp_button", "said": ctx.get("button_text") or None} if payload else {"how": "whatsapp_text", "said": body}
            await (_spa_approve(ctx, pend) if kind == "vault_spa" else _combo_approve(ctx, pend, how))
            return True
        out.text("Tap Yes or No — nothing is booked until you do.")
        return True
    if kind == "vault_order":   # Sasha 121 (F) · one yes, one use of the saved login
        if payload.startswith("no:") or (not payload and _NO.match(body)):
            st["pending"] = None
            out.text("OK — nothing was ordered, and your login wasn't opened.")
            return True
        if payload.startswith("yes:") or YS.is_yes(body):
            st["pending"] = None
            if now - at > APPROVAL_WINDOW:
                out.text("That question has expired (15 minutes) — nothing was ordered. Ask me again.")
                return True
            await _reorder_approve(ctx, pend)
            return True
        out.text("Tap Yes or No — nothing is ordered until you do.")
        return True
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
        from . import decide as D
        want = D.preference(body) if kind == "confirm" and pend.get("read") else None
        if want and want != {"form": "form", "call": "call", "email": "email", "call_email": "call_email"}.get(pend.get("rung")):   # Sasha 130 · the override
            st["pending"] = None
            await _prepare_or_ask(ctx, {"kind": "need", "at": now.isoformat(), "read": pend["read"], "draft": pend["draft"],
                                        "invite_code": pend.get("invite_code"), "prefer": want})
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
            if status != 200:
                out.text(f"I couldn't record it — {refusal_words(j, status)}.")
                return True
            out.text("Noted — booked on their page, by you. I'm looking for their confirmation email in your Gmail now.")
            _spawn(watch_gmail_confirmation(ctx["ch"], ctx["frm"], ctx["account"], pend.get("venue") or "", pend.get("when") or ""))
            return True
        from . import decide as D
        want = D.preference(body)
        if want and want != "one_tap" and pend.get("read"):   # Sasha 130 · "call them instead" — the guest's way
            st["pending"] = None
            await _prepare_or_ask(ctx, {"kind": "need", "at": now.isoformat(), "read": pend["read"], "draft": pend["draft"],
                                        "invite_code": pend.get("invite_code"), "prefer": want})
            return True
        return False
    return False


_REFINE = re.compile(r"^\s*¿?\s*(?:how about|what about|maybe|or|rather|instead|actually|y|qu[eé] tal|mejor|o)\s+(?:some\s+|an?\s+|algo de\s+|un\s+|una\s+)?"
                     r"(?P<what>[^?.!]{2,60}?)\s*(?:instead|then|please|por favor|mejor)?\s*[?.!]*\s*$", re.I)


_FIND_ONLY = re.compile(r"\b(?:find|look for|search for|get|book|show)\s+(?:me\s+|us\s+)?(?:an?\s+|some\s+|the\s+)?"
                        r"(?P<what>[a-z][\w'’ -]{1,40}?)\s*(?:spot|place|restaurant|instead)?\s*(?:[?.!,;]|$)", re.I)
_LIKES = re.compile(r"\b(?:likes?|loves?|prefers?|fancy|fancies|craving|in the mood for|le gusta|prefiere|nos apetece)\s+"
                    r"(?P<what>[a-záéíóúñ][\w ]{1,30}?\s+(?:food|cuisine|restaurants?|comida|cocina))\b", re.I)
_QUALITY = re.compile(r"\b(luxury|luxurious|upscale|fancy|fine[- ]dining|romantic|cheap|casual|quiet|vegetarian|vegan|lujo|"
                      r"rom[aá]ntico)\b", re.I)


_MEAL = re.compile(r"\b(dinner|lunch|breakfast|brunch|supper)\b", re.I)
_NOT_A_KIND = re.compile(r"\b(food|cuisine|comida|cocina|spot|place|restaurants?|restaurante|sitio|so|actually|well|ok|okay|hmm|"
                         r"please|por favor|my|wife|husband|partner|girlfriend|boyfriend|friend|we|i|she|he|they|likes?|loves?|"
                         r"prefers?|would|like|want|wants|can|could|you|find|search|look|for|get|show|me|us|an?|the|some|"
                         r"something|somewhere|instead|then|how|what|about|maybe|rather|really|y|o|qu[eé]|tal|mejor|algo|de|un|"
                         r"una|and|e|is|it|that|this|one|more|other|another|different|do|have|any|nice|good|great|"
                         r"no|nah|nope|yes|yeah|thanks|thank|gracias|vale|s[ií])\b", re.I)


_WHEN_WORDS = re.compile(r"\b(today|tonight|tomorrow|at|on|am|pm|next|week|hoy|mañana|esta|noche|"
                         r"monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", re.I)


def refine(pend: dict, body: str, now) -> Optional[tuple]:
    """(the new find, the draft) for a message said while the cards show — or None when it asks nothing new."""
    f, draft = dict(pend["find"]), dict(pend.get("draft") or {})
    said = HO.spoken(body or "")
    new_q = HO.qualities(said)
    whole = HO.find_request(said, now)                     # a new area (and maybe a new kind): take what it names
    if whole:
        f.update({k: v for k, v in whole.items() if k in ("where", "country", "near", "open_at")})
    else:
        am = re.search(r"\b(?:in|near|around|en|cerca de)\s+(?P<where>[A-ZÁÉÍÓÚ][^?.!,;]{1,60}?)\s*(?:[?.!,;]|$)", said)
        if am:                                             # "how about Indian in Malasaña": the area moves, the rest stays
            kp = HO.known_place(am["where"].strip())
            f.update({"where": f"{kp[0]}, {kp[1]}" if kp and kp[1] else am["where"].strip()}, **({"country": kp[2]} if kp else {}))
            said = said[:am.start()] + said[am.end():]
        if HO.plain_open_at(said, now) and re.search(r"\d|\b(?:at|a las)\b", said):
            f["open_at"] = HO.plain_open_at(said, now)
    party = HO.plain_party(said)
    if party:
        draft["how_many"] = {"count": party, "unit": "people"}
    rest = HO._QUALITY.sub(" ", said)
    for name, code in HO.COUNTRY_NAMES.items():   # Sasha 126 · "in Hanoi, Vietnam": the country, never a kind of place
        if re.search(rf"\b{name}\b", rest, re.I):
            rest, f["country"] = re.sub(rf"\b{name}\b", " ", rest, flags=re.I), code
    rest = _WHEN_WORDS.sub(" ", rest)
    rest = _NOT_A_KIND.sub(" ", re.sub(r"[^\wáéíóúñü' -]", " ", rest))
    kind = " ".join(dict.fromkeys(w for w in rest.split() if w.isalpha() and len(w) > 1))
    if whole and whole.get("what"):
        # Sasha 126 · a whole new request names its own kind: "dinner … in Hanoi, Vietnam tomorrow" is dinner, never the
        # leftover words ("Hanoi Vietnam tomorrow at")
        kind = _MEAL.sub("", re.sub(HO._QUALITY, "", whole["what"])).strip()
    if not (kind or new_q or whole or party or f.get("open_at") != pend["find"].get("open_at")):
        return None
    old = f.get("what") or ""
    old_q = HO.qualities(old)
    meal = (_MEAL.search(old) or [None])[0]
    base = f"{kind} {meal.lower() if meal else 'restaurant'}" if kind else HO._QUALITY.sub("", old).strip()
    f["what"] = " ".join(list(dict.fromkeys(new_q + old_q)) + [re.sub(r"\s+", " ", base).strip()])
    f.pop("priority", None)
    return f, draft


def _payload_ok(pend: dict, payload: str) -> bool:
    """A button answers ONLY the question it was sent with: its id names this card set, or this call and its hash."""
    if pend["kind"] in ("cards", "flight_cards"):
        return payload.startswith(f"pick:{pend['nonce']}:")
    tag = f"{str(pend.get('id', ''))[:8]}:{str(pend.get('sha', ''))[:16]}"
    if pend["kind"] == "hotel_choice":   # Sasha 135
        return payload in (f"test:{tag}", f"req:{tag}")
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

#: Sasha 121 · cuisines (EN/ES): a search for one of these is a search for a table
CUISINE = re.compile(r"\b(japanese|japon[eé]s[a]?|sushi|ramen|indian|indi[oa]|italian[oa]?|italiano|chinese|chino|thai|tailand[eé]s|"
                     r"mexican[oa]?|peruvian[oa]?|peruano|korean[oa]?|coreano|vietnamese|vietnamita|french|franc[eé]s|spanish|"
                     r"espa[nñ]ol[a]?|tapas|mediterranean|mediterr[aá]ne[oa]|greek|grieg[oa]|lebanese|liban[eé]s|turkish|turc[oa]|"
                     r"vegan[oa]?|vegetarian[oa]?|steak|seafood|marisco|marisquer[ií]a|pizza|pizzer[ií]a|burger|hamburguesa|"
                     r"asador|brunch|fusion|fusi[oó]n|nikkei|argentin[oa]|galleg[oa]|vasc[oa])\b", re.I)


async def _picked_card(ctx: dict, pend: dict, card: dict) -> None:
    out, account, f = ctx["out"], ctx["account"], pend["find"]
    if (ctx["st"].get("combo") or {}).get("stage") == "spa":   # Sasha 126 · the combo's second pick
        if card.get("place_id") == SPA_CARD["place_id"]:
            await _combo_final(ctx)
        else:
            out.text(f"Together with the restaurant, I can book only Kanoe Demo Spa today. Tap it, or ask me for "
                     f"{card.get('name') or 'that spa'} on its own. Nothing was sent.")
            ctx["st"]["pending"] = pend
        return
    if (pend.get("draft") or {}).get("nights") and not pend.get("real"):   # Sasha 135 · a hotel: TEST booking, or the real request
        await _hotel_choice(ctx, pend, card)
        return
    if card.get("place_id") == TEST_CARD["place_id"]:
        from .form_rung import test_venue_url
        status, read = await api(account, "POST", "/api/booking/venues/read",
                                 {"name": TEST_CARD["name"], "city": f.get("where") or "Madrid", "country": "ES", "website": test_venue_url()})
    else:
        status, read = await api(account, "POST", "/api/booking/venues/read",
                                 {"name": card.get("name") or f.get("what"), "city": f.get("where"), "country": card.get("country") or f.get("country"),
                                  "place_id": card["place_id"], "asked_for": f.get("what")})
    if status != 200:
        ctx["st"]["pending"] = None
        out.text(f"I couldn't read how {card.get('name') or 'they'} take bookings — {refusal_words(read, status)}.")
        return
    venue = (read.get("listing") or {}).get("name") or card.get("name") or read.get("venue")
    rungs = {r["rung"]: r for r in read.get("rungs") or [] if r.get("available")}
    if not any(k in rungs for k in ("form", "link", "phone", "email")):   # Sasha 135 · an email-only venue has a route (Sasha 130)
        ctx["st"]["pending"] = None
        out.text(f"{read.get('say') or 'I found no way to book them that I may use.'} Nothing was sent.")
        return
    draft = dict(pend.get("draft") or {})
    if "what" not in draft:
        _s, d = await api(account, "POST", "/api/booking/draft", {"text": f.get("what"), "country": read.get("country") or f.get("country")})
        if (d.get("parts") or {}).get("what"):
            draft["what"] = d["parts"]["what"]
        elif CUISINE.search(f.get("what") or ""):   # Sasha 121 · "Japanese in Salamanca" — a cuisine is a table, not a question
            _s, d = await api(account, "POST", "/api/booking/draft", {"text": f"{f.get('what')} restaurant", "country": read.get("country") or f.get("country")})
            if (d.get("parts") or {}).get("what"):
                draft["what"] = d["parts"]["what"]
    if f.get("open_at") and (draft.get("when") or {}).get("mode") != "at":
        draft["when"] = {"mode": "at", "at": f["open_at"]}
    nxt = {"kind": "need", "at": ctx["now"].isoformat(), "invite_code": pend.get("invite_code"),
           "read": {"read_id": read["read_id"], "country": read.get("country"),
           "venue": venue, "rungs": {k: {"fact_index": r.get("fact_index"), "value": r.get("value")} for k, r in rungs.items()},
           **_hours_of(read, ctx["now"])},
           "draft": draft}
    await _prepare_or_ask(ctx, nxt)


def dv_platform(rd: dict) -> str:
    from . import venue_read as V
    link = ((rd.get("rungs") or {}).get("link") or {}).get("value") or ""
    return (V.platform_of(link) if link.startswith("http") else link) or "their booking platform"


async def _send_link(ctx: dict, rd: dict, reservation: dict, name: str, plan: Optional[str], keep: dict) -> bool:
    """The one-tap page, made (with the approved plan in its read-back, Sasha 132) and sent. Sasha 138 · a hotel stay: its own
    booking engine, the dates in the link where the engine takes them — the guest pays there, in one tap."""
    at = reservation["when"]["at"]
    nights = (keep.get("draft") or {}).get("nights")
    status, j = await api(ctx["account"], "POST", "/api/booking/links", {"read_id": rd["read_id"], "date": at[:10], "time": at[11:16],
                                                                          "party": reservation["how_many"]["count"], "name": name,
                                                                          **({"plan_line": plan} if plan else {}),
                                                                          **({"nights": int(nights)} if nights else {})})
    if status != 200:
        return False
    ctx["st"]["pending"] = {"kind": "link", "at": ctx["now"].isoformat(), "link_id": j["link_id"], "venue": rd["venue"], "when": at, **keep}
    if nights:
        lines = (j.get("read_back") or {}).get("lines") or []
        ctx["out"].text(f"One tap: {rd['venue']}'s own booking engine ({j.get('platform') or 'their booking page'}).\n"
                        + "\n".join("• " + ln for ln in lines) + f"\n{j['url']}")
        return True
    ctx["out"].text(f"One tap: {rd['venue']}'s booking page on {j.get('platform') or 'their platform'} — "
                    f"{'the day, time and party are filled in' if j.get('slot_filled') else 'choose the day, time and party there'}. "
                    f"Press their confirm button; I can't press it for you.\n{j['url']}\n"
                    f"Reply BOOKED once it's done, and I'll find their confirmation email in your Gmail and file it.")
    return True


def _hours_of(read: dict, now) -> dict:
    """Sasha 130 · open now / next opening, in the venue's own day — for the decision. Unknown stays unknown (None)."""
    from . import hours as H, venue_read as V
    tz = (V.COUNTRIES.get(read.get("country") or "") or (None, None, None, "Europe/Madrid"))[3]
    try:
        s = H.status(read, now, tz)
    except Exception as e:
        log.info("[guest_whatsapp] no hours: %s", type(e).__name__)
        return {"open_now": None, "opens_at": None}
    return {"open_now": s.get("open_now"), "opens_at": (s.get("opens_at") or "")[11:16] or None}


def decision_of(rd: dict, prefer: Optional[str] = None, at: Optional[str] = None, now=None):
    """Sasha 130 · the read, as the decision workflow sees it. Sasha 131 · `at` (the booking's local time) makes it urgent."""
    from . import calls as C, decide as D, venue_read as V
    rungs = rd.get("rungs") or {}
    country = V.COUNTRIES.get(rd.get("country") or "") or (None, None, "en", "Europe/Madrid")
    lang = country[2]
    hours = None
    if at and now:
        try:
            from zoneinfo import ZoneInfo
            hours = (datetime.fromisoformat(at).replace(tzinfo=ZoneInfo(country[3])) - now).total_seconds() / 3600
        except Exception:
            hours = None
    link = (rungs.get("link") or {}).get("value") or ""   # the link rung's value is the platform's NAME ("CoverManager")
    name = (V.platform_of(link) if link.startswith("http") else link) or "an online booking platform"
    return D.decide(D.Venue(form="form" in rungs, platform=name if "link" in rungs else None,
                            phone="phone" in rungs, email="email" in rungs, open_now=rd.get("open_now"), opens_at=rd.get("opens_at"),
                            scripted=lang in C.LANGUAGES, calls_on=True, language_label=C.LANGUAGE_NAMES.get(lang, ""),
                            hours_until=hours), prefer)


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
    why = None
    # Sasha 130 · THE DECISION (decide.py): the route, and its reason said to the guest first; the others in order after it
    dv = decision_of(rd, pend.get("prefer"), (reservation.get("when") or {}).get("at"), ctx["now"])
    combo = (st.get("combo") or {}).get("stage") == "restaurant"
    order = [r for r in [dv.route] + dv.alternatives if r] if not combo else ["form"]
    if dv.route and not combo:
        out.text(dv.reason)
    keep = {"read": rd, "draft": d, "invite_code": pend.get("invite_code")}   # so "call them instead" can re-decide
    for route in order:
        if route == "form" and "form" in rungs:
            # Sasha 117 · a form wants an email: the account's own (the one receipts go to), shown in the read-back the yes approves
            from . import guest_receipt as GR, ladder_routes as LR
            email = await GR.address_of(ctx["account"]) if LR.LADDER_STORE is not None else None
            res_form = {**reservation, "who": {**reservation["who"], "contact": {**reservation["who"]["contact"], **({"email": email} if email else {})}}}
            from . import loyalty as LY   # Sasha 131 (3) · a matching loyalty number from the vault, under this yes
            ly = await LY.find_for(ctx["account"], rd["venue"], (d.get("what") or {}).get("category"))
            status, j = await api(ctx["account"], "POST", "/api/booking/forms", {"read_id": rd["read_id"], "reservation": res_form,
                                                                                 **({"loyalty_item_id": str(ly["id"])} if ly else {})})
            if status == 200:
                if combo:   # Sasha 126 · held for the ONE combined yes
                    st["combo"]["restaurant"] = {"id": j["form_id"], "sha": j["read_back"]["sha256"], "lines": j["read_back"]["lines"],
                                                 "venue": rd["venue"], "summary": summary(reservation)}
                    st["pending"] = None
                    await _combo_spa(ctx)
                    return
                await _ask_yes(ctx, "form", j["form_id"], j["read_back"], SN.confirm_sentence(reservation, rd["venue"]), rd["venue"],
                               extra={"summary": summary(reservation), **keep})
                return
            why = refusal_words(j, status)
            log.warning("[guest_whatsapp] form rung refused (%s: %s); trying the next route", status, j.get("rule"))
        if combo:   # Sasha 126 · together, only through their own form today
            st["combo"], st["pending"] = None, None
            out.text(f"I can't book {rd['venue']} together with the spa from here (no form I may send{', and calls are off' if 'phone' in rungs else ''}). "
                     f"Nothing was sent. Pick a place I can book by its form, or ask for each one separately.")
            return
        if route == "one_tap" and "link" in rungs and reservation["when"]["mode"] == "at":
            from . import proactive as PR
            plan = dv.then if dv.route == "one_tap" and PR.tap_escalation_on() else None
            if plan:   # Sasha 132 · ONE yes covers the plan: asked first, then the page
                lines = [f"I'll send you {rd['venue']}'s booking page on {dv_platform(rd)} — you press their confirm button; I can't press it for you.",
                         plan]
                sha = hashlib.sha256("\n".join(lines).encode()).hexdigest()
                rid = hashlib.sha256(f"{rd['read_id']}|{reservation['when']['at']}".encode()).hexdigest()[:8]
                out.text("Exactly what I'll do:\n" + "\n".join("• " + ln for ln in lines))
                out.ask(f"Send me their page? {SN.confirm_sentence(reservation, rd['venue'])}", [("Yes, send it", f"yes:{rid}:{sha[:16]}"), ("No", f"no:{rid}:{sha[:16]}")])
                st["pending"] = {"kind": "plan_link", "at": ctx["now"].isoformat(), "id": rid, "sha": sha, "plan": plan, "reservation": reservation,
                                 "contact_name": contact["name"], **keep}
                return
            if await _send_link(ctx, rd, reservation, contact["name"], None, keep):
                return
            log.info("[guest_whatsapp] one-tap link refused; trying the next route")
        if route == "call_email" and "phone" in rungs and "email" in rungs and reservation["when"]["mode"] == "at":
            # Sasha 131 · URGENT: the call AND the email, both read back, on ONE yes
            fi = rungs["phone"].get("fact_index")
            from . import guest_receipt as GR, ladder_routes as LR
            mine = await GR.address_of(ctx["account"]) if LR.LADDER_STORE is not None else None
            at = reservation["when"]["at"]
            s1, cj = await api(ctx["account"], "POST", "/api/booking/calls",
                               {"reservation": reservation, "read_id": rd["read_id"], **({"fact_index": fi} if fi is not None else {})})
            s2, ej = await api(ctx["account"], "POST", "/api/booking/emails",
                               {"read_id": rd["read_id"], "date": at[:10], "time": at[11:16], "party": reservation["how_many"]["count"],
                                "name": contact["name"], "email": mine or ""})
            if s1 == 200 and s2 == 200:
                both = hashlib.sha256(f"{cj['read_back']['sha256']}|{ej['read_back']['sha256']}".encode()).hexdigest()
                lines = ["The call:"] + cj["read_back"]["lines"] + ["The email, sent at the same time:"] + ej["read_back"]["lines"]
                await _ask_yes(ctx, "call_email", cj["call_id"], {"lines": lines, "sha256": both},
                               "Call and email them now? " + SN.confirm_sentence(reservation, rd["venue"]), rd["venue"],
                               extra={"summary": summary(reservation), "trip_item_id": cj.get("trip_item_id"), "call_sha": cj["read_back"]["sha256"],
                                      "email_id": ej["email_id"], "email_sha": ej["read_back"]["sha256"], **keep})
                return
            why = refusal_words(cj if s1 != 200 else ej, s1 if s1 != 200 else s2)
            log.info("[guest_whatsapp] call+email refused (%s/%s); trying the next route", s1, s2)
        if route == "call" and "phone" in rungs:
            fi = rungs["phone"].get("fact_index")
            status, j = await api(ctx["account"], "POST", "/api/booking/calls",
                                  {"reservation": reservation, "read_id": rd["read_id"], **({"fact_index": fi} if fi is not None else {})})
            if status == 200:
                await _ask_yes(ctx, "call", j["call_id"], j["read_back"], j.get("sentence") or SN.confirm_sentence(reservation, rd["venue"]), rd["venue"],
                               extra={"summary": summary(reservation), "invite_code": pend.get("invite_code"), "trip_item_id": j.get("trip_item_id"),
                                      "read": rd, "draft": d})
                return
            why = refusal_words(j, status)
            log.info("[guest_whatsapp] call refused (%s); trying the next route", status)
        if route == "email" and "email" in rungs and reservation["when"]["mode"] == "at":
            from . import guest_receipt as GR, ladder_routes as LR
            mine = await GR.address_of(ctx["account"]) if LR.LADDER_STORE is not None else None
            at = reservation["when"]["at"]
            from . import proactive as PR
            plan = dv.then if dv.route == "email" and PR.no_reply_call_on() else None   # Sasha 132 · in the email's own read-back
            status, j = await api(ctx["account"], "POST", "/api/booking/emails",
                                  {"read_id": rd["read_id"], "date": at[:10], "time": at[11:16], "party": reservation["how_many"]["count"],
                                   "name": contact["name"], "email": mine or "", **({"plan_line": plan} if plan else {}),
                                   **({"nights": d["nights"]} if d.get("nights") else {})})   # Sasha 132 · a hotel room
            if status == 200:
                sentence = SN.confirm_sentence(reservation, rd["venue"])
                if d.get("nights"):   # Sasha 135 · a hotel: a REQUEST for a room, said as one — never "book … at 15:00"
                    n = int(d["nights"])
                    sentence = (f"Email {rd['venue']} to ask for a room for {reservation['how_many']['count']}, {SN.day_words(at[:10])} for "
                                f"{n} night{'s' if n != 1 else ''}? It's a request — nothing is booked until they reply.")
                await _ask_yes(ctx, "email", j["email_id"], j["read_back"], sentence, rd["venue"],
                               extra={"summary": summary(reservation), **keep})
                return
            why = refusal_words(j, status)
            log.info("[guest_whatsapp] email refused (%s); trying the next route", status)
    st["pending"] = None
    said = f"I can't book {rd['venue']} from here right now" + (f" — {why}" if why else "")
    out.text(said + ("" if said.endswith(("?", ".")) else ".") + " Nothing was sent.")


_BULLET = re.compile(r"^[·•]\s*")


async def _ask_yes(ctx: dict, rung: str, rid: str, read_back: dict, sentence: str, venue: str, kind: str = "confirm",
                   extra: Optional[dict] = None) -> None:
    out = ctx["out"]
    sha = read_back["sha256"]
    out.text("Exactly what I'll " + ("say" if rung == "call" else "send") + ":\n" +
             "\n".join("• " + _BULLET.sub("", ln) for ln in read_back["lines"]))   # Sasha 117 · one bullet, not "• ·"
    tag = f"{rid[:8]}:{sha[:16]}"
    yes_title = "Yes, book it" if kind == "confirm" else "Yes, cancel"
    out.ask(sentence, [(yes_title, f"yes:{tag}"), ("No", f"no:{tag}")])
    ctx["st"]["pending"] = {"kind": kind, "at": ctx["now"].isoformat(), "rung": rung, "id": rid, "sha": sha, "venue": venue,
                            **(extra or {})}


# ── the yes → placed → progress → the result ────────────────────────────────────────────────────────────────────────

def summary(o: dict) -> str:
    """'Saturday 3 October at 21:00, 2 people' — the booking as the guest asked for it."""
    w, n = o.get("when") or {}, (o.get("how_many") or {}).get("count")
    when = "whenever they have space" if w.get("mode") == "venue_proposes" else \
        f"{SN.day_words(str(w.get('at') or '')[:10])} at {str(w.get('at') or '')[11:16]}"
    return f"{when}, {n} {'person' if n == 1 else 'people'}"


async def _approve(ctx: dict, pend: dict, how: dict) -> None:
    out, account, venue = ctx["out"], ctx["account"], pend["venue"]
    if pend["rung"] == "form":
        status, j = await api(account, "POST", f"/api/booking/forms/{pend['id']}/send", {"read_back_sha256": pend["sha"], "approval": how}, timeout=120)
        if status != 200:
            out.text(f"❌ Not sent to {venue}: {refusal_words(j, status)}.")
            return
        # Sasha 117 · the send is "sent"; what the venue's page SAID is the reading — "confirmed" was never the status
        result = (j.get("reading") or {}).get("result") if j.get("status") == "sent" else None
        ref = f" Their reference: {j['booking_reference']}." if j.get("booking_reference") and result == "confirmed" else ""
        out.text({"confirmed": f"✅ Booked: {venue}, {pend.get('summary', '')}.{ref}",
                  "proposed": f"⚠ Not confirmed yet: {venue}'s page offers something different — read it below.",
                  "declined": f"❌ They said no: {venue}'s page turned it down."}.get(result) or
                 (f"⚠ Not confirmed yet: I sent {venue} their booking form; their page didn't say it's booked." if j.get("status") == "sent"
                  else f"⚠ Not confirmed yet: {j.get('say') or 'their site did not answer clearly'}"))
        if j.get("their_page"):
            out.text(f"Their page said: “{str(j['their_page'])[:500]}”")
        if _receipt_note():
            out.text(_receipt_note().strip())
        if result == "confirmed" and venue == "Sasha Test Venue" and os.getenv("SASHA_TEST_VENUE_DEPOSIT", "") == "1":
            await _test_deposit(ctx)   # Sasha 131 (4) · one touch, on their page — a TEST payment
        return
    if pend["rung"] == "call_email":   # Sasha 131 · URGENT: both on the one yes — the email first (it can't be refused by a ring)
        s2, ej = await api(account, "POST", f"/api/booking/emails/{pend['email_id']}/send", {"read_back_sha256": pend["email_sha"], "approval": how}, timeout=60)
        out.text(f"✉️ Emailed {venue}." if s2 == 200 and ej.get("status") == "sent" else f"❌ The email to {venue} wasn't sent: {ej.get('say') or refusal_words(ej, s2)}.")
        pend = {**pend, "rung": "call", "sha": pend["call_sha"]}
    if pend["rung"] == "email":   # Sasha 130 · the email route: sent is "requested", never "booked"
        status, j = await api(account, "POST", f"/api/booking/emails/{pend['id']}/send", {"read_back_sha256": pend["sha"], "approval": how}, timeout=60)
        if status != 200 or j.get("status") != "sent":
            out.text(f"❌ Not sent to {venue}: {j.get('say') or refusal_words(j, status)}.")
            return
        out.text(f"✉️ Emailed {venue} — {pend.get('summary', '')}. Not booked yet: I'll show you their reply word for word the moment it arrives.")
        return
    status, j = await api(account, "POST", f"/api/booking/calls/{pend['id']}/place", {"read_back_sha256": pend["sha"], "approval": how}, timeout=120)
    if status != 200:
        out.text(f"❌ Not called: {refusal_words(j, status)}. Nothing was dialled.")
        return
    if j.get("status") == "scheduled":   # Sasha 108 · the venue's own name, never the search words
        at = str(j.get("scheduled_for") or "")[11:16]
        out.text(f"{venue} is closed right now, so I'll call them at {at} — your yes covers that call.")
        return
    if pend.get("invite_code") and pend.get("trip_item_id"):   # S-80 · the invitation follows the inviter's booking
        from . import invitations as IV
        await IV.STORE.update(pend["invite_code"], trip_item_id=pend["trip_item_id"])
    out.text(f"📞 Calling {venue} now." if j.get("status") in ("placed", "uncertain") else f"❌ I couldn't call {venue}: {j.get('why') or 'not placed'}.")
    if j.get("status") in ("placed", "uncertain"):
        _spawn(watch_call(ctx["ch"], ctx["frm"], account, pend["id"], venue, "book", pend.get("summary", "")))


def _receipt_note() -> str:
    from .ladder import emails_ready
    return "" if emails_ready() else " Your receipt is in your email."


def result_lines(v: dict, venue: str, purpose: str, what: str = "") -> List[str]:
    """Sasha 108 · a result in plain words: ONE status line, then the venue's own words. Never internal terms."""
    state, outcome = v.get("status"), v.get("outcome")
    if purpose == "cancel":
        head = (f"✅ Cancelled: {venue} confirmed it." if outcome == "yes" else
                f"❌ {venue} didn't cancel it." if outcome == "no" else
                f"⚠ Not cancelled yet: {venue} didn't confirm it.")
    elif state == "answered" and outcome == "yes":
        head = f"✅ Booked: {venue}" + (f", {what}." if what else ".")
    elif state == "answered" and outcome == "no":
        head = f"❌ {venue} said no."
    elif state == "not_reached":
        head = f"⚠ Not confirmed yet: {venue} didn't pick up."
    else:
        head = f"⚠ Not confirmed yet: {venue} didn't clearly confirm it."
    out = [head]
    if v.get("venue_words"):
        out.append(f"Their words: “{v['venue_words']}”")
    return out


async def offer_escalation(ch: dict, b: dict, read_row: dict, prefer: str, question: str, yes_title: str) -> str:
    """Sasha 130/131 · the next rung of the escalation policy, ASKED: one question, inside the 24-hour window only. Its yes
    leads to that route's own read-back and yes; nothing is sent or dialled from the question itself."""
    st = await STORE.get_state(ch["wa_id_sha256"])
    last = st.get("last_inbound_at")
    if not (last and NOW() - last <= SESSION_WINDOW) or not guest_numbers():
        return "not sent: outside the 24-hour window"
    read = read_row.get("read") or {}
    venue = b.get("venue") or read.get("name") or "the venue"
    kinds = {f.get("kind") for f in read.get("facts") or []}
    rd = {"read_id": str(read_row.get("read_id") or b["read_id"]), "country": read.get("country"), "venue": venue,
          "rungs": {**({"phone": {"fact_index": None, "value": None}} if "phone" in kinds else {}),
                    **({"email": {"fact_index": None, "value": None}} if "email" in kinds else {})},
          "open_now": None, "opens_at": None}
    draft = {"what": {"activity": b.get("what") or "a table", "activity_venue_lang": b.get("what") or "a table",
                      "category": b.get("category") or "restaurant"},
             "when": {"mode": "at", "at": f"{b['date']}T{b['time']}"}, "how_many": {"count": b.get("count") or b.get("party"), "unit": "people"}}
    sha = hashlib.sha256(f"{b['id']}|{prefer}".encode()).hexdigest()
    out = Out().ask(question, [(yes_title, f"yes:{b['id'][:8]}:{sha[:16]}"), ("No", f"no:{b['id'][:8]}:{sha[:16]}")])
    st["pending"] = {"kind": "no_reply_call", "at": NOW().isoformat(), "id": b["id"], "sha": sha, "read": rd, "draft": draft, "prefer": prefer}
    await STORE.put_state(ch["wa_id_sha256"], st)
    return ", ".join(await deliver(ch, sorted(guest_numbers())[0], out, last))


async def _tell(ch: dict, text: str) -> str:
    st = await STORE.get_state(ch["wa_id_sha256"])
    last = st.get("last_inbound_at")
    if not (last and NOW() - last <= SESSION_WINDOW) or not guest_numbers():
        return "not told: outside the 24-hour window"
    return ", ".join(await deliver(ch, sorted(guest_numbers())[0], Out().text(text), last))


def _draft_of(b: dict) -> dict:
    return {"schema": "reservation/1", "flow": "book",
            "what": {"activity": b.get("what") or "a table", "activity_venue_lang": b.get("what") or "a table", "category": b.get("category") or "restaurant"},
            "where": {}, "when": {"mode": "at", "at": f"{b['date']}T{b['time']}"},
            "how_many": {"count": b.get("count") or b.get("party") or 2, "unit": "people"}}


async def auto_email_from_link(ch: dict, l: dict, read_row: dict) -> str:
    """Sasha 132 · the one-tap wasn't pressed in time and the guest's yes covered it: the email is prepared and SENT under
    that yes (the server verifies the plan from its own records), then the guest is told. The email carries the rest of
    the plan (the call after 24 h) in its own read-back."""
    from . import escalation as ESC, decide as D, guest_receipt as GR
    account = l["account_id"]
    kinds = {f.get("kind") for f in ((read_row or {}).get("read") or {}).get("facts") or []}
    _s, cj = await api(account, "GET", "/api/booking/contact")
    name = ((cj or {}).get("contact") or {}).get("name") or ""
    mine = await GR.address_of(account)
    rest = ESC.plan_line(f"If they don't reply within {D._h(D.reply_hours())}, I'll call them", None) if "phone" in kinds else None
    s, ej = await api(account, "POST", "/api/booking/emails", {"read_id": l["read_id"], "date": l["local_date"].isoformat(),
                                                                "time": l["local_time"].strftime("%H:%M"), "party": l.get("party_size") or 2,
                                                                "name": name, "email": mine or "", **({"plan_line": rest} if rest else {})})
    if s != 200:
        await _tell(ch, f"You hadn't booked on {l['venue']}'s page, and I couldn't prepare the email to them: {refusal_words(ej, s)}.")
        return f"not prepared: {s}"
    s2, sj = await api(account, "POST", f"/api/booking/emails/{ej['email_id']}/send",
                       {"read_back_sha256": ej["read_back"]["sha256"], "approval": {"how": "escalation_plan", "from": {"kind": "link", "id": l["link_id"]}}})
    if s2 != 200 or sj.get("status") != "sent":
        await _tell(ch, f"You hadn't booked on {l['venue']}'s page; I tried to email them as agreed, but it wasn't sent: {sj.get('say') or refusal_words(sj, s2)}.")
        return "not sent"
    await _tell(ch, f"You hadn't booked on {l['venue']}'s page for {SN.day_words(l['local_date'].isoformat())} at {l['local_time'].strftime('%H:%M')}, "
                    f"so — as you agreed — I've emailed them. Not booked yet: I'll show you their reply word for word."
                    + (" If there's no reply in 24 hours, I'll call them." if rest else ""))
    return "sent"


async def auto_call_from_email(ch: dict, b: dict, email_id: str) -> str:
    """Sasha 132 · no reply within 24 h and the guest's yes covered it: the call is prepared and PLACED under that yes."""
    account = ch["account_id"]
    s, cj = await api(account, "POST", "/api/booking/calls", {"reservation": _draft_of(b), "read_id": str(b["read_id"])})
    if s != 200:
        await _tell(ch, f"No reply from {b.get('venue')} in 24 hours. I was going to call them as agreed, but couldn't prepare it: {refusal_words(cj, s)}.")
        return f"not prepared: {s}"
    s2, pj = await api(account, "POST", f"/api/booking/calls/{cj['call_id']}/place",
                       {"read_back_sha256": cj["read_back"]["sha256"], "approval": {"how": "escalation_plan", "from": {"kind": "email", "id": email_id}}}, timeout=120)
    if s2 != 200 or pj.get("status") not in ("placed", "uncertain", "scheduled"):
        await _tell(ch, f"No reply from {b.get('venue')} in 24 hours. I tried to call them as agreed, but couldn't: {pj.get('why') or refusal_words(pj, s2)}.")
        return "not placed"
    when = f" at {str(pj.get('scheduled_for') or '')[11:16]}, when they open" if pj.get("status") == "scheduled" else " now"
    await _tell(ch, f"No reply from {b.get('venue')} to my email in 24 hours, so — as you agreed — I'm calling them{when}. I'll tell you what they say.")
    if pj.get("status") in ("placed", "uncertain") and guest_numbers():
        _spawn(watch_call(ch, sorted(guest_numbers())[0], account, cj["call_id"], b.get("venue") or "the venue", "book",
                          f"{SN.day_words(b['date'])} at {b['time']}"))
    return pj.get("status")


async def offer_no_reply_call(ch: dict, b: dict, read_row: dict) -> str:
    venue = b.get("venue") or (read_row.get("read") or {}).get("name") or "the venue"
    return await offer_escalation(ch, b, read_row, "call",
                                  f"No reply yet from {venue} to my email about {SN.day_words(b['date'])} at {b['time']}. Shall I call them? "
                                  f"I'll show you exactly what I'll say first.", "Yes, prepare the call")


WATCH_DEPOSIT = (15, 40)   # every 15 s for 10 minutes


async def _test_deposit(ctx: dict) -> None:
    from . import test_deposit as TD
    got = await TD.link()
    if "why" in got:
        ctx["out"].text(f"(Their test deposit page isn't available: {got['why']}.)")
        return
    ctx["out"].text(TD.message(got["url"]))
    _spawn(watch_deposit(ctx["ch"], ctx["frm"], got["id"], time.time()))


async def watch_deposit(ch: dict, frm: str, link_id: str, since: float) -> None:
    """Their page's own record (Stripe, TEST mode) decides — never the guest's word, never assumed."""
    from . import test_deposit as TD
    every, times = WATCH_DEPOSIT
    for _ in range(times):
        await asyncio.sleep(every)
        paid = await TD.paid_since(link_id, since)
        if paid:
            st = await STORE.get_state(ch["wa_id_sha256"])
            await deliver(ch, frm, Out().text(f"✅ Deposit paid on their page — TEST payment, nothing was charged: €{paid['amount']:.2f}. "
                                              f"Stripe's record: {paid['payment']}."), st.get("last_inbound_at"))
            return
    st = await STORE.get_state(ch["wa_id_sha256"])
    await deliver(ch, frm, Out().text("Their page doesn't show the test deposit paid after 10 minutes. The link still works if you "
                                      "want to try again."), st.get("last_inbound_at"))


WATCH_GMAIL = (30, 10)   # every 30 s, ten times: a platform's confirmation email usually lands within a minute or two


async def watch_gmail_confirmation(ch: dict, frm: str, account: str, venue: str, when: str) -> None:
    """Sasha 130 · ONE-TAP, the second half: after the guest pressed the platform's button and said BOOKED, Sasha looks in
    their Gmail for the confirmation. mailbox.sync matches it to the booking (reference, else venue + day) and offers it
    here — "Yes" files it on the booking and its receipt. Nothing found is said, never assumed."""
    from . import mailbox as MB
    link = await MB.STORE.get_link(account) if MB.STORE else None
    if not link or link.get("needs_reconnect_at"):
        st = await STORE.get_state(ch["wa_id_sha256"])
        await deliver(ch, frm, Out().text(f"Your Gmail isn't connected{' (it needs reconnecting)' if link else ''}, so I can't find "
                                          f"{venue}'s confirmation myself. Forward it to me, or connect Gmail in You."), st.get("last_inbound_at"))
        return
    every, times = WATCH_GMAIL
    for _ in range(times):
        await asyncio.sleep(every)
        try:
            found = await MB.sync(account)   # a matched confirmation is offered on WhatsApp by sync itself
        except Exception as e:
            log.warning("[guest_whatsapp] Gmail check failed: %s", type(e).__name__)
            continue
        if any(f.get("trip_item_id") and f.get("offered_action") for f in found):
            return
    st = await STORE.get_state(ch["wa_id_sha256"])
    await deliver(ch, frm, Out().text(f"No confirmation email from {venue} in your Gmail after 5 minutes. Your booking stays as you "
                                      f"told me; I'll keep checking with your usual email checks, or forward it to me."), st.get("last_inbound_at"))


async def watch_call(ch: dict, frm: str, account: str, call_id: str, venue: str, purpose: str, what: str = "",
                     confirming: bool = False) -> None:
    """The result once the call ends — one message per call, never two for one state; an unclear booking follows its
    ONE confirmation call (Sasha 108) through to its own result."""
    every, times = WATCH_CALL
    for _ in range(times):
        await asyncio.sleep(every)
        status, v = await api(account, "GET", f"/api/booking/calls/{call_id}")
        if status != 200 or v.get("status") in ("placed", "placing", "awaiting_approval"):
            continue
        st = await STORE.get_state(ch["wa_id_sha256"])
        out = Out()
        for line in result_lines(v, venue, purpose, what):
            out.text(line)
        settled = v.get("status") == "answered" and v.get("outcome") in ("yes", "no")
        follow = None
        if purpose == "book" and not settled and not confirming:
            follow = v.get("confirmation_call_id")
            if not follow:   # the confirmation is placed as the result is recorded: give it a moment
                for _ in range(6):
                    await asyncio.sleep(5 if every else 0)
                    _s, v2 = await api(account, "GET", f"/api/booking/calls/{call_id}")
                    follow = (v2 or {}).get("confirmation_call_id")
                    if follow:
                        break
        if follow:   # its own result is sent from where it is recorded (push_confirmation_result)
            out.text(f"I'm calling {venue} back once now to confirm it — I'll tell you here.")
        elif purpose == "book" and not settled:
            out.text("I've asked them to confirm in writing where I can; anything they send goes onto your booking and receipt.")
        elif settled and v.get("outcome") == "yes" and _receipt_note():
            out.text(_receipt_note().strip())
        await deliver(ch, frm, out, st.get("last_inbound_at"))
        return
    st = await STORE.get_state(ch["wa_id_sha256"])
    await deliver(ch, frm, Out().text(f"⚠ The call to {venue} hasn't finished after 8 minutes; I'll keep its result, and the receipt "
                                      f"follows by email."), st.get("last_inbound_at"))


async def venue_display(call: dict) -> str:
    """The venue's own name for the guest: the listing re-read now (Sasha 64 — a listing's name is shown, never stored)."""
    from . import ladder_routes as LR
    brief = call.get("brief") or {}
    vk = str(brief.get("venue_key") or "")
    try:
        row = await LR.LADDER_STORE.get_read(str(call["account_id"]), vk[5:]) if vk.startswith("read:") else None
        if row:
            read = await LR.PT.hydrate_read(LR.HTTP, row["read"], NOW())
            name = ((read.get("listing") or {}).get("name") or "").strip()   # never the stored search words
            if name:
                return name
    except Exception as e:
        log.info("[guest_whatsapp] the venue's name could not be re-read: %s", type(e).__name__)
    return "the venue"


async def push_confirmation_result(call: dict, reading, nxt: Optional[str]) -> str:
    """Sasha 108 · a confirmation call's result, sent to the guest's WhatsApp from where it is recorded (the call may run
    hours after anyone is watching): one status line, their words, and what happens next."""
    if STORE is None or not guest_numbers():
        return "not sent: WhatsApp for guests is off"
    ch = await STORE.channel_of_account(str(call["account_id"]))
    if not ch:
        return "not sent: the guest has no WhatsApp linked"
    brief = call.get("brief") or {}
    venue = await venue_display(call)
    n = brief.get("party")
    what = f"{SN.day_words(str(brief.get('date') or ''))} at {brief.get('time')}, {n} {'person' if n == 1 else 'people'}" if brief.get("date") else ""
    out = Out()
    purpose = "cancel" if brief.get("purpose") == "cancel" else "book"
    for line in result_lines({"status": reading.state, "outcome": reading.outcome, "venue_words": reading.venue_words}, venue, purpose, what):
        out.text(line)
    settled = reading.state == "answered" and reading.outcome in ("yes", "no")
    if purpose == "cancel":
        if nxt and nxt.startswith("scheduled for "):   # Sasha 109 · nobody answered: once more, as the yes covered
            out = Out().text(f"I'll call {venue} once more at {nxt[len('scheduled for '):]} to cancel it — your yes covers it.")
        elif not (call.get("approval") or {}).get("scheduled_for"):
            return "not sent: an immediate cancelling call is told by its watcher"
        st = await STORE.get_state(ch["wa_id_sha256"])
        return ", ".join(await deliver(ch, sorted(guest_numbers())[0], out, st.get("last_inbound_at")))
    if nxt and nxt.startswith("scheduled for "):
        out.text(f"I'll call {venue} once more at {nxt[len('scheduled for '):]} — your yes covers it.")
    elif not settled:
        out.text("I've asked them to confirm in writing where I can; anything they send goes onto your booking and receipt.")
    elif reading.outcome == "yes" and _receipt_note():
        out.text(_receipt_note().strip())
    st = await STORE.get_state(ch["wa_id_sha256"])
    return ", ".join(await deliver(ch, sorted(guest_numbers())[0], out, st.get("last_inbound_at")))


async def push_payment_question(call: dict, pr: dict) -> str:
    """S-81 tier 0 · the ONE sentence for the deposit, with Yes/No bound to its read-back hash."""
    if STORE is None or not guest_numbers():
        return "not sent: WhatsApp for guests is off"
    ch = await STORE.channel_of_account(str(call["account_id"]))
    if not ch:
        return "not sent: no WhatsApp linked (the web shows it)"
    st = await STORE.get_state(ch["wa_id_sha256"])
    out = Out().text("\n".join(pr["read_back_lines"][:2]))
    tag = f"{pr['id'][:8]}:{pr['read_back_sha256'][:16]}"
    out.ask(pr["read_back_lines"][-1], [("Yes, ask them", f"yes:{tag}"), ("No", f"no:{tag}")])
    st["pending"] = {"kind": "payment", "at": NOW().isoformat(), "id": pr["id"], "sha": pr["read_back_sha256"], "venue": pr["payee"]}
    await STORE.put_state(ch["wa_id_sha256"], st)
    return ", ".join(await deliver(ch, sorted(guest_numbers())[0], out, st.get("last_inbound_at")))


# ── receipts and cancelling ─────────────────────────────────────────────────────────────────────────────────────────

async def _upcoming(account: str) -> List[dict]:
    status, j = await api(account, "GET", "/api/booking/reservations")
    if status != 200:
        return []
    from zoneinfo import ZoneInfo

    def ahead(r):   # Sasha 117 · today's 13:00 is not upcoming at 22:51 — the time counts, in the booking's own zone
        if not r.get("date"):
            return True
        try:
            local = NOW().astimezone(ZoneInfo(r.get("timezone") or "Europe/Madrid"))
        except Exception:
            local = NOW()
        return r["date"] > local.date().isoformat() or (r["date"] == local.date().isoformat() and (r.get("time") or "23:59") >= local.strftime("%H:%M"))
    rows = [r for r in j.get("reservations") or [] if r.get("status") not in ("cancelled", "declined", "failed") and ahead(r)]
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


async def _cancel_find(ctx: dict, asked: Optional[str]) -> None:
    """Sasha 109 · the booking a cancellation means: the one named, or — no name — the most recent active one; several →
    a numbered list. Then ONE sentence and one yes (_cancel_row)."""
    out, account = ctx["out"], ctx["account"]
    rows = await _upcoming(account)
    day = ctx.get("cancel_day")
    if day:   # Sasha 121 · "tonight's" / "tomorrow's": only that day's bookings
        from zoneinfo import ZoneInfo
        local = ctx["now"].astimezone(ZoneInfo("Europe/Madrid")).date()
        want = (local + timedelta(days=1 if day == "tomorrow" else 0)).isoformat()
        same = [r for r in rows if r.get("date") == want]
        if not same:
            out.text(f"You have no booking with me {'tomorrow' if day == 'tomorrow' else 'today'}.")
            return
        rows = same
    if asked:
        words = [w for w in re.findall(r"[a-z0-9]+", _fold(asked)) if len(w) > 2]
        hits = [r for r in rows
                if words and all(any(x.startswith(w) or w.startswith(x) for x in re.findall(r"[a-z0-9]+", _fold(r["venue"]))) for w in words)]
        if not hits and not rows:
            out.text(f"I can't find an upcoming booking of yours at {asked}.")
            return
        if not hits:   # Sasha 117 · "the Retiro dinner": guests name the area or the meal, not the venue — show their bookings
            out.text(f"I can't find a booking called “{asked}”.")
            hits = rows if len(rows) > 1 else []
            if not hits:
                rows = rows[:1]
                out.text(f"Your one upcoming booking is {rows[0]['venue']}.")
                await _cancel_row(ctx, rows[0])
                return
    else:
        hits = rows
        if not hits:
            out.text("You have no upcoming bookings with me to cancel.")
            return
    if len(hits) > 1:
        hits = hits[:9]
        lines = [f"{i + 1}. {r['venue']} — {SN.day_words(r.get('date')) or 'no day set'}{' at ' + r['time'] if r.get('time') else ''}"
                 + (f" · {r['status_words']}" if r.get("status_words") else "")
                 + (f" · ref {r['booking_reference']}" if r.get("booking_reference") else "")   # Sasha 117 · two alike, told apart
                 for i, r in enumerate(hits)]
        out.text("Which one should I cancel?\n" + "\n".join(lines) + "\nReply with its number.")
        ctx["st"]["pending"] = {"kind": "cancel_pick", "at": ctx["now"].isoformat(), "rows": [{"id": r["id"], "venue": r["venue"]} for r in hits]}
        return
    await _cancel_row(ctx, hits[0])


async def _cancel_row(ctx: dict, r: dict) -> None:
    out, account = ctx["out"], ctx["account"]
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
        if j.get("status") == "scheduled":   # Sasha 109 · closed now: the cancelling call waits for them to open
            out.text(f"{venue} is closed right now, so I'll call them to cancel at {str(j.get('scheduled_for') or '')[11:16]} — "
                     f"I'll tell you here what they say.")
            return
        out.text(f"📞 Calling {venue} now to cancel.")
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
    if j.get("status") == "not_confirmed" and j.get("their_words"):   # Sasha 117 · "their words are below" — and they are
        out.text(f"⚠ Not cancelled yet: {venue}'s page didn't say it's cancelled.")
        out.text(f"Their page said: “{str(j['their_words'])[:500]}”")
        out.text("I'll tell you here if they confirm it in writing.")
    else:
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
