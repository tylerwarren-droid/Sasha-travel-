"""S-82 · GMAIL, READ-ONLY (testing mode, "beta, by invitation"): booking confirmations, cancellations and bills found in
the guest's inbox — offered one sentence at a time, never acted on without the guest's yes.

Reading narrowly (§2), enforced here:
  · Never the whole inbox: every sync is ONE Gmail search, always with newer_than:90d, and only booking senders or
    booking words (build_query; no code path lists messages without it — a test holds that).
  · Only matching messages are fetched; NO BODY IS STORED — the message id, a sha256 of the body, and the extracted facts
    (kind, venue, time, party, reference, amount). The guest opens the original in Gmail.
  · Rules first (M-3). The model only when the rules can't AND the message already matched a booking, and only if
    SASHA_MAILBOX_MODEL=1 (off by default until counsel's Limited Use view).
  · The vault guard runs on what is extracted: a card number in an email is never extracted or stored.
  · Each offer is one sentence; its accept is bound to the find's id AND the sentence's hash.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import os
import re
import unicodedata
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from .store import StorageUnavailable

log = logging.getLogger("booking_signer.mailbox")
NOW = lambda: datetime.now(timezone.utc)
SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
GMAIL = "https://gmail.googleapis.com/gmail/v1/users/me"
SYNC_EVERY_S = 6 * 3600
CONSENT = {"v1": ("Sasha will look in your Gmail only for emails about bookings, cancellations and bills from the last 90 days, "
                  "keep only the details she needs (venue, date, reference, amount), and never store your emails. You can "
                  "disconnect at any time.")}
CURRENT = "v1"
PLATFORMS = ("thefork.com", "eltenedor.es", "thefork.es", "fresha.com", "covermanager.com", "zenchef.com", "opentable.com",
             "opentable.es", "booking.com", "resy.com", "sevenrooms.com", "quandoo.com", "restaurantes.com")
PLATFORM_NAMES = {"thefork": "TheFork", "eltenedor": "ElTenedor", "opentable": "OpenTable", "covermanager": "CoverManager",
                  "zenchef": "Zenchef", "resy": "Resy", "sevenrooms": "SevenRooms", "quandoo": "Quandoo", "fresha": "Fresha",
                  "booking.com": "Booking.com", "restaurantes.com": "Restaurantes.com"}
KEYWORDS = ("reserva", "booking", "reservation", "confirmación", "confirmation", "cancelación", "cancellation", "factura",
            "invoice", "receipt", "recibo")


def consent(version: str = CURRENT) -> dict:
    t = CONSENT[version]
    return {"version": version, "text": t, "sha256": hashlib.sha256(t.encode()).hexdigest()}


# ── §2 · the one search ─────────────────────────────────────────────────────────────────────────────────────────────

def build_query(venue_domains: List[str]) -> str:
    """newer_than:90d AND (a booking sender OR a booking word). Always both parts — never the whole inbox."""
    senders = sorted({d.strip().lower() for d in list(venue_domains) + list(PLATFORMS) if d and re.fullmatch(r"[a-z0-9.-]+\.[a-z]{2,}", d.strip().lower())})
    words = " OR ".join(KEYWORDS)
    who = " OR ".join(f"from:{d}" for d in senders)
    return f"newer_than:90d ({who} OR subject:({words}))"


# ── §5.3 · reading one message: rules first ─────────────────────────────────────────────────────────────────────────

_MONTHS = {"enero": 1, "january": 1, "janeiro": 1, "febrero": 2, "february": 2, "fevereiro": 2, "marzo": 3, "march": 3, "março": 3,
           "abril": 4, "april": 4, "mayo": 5, "may": 5, "maio": 5, "junio": 6, "june": 6, "junho": 6, "julio": 7, "july": 7,
           "julho": 7, "agosto": 8, "august": 8, "septiembre": 9, "setiembre": 9, "september": 9, "setembro": 9, "octubre": 10,
           "october": 10, "outubro": 10, "noviembre": 11, "november": 11, "novembro": 11, "diciembre": 12, "december": 12,
           "dezembro": 12, "jan": 1, "feb": 2, "apr": 4, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11,
           "dec": 12, "ene": 1, "abr": 4, "ago": 8, "dic": 12}
_MONTH_RX = "|".join(sorted(_MONTHS, key=len, reverse=True))
_DATE_WORDS = re.compile(rf"\b(\d{{1,2}})\s*(?:de\s+)?({_MONTH_RX})\b\.?(?:\s*(?:de\s+)?(\d{{4}}))?", re.I)
_DATE_WORDS_EN = re.compile(rf"\b({_MONTH_RX})\b\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?(?:,?\s*(\d{{4}}))?", re.I)
_DATE_NUM = re.compile(r"\b(\d{1,2})[/.-](\d{1,2})[/.-](\d{4}|\d{2})\b")
_TIME = re.compile(r"\b([01]?\d|2[0-3])[:.h]([0-5]\d)(?:\s*([ap])\.?m\b\.?)?|\b(\d{1,2})\s*([ap])\.?m\b", re.I)
_PARTY = re.compile(r"\b(\d{1,2})\s*(?:personas|comensales|people|guests|persons|pessoas|pax|adults?|adultos)\b", re.I)
_AMOUNT = re.compile(r"(?:€|\bEUR)\s?(\d+(?:[.,]\d{1,2})?)|(\d+(?:[.,]\d{1,2})?)\s?(?:€|EUR\b)", re.I)
_CONFIRM = re.compile(r"confirmad[ao]|reserva confirmada|est[aá] confirmada|booking (?:is )?confirmed|reservation (?:is )?confirmed|\bis confirmed\b|"
                      r"we look forward|te esperamos|os esperamos|le esperamos|confirmamos|your booking|tu reserva|su reserva (?:est[aá]|queda)", re.I)
_CANCEL = re.compile(r"cancelad[ao]|anulad[ao]|cancellation confirmed|has been cancelled|has been canceled|reserva cancelada", re.I)
_BILL = re.compile(r"\b(factura|invoice|receipt|recibo|ticket de compra)\b", re.I)
_CHANGE = re.compile(r"modificad[ao]|ha cambiado|has been (?:changed|modified)|nueva hora|new time", re.I)


def _when(text: str, now: datetime, tz: str = "Europe/Madrid") -> Optional[str]:
    t = text or ""
    d = None
    m = _DATE_WORDS.search(t)
    if m:
        d = (int(m[1]), _MONTHS[m[2].lower()], int(m[3]) if m[3] else None)
    elif _DATE_WORDS_EN.search(t):
        m = _DATE_WORDS_EN.search(t)
        d = (int(m[2]), _MONTHS[m[1].lower()], int(m[3]) if m[3] else None)
    elif _DATE_NUM.search(t):
        m = _DATE_NUM.search(t)
        y = int(m[3]) + (2000 if len(m[3]) == 2 else 0)
        d = (int(m[1]), int(m[2]), y)
    if not d:
        return None
    day, month, year = d
    year = year or now.astimezone(ZoneInfo(tz)).year
    try:
        dd = date(year, month, day)
    except ValueError:
        return None
    tm = _TIME.search(t[t.find(str(day)):] if str(day) in t else t) or _TIME.search(t)
    hh, mi = (None, None)
    if tm:
        if tm[1]:
            hh, mi = int(tm[1]), int(tm[2])
            if tm[3]:
                hh = hh % 12 + (12 if tm[3].lower() == "p" else 0)
        else:
            hh, mi = int(tm[4]) % 12 + (12 if tm[5].lower() == "p" else 0), 0
    return f"{dd.isoformat()}T{hh:02d}:{mi:02d}" if hh is not None else dd.isoformat()


def _amount(text: str) -> Optional[int]:
    m = _AMOUNT.search(text or "")
    if not m:
        return None
    v = (m[1] or m[2]).replace(",", ".")
    try:
        return round(float(v) * 100)
    except ValueError:
        return None


_NAME = r"([A-ZÁÉÍÓÚÑÜ0-9][^\n,.!?¡¿|:;()\[\]<>\"]{1,60}?)"
_NAME_END = r"(?=\s+(?:est[aá]|is|has|ha|queda|para|for|el|la|on|a las|at \d|de \d|del \d)\b|\s*[-–—,.!?|:;(\n]|\s*$)"
_VENUE_AT = re.compile(rf"\b(?:reserva|reservation|booking|mesa|table|cita|appointment)\s+(?:en|at|in|chez|with|con)\s+(?:el\s+|la\s+|the\s+)?{_NAME}{_NAME_END}", re.I)
_VENUE_DASH = re.compile(rf"(?:confirmad[ao]|confirmed|confirmación de (?:tu |su )?reserva|cancelad[ao]|cancell?ed)\s*[-–—:|]\s*{_NAME}{_NAME_END}", re.I)


def platform_of(sender: str) -> Optional[str]:
    """TheFork, OpenTable, CoverManager … when the email was sent by a booking platform rather than by the venue."""
    s = _fold(sender or "")
    addr = (re.search(r"<([^>]+)>", s) or [None, s])[1]
    dom = addr.rsplit("@", 1)[-1].strip()
    if any(dom == p or dom.endswith("." + p) for p in PLATFORMS):
        key = next((k for k in PLATFORM_NAMES if k in dom), None)
        return PLATFORM_NAMES.get(key) if key else dom
    name = re.sub(r"\s*<.*?>\s*$", "", s).strip().strip('"')
    return next((v for k, v in PLATFORM_NAMES.items() if k in name.replace(" ", "")), None)


#: Sasha 144 · words a sentence puts where a name could go: "cancela tu reserva en cualquier momento" is not a venue
_NOT_A_NAME = re.compile(r"(?:cualquier|todo|toda|todos|cualquiera|nuestr[ao]s?|vuestr[ao]s?|línea|linea|online|any|anytime|"
                         r"every|all|our|the\s+app|la\s+app|el\s+app|nuestra\s+web|la\s+web|tu\s+cuenta|your\s+account)\b", re.I)


def _proper(v: str) -> bool:
    """A venue's name is written as a name: it starts with a capital or a digit ("Casa Lucio", "100 Montaditos"), and it
    isn't one of the phrases a confirmation email's small print puts after "reserva en" — "cualquier momento" (Sasha 144:
    a founder's itinerary item was named that)."""
    return bool(v) and (v[0].isupper() or v[0].isdigit()) and not _NOT_A_NAME.match(v)


def venue_in(subject: str, body: str) -> Optional[str]:
    """The venue's own name, from a platform's email: "Tu reserva en Casa Lucio está confirmada", "Your booking at X …",
    "Reserva confirmada - X". Subject first. None rather than a guess — never the platform's name."""
    for text in (subject or "", (body or "")[:3000]):
        for rx in (_VENUE_AT, _VENUE_DASH):
            for m in rx.finditer(text):
                v = m[1].strip(" -–—'\"")
                if v and platform_of(v) is None and not re.fullmatch(r"\d+|(?:tu|su|your|our)\b.*", v, re.I) and _proper(v):
                    return v
    return None


def read(subject: str, sender: str, body: str, now: datetime) -> Tuple[str, dict, str]:
    """(kind, facts, parsed_by) — by rules. Facts never include a card number, and never the body."""
    from .form_rung import _REF
    from .vault.guard import has_card_number
    text = f"{subject}\n{body}"
    kind = ("cancellation" if _CANCEL.search(text) else "change" if _CHANGE.search(text) else
            "bill" if _BILL.search(subject or "") and _AMOUNT.search(text) else "confirmation" if _CONFIRM.search(text) else "other")
    via = platform_of(sender)
    name = venue_in(subject, body) if via else (re.sub(r"\s*<.*?>\s*$", "", sender or "").strip().strip('"') or None)
    ref = _REF.search(text)
    party = _PARTY.search(text)
    facts = {"venue": name, "at": _when(text, now), "party": int(party[1]) if party else None,
             "reference": ref[1] if ref else None, "amount_minor": _amount(text) if kind in ("bill", "receipt") or "señal" in text.lower() or "deposit" in text.lower() else None,
             "currency": "EUR" if _AMOUNT.search(text) else None,
             "sasha_ref": (re.search(r"\bK-[A-Z0-9]{4}\b", text) or [None])[0], "via": via}
    for k, v in list(facts.items()):
        if isinstance(v, str) and has_card_number(v):   # the vault guard on what is extracted
            facts[k] = None
    return kind, facts, "rules"


# ── §4 · matching ───────────────────────────────────────────────────────────────────────────────────────────────────

def _fold(s: str) -> str:
    return "".join(ch for ch in unicodedata.normalize("NFD", s or "") if unicodedata.category(ch) != "Mn").lower()


def match(facts: dict, rows: List[dict]) -> Tuple[Optional[dict], Optional[str]]:
    """A reference beats a K-reference beats the venue within ±90 min. None → a booking made outside Sasha."""
    if facts.get("reference"):
        hit = next((r for r in rows if r.get("booking_reference") and r["booking_reference"].upper() == facts["reference"].upper()), None)
        if hit:
            return hit, "reference"
    if facts.get("sasha_ref"):
        hit = next((r for r in rows if (r.get("sasha_reference") or "").upper() == facts["sasha_ref"].upper()), None)
        if hit:
            return hit, "sasha_ref"
    if facts.get("venue") and facts.get("at") and "T" in facts["at"]:
        at = datetime.fromisoformat(facts["at"])
        for r in rows:
            if not (r.get("date") and r.get("time")):
                continue
            words = [w for w in re.findall(r"[a-z0-9]+", _fold(facts["venue"])) if len(w) > 2]
            if words and all(w in _fold(r.get("venue") or "") for w in words):
                rt = datetime.fromisoformat(f"{r['date']}T{r['time']}")
                if abs((rt - at).total_seconds()) <= 90 * 60:
                    return r, "venue_and_time"
    return None, None


def upcoming(at: Optional[str], now: datetime, tz: str = "Europe/Madrid") -> bool:
    """A found booking still ahead of the guest (a date alone counts until the day is over). Local time, as _when writes it."""
    if not at:
        return False
    local = now.astimezone(ZoneInfo(tz)).replace(tzinfo=None)
    try:
        return datetime.fromisoformat(at) > local if "T" in at else date.fromisoformat(at[:10]) >= local.date()
    except ValueError:
        return False


def offer(kind: str, facts: dict, row: Optional[dict], now: Optional[datetime] = None) -> Optional[Tuple[str, str]]:
    """(action, the ONE sentence) — or None when there is nothing to offer. A booking already in the past is never offered:
    it stays as a find, quietly, as history."""
    from . import sentences as SN
    venue = (row or {}).get("venue") or facts.get("venue") or "A venue"
    at = facts.get("at") or ""
    when = (f"{SN.day_words(at[:10])} {at[11:16]}".strip() if at else "") or "the date shown"
    party = f" for {facts['party']}" if facts.get("party") else ""
    ref = f" (ref {facts['reference']})" if facts.get("reference") else ""
    if row and kind == "confirmation" and row.get("status") in ("requested", "unclear", "attempting", "pending", "link_sent", "proposed",
                                                                      "guest_booked"):   # Sasha 130 · one-tap: the guest pressed; the venue's email confirms
        return "confirm", f"{venue}'s email confirms {when}{party}{ref}. Mark it confirmed?"
    if row and kind == "cancellation" and row.get("status") not in ("cancelled",):
        return "cancel", f"{venue}'s email says your {when} booking is cancelled. Update it?"
    if row is None and kind == "confirmation" and facts.get("venue") and upcoming(at, now or NOW()):
        via = f" (via {facts['via']})" if facts.get("via") else ""
        return "add", f"Your inbox has a booking at {venue}{via}, {when}{party}. Add it to your itinerary?"
    return None


# ── the store: Memory for tests, Postgres (sql/025) for real ────────────────────────────────────────────────────────

class MemoryMailboxStore:
    def __init__(self) -> None:
        self.links: Dict[str, dict] = {}
        self.finds: Dict[str, dict] = {}
        self.applied: List[tuple] = []

    async def get_link(self, account):
        return dict(self.links[account]) if account in self.links else None

    async def put_link(self, row):
        self.links[row["account_id"]] = dict(row)

    async def set_link(self, account, **kw):
        if account in self.links:
            self.links[account].update(kw)

    async def delete_account_finds(self, account):
        ks = [k for k, f in self.finds.items() if f["account_id"] == account]
        for k in ks:
            del self.finds[k]
        self.links.pop(account, None)
        return len(ks)

    async def seen(self, account, mid):
        return any(f["account_id"] == account and f["gmail_message_id"] == mid for f in self.finds.values())

    async def put_find(self, row):
        self.finds[row["id"]] = dict(row)

    async def get_find(self, account, fid):
        f = self.finds.get(fid)
        return dict(f) if f and f["account_id"] == account else None

    async def list_finds(self, account):
        return [dict(f) for f in self.finds.values() if f["account_id"] == account]

    async def set_find(self, fid, **kw):
        self.finds[fid].update(kw)

    async def all_links(self):
        return [dict(l) for l in self.links.values()]

    async def apply(self, account, action, trip_item_id, facts):
        self.applied.append((account, action, trip_item_id, facts.get("reference")))
        return trip_item_id or "new-item"


class PostgresMailboxStore:
    def __init__(self, base) -> None:
        self._base = base

    async def _run(self, fn):
        try:
            return await self._base._run(fn)
        except StorageUnavailable as e:
            raise e.rehint("025_mailbox.sql") from None

    async def get_link(self, account):
        r = await self._run(lambda c: c.fetchrow("select * from mailbox_links where account_id = $1", uuid.UUID(account)))
        return {**dict(r), "account_id": str(r["account_id"]), "vault_item_id": str(r["vault_item_id"])} if r else None

    async def put_link(self, row):
        await self._run(lambda c: c.execute(
            "insert into mailbox_links (account_id, vault_item_id, consent_at, consent_wording_version, consent_text_sha256) "
            "values ($1,$2,$3,$4,$5) on conflict (account_id) do update set vault_item_id = excluded.vault_item_id, "
            "consent_at = excluded.consent_at, consent_wording_version = excluded.consent_wording_version, "
            "consent_text_sha256 = excluded.consent_text_sha256, needs_reconnect_at = null, told_reconnect_at = null",
            uuid.UUID(row["account_id"]), uuid.UUID(row["vault_item_id"]), row["consent_at"], row["consent_wording_version"],
            row["consent_text_sha256"]))

    async def set_link(self, account, **kw):
        cols = [k for k in kw if k in ("last_sync_at", "history_id", "needs_reconnect_at", "told_reconnect_at")]
        if cols:
            sets = ", ".join(f"{k} = ${i + 2}" for i, k in enumerate(cols))
            await self._run(lambda c: c.execute(f"update mailbox_links set {sets} where account_id = $1", uuid.UUID(account), *[kw[k] for k in cols]))

    async def delete_account_finds(self, account):
        async def go(c):
            async with c.transaction():
                n = await c.execute("delete from mailbox_finds where account_id = $1", uuid.UUID(account))
                await c.execute("delete from mailbox_links where account_id = $1", uuid.UUID(account))
                return int(n.split()[-1])
        return await self._run(go)

    async def seen(self, account, mid):
        return bool(await self._run(lambda c: c.fetchval(
            "select exists (select 1 from mailbox_finds where account_id = $1 and gmail_message_id = $2)", uuid.UUID(account), mid)))

    async def put_find(self, row):
        await self._run(lambda c: c.execute(
            "insert into mailbox_finds (id, account_id, gmail_message_id, body_sha256, kind, facts, parsed_by, trip_item_id, match_basis, "
            "offered_action, offered_sentence, offer_sha256, action_status) values ($1,$2,$3,$4,$5,$6::jsonb,$7,$8,$9,$10,$11,$12,$13) "
            "on conflict do nothing",
            uuid.UUID(row["id"]), uuid.UUID(row["account_id"]), row["gmail_message_id"], row["body_sha256"], row["kind"], row["facts"],
            row["parsed_by"], uuid.UUID(row["trip_item_id"]) if row.get("trip_item_id") else None, row.get("match_basis"),
            row.get("offered_action"), row.get("offered_sentence"), row.get("offer_sha256"), row.get("action_status", "none")))

    @staticmethod
    def _f(r):
        return {**dict(r), "id": str(r["id"]), "account_id": str(r["account_id"]),
                "trip_item_id": str(r["trip_item_id"]) if r["trip_item_id"] else None} if r else None

    async def get_find(self, account, fid):
        return self._f(await self._run(lambda c: c.fetchrow("select * from mailbox_finds where id = $1 and account_id = $2",
                                                            uuid.UUID(fid), uuid.UUID(account))))

    async def list_finds(self, account):
        rows = await self._run(lambda c: c.fetch("select * from mailbox_finds where account_id = $1 order by found_at desc limit 50",
                                                 uuid.UUID(account)))
        return [self._f(r) for r in rows]

    async def set_find(self, fid, **kw):
        cols = [k for k in kw if k in ("action_status", "trip_item_id", "facts")]
        vals = [uuid.UUID(kw[k]) if k == "trip_item_id" and kw[k] else kw[k] for k in cols]
        sets = ", ".join(f"{k} = ${i + 2}" + ("::jsonb" if k == "facts" else "") for i, k in enumerate(cols))
        await self._run(lambda c: c.execute(f"update mailbox_finds set {sets} where id = $1", uuid.UUID(fid), *vals))

    async def all_links(self):
        rows = await self._run(lambda c: c.fetch("select * from mailbox_links where needs_reconnect_at is null"))
        return [{**dict(r), "account_id": str(r["account_id"]), "vault_item_id": str(r["vault_item_id"])} for r in rows]

    async def apply(self, account, action, trip_item_id, facts):
        """The status write the guest said yes to (S-79's trigger then updates the calendar)."""
        from .store import BOOKINGS_TRIP_TITLE

        async def go(c):
            async with c.transaction():
                if action in ("confirm", "cancel"):
                    owned = await c.fetchval("select ti.id from trip_items ti join trips t on t.id = ti.trip_id where ti.id = $1 and t.owner_id = $2",
                                             uuid.UUID(trip_item_id), uuid.UUID(account))
                    if not owned:
                        return None
                    await c.execute("update trip_items set status = $2, booking_reference = coalesce($3, booking_reference), updated_at = now() "
                                    "where id = $1", uuid.UUID(trip_item_id), "confirmed" if action == "confirm" else "cancelled",
                                    facts.get("reference") if action == "confirm" else None)
                    return trip_item_id
                trip = await c.fetchval("select id from trips where owner_id = $1 and title = $2 limit 1", uuid.UUID(account), BOOKINGS_TRIP_TITLE)
                if trip is None:
                    trip = await c.fetchval("insert into trips (owner_id, title) values ($1,$2) returning id", uuid.UUID(account), BOOKINGS_TRIP_TITLE)
                at = datetime.fromisoformat(facts["at"]).replace(tzinfo=ZoneInfo("Europe/Madrid")) if facts.get("at") and "T" in facts["at"] else None
                r = await c.fetchval("insert into trip_items (trip_id, type, status, provider_name, date_time, party_size, booking_reference, local_timezone) "
                                     "values ($1,'restaurant','guest_booked',$2,$3,$4,$5,'Europe/Madrid') returning id",
                                     trip, facts.get("venue") or "Booking", at, facts.get("party"), facts.get("reference"))
                return str(r)
        return await self._run(go)


STORE: Any = None


# ── Gmail over its REST API (the token by vault.use_connection, purpose gmail_read) ─────────────────────────────────

async def _http(method, url, token, params=None):
    import httpx
    async with httpx.AsyncClient(timeout=httpx.Timeout(20.0)) as c:
        r = await c.request(method, url, headers={"authorization": f"Bearer {token}"}, params=params)
    try:
        return r.status_code, r.json()
    except Exception:
        return r.status_code, {}

GMAIL_HTTP = _http   # tests replace it
MODEL_READER = None  # M-3 · off unless SASHA_MAILBOX_MODEL=1 — tests count its calls


def _body_text(payload: dict) -> str:
    out = []

    def walk(p):
        if p.get("mimeType", "").startswith("text/plain") and (p.get("body") or {}).get("data"):
            out.append(base64.urlsafe_b64decode(p["body"]["data"] + "==").decode("utf-8", "replace"))
        for q in p.get("parts") or []:
            walk(q)
    walk(payload or {})
    return "\n".join(out)


def _header(payload: dict, name: str) -> str:
    return next((h.get("value") or "" for h in (payload or {}).get("headers") or [] if (h.get("name") or "").lower() == name.lower()), "")


async def sync(account: str) -> List[dict]:
    """One narrow search; each new matching message read by rules; facts kept, bodies never. Returns the new finds."""
    from . import guest_whatsapp as GW
    from .vault import crypto as VC
    link = await STORE.get_link(account)
    if not link or link.get("needs_reconnect_at"):
        return []
    try:
        token = await VC.use_connection(account, link["vault_item_id"], purpose="gmail_read")
    except VC.UseRefused as e:
        if e.rule == "connection_invalid_grant":
            await STORE.set_link(account, needs_reconnect_at=NOW())
        return []
    rows = await GW._upcoming(account, names=False) if GW.STORE else []   # Sasha 143 · domains only: no listing re-read
    domains = [r.get("venue_domain") for r in rows if r.get("venue_domain")]
    q = build_query(domains)
    status, j = await GMAIL_HTTP("GET", f"{GMAIL}/messages", token, {"q": q, "maxResults": 50})
    if status != 200:
        log.warning("[mailbox] Gmail search answered HTTP %s", status)
        return []
    found = []
    now = NOW()
    for m in j.get("messages") or []:
        if await STORE.seen(account, m["id"]):
            continue
        s2, msg = await GMAIL_HTTP("GET", f"{GMAIL}/messages/{m['id']}", token, {"format": "full"})
        if s2 != 200:
            continue
        payload = msg.get("payload") or {}
        body = _body_text(payload)
        kind, facts, parsed_by = read(_header(payload, "Subject"), _header(payload, "From"), body, now)
        row, basis = match(facts, rows)
        if kind == "other" and row and MODEL_READER and os.getenv("SASHA_MAILBOX_MODEL", "") == "1":
            kind, facts, parsed_by = await MODEL_READER(body, row), facts, "model"   # M-3 · matched and unread by rules only
        off = offer(kind, facts, row, now)
        find = {"id": str(uuid.uuid4()), "account_id": account, "gmail_message_id": m["id"],
                "body_sha256": hashlib.sha256(body.encode()).hexdigest(), "kind": kind, "facts": facts, "parsed_by": parsed_by,
                "trip_item_id": (row or {}).get("id"), "match_basis": basis, "offered_action": off[0] if off else None,
                "offered_sentence": off[1] if off else None, "offer_sha256": hashlib.sha256(off[1].encode()).hexdigest() if off else None,
                "action_status": "offered" if off else "none"}
        await STORE.put_find(find)
        found.append(find)
    for f in await STORE.list_finds(account):          # an "add" not answered before its day: withdrawn, kept as history
        if f["action_status"] == "offered" and f.get("offered_action") == "add" and not upcoming((f.get("facts") or {}).get("at"), now):
            await STORE.set_find(f["id"], action_status="none")
    await STORE.set_link(account, last_sync_at=now)
    await _offer_on_whatsapp(account, [f for f in found if f["offered_action"]])
    return found


async def _offer_on_whatsapp(account: str, finds: List[dict]) -> None:
    from . import guest_whatsapp as GW
    if not finds or GW.STORE is None or not GW.guest_numbers():
        return
    ch = await GW.STORE.channel_of_account(account)
    if not ch:
        return
    st = await GW.STORE.get_state(ch["wa_id_sha256"])
    f = finds[0]                                         # ONE offer at a time; the rest wait on the web page
    tag = f"{f['id'][:8]}:{f['offer_sha256'][:16]}"
    out = GW.Out().ask(f["offered_sentence"], [("Yes", f"yes:{tag}"), ("No", f"no:{tag}")])
    st["pending"] = {"kind": "mailbox", "at": NOW().isoformat(), "id": f["id"], "sha": f["offer_sha256"]}
    await GW.STORE.put_state(ch["wa_id_sha256"], st)
    await GW.deliver(ch, sorted(GW.guest_numbers())[0], out, st.get("last_inbound_at"))


async def accept(account: str, fid: str, offer_sha256: str, yes: bool) -> dict:
    """The guest's answer to ONE find's sentence — bound to the find AND the sentence's hash."""
    f = await STORE.get_find(account, fid)
    if f is None:
        return {"ok": False, "rule": "find_unknown", "message": "no such find of yours"}
    if f["action_status"] != "offered" or offer_sha256 != f.get("offer_sha256"):
        return {"ok": False, "rule": "offer_stale", "message": "that question is no longer the current one"}
    if not yes:
        await STORE.set_find(fid, action_status="declined")
        return {"ok": True, "status": "declined", "say": "OK — I've left it as it was."}
    tid = await STORE.apply(account, f["offered_action"], f.get("trip_item_id"), f["facts"])
    if tid is None:
        return {"ok": False, "rule": "booking_unknown", "message": "that booking is no longer yours"}
    await STORE.set_find(fid, action_status="done", trip_item_id=tid)
    say = {"confirm": "Marked confirmed, from their email.", "cancel": "Updated: cancelled, from their email.",
           "add": "Added to your itinerary as booked by you."}[f["offered_action"]]
    return {"ok": True, "status": "done", "say": say}


# ── the loop: every 6 hours, each connected account ─────────────────────────────────────────────────────────────────

_task: Optional[asyncio.Task] = None


async def _forever() -> None:
    while True:
        try:
            for link in await STORE.all_links():
                found = await sync(link["account_id"])
                if found:
                    log.info("[mailbox] %d new find(s) for an account", len(found))
        except StorageUnavailable as e:
            log.error("[mailbox] not running: %s", e.detail)
        except Exception as e:
            log.error("[mailbox] sync failed: %s: %s", type(e).__name__, e)
        await asyncio.sleep(SYNC_EVERY_S)


def start() -> None:
    from .calendar_sync import configured
    global _task
    if _task is None and os.getenv("SASHA_MAILBOX_LOOP", "1") == "1" and os.getenv("DATABASE_URL", "").strip() and configured():
        _task = asyncio.create_task(_forever())


# ── routes ──────────────────────────────────────────────────────────────────────────────────────────────────────────

router = APIRouter(prefix="/mailbox", tags=["booking-mailbox"])


def _refuse(status: int, rule: str, message: str) -> JSONResponse:
    return JSONResponse({"ok": False, "rule": rule, "message": message}, status_code=status)


def invited(account: str) -> bool:
    """Sasha 120 · Gmail is a beta BY INVITATION (Google's testing mode admits only its listed test users): the founder,
    and the accounts he lists in SASHA_GMAIL_ACCOUNTS."""
    from .identity import founder_account
    listed = {a.strip().lower() for a in os.getenv("SASHA_GMAIL_ACCOUNTS", "").split(",") if a.strip()}
    return account == founder_account() or account.lower() in listed


def status() -> dict:
    return {"loop": _task is not None, "model": os.getenv("SASHA_MAILBOX_MODEL", "") == "1"}


@router.get("")
async def mailbox_view(request: Request):
    from .account import account_for
    from .calendar_sync import configured
    account = account_for(request)
    try:
        link = await STORE.get_link(account) if STORE else None
        finds = await STORE.list_finds(account) if (STORE and link) else []
    except StorageUnavailable as e:
        return _refuse(503, e.rule, e.detail)
    return {"configured": configured(), "invited": invited(account), "connected": bool(link and not link.get("needs_reconnect_at")),
            "expired": bool(link and link.get("needs_reconnect_at")), "consent": consent(),
            "finds": [{"id": f["id"], "kind": f["kind"], "facts": {k: v for k, v in f["facts"].items() if k != "sasha_ref"},
                       "action": f.get("offered_action"), "status": f["action_status"],
                       "offer_sha256": f.get("offer_sha256"), "sentence": f.get("offered_sentence")}
                      for f in finds]}


@router.post("/connect")
async def mailbox_connect(request: Request):
    from urllib.parse import urlencode
    from .account import account_for
    from .calendar_sync import configured, make_state
    account = account_for(request)
    try:
        body = await request.json()
    except Exception:
        body = {}
    if not invited(account):
        return _refuse(403, "gmail_by_invitation", "Gmail is a beta by invitation, and it isn't open for your account yet")
    c = consent()
    if body.get("consent_version") != c["version"] or body.get("consent_sha256") != c["sha256"]:
        return _refuse(422, "consent_stale", "tick the sentence shown — it must be the current one")
    if not configured():
        return _refuse(503, "google_not_configured", "Google sign-in isn't set up on this server yet")
    q = {"client_id": os.getenv("SASHA_GOOGLE_OAUTH_CLIENT_ID", "").strip(), "redirect_uri": os.getenv("SASHA_GOOGLE_OAUTH_REDIRECT", "").strip(),
         "response_type": "code", "scope": SCOPE, "access_type": "offline", "prompt": "consent", "include_granted_scopes": "true",
         "state": make_state(account, c["version"], product="gmail")}
    return {"url": "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(q)}


async def on_connected(account: str, refresh_token: str, version: str, now: datetime) -> None:
    """From S-79's shared callback (state product = gmail): the token sealed as its own vault item, then a first sync."""
    from .vault import crypto as VC
    item_id = str(uuid.uuid4())
    sealed = await VC.seal(account, item_id, "oauth", json.dumps({"refresh_token": refresh_token}).encode())
    await VC.STORE.create({"id": item_id, "account_id": account, "provider": "google.com", "label": "Gmail (read-only)", "kind": "oauth",
                           **sealed, "special_category": False, "created_at": now, "updated_at": now})
    await VC.STORE.event(account, item_id, "created", {"kind": "oauth", "provider": "google.com", "purpose": "gmail_read"}, now)
    old = await STORE.get_link(account)
    c = consent(version)
    await STORE.put_link({"account_id": account, "vault_item_id": item_id, "consent_at": now, "consent_wording_version": c["version"],
                          "consent_text_sha256": c["sha256"]})
    if old:
        await VC.STORE.revoke(account, old["vault_item_id"], now)
    try:
        await sync(account)
    except Exception as e:
        log.warning("[mailbox] the first sync failed: %s", type(e).__name__)


@router.post("/sync")
async def mailbox_sync(request: Request):
    from .account import account_for
    try:
        found = await sync(account_for(request))
    except StorageUnavailable as e:
        return _refuse(503, e.rule, e.detail)
    return {"found": len(found)}


@router.post("/finds/{fid}")
async def mailbox_answer(fid: str, request: Request):
    from .account import account_for
    account = account_for(request)
    try:
        body = await request.json()
        r = await accept(account, fid, str(body.get("offer_sha256") or ""), bool(body.get("yes")))
    except StorageUnavailable as e:
        return _refuse(503, e.rule, e.detail)
    except Exception:
        return _refuse(400, "malformed", "send {offer_sha256, yes}")
    return r if r.get("ok") else _refuse(422, r["rule"], r["message"])


@router.delete("")
async def mailbox_disconnect(request: Request):
    from .account import account_for
    from .vault import crypto as VC
    account = account_for(request)
    link = await STORE.get_link(account) if STORE else None
    if not link:
        return {"disconnected": False}
    revoked = "not revoked"
    try:
        revoked = await VC.use_connection(account, link["vault_item_id"], purpose="gmail_revoke", revoke=True)
    except Exception as e:
        log.warning("[mailbox] revoke at Google failed: %s", type(e).__name__)
    await VC.STORE.revoke(account, link["vault_item_id"], NOW())
    n = await STORE.delete_account_finds(account)   # §5.5 · the finds go; facts stay only on bookings the guest accepted
    return {"disconnected": True, "at_google": revoked, "finds_deleted": n}


__all__ = ["build_query", "read", "match", "offer", "sync", "accept", "router", "start", "status", "MemoryMailboxStore",
           "PostgresMailboxStore", "consent", "on_connected"]
