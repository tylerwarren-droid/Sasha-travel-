"""CR 84 · RECEIPTS FROM GMAIL for /s2's subscription finder — read-only, through the person's existing Gmail connection (S-82's sealed
token, purpose gmail_read; Google's testing mode admits only its listed test users). Imported here; S1's mailbox is unchanged.

Reading narrowly:
  · ONE search, always this one: receipt / renewal / subscription subjects from the last 13 months (annual plans renew once a year).
    No code path lists the inbox without it.
  · Only the messages it returns are fetched; their text goes to AgAPI (which reads only receipts and keeps only the quoted facts and the
    email's sha256) and is dropped here as soon as the call returns — never written anywhere.
  · Its own consent sentence (CONSENT), asked in the chat and answered in a later turn, before the first search."""
from __future__ import annotations

import base64
import hashlib
import re
from typing import Dict, List, Optional

WORDS = ("receipt", "invoice", "renewal", "renews", "renew", "subscription", "membership", "\"your plan\"", "billing", "recibo", "factura",
         "suscripción", "renovación", "cuota", "membresía")
QUERY = "newer_than:400d subject:(" + " OR ".join(WORDS) + ")"
MAX = 60
CONSENT = ("I'll look in your Gmail only for receipt and renewal emails from the last 13 months, keep only each subscription's name, price and "
           "dates (each with the line it came from), and never store your emails. OK?")
CONSENT_VERSION = "s2-subs-1"


def consent() -> Dict[str, str]:
    return {"version": CONSENT_VERSION, "text": CONSENT, "text_sha256": "sha256:" + hashlib.sha256(CONSENT.encode()).hexdigest()}


def _html_text(payload: dict) -> str:
    out: List[str] = []

    def walk(p):
        if p.get("mimeType", "").startswith("text/html") and (p.get("body") or {}).get("data"):
            h = base64.urlsafe_b64decode(p["body"]["data"] + "==").decode("utf-8", "replace")
            h = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", h)
            h = re.sub(r'(?is)<a [^>]*href="(https?://[^"]+)"[^>]*>(.*?)</a>', r"\2 [\1]", h)   # a link's address after its words (AgAPI quotes it)
            out.append(re.sub(r"[ \t]+", " ", re.sub(r"<[^>]+>", "\n", h)))
        for q in p.get("parts") or []:
            walk(q)
    walk(payload or {})
    return re.sub(r"\n\s*\n+", "\n", "\n".join(out)).strip()


async def connected(account: str) -> bool:
    try:
        from booking_signer import mailbox as MB
        if MB.STORE is None:
            return False
        link = await MB.STORE.get_link(account)
        return bool(link and not link.get("needs_reconnect_at"))
    except Exception:
        return False


async def receipts(account: str) -> Optional[List[dict]]:
    """The receipt emails (memory only), or None when Gmail isn't connected / its token was refused."""
    from booking_signer import mailbox as MB
    from booking_signer.vault import crypto as VC
    if MB.STORE is None:
        return None
    link = await MB.STORE.get_link(account)
    if not link or link.get("needs_reconnect_at"):
        return None
    try:
        token = await VC.use_connection(account, link["vault_item_id"], purpose="gmail_read")
    except VC.UseRefused:
        return None
    status, j = await MB.GMAIL_HTTP("GET", f"{MB.GMAIL}/messages", token, {"q": QUERY, "maxResults": MAX})
    if status != 200:
        return None
    out = []
    for m in (j.get("messages") or [])[:MAX]:
        s, msg = await MB.GMAIL_HTTP("GET", f"{MB.GMAIL}/messages/{m['id']}", token, {"format": "full"})
        if s != 200:
            continue
        payload = msg.get("payload") or {}
        text = MB._body_text(payload) or _html_text(payload)
        out.append({"message_id": m["id"], "from": MB._header(payload, "From")[:200], "subject": MB._header(payload, "Subject")[:300],
                    "date": MB._header(payload, "Date")[:40], "text": text[:6000]})
    return out
