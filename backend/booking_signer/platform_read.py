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

Sasha 270 · THE GUARD IS CODE (incident 10 Oct, mailbox row 1002): a "server-side" check ran in-process under `railway run` and its 8
robots.txt GETs left from the founder's home network. HTTP — the ONE place a request to a platform leaves this module — now refuses
anywhere but Railway's DEPLOYED server, loudly (NotOnRailway, logged as an error, never swallowed). `railway run` injects
RAILWAY_ENVIRONMENT too, so that alone proves nothing: a deployment's own RAILWAY_DEPLOYMENT_ID / RAILWAY_REPLICA_ID must be there
(checked 15 Oct: `railway run` sets neither).
"""
from __future__ import annotations

import logging
import os
import re
import time
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlsplit

from . import venue_read as V

log = logging.getLogger("booking_signer.platform_read")


class NotOnRailway(RuntimeError):
    """A platform read asked for off Railway's deployed server (a laptop, `railway run`, a test with no fake): refused, loudly."""


def on_railway() -> bool:
    """True only inside a Railway DEPLOYMENT: RAILWAY_ENVIRONMENT and the deployment's own id (`railway run` sets only the first)."""
    return bool(os.environ.get("RAILWAY_ENVIRONMENT")) and bool(os.environ.get("RAILWAY_DEPLOYMENT_ID") or os.environ.get("RAILWAY_REPLICA_ID"))


def must_be_on_railway(url: str = "") -> None:
    if not on_railway():
        host = (urlsplit(str(url or "")).hostname or "?")
        log.error("[platform_read] REFUSED: a platform read (%s) off Railway's deployed server — never from this machine's network", host)
        raise NotOnRailway(f"platform reads run only on Railway's deployed server (RAILWAY_ENVIRONMENT + RAILWAY_DEPLOYMENT_ID); "
                           f"refused here — nothing was sent to {host}")


def status() -> dict:
    """For /api/booking/health: whether platform reads may run on this process (never which platform, never a URL)."""
    return {"reads_allowed_here": on_railway()}

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
    """A fresh client per request: NO cookie jar is ever kept or sent to a platform (the pooled client keeps one).
    Sasha 270 · the one place a platform request leaves: refused off Railway's deployed server, before anything is opened."""
    must_be_on_railway(url)
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
        except NotOnRailway:
            raise   # Sasha 270 · loud: never "robots.txt unreadable"
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


# ── what a venue's page offers: its services and prices, from the schema.org data it publishes (read on the server, 11 Oct) ──
#
#   Booksy:    the business's JSON-LD `makesOffer` — [{Offer, name, price, priceCurrency}] (BELMONT, Madrid: 12 offers)
#   Treatwell: JSON-LD `@graph` → `hasOfferCatalog` → OfferCatalog → [{AggregateOffer, itemOffered{name, Duration PT1H},
#              lowPrice, highPrice}] (a Granada salon: 30+ services)
#   Fresha:    not read yet — its venue page is allowed, so the same reader applies when one is linked; none is assumed.
# ⚠ OPEN SLOTS: no platform publishes them on a page robots allows (Fresha *booking/time*, Booksy /*/l/book/, Treatwell
#   /availability — all Disallow), so Sasha never says a time is free; the person picks it on the page and presses Book.

SLOTS_CLOSED = {"fresha": "Fresha", "treatwell": "Treatwell", "booksy": "Booksy"}
_ISO = re.compile(r"PT(?:(\d+)H)?(?:(\d+)M)?")


def _minutes(v) -> Optional[int]:
    m = _ISO.match(str(v or "").strip())
    if not m or not (m.group(1) or m.group(2)):
        return None
    return int(m.group(1) or 0) * 60 + int(m.group(2) or 0)


def _num(v) -> Optional[float]:
    try:
        return float(str(v).replace(",", "."))
    except (TypeError, ValueError):
        return None


def services(html: str) -> List[dict]:
    """[{name, price | low+high, currency, minutes}] — every Offer / AggregateOffer in the page's JSON-LD, nothing else."""
    import html as H
    import json
    out: List[dict] = []

    def walk(x):
        if isinstance(x, list):
            for y in x:
                walk(y)
            return
        if not isinstance(x, dict):
            return
        t = x.get("@type")
        if t in ("Offer", "AggregateOffer"):
            item = x.get("itemOffered") if isinstance(x.get("itemOffered"), dict) else {}
            name = H.unescape(str(item.get("name") or x.get("name") or "")).strip()
            prop = item.get("additionalProperty") if isinstance(item.get("additionalProperty"), dict) else {}
            dur = str(prop.get("value") or "") if str(prop.get("name") or "").lower() == "duration" else ""
            mins = [_minutes(d) for d in dur.split(" - ")] if dur else []
            mins = [m for m in mins if m]
            if not mins:
                mm = re.search(r"(\d{2,3})\s*min", name, re.I)
                mins = [int(mm.group(1))] if mm else []
            if name:
                out.append({"name": name[:160], "price": _num(x.get("price")), "low": _num(x.get("lowPrice")),
                            "high": _num(x.get("highPrice")), "currency": x.get("priceCurrency") or "EUR",
                            "minutes": mins[0] if len(mins) == 1 else None, "minutes_range": mins if len(mins) > 1 else None})
            return
        for v in x.values():
            walk(v)

    for block in re.findall(r'<script[^>]+type="application/ld\+json"[^>]*>(.*?)</script>', html or "", re.S | re.I):
        try:
            walk(json.loads(block))
        except ValueError:
            continue
    return out[:200]


#: the words a person says → the words these pages use (Spanish venues name services in Spanish, often both)
_SYN = {"massage": "masaje", "relaxing": "relajante", "relax": "relajante", "deep": "descontracturante", "tissue": "descontracturante",
        "sports": "deportivo", "sport": "deportivo", "nails": "uñas", "nail": "uñas", "manicure": "manicura", "pedicure": "pedicura",
        "haircut": "corte", "hair": "pelo", "facial": "facial", "wax": "depilación", "waxing": "depilación", "couples": "pareja",
        "back": "espalda", "feet": "pies", "foot": "pies", "thai": "tailandés", "hot": "piedras", "stones": "piedras"}
_STOP = {"a", "an", "the", "for", "at", "of", "and", "y", "de", "la", "el", "un", "una", "con", "min", "minute", "minutes", "minutos"}


def _words(s: str) -> set:
    w = {x for x in re.findall(r"[a-záéíóúñü]+", s.lower()) if x not in _STOP and len(x) > 2}
    return w | {_SYN[x] for x in w if x in _SYN}


_BUNDLE = re.compile(r"\b(pack|bono|combo|bundle|package|paquete)\b|\+", re.I)


def pick(svcs: List[dict], asked: str) -> Optional[dict]:
    """The service that best matches what was asked ("a 60-minute relaxing massage"), or None — never a guess on no overlap."""
    want = _words(asked or "")
    m = re.search(r"(\d{2,3})\s*-?\s*min", asked or "", re.I) or re.search(r"\b(\d)\s*-?\s*(?:h|hour)", asked or "", re.I)
    mins = (int(m.group(1)) * (60 if int(m.group(1)) < 10 else 1)) if m else None
    best, score = None, float("-inf")   # Sasha 234 · was 0.0; any overlap still qualifies (the tie-breaks below may go under 0)
    for s in svcs:
        hit = len(want & _words(s["name"]))
        if not hit:
            continue
        sc = hit + (1.5 if mins and (s.get("minutes") == mins or mins in (s.get("minutes_range") or [])) else 0) \
            - (0.5 if mins and s.get("minutes") and s["minutes"] != mins else 0)
        # Sasha 234 · ties: a bundle loses unless asked for (live: "Pack masaje anticelulítico (masaje + presoterapia)" won a plain
        # "60-minute massage" by being listed first), then fewer unasked words, then the closer duration
        sc -= (1.0 if (_BUNDLE.search(s["name"]) and not _BUNDLE.search(asked or "")) else 0) + 0.1 * len(_words(s["name"]) - want) \
            + (min(abs(s["minutes"] - mins), 60) / 600 if mins and s.get("minutes") else 0)
        if sc > score:
            best, score = s, sc
    return best


def price_words(s: dict) -> str:
    cur = "€" if (s.get("currency") or "EUR") == "EUR" else (s.get("currency") + " ")
    f = lambda v: f"{cur}{v:g}"
    if s.get("price") is not None:
        p = f(s["price"])
    elif s.get("low") is not None and s.get("high") is not None and s["low"] != s["high"]:
        p = f"{f(s['low'])}–{f(s['high'])}"
    elif s.get("low") is not None:
        p = f"from {f(s['low'])}"
    else:
        return ""
    d = f"{s['minutes']} min, " if s.get("minutes") else ""
    return f"{d}{p}"


async def offer(http, url: str, asked: str) -> Optional[dict]:
    """The asked service on a named platform's venue page, read only where robots allows; None when not read (refused,
    unreadable, no service matched) — the caller then says what it always said."""
    plat = named(url)
    if plat not in SLOTS_CLOSED or not str(asked or "").strip():
        return None
    try:
        got = await fetch(http, url)
    except Refused:
        return None
    except NotOnRailway:
        raise   # Sasha 270 · loud: never a quiet "no offer" from the wrong machine
    except Exception:
        return None
    if got.get("status") != 200:
        return None
    svcs = services(got.get("text") or "")
    s = pick(svcs, asked)
    if not s:
        return None
    return {"platform": SLOTS_CLOSED[plat], "url": got["url"], "service": s["name"], "price": price_words(s), "services_read": len(svcs),
            "slots": None, "slots_why": f"{SLOTS_CLOSED[plat]}'s booking calendar is closed to readers (its robots.txt)"}


__all__ = ["named", "robots", "fetch", "Refused", "NAMED", "services", "pick", "price_words", "offer", "NotOnRailway", "on_railway",
           "must_be_on_railway", "status"]
