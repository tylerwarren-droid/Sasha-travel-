"""CR 60 · S2's first powers, BUILT ONCE — pure, no I/O, no dependencies. The AgAPI sandbox's v1 operations
(agapi_service: messages.send_email, calendar.add_event) and Sasha's own tools (agapi/s2_tools.py) both call this module,
so a partner and Sasha get exactly the same read-back, the same bytes and the same hashes.

  EMAIL  from Sasha's own sending address (never the user's mailbox) to someone the user names. The read-back is the exact
         message (from, to, subject, every body line); the payload is what will be sent; any change → a new read-back.
         Sending needs the user's Approval (AP1–AP9; a question is never a yes) and it is irreversible.
  CALENDAR  a booked item as an RFC 5545 .ics file + "Add to calendar" links (Google, Outlook; Apple = the .ics). No OAuth:
         nothing leaves the user's account, so no Approval. Evidence = the event's sha256.
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple
from urllib.parse import quote, urlencode

EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+'-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}$")
SUBJECT_MAX, BODY_MAX, NAME_MAX = 200, 5000, 120


class Refused(ValueError):
    def __init__(self, path: str, rule: str, message: str):
        super().__init__(message)
        self.path, self.rule, self.message = path, rule, message


def canonical(v) -> str:
    """AgAPI v1 §4.1 for the values used here (strings, integers, lists, objects with [a-z0-9_] keys)."""
    return json.dumps(v, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256(v) -> str:
    return "sha256:" + hashlib.sha256(canonical(v).encode("utf-8")).hexdigest()


def text_sha256(s: str) -> str:
    return "sha256:" + hashlib.sha256(s.encode("utf-8")).hexdigest()


def _clean(s: str) -> str:
    """No control, bidi-override or zero-width characters; NFC. (Newlines kept only in a body — callers split them.)"""
    s = unicodedata.normalize("NFC", s or "")
    return re.sub("[\u0000-\u0008\u000b-\u001f\u007f-\u009f\u200b-\u200d\u202a-\u202e\u2066-\u2069\ufeff]", "", s)


# ── email ──────────────────────────────────────────────────────────────────────────────────────────────────────────────

def email_message(from_: str, to_address: str, to_name: Optional[str], subject: str, body: str, reply_to: Optional[str] = None) -> Dict:
    """The exact message, validated: one recipient, no header injection (CR/LF), sizes capped. → the payload that is sent."""
    to_address = (to_address or "").strip()
    if not EMAIL_RE.match(to_address) or len(to_address) > 254:
        raise Refused("/to/address", "email", "That isn't an email address.")
    name = _clean((to_name or "").strip())
    if any(c in name for c in "\r\n<>\"") or len(name) > NAME_MAX:
        raise Refused("/to/name", "name", "The recipient's name can't contain line breaks, quotes or angle brackets.")
    subject = _clean(subject or "").strip()
    if not subject or "\n" in subject or "\r" in subject or len(subject) > SUBJECT_MAX:
        raise Refused("/subject", "subject", f"The subject is one line of 1–{SUBJECT_MAX} characters.")
    body = _clean((body or "").replace("\r\n", "\n").replace("\r", "\n")).strip()
    if not body or len(body) > BODY_MAX:
        raise Refused("/body", "body", f"The message is 1–{BODY_MAX} characters.")
    msg = {"from": from_, "to": {"address": to_address, **({"name": name} if name else {})},
           "subject": subject, "body": body}
    if reply_to:
        msg["reply_to"] = reply_to
    return msg


def email_read_back(msg: Dict) -> List[str]:
    """What the user is shown — the WHOLE message, word for word, before any yes."""
    to = msg["to"]
    who = f"{to['name']} <{to['address']}>" if to.get("name") else to["address"]
    lines = [f"Send this email from {msg['from']} (Sasha's own address — not your mailbox).", f"To: {who}", f"Subject: {msg['subject']}"]
    lines += [ln if ln.strip() else "·" for ln in msg["body"].split("\n")]
    lines.append("Once sent it can't be unsent. Their reply comes to Sasha, and you'll see it word for word.")
    return lines


def email_body_sha256(msg: Dict) -> str:
    return text_sha256(msg["body"])


# ── calendar ───────────────────────────────────────────────────────────────────────────────────────────────────────────

def _utc(dt_iso: str) -> datetime:
    d = datetime.fromisoformat(dt_iso.replace("Z", "+00:00"))
    if d.tzinfo is None:
        raise Refused("/starts_at", "offset", "A time needs its UTC offset.")
    return d.astimezone(timezone.utc)


def event(uid: str, title: str, starts_at: str, ends_at: Optional[str], location: Optional[str], details: Optional[str]) -> Dict:
    """The event, normalised (UTC instants, cleaned text). Its sha256 is the evidence; the .ics and links are derived from it."""
    s = _utc(starts_at)
    e = _utc(ends_at) if ends_at else s + timedelta(hours=2)
    if e <= s:
        raise Refused("/ends_at", "order", "The event ends after it starts.")
    ev = {"uid": uid, "title": _clean(title).strip()[:200], "starts_at": s.strftime("%Y-%m-%dT%H:%M:%SZ"),
          "ends_at": e.strftime("%Y-%m-%dT%H:%M:%SZ")}
    if location:
        ev["location"] = _clean(location).strip()[:300]
    if details:
        ev["details"] = _clean(details).strip()[:1000]
    return ev


def _ics_text(s: str) -> str:
    return s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _fold(line: str) -> str:
    """RFC 5545 §3.1: lines of at most 75 octets, continued with CRLF + one space (never splitting a UTF-8 character)."""
    out, cur = [], b""
    for ch in line:
        b = ch.encode("utf-8")
        if len(cur) + len(b) > (75 if not out else 74):
            out.append(cur)
            cur = b""
        cur += b
    out.append(cur)
    return "\r\n ".join(x.decode("utf-8") for x in out)


def ics(ev: Dict, dtstamp: str) -> str:
    """One VEVENT, RFC 5545, CRLF line ends, folded. `dtstamp` (UTC, YYYYMMDDTHHMMSSZ) is passed in so the bytes are reproducible."""
    z = lambda iso: iso.replace("-", "").replace(":", "")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Kanoe//AgAPI v1//EN", "CALSCALE:GREGORIAN", "METHOD:PUBLISH", "BEGIN:VEVENT",
             f"UID:{ev['uid']}", f"DTSTAMP:{dtstamp}", f"DTSTART:{z(ev['starts_at'])}", f"DTEND:{z(ev['ends_at'])}",
             f"SUMMARY:{_ics_text(ev['title'])}"]
    if ev.get("location"):
        lines.append(f"LOCATION:{_ics_text(ev['location'])}")
    if ev.get("details"):
        lines.append(f"DESCRIPTION:{_ics_text(ev['details'])}")
    lines += ["END:VEVENT", "END:VCALENDAR"]
    return "\r\n".join(_fold(x) for x in lines) + "\r\n"


def calendar_links(ev: Dict, ics_url: str) -> Dict[str, str]:
    """"Add to calendar" for Google and Outlook (their own template links), and Apple/any app = the .ics file itself."""
    z = lambda iso: iso.replace("-", "").replace(":", "")
    g = {"action": "TEMPLATE", "text": ev["title"], "dates": f"{z(ev['starts_at'])}/{z(ev['ends_at'])}"}
    o = {"path": "/calendar/action/compose", "rru": "addevent", "subject": ev["title"], "startdt": ev["starts_at"], "enddt": ev["ends_at"]}
    if ev.get("details"):
        g["details"] = o["body"] = ev["details"]
    if ev.get("location"):
        g["location"] = o["location"] = ev["location"]
    return {"google": "https://calendar.google.com/calendar/render?" + urlencode(g, quote_via=quote),
            "outlook": "https://outlook.live.com/calendar/0/deeplink/compose?" + urlencode(o, quote_via=quote),
            "apple": ics_url, "ics": ics_url}


def event_for_flight(uid: str, carrier: str, flight_numbers: List[str], frm: str, to: str, departs: str, arrives: str,
                     reference: Optional[str]) -> Dict:
    return event(uid, f"Flight {' + '.join(flight_numbers)} {frm} → {to}", departs, arrives, f"{frm} airport",
                 f"{carrier} {' + '.join(flight_numbers)}" + (f" · booking reference {reference}" if reference else ""))


def event_for_table(uid: str, venue: str, address: Optional[str], at: str, party: int, reference: Optional[str]) -> Dict:
    return event(uid, f"Table for {party} at {venue}", at, None, address,
                 f"Booked for {party}" + (f" · reference {reference}" if reference else ""))


def event_for_stay(uid: str, name: str, address: Optional[str], check_in: str, nights: int, reference: Optional[str]) -> Dict:
    s = _utc(check_in)
    return event(uid, f"Stay at {name} ({nights} night{'s' if nights != 1 else ''})", s.isoformat(),
                 (s + timedelta(days=nights)).isoformat(), address, "Check-in" + (f" · reference {reference}" if reference else ""))


# ── CR 62 · WhatsApp to someone the user names ───────────────────────────────────────────────────────────────────────────
# WhatsApp's rule: a business may write free text only inside 24 hours of the person's own last message to it. To start a
# conversation (a new number, or a quiet one) it must send a template Meta has APPROVED. Ours asks the recipient whether they
# want the message at all: the user's own words go only after they reply (which also opens the window). Nobody is sent a
# stranger's free text, and the user's note never rides on an old yes.

E164_RE = re.compile(r"^\+[1-9][0-9]{7,14}$")
WA_TEXT_MAX, WA_PARAM_MAX = 1000, 60
WA_WINDOW = timedelta(hours=24)

#: The first-contact template, word for word what is submitted to Meta (category UTILITY). {{1}} the recipient's name,
#: {{2}} the user's name. The sandbox treats it as approved; Sasha only once its ContentSid is configured (Tyler submits it).
ON_BEHALF = {"name": "kanoe_on_behalf_v1", "language": "en", "params": 2,
             "body": "Hi {{1}}, this is Sasha, an assistant writing for {{2}}. {{2}} asked me to send you a message here. "
                     "Reply YES to receive it, or STOP and I won't write again."}
TEMPLATES = {ON_BEHALF["name"]: ON_BEHALF}

NO_FREE_TEXT = ("WhatsApp doesn't let me send a free-text message to someone who hasn't written to me in the last 24 hours. "
                "I can send them a short approved message asking if they'd like your note, and send your words once they reply.")
NO_TEMPLATE_YET = ("I can't start a WhatsApp conversation with a new number yet: the approved first message isn't set up. "
                   "I can email them instead, or you can message them yourself.")


def _phone(number: str) -> str:
    n = re.sub(r"[\s().-]", "", number or "")
    if n.startswith("00"):
        n = "+" + n[2:]
    if not E164_RE.match(n):
        raise Refused("/to/number", "e164", "That isn't a full international mobile number (like +44 7700 900123).")
    return n


def _param(s: str, path: str) -> str:
    s = re.sub(r"\s+", " ", _clean(s or "")).strip()
    if not s or len(s) > WA_PARAM_MAX or any(c in s for c in "{}"):
        raise Refused(path, "param", f"A name in the message is 1–{WA_PARAM_MAX} characters, one line.")
    return s


def window_open(last_inbound_at: Optional[str], now: str) -> bool:
    """Inside WhatsApp's 24-hour customer-service window: the recipient wrote to Sasha within the last 24 hours."""
    if not last_inbound_at:
        return False
    return _utc(now) - _utc(last_inbound_at) <= WA_WINDOW


def whatsapp_message(from_: str, to_number: str, to_name: Optional[str], *, text: Optional[str] = None,
                     template: Optional[str] = None, on_behalf_of: Optional[str] = None) -> Dict:
    """The exact WhatsApp, validated. EITHER free text (only inside the window — the caller checks) OR the approved
    first-contact template rendered with the two names. → the payload that is sent (and hashed for the read-back)."""
    number = _phone(to_number)
    name = _clean((to_name or "").strip())
    if any(c in name for c in "\r\n<>\"{}") or len(name) > NAME_MAX:
        raise Refused("/to/name", "name", "The recipient's name can't contain line breaks, quotes or brackets.")
    to = {"number": number, **({"name": name} if name else {})}
    if (text is None) == (template is None):
        raise Refused("/text", "one_of", "A WhatsApp is either your own words or the approved first message — one of the two.")
    if text is not None:
        body = _clean(text.replace("\r\n", "\n").replace("\r", "\n")).strip()
        if not body or len(body) > WA_TEXT_MAX:
            raise Refused("/text", "text", f"The message is 1–{WA_TEXT_MAX} characters.")
        return {"from": from_, "to": to, "kind": "text", "text": body}
    t = TEMPLATES.get(template or "")
    if not t:
        raise Refused("/template", "unknown_template", "That isn't an approved WhatsApp template.")
    params = [_param(name or "there", "/to/name"), _param(on_behalf_of or "", "/on_behalf_of")]
    body = t["body"]
    for i, p in enumerate(params, 1):
        body = body.replace("{{%d}}" % i, p)
    return {"from": from_, "to": to, "kind": "template", "template": {"name": t["name"], "language": t["language"], "params": params},
            "text": body}


def whatsapp_read_back(msg: Dict) -> List[str]:
    """What the user is shown — the WHOLE message, word for word, before any yes."""
    to = msg["to"]
    who = f"{to['name']} ({to['number']})" if to.get("name") else to["number"]
    lines = [f"Send this WhatsApp from {msg['from']} (Sasha's number — not your phone).", f"To: {who}"]
    if msg["kind"] == "template":
        lines.append("WhatsApp's approved first message (they haven't written to Sasha in the last 24 hours):")
    lines += [ln if ln.strip() else "·" for ln in msg["text"].split("\n")]
    if msg["kind"] == "template":
        lines.append("Your own note isn't sent now: only after they reply, and after you say yes to it again.")
    lines.append("Once sent it can't be unsent. Their reply comes to Sasha, and you'll see it word for word.")
    return lines


def whatsapp_body_sha256(msg: Dict) -> str:
    return text_sha256(msg["text"])


# ── CR 62 · the Activity view: one line per thing Sasha did, in our words only ───────────────────────────────────────────
# `line` is always one of the fixed sentences below (never a provider's or a person's words); the venue or the recipient
# travels separately as `about` (untrusted text). check: green ✓ done · red ✗ failed / not sent · amber … waiting.

ACTIVITY_LINES = {
    ("booking", "done"): "Booked", ("booking", "waiting"): "Waiting for payment", ("booking", "failed"): "Booking failed",
    ("booking", "requested"): "Asked them — waiting for their answer",
    ("payment", "done"): "Paid", ("payment", "failed"): "Payment failed",
    ("email", "done"): "Email sent", ("email", "not_sent"): "Email not sent", ("email", "failed"): "Email failed",
    ("whatsapp", "done"): "WhatsApp sent", ("whatsapp", "not_sent"): "WhatsApp not sent", ("whatsapp", "failed"): "WhatsApp failed",
    ("whatsapp_reply", "done"): "They replied on WhatsApp",
    ("calendar", "done"): "Added to your calendar",
    ("cancellation", "done"): "Cancelled", ("cancellation", "failed"): "Cancellation failed",
    ("cancellation", "waiting"): "Cancellation asked — waiting for their answer",
    # CR 63 · the Keep: every save, use, show and deletion (the item travels as its MASK, never its value)
    ("keep_save", "done"): "Saved to your Keep", ("keep_use", "done"): "Used from your Keep for a booking",
    ("keep_show", "done"): "Shown on your phone from your Keep", ("keep_delete", "done"): "Deleted from your Keep",
}
CHECK = {"done": "green", "failed": "red", "not_sent": "red", "waiting": "amber", "requested": "amber"}


def activity_entry(kind: str, state: str, at: str, *, ref: str, proof: Optional[str] = None) -> Dict:
    """One row of the Activity view. `ref` = the id behind it (an act, a booking); `proof` = its evidence id, if any."""
    line = ACTIVITY_LINES.get((kind, state))
    if line is None:
        raise Refused("/state", "activity", f"No activity line for {kind} {state}.")
    return {"kind": kind, "state": state, "check": CHECK[state], "line": line,
            "at": _utc(at).isoformat(timespec="microseconds").replace("+00:00", "Z"),   # exact, so newest-first is never a tie
            "ref": ref, **({"proof": proof} if proof else {})}


def activity_sorted(rows: List[Dict]) -> List[Dict]:
    """Newest first; equal times keep a stable order by ref."""
    return sorted(rows, key=lambda r: (r["at"], r["ref"]), reverse=True)
