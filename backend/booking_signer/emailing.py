"""S-36 · THE EMAIL RUNG — the smallest honest version.

  1. Sasha composes the exact email (to, cc, from, reply-to, subject, body) and READS IT BACK.
  2. The yes binds to the sha256 of exactly that email.
  3. It is sent through Resend, and RESEND'S ANSWER IS CHECKED: "sent" means Resend answered HTTP 200 with an email
     id — i.e. accepted for delivery. It never means "delivered", and never "booked".
  4. Replies go to act-{email_id}@<SASHA_INBOUND_DOMAIN>, an address she controls. Resend's inbound webhook (svix-
     signed) posts each one; it is matched BY THE ADDRESS IT WAS SENT TO, never by guessing from content, and shown
     word for word. Mail matching no email is quarantined.

The guest is BCC'd, never CC'd (founder, S-52, superseding S-32): they receive a copy of exactly what was sent, and the
venue sees only Sasha's address. The read-back says so before the yes.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import time as _time
from dataclasses import dataclass

from .wordings import DISCLOSURE
from datetime import date, time
from typing import Any, Awaitable, Callable, Mapping, Optional

RESEND_SEND_URL = "https://api.resend.com/emails"
RESEND_RECEIVED_URL = "https://api.resend.com/emails/receiving/{id}"
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
SVIX_TOLERANCE_S = 300


class EmailRefused(Exception):
    def __init__(self, rule: str, message: str) -> None:
        super().__init__(f"{rule}: {message}")
        self.rule = rule


def _env(n: str) -> str:
    return os.getenv(n, "").strip()


#: ⚠ Sasha's OWN Resend key — never `RESEND_API_KEY`, which backend/app/api/payments.py reads for its own sends. Two
#: keys, so neither sender's scope, domain or rotation can move the other's (P807nu §3).
KEY_VAR = "SASHA_RESEND_API_KEY"


def act_address(email_id: str) -> str:
    return f"act-{email_id}@{_env('SASHA_INBOUND_DOMAIN')}"


_ACT = re.compile(r"act-([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})@([A-Za-z0-9.-]+)", re.I)


def act_id_of(addresses: Any) -> Optional[str]:
    """The email id an inbound message was sent to — only on OUR inbound domain."""
    dom = _env("SASHA_INBOUND_DOMAIN").lower()
    for a in addresses if isinstance(addresses, list) else [addresses]:
        m = _ACT.search(str(a or ""))
        if m and m.group(2).lower() == dom:
            return m.group(1).lower()
    return None


# ── the words ───────────────────────────────────────────────────────────────────────────────────

# S-52 · the disclosure is the FIRST line (wordings.DISCLOSURE); the guest is BCC'd, so the body never names their
# address — the venue sees only Sasha's.
_T = {
    "en": ("Table request — {n} on {d} at {t}",
           "Hello, this is {disclosure}, writing on behalf of {who} to ask for a table for {n} on {d} at {t}.\n\n"
           "Could you reply to this email to confirm, or to tell us if that isn't possible?\n\n"
           "We can't agree to a deposit or a different time by email on {guest_short}'s behalf — if either is needed, please say so and they will decide.\n\n"
           "Thank you,\nSasha (AI concierge, Kanoe Technologies SL), for {guest_short}"),
    "es": ("Solicitud de mesa — {n} el {d} a las {t}",
           "Hola, soy {disclosure}, y le escribo de parte de {who} para pedir una mesa para {n} el {d} a las {t}.\n\n"
           "¿Podrían responder a este correo para confirmarlo, o decirnos si no es posible?\n\n"
           "No podemos aceptar por correo una señal ni otro horario en nombre de {guest_short}; si hiciera falta, indíquenlo y lo decidirá.\n\n"
           "Gracias,\nSasha (concierge de IA, Kanoe Technologies SL), en nombre de {guest_short}"),
    "pt": ("Pedido de mesa — {n} a {d} às {t}",
           "Olá, sou a {disclosure}, e escrevo em nome de {who} para pedir uma mesa para {n} a {d} às {t}.\n\n"
           "Poderiam responder a este email a confirmar, ou a dizer-nos se não for possível?\n\n"
           "Não podemos aceitar por email um sinal nem outro horário em nome de {guest_short}; se for necessário, indiquem-no e decidirá.\n\n"
           "Obrigada,\nSasha (concierge de IA, Kanoe Technologies SL), em nome de {guest_short}"),
    "fr": ("Demande de table — {n} le {d} à {t}",
           "Bonjour, ici {disclosure}. J'écris de la part de {who} pour demander une table pour {n} le {d} à {t}.\n\n"
           "Pourriez-vous répondre à cet e-mail pour confirmer, ou nous dire si ce n'est pas possible ?\n\n"
           "Nous ne pouvons pas accepter par e-mail un acompte ni un autre horaire au nom de {guest_short} ; si c'est nécessaire, dites-le et il ou elle décidera.\n\n"
           "Merci,\nSasha (concierge IA, Kanoe Technologies SL), pour {guest_short}"),
    "it": ("Richiesta tavolo — {n} il {d} alle {t}",
           "Buongiorno, sono {disclosure}. Scrivo per conto di {who} per chiedere un tavolo per {n} il {d} alle {t}.\n\n"
           "Potreste rispondere a questa email per confermare, o dirci se non è possibile?\n\n"
           "Non possiamo accettare via email una caparra né un altro orario per conto di {guest_short}; se serve, ditecelo e deciderà.\n\n"
           "Grazie,\nSasha (concierge IA, Kanoe Technologies SL), per conto di {guest_short}"),
    "de": ("Tischanfrage — {n} am {d} um {t}",
           "Guten Tag, hier ist {disclosure}. Ich schreibe im Auftrag von {who} und frage einen Tisch für {n} am {d} um {t} an.\n\n"
           "Könnten Sie auf diese E-Mail antworten, um zu bestätigen oder uns zu sagen, falls es nicht möglich ist?\n\n"
           "Eine Anzahlung oder eine andere Uhrzeit können wir per E-Mail nicht im Namen von {guest_short} zusagen; falls nötig, sagen Sie es bitte, dann entscheidet {guest_short}.\n\n"
           "Vielen Dank,\nSasha (KI-Concierge, Kanoe Technologies SL), im Auftrag von {guest_short}"),
}
_WHO = {"en": "the {s} family", "es": "la familia {s}", "pt": "a família {s}", "fr": "la famille {s}", "it": "la famiglia {s}", "de": "Familie {s}"}
_PEOPLE = {"en": "{n}", "es": "{n} personas", "pt": "{n} pessoas", "fr": "{n} personnes", "it": "{n} persone", "de": "{n} Personen"}
#: S-64 · one person is one person: "1 persona", never "1 personas" (founder, Sasha 44)
_PERSON = {"en": "{n}", "es": "{n} persona", "pt": "{n} pessoa", "fr": "{n} personne", "it": "{n} persona", "de": "{n} Person"}


@dataclass(frozen=True)
class EmailParticulars:
    on: date
    at: time
    party: int
    name: str
    guest_email: str


def parse_email_particulars(body: Mapping[str, Any], parse_call) -> EmailParticulars:
    p = parse_call(body)   # the same strict date/time/party/name rules as a call
    g = body.get("email")
    if not isinstance(g, str) or not _EMAIL.fullmatch(g.strip()):
        raise EmailRefused("guest_email_invalid", "the guest's email address is required: they are BCC'd, so they hold what was sent")
    if any(k in body for k in ("to", "venue_email", "recipient")):
        raise EmailRefused("recipient_from_request", "the venue's address is never taken from the request — it comes from what was read")
    return EmailParticulars(on=p.on, at=p.at, party=p.party, name=p.name, guest_email=g.strip().lower())


def compose(lang: str, venue_name: str, venue_email: str, p: EmailParticulars, email_id: str) -> dict:
    lang = lang if lang in _T else "en"
    subj_t, body_t = _T[lang]
    surname = p.name.split()[-1]
    who = _WHO[lang].format(s=surname) if p.party > 1 else p.name
    d = p.on.isoformat()
    t = p.at.strftime("%H:%M")
    n = (_PERSON if p.party == 1 else _PEOPLE)[lang].format(n=p.party)
    email = {
        "from": _env("SASHA_EMAIL_FROM"),
        "to": venue_email,
        # S-52 (supersedes S-32): BCC, never CC — the venue never sees the guest's address
        "bcc": p.guest_email,
        "reply_to": act_address(email_id),
        "subject": subj_t.format(n=n, d=d, t=t),
        # the guest's address is never in the body: it is not the venue's to see
        "text": body_t.format(disclosure=DISCLOSURE.get(lang, DISCLOSURE["en"]), who=who, n=n, d=d, t=t, guest_short=p.name),
    }
    return email


def email_sha256(email: Mapping[str, Any]) -> str:
    return hashlib.sha256(json.dumps(dict(email), sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def read_back(email: Mapping[str, Any], venue_name: str, source_label: str) -> list:
    return [
        f"I'll email {venue_name} at {email['to']} — the address on {source_label} — from {email['from']}.",
        f"You're copied privately (BCC) at {email['bcc']}: you'll get a copy of what I send, and they won't see your address — they'll only have mine.",
        f"Their reply comes to me at {email['reply_to']}; I'll show it to you word for word, and it'll be in your itinerary.",
        f"Subject: {email['subject']}",
        email["text"],
        "Shall I send it?",
    ]


# ── sending: Resend's answer is READ ────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Sent:
    sent: bool
    provider_id: Optional[str]
    http_status: Optional[int]
    answer: Any
    why: Optional[str]


Http = Callable[..., Awaitable[Any]]


async def send(http: Http, email: Mapping[str, Any]) -> Sent:
    """⛔ `sent` is True ONLY when Resend answered HTTP 200 with an email id. Everything else is not sent, with Resend's
    own words. "Sent" means accepted for delivery — not delivered, and not booked."""
    key = _env(KEY_VAR)
    payload = {"from": email["from"], "to": [email["to"]], "subject": email["subject"], "text": email["text"]}
    if email.get("bcc"):
        payload["bcc"] = [email["bcc"]]
    if email.get("reply_to"):
        payload["reply_to"] = email["reply_to"]   # S-55 · the opt-in confirmation has neither
    try:
        r = await http("POST", RESEND_SEND_URL, headers={"authorization": f"Bearer {key}", "content-type": "application/json"}, json=payload)
    except Exception as e:
        return Sent(False, None, None, None, f"the mail service could not be reached: {type(e).__name__}: {e}")
    try:
        body = r.json()
    except Exception:
        return Sent(False, None, r.status_code, None, f"the mail service answered HTTP {r.status_code} with a body that is not JSON")
    eid = body.get("id") if isinstance(body, dict) else None
    if r.status_code == 200 and isinstance(eid, str) and eid.strip():
        return Sent(True, eid.strip(), 200, body, None)
    words = (body.get("message") or body.get("name") or "no message") if isinstance(body, dict) else str(body)[:200]
    return Sent(False, None, r.status_code, body, f"the mail service did not accept it (HTTP {r.status_code}): {words}")


# ── inbound: svix-verified, matched by address ──────────────────────────────────────────────────

def verify_svix(secret: str, headers: Mapping[str, str], body: bytes, now: Optional[float] = None) -> bool:
    """Svix's scheme (Resend's webhooks): HMAC-SHA256 over "{id}.{timestamp}.{body}" with the base64 key after
    `whsec_`; the header holds space-separated "v1,<base64>" entries; the timestamp within five minutes."""
    sid, ts, sig = headers.get("svix-id"), headers.get("svix-timestamp"), headers.get("svix-signature")
    if not (secret and sid and ts and sig):
        return False
    try:
        if abs((now if now is not None else _time.time()) - int(ts)) > SVIX_TOLERANCE_S:
            return False
        key = base64.b64decode(secret.removeprefix("whsec_"))
    except Exception:
        return False
    expected = base64.b64encode(hmac.new(key, f"{sid}.{ts}.".encode() + body, hashlib.sha256).digest()).decode()
    return any(hmac.compare_digest(expected, part.split(",", 1)[1]) for part in sig.split() if part.startswith("v1,"))


async def fetch_received(http: Http, provider_id: str) -> dict:
    r = await http("GET", RESEND_RECEIVED_URL.format(id=provider_id), headers={"authorization": f"Bearer {_env(KEY_VAR)}"})
    if r.status_code != 200:
        raise EmailRefused("received_email_unavailable", f"the mail service answered HTTP {r.status_code} for {provider_id}")
    return r.json()
