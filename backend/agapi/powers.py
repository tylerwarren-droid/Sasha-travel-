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
