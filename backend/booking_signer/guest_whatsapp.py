"""S-75 · SASHA ON WHATSAPP FOR GUESTS — the sandbox phase (docs/sasha/S-75-whatsapp-interface.md, steps 1–10).

A linked guest books, cancels and gets receipts entirely in WhatsApp, on the SAME booking routes the web chat uses,
called in process (no HTTP to ourselves) as that guest's own account. What is never done:
  · Sasha 237 / 253 · ONE BRAIN FOR EVERYONE: every linked account's message goes to the SAME agent as /s2
    (wa_agent.agent_turn → sasha.turn surface "wa": S2's tools, persona, guards and the one yes rule), drawn for WhatsApp by
    wa_agent.render. Identity, STOP/START, reminders words, products, invitations, LINK codes and the 24-hour rule stay here,
    in front. The OLD WhatsApp flow is retired as an entry point (Sasha 253 · item 5 — see turn()): no WhatsApp message reaches
    _new_request / _answer_pending except through the kept front routes (invitations, the three demos until G11) and the G3
    resolver (Sasha's own open questions). The functions stay: the web voice avatar (voice_turn), the brain's venue tools,
    products, invitations and proactive call them.
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


#: Sasha 167 · no longer said anywhere (the web chat's brain answers instead); kept only as an exported name
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


# Sasha 249 · ONE CAPABILITY LIST (EU 245 §1.5 / T10): HELP / LINKED / ONBOARD on WhatsApp are generated from agapi/s2_home.py
# CAPABILITIES — the same list as /s2's card, its chips and /next. Sasha 253 · item 5: the one brain answers everyone, so these are
# the only WhatsApp words. The three fixed lines above stay only as exported names (HELP is still the web voice avatar's answer to
# "hi" — voice_turn runs _new_request, unchanged).
def help_words(account: Optional[str] = None) -> str:
    from agapi import s2_home as S2H
    return S2H.wa_help()


def linked_words(account: Optional[str] = None) -> str:
    from agapi import s2_home as S2H
    return S2H.wa_linked()


def onboard_words() -> str:
    """Sasha 253 · an unlinked number: ONE short line — link this number once at /you. Never the old flow, never a guest account."""
    from agapi import s2_home as S2H
    return S2H.wa_onboard()


NO_CONTACT = ("I need the name and mobile to book under first. Add them once at {web} (kept with your consent), then ask me "
              "again.")

_STOP = re.compile(r"^\s*(stop|parar|baja|arr[eê]t|unsubscribe|cancelar suscripci[oó]n)\s*[.!]?\s*$", re.I)
_START = re.compile(r"^\s*(start|unstop|alta)\s*[.!]?\s*$", re.I)
_LINK = re.compile(r"^\s*(?:kanoe\s+)?link\s+(\d{6})\s*$", re.I)   # Sasha 269 · AgAPI's text: "Kanoe link 123456"
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


SANDBOX_NUMBER = "+14155238886"


def sender_for(st: Optional[dict] = None) -> str:
    """Sasha 162 · the number a message Sasha STARTS goes from: the one this guest last wrote to; else a permanent sender
    (not the sandbox); else the sandbox — kept as the fallback through Friday (founder)."""
    nums = guest_numbers()
    last = (st or {}).get("last_to")
    if last and last in nums:
        return last
    permanent = sorted(n for n in nums if n != SANDBOX_NUMBER)
    return permanent[0] if permanent else sorted(nums)[0]


def guest_numbers() -> set:
    """The numbers that serve GUESTS (the sandbox's, in phase 1). Empty: the guest pipeline is off everywhere."""
    return {n.strip() for n in os.getenv("SASHA_GUEST_WHATSAPP_TO", "").split(",") if n.strip()}


def title(s: str) -> str:
    s = re.sub(r"\s+", " ", s or "").strip()
    return s if len(s) <= TITLE_MAX else s[:TITLE_MAX - 1].rstrip() + "…"


def _fold(s: str) -> str:
    return "".join(ch for ch in unicodedata.normalize("NFD", (s or "").replace("đ", "d").replace("Đ", "D"))
                   if unicodedata.category(ch) != "Mn").lower()   # Sasha 169 · đ has no decomposition: "Bạch Đằng" → "bach dang"


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
        from .wa_agent import unpack_state   # Sasha 252 · the brain's own state out of the pending column, into st["agent"]
        return unpack_state(dict(self.state.get(key) or {"history": [], "pending": None, "last_inbound_at": None, "link_tries": []}))

    async def put_state(self, key: str, st: dict) -> None:
        # only what guest_wa_state's columns hold: anything else is lost in production, so it is lost here too
        # (Sasha 206 · last_to is a column since 034_guest_wa_last_to_and_sids.sql)
        from .wa_agent import pack_pending   # Sasha 252 · st["agent"] rides in the pending column, as in Postgres
        self.state[key] = copy.deepcopy({**{k: st.get(k) for k in ("history", "last_inbound_at", "link_tries", "last_to")},
                                         "pending": pack_pending(st)})

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
        from .wa_agent import unpack_state   # Sasha 252 · the brain's own state out of the pending column, into st["agent"]
        return unpack_state({"history": json.loads(d["history"]) if isinstance(d["history"], str) else d["history"],
                             "pending": json.loads(d["pending"]) if isinstance(d["pending"], str) else d["pending"],
                             "last_inbound_at": d["last_inbound_at"], "last_to": d.get("last_to"),   # Sasha 206/207 · 034
                             "link_tries": json.loads(d["link_tries"]) if isinstance(d["link_tries"], str) else d["link_tries"]})

    async def put_state(self, key, st):
        # Sasha 207 · last_to (034, applied 8 Oct 2026) — the number they last wrote to; a save without it never erases it
        await self._run(lambda c: c.execute(
            "insert into guest_wa_state (wa_id_sha256, history, pending, last_inbound_at, link_tries, last_to, updated_at) "
            "values ($1, $2, $3, $4, $5, $6, now()) on conflict (wa_id_sha256) do update set history = excluded.history, "
            "pending = excluded.pending, last_inbound_at = excluded.last_inbound_at, link_tries = excluded.link_tries, "
            "last_to = coalesce(excluded.last_to, guest_wa_state.last_to), updated_at = now()",
            # the pool's jsonb codec encodes: pass the values themselves (Sasha 104 · a json.dumps here stored a JSON string)
            # Sasha 252 · the pending column: Sasha's own question + the brain's state under "_agent" (wa_agent.pack_pending)
            key, st.get("history") or [], _pack(st), st.get("last_inbound_at"), st.get("link_tries") or [], st.get("last_to")))

    async def delete_account(self, account):
        async def go(c):
            async with c.transaction():
                a = uuid.UUID(account)
                st = await c.execute("delete from guest_wa_state where wa_id_sha256 in (select wa_id_sha256 from guest_channels where account_id = $1)", a)
                ch = await c.execute("delete from guest_channels where account_id = $1", a)
                co = await c.execute("delete from guest_link_codes where account_id = $1", a)
                return {"guest_channels": int(ch.split()[-1]), "guest_wa_state": int(st.split()[-1]), "guest_link_codes": int(co.split()[-1])}
        return await self._run(go)


def _pack(st: dict):
    from .wa_agent import pack_pending
    return pack_pending(st)


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

    async def list_picker(self, body: str, button: str, rows: List[Tuple[str, str, str]]) -> Optional[str]:
        """Sasha 237 · a twilio/list-picker content made for THIS list (≤ 10 rows: title ≤ 24, description ≤ 72), or None."""
        auth = self._auth()
        if not auth or not rows:
            return None
        spec = {"friendly_name": f"sasha_wa_list_{uuid.uuid4().hex[:12]}", "language": "en",
                "types": {"twilio/list-picker": {"body": body[:1024], "button": button[:20],
                                                 "items": [{"item": t[:24], "id": i[:200], "description": (d or "")[:72]} for t, d, i in rows[:10]]},
                          "twilio/text": {"body": body[:1024]}}}
        try:
            import httpx
            async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
                r = await client.post("https://content.twilio.com/v1/Content", json=spec,
                                      headers={"authorization": f"Basic {auth[1]}", "user-agent": "sasha-booking/1"})
            if r.status_code in (200, 201) and (r.json() or {}).get("sid"):
                return r.json()["sid"]
            log.error("[guest_whatsapp] list-picker content not created: HTTP %s %s", r.status_code, r.text[:200])
        except Exception as e:
            log.error("[guest_whatsapp] list-picker content failed: %s: %s", type(e).__name__, e)
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

    def pick(self, s: str, button: str, rows: List[Tuple[str, str, str]]) -> "Out":
        """Sasha 237 · a list picker: `s` (the options, numbered, as text too), its button, rows of (title, description, id)."""
        self.items.append(("list", s, button, rows))
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
        elif it[0] == "list":   # Sasha 237 · the options as a list picker; no picker → the numbered text (answered by typing)
            mk = getattr(SENDER, "list_picker", None)
            sid = await mk(it[1], it[2], it[3]) if mk and it[3] else None
            results.append(await SENDER.send(frm, ch["number_e164"], content_sid=sid) if sid
                           else await SENDER.send(frm, ch["number_e164"], body=it[1]))
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
            if request.state.account:   # Sasha 254 · the record warmed for the booking routes' sync checks
                from agapi import person_access as PA
                await PA.warm(request.state.account)

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
# Sasha 206 (EU 186 R3) · the per-number lock is IN-PROCESS, and that is safe because WhatsApp is served by ONE process: uvicorn
# with no --workers (railway.json startCommand) on ONE replica (railway.json numReplicas: 1; the live log shows a single
# "Started server process [1]"). check_single_worker() logs an error at startup if that ever changes — then this must become a
# Postgres advisory lock per account (pg_advisory_xact_lock), as sasha-rebuild-plan.md §2.2 sets out.
_TURN_LOCKS: Dict[str, asyncio.Lock] = {}


def check_single_worker() -> bool:
    """True when this process is the only one serving WhatsApp, as the in-process lock needs; logs an error otherwise."""
    many = [f"{k}={os.getenv(k)}" for k in ("WEB_CONCURRENCY", "UVICORN_WORKERS", "GUNICORN_WORKERS") if (os.getenv(k) or "1").strip() not in ("", "1")]
    if many:
        log.error("[guest_whatsapp] MORE THAN ONE WORKER (%s): the per-number turn lock is in-process — two turns for one guest could "
                  "run at once. Make it a Postgres advisory lock before scaling (EU 186 R3).", ", ".join(many))
        return False
    log.info("[guest_whatsapp] one worker: the per-number turn lock holds (EU 186 R3)")
    return True


def _spawn(coro) -> None:
    t = asyncio.ensure_future(coro)
    _TASKS.add(t)
    t.add_done_callback(_TASKS.discard)


def _twiml_message(text: str) -> str:
    return f"<Message>{escape(text)}</Message>"


_SEEN_SIDS: Dict[str, float] = {}   # the memory store's (tests); the Postgres store uses guest_inbound_sids (034)


async def linked(number: str) -> bool:
    """Sasha 285 · a guest talking to Sasha on WhatsApp (their number linked to an account) — their messages are hers, never AgAPI's."""
    if STORE is None or not number:
        return False
    try:
        return bool(await STORE.channel_for(wa_key(number)))
    except Exception as e:
        log.warning("[guest_whatsapp] linked() unreadable: %s", type(e).__name__)
        return True   # unreadable: treated as a guest — the guest pipeline decides, nothing is handed to anyone


async def first_time(sid: str) -> bool:
    """True the first time a MessageSid is seen (or when there is none to go by); False for a repeat — in guest_inbound_sids
    on the Postgres store (Sasha 207 · 034 applied: across restarts), in this process on the memory store."""
    if not sid:
        return True
    run = getattr(STORE, "_run", None)
    if run is not None:
        try:
            new = await run(lambda c: c.fetchval("insert into guest_inbound_sids (message_sid) values ($1) on conflict do nothing "
                                                 "returning message_sid", sid))
            return new is not None
        except Exception as e:
            log.error("[guest_whatsapp] MessageSid not checked: %s: %s", type(e).__name__, e)
            return True   # never drop a guest's message over the check itself
    import time as _t
    now = _t.time()
    for k in [k for k, at in _SEEN_SIDS.items() if now - at > 86400]:
        del _SEEN_SIDS[k]
    if sid in _SEEN_SIDS:
        return False
    _SEEN_SIDS[sid] = now
    return True


async def seen(sid: str) -> bool:
    """Sasha 294 · was this key marked before? (read only — first_time() marks). The same store as first_time."""
    if not sid:
        return False
    run = getattr(STORE, "_run", None)
    if run is not None:
        try:
            return bool(await run(lambda c: c.fetchval("select 1 from guest_inbound_sids where message_sid = $1", sid)))
        except Exception as e:
            log.error("[guest_whatsapp] MessageSid not read: %s: %s", type(e).__name__, e)
            return False
    return sid in _SEEN_SIDS


async def dispatch(p: Dict[str, str], venue_call_for) -> Optional[str]:
    """None: not ours — the venue path runs exactly as before. A string: the TwiML inside <Response> (often empty: the
    guest's turn runs in the background and answers through the API, a message every three seconds)."""
    to = (p.get("To") or "").split(":", 1)[-1].strip()
    sender = (p.get("From") or "").split(":", 1)[-1].strip()
    if not (p.get("From") or "").lower().startswith("whatsapp:") or to not in guest_numbers() or not sender or STORE is None:
        return None
    key = wa_key(sender)
    ch = await STORE.channel_for(key)
    if not ch and await venue_call_for(sender):
        return None                        # a venue that is not a linked guest: the venue path (de-duplicated there), never a reply
    if not await first_time(p.get("MessageSid") or ""):   # Sasha 206 (EU 186 R2) · a guest's Twilio retry never runs a turn twice
        log.info("[guest_whatsapp] a repeated MessageSid — already handled, nothing run")
        return ""
    if ch:
        m = _LINK.match(p.get("Body") or "")
        if m:   # Sasha 309 · a number linked BEFORE CR 100 confirms itself the CR 100 way: its own code, sent from it — only that account's
            code = await STORE.take_code(m[1], NOW())
            if code is not None and code["account_id"] == ch["account_id"]:
                from agapi import venue_submit as VS
                ok = await VS.confirm_whatsapp(code["account_id"], sender, p.get("MessageSid") or "", p.get("Body") or "")
                verified = ok.get("ok") and ok.get("state") == "verified"
                log.info("[guest_whatsapp] a linked number's confirmation: %s", "verified" if verified else (ok.get("error") or {}).get("code"))
                from app.agent import voice as V
                return _twiml_message(V.NUMBER_CONFIRMED if verified else V.NUMBER_NOT_CONFIRMED)
        _spawn(_turn(ch, to, p))
        return ""
    now = NOW()
    st = await STORE.get_state(key)
    m = _LINK.match(p.get("Body") or "")
    if m:
        tries = [t for t in st.get("link_tries") or [] if _dt(t) > now - timedelta(hours=1)]
        if len(tries) >= LINK_TRIES_PER_HOUR:   # Sasha 269 · an unverified number: nothing is sent to it (CR 100)
            await STORE.put_state(key, {**st, "link_tries": tries})
            log.info("[guest_whatsapp] too many link tries — nothing sent to that number")
            return ""
        code = await STORE.take_code(m[1], now)
        if code is None:   # Sasha 269 · an UNVERIFIED number: nothing is sent to it (CR 100) — the page says what to do
            await STORE.put_state(key, {**st, "link_tries": tries + [now.isoformat()]})
            log.info("[guest_whatsapp] a link code that isn't waiting — nothing sent to that number")
            return ""
        # Sasha 269 · CR 100 §F: AgAPI says whether the code came FROM the number being linked (Sasha-signed) — verified only then
        from agapi import venue_submit as VS
        ok = await VS.confirm_whatsapp(code["account_id"], sender, p.get("MessageSid") or "", p.get("Body") or "")
        if not ok.get("ok") or ok.get("state") != "verified":
            await STORE.put_state(key, {**st, "link_tries": tries + [now.isoformat()]})
            log.info("[guest_whatsapp] link not verified by AgAPI (%s) — nothing linked, nothing sent", (ok.get("error") or {}).get("code"))
            return ""
        await STORE.link({"account_id": code["account_id"], "wa_id_sha256": key, "number_e164": sender, "linked_at": now,
                          "consent_at": code["consent_at"], "consent_wording_version": code["consent_wording_version"],
                          "consent_text_sha256": code["consent_text_sha256"]})
        await STORE.put_state(key, {"history": [], "pending": None, "last_inbound_at": now, "link_tries": []})
        log.info("[guest_whatsapp] a WhatsApp number was linked to an account")
        return _twiml_message(linked_words(code["account_id"]))   # Sasha 249 · the one brain's words from the one capability list
    from agapi import s2_whatsapp as S2WA   # CR 62 / Sasha 217 · a reply from someone Sasha wrote to FOR a person: kept, never answered by the model
    kept = await S2WA.on_contact_message(sender, p.get("Body") or "")
    if kept is not None:
        return _twiml_message(kept) if kept else ""
    from . import invitations as IV   # S-80 · Jon opting in to ONE invitation, or stopping it
    joined = await IV.on_invite_message(sender, p.get("Body") or "")
    if joined:
        return _twiml_message(joined)
    stopped = await IV.on_invitee_stop(sender, p.get("Body") or "")
    if stopped:
        return _twiml_message(stopped)
    # Sasha 253 · item 5 — RETIRED: Sasha 153's automatic guest account for a new number (GA.create_guest("whatsapp") + STORE.link
    # + a turn, behind SASHA_AUTO_GUESTS). Tyler (mailbox 807): a new user links their number once on /you; an unlinked number gets
    # the ONE line below — never the old flow, never an account made for it.
    # an unknown sender: one short line, at most every ten minutes; only the hash and the time are kept
    tries = [t for t in st.get("link_tries") or [] if _dt(t) > now - timedelta(hours=1)]
    onboarded = [t for t in tries if t.startswith("onboard:")]
    if onboarded and _dt(onboarded[-1]) > now - timedelta(minutes=10):
        return ""
    await STORE.put_state(key, {**st, "link_tries": tries + [f"onboard:{now.isoformat()}"]})
    return _twiml_message(onboard_words().format(web=web_url()))   # Sasha 249


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


async def voice_text(p: Dict[str, str]) -> Optional[str]:
    """Sasha 165 (5) · a WhatsApp VOICE NOTE → its words (Deepgram, any language), handled like typed text. The audio is
    fetched once from Twilio with our own credentials and not kept. None when it isn't a voice note or can't be read."""
    try:
        n = int(p.get("NumMedia") or 0)
    except ValueError:
        n = 0
    if n < 1 or not str(p.get("MediaContentType0") or "").startswith("audio/") or not p.get("MediaUrl0"):
        return None
    from .http_pool import request
    sid, token = os.getenv("TWILIO_ACCOUNT_SID", "").strip(), os.getenv("TWILIO_AUTH_TOKEN", "").strip()
    key = os.getenv("DEEPGRAM_API_KEY", "").strip()
    if not (sid and token and key):
        return None
    try:
        auth = {"authorization": "Basic " + base64.b64encode(f"{sid}:{token}".encode()).decode()}
        r = await request("GET", p["MediaUrl0"], timeout=20.0, follow_redirects=True, headers=auth)
        # Sasha 173 · live on the +44 business sender (same account): HTTP 404 at once — its media isn't stored yet when the
        # webhook arrives (the sandbox's is). A few short retries before giving up.
        for wait in (1.0, 1.5, 2.5, 4.0):
            if r.status_code != 404:
                break
            await asyncio.sleep(wait)
            r = await request("GET", p["MediaUrl0"], timeout=20.0, follow_redirects=True, headers=auth)
        if r.status_code != 200 or not r.content:
            # Sasha 173 · live: HTTP 404 with our credentials — the note came in on a number of ANOTHER Twilio account (its media
            # URL names that account). Twilio's media is readable without credentials unless media auth is enforced: try that.
            acct = (re.search(r"/Accounts/(AC[0-9a-f]{6})", str(p["MediaUrl0"])) or [None, "?"])[1]
            log.warning("[guest_whatsapp] voice note not fetched with our credentials: HTTP %s (media of account %s…, to %s)",
                        r.status_code, acct, str(p.get("To") or "")[-6:])
            r = await request("GET", p["MediaUrl0"], timeout=20.0, follow_redirects=True)
            if r.status_code != 200 or not r.content:
                log.warning("[guest_whatsapp] voice note not fetched without credentials either: HTTP %s", r.status_code)
                return None
        base = os.getenv("DEEPGRAM_STT_BASE", "").strip().rstrip("/") or "https://api.deepgram.com"
        ctype = str(p["MediaContentType0"]).split(";")[0]
        # Sasha 173 · live, a voice note came back with no words and nothing was logged: the reason is logged now, and an empty
        # or failed transcript is tried once more with the plain English model before Sasha says she couldn't make it out
        for params in ({"model": "nova-3", "language": "multi", "smart_format": "true", "punctuate": "true"},
                       {"model": "nova-2", "language": "en", "smart_format": "true", "punctuate": "true"}):
            d = await request("POST", f"{base}/v1/listen", timeout=30.0, content=r.content, params=params,
                              headers={"Authorization": f"Token {key}", "Content-Type": ctype})
            if d.status_code != 200:
                log.warning("[guest_whatsapp] voice note: Deepgram %s HTTP %s: %s", params["model"], d.status_code, d.text[:200])
                continue
            alts = ((d.json().get("results") or {}).get("channels") or [{}])[0].get("alternatives") or [{}]
            words = " ".join(str(alts[0].get("transcript") or "").split())
            if words:
                return words
            log.warning("[guest_whatsapp] voice note: Deepgram %s heard no words (%s bytes, %s)", params["model"], len(r.content), ctype)
        return None
    except Exception as e:
        log.warning("[guest_whatsapp] voice note not transcribed: %s: %s", type(e).__name__, e)
        return None


async def turn(ch: dict, frm: str, p: Dict[str, str]) -> Out:
    key, account = ch["wa_id_sha256"], ch["account_id"]
    from agapi import person_access as PA
    await PA.warm(account)   # Sasha 254 · the one record, fresh for this turn's sync checks (rehearsal, calls, real venues …)
    body = (p.get("Body") or "").strip()
    heard = None
    st = await STORE.get_state(key)
    _pend = st.get("pending") or {}
    in_ad = _pend.get("kind") == "product" and _pend.get("product") == "diligence"   # CR 136 · AD's space: the AUDIO is the evidence
    if not body and not (p.get("ButtonPayload") or "").strip() and not in_ad:
        heard = await voice_text(p)   # Sasha 165 (5) · a voice note: its words, as if typed
        if heard:
            body = heard
            # Sasha 173 · the WORDS go on, never the audio: a voice note's file was handed to the products as if it were a photo,
            # and EspañaMe's DNI reader took "a massage at a spa in Hanoi …" (live)
            p = {**{k: v for k, v in p.items() if not k.startswith("Media")}, "Body": heard, "NumMedia": "0"}
    payload = (p.get("ButtonPayload") or "").strip()
    now = NOW()
    loaded = copy.deepcopy(st.get("pending"))   # Sasha 252 · the open question as this turn found it
    st["last_inbound_at"] = now
    st["last_to"] = frm   # Sasha 162 · the number they wrote to: what Sasha starts goes from it
    out = Out()
    if heard:   # what she heard, so a mis-hearing is seen before anything happens
        out.text(f"🎙 I heard: “{heard}”")
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
    # Sasha 249 / 253 · ONE BRAIN FOR EVERYONE: everything after STOP / opt-out and the reminders consent words goes to sasha.turn —
    # empty messages, documents, every button. Only the FRONT items below stay in front of it (see the routing at the end).
    from . import wa_agent as WA
    # CR 1 products (backend/products/whatsapp.py): CampusMe / relocation by MODE on this one sandbox number. Not in a
    # mode and no "campus…"/"relocation…" keyword → returns False at once and everything below runs as before.
    from products import whatsapp as PW
    from . import me3   # Sasha 155 · "tell me about RelocateMe" → two sentences, then the product's own keyword opens its mode
    m3 = me3.asked(body) if not payload else None
    if m3:
        out.text(me3.INTRO[m3])
        p = {**p, "Body": me3.KEYWORD[m3]}
    elif not payload and me3.back(body):   # Sasha 178 · "back to the campus tour": the product's own word resumes it, no intro
        p = {**p, "Body": me3.KEYWORD[me3.back(body)]}

    async def _early(text: str) -> None:   # "Reading Yale's calendar…" goes out before a slow read, not after it
        await deliver(ch, frm, Out().text(text), now)
    # Sasha 179 · AUTOMATIC SWITCHING (switching.py): the mode this turn starts in; a product idle 30 min steps aside (kept)
    from . import switching as SW
    lead = 1 if heard else 0
    sw = SW.on(account)
    pend0 = {}   # Sasha 194 · no idle exit from a space: only its word leaves it
    if pend0.get("kind") == "product":
        try:
            if now - datetime.fromisoformat(pend0.get("touched")) > SW.PRODUCT_IDLE:
                await PW._set_aside(st, ch)
        except (TypeError, ValueError):
            pass
    if pend0.get("kind") == "amb" and not payload.startswith("amb:"):
        st["pending"] = None
    mode0 = SW.before(st, now) if sw else None
    skip_products = False
    bk = SW.back_to(payload) if sw else None
    if bk and bk[0] == "p":   # "Back to RelocateMe": its own word resumes it, where it was
        p = {**p, "Body": PW.START_WORD.get(bk[1], bk[1]), "ButtonPayload": ""}
        payload = ""
    elif bk:
        if (st.get("pending") or {}).get("kind") == "product":
            await PW._set_aside(st, ch)
        out.text(f"↩ Back to {SW._short(bk[1])} — what next?")
        SW.label_first(out.items, {"k": "j", "label": bk[1]})
        st["history"] = ((st.get("history") or []) + [{"role": "user", "content": body or "back"},
                                                     {"role": "assistant", "content": out.said()}])[-HISTORY_KEEP:]
        await STORE.put_state(key, st)
        await deliver(ch, frm, out, now)
        return out
    if sw and payload.startswith("amb:") and (st.get("pending") or {}).get("kind") == "amb":
        ap, parts = st["pending"], payload.split(":", 3)
        st["pending"] = None
        if len(parts) == 4 and parts[1] == ap.get("nonce"):
            if parts[2] == "s":
                said = await SW.flights_for(account, parts[3])
                if said:
                    body, payload, skip_products = said, "", True
                    p = {**p, "Body": said, "ButtonPayload": ""}
            else:
                body, payload = ap.get("body") or body, ""
                p = {**p, "Body": body, "ButtonPayload": ""}
    elif sw and not payload and body:
        pq = (st.get("pending") or {})
        amb = await SW.ambiguous(account, body, [w for w, _ in await PW._waiting(ch, now)],
                                 pq.get("product") if pq.get("kind") == "product" else None)
        if amb:
            if pq.get("kind") == "product":
                await PW._set_aside(st, ch)
            out.ask(amb[0], amb[1])
            st["pending"] = {"kind": "amb", "nonce": amb[1][0][1].split(":")[1], "body": body, "at": now.isoformat()}
            SW.label_first(out.items, mode0)
            await STORE.put_state(key, st)
            await deliver(ch, frm, out, now)
            return out
    from products import space as _SPC
    _space_before = _SPC.from_pending(st.get("pending"))
    _in_product = await PW.product_turn(ch, frm, p, st, out, now, early=_early) if not skip_products else False
    try:   # Sasha 249 · ONE SPACE: the space this line's products ended the turn in, kept per account (products/space.py) — the
        # keywords themselves ("campus", "relocate", "españa", "sasha") work exactly as before. Sasha 256 · written only when THIS
        # turn moved it (a product entered or left by their word): a message with no product never resets the space
        if _SPC.from_pending(st.get("pending")) != _space_before:
            await _SPC.set_space(account, _SPC.from_pending(st.get("pending")), "whatsapp")
    except Exception as e:
        log.warning("[guest_whatsapp] space not kept: %s", type(e).__name__)
    if _in_product:
        _pp = st.get("pending") or {}
        if sw:   # Sasha 194 · the space, always said (the founder's account; guests next, with their tests)
            SW.label_space(out.items, _pp.get("product") if _pp.get("kind") == "product" else None)
        await STORE.put_state(key, st)   # never into Sasha's history: a product's answers (passport facts) aren't hers
        await deliver(ch, frm, out, now)
        return out
    # CR 13 products: a product may hand Sasha a sentence ("flights from London to Madrid on 2027-03-01 for 1") — answered exactly
    # as if typed; every booking still needs its own read-back and yes. Never a button's answer: a payload is never rewritten.
    handed = (p.get("Body") or "").strip()
    if handed and handed != body and not payload:
        body = handed
    # Sasha 238 · a PHOTO on the one brain → the same handlers as /s2 (products first, above)
    if WA.is_photo(p) and not payload:
        await WA.photo_intake(ch, p, st, out, now)
        await _save_keeping_their_question(key, st, loaded)   # Sasha 252 · Sasha's open question stays
        await deliver(ch, frm, out, now)
        return out
    if not body and not payload:   # Sasha 249 · empty, or a file that isn't a photo: the brain answers it, never HELP
        # Sasha 253 · RETIRED: the old flow's fixed answers to an empty message (HELP, "Got the picture, but…", "couldn't make out")
        has_media = int(p.get("NumMedia") or 0) > 0
        audio = str(p.get("MediaContentType0") or "").startswith("audio")
        body = ("[they sent a voice note that couldn't be made out]" if audio else
                f"[they sent a file ({p.get('MediaContentType0') or 'unknown type'}) with no words]" if has_media else "[an empty message]")
    if G.looks_like_secret(body):
        # S-78 · never stored (not in the history either), never passed on
        out.text(G.CARD_REPLY if G.looks_like_secret(body) == "card" else G.SECRET_REPLY)
        await STORE.put_state(key, st)
        await deliver(ch, frm, out, now)
        return out
    # Sasha 253 · item 5 — THE ROUTING (Tyler, mailbox 807/809: ONE BRAIN FOR EVERYONE). After the FRONT items above (opt-out /
    # START, reminders words, STOP, me3 intros, switching / amb:, products and the space, the handed sentence, the secret guard),
    # a message reaches the OLD handlers through exactly three kept routes, and nothing else does:
    #   1. Sasha 252 · G3 — Sasha's OWN open question (st["pending"]: a no-reply / page offer, a Gmail find, the deposit, their page
    #      sent, an invitation's question, and the questions they lead to) answered — tap or typed — by the code that asked it
    #      (_answer_pending). The ONE owner of those questions. Not its answer after all → the brain.
    #   2. An invitation request ("book dinner with Jon this week", S-80) → _invite, FRONT by design (no agent tool for it).
    # (Sasha 254 · the three demos — restaurant + spa combo, Kanoe Demo Spa, Kanoe Demo Market reorder — RETIRED, Tyler row 817.)
    # RETIRED as WhatsApp entry points (the functions stay — voice_turn, the brain's venue tools, products, invitations and
    # proactive call them): the non-brain branch `_answer_pending` → `_new_request` (the scope gate: HELP, receipts, cancel_find,
    # forwarded confirmation, itinerary_q, flights, hotels, captcha test, start-another, placeless search, booking_handoff → old
    # cards (_find), chat_request, ASK_ONE, WB.web_turn), the old card flow and the old question flow for a new message, the
    # trailing _reminders_offer / space label of that branch (the brain has its own: _brain_tail), and Sasha 249's per-account
    # switch (SASHA_WA_BRAIN).
    sashas = answers_sashas_question(st, body, payload, now)
    invite = not payload and not sashas and _invite_words(body, now)
    if not (sashas or invite):
        if body and not payload:   # Sasha 253 · G4 — a space set on the laptop, continued on the phone (before the brain)
            handed = await _space_resume(ch, body, out, now)
            if handed == "":
                await _brain_tail(ch, out)
                await _save_keeping_their_question(key, st, loaded)
                await deliver(ch, frm, out, now)
                return out
            if handed:
                body = handed   # the product hands Sasha ITS sentence: answered as typed, under the product's words
        await _brain_turn(ch, key, frm, body, payload, p, st, out, now, heard, loaded)
        return out
    ctx = {"account": account, "ch": ch, "frm": frm, "st": st, "now": now, "out": out, "button_text": (p.get("ButtonText") or "").strip(),
           "wa_number": str(p.get("From") or "").replace("whatsapp:", "") or None}   # Sasha 167 · the guest's own number, to book under
    handled = await _answer_pending(ctx, body, payload)   # as the old flow did: the open question first
    if not handled and invite:   # S-80 · the invitation request → its own handler (FRONT by design)
        from . import invitations as IV
        await _invite(ctx, IV.invite_request(body, now))
        handled = True
    if not handled:
        # Sasha 252 · it looked like the answer but the question's own rules let it go (expired cards, a trip question): the
        # message is the brain's, as any new one is
        await _brain_turn(ch, key, frm, body, payload, p, st, out, now, heard, loaded)
        return out
    await _brain_tail(ch, out)
    st["history"] = (st.get("history") or []) + [{"role": "user", "content": body}] + \
                    ([{"role": "assistant", "content": out.said()}] if out.items else [])
    st["history"] = st["history"][-HISTORY_KEEP:]
    await STORE.put_state(key, st)
    await deliver(ch, frm, out, now)
    return out




async def _brain_turn(ch: dict, key: str, frm: str, body: str, payload: str, p: Dict[str, str], st: dict, out: "Out", now,
                      heard, loaded) -> None:
    """The one brain answers this message. Sasha 252 · it never writes st["pending"]: Sasha's open question stays open."""
    import asyncio
    from . import wa_agent as WA
    from app.agent import voice as V
    steps = V.Steps()   # Sasha 264 · item 1: the step her turn is on (wa_agent.agent_turn reports its tools into it)
    tok = V.STEPS.set(steps)
    try:
        task = asyncio.ensure_future(WA.agent_turn(ch, body, payload, st, out, now, button_text=(p.get("ButtonText") or "").strip(),
                                                   voice_in=bool(heard)))   # Sasha 238 · a voice note in → a voice note back
    finally:
        V.STEPS.reset(tok)
    # Sasha 257 · THE HOLDING LINE (row 863): her answer not ready within voice.HOLD_AFTER_S → ONE short line goes first (never a
    # claim, never for a fast reply); the answer follows when it's ready. Awaited — never fire-and-forget. Sasha 264 · then, while
    # it still works, a line every voice.PROGRESS_S from the step actually running — never silence longer than that.
    # Sasha 265 · item 5 (row 935): a request for work hears voice.first_line AT ONCE (the same words as /s2 and /next), then a
    # progress line every voice.PROGRESS_S; anything else keeps the holding line after voice.HOLD_AFTER_S, only if it's slow
    # Sasha 279 · A: said ONCE — a second line only on a long wait (voice.progress_due), never a third; then quiet until her answer
    at_once = V.first_line(body) if body else None
    done, _ = await asyncio.wait({task}, timeout=0 if at_once else V.HOLD_AFTER_S)
    said = 0
    while not done and body and V.progress_due(said, V.LONG_WAIT_S):
        hold = Out()
        hold.text((at_once or V.holding_line(ch.get("account_id") or "")) if not said else V.progress_line(steps.now, ch.get("account_id") or ""))
        said += 1
        try:
            await deliver(ch, frm, hold, now)
        except Exception as e:
            log.warning("[guest_whatsapp] holding line not sent: %s", type(e).__name__)
        if V.progress_due(said, V.LONG_WAIT_S):
            done, _ = await asyncio.wait({task}, timeout=V.LONG_WAIT_S)
    await task
    await _brain_tail(ch, out)
    await _save_keeping_their_question(key, st, loaded)
    await deliver(ch, frm, out, now)


async def _brain_tail(ch: dict, out: "Out") -> None:
    """Sasha 253 · G16 — the reminders offer (S-83 §3a: a v2-consent guest asked ONCE, in reply to their next message) on the one
    brain's replies too — the same _reminders_offer the old flow appends."""
    offer = await _reminders_offer(ch)
    if offer:
        out.text(offer)


async def _space_resume(ch: dict, body: str, out: "Out", now) -> Optional[str]:
    """Sasha 253 · G4 — CROSS-DEVICE RESUME on the one brain: the account is in a product's space set on the web (its webstate —
    products.web.current_space, as the old conductor's strict spaces read it) and WhatsApp's own product turn declined (it keeps
    its own state): "what's next for my application?" is that product's, answered by the SAME products.web.web_turn the web chat
    and the old flow (WB.web_turn → conductor) use. → None: not the product's (the brain answers); "": answered; a sentence:
    the product's hand-off to Sasha (its words are already in `out`). "reset the demo" never goes to a product."""
    from products import web as PWEB
    from . import wa_brain as WB
    account = ch["account_id"]
    if WB.RESET.match(body or ""):
        return None
    try:
        if not await PWEB.current_space(account):
            return None
        r = await PWEB.web_turn(account, body, now=now, signed_in=True)
    except Exception as e:   # a product's failure never stops the turn — the brain answers instead, and it is logged
        log.error("[guest_whatsapp] the space was not resumed: %s: %s", type(e).__name__, e)
        return None
    if r is None:
        return None
    for c in WB.chunks([WB.wa_markdown(r.get("response") or "")]):
        if c:
            out.text(c)
    return r.get("handoff") or ""


async def _save_keeping_their_question(key: str, st: dict, loaded) -> None:
    """Sasha 252 · a question written to the store WHILE this turn ran (their page sent mid-turn: tap_platform's `link`, VN 647)
    is newer than what this turn holds: kept, never saved over by the turn's own save (row 98)."""
    try:
        now_stored = (await STORE.get_state(key)).get("pending")
        if now_stored != loaded:
            st["pending"] = now_stored
    except Exception as e:
        log.warning("[guest_whatsapp] open question not re-read: %s", type(e).__name__)
    await STORE.put_state(key, st)


# Sasha 252 · G3 — Sasha's OWN questions on the one brain: the ones she pushes (no-reply / page-not-pressed offers, a Gmail find,
# the deposit, their page sent, an invitation's area / days / cards) and the questions they lead to (the route's choice — the
# ladder —, the call's or the page's read-back).
SASHAS_OWN = ("no_reply_call", "mailbox", "payment", "link", "invite_where", "invite_window", "cards", "ladder", "confirm", "plan_link")
_YES_NO_KINDS = ("no_reply_call", "mailbox", "payment", "ladder", "confirm", "plan_link")
_A_QUESTION = re.compile(r"\s*(?:what|what's|whats|where|when|how|who|why|which|can|could|would|will|is|are|do|does|did|should|"
                         r"qu[eé]|d[oó]nde|cu[aá]ndo|c[oó]mo|qui[eé]n|por qu[eé])\b", re.I)
_ROUTE_SAID = re.compile(r"\s*(?:please\s+)?(?:call|email|phone)(?:\s+them)?(?:\s+please)?\s*[.!]*\s*", re.I)   # the ladder's own words


def answers_sashas_question(st: dict, body: str, payload: str, now) -> bool:
    """Sasha 252 · does this message answer Sasha's open question? A TAP: the button that question was sent with (its own id —
    `_payload_ok`, as Sasha 249's old_owns). TYPED: yes / no (the same words _answer_pending reads: YS.is_yes / _NO), "BOOKED"
    after their page, the days or an area for an invitation, a pick from the invitation's cards. Not when the brain has asked its
    own question since (a bare "yes" is then the brain's). Never decides WHAT happens — _answer_pending does, as today."""
    from . import wa_agent as WA
    pend = st.get("pending") or {}
    kind = pend.get("kind")
    if not kind:
        return False
    if payload:
        try:
            return bool(_payload_ok(pend, payload))
        except Exception:
            return False
    t = (body or "").strip()
    if kind not in SASHAS_OWN or not t:
        return False
    asked, at = WA.agent_state(st).get("asked"), pend.get("at")
    if asked and at and _dt(str(asked)) >= _dt(str(at)):
        return False
    if pend.get("resume_asked"):   # "Still want …? Say yes to carry on" (Sasha 161) — asked by _answer_pending itself
        return bool(RESUME.fullmatch(t) or NO.fullmatch(t))
    if kind in _YES_NO_KINDS:
        return YS.is_yes(t) or bool(_NO.match(t)) or (kind == "ladder" and bool(_ROUTE_SAID.fullmatch(t)))
    if kind == "link":
        return bool(re.match(r"^\s*booked\b", t, re.I))
    from . import invitations as IV
    plain = len(t.split()) <= 5 and "?" not in t and not _A_QUESTION.match(t)   # an answer, said plainly — never a new question
    if kind == "invite_window":   # the days ("next week", "Friday")
        return plain and IV.window(t, now) is not None
    if kind == "invite_where":    # an area ("Chamberí", "in Malasaña")
        area = re.sub(r"^\s*(?:in|en|near|around)\s+", "", t, flags=re.I).strip(" .!")
        return (plain and bool(area) and len(area.split()) <= 4 and not re.search(r"\d", area)
                and not (YS.is_yes(area) or _NO.match(area) or GREETING.fullmatch(area)) and cancel_intent(t) is None)
    if kind == "cards":
        try:
            return _picked(pend, t, "") is not None
        except Exception:
            return False
    return False


def _invite_words(body: str, now) -> bool:
    """Sasha 237 · an invitation request (S-80) — still answered by the path below (the agent has no invite tool yet)."""
    from . import invitations as IV
    try:
        return IV.STORE is not None and IV.invite_request(body, now) is not None
    except Exception:
        return False


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
    """The scope gate: a booking, a cancellation, receipts or help — anything else is the one fixed sentence.
    Sasha 253 · item 5 — RETIRED as a WhatsApp entry point: no WhatsApp message reaches it (turn() routes everything to the one
    brain, the kept front routes call their own handlers). Kept, unchanged, for the web voice avatar (voice_turn.py)."""
    out, st = ctx["out"], ctx["st"]
    history = st.get("history") or []
    if _HELP.match(body):
        # Sasha 253 · reached only by the web voice avatar now (voice_turn) — its own fixed line, as before the one brain
        out.text(HELP)
        return
    from . import wa_brain as WB
    if WB.RESET.match(body or ""):   # Sasha 167 (4) · "reset the demo" — founder only, after a yes
        await WB.start_reset(ctx)
        return
    # Sasha 109 · CANCEL before anything else: "Please cancel", "No Please Cancel Yatri", "cancela", "anula la de Yatri"
    ci = cancel_intent(body)
    if ci is not None:
        ctx["cancel_day"] = cancel_day(body)
        await _cancel_find(ctx, ci or None)
        return
    from .itinerary_q import TRIP as _TRIP
    from .itinerary_q import ASK_WHEN as _ASK_WHEN, TRIPS as _TRIPS
    if _RECEIPTS.search(body) and not _TRIP.search(body) and not _ASK_WHEN.search(body) and not _TRIPS.search(body):   # Sasha 165/178
        await _receipts(ctx)
        return
    if await _forwarded_confirmation(ctx, body):   # Sasha 118 · the venue's confirmation, forwarded by the guest
        return
    if ITINERARY_Q.search(body or ""):   # Sasha 132 · ask your itinerary — first: "do I have time to fly…" is a question, not a search
        from . import itinerary_q as IQ
        lines = await IQ.answer(ctx["account"], body, ctx["now"])
        if IQ.TRIP.search(body or ""):   # Sasha 165 · the trip compactly: as few messages as WhatsApp's length allows
            chunk = ""
            for ln in lines:
                if chunk and len(chunk) + len(ln) + 2 > 1400:
                    ctx["out"].text(chunk)
                    chunk = ""
                chunk = f"{chunk}\n\n{ln}" if chunk else ln
            if chunk:
                ctx["out"].text(chunk)
            return
        for line in lines:
            ctx["out"].text(line)
        return
    if FLIGHT.search(body or ""):   # Sasha 132 · flights, Duffel TEST mode
        await _flights(ctx, body)
        return
    if HOTEL.search(body or ""):   # Sasha 132 · a hotel: found as cards, requested from the hotel itself
        await _hotels(ctx, body)
        return
    from . import invitations as IV   # S-80 · "book dinner with Jon this week"
    inv_req = IV.invite_request(body, ctx["now"])
    if inv_req is not None and IV.STORE is not None:
        await _invite(ctx, inv_req)
        return
    from . import captcha_test as CT   # Sasha 159 (5) · "send me the captcha test" (founder only)
    if CT.asked(body):
        out.text(await CT.send(ctx["account"]))
        return
    sm = WB.START.match(body or "")
    if sm and sm["rest"].strip():   # Sasha 178 · "let me start another: …" with nothing open
        await WB.start_another(ctx, sm["rest"])
        return
    want = WB.placeless(body)   # Sasha 167 (2) · a place asked for, no place said: the trip's city (or ONE question), else home
    if want is not None:
        await WB.search(ctx, want, body)
        return
    h = HO.booking_handoff(body, history, ctx["now"])   # Sasha 138 · the turn's own clock: "Saturday" and urgency agree
    if h is not None:
        if h.get("booking_cancel"):
            await _cancel_find(ctx, h["booking_cancel"]["venue"])
        elif h.get("booking_find"):   # Sasha 167 · morning or night? inside the trip? — asked first, then the search
            await WB.gate(ctx, dict(h["booking_find"]), dict((h.get("reservation_draft") or {}).get("parts") or {}), body)
        else:
            out.text(h["response"])
        return
    from .chat_request import booking_turn
    t = booking_turn(body, history)
    if t is not None:
        out.text(t["response"])
        return
    # Sasha 104 · a booking said only in part ("sort out Saturday night for 2") → one question, in WhatsApp's own flow
    if maybe_booking(body):
        out.text(ASK_ONE)
        return
    # Sasha 167 (1) · no dead end: anything else is the web chat's own turn (plan a trip, ideas, questions), here
    if await WB.web_turn(ctx, body):
        return
    out.text("I couldn't answer that just now — please try again in a moment.")


# ── Sasha 132 · flights in Duffel TEST mode: cards → Book it → one-touch test payment → the test order → the itinerary ──

FLIGHT = re.compile(r"\b(flights?|fly|vuelos?|volar)\b.*\bfrom\s+\S.*\bto\s+\S|\b(flights?|vuelos?)\s+(?:from\s+)?[A-Z][\w .'-]+\s+to\s+[A-Z]", re.I)
_FROM_TO = re.compile(r"\b(?:from\s+)?(?P<o>[A-ZÁÉÍÓÚ][\wáéíóúñ .'-]*?)\s+to\s+(?P<d>[A-ZÁÉÍÓÚ][\wáéíóúñ .'-]*?)"
                      r"(?=\s+(?:on|for|next|this|tomorrow|today|el|para)\b|\s*[,.?!]|\s*$)")
from .itinerary_q import QUESTION as ITINERARY_Q   # noqa: E402 — the same question, on the web and WhatsApp


HOTEL = re.compile(r"\b(hotel|room|stay|alojamiento|habitaci[oó]n)\b.*\bin\s+[A-ZÁÉÍÓÚ]", re.I)
_DATES = re.compile(r"\bfrom\s+(?P<a>.+?)\s+(?:to|until|till)\s+(?P<b>[^,.?!]+)", re.I)
_NIGHTS = re.compile(r"\b(\d{1,2})\s+nights?\b", re.I)


def stay_of(body: str, now: datetime) -> Optional[dict]:
    """A hotel stay in words ("a hotel in Hoi An from 14 to 16 November for 2") → {where, find, a, nights, party}, or None.
    Shared by WhatsApp and the web (Sasha 143: hotel_web.web_turn), so both read a stay the same way."""
    m = re.search(r"\bin\s+(?P<w>[A-ZÁÉÍÓÚ][\wáéíóúñ ,'-]*?)(?=\s+(?:from|for|on|next|this)\b|[.?!]|$)", body or "")
    dm, nm = _DATES.search(body or ""), _NIGHTS.search(body or "")
    a = HO.plain_date(dm["a"], now) if dm else HO.plain_date(body or "", now)
    b = HO.plain_date(dm["b"], now) if dm else None
    if dm and a and not b and re.fullmatch(r"\s*\d{1,2}\s*", dm["a"] or ""):   # "from 14 to 16 November": the month is said once
        b = HO.plain_date(dm["b"], now)
    if dm and not a and b and re.fullmatch(r"\s*\d{1,2}(?:st|nd|rd|th)?\s*", dm["a"]):
        a = b[:8] + "%02d" % int(re.sub(r"\D", "", dm["a"]))
    nights = (date.fromisoformat(b) - date.fromisoformat(a)).days if a and b else (int(nm[1]) if nm else 0)
    if not m or not a or not 1 <= nights <= 30:
        return None
    f = HO.find_request(f"hotel in {m['w'].strip()}", now) or {"what": "hotel", "where": m["w"].strip()}
    if not f.get("country"):   # Sasha 138 · "Madrid" is Spain: the country decides the call's language and the hotel's time zone
        w = m["w"].strip()
        cn = re.fullmatch(r"(.+?),\s*([^,]+)", w)
        f["country"] = (HO.COUNTRY_NAMES.get(cn[2].strip().lower()) if cn else None) or (HO.known_place(w) or (None, None, None))[2]
    return {"where": m["w"].strip(), "find": f, "a": a, "nights": nights, "party": HO.plain_party(body or "") or 2}


def stay_what(nights: int, checkin: str, country: Optional[str]) -> dict:
    """Sasha 138 · a room for N nights, as a call or a form says the stay (in Spanish in Spain). Shared with the brain (Sasha 253, G8)."""
    out_day = (date.fromisoformat(checkin) + timedelta(days=nights)).isoformat()
    en = f"a room for {nights} night{'s' if nights != 1 else ''} (check-out {out_day})"
    es = f"una habitación para {nights} noche{'s' if nights != 1 else ''} (salida el {out_day})"
    return {"activity": en, "activity_venue_lang": es if (country or "") == "ES" else en, "category": "other"}


async def _hotels(ctx: dict, body: str) -> None:
    """Duffel Stays isn't enabled on this account and RateHawk has no credentials, so a hotel is NOT booked instantly: it is
    found (Google, with its own photo), and the room is requested from the hotel itself — its form, page or email — said so."""
    out = ctx["out"]
    stay = stay_of(body, ctx["now"])
    if stay is None:
        out.text("Tell me where and the dates, e.g. “a hotel in Hoi An from 14 to 16 November for 2”.")
        return
    m, f, a, nights, party = {"w": stay["where"]}, stay["find"], stay["a"], stay["nights"], stay["party"]
    out.text(f"Hotels for {nights} night{'s' if nights != 1 else ''} from {SN.day_words(a)}, {party} {'person' if party == 1 else 'people'}. "
             f"For the one you pick: a TEST booking (no hotel contacted), or a real request to the hotel.")
    ctx["no_test_card"] = True
    await _find(ctx, {"what": "hotel", "where": f.get("where") or m["w"].strip(), "country": f.get("country")},
                {"parts": {"what": stay_what(nights, a, f.get("country")),
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
    # Sasha 282 · written down BEFORE the payment is offered (as a flight, Sasha 183): settle books it from this record, and only from it
    from . import paid_watch as PWT
    stay = {k: pend.get(k) for k in ("hotel", "city", "country", "checkin", "nights", "party")}
    if not await PWT.remember(ctx["account"], "hotel", got["id"], {"stay": stay}, f"{HT.LABEL} — {pend['hotel']}", None, HT.tz_of(pend.get("country"))):
        ctx["out"].text("I can't take the test payment right now — I couldn't note it down first. No test booking was made; ask me again in a moment.")
        return
    ctx["out"].text(f"One touch: pay the TEST price (€{pend['eur']:.2f}) on Stripe's test page — Apple Pay or your phone's saved card; nothing "
                    f"is charged and no hotel is contacted.\n{got['url']}\nI'll add the TEST booking the moment it's paid.")
    _spawn(watch_payment(ctx["ch"], ctx["frm"], got["id"], "The test payment wasn't completed within 10 minutes, so no test booking was made."))


async def watch_payment(ch: Optional[dict], frm: str, session_id: str, unpaid: str) -> None:
    """Sasha 282 · a paid thing is booked by paid_watch.settle ONLY, from the record written before paying — which goes with its owner
    (trips.owner_id → auth.users, on delete cascade). This only asks settle sooner than its own loop; it never books. No record any
    more (the account was deleted) → it stops: there is no one to book for."""
    from . import paid_watch as PWT
    every, times = WATCH_PAY
    for _ in range(times):
        await asyncio.sleep(every)
        r = await PWT.settle(session_id)   # booked once, by whoever sees the payment first — and said by it (live_events.completed)
        if r is not None and r.get("status") in ("booked", "failed"):
            return
        if r is None and not await _remembered(session_id):
            log.info("[guest_whatsapp] payment watch stopped: no record for the session (its account is gone)")
            return
    await _tell_if_linked(ch, frm, unpaid)


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
    from . import paid_watch as PWT   # Sasha 183 · written down BEFORE paying: a restart can never lose the booking
    if not await PWT.remember(ctx["account"], "flight", got["id"], {"card": c, "name": pend["name"], "email": pend["email"], "phone": pend.get("phone")},
                              f"Flight {c['flights']} {c['from']} → {c['to']}", c.get("departs"), c.get("from_tz") or "Europe/Madrid"):
        ctx["out"].text("I can't take the test payment right now — I couldn't note it down first. Nothing was booked; ask me again in a moment.")
        return   # Sasha 282 · no record, no payment: settle books only from its record
    ctx["out"].text(f"One touch: pay the TEST fare ({c['currency']} {c['amount']}) on Stripe's test page — Apple Pay or your phone's saved card; "
                    f"nothing is charged, and I never see your card.\n{got['url']}\nI'll book the test flight the moment it's paid, and tell you here.")
    _spawn(watch_payment(ctx["ch"], ctx["frm"], got["id"], "The test payment wasn't completed within 10 minutes, so nothing was booked. Ask me again any time."))


WATCH_PAY = (10, 60)   # every 10 s for 10 minutes


async def _remembered(session_id: str) -> bool:
    """A payment paid_watch holds (it books it); False → the old path books it here."""
    from . import paid_watch as PWT
    run = PWT._run()
    if run is None:
        return False
    try:
        return bool(await run(lambda c: c.fetchval("select 1 from trip_items where escalation_notes like $1 limit 1",
                                                   f"Sasha 183 · %\"sid\": \"{session_id}\"%")))
    except Exception:
        return False


async def _tell_if_linked(ch: Optional[dict], frm: str, text: str) -> None:
    """Sasha 216 · the payment watcher's word to their WhatsApp — only when there IS a channel (a watch can outlive it: the
    channel deleted, or never linked). The booking itself and the payment page's note never depend on it."""
    if not ch or not ch.get("wa_id_sha256"):
        log.info("[guest_whatsapp] payment outcome not sent to WhatsApp: no channel")
        return
    st = await STORE.get_state(ch["wa_id_sha256"]) or {}
    await deliver(ch, frm, Out().text(text), st.get("last_inbound_at"))


# ── Sasha 126 · the spa membership (Kanoe Demo Spa, ours) and two bookings from one sentence ───────────────────────

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




async def _forwarded_confirmation(ctx: dict, body: str) -> bool:
    """Sasha 118 (3) · a guest forwards (or pastes) a venue's confirmation: filed on the ONE booking it names (written.py),
    read with the field checks, and answered here. Not a confirmation → False (the turn goes on)."""
    # Sasha 253 · the web voice avatar runs this turn with no WhatsApp channel (ch None) — found by the gate: every voice turn crashed
    line = await forwarded_confirmation(ctx["account"], (ctx.get("ch") or {}).get("number_e164"), body, ctx["now"])
    if line is None:
        return False
    ctx["out"].text(line)
    return True


async def forwarded_confirmation(account: str, number: Optional[str], body: str, now, prefix: str = "wa-fwd-") -> Optional[str]:
    """Sasha 253 · G1 — the ONE place a forwarded / pasted venue confirmation is filed (Sasha 118's, unchanged): the old flow
    (_forwarded_confirmation) and the one brain's tool (agapi/s2_manage.file_confirmation) both call it. → the line to say, or
    None when it isn't a confirmation (nothing filed)."""
    from . import mailbox as MB, written as W
    if len(body or "") < 40 or not MB._CONFIRM.search(body or "") or not MB._when(body, now):
        return None
    if HO.booking_handoff(body, []) is not None:   # a new request that happens to say "your booking" is a request
        return None
    sid = prefix + hashlib.sha256(f"{account}|{body}".encode()).hexdigest()[:24]
    try:
        got = await W.file(sid, "whatsapp", number, None, body, now, account=account, forwarded=True)
    except Exception as e:
        log.error("[guest_whatsapp] a forwarded confirmation was not filed: %s: %s", type(e).__name__, e)
        got = None
    if got is None:
        return ("That reads like a booking confirmation, but I can't tell which of your bookings it's for — it needs their "
                "reference, or the venue's name and the day. Nothing was changed.")
    when = SN.day_words(got.get("day")) if got.get("day") else ""
    if got["result"] == "confirmed":
        return f"✅ Confirmed in writing: {got['venue']}{', ' + when if when else ''}. I've filed their confirmation on it (forwarded by you)."
    if got["result"] == "already filed":
        return f"I already have that confirmation on {got['venue']}."
    if got["result"] == "proposed":
        return f"⚠ {got['venue']}'s message offers something different — {got['why']}. I've filed it on the booking; nothing else changed."
    return (f"I've filed it on {got['venue']}{', ' + when if when else ''}, but it doesn't confirm the day, time and number "
            f"together, so I haven't marked it confirmed.")


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
        from . import wa_brain as WB   # Sasha 167 (5) · asked here, never "add them at …"
        await WB.ask_contact(ctx, None)
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

def _header(f: dict, luxe: bool) -> str:
    from .handoff import _plural_kind
    # Sasha 248 · the search's words describe the SEARCH, never every card ("the best-rated Korean restaurants" over a Spanish one)
    return f"Here are the best-rated places for “{f.get('what') or 'your search'}” in {f.get('where')}{' (€€€ and up first)' if luxe else ''}."


def city_of(address: Optional[str]) -> Optional[str]:
    """The city in a Google address ("…, 28005 Madrid, Spain" → "Madrid") for a venue found by its name alone."""
    parts = [x.strip() for x in (address or "").split(",") if x.strip()]
    c = re.sub(r"[\d-]+", "", parts[-2]).strip() if len(parts) >= 2 else ""
    return c if len(c) >= 2 else None


def luxe_of(what: Optional[str]) -> bool:
    """Sasha 104 · they asked for luxury ("luxury", "upscale", "fine dining", "lujo"…). Shared with the brain (Sasha 253, G14)."""
    return any(q in HO.LUXURY for q in HO.qualities(what or ""))


def luxe_first(order: list, cands: dict) -> list:
    """Sasha 104 · "luxury": Google's €€€ and €€€€ first, best rated within; the rest after, never dropped."""
    return sorted(order, key=lambda pid: not ((cands.get(pid) or {}).get("price_level") or 0) >= 3)


async def _find(ctx: dict, f: dict, draft: dict) -> None:
    from .ranking import rating_words
    from .venue_read import distance_words
    out, account = ctx["out"], ctx["account"]
    status, j = await api(account, "POST", "/api/booking/venues/find",
                          {k: v for k, v in {"what": f.get("what"), "where": f.get("where"), "country": f.get("country"),
                                             "open_at": f.get("open_at"), "named": f.get("named")}.items() if v})
    if status != 200:
        out.text(f"I can't search for places right now — {refusal_words(j, status)}.")
        return
    if f.get("named"):   # Sasha 158 · NAME IT: that venue, one card, then straight on to booking it
        c = (j.get("candidates") or [None])[0]
        if not c:
            out.text(f"I couldn't find {f.get('what')}. Could you tell me the city?")
            return
        photos, _late = await _photos_within([c], photo_wait() + 1.0)
        out.media(" · ".join(x for x in (c.get("name"), rating_words(c), c.get("address")) if x), photos.get(c["place_id"]))
        parts = dict(draft.get("parts") or {})
        if "what" not in parts and re.search(r"restaurant|bar|caf|bistro|tavern|grill|steak|sushi|pizz|brasserie|tapas|food|bodega",
                                             str(c.get("type") or ""), re.I):
            parts["what"] = {"activity": "a table", "activity_venue_lang": "una mesa", "category": "restaurant"}   # a restaurant: a table
            if f.get("bare_time") and not f.get("open_at"):
                f = {**f, "open_at": HO.restaurant_time(f["bare_time"])}
        await _picked_card(ctx, {"find": {**f, "where": f.get("where") or city_of(c.get("address")) or "the city"},
                                 "draft": parts},
                           {"place_id": c["place_id"], "name": c.get("name"), "country": c.get("country"), "type": c.get("type")})
        return
    cands = {c["place_id"]: c for c in j.get("candidates") or []}
    ranking = j.get("ranking") or {}
    chip = f.get("priority") if f.get("priority") in (ranking.get("orders") or {}) else ranking.get("default", "rated")
    order = (ranking.get("orders") or {}).get(chip) or list(cands)
    luxe = luxe_of(f.get("what"))
    if luxe:
        order = luxe_first(order, cands)
    shown = [cands[i] for i in order if i in cands][:3]
    if j.get("note"):   # Sasha 187 · said in one line: online-only, looked further, or none online
        out.text(j["note"])
    if not shown and j.get("note"):
        return
    if not shown and j.get("no_match"):   # Sasha 186 · the cuisine is honoured: never another kind of place in its place
        out.text(f"I found no {j['no_match'].title()} places in {f.get('where')} — Google's results there weren't {j['no_match'].title()}. "
                 f"Shall I widen it (say “restaurants in {f.get('where')}”) or try another area?")
        return
    if not shown:
        out.text(f"I found no {f.get('what')} in {f.get('where')}. Try another area or kind of place.")
        return
    pick = shown[0]["place_id"] if luxe else (ranking.get("picks") or {}).get(chip)
    # Sasha 149 · streamed: the header goes NOW, then each card the moment its own photo is ready (rank order kept)
    if stream_cards() and ctx.get("ch") and ctx.get("frm"):
        await _stream_cards(ctx, f, shown, cands, ranking, luxe, pick, draft, account)
        return
    # Sasha 140 · never block on photos: the cards go with what's ready within the budget; the rest follow on their own
    photos, late = await _photos_within(shown, ctx.get("photo_wait") or photo_wait())   # Sasha 169 · the voice page waits longer (no late photos)
    if rehearsal(account) and not ctx.get("no_test_card") and not _real_restaurant(f, account):   # Sasha 186 · restaurants are real   # Sasha 117 · the dress rehearsal books OUR test venue; the card says so
        shown = shown[:2] + [TEST_CARD]                   # still three: WhatsApp shows at most three reply buttons
    what = f.get("what") or ""
    out.text(_header(f, luxe))   # Sasha 158 · one sentence; how they were found and ranked is not the guest's business
    for c in shown:
        line = " · ".join(x for x in (c.get("name") or "no name listed", rating_words(c),
                                       distance_words(c["distance_m"]) if c.get("distance_m") is not None else None) if x)
        if c is TEST_CARD:
            line = "Rehearsal · Sasha Test Venue — ours, not a real restaurant: booking it contacts no one"
        out.media(("Sasha's pick · " if c["place_id"] == pick else "") + line, photos.get(c["place_id"]))
    nonce = secrets.token_hex(3)
    out.ask("Which one?", [(c.get("name") or f"Option {i + 1}", f"pick:{nonce}:{i}") for i, c in enumerate(shown)])
    if late and ctx.get("ch"):
        _spawn(_late_photos(ctx["ch"], ctx["frm"], {c["place_id"]: c.get("name") or "" for c in shown}, late))
    ctx["st"]["pending"] = {"kind": "cards", "at": ctx["now"].isoformat(), "nonce": nonce, "find": f,
                            "draft": draft.get("parts") or {},
                            "cards": [{"place_id": c["place_id"], "name": c.get("name"), "country": c.get("country"),
                                       "address": c.get("address"), "type": c.get("type")} for c in shown]}   # Sasha 169 · "the one by the river"


def _founder_demo(account) -> bool:
    """The founder's demo is on (his record: demo = founder_rehearsal; was SASHA_DEMO_STANDIN): only then does a read-back say which kind it is (guests unchanged)."""
    from .ladder_routes import standin
    return standin(account)


def _real_restaurant(f: dict, account=None) -> bool:
    """Sasha 186 · in the founder's demo (stand-in on) his restaurants are real: no test card beside them (spas, studios keep it)."""
    from .ladder_routes import is_restaurant
    return is_restaurant((f or {}).get("what")) and _founder_demo(account)


TEST_CARD = {"place_id": "sasha-test-venue", "name": "Sasha Test Venue", "country": "ES"}


def rehearsal(account: str) -> bool:
    """The cards end with OUR test venue: on a record with demo = founder_rehearsal (Sasha 254; was the founder + SASHA_REHEARSAL=1) — and ALWAYS for an account
    that may not contact real venues (Sasha 153: every automatic guest), so a guest can complete a booking end to end."""
    from app.services.accounts import is_founder_test   # Sasha 254 · the one record: demo = founder_rehearsal
    # Sasha 175 (EU 172) · never to a guest: "Sasha Test Venue (ours — rehearsal)" in a stranger's search was a failure
    return is_founder_test(account, power="rehearsal")


#: Sasha 140 · each venue's OWN share-picture URL, by its website (not Google content: cacheable), with "none" remembered too
PHOTO_CACHE: Dict[str, Tuple[float, Optional[str]]] = {}
PHOTO_TTL = 24 * 3600


def photo_wait() -> float:
    """How long the cards wait for photos before going out without the late ones (they follow on their own)."""
    try:
        return float(os.getenv("SASHA_PHOTO_WAIT_S", "") or 1.0)
    except ValueError:
        return 1.0


async def _photo_of(c: dict) -> Tuple[str, Optional[str]]:
    """The venue's OWN picture first; Sasha 156: else its Google listing's photo (never cached — Google's URL is short-lived)."""
    from . import ladder_routes as LR, venue_read as V
    gname = (c.get("gphoto") or {}).get("name")
    if not c.get("website"):
        return c["place_id"], (await V.google_photo_uri(LR.HTTP, gname) if gname else None)
    if not gname:
        return await _own_photo_of(c)
    own = asyncio.ensure_future(_own_photo_of(c))
    goog = asyncio.ensure_future(V.google_photo_uri(LR.HTTP, gname))
    try:   # their own picture wins when it comes in time (a warm cache: at once); else Google's, never a wait for both
        _pid, img = await asyncio.wait_for(asyncio.shield(own), own_photo_wait())
        if img:
            goog.cancel()
            return c["place_id"], img
    except asyncio.TimeoutError:
        pass
    except Exception:
        pass
    g = await goog
    if g:
        return c["place_id"], g
    _pid, img = await own
    return c["place_id"], img


def own_photo_wait() -> float:
    try:
        return float(os.getenv("SASHA_OWN_PHOTO_WAIT_S", "") or 0.8)
    except ValueError:
        return 0.8


async def _own_photo_of(c: dict) -> Tuple[str, Optional[str]]:
    from . import ladder_routes as LR, style as ST
    site = c.get("website")
    hit = PHOTO_CACHE.get(site)
    if hit and time.time() - hit[0] < PHOTO_TTL:
        return c["place_id"], hit[1]
    try:
        page = await ST.page_text(LR.HTTP, site, LR.RESOLVE)
        img = page.get("image")
    except Exception as e:
        log.info("[guest_whatsapp] no photo: %s", type(e).__name__)
        return c["place_id"], None   # a failure isn't cached: the next ask tries again
    PHOTO_CACHE[site] = (time.time(), img)
    return c["place_id"], img


async def _photos(account: str, what: str, shown: List[dict]) -> Dict[str, str]:
    """The venue's OWN share picture from its own site (og:image, robots first — style.page_text), never a Google one.
    Read WITHOUT the style summary: that is a model call, and on WhatsApp the model is never called. In parallel, cached."""
    got = await asyncio.gather(*(_photo_of(c) for c in shown if c.get("website") or c.get("gphoto")))
    return {pid: url for pid, url in got if url}


def stream_cards() -> bool:
    """Sasha 149 · SASHA_STREAM_CARDS=1: WhatsApp sends each card as it's ready instead of all three together."""
    return os.getenv("SASHA_STREAM_CARDS", "") == "1"


def _card_line(c: dict, pick: Optional[str]) -> str:
    from .ranking import rating_words
    from .venue_read import distance_words
    line = " · ".join(x for x in (c.get("name") or "no name listed", rating_words(c),
                                   distance_words(c["distance_m"]) if c.get("distance_m") is not None else None) if x)
    if c is TEST_CARD:
        line = "Rehearsal · Sasha Test Venue — ours, not a real restaurant: booking it contacts no one"
    return ("Sasha's pick · " if c["place_id"] == pick else "") + line


async def _stream_cards(ctx: dict, f: dict, shown: List[dict], cands: dict, ranking: dict, luxe: bool, pick: Optional[str],
                        draft: dict, account: str) -> None:
    """The same cards, the same words and order — sent one by one as each is ready. What the turn had already said goes
    first (so nothing arrives out of order); the "Which one?" buttons stay in the turn's own reply, last."""
    out, ch, frm = ctx["out"], ctx["ch"], ctx["frm"]
    last = (ctx.get("st") or {}).get("last_inbound_at")
    started = asyncio.get_running_loop().time()
    tasks = {c["place_id"]: asyncio.ensure_future(_photo_of(c)) for c in shown if c.get("website") or c.get("gphoto")}
    if rehearsal(account) and not ctx.get("no_test_card") and not _real_restaurant(f, account):   # Sasha 186 · restaurants are real
        shown = shown[:2] + [TEST_CARD]
    what = f.get("what") or ""
    out.text(_header(f, luxe))   # Sasha 158 · one sentence; how they were found and ranked is not the guest's business
    head = Out()
    head.items, out.items = list(out.items), []   # what the turn said so far, the header last: sent now, in order
    await deliver(ch, frm, head, last)
    late: List[asyncio.Task] = []
    for c in shown:
        url, t = None, tasks.get(c["place_id"])
        if t is not None:
            left = photo_wait() - (asyncio.get_running_loop().time() - started)
            try:
                _pid, url = await asyncio.wait_for(asyncio.shield(t), max(0.0, left))
            except asyncio.TimeoutError:
                late.append(t)
            except Exception:
                url = None
        await deliver(ch, frm, Out().media(_card_line(c, pick), url), last)
    nonce = secrets.token_hex(3)
    out.ask("Which one?", [(c.get("name") or f"Option {i + 1}", f"pick:{nonce}:{i}") for i, c in enumerate(shown)])
    if late:
        _spawn(_late_photos(ch, frm, {c["place_id"]: c.get("name") or "" for c in shown}, late))
    ctx["st"]["pending"] = {"kind": "cards", "at": ctx["now"].isoformat(), "nonce": nonce, "find": f,
                            "draft": draft.get("parts") or {},
                            "cards": [{"place_id": c["place_id"], "name": c.get("name"), "country": c.get("country"),
                                       "address": c.get("address"), "type": c.get("type")} for c in shown]}   # Sasha 169 · "the one by the river"


async def _photos_within(shown: List[dict], budget: float) -> Tuple[Dict[str, str], List[asyncio.Task]]:
    """Sasha 140 · the photos ready within `budget` seconds (all of them on a warm cache), and the fetches still running."""
    tasks = [asyncio.ensure_future(_photo_of(c)) for c in shown if c.get("website") or c.get("gphoto")]
    if not tasks:
        return {}, []
    done, pending = await asyncio.wait(tasks, timeout=budget)
    ready = {pid: url for pid, url in (t.result() for t in done) if url}
    return ready, list(pending)


async def _late_photos(ch: dict, frm: str, names: Dict[str, str], pending: List[asyncio.Task]) -> None:
    """The photos that came after the cards: each its own message, named — the cards never waited for them."""
    await asyncio.sleep(2)   # the cards (the turn's own reply) go first
    for t in asyncio.as_completed(pending, timeout=20):
        try:
            pid, url = await t
        except Exception:
            continue
        if url and pid in names:
            st = await STORE.get_state(ch["wa_id_sha256"])
            await deliver(ch, frm, Out().media(f"📷 {names[pid]}", url), st.get("last_inbound_at"))


# ── pending questions ───────────────────────────────────────────────────────────────────────────────────────────────

GREETING = re.compile(r"\s*(?:hi|hey|hello|hola|buenas|good (?:morning|afternoon|evening)|ola|ciao)(?:\s+(?:sasha|there|again))?\s*[!.?👋]*\s*", re.I)


STALE_AFTER = timedelta(hours=2)
RESUME = re.compile(r"\s*(?:yes|yeah|yep|sure|ok(?:ay)?|carry on|continue|go on|s[ií]|vale)\b.*", re.I)
NO = re.compile(r"\s*(?:no|nope|drop it|cancel that|never mind|forget it)\b.*", re.I)


def _still_want(pend: dict) -> str:
    """"Still want Casa Lucio for Wednesday?" — from what the pending step holds."""
    from . import sentences as SN
    venue = (pend.get("read") or {}).get("venue") or pend.get("venue")
    at = (((pend.get("draft") or {}).get("when") or {}).get("at") or "")
    day = f" for {SN.day_words(at[:10]).split(' ')[0]}" if len(at) >= 10 else ""
    if pend.get("kind") == "cards":
        f = pend.get("find") or {}
        return f"Still looking for {f.get('what') or 'a place'} in {f.get('where') or 'town'}?"
    return f"Still want {venue}{day}?" if venue else "Still want to finish what we started?"


def _open_item(pend: dict) -> str:
    """What's half-done, in a few words, from what the pending step holds (never its machinery)."""
    venue = (pend.get("read") or {}).get("venue") or pend.get("venue")
    kind = pend.get("kind")
    if kind == "cards":
        f = pend.get("find") or {}
        return f"You were choosing {f.get('what') or 'a place'} in {f.get('where') or 'town'}."
    if kind in ("confirm", "cancel_confirm"):
        return f"Your {'cancellation' if kind == 'cancel_confirm' else 'booking'} at {venue or 'the venue'} is waiting for your yes."
    if venue:
        return f"We were in the middle of your booking at {venue}."
    return "We were in the middle of something."


async def _answer_pending(ctx: dict, body: str, payload: str) -> bool:
    """Sasha 253 · item 5 — on WhatsApp, reached only for Sasha's own open question (answers_sashas_question, the G3 resolver), a
    demo's own question (until G11) and before an invitation request; the web voice avatar (voice_turn.py) calls it as before."""
    out, st, now = ctx["out"], ctx["st"], ctx["now"]
    pend = st.get("pending")
    if payload and (not pend or not _payload_ok(pend, payload)):
        out.text("That button was for an earlier question — nothing was sent. Ask me again and I'll start afresh.")
        return True
    if not pend:
        return False
    at = _dt(pend.get("at") or "")
    kind = pend["kind"]
    # Sasha 165 · "show me my itinerary" / "what was I doing?" is a QUESTION, never the answer to the open one: it's
    # answered, and the open item stays open
    from .itinerary_q import TRIP as _TRIP
    if not payload and _TRIP.search(body or "") and not RESUME.fullmatch(body or ""):
        return False
    if kind == "booked":
        if payload == f"cxl:{pend['nonce']}":   # the Cancel button: the same cancellation as typed, one yes before anything
            st["pending"] = None
            await _cancel_find(ctx, pend.get("venue"))
            return True
        st["pending"] = None
        return False
    from . import wa_brain as _WB
    if not payload and kind in _WB.PARKABLE:   # Sasha 178 · PARK AND SWITCH
        sm = _WB.START.match(body or "")
        if sm:
            out.text(await _WB.park(ctx, pend))
            await _WB.start_another(ctx, sm["rest"])
            return True
        if _WB.PARK.search(body or ""):
            out.text(await _WB.park(ctx, pend))
            return True
    if kind == "ladder":   # Sasha 195 · the ladder's choice → acted on at once (the choice IS the yes; nothing read out again)
        opts = pend.get("options") or {}
        route = payload.split(":", 2)[2] if payload.startswith(f"lad:{pend['nonce']}:") else None
        if route is None:
            t = (body or "").lower()
            route = ("no" if re.search(r"\b(no|nope|not now|cancel)\b", t) else
                     # Sasha 254 · the booking rules' ONE question's two answers: "handle it" (the form) / "prefilled form" (their page)
                     "form" if re.search(r"\bhandle\b", t) and "form" in opts.values() else
                     "page" if re.search(r"\bprefilled\b", t) and "page" in opts.values() else "email" if "email" in t else
                     "call" if re.search(r"\bcall\b", t) else "page" if re.search(r"\b(now|page|send|link)\b", t) else
                     next((r for r in opts.values() if r != "no"), None) if re.search(r"\b(yes|ok|okay|sure|go ahead|book it|please)\b", t) else None)
        if route is None or (route != "no" and route not in opts.values()):
            st["pending"] = None
            return False
        st["pending"] = None
        try:   # the same 15-minute window as every yes: a late choice places nothing
            if route != "no" and ctx["now"] - datetime.fromisoformat(pend["at"]) > APPROVAL_WINDOW:
                out.text("That question has expired (15 minutes) — nothing was booked. Ask me again.")
                return True
        except (KeyError, ValueError):
            pass
        if route == "no":
            out.text("OK — nothing was sent.")
            return True
        mark = len(out.items)
        await _prepare_or_ask(ctx, {**(pend.get("saved") or {}), "ladder_route": route})
        p2 = st.get("pending") or {}
        if route in ("form", "email", "call") and p2.get("kind") == "confirm":
            del out.items[mark:]
            await _approve(ctx, p2, {"how": "button"})
            if route == "email":
                v = plain_venue(p2.get("venue"))
                out.items = [(it[0], f"Done — I've emailed {v}. I'll update you as soon as I hear back.", *it[2:]) if it[0] == "text" and it[1] == DONE_ASKED else it
                             for it in out.items]
        return True
    if kind == "city_q":
        if await _WB.city_answer(ctx, pend, body, payload):
            return True
        st["pending"] = None
        return False
    if kind in ("trip_where", "trip_added", "contact_name", "demo_reset", "gate"):   # Sasha 167 · wa_brain's own questions
        from . import wa_brain as WB
        if await WB.answer(ctx, pend, body, payload):
            return True
        if kind != "trip_added":   # an added place stays bookable ("book it at 8") across other questions
            st["pending"] = None
        return False
    # Sasha 161 · STALE: after a greeting or a gap, ASK whether to continue — never resume mid-question
    if pend.get("resume_asked") and not payload:
        if RESUME.fullmatch(body or ""):
            pend.pop("resume_asked", None)
            pend["at"] = ctx["now"].isoformat()
            if kind == "need":
                await _prepare_or_ask(ctx, pend)
            else:
                out.text("OK — where were we: " + _open_item(pend))
            return True
        if NO.fullmatch(body or ""):
            st["pending"] = None
            out.text("OK — dropped. What would you like instead?")
            return True
        st["pending"] = None
        return False   # anything else is a new request: it starts afresh
    gap = (ctx["now"] - at) > STALE_AFTER if at else False
    if not payload and (GREETING.fullmatch(body or "") or (gap and kind in ("need", "cards", "confirm"))):
        from .handoff import booking_handoff
        if gap and not GREETING.fullmatch(body or "") and booking_handoff(body or "") is not None:
            st["pending"] = None
            return False   # a whole new request after a gap starts afresh
        pend["resume_asked"] = True
        out.text(f"{'Hi! ' if GREETING.fullmatch(body or '') else ''}{_still_want(pend)} Say “yes” to carry on, or tell me what you'd like now.")
        return True
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
        if i is None and not payload:
            # Sasha 167 · a WHOLE new request (a kind of place AND a place, said plainly) is a new search — never folded into
            # these cards as a refinement (live: "romantic booking for two at a restaurant in Hoi An, October 27 at 09:00"
            # was searched as "romantic booking two October restaurant", and its 09:00 never asked about)
            from . import wa_brain as WB
            nh = HO.booking_handoff(body, [], ctx["now"]) or {}
            nf, nparts = nh.get("booking_find") or {}, (nh.get("reservation_draft") or {}).get("parts") or {}
            # its own place AND its own day/time or party — "Italian in Malasaña" alone stays a refinement (day and party kept)
            old = pend.get("find") or {}
            ow, nw = _fold(old.get("where") or ""), _fold(nf.get("where") or "")
            # another CITY (Hoi An after Hanoi), never a neighbourhood of the same one ("Malasaña" → "Malasaña, Madrid" after Madrid)
            other_place = bool(nw) and bool(ow) and ow.split(",")[-1].strip() not in nw and nw.split(",")[0].strip() not in ow
            if nf.get("where") and (nf.get("open_at") or nparts.get("when") or nparts.get("how_many") or WB._ORD_DAY.search(body or "")
                                    or other_place) \
                    and WB.sasha_clear(body, [], ctx["now"]):   # Sasha 169/174 · its own day, place or kind: a new search
                st["pending"] = None
                return False
        if i is None:
            # Sasha 104 · while the cards show, anything that is not a pick is a REFINEMENT of this search: the area,
            # day, time and party are kept unless the message changes them; the kind of place is replaced; every
            # quality asked for is kept. A plain yes/no/thanks gets the question again.
            merged = refine(pend, body, ctx["now"])
            if merged is None and not payload:
                # Sasha 156 · a whole new search ("restaurants in Lisbon tonight") is a NEW search, never "Which one?" again
                from .handoff import booking_handoff
                if ((booking_handoff(body) or {}).get("booking_find") or {}).get("where"):
                    st["pending"] = None
                    return False
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
        got = engine_check_answer(pend, body, now)
        if got is None:
            return False
        if got is False:
            st["pending"] = None
            return False
        line, st["pending"] = got
        out.text(line)
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
        if payload.startswith("yes:") or YS.is_yes(body):   # Sasha 269 · a question left from before 269: Sasha's own R5 call is gone
            st["pending"] = None                              # (a call is the act's — venue.call_again); nothing is prepared or dialled
            from app.agent import voice as V
            out.text(V.NO_CALL_OPEN)
            return True
        return False
    if kind in ("confirm", "cancel_confirm"):
        return f"Your {'cancellation' if kind == 'cancel_confirm' else 'booking'} at {venue or 'the venue'} is waiting for your yes."
    if venue:
        return f"We were in the middle of your booking at {venue}."
    return "We were in the middle of something."


async def _answer_pending(ctx: dict, body: str, payload: str) -> bool:
    """Sasha 253 · item 5 — on WhatsApp, reached only for Sasha's own open question (answers_sashas_question, the G3 resolver), a
    demo's own question (until G11) and before an invitation request; the web voice avatar (voice_turn.py) calls it as before."""
    out, st, now = ctx["out"], ctx["st"], ctx["now"]
    pend = st.get("pending")
    if payload and (not pend or not _payload_ok(pend, payload)):
        out.text("That button was for an earlier question — nothing was sent. Ask me again and I'll start afresh.")
        return True
    if not pend:
        return False
    at = _dt(pend.get("at") or "")
    kind = pend["kind"]
    # Sasha 165 · "show me my itinerary" / "what was I doing?" is a QUESTION, never the answer to the open one: it's
    # answered, and the open item stays open
    from .itinerary_q import TRIP as _TRIP
    if not payload and _TRIP.search(body or "") and not RESUME.fullmatch(body or ""):
        return False
    if kind == "booked":
        if payload == f"cxl:{pend['nonce']}":   # the Cancel button: the same cancellation as typed, one yes before anything
            st["pending"] = None
            await _cancel_find(ctx, pend.get("venue"))
            return True
        st["pending"] = None
        return False
    from . import wa_brain as _WB
    if not payload and kind in _WB.PARKABLE:   # Sasha 178 · PARK AND SWITCH
        sm = _WB.START.match(body or "")
        if sm:
            out.text(await _WB.park(ctx, pend))
            await _WB.start_another(ctx, sm["rest"])
            return True
        if _WB.PARK.search(body or ""):
            out.text(await _WB.park(ctx, pend))
            return True
    if kind == "ladder":   # Sasha 195 · the ladder's choice → acted on at once (the choice IS the yes; nothing read out again)
        opts = pend.get("options") or {}
        route = payload.split(":", 2)[2] if payload.startswith(f"lad:{pend['nonce']}:") else None
        if route is None:
            t = (body or "").lower()
            # Sasha 254 · the rules' one question's own answers, typed ("Handle it", "a prefilled form") — found by the gate: the
            # typed answer matched nothing, the question was dropped and the message went elsewhere
            named = next((r for title, r in (opts.items() if isinstance(opts, dict) else []) if title and title.lower() in t), None)
            route = (named or ("form" if re.search(r"\bhandle\b", t) and "form" in opts.values() else None) or
                     ("page" if re.search(r"\b(prefilled|pre-filled)\b", t) and "page" in opts.values() else None))
        if route is None:
            route = ("no" if re.search(r"\b(no|nope|not now|cancel)\b", t) else "email" if "email" in t else
                     "call" if re.search(r"\bcall\b", t) else "page" if re.search(r"\b(now|page|send|link)\b", t) else
                     next((r for r in opts.values() if r != "no"), None) if re.search(r"\b(yes|ok|okay|sure|go ahead|book it|please)\b", t) else None)
        if route is None or (route != "no" and route not in opts.values()):
            st["pending"] = None
            return False
        st["pending"] = None
        try:   # the same 15-minute window as every yes: a late choice places nothing
            if route != "no" and ctx["now"] - datetime.fromisoformat(pend["at"]) > APPROVAL_WINDOW:
                out.text("That question has expired (15 minutes) — nothing was booked. Ask me again.")
                return True
        except (KeyError, ValueError):
            pass
        if route == "no":
            out.text("OK — nothing was sent.")
            return True
        mark = len(out.items)
        await _prepare_or_ask(ctx, {**(pend.get("saved") or {}), "ladder_route": route})
        p2 = st.get("pending") or {}
        if route in ("form", "email", "call") and p2.get("kind") == "confirm":
            del out.items[mark:]
            await _approve(ctx, p2, {"how": "button"})
            if route == "email":
                v = plain_venue(p2.get("venue"))
                out.items = [(it[0], f"Done — I've emailed {v}. I'll update you as soon as I hear back.", *it[2:]) if it[0] == "text" and it[1] == DONE_ASKED else it
                             for it in out.items]
        return True
    if kind == "city_q":
        if await _WB.city_answer(ctx, pend, body, payload):
            return True
        st["pending"] = None
        return False
    if kind in ("trip_where", "trip_added", "contact_name", "demo_reset", "gate"):   # Sasha 167 · wa_brain's own questions
        from . import wa_brain as WB
        if await WB.answer(ctx, pend, body, payload):
            return True
        if kind != "trip_added":   # an added place stays bookable ("book it at 8") across other questions
            st["pending"] = None
        return False
    # Sasha 161 · STALE: after a greeting or a gap, ASK whether to continue — never resume mid-question
    if pend.get("resume_asked") and not payload:
        if RESUME.fullmatch(body or ""):
            pend.pop("resume_asked", None)
            pend["at"] = ctx["now"].isoformat()
            if kind == "need":
                await _prepare_or_ask(ctx, pend)
            else:
                out.text("OK — where were we: " + _open_item(pend))
            return True
        if NO.fullmatch(body or ""):
            st["pending"] = None
            out.text("OK — dropped. What would you like instead?")
            return True
        st["pending"] = None
        return False   # anything else is a new request: it starts afresh
    gap = (ctx["now"] - at) > STALE_AFTER if at else False
    if not payload and (GREETING.fullmatch(body or "") or (gap and kind in ("need", "cards", "confirm"))):
        from .handoff import booking_handoff
        if gap and not GREETING.fullmatch(body or "") and booking_handoff(body or "") is not None:
            st["pending"] = None
            return False   # a whole new request after a gap starts afresh
        pend["resume_asked"] = True
        out.text(f"{'Hi! ' if GREETING.fullmatch(body or '') else ''}{_still_want(pend)} Say “yes” to carry on, or tell me what you'd like now.")
        return True
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
        if i is None and not payload:
            # Sasha 167 · a WHOLE new request (a kind of place AND a place, said plainly) is a new search — never folded into
            # these cards as a refinement (live: "romantic booking for two at a restaurant in Hoi An, October 27 at 09:00"
            # was searched as "romantic booking two October restaurant", and its 09:00 never asked about)
            from . import wa_brain as WB
            nh = HO.booking_handoff(body, [], ctx["now"]) or {}
            nf, nparts = nh.get("booking_find") or {}, (nh.get("reservation_draft") or {}).get("parts") or {}
            # its own place AND its own day/time or party — "Italian in Malasaña" alone stays a refinement (day and party kept)
            old = pend.get("find") or {}
            ow, nw = _fold(old.get("where") or ""), _fold(nf.get("where") or "")
            # another CITY (Hoi An after Hanoi), never a neighbourhood of the same one ("Malasaña" → "Malasaña, Madrid" after Madrid)
            other_place = bool(nw) and bool(ow) and ow.split(",")[-1].strip() not in nw and nw.split(",")[0].strip() not in ow
            if nf.get("where") and (nf.get("open_at") or nparts.get("when") or nparts.get("how_many") or WB._ORD_DAY.search(body or "")
                                    or other_place) \
                    and WB.sasha_clear(body, [], ctx["now"]):   # Sasha 169/174 · its own day, place or kind: a new search
                st["pending"] = None
                return False
        if i is None:
            # Sasha 104 · while the cards show, anything that is not a pick is a REFINEMENT of this search: the area,
            # day, time and party are kept unless the message changes them; the kind of place is replaced; every
            # quality asked for is kept. A plain yes/no/thanks gets the question again.
            merged = refine(pend, body, ctx["now"])
            if merged is None and not payload:
                # Sasha 156 · a whole new search ("restaurants in Lisbon tonight") is a NEW search, never "Which one?" again
                from .handoff import booking_handoff
                if ((booking_handoff(body) or {}).get("booking_find") or {}).get("where"):
                    st["pending"] = None
                    return False
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
        got = engine_check_answer(pend, body, now)
        if got is None:
            return False
        if got is False:
            st["pending"] = None
            return False
        line, st["pending"] = got
        out.text(line)
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
        if payload.startswith("yes:") or YS.is_yes(body):   # Sasha 269 · a question left from before 269: Sasha's own R5 call is gone
            st["pending"] = None                              # (a call is the act's — venue.call_again); nothing is prepared or dialled
            from app.agent import voice as V
            out.text(V.NO_CALL_OPEN)
            return True
        return False
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
    if pend["kind"] == "trip_where":   # Sasha 167
        return payload.startswith(f"where:{pend['nonce']}:")
    if pend["kind"] == "booked":   # Sasha 171 · the Cancel under a confirmation
        return payload == f"cxl:{pend['nonce']}"
    if pend["kind"] == "gate":   # Sasha 167
        return payload.split(":", 1)[-1] == pend["nonce"] and payload.split(":", 1)[0] in ("am", "pm", "tripadd", "tripkeep")
    if pend["kind"] == "ladder":   # Sasha 195
        return payload.startswith(f"lad:{pend['nonce']}:")
    if pend["kind"] == "city_q":   # Sasha 178
        return payload in (f"oneoff:{pend['nonce']}", f"tripq:{pend['nonce']}")
    if pend["kind"] == "demo_reset":
        return payload in (f"yes:{pend['nonce']}", f"no:{pend['nonce']}")
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
    # Sasha 173 · live: "please book the first one" (5 words) became a NEW search ("book first restaurants in Hanoi"). The
    # ways a pick is said around the number don't count: please, book, pick, choose, let's go with, I'll take, can you…
    core = re.sub(r"\b(please|pls|plz|ok(?:ay)?|yes|yeah|so|then|thanks|thank you|can you|could you|would you|i'?d like|i want|"
                  r"i'?ll (?:take|have|go with)|let'?s (?:go (?:with|for)|do|book|have)|go (?:with|for)|book|reserve|pick|choose|"
                  r"select|take|make it|that|me|us|it|for|(?:the|a) one)\b", " ", t)
    for w in re.findall(r"[a-z0-9]+", core):   # "the one by the river" is a description, not "one"
        if w in _ORDINAL and _ORDINAL[w] < len(pend["cards"]) and (len(t.split()) <= 4 or len(core.split()) <= 3):
            return _ORDINAL[w]
    words = [w for w in re.findall(r"[a-z0-9]+", core) if len(w) > 2 and w not in ("the", "one", "that", "please")]
    hits = [i for i, c in enumerate(pend["cards"]) if words and all(w in _fold(c.get("name") or "") for w in words)]
    if len(hits) == 1:
        return hits[0]
    return described(pend["cards"], t)


#: Sasha 169 · a card picked by what it's LIKE, said aloud: "the one by the river", "the one in the old town" — read against
#: each card's own name, address and kind (never a guess: one card must match, else the question is asked again)
_DESCRIBED = {"river": r"river|riverside|bach dang|thu bon|an hoi|bo song|waterfront|quay|ben",
              "beach": r"beach|bien|bai|seaside|an bang|cua dai|my khe|playa",
              "old town": r"old town|old quarter|pho co|minh an|tran phu|nguyen thai hoc|le loi|hoan kiem|casco",
              "market": r"market|cho|mercado", "rooftop": r"rooftop|sky|terrace|azotea", "garden": r"garden|vuon|jardin",
              "hotel": r"hotel|resort|khach san"}


def described(cards: list, t: str) -> Optional[int]:
    if not re.search(r"\b(?:by|near|on|in|at|with|next to|close to|beside)\b", t):
        return None
    keys = [k for k in _DESCRIBED if re.search(rf"\b{k}\b", t)]
    if not keys:
        return None
    hits = [i for i, c in enumerate(cards) if all(re.search(rf"\b(?:{_DESCRIBED[k]})\b", _fold(" ".join(str(c.get(x) or "") for x in ("name", "address", "type"))))
                                                  for k in keys)]   # whole words: "bean hoi" is not "an hoi"
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
    if (pend.get("find") or {}).get("trip"):   # Sasha 167 (3) · picked from a trip search: on the trip, on its day — not booked
        from . import wa_brain as WB
        await WB.add_to_trip(ctx, pend, card)
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
                                  "place_id": card["place_id"],
                                  # Sasha 187 · the listing's type rides along ("Spanish Restaurant"): a restaurant named by its name is real
                                  "asked_for": " ".join(x for x in (f.get("what"), card.get("type")) if x)[:200]})
    if status != 200:
        ctx["st"]["pending"] = None
        out.text(f"I couldn't read how {card.get('name') or 'they'} take bookings — {refusal_words(read, status)}.")
        return
    venue = (read.get("listing") or {}).get("name") or card.get("name") or read.get("venue")
    if "(TEST stand-in)" in str(read.get("venue") or ""):   # Sasha 169 · the demo stand-in says so, always
        venue = read["venue"]
    rungs = {r["rung"]: r for r in read.get("rungs") or [] if r.get("available")}
    if not any(k in rungs for k in ("form", "link", "own_page", "phone", "email")):   # Sasha 135 · Sasha 246 · their own page too · an email-only venue has a route (Sasha 130)
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
                                                                          "venue": plain_venue(rd.get("venue"))[:120],   # Sasha 187 · the name he picked, never the site's legal name
                                                                          **({"plan_line": plan} if plan else {}),
                                                                          **({"nights": int(nights)} if nights else {})})
    if status != 200:
        return False
    ctx["st"]["pending"] = {"kind": "link", "at": ctx["now"].isoformat(), "link_id": j["link_id"], "venue": rd["venue"], "when": at, **keep}
    await _outcome(ctx["account"], {**keep, "link_id": j["link_id"], "venue": rd["venue"], "read": rd}, "page", status="page_link", j=j)   # Sasha 247 · their page, sent
    if nights:
        ctx["out"].text(hotel_link_text(rd["venue"], j))
        return True
    from . import slot_link as SL   # Sasha 163 · the one platform message
    dt = datetime.fromisoformat(at)
    ctx["out"].text(SL.platform_message(rd["venue"], j.get("platform") or "their booking page", dt.date(), dt.time(),
                                        reservation["how_many"]["count"], bool(j.get("slot_filled")), j["url"]))
    return True


def hotel_link_text(venue: str, j: dict) -> str:
    """Sasha 138 · a hotel's own booking engine, the stay in its link: one tap. Shared with the brain (Sasha 253, G8)."""
    lines = (j.get("read_back") or {}).get("lines") or []
    return (f"One tap: {venue}'s own booking engine ({j.get('platform') or 'their booking page'}).\n"
            + "\n".join("• " + ln for ln in lines) + f"\n{j['url']}")


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


OWN_PAGE = "their own booking page"   # Sasha 246 · rung 2's "platform" name: the venue's own site (ladder.own_page)


def ladder_of(rd: dict, reservation: dict, now, account: Optional[str] = None) -> Optional[dict]:
    """Sasha 254 · no longer a decider: the booking rules' ONE question (R2) when they ask it, from agapi.booking_decide (the old
    flow's and the web card's shape: {"line", "options": [(title, route)]}), else None. decide.ladder is retired."""
    from agapi import booking_decide as BD
    return BD.legacy_ladder(rd, reservation, now, account)


def route_line_of(rd: dict, dv) -> str:
    """Sasha 254 · the decision's one plain line = the booking rules' say_text + the take-over (agapi.booking_decide.say), the same
    words on every surface. decide.line is retired."""
    return dv.reason


def plain_venue(name: Optional[str]) -> str:
    """Sasha 171 · the venue as the guest knows it: the demo's stand-in mark is said once, in the read-back, not in every line."""
    return (name or "").replace(" (TEST stand-in)", "")


def decision_of(rd: dict, prefer: Optional[str] = None, at: Optional[str] = None, now=None, account: Optional[str] = None):
    """Sasha 254 · no longer a decider: the booking rules' Decision (agapi.booking_decide.legacy_decision) in the old flow's shape
    (.route, .reason, .then, .alternatives). decide.decide is retired; the founder-demo's own channel choices (Sasha 187/193) went
    with it — the rules decide for every account."""
    from agapi import booking_decide as BD
    return BD.legacy_decision(rd, prefer, at, now, account)


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
        day = plain_day(body, ctx["now"]) or day or draft.get("day")   # Sasha 148 · the day given earlier, kept
        from . import wa_brain as WB
        hhmm = _time(body.lower()) or HO.context_time(body) or HO.plain_time(body) or WB.spoken_time(body)   # Sasha 169 · "10 in the morning"
        if (d.get("how_many") or {}).get("count") and not draft.get("how_many"):   # "… for 2" said with the time: kept
            draft["how_many"] = d["how_many"]
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
        if need == "when" and pend["draft"].get("day"):   # Sasha 148 · only the time is missing: ask only for it
            out.text(f"What time on {SN.day_words(pend['draft']['day'])}?")
        else:
            out.text(_NEED_Q[need])
        return
    status, cj = await api(ctx["account"], "GET", "/api/booking/contact")
    contact = cj.get("contact") if status == 200 else None
    if not contact:
        from . import wa_brain as WB   # Sasha 167 (5) · asked here, then straight on with this booking
        await WB.ask_contact(ctx, {**pend})
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
    lr = pend.get("ladder_route")
    dv = decision_of(rd, {"form": "form", "email": "email", "page": "one_tap", "call": "call"}.get(lr) or pend.get("prefer"),
                     (reservation.get("when") or {}).get("at"), ctx["now"], ctx.get("account"))
    if not d.get("nights") and not lr:   # Sasha 195 · THE LADDER'S WORDS, asked once
        lad = ladder_of(rd, reservation, ctx["now"], ctx.get("account"))
        if lad:
            nonce = uuid.uuid4().hex[:6]
            out.ask(lad["line"], [(t, f"lad:{nonce}:{r}") for t, r in lad["options"]])
            st["pending"] = {"kind": "ladder", "at": ctx["now"].isoformat(), "nonce": nonce, "options": {t: r for t, r in lad["options"]},
                             "saved": {k: pend[k] for k in ("read", "draft", "invite_code", "find", "venue") if k in pend}}
            return
    order = [r for r in [dv.route] + dv.alternatives if r]
    log.info("[guest_whatsapp] route %s: %s", dv.route, dv.reason)   # Sasha 158 · the reasoning is the ops console's
    # Sasha 161 · the route in ONE plain line, asked once (the read-back stays in the record and the logs)
    ctx["route_line"] = route_line_of(rd, dv) if not d.get("nights") else None   # a hotel room keeps its own request sentence
    if dv.route == "one_tap" and not lr:   # their page is sent next (no yes card): the line goes first, on its own
        if not _founder_demo(ctx.get("account")):
            out.text(route_line_of(rd, dv))
        elif any(f.get("kind") == "challenge" for f in rd.get("facts") or []):   # Sasha 187 · the 175 flow: one message (+ the CAPTCHA beat)
            out.text("Their page asks you to prove you're human — I've sent it to your phone.")
    if not dv.route:
        ctx["route_line"] = route_line_of(rd, dv)
        st["pending"] = None
        out.text(ctx["route_line"])
        return
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
                await _ask_yes(ctx, "form", j["form_id"], j["read_back"], SN.confirm_sentence(reservation, rd["venue"]), rd["venue"],
                               extra={"summary": summary(reservation), "trip_item_id": j.get("trip_item_id"), **keep})   # Sasha 247 · the ledger's key
                return
            if j.get("rule") == "form_challenge" and "(TEST stand-in)" in str(rd.get("venue") or ""):
                # Sasha 172 · the demo's CAPTCHA (our own test page): Sasha fills everything else, the guest ticks it on the phone
                s2, j2 = await api(ctx["account"], "POST", "/api/booking/forms", {"read_id": rd["read_id"], "reservation": res_form, "handover": True})
                if s2 == 200:
                    # Sasha 173 · the founder's words: conversational, not technical
                    ctx["route_line"] = "Stand by — a human is required for this one. A CAPTCHA will appear on your phone. Shall I go ahead?"
                    await _ask_yes(ctx, "handover", j2["form_id"], j2["read_back"], ctx["route_line"], rd["venue"],
                                   extra={"summary": summary(reservation), **keep})
                    return
                j, status = j2, s2
            why = refusal_words(j, status)
            log.warning("[guest_whatsapp] form rung refused (%s: %s); trying the next route", status, j.get("rule"))
        if route == "one_tap" and ("link" in rungs or "own_page" in rungs or ("form" in rungs and lr == "page") or ("form" in rungs and _founder_demo(ctx.get("account"))
                                                          and "(TEST stand-in)" not in str(rd.get("venue") or ""))) \
                and reservation["when"]["mode"] == "at":   # Sasha 187 · or their own booking page, on the founder's phone
            from . import proactive as PR
            plan = dv.then if dv.route == "one_tap" and PR.tap_escalation_on() and not _founder_demo(ctx.get("account")) and not lr else None
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
                    sentence = room_email_sentence(rd["venue"], reservation["how_many"]["count"], at[:10], int(d["nights"]))
                await _ask_yes(ctx, "email", j["email_id"], j["read_back"], sentence, rd["venue"],
                               extra={"summary": summary(reservation), "trip_item_id": j.get("trip_item_id"), **keep})   # Sasha 247 · the ledger's key
                return
            why = refusal_words(j, status)
            log.info("[guest_whatsapp] email refused (%s); trying the next route", status)
        elif route == "email" and "email" in rungs:
            # Sasha 170 · no slot to book (a tattoo, custom work): their email asks for a date and a quote — as the web does
            from . import guest_receipt as GR, ladder_routes as LR
            mine = await GR.address_of(ctx["account"]) if LR.LADDER_STORE is not None else None
            day = d.get("day") or ((reservation.get("when") or {}).get("at") or "")[:10]
            want = d.get("quote_what") or (d.get("what") or {}).get("activity")
            status, j = await api(ctx["account"], "POST", "/api/booking/emails", quote_email(rd["read_id"], contact["name"], mine, want, day))
            if status == 200:
                sentence = quote_sentence(rd["venue"], day)
                await _ask_yes(ctx, "email", j["email_id"], j["read_back"], sentence, rd["venue"],
                               extra={"summary": "", "trip_item_id": j.get("trip_item_id"), **keep})   # Sasha 247 · the ledger's key
                return
            why = refusal_words(j, status)
    st["pending"] = None
    said = f"I can't book {rd['venue']} from here right now" + (f" — {why}" if why else "")
    out.text(said + ("" if said.endswith(("?", ".")) else ".") + " Nothing was sent.")


def room_email_sentence(venue: str, count: int, day: str, n: int) -> str:
    """Sasha 135 · a hotel: a REQUEST for a room, said as one. Shared with the brain (Sasha 253, G8)."""
    return (f"Email {venue} to ask for a room for {count}, {SN.day_words(day)} for {n} night{'s' if n != 1 else ''}? "
            f"It's a request — nothing is booked until they reply.")


def quote_email(read_id: str, name: str, mine: Optional[str], want: Optional[str], day: Optional[str]) -> dict:
    """Sasha 170 · no slot to book (a tattoo, custom work, "whenever they have space"): the email asks for a date and a quote —
    the body of POST /api/booking/emails. Shared with the brain (Sasha 253, G7)."""
    want = (want or "an appointment").strip()
    return {"read_id": read_id, "name": name, "email": mine or "",
            "quote": {"what": want if len(want.split()) >= 2 else f"{want} — please tell me what you can offer",
                      "dates": SN.day_words(day) if day else ""}}


def quote_sentence(venue: str, day: Optional[str]) -> str:
    return f"I'll send {venue} your request and ask for a date and a quote{' for ' + SN.day_words(day) if day else ''}. Shall I?"


_BULLET = re.compile(r"^[·•]\s*")
#: Sasha 158 · the read-back's machinery lines (addresses, copies, where replies go) stay in the record the yes binds to,
#: and in the ops console; the guest sees what will be SAID to the venue, and any step their yes also covers
_MACHINERY = re.compile(r"^(?:I'll email .+ at .+ from |You're copied privately|Their reply comes to me|Shall I send it\?|Subject: |"
                        r"I'll send the booking form on |I'll write in English)", re.I)


def guest_lines(rung: str, lines: list) -> list:
    out = [ln for ln in lines if not _MACHINERY.match(_BULLET.sub("", str(ln)).strip())]
    return out or list(lines)


async def _ask_yes(ctx: dict, rung: str, rid: str, read_back: dict, sentence: str, venue: str, kind: str = "confirm",
                   extra: Optional[dict] = None) -> None:
    out = ctx["out"]
    sha = read_back["sha256"]
    if ctx.get("route_line") and kind == "confirm":   # Sasha 161 · one plain line + what's booked; no script in the chat
        sentence = f"{ctx['route_line']}\n{(extra or {}).get('summary') or ''}".strip()
    else:
        out.text("What I'll " + ("say" if rung == "call" else "send") + ":\n" +
                 "\n".join("• " + _BULLET.sub("", ln) for ln in guest_lines(rung, read_back["lines"])))   # Sasha 117 · one bullet
    if kind == "confirm" and "(TEST stand-in)" not in (venue or "") and _founder_demo(ctx.get("account")) \
            and "Sasha Test Venue" not in (venue or ""):   # Sasha 186 · said plainly which it is: a REAL booking
        sentence = f"✅ Real booking: {venue} itself gets this — it's not a test.\n{sentence}"
    if kind == "confirm" and "(TEST stand-in)" in (venue or ""):   # Sasha 169 · the stand-in (still underneath: nothing changes)
        # Sasha 220 · the founder's call: the stand-in note is no longer said — only the place's own name, without its tag
        sentence = sentence.replace(" (TEST stand-in)", "")
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


async def _outcome(account: str, pend: dict, rung: str, status: Optional[str] = None, error: Optional[str] = None,
                   j: Optional[dict] = None, reference: Optional[str] = None) -> None:
    """Sasha 247 · CR 87's gap: the older WhatsApp-guest flow records each booking in the outcomes ledger AT THE MOMENT IT'S SENT —
    the same rung/channel mapping and key (the reservation's own id) as the agent's book_venue. Never the person's details; awaited
    in the turn; a ledger that doesn't answer never stops the booking."""
    try:
        from agapi import s2_outcomes as OC
        try:   # asked_at = when the person was asked (the read-back / question they said yes to), never the send — CR: a median of 0 s
            asked = datetime.fromisoformat(str(pend["at"])) if pend.get("at") else None
        except ValueError:
            asked = None
        held = {"rung": rung, "id": pend.get("id") or pend.get("link_id"), "trip_item_id": pend.get("trip_item_id") or (j or {}).get("trip_item_id"),
                "sector": ((pend.get("draft") or {}).get("what") or {}).get("category"), "at": asked or NOW()}
        await OC.booked(account, held, plain_venue(pend.get("venue") or ""), (pend.get("read") or {}).get("city"),
                        result=None if error else {"status": status, **({"reference": reference} if reference else {})}, error=error)
    except Exception as e:
        log.warning("[guest_whatsapp] outcome not recorded: %s", type(e).__name__)


async def _approve(ctx: dict, pend: dict, how: dict) -> None:
    out, account, venue = ctx["out"], ctx["account"], pend["venue"]
    if pend["rung"] == "form":
        status, j = await api(account, "POST", f"/api/booking/forms/{pend['id']}/send", {"read_back_sha256": pend["sha"], "approval": how}, timeout=120)
        if status != 200:
            out.text(f"❌ Not sent to {venue}: {refusal_words(j, status)}.")
            await _outcome(account, pend, "form", error=refusal_words(j, status), j=j)   # Sasha 247
            return
        # Sasha 117 · the send is "sent"; what the venue's page SAID is the reading — "confirmed" was never the status
        result = (j.get("reading") or {}).get("result") if j.get("status") == "sent" else None
        await _outcome(account, pend, "form", status="confirmed" if result == "confirmed" else "requested", j=j,   # Sasha 247
                       reference=j.get("booking_reference") if result == "confirmed" else None)
        ref = f" Their reference: {j['booking_reference']}." if j.get("booking_reference") and result == "confirmed" else ""
        shown = plain_venue(venue)   # Sasha 171 · the stand-in was said once, before the yes — not again
        out.text({"confirmed": f"✅ Booked: {shown}, {pend.get('summary', '')}.{ref}",
                  "proposed": f"⚠ Not confirmed yet: {venue}'s page offers something different — read it below.",
                  "declined": f"❌ They said no: {venue}'s page turned it down."}.get(result) or
                 (DONE_ASKED if j.get("status") == "sent"   # Sasha 158 · one sentence after
                  else f"⚠ Not confirmed yet: {j.get('say') or 'their site did not answer clearly'}"))
        if j.get("their_page"):   # Sasha 171 · their words, without a raw link: cancelling is the Cancel button below
            words = re.sub(r"\s*(?:Para cancelar|To cancel|Cancel)[^:]*:\s*https?://\S+", "", str(j["their_page"]), flags=re.I)
            words = re.sub(r"https?://\S+", "", words).strip()
            if words:
                out.text(f"Their page said: “{words[:500]}”")
        note = _receipt_note(venue, j.get("status") == "sent")
        if result == "confirmed":
            from . import wa_brain as WB
            at = ((pend.get("draft") or {}).get("when") or {}).get("at") or ""
            where = await WB.trip_day_words(account, at[:10], shown)
            emailed = note.strip() == "Your receipt is in your email."
            nonce = secrets.token_hex(3)
            out.ask(f"{where} — receipt sent to your email." if emailed else f"{where}.",
                    [("Cancel", f"cxl:{nonce}")])
            ctx["st"]["pending"] = {"kind": "booked", "at": ctx["now"].isoformat(), "nonce": nonce, "venue": shown}
        elif note:   # Sasha 147 · a refused send has no receipt
            out.text(note.strip())
        if result == "confirmed" and venue == "Sasha Test Venue" and os.getenv("SASHA_TEST_VENUE_DEPOSIT", "") == "1":
            await _test_deposit(ctx)   # Sasha 131 (4) · one touch, on their page — a TEST payment
        return
    if pend["rung"] == "handover":   # Sasha 172 · filled in the cloud browser; the guest ticks the CAPTCHA and presses, on the phone
        status, j = await api(account, "POST", f"/api/booking/forms/{pend['id']}/handover", {}, timeout=120)
        if status != 200:
            out.text(f"❌ I couldn't open {plain_venue(venue)}'s page for you: {j.get('say') or refusal_words(j, status)}. Nothing was sent.")
            await _outcome(account, pend, "handover", error=j.get("say") or refusal_words(j, status), j=j)   # Sasha 247
            return
        await _outcome(account, pend, "handover", status="tap_to_finish", j=j)   # Sasha 247
        sent = (j.get("phone") or {}).get("sent")
        out.text("📲 It's on your phone — tick the box, then press Reservar. I'll confirm here."
                 if sent else f"Open this, tick the box, then press Reservar: {j.get('view_url')}")
        return
    if pend["rung"] == "call_email":   # Sasha 131 · URGENT: both on the one yes — the email first (it can't be refused by a ring)
        s2, ej = await api(account, "POST", f"/api/booking/emails/{pend['email_id']}/send", {"read_back_sha256": pend["email_sha"], "approval": how}, timeout=60)
        out.text(f"✉️ Emailed {venue}." if s2 == 200 and ej.get("status") == "sent" else f"❌ The email to {venue} wasn't sent: {ej.get('say') or refusal_words(ej, s2)}.")
        pend = {**pend, "rung": "call", "sha": pend["call_sha"]}
    if pend["rung"] == "email":   # Sasha 130 · the email route: sent is "requested", never "booked"
        status, j = await api(account, "POST", f"/api/booking/emails/{pend['id']}/send", {"read_back_sha256": pend["sha"], "approval": how}, timeout=60)
        if status != 200 or j.get("status") != "sent":
            out.text(f"❌ Not sent to {venue}: {j.get('say') or refusal_words(j, status)}.")
            await _outcome(account, pend, "email", error=j.get("say") or refusal_words(j, status), j=j)   # Sasha 247
            return
        await _outcome(account, pend, "email", status="requested", j=j)   # Sasha 247
        out.text(DONE_ASKED)   # Sasha 158 · one sentence after; the itinerary says "Requested — waiting for <venue>"
        return
    status, j = await api(account, "POST", f"/api/booking/calls/{pend['id']}/place", {"read_back_sha256": pend["sha"], "approval": how}, timeout=120)
    if status != 200:
        out.text(f"❌ Not called: {refusal_words(j, status)}. Nothing was dialled.")
        await _outcome(account, pend, "call", error=refusal_words(j, status), j=j)   # Sasha 247
        return
    await _outcome(account, pend, "call", status=j.get("status") if j.get("status") in ("scheduled", "placed") else
                   ("placed" if j.get("status") == "uncertain" else None), error=None if j.get("status") in ("scheduled", "placed", "uncertain")
                   else (j.get("why") or "not placed"), j=j)   # Sasha 247
    if j.get("status") == "scheduled":   # Sasha 108 · the venue's own name, never the search words
        at = str(j.get("scheduled_for") or "")[11:16]
        out.text(f"{venue} is closed right now, so I'll call them at {at} — your yes covers that call.")
        return
    if pend.get("invite_code") and pend.get("trip_item_id"):   # S-80 · the invitation follows the inviter's booking
        from . import invitations as IV
        await IV.STORE.update(pend["invite_code"], trip_item_id=pend["trip_item_id"])
    out.text(f"📞 Calling {venue} now — I'll tell you what they say." if j.get("status") in ("placed", "uncertain") else f"❌ I couldn't call {venue}: {j.get('why') or 'not placed'}.")
    if j.get("status") in ("placed", "uncertain"):
        _spawn(watch_call(ctx["ch"], ctx["frm"], account, pend["id"], venue, "book", pend.get("summary", "")))


DONE_ASKED = "Done — I've asked them and I'll confirm here as soon as they reply."


def _receipt_note(venue: Optional[str] = None, sent: bool = True) -> str:
    """The receipt line, only when it is true (Sasha 147): nothing sent → no receipt; our own test venue → none is emailed."""
    from .ladder import emails_ready
    from . import guest_receipt as GR
    if not sent:
        return ""
    if GR.test_reason(venue):
        return " No receipt is emailed: this was our own test venue."
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


# Sasha 269 · offer_escalation (the R5 question's sender) DELETED with offer_no_reply_call — R5 is the act's (venue.call_again).


_TAPPED: set = set()


async def tap_to_pay(account: Optional[str], amount: str, what: str, url: str) -> str:
    """Sasha 161 · DESKTOP BOOKS, PHONE CONFIRMS: a payment started on the web → ONE WhatsApp to the account's phone,
    "Tap to pay €X for <what>", opening Stripe's (TEST) page, where Apple Pay works. Stripe's own checkout links only."""
    from urllib.parse import urlsplit
    if (urlsplit(url or "").hostname or "") != "checkout.stripe.com":
        return "not sent: not a Stripe checkout link"
    if url in _TAPPED:
        return "not sent: already sent"
    what = plain_venue(what)   # Sasha 172 · the stand-in mark was said once, before the yes (Sasha 182 · it named an unset variable: every tap to pay crashed)
    if not account or STORE is None:
        return "not sent: no account"
    ch = await STORE.channel_of_account(account)
    if not ch:
        return "not sent: no WhatsApp linked to this account"
    tag = "" if "TEST" in what else " · TEST"   # Sasha 210 · a small TEST tag on the checkout message, never a spoken disclaimer
    out = await _tell(ch, f"💳 Tap to pay {amount} for {what}{tag}: {url}",
                      ("tap_to_pay", {1: what.split(",")[0], 2: what, 3: amount, 4: url}))
    if "sent" in out and "not" not in out:
        _TAPPED.add(url)
    return out


async def tap_platform(account: Optional[str], text: str, url: str, link_id: Optional[str] = None, venue: Optional[str] = None,
                       when: Optional[str] = None) -> str:
    """Sasha 163 · a platform venue booked from the laptop: the ONE message, on the guest's phone. Only a URL Sasha built
    for a booking platform's venue page (slot_link) — Sasha never fetched it; the guest's own browser opens it."""
    from .venue_read import platform_of
    if not platform_of(url or ""):
        return "not sent: not a booking platform's page"
    if url in _TAPPED:
        return "not sent: already sent"
    if not account or STORE is None:
        return "not sent: no account"
    ch = await STORE.channel_of_account(account)
    if not ch:
        return "not sent: no WhatsApp linked to this account"
    out = await _tell(ch, text)
    if "sent" in out and "not" not in out:
        _TAPPED.add(url)
        if link_id:   # Sasha 175 · the guest's "BOOKED" on WhatsApp now belongs to THIS link (it went nowhere: no pending link)
            st = await STORE.get_state(ch["wa_id_sha256"])
            st["pending"] = {"kind": "link", "at": NOW().isoformat(), "link_id": link_id, "venue": venue or "", "when": when or ""}
            await STORE.put_state(ch["wa_id_sha256"], st)
            from . import mailbox as MB   # Sasha 175 · and its confirmation email marks it booked on its own (Gmail connected)
            if MB.STORE is not None and await MB.STORE.get_link(account):
                _spawn(MB.watch_after_link(account, link_id))
    return out


async def tap_to_finish(account: Optional[str], venue: str, url: str, what: str = "") -> str:
    """Sasha 158 · TAP TO FINISH: a booking reached a human step (a CAPTCHA, a terms box, a payment, the final Book) — ONE
    WhatsApp message to the phone linked to this account, wherever the booking started, opening the live hand-over, filled
    in. Only our own hand-over links; once per link; inside WhatsApp's 24-hour window (the sandbox has no templates)."""
    from urllib.parse import urlsplit
    from . import form_rung as FR
    u = urlsplit(url or "")
    if (u.hostname or "") != (urlsplit(FR.public_base()).hostname or "") or not u.path.startswith("/api/booking/handover/"):
        return "not sent: not one of our hand-over links"
    if url in _TAPPED:
        return "not sent: already sent"
    if not account or STORE is None:
        return "not sent: no account"
    ch = await STORE.channel_of_account(account)
    if not ch:
        return "not sent: no WhatsApp linked to this account"
    out = await _tell(ch, f"👉 Tap to finish at {venue}: {url}\nEverything's filled in{f' — {what}' if what else ''}. The last tap is yours.",
                      ("tap_to_finish", {1: venue, 2: what or "your booking", 3: url}))
    if "sent" in out and "not" not in out:
        _TAPPED.add(url)
    return out


#: Sasha 162 · CR's Utility templates (Twilio Content API), for OUTSIDE the 24-hour window only: (en, es) ContentSids
TEMPLATES = {"tap_to_finish": ("HX12e6eec86092c1d454b65b2d589c92f2", "HX4bcb4eadb04d342fa07739eb59422459"),
             "tap_to_pay": ("HX93b4206c856d2ec3dea35e3ff6585f35", "HX0d88d7b092003bee468ba0ccee3c135d"),
             "booking_confirmed": ("HXefe783beee3e58392b92afa12ee2fb85", "HX4e70a561daf564d8ada567bc5795e18f"),
             "booking_declined": ("HX1be24941f5128ecb6b1015b9962b91ba", "HXe0caf9bf80181a5bf81633818e0fa9e1"),
             "booking_reminder": ("HX393eb8f7cf23d412f9ae1dc591d20588", "HXcb573c6fb66ef00606343dfa44923085")}


async def _tell(ch: dict, text: str, template: Optional[tuple] = None) -> str:
    """Inside the 24-hour window: the text. Outside it: the approved template (name, variables), when one is given."""
    st = await STORE.get_state(ch["wa_id_sha256"])
    last = st.get("last_inbound_at")
    if not guest_numbers():
        return "not told: WhatsApp for guests is off"
    if not (last and NOW() - last <= SESSION_WINDOW):
        if not template or ch.get("opted_out_at") or not ch.get("number_e164"):
            return "not told: outside the 24-hour window"
        name, variables = template
        sid = TEMPLATES[name][1 if str(ch["number_e164"]).startswith("+34") else 0]
        r = await SENDER.send(sender_for(st), ch["number_e164"], content_sid=sid, variables=variables)
        log.info("[guest_whatsapp] %s template outside the window: %s", name, str(r)[:80])
        return f"{r} (template)" 
    return ", ".join(await deliver(ch, sender_for(st), Out().text(text), last))


def _draft_of(b: dict) -> dict:
    return {"schema": "reservation/1", "flow": "book",
            "what": {"activity": b.get("what") or "a table", "activity_venue_lang": b.get("what") or "a table", "category": b.get("category") or "restaurant"},
            "where": {}, "when": {"mode": "at", "at": f"{b['date']}T{b['time']}"},
            "how_many": {"count": b.get("count") or b.get("party") or 2, "unit": "people"}}


# Sasha 269 (CR 100) · DELETED: auto_call_from_email and offer_no_reply_call (Sasha 130/132's own R5 call after an email nobody answered).
# R5 is the act's: proactive.no_reply_offers → venue_calls.again(act, "R5") → venue.call_again → its call_plan only.


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
        elif settled and v.get("outcome") == "yes" and _receipt_note(venue):
            out.text(_receipt_note(venue).strip())
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
        return ", ".join(await deliver(ch, sender_for(st), out, st.get("last_inbound_at")))
    if nxt and nxt.startswith("scheduled for "):
        out.text(f"I'll call {venue} once more at {nxt[len('scheduled for '):]} — your yes covers it.")
    elif not settled:
        out.text("I've asked them to confirm in writing where I can; anything they send goes onto your booking and receipt.")
    elif reading.outcome == "yes" and _receipt_note(venue):
        out.text(_receipt_note(venue).strip())
    st = await STORE.get_state(ch["wa_id_sha256"])
    return ", ".join(await deliver(ch, sender_for(st), out, st.get("last_inbound_at")))


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
    return ", ".join(await deliver(ch, sender_for(st), out, st.get("last_inbound_at")))


# ── receipts and cancelling ─────────────────────────────────────────────────────────────────────────────────────────

async def _upcoming(account: str, names: bool = True) -> List[dict]:
    """`names=False` (Sasha 141) · the minute-by-minute watchers read status and times only: a phone booking's name is a
    Google listing re-read (an Enterprise Place Details call), so they ask for it only for a message actually sent."""
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
    return await _with_names(account, rows) if names else rows


async def _with_names(account: str, rows: List[dict]) -> List[dict]:
    for r in rows:   # a phone booking's real name is on its receipt (the stored row keeps a marker, Sasha 64)
        if r.get("receipt"):
            s, rc = await api(account, "GET", r["receipt"])
            if s == 200 and (rc.get("venue") or {}).get("name"):
                r["venue"] = rc["venue"]["name"]
    from . import plan_store as PS
    return PS.truthful(rows)   # Sasha 179 · TEST never "Confirmed"


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


_ENGINE_ANSWER = re.compile(r"^\s*(?:(?P<n>[1-9])\s*[:.)-]?\s*)?(?P<a>not\s+filled|filled|wrong(?:\s+page)?|right(?:\s+page)?)\b", re.I)


def engine_check_answer(pend: dict, body: str, now):
    """Sasha 139 · the founder's answer for one hotel engine link ("1 filled / 2 not filled / 3 wrong page"), recorded on the
    engine_check question. Sasha 253 · G15: the ONE place — the WhatsApp word (_answer_pending) and the ops console
    (demo_ops /ops/demo/engine-check) both call it. → None: not an answer; False: nothing left to answer; else (the line, the
    question as it stands now — kind "engine_check_done" once every link is answered)."""
    m = _ENGINE_ANSWER.match(body or "")
    if not m:
        return None
    todo = [h for h in pend["hotels"] if str(h["n"]) not in pend.get("answers", {})]   # str keys: the state is stored as JSON
    h = next((x for x in pend["hotels"] if m["n"] and x["n"] == int(m["n"])), todo[0] if todo else None)
    if h is None:
        return False
    ans = re.sub(r"\s+", " ", m["a"].lower())
    pend.setdefault("answers", {})[str(h["n"])] = {"answer": ans, "said": body, "at": now.isoformat()}
    left = len([x for x in pend["hotels"] if str(x["n"]) not in pend["answers"]])
    line = (f"Noted — {h['name']} ({h['engine']}): {ans}." + (f" {left} to go." if left else   # Sasha 150 · any number of links
            f" That's all {len(pend['hotels'])} — thank you."))
    log.info("[guest_whatsapp] engine check: %s %s → %s", h["name"], h["engine"], ans)
    return line, (pend if left else {**pend, "kind": "engine_check_done"})


async def watch_for_brain(account: str, *, call_id: Optional[str] = None, trip_item_id: Optional[str] = None, venue: str = "",
                          purpose: str = "book", what: str = "") -> str:
    """Sasha 253 · G2 — a result the one brain started (an immediate call placed by book_venue; a written cancellation sent by
    cancel_venue), pushed to the account's WhatsApp when it comes: the SAME watchers as the old flow (watch_call — one message per
    state, the confirmation call followed; watch_cancel — "cancelled" only on their words), started the same way (_spawn).
    Whatever screen the booking was made on, the result reaches the linked phone. Never raises; → what happened, in words."""
    try:
        if STORE is None or not guest_numbers():
            return "not watched: WhatsApp for guests is off"
        ch = await STORE.channel_of_account(account)
        if not ch:
            return "not watched: no WhatsApp linked"
        if ch.get("opted_out_at"):
            return "not watched: they said STOP"
        st = await STORE.get_state(ch["wa_id_sha256"])
        frm = sender_for(st)
        if call_id:
            _spawn(watch_call(ch, frm, account, call_id, venue, purpose, what))
        elif trip_item_id:
            _spawn(watch_cancel(ch, frm, account, trip_item_id, venue))
        else:
            return "not watched: nothing to watch"
        return "watching"
    except Exception as e:
        log.warning("[guest_whatsapp] the brain's result is not watched: %s: %s", type(e).__name__, e)
        return f"not watched: {type(e).__name__}"


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
    """The guest ticked consent v2 (its version and hash prove these exact words were shown) and gave their WhatsApp number.
    Sasha 269 · CR 100 §E: users.link_whatsapp registers it UNVERIFIED and returns a one-time code — NOTHING is sent to it; the
    wa.me link opens their WhatsApp with AgAPI's text ("Kanoe link 123456") ready to send to Kanoe. Verified only when it arrives."""
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
    theirs = re.sub(r"[^\d+]", "", str(body.get("whatsapp") or ""))
    if not re.fullmatch(r"\+[1-9]\d{6,14}", theirs):
        return _refuse(422, "number_invalid", "your WhatsApp number, with its country code (+34 …)")
    from agapi import venue_submit as VS
    got = await VS.link_whatsapp(account, theirs)   # registered UNVERIFIED; nothing is sent to it
    if not got.get("ok"):
        return _refuse(422 if got["error"]["code"] == "invalid_input" else 503, got["error"]["code"], got["error"]["message"])
    if got.get("state") == "verified" or not got.get("code"):
        return {"verified": True, "say": got.get("say")}
    now = NOW()
    try:   # Sasha's own note of whose code it is (the inbound message names the account), the code AgAPI made
        ok = await STORE.put_code({"code": got["code"], "account_id": account, "consent_at": now, "consent_wording_version": c["version"],
                                   "consent_text_sha256": c["sha256"], "created_at": now})
    except StorageUnavailable as e:
        return _refuse(503, e.rule, e.detail)
    if not ok:
        return _refuse(503, "code_unavailable", "no code could be made just now; try again")
    from urllib.parse import quote
    text = str(got.get("text") or f"Kanoe link {got['code']}")
    return {"code": got["code"], "text": text, "expires_at": got.get("expires_at"), "number": number, "sent": False,
            "wa_link": f"https://wa.me/{number.lstrip('+')}?text={quote(text)}", "say": got.get("say"),
            "join": os.getenv("SASHA_WA_SANDBOX_JOIN", "").strip() or None}


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


async def _told_handover_booked(pub: dict) -> None:
    """Sasha 172 · a hand-over the guest finished (ticked, pressed) → "✅ Booked …" and its trip day, on WhatsApp."""
    account = pub.get("account_id")
    if not account or pub.get("state") != "booked":
        return
    ch = await STORE.channel_of_account(account)
    if not ch:
        return
    from . import itinerary_q as IQ, wa_brain as WB
    venue = plain_venue(pub.get("venue"))
    rows = [r for r in await IQ._rows(account) if plain_venue(r.get("venue")) == venue]
    day = (rows[-1].get("date") if rows else "") or ""
    where = await WB.trip_day_words(account, day, venue)
    ref = f", ref {pub['reference']}" if pub.get("reference") else ""
    await _tell(ch, f"✅ Booked: {venue}{ref}.\n{where} — receipt sent to your email.")


try:
    from . import handover as _H
    _H.ON_BOOKED.append(_told_handover_booked)
except Exception as _e:   # the hook never stops the module loading
    log.warning("[guest_whatsapp] hand-over hook not registered: %s", _e)

