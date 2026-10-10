"""Sasha 233 · TYLER'S NAMED-PLATFORM EXCEPTION (10 Oct 2026) to "never probe a booking platform" — and ONLY this:

    Fresha, Treatwell, Booksy (a venue's own booking page) and Rover (a marketplace) may be READ — public pages only, by THIS
    SERVER (never the founder's machine), only where that platform's robots.txt allows the path, for NON-restaurant requests.
    Read: services, prices, open slots; hand the link that opens on the slot (or the listing); the person taps Book.
    NEVER press Book, never log in, never submit anything, never send a cookie or a credential. GET only.
    Robots disallows → today's behaviour (their page to the phone, the asked service + time in words).
    Restaurants: unchanged — every other platform stays "recognised from a link, never fetched" (venue_read.PLATFORMS).

    named(url)            → "fresha" | "treatwell" | "booksy" | "rover" | None
    robots(http, url)     → {"allowed", "robots_url", "status", "rules"}  (cached 6 h per host; unreadable (5xx/refused) = NOT allowed)
    fetch(http, url)      → {"url", "status", "text"} — refused unless named + allowed; redirects followed by hand, each hop
                            re-checked (public host, named platform, robots)
"""
from __future__ import annotations

import re
import time
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlsplit

from . import venue_read as V

NAMED = {"fresha": re.compile(r"(^|\.)fresha\.com$"), "treatwell": re.compile(r"(^|\.)treatwell\.(es|co\.uk|de|fr|it|pt|nl|be|at|ch|ie|com)$"),
         "booksy": re.compile(r"(^|\.)booksy\.com$"), "rover": re.compile(r"(^|\.)rover\.com$")}
USER_AGENT = V.USER_AGENT
ROBOTS_TTL_S = 6 * 3600
_ROBOTS: Dict[str, tuple] = {}   # host → (when, status, text)
MAX_BYTES = 3_000_000


class Refused(Exception):
    def __init__(self, rule: str, detail: str):
        super().__init__(detail)
        self.rule, self.detail = rule, detail


def named(url: str) -> Optional[str]:
    host = (urlsplit(str(url or "")).hostname or "").lower()
    return next((k for k, rx in NAMED.items() if rx.search(host)), None)


def _rules_for(text: str) -> List[str]:
    """The lines of the groups that apply to us (our agent, else '*') — Allow / Disallow / Crawl-delay, as written."""
    groups: List[tuple] = []   # (agents, rules)
    for line in text.splitlines():
        s = line.split("#", 1)[0].strip()
        if not s:
            continue
        k, _, v = s.partition(":")
        k, v = k.strip().lower(), v.strip()
        if k == "user-agent":
            if not groups or groups[-1][1]:
                groups.append(([], []))
            groups[-1][0].append(v.lower())
        elif groups:
            groups[-1][1].append(s)
    ours = [g for g in groups if any(a != "*" and a in USER_AGENT.lower() for a in g[0])]
    star = [g for g in groups if "*" in g[0]]
    return [r for g in (ours or star) for r in g[1]][:600]


def _rx(pattern: str):
    """A robots path pattern (Google / RFC 9309): '*' any run of characters, a trailing '$' the end; else a prefix."""
    end = pattern.endswith("$")
    body = re.escape(pattern[:-1] if end else pattern).replace(r"\*", ".*")
    return re.compile("^" + body + ("$" if end else ""))


def verdict(rules: List[str], url: str) -> tuple:
    """(allowed, the deciding rule or None): the LONGEST matching Allow/Disallow wins; a tie goes to Allow; none → allowed.
    Python's RobotFileParser ignores '*' and '$' — Fresha's '*booking/time*' and Booksy's '/*/l/book/' need them."""
    u = urlsplit(url)
    path = (u.path or "/") + (("?" + u.query) if u.query else "")
    best = None   # (length, is_allow, rule)
    for r in rules:
        k, _, v = r.partition(":")
        k, v = k.strip().lower(), v.strip()
        if k not in ("allow", "disallow") or not v:
            continue
        if _rx(v).match(path):
            cand = (len(v), k == "allow", r)
            if best is None or cand[:2] > best[:2]:
                best = cand
    return (True, None) if best is None else (best[1], best[2])


def crawl_delay(rules: List[str]) -> float:
    for r in rules:
        k, _, v = r.partition(":")
        if k.strip().lower() == "crawl-delay":
            try:
                return min(10.0, max(0.0, float(v.strip())))
            except ValueError:
                pass
    return 0.0


async def HTTP(method: str, url: str, headers: dict, json: Optional[dict] = None):
    """A fresh client per request: NO cookie jar is ever kept or sent to a platform (the pooled client keeps one)."""
    import httpx
    async with httpx.AsyncClient(follow_redirects=False, timeout=httpx.Timeout(15.0)) as c:
        return await c.request(method, url, headers=headers)


async def _get(http, url: str) -> Any:
    V.public_url(url)
    return await (http or HTTP)("GET", url, headers={"user-agent": USER_AGENT, "accept": "text/html,application/xhtml+xml,text/plain",
                                                     "accept-language": "es-ES,es;q=0.9,en;q=0.8"})


async def robots(http, url: str) -> dict:
    u = urlsplit(url)
    host = (u.hostname or "").lower()
    if not named(url):
        return {"allowed": False, "why": "not a named platform"}
    robots_url = f"{u.scheme or 'https'}://{u.netloc}/robots.txt"
    got = _ROBOTS.get(host)
    if not got or time.time() - got[0] > ROBOTS_TTL_S:
        try:
            r = await _get(http, robots_url)
            got = (time.time(), r.status_code, r.text if r.status_code == 200 else "")
        except Exception as e:
            got = (time.time(), 0, "")
            _ROBOTS[host] = got
            return {"allowed": False, "robots_url": robots_url, "status": 0, "why": f"robots.txt unreadable ({type(e).__name__})"}
        _ROBOTS[host] = got
    _, status, text = got
    if status == 0 or status >= 500 or status in (401, 403):
        return {"allowed": False, "robots_url": robots_url, "status": status, "why": "robots.txt unreadable — no permission assumed"}
    if status != 200:
        return {"allowed": True, "robots_url": robots_url, "status": status, "why": "no robots.txt"}
    rules = _rules_for(text)
    ok, rule = verdict(rules, url)
    return {"allowed": ok, "robots_url": robots_url, "status": status, "rules": rules, "rule": rule, "crawl_delay": crawl_delay(rules),
            "why": ("robots.txt allows this path" + (f" ({rule})" if rule else "")) if ok else f"robots.txt disallows this path ({rule})"}


_LAST: Dict[str, float] = {}   # host → when we last fetched a page there


async def _pace(url: str, delay: float) -> None:
    """Their Crawl-delay (Treatwell: 5 s), and never more than one page a second from us on any platform."""
    import asyncio
    host = (urlsplit(url).hostname or "").lower()
    wait = max(delay, 1.0) - (time.time() - _LAST.get(host, 0.0))
    if wait > 0:
        await asyncio.sleep(wait)
    _LAST[host] = time.time()


async def fetch(http, url: str) -> dict:
    """One public page of a named platform, GET only, robots first at every hop. No cookies, no login, nothing submitted."""
    for _ in range(4):
        if not named(url):
            raise Refused("not_named_platform", f"{url} is not Fresha, Treatwell, Booksy or Rover")
        rb = await robots(http, url)
        if not rb.get("allowed"):
            raise Refused("robots_disallow", f"{url}: {rb.get('why')}")
        await _pace(url, rb.get("crawl_delay") or 0.0)
        r = await _get(http, url)
        if r.status_code in (301, 302, 303, 307, 308) and r.headers.get("location"):
            url = urljoin(url, r.headers["location"])
            continue
        return {"url": url, "status": r.status_code, "text": (r.text or "")[:MAX_BYTES], "robots": rb}
    raise Refused("too_many_redirects", "more than three redirects")


__all__ = ["named", "robots", "fetch", "Refused", "NAMED"]
