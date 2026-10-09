"""DIVE · reading a REAL operator's website — CR 69: through AgAPI's PUBLIC API (magellan.read_site, with DIVE's own key, like any
partner). The reading itself (robots.txt first, own domain, ≤15 pages, never a private address or a booking platform, the AI reader, quotes
checked against their pages) MOVED into AgAPI (agapi_service/magellan.py); DIVE no longer fetches a real site or calls a model. The fixed
rules for the FAKE Blue Kyma site stay in onboard.py. Isolation unchanged: no import of agapi_service — only sandbox.py's HTTP call."""
from __future__ import annotations

import re
from typing import Any, Callable, Dict, Optional
from urllib.parse import urlsplit, urlunsplit

from . import sandbox as SB

LOW = 60


class Unreadable(Exception):
    """Why a site couldn't be read (AgAPI's error details: rule + why) — said to the operator, never 'nothing found'."""

    def __init__(self, rule: str, say: str):
        super().__init__(say)
        self.rule, self.say = rule, say


def normalise(url: str) -> str:
    """Only the address's shape here (for the demo's slug); AgAPI applies every reading rule."""
    u = (url or "").strip()
    if not u:
        raise Unreadable("invalid_url", "Paste the website's address, e.g. https://www.example.com")
    if re.match(r"^[a-z][a-z0-9+.-]*://", u, re.I) and not re.match(r"^https?://", u, re.I):
        raise Unreadable("invalid_url", "Only web addresses (http or https) are read.")
    if not re.match(r"^https?://", u, re.I):
        u = "https://" + u
    p = urlsplit(u)
    if not p.hostname or p.username or p.password or (p.port not in (None, 80, 443)):
        raise Unreadable("invalid_url", "That isn't a website address we can read.")
    return urlunsplit((p.scheme.lower(), p.hostname.lower(), p.path or "/", p.query, ""))


def _item(x: dict, fields) -> dict:
    q = x.get("quote") or {}
    return {**{f: x[f] for f in fields if f in x}, "source_url": x.get("source_url", ""), "quote": q.get("text", "") if isinstance(q, dict) else str(q),
            "quote_found": bool(x.get("quote_found")), "instruction_like": bool(x.get("instruction_like")), "confidence": int(x.get("confidence", 0)),
            "low_confidence": bool(x.get("low_confidence")), "notes": list(x.get("notes") or [])}


async def read_site(url: str, *, progress: Optional[Callable[[str], None]] = None) -> Dict[str, Any]:
    """→ {state: read|ai_off|ai_failed, coverage, draft?, usage?, why?}; Unreadable for robots / unreachable / no text / not allowed."""
    (progress or (lambda m: None))("AgAPI is reading their website (magellan.read_site): robots.txt first, at most 15 pages")
    env = await SB.call("magellan.read_site", {"url": url, "purpose": "operator"})
    if not env.get("ok"):
        err = env.get("error") or {}
        d = err.get("details") or {}
        rule, why = d.get("rule") or err.get("code") or "unreachable", d.get("why") or err.get("message") or "AgAPI didn't answer."
        if rule in ("ai_off", "ai_failed"):
            return {"state": rule, "coverage": None, "why": why}
        raise Unreadable(rule, why)
    r = env["result"]
    draft = {"operator": r.get("operator") or {"name": "", "summary": ""},
             "products": [_item(x, ("title", "kind", "price_text", "price_amount", "currency", "price_unit", "duration_text", "times_text",
                                    "group_size_text", "includes", "how_to_book")) for x in r.get("offers") or []],
             "suppliers": [_item(x, ("name", "kind", "role", "contacts")) for x in r.get("partners") or []],
             "instruction_like": [{"source_url": f.get("source_url", ""), "quote": (f.get("quote") or {}).get("text", "")} for f in r.get("instruction_like") or []],
             "contacts": r.get("contacts") or [], "booking_channels": r.get("booking_channels") or []}
    rd = r.get("reader") or {}
    usage = {"model": rd.get("model", ""), "input_tokens": rd.get("input_tokens", 0), "output_tokens": rd.get("output_tokens", 0), "usd": rd.get("usd", 0.0)} \
        if "input_tokens" in rd else None
    return {"state": "read", "coverage": r["coverage"], "draft": draft, "usage": usage}
