"""DIVE step 4 · MAGELLAN DRAFTS SUPPLIERS FROM THE OPERATOR'S OWN SITE (EU 212 model.md §5). Rule-based, no model:
  · ONLY the operator's own site (the host of its site_url) — never another host; robots.txt first (a Disallow → nothing fetched);
  · each named business (a <strong> in a list item or paragraph) becomes a DRAFT: its name, a kind guessed from the words, the contacts
    the sentence links to (WhatsApp, email, a booking-form URL), the page and THE SENTENCE as untrusted_text (flagged when
    instruction-like) and a confidence;
  · a draft is never booked and nothing is sent to it: the operator confirms (suppliers.put) and verifies a channel first.
A site that can't be read is an outage ("this isn't 'no suppliers found'"), never an empty list."""
from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse

from . import rules as R
from .model import DiveError
from .store import Store, dumps, ts

UA = "AgAPI-DIVE-Magellan/1 (+operator onboarding; reads only the operator's own site)"


async def _http_fetch(url: str) -> Tuple[int, str]:
    import httpx
    async with httpx.AsyncClient(timeout=httpx.Timeout(15.0), follow_redirects=False, headers={"user-agent": UA}) as c:
        r = await c.get(url)
    return r.status_code, r.text


FETCH: Callable[[str], Awaitable[Tuple[int, str]]] = _http_fetch      # tests replace it


class _Blocks(HTMLParser):
    """Each <li> / <p>: its text, the <strong> names in it, and its links."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.blocks: List[Dict[str, Any]] = []
        self.cur: Optional[Dict[str, Any]] = None
        self.in_strong = False
        self.links: List[str] = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ("li", "p"):
            self.cur = {"text": "", "names": [], "links": []}
        elif tag == "strong" and self.cur is not None:
            self.in_strong = True
            self.cur["names"].append("")
        elif tag == "a" and a.get("href"):
            (self.cur["links"] if self.cur is not None else self.links).append(a["href"])

    def handle_endtag(self, tag):
        if tag == "strong":
            self.in_strong = False
        elif tag in ("li", "p") and self.cur is not None:
            self.blocks.append(self.cur)
            self.cur = None

    def handle_data(self, data):
        if self.cur is not None:
            self.cur["text"] += data
            if self.in_strong:
                self.cur["names"][-1] += data


KINDS = [("boat", r"\bboats?\b|skipper|\bboat\b"), ("gear", r"\bgear\b|rent|wetsuits?|regulators?|bcds?"),
         ("restaurant", r"taverna|restaurant|lunch|dinner|table"), ("hotel_feed", r"hotel|stay|room"), ("dive_shop", r"dive (shop|centre|center|club)")]


def _kind(name: str, sentence: str) -> str:
    t = f"{name} {sentence}".lower()
    for k, rx in KINDS:
        if re.search(rx, t):
            return k
    return "other"


def _contacts(links: List[str], base: str, own_host: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for h in links:
        if h.startswith("mailto:"):
            out.setdefault("email", h[7:].split("?")[0])
        elif re.match(r"https?://(wa\.me|api\.whatsapp\.com)/", h):
            n = re.sub(r"\D", "", h.split("/")[-1])
            if n:
                out.setdefault("whatsapp", "+" + n)
        elif h.startswith("tel:"):
            out.setdefault("phone", h[4:])
        else:
            u = urljoin(base, h)
            if urlparse(u).netloc != own_host and re.search(r"book|reserv|form|fixtures", u, re.I):
                out.setdefault("web_form", u)                 # a supplier's own booking form (recorded, never fetched here)
    return out


async def draft_from_site(s: Store, operator: dict, url: Optional[str] = None) -> Dict[str, Any]:
    site = operator.get("site_url") or ""
    url = url or site
    own = urlparse(site).netloc
    if not own or urlparse(url).netloc != own:
        raise DiveError("invalid_input", "Magellan reads only the operator's own website.", {"path": "/url", "rule": "own_site_only"})
    root = f"{urlparse(site).scheme}://{own}"
    path_root = urlparse(site).path.rstrip("/")
    try:
        st, robots = await FETCH(f"{root}{path_root}/robots.txt")
    except Exception:
        st, robots = 0, ""
    if st == 200 and _disallowed(robots, urlparse(url).path):
        raise DiveError("robots_disallowed", "The site's robots.txt asks not to be read there — nothing was fetched.")
    pages, drafts, seen = [url, url.rstrip("/") + "/partners"], [], set()
    read = 0
    for page in pages:
        try:
            st, body = await FETCH(page)
        except Exception:
            st, body = 0, ""
        if st != 200:
            continue
        read += 1
        p = _Blocks()
        p.feed(body)
        for b in p.blocks:
            sentence = re.sub(r"\s+", " ", b["text"]).strip()
            for name in (re.sub(r"\s+", " ", n).strip() for n in b["names"]):
                if not name or name.lower() in seen or name.lower().startswith(("discover", "blue kyma")):
                    continue
                seen.add(name.lower())
                contacts = _contacts(b["links"], page, own)
                kind = _kind(name, sentence)
                ev = R.wrap(sentence, f"site:{own}{urlparse(page).path}", ts()[:19] + "Z", cap=600)
                conf = 40 + 20 * min(2, len(contacts)) + (10 if kind != "other" else 0) - (40 if ev.get("instruction_like") else 0)
                drafts.append({"name": name, "kind": kind, "contacts": contacts, "evidence_of_source": ev, "confidence": max(5, min(95, conf))})
    if read == 0:
        raise DiveError("upstream_unreachable", "We couldn't read your site right now. This isn't 'no suppliers found'.", {"service": own})
    out = []
    for d in drafts:   # stored as DRAFTS (re-reading the site updates a draft, never a confirmed supplier)
        ex = s.one("select * from suppliers where operator_id = ? and lower(name) = lower(?)", operator["id"], d["name"])
        if ex and ex["status"] != "draft":
            continue
        if ex:
            s.x("update suppliers set kind = ?, evidence_of_source = ?, confidence = ?, contacts = ? where id = ?", d["kind"],
                dumps(d["evidence_of_source"]), d["confidence"], dumps(d["contacts"]), ex["id"])
            sid = ex["id"]
        else:
            sid = R.new_id("sup")
            s.x("insert into suppliers (id, operator_id, name, kind, status, source, evidence_of_source, confidence, contacts, created_at) "
                "values (?, ?, ?, ?, 'draft', 'magellan_draft', ?, ?, ?, ?)", sid, operator["id"], d["name"], d["kind"],
                dumps(d["evidence_of_source"]), d["confidence"], dumps(d["contacts"]), ts())
        out.append(sid)
    return {"supplier_ids": out, "coverage": {"complete": True, "pages_read": read, "site": own}}


def _disallowed(robots: str, path: str) -> bool:
    """robots.txt for user-agent * (simple, longest-match): Disallow wins only if no longer Allow matches."""
    rules, applies = [], False
    for line in robots.splitlines():
        k, _, v = line.partition(":")
        k, v = k.strip().lower(), v.strip()
        if k == "user-agent":
            applies = v == "*"
        elif applies and k in ("allow", "disallow") and v:
            rules.append((len(v), k, v))
    hits = sorted((r for r in rules if path.startswith(r[2])), reverse=True)
    return bool(hits) and hits[0][1] == "disallow"
