"""DIVE step 5 · THE CHANNELS (EU 212 model.md §1 ladder; bundles.md §2). Each send → evidence fields; an undelivered send is
`unreachable` — NEVER `declined` (only a supplier's own NO is a no). Free text from a model never goes to a supplier: every message
is a fixed template with slots.

  whatsapp  through the AgAPI sandbox's public API (messages.send_whatsapp → messages.replies). AgAPI 1.1 has no way to send a
            supplier message under a BUNDLE's approval, so in TEST mode DIVE bridges each send with sandbox.simulate_approval
            ("TEST BRIDGE", logged on the evidence) — the gap EU's 1.2 must close. The sandbox captures; it never sends.
  email     a REAL send only with a sending key AND an allow-listed address (Tyler: "our own addresses only"); otherwise captured,
            and said so. Replies: recorded by the operator / sandbox.supplier_reply (inbound mail is not built yet).
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
    uid = await _operator_end_user(s, operator)
    r = await SB.call("messages.replies", {"end_user": uid, "number": number}) if uid else {"ok": False}
    return r["result"]["replies"] if r.get("ok") else []


async def whatsapp_simulate_reply(number: str, text: str) -> Dict[str, Any]:
    return await SB.call("sandbox.simulate_reply", {"number": number, "text": text})


# ── email ───────────────────────────────────────────────────────────────────────────────────────────────────────────────

async def email_send(s: Store, to: str, subject: str, text: str) -> Dict[str, Any]:
    """REAL only with a key AND an allow-listed address; otherwise captured (and the result says so)."""
    to_l = to.strip().lower()
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
