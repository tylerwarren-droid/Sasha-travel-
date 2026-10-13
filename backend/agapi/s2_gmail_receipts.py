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


class Unreachable(Exception):
    """Sasha 259 · Gmail didn't answer (a connection timeout, an outage) — said as that, never a failed turn."""


#: Sasha 259 · found on Tyler's /s2 (13 Oct ~12:12 UTC, "I lost the connection there"): up to 60 receipts were fetched ONE AFTER
#: ANOTHER — 30–90 s on a real inbox, past the page's stall and close to the turn's deadline. Fetched CONCURRENTLY now, ten at a time.
FETCH_AT_ONCE = 10


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
    try:
        status, j = await MB.GMAIL_HTTP("GET", f"{MB.GMAIL}/messages", token, {"q": QUERY, "maxResults": MAX})
    except Exception as e:   # the list itself didn't answer: Gmail is unreachable just now (said, never a failed turn)
        raise Unreachable(type(e).__name__) from e
    if status != 200:
        return None
    import asyncio
    gate = asyncio.Semaphore(FETCH_AT_ONCE)

    async def one(m: dict) -> Optional[dict]:
        async with gate:
            try:
                s, msg = await MB.GMAIL_HTTP("GET", f"{MB.GMAIL}/messages/{m['id']}", token, {"format": "full"})
            except Exception:
                return None   # one email that didn't come: left out, the rest read
        if s != 200:
            return None
        payload = msg.get("payload") or {}
        text = MB._body_text(payload) or _html_text(payload)
        return {"message_id": m["id"], "from": MB._header(payload, "From")[:200], "subject": MB._header(payload, "Subject")[:300],
                "date": MB._header(payload, "Date")[:40], "text": text[:6000]}
    got = await asyncio.gather(*[one(m) for m in (j.get("messages") or [])[:MAX]])
    return [x for x in got if x]   # in the list's own order
