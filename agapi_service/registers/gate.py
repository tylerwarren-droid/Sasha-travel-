"""What the registry track may fetch, and how a single page is read for registry.verify.

AD's never-fetch list is ported here as it stands in scripts/discovery-crawler/guardrails.py (read 10 Oct 2026); a host on it is refused
BEFORE any request, robots.txt included. Robots are strict: a 200 that isn't a robots file (an HTML login page, a WAF challenge) is
`unreadable`, and unreadable means not allowed (the profile standard). A robots file that names Anthropic's agents is honoured for them too."""
from __future__ import annotations

import re
from typing import Dict, Optional, Tuple
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

from .. import magellan as MG

NEVER_FETCH_TIER1 = frozenset({"data.gov.gr", "caselaw.nationalarchives.gov.uk", "www.courtlistener.com", "courtlistener.com"})
NEVER_FETCH_TIER2 = frozenset({"arc-sos.state.al.us", "mblsportal.sos.mn.gov", "www.sos.ok.gov", "coraweb.sos.la.gov", "isir.justice.cz"})
NEVER_FETCH_UNREADABLE = frozenset({"ros.gov.uk", "www.ros.gov.uk", "iapps.courts.state.ny.us", "www.nmlsconsumeraccess.org", "data.gov.sg",
                                    "new.kenyalaw.org", "www.saflii.org", "opencorporates.com", "www.opencorporates.com", "www.bvdinfo.com",
                                    "krz.ms.gov.pl", "cegportal.im.gov.hu", "accounts.ecitizen.go.ke"})
NEVER_FETCH = NEVER_FETCH_TIER1 | NEVER_FETCH_TIER2 | NEVER_FETCH_UNREADABLE
AGENTS = (MG.UA_TOKEN, "ClaudeBot", "Claude-User", "anthropic-ai")      # every agent name robots may address us by
VERDICTS = ("allowed", "disallowed", "unreadable", "never_fetch", "not_applicable", "unknown")
_ROBOTS_START = re.compile(r"^\s*﻿?(#|user-agent|sitemap|disallow|allow|crawl-delay)", re.I)


def never_fetch(host: str) -> Optional[str]:
    h = (host or "").lower()
    if h in NEVER_FETCH_TIER1:
        return f"{h} names AI agents in its robots.txt: never fetched (AD's tier-1 list)"
    if h in NEVER_FETCH_TIER2:
        return f"{h} disallows automated clients: never fetched (AD's tier-2 list)"
    if h in NEVER_FETCH_UNREADABLE:
        return f"{h}'s robots.txt can't be read: never fetched (AD's list)"
    return None


def classify_robots(status: int, ctype: str, body: str) -> Tuple[str, Optional[RobotFileParser], str]:
    """(verdict-for-the-file, parser, why). A 4xx = no robots file = everything allowed (RFC 9309); 5xx/odd = unreadable;
    a 200 that isn't a robots file (HTML, a challenge page) = unreadable."""
    if 400 <= status < 500:
        rp = RobotFileParser()
        rp.parse([])
        return "allowed", rp, f"robots.txt answered HTTP {status}: no robots file"
    if not (200 <= status < 300):
        return "unreadable", None, f"robots.txt answered HTTP {status}"
    looks = "text/plain" in (ctype or "").lower() or bool(_ROBOTS_START.match(body or "")) or not (body or "").strip()
    if not looks or re.search(r"<html|<!doctype", (body or "")[:2000], re.I):
        return "unreadable", None, "robots.txt answered a web page, not a robots file"
    rp = RobotFileParser()
    rp.parse((body or "").splitlines())
    return "allowed", rp, "robots.txt read"


def may_fetch(rp: RobotFileParser, url: str) -> bool:
    return all(rp.can_fetch(a, url) for a in AGENTS)


def robots_line(body: str, url: str) -> str:
    """The robots line a verdict rests on (for the claim's quote) — the most specific Disallow that matches the path."""
    path = urlsplit(url).path or "/"
    best = ""
    for ln in (body or "").splitlines():
        m = re.match(r"\s*disallow\s*:\s*(\S*)", ln, re.I)
        if m and m.group(1) and path.startswith(m.group(1).rstrip("*")) and len(ln.strip()) > len(best):
            best = ln.strip()
    return best[:200]


async def robots_verdict(url: str, cache: Optional[Dict[str, tuple]] = None) -> Dict[str, str]:
    """{verdict, why, robots_url, quote} for one URL — never_fetch before any request."""
    p = urlsplit(url)
    host = (p.hostname or "").lower()
    if p.scheme not in ("http", "https") or not host:
        return {"verdict": "not_applicable", "why": "not a web address", "robots_url": "", "quote": ""}
    nf = never_fetch(host)
    robots_url = f"{p.scheme}://{p.netloc.lower()}/robots.txt"          # robots.txt is per scheme + host (RFC 9309)
    if nf:
        return {"verdict": "never_fetch", "why": nf, "robots_url": robots_url, "quote": ""}
    cache = {} if cache is None else cache
    ck = f"{p.scheme}://{host}"
    if ck not in cache:
        try:
            st, ctype, body, _ = await MG.FETCH(robots_url)
            cache[ck] = (st, ctype, body)
        except MG.Unreadable as u:
            cache[ck] = (0, "", "", u.say)
        except Exception as e:
            cache[ck] = (0, "", "", type(e).__name__)
    got = cache[ck]
    if got[0] == 0:
        return {"verdict": "unreadable", "why": f"robots.txt couldn't be read ({got[3]})", "robots_url": robots_url, "quote": ""}
    verdict, rp, why = classify_robots(got[0], got[1], got[2])
    if verdict != "allowed":
        return {"verdict": verdict, "why": why, "robots_url": robots_url, "quote": ""}
    if not may_fetch(rp, url):
        return {"verdict": "disallowed", "why": "robots.txt disallows this path for automated readers", "robots_url": robots_url,
                "quote": robots_line(got[2], url)}
    return {"verdict": "allowed", "why": why, "robots_url": robots_url, "quote": ""}


class Broken(Exception):
    """The page is there no more, or may not be read now: verify's state 'broken' with the layer it failed at."""

    def __init__(self, layer: str, why: str):
        super().__init__(why)
        self.layer, self.why = layer, why


class Unreachable(Exception):
    """Transport: DNS, timeout, refused connection — registry.verify answers source_unreachable (503, retry), NEVER 'drifted'."""


async def read_page(url: str) -> Tuple[str, str]:
    """One page, robots first → (text, final_url). Broken(layer) or Unreachable."""
    v = await robots_verdict(url)
    if v["verdict"] in ("never_fetch", "disallowed", "unreadable"):
        raise Broken("robots", v["why"])
    try:
        st, ctype, body, final = await MG.FETCH(url)
    except MG.Unreadable as u:
        if u.rule == "dns":
            raise Unreachable(u.say)
        raise Broken("policy", u.say)
    except Exception as e:
        name = type(e).__name__
        if "SSL" in name or "Certificate" in name or "ssl" in str(e).lower():
            raise Broken("tls", f"TLS failed ({name})")
        raise Unreachable(name)
    if st in (404, 410):
        raise Broken("http", f"HTTP {st}: the page is gone")
    if not (200 <= st < 300):
        if st >= 500 or st == 429:
            raise Unreachable(f"HTTP {st}")
        raise Broken("http", f"HTTP {st}")
    if "html" not in (ctype or "html").lower() and "text" not in (ctype or "").lower():
        raise Broken("content", "not a web page")
    _, text, _, _ = MG.parse(body)
    return text, final
