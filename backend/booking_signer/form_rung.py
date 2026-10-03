"""Sasha 89 · THE FORM RUNG, SUBMITTING — Sasha fills a venue's own booking form and sends it, behind the guest's yes.

    POST /api/booking/forms                 {read_id, reservation} → the read-back: EVERY field and the value she'll send
    POST /api/booking/forms/{form_id}/send  {read_back_sha256, approval} → sent once; their answer page kept verbatim
    GET  /api/booking/forms/{form_id}       the form as it stands

  · ONLY a mapped, approved form: our own TEST VENUE (below) always; a real venue only once the founder approves it —
    its host in SASHA_FORM_HOSTS **and** a field map for it in FORM_MAPS. Nothing else is ever submitted.
  · Read live, robots first, never a booking platform (venue_read's guarded fetch). Every field the live form has is
    accounted for: mapped → filled from the reservation (formfill.fill); a CAPTCHA anywhere → STOP; a box agreeing to
    terms → STOP (never ticked for the guest); a required field nobody mapped → STOP; a honeypot → never touched; the
    page's own hidden fields → sent with the page's own values, named in the read-back.
  · The read-back lists every field and value; the yes binds to its hash; one send per yes, within 15 minutes.
  · The answer page is kept word for word and read with the field checks (followup.reply_reading): only an answer
    that restates the booking with a yes CONFIRMS it.

THE TEST VENUE (never a real one): GET /api/booking/test-venue/{plain|consent|captcha} serves a booking form on this
server; POSTing it records the submission here and answers "Reserva recibida … Localizador TV-…". The founder's key
reads the submissions back (GET /api/booking/test-venue/submissions).
"""
from __future__ import annotations

import hashlib
import logging
import os
import re
import uuid
from datetime import date, datetime, time, timedelta, timezone
from html import escape
from html.parser import HTMLParser
from typing import Any, Dict, List, Mapping, Optional
from urllib.parse import urlencode, urljoin, urlsplit

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

from . import formfill as FF
from . import yes as YS
from . import reservation as RS
from . import venue_read as V
from .account import account_for
from .store import StorageUnavailable, _row, _uuid_or_none

log = logging.getLogger("booking_signer.form_rung")
router = APIRouter(tags=["booking-form-rung"])
APPROVAL_WINDOW = timedelta(minutes=15)
NOW = lambda: datetime.now(timezone.utc)
RESPONSE_CHARS = 4000
TEST_VARIANTS = ("plain", "consent", "captcha", "wizard")


def public_base() -> str:
    return os.getenv("SASHA_PUBLIC_BASE", os.getenv("TWILIO_WEBHOOK_BASE", "https://sasha-travel-production.up.railway.app")).rstrip("/")


def test_venue_url(variant: str = "plain") -> str:
    return f"{public_base()}/api/booking/test-venue/{variant}"


# ── the maps: which forms Sasha may send, and what each field is ──────────────────────────────────────────────────

#: field name → (S-46 role, the label the read-back shows). The test venue's form, all three variants.
TEST_FIELDS = {"fecha": ("date", "Día"), "hora": ("time", "Hora"), "personas": ("party_size", "Personas"),
               "nombre": ("person_name", "Nombre"), "email": ("email", "Email"), "telefono": ("phone", "Teléfono"),
               "comentarios": ("free_text", "Comentarios")}
def _es_national(e164: str) -> str:
    """+34608445715 → 608445715: a Spanish form that takes exactly 9 digits (its own validation says so)."""
    d = re.sub(r"\D", "", e164 or "")
    if d.startswith("34") and len(d) == 11:
        d = d[2:]
    if len(d) != 9:
        raise FF.Stop("phone_format", "their form takes a 9-digit Spanish phone number; yours isn't one — which number should they have?")
    return d


#: A real venue's form, once the founder APPROVES it (its host also in SASHA_FORM_HOSTS). Every entry says where each
#: fact came from. Keys: fields (name → role, label), action (the real endpoint, https, same site), fixed (name → value,
#: label: sent as the venue's own default), date_fmt, time_fmt, phone_fmt, provenance.
_HANAKURA = {
    "fields": {"nombre": ("person_name", "Nombre y apellidos"), "telefono": ("phone", "Teléfono"), "email": ("email", "Email"),
               "comensales": ("party_size", "Comensales"), "fecha": ("date", "Fecha"), "hora": ("time", "Hora")},
    "fixed": {"menu": ("degustacion", "Menús degustación (their default, \"No deseo menú degustación\")")},
    "action": "https://www.hanakura.es/formularios/reservar.php",
    "date_fmt": lambda d: d.strftime("%d/%m/%Y"),
    "time_fmt": lambda t: t.strftime("%H:%M"),
    "phone_fmt": _es_national,
    "provenance": ("Sasha 96, 2 Oct 2026, read live from hanakura.es: the form on /solicitar-reserva.html (no action; "
                   "fields nombre, telefono, email, comensales 1–10, fecha, hora 13:30–23:00, menu default 'degustacion'); "
                   "/formularios/validation_reservas.js posts $('form').serialize() to formularios/reservar.php, requires "
                   "telefono of exactly 9 digits, and dates by jQuery UI's Spanish datepicker (dd/mm/yyyy), closed Mondays. "
                   "No robots.txt; aviso-legal says nothing on automated use. Approved by the founder, 2 Oct 2026."),
}
FORM_MAPS: Dict[str, Dict[str, Any]] = {"www.hanakura.es": _HANAKURA, "hanakura.es": _HANAKURA}


def _test_host() -> str:
    return urlsplit(public_base()).hostname or ""


def is_test_venue(url: str) -> bool:
    u = urlsplit(url or "")
    return (u.hostname or "").lower() == _test_host() and u.path.startswith("/api/booking/test-venue/")


def form_map(url: str) -> Optional[Dict[str, Any]]:
    """The map for the form at `url`, if Sasha may send it — the test venue always, a real host only when approved."""
    u = urlsplit(url or "")
    host = (u.hostname or "").lower()
    if host == _test_host() and u.path.startswith("/api/booking/test-venue/"):
        return {"fields": TEST_FIELDS, "date_fmt": lambda d: d.isoformat(), "time_fmt": lambda t: t.strftime("%H:%M"), "test": True}
    approved = {h.strip().lower() for h in os.getenv("SASHA_FORM_HOSTS", "").split(",") if h.strip()}
    m = FORM_MAPS.get(host)
    return {**m, "test": False} if (m and host in approved) else None


def forms_status() -> dict:
    """For /health: which forms can be sent. Never a secret."""
    return {"test_venue": test_venue_url(), "approved_hosts": sorted(h for h in FORM_MAPS
            if h in {x.strip().lower() for x in os.getenv("SASHA_FORM_HOSTS", "").split(",")}),
            "real_forms_enabled": os.getenv("SASHA_FORMS_ENABLED", "").strip() == "1"}


# ── the live form, read field by field ────────────────────────────────────────────────────────────────────────────

_CHALLENGE = re.compile(r"recaptcha|hcaptcha|turnstile|captcha|g-recaptcha|cf-chl|friendlycaptcha", re.I)


class _LiveForm(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.forms: List[Dict[str, Any]] = []
        self.labels: Dict[str, str] = {}
        self.challenge = False
        self.text: List[str] = []
        self._label_for: Optional[str] = None
        self._label: List[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        a = {k: (v if v is not None else "") for k, v in attrs}
        blob = " ".join(str(v) for v in a.values())
        if _CHALLENGE.search(blob):
            self.challenge = True
        if tag in ("script", "style"):
            self._skip += 1
        if tag == "form":
            self.forms.append({"action": a.get("action", ""), "method": (a.get("method") or "get").lower(), "fields": []})
        if tag == "label":
            self._label_for, self._label = a.get("for"), []
        if tag == "option" and self.forms and self.forms[-1]["fields"] and self.forms[-1]["fields"][-1]["type"] == "select":
            self.forms[-1]["fields"][-1].setdefault("options", []).append(a.get("value", ""))
        if tag in ("input", "select", "textarea") and self.forms:
            typ = (a.get("type") or ("select" if tag == "select" else "textarea" if tag == "textarea" else "text")).lower()
            style = (a.get("style") or "").replace(" ", "").lower()
            self.forms[-1]["fields"].append({
                "name": a.get("name", ""), "id": a.get("id", ""), "type": typ, "value": a.get("value", ""),
                "required": "required" in a or a.get("aria-required") == "true",
                "hidden_by_style": "display:none" in style or "visibility:hidden" in style or "tabindex" in a and a.get("tabindex") == "-1",
                "autocomplete_off_trap": a.get("autocomplete") == "off" and "hp" in a.get("name", "").lower()})

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self._skip:
            self._skip -= 1
        if tag == "label" and self._label_for is not None:
            self.labels[self._label_for] = " ".join("".join(self._label).split())
            self._label_for = None

    def handle_data(self, data):
        if self._skip:
            if _CHALLENGE.search(data):
                self.challenge = True
            return
        if self._label_for is not None:
            self._label.append(data)
        self.text.append(data)


def read_form(html: str, page_url: str) -> Dict[str, Any]:
    p = _LiveForm()
    try:
        p.feed((html or "")[:V.MAX_BYTES])
    except Exception:
        pass
    booking = [f for f in p.forms if sum(1 for x in f["fields"] if x["name"] and x["type"] not in ("hidden", "submit", "button")) >= 3]
    if not booking:
        return {"why": "no booking form on the page"}
    f = booking[0]
    for x in f["fields"]:
        x["label"] = p.labels.get(x["id"]) or x["name"]
    return {"action": urljoin(page_url, f["action"] or page_url), "method": f["method"], "fields": f["fields"],
            "challenge": p.challenge, "text": " ".join(" ".join(p.text).split())}


def roles_for(live: Dict[str, Any], m: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Every live field with its role — mapped, or what the markup says it is; nothing guessed into a booking role."""
    out = []
    for x in live["fields"]:
        if not x["name"] or x["type"] in ("submit", "button", "reset", "image"):
            continue
        if x["type"] == "hidden":
            out.append({**x, "role": "hidden"})
        elif _CHALLENGE.search(x["name"]):
            out.append({**x, "role": "challenge"})
        elif x["hidden_by_style"] or x["autocomplete_off_trap"]:
            out.append({**x, "role": "trap"})
        elif x["name"] in m["fields"]:
            role, label = m["fields"][x["name"]]
            out.append({**x, "role": role, "label": label})
        elif x["name"] in (m.get("fixed") or {}):
            out.append({**x, "role": "fixed", "label": m["fixed"][x["name"]][1]})
        elif x["type"] in ("checkbox", "radio"):
            out.append({**x, "role": "consent"})          # a box to tick is the guest's, never Sasha's
        else:
            out.append({**x, "role": "other"})
    if live.get("challenge"):
        out.append({"name": "(the page's CAPTCHA)", "role": "challenge", "required": True, "type": "challenge", "label": "CAPTCHA"})
    return out


def _sha(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def read_back(page_url: str, action: str, filled: List[Dict[str, str]], hidden: List[str], venue: str) -> List[str]:
    lines = [f"I'll send the booking form on {venue}'s own website ({page_url}), to {action}, with exactly these fields:"]
    lines += [f"· {f['label']}: {f['value']}" for f in filled]
    if hidden:
        lines.append(f"· plus the page's own hidden fields, sent with the page's values: {', '.join(hidden)}.")
    lines += ["I won't tick any box agreeing to their terms, and I stop at any CAPTCHA.",
              "Their answer page is kept word for word. I send it once. Shall I send it?"]
    return lines


# ── Sasha 94 · the WIZARD: the date on one page, the details on the next ─────────────────────────────────────────

_STEP_ONE = {"date", "time", "date_time", "party_size", "service"}
_STEP_TWO = ("person_name", "given_name", "family_name", "email", "phone", "free_text")


def venue_formats(filled: List[Dict[str, str]], fields: List[Dict[str, Any]], m: Dict[str, Any]) -> List[Dict[str, str]]:
    """The venue's own formats (a phone as its validation demands) and, for a list, only a value it actually offers."""
    by = {f["name"]: f for f in fields}
    out = []
    for f in filled:
        v, live = f["value"], by.get(f["name"]) or {}
        if live.get("role") == "phone" and m.get("phone_fmt"):
            v = m["phone_fmt"](v)
        opts = live.get("options")
        if opts and v not in opts:
            raise FF.Stop("option_unavailable", f"their form's '{live.get('label') or f['name']}' doesn't offer {v} "
                                                f"(it offers {', '.join(opts)}) — which should it be?")
        out.append({**f, "value": v})
    return out


#: Sasha 99 · the line that asks a venue to copy Sasha — in a comments box, never in place of the guest's own address
_COPY_ASK = {"ES": "Por favor, envíen también una copia de la confirmación a {me}.", "PT": "Por favor, enviem também uma cópia da confirmação para {me}.",
             "FR": "Merci d'envoyer aussi une copie de la confirmation à {me}.", "IT": "Per favore, inviate anche una copia della conferma a {me}.",
             "DE": "Bitte senden Sie eine Kopie der Bestätigung auch an {me}."}


def with_sasha_copy(filled: List[Dict[str, str]], fields: List[Dict[str, Any]], country: Optional[str]) -> List[Dict[str, str]]:
    """The guest's own email and phone stay in the form's single email/phone fields (they need the reminder); a
    comments field, when there is one, asks the venue to copy Sasha too — so the confirmation and any cancel link
    reach her. No comments field: nothing added (the form is never repurposed)."""
    from .followup import own_email
    me = own_email()
    box = next((f for f in fields if f.get("role") == "free_text"), None)
    if not me or box is None:
        return filled
    ask = _COPY_ASK.get((country or "").upper(), "Please also send a copy of the confirmation to {me}.").format(me=me)
    out, done = [], False
    for f in filled:
        if f["name"] == box["name"]:
            f = {**f, "value": f"{f['value']} · {ask}" if f.get("value") else ask}
            done = True
        out.append(f)
    return out if done else out + [{"name": box["name"], "value": ask}]


def effective_action(live: Dict[str, Any], m: Dict[str, Any]) -> Optional[str]:
    """Where the form really goes: the approved map's endpoint (https, on the venue's own site) or the form's action."""
    a = m.get("action")
    if not a:
        return live["action"]
    if urlsplit(a).scheme != "https" or reg_host(a) != reg_host(live.get("page_url") or live["action"]):
        return None
    return a


def is_wizard(fields: List[Dict[str, Any]], m: Dict[str, Any]) -> bool:
    """A first page that asks only WHEN (and how many), on a form whose map also holds the guest's details."""
    asked = {f["role"] for f in fields if f["role"] not in ("hidden", "trap", "fixed")}
    return bool(asked) and asked <= _STEP_ONE and any(r in _STEP_TWO for r, _ in m["fields"].values())


def step_two_fields(m: Dict[str, Any]) -> List[Dict[str, Any]]:
    """The details page as its map says it is — it exists only once step 1 is sent, so it is checked live then."""
    return [{"name": n, "role": r, "label": lbl, "required": r in ("person_name", "email", "phone")}
            for n, (r, lbl) in m["fields"].items() if r in _STEP_TWO]


def read_back_wizard(page_url: str, action: str, shown: List[Dict[str, Any]], hidden: List[str], venue: str) -> List[str]:
    lines = [f"{venue}'s own booking form ({page_url}) has two steps. Step 1 — the day — sent to {action}:"]
    lines += [f"· {f['label']}: {f['value']}" for f in shown if f.get("step") == 1]
    if hidden:
        lines.append(f"· plus the page's own hidden fields, with the page's values: {', '.join(hidden)}.")
    lines.append("Step 2 — the page step 1 opens — with exactly these fields:")
    lines += [f"· {f['label']}: {f['value']}" for f in shown if f.get("step") == 2]
    lines += ["If step 2 asks for anything else, has a CAPTCHA or a box agreeing to their terms, I stop there: only the day "
              "and the number of people will have reached them, and nothing is booked.",
              "Their answer page is kept word for word. I send it once. Shall I send it?"]
    return lines


_REF = re.compile(r"\b(?:localizador|referencia|reference|booking (?:number|ref(?:erence)?)|confirmation (?:number|code)|n[º°o]\.? de reserva)\s*[:#]?\s*([A-Z0-9][A-Z0-9-]{2,24})", re.I)


# ── storage: Memory for tests, Postgres (sql/018) for real ────────────────────────────────────────────────────────

class MemoryFormStore:
    def __init__(self, calls_store=None) -> None:
        self.forms: Dict[str, dict] = {}
        self.calls = calls_store      # its trip_items, so a form's reservation sits beside the calls'
        self.attempts: List[dict] = []

    async def put(self, row: dict, item: dict) -> str:
        item_id = str(uuid.uuid4())
        if self.calls is not None:
            self.calls.trip_items[item_id] = {"id": item_id, "status": "pending", **item}
        self.forms[row["form_id"]] = {**row, "trip_item_id": item_id, "status": "awaiting_approval"}
        return item_id

    async def get(self, account: str, form_id: str) -> Optional[dict]:
        r = self.forms.get(form_id)
        return dict(r) if r and r["account_id"] == account else None

    async def for_item(self, account: str, trip_item_id: str) -> Optional[dict]:
        rs = [dict(r) for r in self.forms.values() if r.get("trip_item_id") == trip_item_id and r["account_id"] == account]
        return rs[-1] if rs else None

    async def claim(self, account, form_id, approval, now, fresh_after) -> str:
        r = self.forms.get(form_id)
        if not r or r["account_id"] != account:
            return "unknown"
        if r["status"] != "awaiting_approval":
            return "already"
        if r["created_at"] < fresh_after:
            return "expired"
        r.update(status="sending", approval=approval, approved_at=now)
        return "claimed"

    async def finish(self, form_id, outcome: dict, trip_status: str, attempt_status: str, now) -> None:
        r = self.forms[form_id]
        r.update(outcome)
        if self.calls is not None and r.get("trip_item_id") in self.calls.trip_items:
            self.calls.trip_items[r["trip_item_id"]]["status"] = trip_status
            if outcome.get("booking_reference"):
                self.calls.trip_items[r["trip_item_id"]]["booking_reference"] = outcome["booking_reference"]
        self.attempts.append({"trip_item_id": r.get("trip_item_id"), "method": "web_form", "status": attempt_status,
                              "response_received": outcome.get("response_text")})


class PostgresFormStore:
    def __init__(self, base) -> None:
        self._base = base

    async def _run(self, fn):
        try:
            return await self._base._run(fn)
        except StorageUnavailable as e:
            raise e.rehint("018_booking_forms.sql") from None

    async def put(self, row: dict, item: dict) -> str:
        acct = uuid.UUID(row["account_id"])

        async def fn(conn):
            from .call_store import BOOKINGS_TRIP_TITLE
            async with conn.transaction():
                tid = await conn.fetchval("select id from trips where owner_id = $1 and title = $2 and status in ('draft','active') "
                                          "order by created_at limit 1", acct, BOOKINGS_TRIP_TITLE)
                if tid is None:
                    tid = await conn.fetchval("insert into trips (owner_id, title) values ($1, $2) returning id", acct, BOOKINGS_TRIP_TITLE)
                item_id = await conn.fetchval(
                    "insert into trip_items (trip_id, type, status, provider_name, date_time, local_timezone, party_size) "
                    "values ($1, $2, 'pending', $3, ($4::date + $5::time) at time zone $6, $6, $7) returning id",
                    tid, item["type"], item["provider_name"], item["local_date"], item["local_time"], item["local_timezone"], item["party_size"])
                await conn.execute(
                    "insert into booking_forms (form_id, account_id, trip_item_id, read_id, host, page_url, action_url, fields, "
                    "hidden_names, read_back_lines, read_back_sha256, status, request_sha256, created_at) "
                    "values ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,'awaiting_approval',$12,$13)",
                    uuid.UUID(row["form_id"]), acct, item_id, _uuid_or_none(row.get("read_id")), row["host"], row["page_url"],
                    row["action_url"], row["fields"], row["hidden_names"], row["read_back_lines"], row["read_back_sha256"],
                    row.get("request_sha256"), row["created_at"])
                if item.get("request"):
                    await conn.execute("update trip_items set request = $2, request_sha256 = $3, request_schema = $4 where id = $1",
                                       item_id, item["request"], RS.sha256(item["request"]), RS.SCHEMA)
                return str(item_id)
        return await self._run(fn)

    async def get(self, account, form_id):
        fid = _uuid_or_none(form_id)
        if fid is None:
            return None
        return _row(await self._run(lambda c: c.fetchrow("select * from booking_forms where form_id = $1 and account_id = $2",
                                                         fid, uuid.UUID(account))))

    async def for_item(self, account, trip_item_id):
        iid = _uuid_or_none(trip_item_id)
        if iid is None:
            return None
        return _row(await self._run(lambda c: c.fetchrow(
            "select * from booking_forms where trip_item_id = $1 and account_id = $2 order by created_at desc limit 1", iid, uuid.UUID(account))))

    async def claim(self, account, form_id, approval, now, fresh_after) -> str:
        async def fn(conn):
            r = await conn.fetchrow("update booking_forms set status = 'sending', approval = $3, approved_at = $4 "
                                    "where form_id = $1 and account_id = $2 and status = 'awaiting_approval' and created_at >= $5 "
                                    "returning form_id", uuid.UUID(form_id), uuid.UUID(account), approval, now, fresh_after)
            if r:
                return "claimed"
            st = await conn.fetchrow("select status, created_at from booking_forms where form_id = $1 and account_id = $2",
                                     uuid.UUID(form_id), uuid.UUID(account))
            return "unknown" if st is None else "already" if st["status"] != "awaiting_approval" else "expired"
        return await self._run(fn)

    async def finish(self, form_id, outcome, trip_status, attempt_status, now) -> None:
        async def fn(conn):
            async with conn.transaction():
                item = await conn.fetchval(
                    "update booking_forms set status = $2, sent_at = $3, http_status = $4, final_url = $5, response_text = $6, "
                    "response_sha256 = $7, reading = $8, not_sent_why = $9 where form_id = $1 returning trip_item_id",
                    uuid.UUID(form_id), outcome["status"], outcome.get("sent_at"), outcome.get("http_status"), outcome.get("final_url"),
                    outcome.get("response_text"), outcome.get("response_sha256"), outcome.get("reading"), outcome.get("not_sent_why"))
                if item is None:
                    return
                await conn.execute("update trip_items set status = $2, booking_reference = coalesce($3, booking_reference), "
                                   "updated_at = now() where id = $1", item, trip_status, outcome.get("booking_reference"))
                await conn.execute("insert into booking_attempts (trip_item_id, method, attempted_at, status, response_received, "
                                   "response_at, observed_by) values ($1, 'web_form', $2, $3, $4, $2, $5)",
                                   item, now, attempt_status, (outcome.get("response_text") or outcome.get("not_sent_why") or "")[:4000],
                                   "their own booking form, sent by Sasha after your yes; their answer page, word for word (Sasha 89)")
        await self._run(fn)


STORE: Any = None
TEST_SUBMISSIONS: List[dict] = []   # the test venue's own book of reservations (this server's memory; it is ours)


# ── injectable HTTP ───────────────────────────────────────────────────────────────────────────────────────────────

async def FORM_POST(url: str, data: Dict[str, str], headers: Dict[str, str]):
    """POST a form, url-encoded, no redirects followed (the caller follows one, checked)."""
    import httpx
    async with httpx.AsyncClient(timeout=httpx.Timeout(20.0), follow_redirects=False) as client:
        return await client.post(url, data=data, headers=headers)


def _refuse(status: int, rule: str, message: str) -> JSONResponse:
    return JSONResponse({"ok": False, "rule": rule, "message": message}, status_code=status)


async def _live(page_url: str) -> Dict[str, Any]:
    """The page, fetched now through venue_read's guards (robots first, public host, never a platform)."""
    from . import ladder_routes as LR
    if V.platform_of(page_url):
        return {"why": "a booking platform's page — never filled"}
    if not await V._allowed(LR.HTTP, page_url, LR.RESOLVE):
        return {"why": "their robots.txt does not allow it"}
    final, r = await V._get(LR.HTTP, page_url, LR.RESOLVE)
    if r.status_code != 200:
        return {"why": f"their page answered HTTP {r.status_code}"}
    out = read_form(r.text or "", final)
    return {**out, "page_url": final}


# ── the routes ────────────────────────────────────────────────────────────────────────────────────────────────────

@router.post("/forms")
async def prepare(request: Request):
    from . import ladder_routes as LR
    try:
        body = await request.json()
    except Exception:
        body = None
    if not isinstance(body, dict) or not body.get("read_id") or not isinstance(body.get("reservation"), dict):
        return _refuse(400, "form_malformed", "send {read_id, reservation}")
    account = account_for(request)
    row = await LR.LADDER_STORE.get_read(account, str(body["read_id"]))
    if row is None:
        return _refuse(404, "read_unknown", "no venue read with that id for this account")
    read = row["read"]
    form_fact = next((f for f in read.get("facts") or [] if f.get("kind") == "booking_form" and f.get("value")), None)
    if form_fact is None:
        return _refuse(422, "no_form_read", "no booking form was read on their website")
    page_url = form_fact.get("source_url") or form_fact["value"]
    m = form_map(page_url)
    if m is None:
        return _refuse(422, "form_not_approved", "Sasha only sends a form that has been mapped and approved — our test venue, "
                                                 "or a venue the founder has approved; this one hasn't been")
    if not m["test"] and os.getenv("SASHA_FORMS_ENABLED", "").strip() != "1":
        return _refuse(422, "forms_disabled", "sending real venues' forms is switched off on this server; nothing was filled")
    country = read.get("country")
    if country not in V.COUNTRIES:
        return _refuse(422, "venue_country_unknown", "the venue's country is not known, so neither its day nor its time can be")
    tz = V.COUNTRIES[country][3]
    obj = body["reservation"]
    # the account is the caller's own, never the object's; the venue is the one READ (as for a call)
    obj = {**obj, "who": {**(obj.get("who") or {}), "account_id": account},
           "where": {**(obj.get("where") or {}), "read_id": str(row["read_id"]), "venue_name": read["name"], "timezone": tz}}
    try:
        o = RS.validate(obj)
    except RS.ReservationRefused as e:
        return _refuse(422, e.rule, str(e).split(": ", 1)[-1])
    try:
        live = await _live(page_url)
    except V.ReadRefused as e:
        return _refuse(422, "form_unreadable", f"their form could not be read: {e}")
    if "why" in live:
        return _refuse(422, "form_unreadable", live["why"])
    if live["method"] != "post":
        return _refuse(422, "form_not_post", "their form doesn't post a booking (it's a search or a link); Sasha won't send it")
    fields = roles_for(live, m)
    wizard = is_wizard(fields, m)
    step2 = step_two_fields(m) if wizard else []
    try:
        filled = FF.fill(o, [f for f in fields if f["role"] not in ("hidden", "fixed")], date_fmt=m["date_fmt"], time_fmt=m["time_fmt"])
        filled2 = FF.fill(o, step2, date_fmt=m["date_fmt"], time_fmt=m["time_fmt"]) if wizard else []
        filled, filled2 = venue_formats(filled, fields, m), venue_formats(filled2, step2, m)
    except FF.Stop as e:
        return _refuse(422, f"form_{e.rule}", e.ask)
    filled += [{"name": f["name"], "value": m["fixed"][f["name"]][0]} for f in fields if f["role"] == "fixed"]
    if wizard:   # the comments box is on the details page
        filled2 = with_sasha_copy(filled2, step2, read.get("country"))
    else:
        filled = with_sasha_copy(filled, fields, read.get("country"))
    action = effective_action(live, m)
    if action is None:
        return _refuse(422, "form_endpoint", "their form's real address isn't on their own site over https; Sasha won't send it")
    live = {**live, "action": action}
    labels = {f["name"]: f.get("label") or f["name"] for f in fields + step2}
    roles = {f["name"]: f["role"] for f in fields + step2}
    shown = [{"name": f["name"], "label": labels.get(f["name"], f["name"]), "role": roles.get(f["name"]), "value": f["value"],
              **({"step": 1} if wizard else {})} for f in filled]
    shown += [{"name": f["name"], "label": labels.get(f["name"], f["name"]), "role": roles.get(f["name"]), "value": f["value"], "step": 2}
              for f in filled2]
    hidden = [f["name"] for f in fields if f["role"] == "hidden"]
    lines = (read_back_wizard(live["page_url"], live["action"], shown, hidden, read["name"]) if wizard
             else read_back(live["page_url"], live["action"], shown, hidden, read["name"]))
    now = NOW()
    form_id = str(uuid.uuid4())
    rec = {"form_id": form_id, "account_id": account, "read_id": str(row["read_id"]), "host": urlsplit(live["page_url"]).hostname,
           "page_url": live["page_url"], "action_url": live["action"], "fields": shown, "hidden_names": hidden,
           "read_back_lines": lines, "read_back_sha256": _sha("\n".join(lines)), "request_sha256": RS.sha256(o), "created_at": now}
    on, at = o["when"]["at"].split("T")
    item = {"type": o["what"]["category"] if o["what"]["category"] in ("restaurant", "beauty", "experience", "appointment") else "other",
            "provider_name": read["name"], "local_date": date.fromisoformat(on), "local_time": time.fromisoformat(at),
            "local_timezone": tz, "party_size": o["how_many"]["count"] if o["how_many"]["unit"] == "people" else None, "request": o}
    try:
        item_id = await STORE.put(rec, item)
    except StorageUnavailable as e:
        return _refuse(503, e.rule, e.detail)
    return {"form_id": form_id, "trip_item_id": item_id, "test_venue": m["test"],
            "read_back": {"lines": lines, "sha256": rec["read_back_sha256"]}}


@router.post("/forms/{form_id}/send")
async def send(form_id: str, request: Request):
    from . import followup as FU
    try:
        body = await request.json()
    except Exception:
        body = None
    if not isinstance(body, dict) or not isinstance(body.get("approval"), dict):
        return _refuse(400, "approval_void", "send {read_back_sha256, approval: {how, said}}")
    if not YS.approval_ok(body["approval"]):   # S-75 step 2 · the same rule as a call's yes (yes.py)
        return _refuse(422, "approval_void", YS.APPROVAL_VOID)
    account = account_for(request)
    from .limits import check
    over = check(account, "form_send")   # Sasha 120 · a real submission to a venue: capped per guest
    if over:
        return over
    try:
        f = await STORE.get(account, form_id)
    except StorageUnavailable as e:
        return _refuse(503, e.rule, e.detail)
    if f is None:
        return _refuse(404, "form_unknown", "no prepared form with that id for this account")
    if body.get("read_back_sha256") != f["read_back_sha256"]:
        return _refuse(422, "read_back_mismatch", "that yes was to different words; prepare it again")
    m = form_map(f["page_url"])
    if m is None or (not m["test"] and os.getenv("SASHA_FORMS_ENABLED", "").strip() != "1"):
        return _refuse(422, "form_not_approved", "this form is no longer approved to send; nothing was sent")
    now = NOW()
    approval = {"how": body["approval"].get("how"), "said": body["approval"].get("said"), "at": now.isoformat(),
                "read_back_sha256": f["read_back_sha256"]}
    claimed = await STORE.claim(account, form_id, approval, now, now - APPROVAL_WINDOW)
    if claimed != "claimed":
        return _refuse(409 if claimed == "already" else 422, f"form_{claimed}",
                       {"already": "this form was already sent (or is being sent) — once per yes",
                        "expired": "that read-back is more than 15 minutes old; prepare it again",
                        "unknown": "no prepared form with that id"}[claimed])

    async def not_sent(why: str):
        await STORE.finish(form_id, {"status": "not_sent", "not_sent_why": why}, "failed", "failed", now)
        return {"status": "not_sent", "say": f"I didn't send it: {why}. Nothing reached them."}

    # re-read the live form: the page's hidden values are fresh (a token changes per visit), and nothing may have moved
    try:
        live = await _live(f["page_url"])
    except V.ReadRefused as e:
        return await not_sent(f"their form could not be read again ({e})")
    if "why" in live:
        return await not_sent(live["why"])
    fields = roles_for(live, m)
    names = {x["name"] for x in fields}
    if any(x["role"] == "challenge" for x in fields):
        return await not_sent("their form now has a CAPTCHA — Sasha never solves one")
    if any(x["role"] == "consent" and x["required"] for x in fields):
        return await not_sent("their form now asks you to accept its terms — that box is yours, not Sasha's")
    missing = [x["name"] for x in f["fields"] if x.get("step", 1) == 1 and x["name"] not in names]   # step 2 is checked after step 1
    unmapped = [x["name"] for x in fields if x["role"] == "other" and x["required"]]
    live = {**live, "action": effective_action(live, m) or "(no approved endpoint)"}
    if missing or unmapped or live["action"] != f["action_url"]:
        return await not_sent("their form changed since you approved it" + (f" (gone: {', '.join(missing)})" if missing else "")
                              + (f" (new required: {', '.join(unmapped)})" if unmapped else ""))
    wizard = any(x.get("step") == 2 for x in f["fields"])
    data = {x["name"]: x.get("value", "") for x in fields if x["role"] == "hidden"}
    data.update({x["name"]: x["value"] for x in f["fields"] if x.get("step", 1) == 1})
    try:
        r, final = await _post(f["action_url"], data, f["page_url"])
    except Exception as e:
        await STORE.finish(form_id, {"status": "failed", "not_sent_why": f"{type(e).__name__}: {e}"[:300]}, "unclear", "unclear", now)
        return {"status": "failed", "say": "I sent it, but their site didn't answer clearly — it may or may not have arrived. Check with them before relying on it."}
    if wizard:
        # Sasha 94 · step 1 has gone (the day, how many): step 2 is read, checked against the map, and only then sent
        async def stopped(why: str):
            await STORE.finish(form_id, {"status": "not_sent", "not_sent_why": f"step 2: {why}", "http_status": r.status_code},
                               "failed", "failed", now)
            return {"status": "not_sent", "say": f"I stopped at step 2: {why}. Only the day and the number of people reached "
                                                 "them; nothing is booked."}
        page2 = read_form(r.text or "", final) if r.status_code < 400 else {"why": f"their site answered HTTP {r.status_code}"}
        if "why" in page2:
            return await stopped(f"no details page came back ({page2['why']})")
        if reg_host(page2["action"]) != reg_host(f["page_url"]) or page2["method"] != "post":
            return await stopped("the details page sends somewhere else (another site, or not a booking post)")
        fields2 = roles_for(page2, m)
        names2 = {x["name"] for x in fields2}
        if any(x["role"] == "challenge" for x in fields2):
            return await stopped("it has a CAPTCHA — Sasha never solves one")
        if any(x["role"] == "consent" and x["required"] for x in fields2):
            return await stopped("it asks you to accept its terms — that box is yours, not Sasha's")
        gone = [x["name"] for x in f["fields"] if x.get("step") == 2 and x["name"] not in names2]
        extra = [x["name"] for x in fields2 if x["role"] == "other" and x["required"]]
        if gone or extra:
            return await stopped("it isn't the page you approved" + (f" (missing: {', '.join(gone)})" if gone else "")
                                 + (f" (it also requires: {', '.join(extra)})" if extra else ""))
        data2 = {x["name"]: x.get("value", "") for x in fields2 if x["role"] == "hidden"}
        data2.update({x["name"]: x["value"] for x in f["fields"] if x.get("step") == 2})
        try:
            r, final = await _post(page2["action"], data2, final)
        except Exception as e:
            await STORE.finish(form_id, {"status": "failed", "not_sent_why": f"step 2: {type(e).__name__}: {e}"[:300]}, "unclear", "unclear", now)
            return {"status": "failed", "say": "I sent step 2, but their site didn't answer clearly — it may or may not have arrived. Check with them."}
    text = " ".join(" ".join(_LiveForm_text(r.text or "")).split())[:RESPONSE_CHARS]
    reading = FU.reply_reading(text, (await _request_of(f)) or {}) if text else {"result": "none", "why": "their answer page had no text"}
    ref_m = _REF.search(text)
    trip, attempt = {"confirmed": ("confirmed", "confirmed"), "proposed": ("proposed", "unclear"),
                     "declined": ("declined", "declined")}.get(reading.get("result"), ("requested", "requested"))
    if r.status_code >= 400:
        trip, attempt = "failed", "failed"
    outcome = {"status": "sent" if r.status_code < 400 else "failed", "sent_at": now, "http_status": r.status_code, "final_url": final,
               "response_text": text, "response_sha256": _sha(text), "reading": reading,
               "booking_reference": ref_m.group(1) if ref_m else None}
    await STORE.finish(form_id, outcome, trip, attempt, now)
    # Sasha 99 · the guest's receipt after the form, too
    from . import guest_receipt as GR
    o = (await _request_of(f)) or {}
    when = (o.get("when") or {}).get("at", "").replace("T", " at ")
    from . import ladder_routes as LR   # Sasha 117 · the receipt names the VENUE, not its web host (Sasha 108's rule)
    rd = await LR.LADDER_STORE.get_read(account, str(f["read_id"])) if LR.LADDER_STORE is not None and f.get("read_id") else None
    log.info("[form_rung] %s guest receipt: %s", form_id, await GR.send_for_route(
        account, (rd or {}).get("venue_name") or urlsplit(f["page_url"]).hostname or "the venue", "their own booking form, sent by Sasha after your yes",
        {"confirmed": "Confirmed by the venue", "proposed": "They offered something else", "declined": "They said no"}.get(
            reading.get("result"), "Requested — not confirmed until they confirm"),
        {"what": (o.get("what") or {}).get("activity"), "when": when, "party": (o.get("how_many") or {}).get("count"),
         "name": (o.get("who") or {}).get("name"), "venue_reference": outcome.get("booking_reference"), "their_words": text}))
    say = {"confirmed": "Sent. Their page confirms it, word for word below.",
           "proposed": "Sent. Their page offers something different — read it below before relying on anything.",
           "declined": "Sent. Their page says no — their words are below."}.get(reading.get("result"),
           "Sent. Their page doesn't say it's confirmed — their words are below; it's a request until they confirm.")
    if r.status_code >= 400:
        say = f"Their site answered HTTP {r.status_code}; it may not have arrived. Their words are below."
    return {"status": outcome["status"], "say": say, "their_page": text, "reading": reading,
            "booking_reference": outcome["booking_reference"], "http_status": r.status_code}


def reg_host(url: str) -> str:
    parts = (urlsplit(url or "").hostname or "").lower().split(".")
    return ".".join(parts[-3:]) if len(parts) > 2 and parts[-2] in ("co", "com") else ".".join(parts[-2:])


async def _post(url: str, data: Dict[str, str], referer: str):
    """POST the form; one redirect followed, checked (venue_read's guards). → (response, final url)."""
    r = await FORM_POST(url, data, {"user-agent": V.USER_AGENT, "referer": referer})
    final = url
    if r.status_code in (301, 302, 303) and r.headers.get("location"):
        final = urljoin(final, r.headers["location"])
        from . import ladder_routes as LR
        final, r = await V._get(LR.HTTP, final, LR.RESOLVE)
    return r, final


def _LiveForm_text(html: str) -> List[str]:
    p = _LiveForm()
    try:
        p.feed(html[:V.MAX_BYTES])
    except Exception:
        pass
    return p.text


async def _request_of(f: Mapping[str, Any]) -> Optional[dict]:
    """The reservation the form was filled from (its trip item's object)."""
    calls = getattr(STORE, "calls", None)
    if calls is not None:
        return (calls.trip_items.get(f.get("trip_item_id")) or {}).get("request")
    base = getattr(STORE, "_base", None)
    if base is None or not f.get("trip_item_id"):
        return None
    return await base._run(lambda c: c.fetchval("select request from trip_items where id = $1", _uuid_or_none(f["trip_item_id"])))


@router.get("/forms/{form_id}")
async def get_form(form_id: str, request: Request):
    try:
        f = await STORE.get(account_for(request), form_id)
    except StorageUnavailable as e:
        return _refuse(503, e.rule, e.detail)
    if f is None:
        return _refuse(404, "form_unknown", "no prepared form with that id for this account")
    keep = ("form_id", "trip_item_id", "page_url", "action_url", "fields", "hidden_names", "read_back_lines", "read_back_sha256",
            "status", "approval", "http_status", "response_text", "response_sha256", "reading", "not_sent_why")
    return {k: (str(f[k]) if isinstance(f.get(k), uuid.UUID) else f.get(k)) for k in keep}


# ── the test venue (ours; never a real one) ───────────────────────────────────────────────────────────────────────

_PAGE = """<!doctype html><html lang="es"><head><meta charset="utf-8"><title>Sasha Test Venue — reservas</title>
<meta property="og:site_name" content="Sasha Test Venue">{head}</head><body>
<h1>Sasha Test Venue</h1><p>Restaurante de pruebas de Kanoe. No es un restaurante real: aquí solo reserva Sasha, para comprobar su formulario.</p>
<form method="post" action="/api/booking/test-venue/{variant}">
<input type="hidden" name="token" value="{token}">
<label for="fecha">Día</label><input id="fecha" name="fecha" type="date" required>
<label for="hora">Hora</label><input id="hora" name="hora" type="time" required>
<label for="personas">Personas</label><input id="personas" name="personas" type="number" min="1" max="20" required>
<label for="nombre">Nombre</label><input id="nombre" name="nombre" required>
<label for="email">Email</label><input id="email" name="email" type="email" required>
<label for="telefono">Teléfono</label><input id="telefono" name="telefono" type="tel" required>
<label for="comentarios">Comentarios</label><textarea id="comentarios" name="comentarios"></textarea>
<input name="website_url" style="display:none" tabindex="-1" autocomplete="off">
{extra}<button type="submit">Reservar</button></form></body></html>"""


@router.get("/test-venue/submissions")
async def test_venue_submissions():
    """The test venue's book (behind the booking key: not exempt)."""
    return {"submissions": TEST_SUBMISSIONS[-20:]}


_WIZARD_ONE = """<!doctype html><html lang="es"><head><meta charset="utf-8"><title>Sasha Test Venue — reservas (paso 1)</title>
<meta property="og:site_name" content="Sasha Test Venue"></head><body><h1>Sasha Test Venue</h1>
<p>Restaurante de pruebas de Kanoe. No es un restaurante real. Paso 1 de 2: elige el día.</p>
<form method="post" action="/api/booking/test-venue/wizard/step2"><input type="hidden" name="token" value="{token}">
<label for="fecha">Día</label><input id="fecha" name="fecha" type="date" required>
<label for="hora">Hora</label><input id="hora" name="hora" type="time" required>
<label for="personas">Personas</label><input id="personas" name="personas" type="number" min="1" max="20" required>
<button type="submit">Ver disponibilidad</button></form></body></html>"""

_WIZARD_TWO = """<!doctype html><html lang="es"><head><meta charset="utf-8"><title>Sasha Test Venue — reservas (paso 2)</title></head><body>
<p>Paso 2 de 2: hay mesa el {fecha} a las {hora} para {personas}. Tus datos:</p>
<form method="post" action="/api/booking/test-venue/wizard/confirm">
<input type="hidden" name="token" value="{token}"><input type="hidden" name="fecha" value="{fecha}">
<input type="hidden" name="hora" value="{hora}"><input type="hidden" name="personas" value="{personas}">
<label for="nombre">Nombre</label><input id="nombre" name="nombre" required>
<label for="email">Email</label><input id="email" name="email" type="email" required>
<label for="telefono">Teléfono</label><input id="telefono" name="telefono" type="tel" required>
<label for="comentarios">Comentarios</label><textarea id="comentarios" name="comentarios"></textarea>
<input name="website_url" style="display:none" tabindex="-1" autocomplete="off">
<button type="submit">Confirmar reserva</button></form></body></html>"""


@router.post("/test-venue/wizard/step2", response_class=HTMLResponse)
async def test_venue_wizard_two(request: Request):
    form = {k: str(v) for k, v in (await request.form()).items()}
    if not all(form.get(k) for k in ("fecha", "hora", "personas")):
        return HTMLResponse("<p>Elige día, hora y personas.</p>", status_code=422)
    return HTMLResponse(_WIZARD_TWO.format(**{k: escape(form.get(k, "")) for k in ("fecha", "hora", "personas", "token")}))


@router.post("/test-venue/wizard/confirm", response_class=HTMLResponse)
async def test_venue_wizard_confirm(request: Request):
    return await _book("wizard", {k: str(v) for k, v in (await request.form()).items()})


@router.get("/test-venue/{variant}", response_class=HTMLResponse)
async def test_venue(variant: str):
    if variant not in TEST_VARIANTS:
        return HTMLResponse("not found", status_code=404)
    if variant == "wizard":
        return HTMLResponse(_WIZARD_ONE.format(token=uuid.uuid4().hex))
    head = '<script src="https://www.google.com/recaptcha/api.js" async defer></script>' if variant == "captcha" else ""
    extra = {"consent": '<input id="acepto" name="acepto" type="checkbox" required><label for="acepto">Acepto la política de privacidad</label>\n',
             "captcha": '<div class="g-recaptcha" data-sitekey="test-site-key"></div>\n'}.get(variant, "")
    return HTMLResponse(_PAGE.format(variant=variant, head=head, extra=extra, token=uuid.uuid4().hex))


@router.post("/test-venue/{variant}", response_class=HTMLResponse)
async def test_venue_book(variant: str, request: Request):
    if variant not in TEST_VARIANTS or variant == "wizard":
        return HTMLResponse("not found", status_code=404)
    return await _book(variant, {k: str(v) for k, v in (await request.form()).items()})


def _tv_ref(body: str) -> str:
    """Sasha 117 · the test venue's reference carries its own check (TV-XXXXXX-YY): its book is in memory and a redeploy
    empties it, so it still knows a reference it issued — as a real venue's would — without keeping anyone's data."""
    k = (os.getenv("SASHA_BOOKING_KEY", "") or "test-venue").encode()
    return f"TV-{body}-{hashlib.sha256(k + b':tv:' + body.encode()).hexdigest()[:2].upper()}"


def _tv_ref_ok(ref: str) -> bool:
    m = re.fullmatch(r"TV-([0-9A-F]{6})-[0-9A-F]{2}", ref or "")
    return bool(m) and _tv_ref(m[1]) == ref


async def _book(variant: str, form: Dict[str, str]) -> HTMLResponse:
    """The test venue's book: record one reservation and answer as a restaurant would."""
    if form.get("website_url"):
        return HTMLResponse("<p>Rechazado.</p>", status_code=400)            # a filled honeypot is a bot
    missing = [k for k in ("fecha", "hora", "personas", "nombre", "email", "telefono") if not form.get(k)]
    if variant == "consent" and form.get("acepto") != "on":
        missing.append("acepto")
    if missing:
        return HTMLResponse(f"<p>Faltan campos: {escape(', '.join(missing))}.</p>", status_code=422)
    ref = _tv_ref(uuid.uuid4().hex[:6].upper())
    TEST_SUBMISSIONS.append({"variant": variant, "received_at": NOW().isoformat(), "reference": ref,
                             "fields": {k: v for k, v in form.items() if k != "token"}, "had_token": bool(form.get("token"))})
    del TEST_SUBMISSIONS[:-50]
    try:
        d = date.fromisoformat(form["fecha"])
        dias = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
        meses = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
        cuando = f"{dias[d.weekday()]} {d.day} de {meses[d.month - 1]} a las {form['hora']}"
    except ValueError:
        cuando = f"{form['fecha']} a las {form['hora']}"
    cancel = f"{public_base()}/api/booking/test-venue/cancel/{ref}"   # Sasha 99 · a cancel link, as real venues send
    return HTMLResponse(f"<html><body><h1>Reserva confirmada</h1><p>Confirmado: mesa para {escape(form['personas'])} personas el "
                        f"{escape(cuando)}, a nombre de {escape(form['nombre'])}.</p><p>Localizador: {ref}</p>"
                        f"<p>Para cancelar: {cancel}</p></body></html>")


@router.get("/test-venue/cancel/{ref}", response_class=HTMLResponse)
async def test_venue_cancel(ref: str):
    """The test venue's own cancel link: the booking in its book is marked cancelled, and its page says so."""
    hit = next((x for x in TEST_SUBMISSIONS if x["reference"] == ref), None)
    if hit is None and not _tv_ref_ok(ref):
        return HTMLResponse(f"<p>No encontramos la reserva {escape(ref)}.</p>", status_code=404)
    if hit is not None:
        hit["cancelled_at"] = NOW().isoformat()
    name = f" a nombre de {escape(hit['fields'].get('nombre', ''))}" if hit else ""
    return HTMLResponse(f"<html><body><h1>Reserva cancelada</h1><p>La reserva {escape(ref)}{name} queda cancelada. Gracias.</p></body></html>")


__all__ = ["router", "form_map", "read_form", "roles_for", "MemoryFormStore", "PostgresFormStore", "test_venue_url",
           "forms_status", "TEST_SUBMISSIONS"]
