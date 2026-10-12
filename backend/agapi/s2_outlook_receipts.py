"""CR 86 · RECEIPTS FROM OUTLOOK / MICROSOFT 365 for /s2's subscription finder — read-only, through the person's own Outlook
connection (booking_signer/outlook.py: Microsoft Graph, delegated Mail.Read, sealed in the vault, purpose outlook_read). The same rules
as Gmail's (s2_gmail_receipts):
  · ONE search, always this one: receipt / renewal / subscription subjects received in the last 13 months. No code path lists the
    mailbox without it.
  · Only the messages it returns are fetched; their text goes to AgAPI (which reads only receipts, keeps only the quoted facts and the
    email's sha256) and is dropped here as soon as the call returns — never written anywhere.
  · Its own consent sentence (CONSENT), asked in the chat and answered in a later turn, before the first search."""
from __future__ import annotations

import hashlib
import re
from datetime import date, timedelta
from typing import Dict, List, Optional

from agapi.s2_gmail_receipts import WORDS

GRAPH = "https://graph.microsoft.com/v1.0/me"
MAX = 60
CONSENT = ("I'll look in your Outlook only for receipt and renewal emails from the last 13 months, keep only each subscription's name, "
           "price and dates (each with the line it came from), and never store your emails. OK?")
CONSENT_VERSION = "s2-outlook-1"


def consent() -> Dict[str, str]:
    return {"version": CONSENT_VERSION, "text": CONSENT, "text_sha256": "sha256:" + hashlib.sha256(CONSENT.encode()).hexdigest()}


def query(today: Optional[date] = None) -> str:
    """Graph's KQL: the subjects Gmail's search uses, received in the last 400 days."""
    since = ((today or date.today()) - timedelta(days=400)).isoformat()
    words = [w for w in WORDS if '"' not in w]   # a quoted phrase can't sit inside Graph's quoted $search: the single words only
    return f"received>={since} AND (" + " OR ".join(f"subject:{w}" for w in words) + ")"


def _text(body: dict) -> str:
    t = (body or {}).get("content") or ""
    if (body or {}).get("contentType", "").lower() == "html":   # asked for text; an html body is flattened the way Gmail's is
        t = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", t)
        t = re.sub(r'(?is)<a [^>]*href="(https?://[^"]+)"[^>]*>(.*?)</a>', r"\2 [\1]", t)
        t = re.sub(r"<[^>]+>", "\n", t)
    return re.sub(r"\n\s*\n+", "\n", re.sub(r"[ \t]+", " ", t)).strip()


def _from(m: dict) -> str:
    a = ((m.get("from") or {}).get("emailAddress")) or {}
    return (f"{a.get('name')} <{a.get('address')}>" if a.get("name") else str(a.get("address") or ""))[:200]


async def _http(url: str, token: str, params: Optional[dict] = None):
    import httpx
    async with httpx.AsyncClient(timeout=httpx.Timeout(20.0)) as c:
        r = await c.get(url, params=params, headers={"Authorization": f"Bearer {token}", "Prefer": 'outlook.body-content-type="text"'})
    return r.status_code, (r.json() if r.headers.get("content-type", "").startswith("application/json") else {})


GRAPH_HTTP = _http   # tests replace it


async def connected(account: str) -> bool:
    try:
        from booking_signer import outlook as OL
        return bool(await OL.link(account))
    except Exception:
        return False


async def receipts(account: str) -> Optional[List[dict]]:
    """The receipt emails (memory only), or None when Outlook isn't connected / Microsoft refused its token."""
    from booking_signer import outlook as OL
    from booking_signer.vault import crypto as VC
    lk = await OL.link(account)
    if not lk:
        return None
    try:
        token = await VC.use_connection(account, lk["id"], purpose="outlook_read")
    except VC.UseRefused:
        return None
    status, j = await GRAPH_HTTP(f"{GRAPH}/messages", token, {"$search": f'"{query()}"', "$top": MAX,
                                                              "$select": "id,from,subject,receivedDateTime,body"})
    if status != 200:
        return None
    return [{"message_id": str(m.get("id") or "")[:80], "from": _from(m), "subject": str(m.get("subject") or "")[:300],
             "date": str(m.get("receivedDateTime") or "")[:40], "text": _text(m.get("body") or {})[:6000]}
            for m in (j.get("value") or [])[:MAX]]
