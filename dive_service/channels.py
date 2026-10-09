"""DIVE step 5 · THE CHANNELS (EU 212 model.md §1 ladder; bundles.md §2). Each send → evidence fields; an undelivered send is
`unreachable` — NEVER `declined` (only a supplier's own NO is a no). Free text from a model never goes to a supplier: every message
is a fixed template with slots.

  whatsapp  through the AgAPI sandbox's public API (messages.send_whatsapp → messages.replies). AgAPI 1.1 has no way to send a
            supplier message under a BUNDLE's approval, so in TEST mode DIVE bridges each send with sandbox.simulate_approval
            ("TEST BRIDGE", logged on the evidence) — the gap EU's 1.2 must close. The sandbox captures; it never sends.
            CR 67: REAL through DIVE's own Twilio account only when switched on AND the number is allow-listed (hooks.py).
  email     a REAL send only with a sending key AND an allow-listed address (Tyler: "our own addresses only"); otherwise captured,
            and said so. Replies: recorded by the operator / sandbox.supplier_reply; CR 67: /hooks/resend/inbound when switched on.
  web_form  the one known form (the taverna's, the sandbox's public fixture): fields filled, the confirmation page read (#reference),
            the page hashed. A refusal ON the page is the supplier's answer (declined); a page that can't be read is unreachable.
  feed      the fixture hotel feed `feed:sandbox-hotels` (instant: search → hold → book), inside DIVE.
"""
from __future__ import annotations

import re
import secrets
from datetime import datetime, timedelta
from typing import Any, Awaitable, Callable, Dict, Optional, Tuple
from zoneinfo import ZoneInfo

from . import config, rules as R, sandbox as SB
from .model import DiveError, evidence
from .store import Store, dumps, loads, ts

TEMPLATES = {
    "request": {"en": "{operator} booking request: {what}, {when}. Ref {ref}. Reply YES or NO.",
                "el": "Αίτημα κράτησης {operator}: {what}, {when}. Κωδ. {ref}. Απαντήστε ΝΑΙ ή ΟΧΙ."},
    "cancel": {"en": "{operator}: booking {ref} ({what}, {when}) is cancelled by the customer. Sorry, and thank you.",
               "el": "{operator}: η κράτηση {ref} ({what}, {when}) ακυρώθηκε από τον πελάτη. Συγγνώμη και ευχαριστούμε."},
    "release": {"en": "{operator}: booking {ref} is cancelled — the group isn't coming. Sorry, and thank you.",
                "el": "{operator}: η κράτηση {ref} ακυρώνεται. Συγγνώμη και ευχαριστούμε."},
}


def template(kind: str, lang: str, **slots) -> str:
    t = TEMPLATES[kind].get(lang) or TEMPLATES[kind]["en"]
    return t.format(**slots)


# ── WhatsApp, through the sandbox ───────────────────────────────────────────────────────────────────────────────────────

async def _operator_end_user(s: Store, operator: dict) -> Optional[str]:
    if operator.get("sandbox_end_user"):
        return operator["sandbox_end_user"]
    r = await SB.call("users.register", {"external_ref": f"dive-{operator['slug']}"}, idem=True)
    if not r.get("ok"):
        return None
    uid = r["result"]["end_user_id"]
    s.x("update operators set sandbox_end_user = ? where id = ?", uid, operator["id"])
    return uid


async def whatsapp_send(s: Store, operator: dict, number: str, name: str, text: Optional[str]) -> Dict[str, Any]:
    """→ {ok, reference, sent_at, kind (text|template), sandbox_evidence_id, bridge} or {ok: False, unreachable, why}."""
    if config.whatsapp_real_to(number):          # CR 67 · REAL only when switched on AND the number is allow-listed
        return await _whatsapp_real(s, number, text)
    uid = await _operator_end_user(s, operator)
    if not uid:
        return {"ok": False, "unreachable": True, "why": "the AgAPI sandbox didn't answer"}
    msg = {"end_user": uid, "to": {"number": number, "name": name[:120]}}
    body = {**msg, "text": text} if text else {**msg, "on_behalf_of": operator["name"][:60]}
    r = await SB.call("messages.send_whatsapp", body, idem=True)
    if not r.get("ok") and (r.get("error") or {}).get("details", {}).get("rule") == "whatsapp_first_contact":
        body = {**msg, "on_behalf_of": operator["name"][:60]}          # their window is closed: the approved first message only
        r = await SB.call("messages.send_whatsapp", body, idem=True)
    if r.get("ok"):
        return {"ok": True, **_sent(r["result"]), "bridge": None}
    if (r.get("error") or {}).get("code") != "approval_required":
        return {"ok": False, "unreachable": True, "why": (r.get("error") or {}).get("code", "upstream")}
    rb = r["error"]["details"]["read_back_id"]
    a = await SB.call("sandbox.simulate_approval", {"read_back_id": rb, "said": "Yes, send it."}, idem=True)   # TEST BRIDGE (1.2 gap)
    if not a.get("ok"):
        return {"ok": False, "unreachable": True, "why": (a.get("error") or {}).get("code", "approval")}
    r = await SB.call("messages.send_whatsapp", body, approval=a["result"]["approval_id"], idem=True)
    if not r.get("ok"):
        return {"ok": False, "unreachable": True, "why": (r.get("error") or {}).get("code", "upstream")}
    s.x("insert into captured (channel, to_, body, real, at) values ('whatsapp', ?, ?, ?, ?)", number,
        text or f"[first contact on behalf of {operator['name']}]", 0, ts())
    return {"ok": True, **_sent(r["result"]), "bridge": "sandbox.simulate_approval (TEST BRIDGE — AgAPI 1.2 must define bundle-authorised sends)"}


def _sent(res: dict) -> Dict[str, Any]:
    return {"reference": res["outcome"]["reference"], "sent_at": res["message"]["sent_at"], "kind": res["message"]["kind"],
            "body_sha256": res["message"]["body_sha256"], "sandbox_evidence_id": res["evidence_id"], "intent_id": res["intent_id"]}


async def whatsapp_replies(s: Store, operator: dict, number: str) -> list:
    """Newest first: the sandbox's replies (test) and — CR 67 — what arrived on the real hook from this number (signed, allow-listed)."""
    uid = await _operator_end_user(s, operator)
    r = await SB.call("messages.replies", {"end_user": uid, "number": number}) if uid else {"ok": False}
    out = r["result"]["replies"] if r.get("ok") else []
    real = [{"reply_id": x["provider_id"], "received_at": x["received_at"], "text": R.wrap(x["text"], "whatsapp_supplier", x["received_at"][:19] + "Z")}
            for x in s.q("select * from inbound where channel = 'whatsapp' and address = ? order by id desc limit 20", config.norm_number(number))]
    return sorted(out + real, key=lambda x: x["received_at"], reverse=True) if real else out


# ── CR 67 · REAL sends and what comes back (OFF unless switched on; docs/agapi/dive/switch-on-list.md) ─────────────────────

STOP_WORDS = {"stop", "stopall", "unsubscribe", "end", "quit", "στοπ", "σταματηστε"}
START_WORDS = {"start", "unstop", "yes start"}
WINDOW_S = 24 * 3600


def _first_words(text: str) -> str:
    import unicodedata
    t = "".join(c for c in unicodedata.normalize("NFD", (text or "").strip().lower()) if unicodedata.category(c) != "Mn")
    return re.sub(r"[^\w ]+", " ", t).strip()


def is_stop(text: str) -> bool:
    """A STOP is 'no more messages to me' — never a supplier's no to a booking (the leg is not declined)."""
    return _first_words(text) in STOP_WORDS


def is_start(text: str) -> bool:
    return _first_words(text) in START_WORDS


def opted_out(s: Store, channel: str, address: str) -> bool:
    return bool(s.one("select 1 from opt_outs where channel = ? and address = ?", channel, _addr(channel, address)))


def _addr(channel: str, address: str) -> str:
    return config.norm_number(address) if channel == "whatsapp" else (address or "").strip().lower()


def window_open(s: Store, number: str) -> bool:
    """WhatsApp's 24-hour rule: free text only within 24 h of THEIR last message (Jon says hi on the morning of the run)."""
    last = s.one("select max(received_at) t from inbound where channel = 'whatsapp' and address = ?", config.norm_number(number))["t"]
    from .store import now, parse_ts
    return bool(last) and (now() - parse_ts(last)).total_seconds() < WINDOW_S


async def _http(method: str, url: str, *, headers: Optional[dict] = None, data: Optional[dict] = None,
                auth: Optional[Tuple[str, str]] = None) -> Tuple[int, Any]:
    import httpx
    async with httpx.AsyncClient(timeout=httpx.Timeout(20.0)) as c:
        r = await c.request(method, url, headers=headers, data=data, auth=auth)
    try:
        return r.status_code, r.json()
    except ValueError:
        return r.status_code, {}


HTTP: Callable[..., Awaitable[Tuple[int, Any]]] = _http     # tests replace it: no request leaves a test


async def _whatsapp_real(s: Store, number: str, text: Optional[str]) -> Dict[str, Any]:
    n = config.norm_number(number)
    if opted_out(s, "whatsapp", n):
        return {"ok": False, "unreachable": True, "why": "they sent STOP: no more WhatsApp to them (not a no — ask by phone)"}
    if not text:
        return {"ok": False, "unreachable": True, "why": "a first message needs an approved template; ask them to message first"}
    if not window_open(s, n):
        return {"ok": False, "unreachable": True, "why": "outside WhatsApp's 24-hour window: ask them to send 'hi' first"}
    try:
        st, body = await HTTP("POST", f"https://api.twilio.com/2010-04-01/Accounts/{config.TWILIO_SID}/Messages.json",
                              data={"From": "whatsapp:" + config.norm_number(config.WHATSAPP_FROM), "To": "whatsapp:" + n, "Body": text[:1500]},
                              auth=(config.TWILIO_SID, config.TWILIO_TOKEN))
    except Exception as e:
        return {"ok": False, "unreachable": True, "why": type(e).__name__}
    if st not in (200, 201) or not str((body or {}).get("sid") or "").startswith(("SM", "MM")):
        return {"ok": False, "unreachable": True, "why": f"Twilio answered HTTP {st}" + (f" ({body.get('code')})" if isinstance(body, dict) and body.get("code") else "")}
    s.x("insert into captured (channel, to_, body, real, at) values ('whatsapp', ?, ?, 1, ?)", n, text, ts())
    return {"ok": True, "reference": body["sid"], "sent_at": ts()[:19] + "Z", "kind": "text", "body_sha256": R.text_sha256(text),
            "real": True, "bridge": None}


async def email_received_text(provider_id: str) -> Optional[str]:
    """Resend's email.received carries no body: read it (a key that can read received mail; DIVE's own Resend account)."""
    key = config.RESEND_READ_KEY or config.RESEND_KEY
    st, body = await HTTP("GET", f"https://api.resend.com/emails/receiving/{provider_id}", headers={"Authorization": f"Bearer {key}"})
    return (body or {}).get("text") if st == 200 and isinstance(body, dict) else None


_QUOTE = re.compile(r"^\s*(>|On .{0,200}wrote:\s*$|Στις .{0,200}έγραψε|-{2,}\s*Original Message|From:\s|Sent from my )", re.I)


def top_reply(text: str) -> str:
    """Only what they typed: the quoted request below ('Reply YES or NO') must never be read as their answer."""
    out = []
    for line in (text or "").replace("\r\n", "\n").split("\n"):
        if _QUOTE.match(line):
            break
        out.append(line)
    return "\n".join(out).strip()


async def whatsapp_simulate_reply(number: str, text: str) -> Dict[str, Any]:
    return await SB.call("sandbox.simulate_reply", {"number": number, "text": text})


# ── email ───────────────────────────────────────────────────────────────────────────────────────────────────────────────

async def email_send(s: Store, to: str, subject: str, text: str) -> Dict[str, Any]:
    """REAL only with a key AND an allow-listed address; otherwise captured (and the result says so)."""
    to_l = to.strip().lower()
    if opted_out(s, "email", to_l):              # CR 67 · they wrote STOP: nothing more to them, real or captured
        return {"ok": False, "unreachable": True, "why": "they asked us to stop emailing (not a no — ask by phone)"}
    if config.RESEND_KEY and config.EMAIL_FROM and to_l in config.EMAIL_ALLOW:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=httpx.Timeout(20.0)) as c:
                r = await c.post("https://api.resend.com/emails", headers={"Authorization": f"Bearer {config.RESEND_KEY}"},
                                 json={"from": config.EMAIL_FROM, "to": [to], "subject": subject, "text": text})
            if r.status_code in (200, 201) and (r.json() or {}).get("id"):
                s.x("insert into captured (channel, to_, body, real, at) values ('email', ?, ?, 1, ?)", to, subject, ts())
                return {"ok": True, "reference": r.json()["id"], "real": True, "sent_at": ts()[:19] + "Z", "body_sha256": R.text_sha256(text)}
            return {"ok": False, "unreachable": True, "why": f"the mail service answered HTTP {r.status_code}"}
        except Exception as e:
            return {"ok": False, "unreachable": True, "why": type(e).__name__}
    s.x("insert into captured (channel, to_, body, real, at) values ('email', ?, ?, 0, ?)", to, f"Subject: {subject}\n\n{text}", ts())
    return {"ok": True, "reference": "captured_" + secrets.token_hex(8), "real": False, "sent_at": ts()[:19] + "Z",
            "body_sha256": R.text_sha256(text), "note": "captured, not sent (no key, or not an allow-listed address)"}


# ── web form: the taverna's (one known form) ────────────────────────────────────────────────────────────────────────────

async def _post_form(url: str, fields: Dict[str, str]) -> Tuple[int, str]:
    import httpx
    async with httpx.AsyncClient(timeout=httpx.Timeout(20.0), follow_redirects=False) as c:
        r = await c.post(url, data=fields, headers={"user-agent": "AgAPI-DIVE-Austen/1 (books for the operator)"})
    return r.status_code, r.text


POST_FORM: Callable[[str, Dict[str, str]], Awaitable[Tuple[int, str]]] = _post_form   # tests replace it
TAVERNA_SLOTS = ["13:00", "13:30", "14:00", "14:30", "15:00", "20:00", "20:30", "21:00", "21:30", "22:00", "22:30"]


async def form_submit(form_url: str, local_dt: datetime, party: int, name: str) -> Dict[str, Any]:
    """→ {state confirmed|declined|unreachable, reference?, words, page_sha256, fields_sha256}."""
    action = form_url.rstrip("/") + "/book"
    hhmm = local_dt.strftime("%H:%M")
    fields = {"date": local_dt.date().isoformat(), "time": hhmm, "party_size": str(party), "name": name[:80]}
    fsha = R.sha256(fields)
    if hhmm not in TAVERNA_SLOTS:
        return {"state": "unreachable", "words": f"{hhmm} isn't one of the form's times — not submitted", "fields_sha256": fsha}
    try:
        st, page = await POST_FORM(action, fields)
    except Exception as e:
        return {"state": "unreachable", "words": f"the form didn't answer ({type(e).__name__})", "fields_sha256": fsha}
    psha = R.text_sha256(page)
    ref = re.search(r'id="reference">([A-Z]{2,4}-[0-9A-F]{4,8})<', page)
    if st in (200, 201) and ref:
        return {"state": "confirmed", "reference": ref.group(1), "words": "Booking confirmed on their page", "page_sha256": psha, "fields_sha256": fsha}
    refusal = re.search(r'id="refusal">([^<]{1,300})<', page)
    if st in (400, 409) and refusal:   # the supplier's OWN page said no — their answer
        import html as _h
        return {"state": "declined", "words": _h.unescape(refusal.group(1)), "page_sha256": psha, "fields_sha256": fsha}
    return {"state": "unreachable", "words": f"the form answered HTTP {st} without a confirmation or a refusal", "page_sha256": psha,
            "fields_sha256": fsha}


# ── feed: the fixture hotel feed (instant) ──────────────────────────────────────────────────────────────────────────────

FEED = {"feed:sandbox-hotels": {"Hotel Kyma View": {"room": "Double, sea view", "per_night_minor": 14000, "currency": "EUR"}}}
_HOLDS: Dict[str, dict] = {}
FEED_DOWN = False                       # tests (and the test drawer) can take the feed down: an outage, never "no rooms"


def feed_hold(feed: str, hotel: str, nights: int) -> Dict[str, Any]:
    if FEED_DOWN:
        return {"state": "unreachable", "words": "the hotel feed isn't answering"}
    h = FEED.get(feed, {}).get(hotel)
    if not h:
        return {"state": "declined", "words": "the feed has no such hotel"}
    ref = "HOLD-" + secrets.token_hex(3).upper()
    _HOLDS[ref] = {"hotel": hotel, "nights": nights, "booked": None}
    return {"state": "held", "hold": ref, "amount_minor": h["per_night_minor"] * nights, "words": f"{h['room']} held"}


def feed_book(hold: str) -> Dict[str, Any]:
    if FEED_DOWN:
        return {"state": "unreachable", "words": "the hotel feed isn't answering"}
    h = _HOLDS.get(hold)
    if not h:
        return {"state": "unreachable", "words": "the hold is gone"}
    h["booked"] = h["booked"] or "HKV-" + secrets.token_hex(3).upper()
    return {"state": "booked", "reference": h["booked"], "words": f"Booked, reference {h['booked']}"}


def feed_release(hold: str) -> None:
    _HOLDS.pop(hold, None)


# ── quiet hours (Tyler: 22:00–08:00 Mykonos) ────────────────────────────────────────────────────────────────────────────

def send_time(now_utc: datetime, quiet: Optional[str], tz: str = config.TIMEZONE) -> datetime:
    """When a supplier message may go: now, or — inside quiet hours — at their end (08:00 local)."""
    if not quiet:
        return now_utc
    start, end = quiet.split("-")
    local = now_utc.astimezone(ZoneInfo(tz))
    hm = local.strftime("%H:%M")
    inside = (hm >= start or hm < end) if start > end else (start <= hm < end)
    if not inside:
        return now_utc
    h, m = map(int, end.split(":"))
    nxt = local.replace(hour=h, minute=m, second=0, microsecond=0)
    if nxt <= local:
        nxt += timedelta(days=1)
    return nxt.astimezone(now_utc.tzinfo)
