"""S-36 · MAGELLAN ARRIVES — read what a venue publishes: a booking form, an email address, a phone number, a
WhatsApp link, a booking platform. Each is a FACT WE READ, kept with where it was read.

Founder's rule (S-36): a number on the venue's own website, or on its published Google business listing, IS a fact
we read. What is forbidden is asking a MODEL for a number — the deleted restaurant_agent's "best guess". So:
  · a fact is a value PRESENT IN BYTES WE FETCHED from a named source (a page, or Google's Places API response),
    stored with the URL, the moment, the sha256 of the bytes and the snippet it came from;
  · no model is consulted here, anywhere.

Two sources:
  · the venue's own website — fetched by THIS SERVER (Railway), robots.txt first, public hosts only, https or http,
    the home page and at most two same-host pages whose link says contact / reservations;
  · Google Places (Text Search, New) — only when GOOGLE_PLACES_API_KEY is set; the listing's own phone and website.

⛔ A booking platform's host is NEVER fetched (TheFork blocked the founder's network over exactly this, S-35). A link
to one is recorded as a `platform` fact from the link alone.
"""
from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import re
import socket
from dataclasses import asdict, dataclass, field
from datetime import datetime
from html.parser import HTMLParser
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urljoin, urlsplit
from urllib.robotparser import RobotFileParser

USER_AGENT = "SashaConcierge/1.0 (+https://project.kanoe.ai; reads a venue's published contact details)"
MAX_BYTES = 2_000_000
MAX_EXTRA_PAGES = 2
PLACES_URL = "https://places.googleapis.com/v1/places:searchText"
PLACES_FIELDS = ("places.id,places.displayName,places.formattedAddress,places.internationalPhoneNumber,"
                 "places.nationalPhoneNumber,places.websiteUri,places.addressComponents,places.regularOpeningHours")

#: country → (calling code, drops a leading trunk 0, language, IANA timezone)
COUNTRIES: Dict[str, Tuple[str, bool, str, str]] = {
    "ES": ("34", False, "es", "Europe/Madrid"), "PT": ("351", False, "pt", "Europe/Lisbon"),
    "FR": ("33", True, "fr", "Europe/Paris"), "IT": ("39", False, "it", "Europe/Rome"),
    "DE": ("49", True, "de", "Europe/Berlin"), "AT": ("43", True, "de", "Europe/Vienna"),
    "GB": ("44", True, "en", "Europe/London"), "IE": ("353", True, "en", "Europe/Dublin"),
    "VN": ("84", True, "vi", "Asia/Ho_Chi_Minh"),
}

#: Booking platforms, recognised from a LINK or an embed — never fetched.
PLATFORMS = {
    "thefork": "TheFork", "eltenedor": "TheFork", "lafourchette": "TheFork", "opentable": "OpenTable",
    "covermanager": "CoverManager", "sevenrooms": "SevenRooms", "resy.com": "Resy", "quandoo": "Quandoo",
    "tablein": "Tablein", "bookatable": "Bookatable", "resdiary": "ResDiary", "zenchef": "Zenchef",
    "guestonline": "Guestonline", "restoo": "Restoo", "booksy": "Booksy", "fresha": "Fresha",
}

_E164 = re.compile(r"\+[1-9]\d{7,14}")
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_BOOKING_FIELD = re.compile(r"date|fecha|data|datum|time|hora|heure|uhrzeit|party|guests|people|personas|pessoas|pax|comensales|kişi|reserv|booking", re.I)
_CONTACT_LINK = re.compile(r"contact|contacto|contato|contatti|kontakt|reserv|book|booking", re.I)


class ReadRefused(Exception):
    def __init__(self, rule: str, message: str) -> None:
        super().__init__(f"{rule}: {message}")
        self.rule = rule


@dataclass
class Fact:
    kind: str                  #: phone | email | whatsapp | booking_form | platform | address | website | hours
    value: str                 #: E.164 / address / wa.me digits / form action / platform name
    source_kind: str           #: site | places
    source_url: str
    source_label: str          #: as the read-back says it: "their website, lacontra.es" / "their Google listing"
    snippet: str
    fetched_at: str
    sha256: str
    detail: Dict[str, Any] = field(default_factory=dict)


@dataclass
class VenueRead:
    name: str
    country: Optional[str]
    facts: List[Fact]
    sources: List[Dict[str, Any]]          #: every fetch attempted, with its result — including refusals
    listing: Optional[Dict[str, Any]] = None   #: the Places listing's name and address, said aloud to identify it

    def to_json(self) -> dict:
        return {"name": self.name, "country": self.country, "facts": [asdict(f) for f in self.facts],
                "sources": self.sources, "listing": self.listing}


# ── phone numbers ───────────────────────────────────────────────────────────────────────────────

def to_e164(raw: str, country: Optional[str]) -> Optional[str]:
    """A published number → E.164, or None. A national number needs the venue's country; never guessed."""
    s = raw.strip()
    s = re.sub(r"^tel:", "", s, flags=re.I).split(";")[0].split(",")[0]
    s = re.sub(r"\(0\)", "", s)
    digits = re.sub(r"[^\d+]", "", s)
    if digits.startswith("00"):
        digits = "+" + digits[2:]
    if not digits.startswith("+"):
        if not country or country not in COUNTRIES:
            return None
        code, trunk, _, _ = COUNTRIES[country]
        if trunk and digits.startswith("0"):
            digits = digits[1:]
        digits = f"+{code}{digits}"
    return digits if _E164.fullmatch(digits) else None


# ── the page reader ─────────────────────────────────────────────────────────────────────────────

class _Page(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: List[Tuple[str, str]] = []       # (href, text)
        self.srcs: List[str] = []
        self.ld: List[str] = []
        self.forms: List[Dict[str, Any]] = []
        self.text: List[str] = []
        self._a: Optional[List[str]] = None
        self._href: Optional[str] = None
        self._ld = False
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        a = {k: (v or "") for k, v in attrs}
        if tag == "a" and a.get("href"):
            self._href, self._a = a["href"], []
        if tag in ("iframe", "script", "img", "link") and (a.get("src") or a.get("href")):
            self.srcs.append(a.get("src") or a.get("href"))
        if tag == "script" and a.get("type", "").lower() == "application/ld+json":
            self._ld, self.ld = True, self.ld + [""]
        elif tag in ("script", "style"):
            self._skip += 1
        if tag == "form":
            self.forms.append({"action": a.get("action", ""), "fields": []})
        if tag in ("input", "select", "textarea") and self.forms:
            self.forms[-1]["fields"].append(" ".join(filter(None, [a.get("type"), a.get("name"), a.get("id"), a.get("placeholder"), a.get("aria-label")])))

    def handle_endtag(self, tag):
        if tag == "a" and self._href is not None:
            self.links.append((self._href, " ".join("".join(self._a or []).split())))
            self._href, self._a = None, None
        if tag == "script" and self._ld:
            self._ld = False
        elif tag in ("script", "style") and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if self._ld:
            self.ld[-1] += data
            return
        if self._skip:
            return
        if self._a is not None:
            self._a.append(data)
        self.text.append(data)


def _ld_values(node: Any, key: str) -> List[str]:
    out: List[str] = []
    if isinstance(node, dict):
        for k, v in node.items():
            if k == key and isinstance(v, str):
                out.append(v)
            else:
                out += _ld_values(v, key)
    elif isinstance(node, list):
        for v in node:
            out += _ld_values(v, key)
    return out


def platform_of(url: str) -> Optional[str]:
    host = (urlsplit(url).hostname or "").lower()
    return next((name for k, name in PLATFORMS.items() if k in host), None)


def facts_from_html(html: str, url: str, country: Optional[str], fetched_at: str) -> List[Fact]:
    """Every fact a page publishes. ⚠ Nothing is inferred: a phone is a tel: link or a JSON-LD telephone; an email is a
    mailto:, a JSON-LD email or an address written in the page's text; a WhatsApp link is wa.me / api.whatsapp.com."""
    sha = hashlib.sha256(html.encode("utf-8", "replace")).hexdigest()
    host = urlsplit(url).hostname or url
    label = f"their website, {host.removeprefix('www.')}"
    p = _Page()
    try:
        p.feed(html)
    except Exception:
        pass
    facts: List[Fact] = []
    seen = set()

    def add(kind, value, snippet, detail=None):
        if (kind, value) in seen:
            return
        seen.add((kind, value))
        facts.append(Fact(kind, value, "site", url, label, snippet[:200], fetched_at, sha, detail or {}))

    for href, text in p.links:
        h = href.strip()
        if h.lower().startswith("tel:"):
            n = to_e164(h, country)
            if n:
                add("phone", n, f'<a href="{h}">{text}</a>')
        elif h.lower().startswith("mailto:"):
            addr = h[7:].split("?")[0].strip()
            if _EMAIL.fullmatch(addr):
                add("email", addr.lower(), f'<a href="{h}">{text}</a>')
        else:
            u = urlsplit(urljoin(url, h))
            if u.hostname in ("wa.me", "www.wa.me") and re.fullmatch(r"/\d{8,15}/?", u.path or ""):
                add("whatsapp", "+" + u.path.strip("/"), f'<a href="{h}">{text}</a>')
            elif u.hostname in ("api.whatsapp.com", "wa.link") and parse_qs(u.query).get("phone"):
                d = re.sub(r"\D", "", parse_qs(u.query)["phone"][0])
                if 8 <= len(d) <= 15:
                    add("whatsapp", "+" + d, f'<a href="{h}">{text}</a>')
            plat = platform_of(u.geturl()) if u.hostname else None
            if plat:
                add("platform", plat, f'<a href="{h}">{text}</a>', {"link": u.geturl()})
    for src in p.srcs:
        plat = platform_of(urljoin(url, src))
        if plat:
            add("platform", plat, src, {"embed": urljoin(url, src)})
    for block in p.ld:
        try:
            data = json.loads(block)
        except ValueError:
            continue
        for t in _ld_values(data, "telephone"):
            n = to_e164(t, country)
            if n:
                add("phone", n, f'"telephone": "{t}"')
        for e in _ld_values(data, "email"):
            e = e.removeprefix("mailto:").strip()
            if _EMAIL.fullmatch(e):
                add("email", e.lower(), f'"email": "{e}"')
    text = " ".join(" ".join(p.text).split())
    for m in _EMAIL.finditer(text):
        addr = m.group(0).rstrip(".").lower()
        if not re.search(r"\.(png|jpe?g|gif|webp|svg)$", addr):
            add("email", addr, text[max(0, m.start() - 40): m.end() + 20])
    for f in p.forms:
        joined = " ".join(f["fields"])
        if len(f["fields"]) >= 3 and len(_BOOKING_FIELD.findall(joined)) >= 2:
            add("booking_form", urljoin(url, f["action"] or url), joined[:200], {"fields": f["fields"][:20]})
    return facts


def contact_links(html: str, url: str) -> List[str]:
    p = _Page()
    try:
        p.feed(html)
    except Exception:
        pass
    host = urlsplit(url).hostname
    out = []
    for href, text in p.links:
        u = urljoin(url, href.split("#")[0])
        if urlsplit(u).hostname == host and u != url and _CONTACT_LINK.search(f"{href} {text}") and u not in out:
            out.append(u)
    return out[:MAX_EXTRA_PAGES]


# ── fetching, guarded ───────────────────────────────────────────────────────────────────────────

Http = Callable[..., Awaitable[Any]]      # (method, url, headers=, json=) -> .status_code, .text, .json(), .headers
Resolve = Callable[[str], List[str]]      # host -> IP strings


def _resolve(host: str) -> List[str]:
    return [ai[4][0] for ai in socket.getaddrinfo(host, None)]


def public_url(url: str, resolve: Resolve = _resolve) -> str:
    """Refuse anything but http(s) on a PUBLIC host: this server must never be made to fetch its own network."""
    u = urlsplit(url)
    if u.scheme not in ("http", "https") or not u.hostname:
        raise ReadRefused("url_not_web", f"{url!r} is not an http(s) URL")
    if u.username or u.password or (u.port not in (None, 80, 443)):
        raise ReadRefused("url_not_plain", "a venue URL carries no credentials and no unusual port")
    try:
        ips = resolve(u.hostname)
    except Exception:
        raise ReadRefused("host_unresolvable", f"{u.hostname} does not resolve") from None
    for ip in ips:
        a = ipaddress.ip_address(ip.split("%")[0])
        if not a.is_global:
            raise ReadRefused("host_not_public", f"{u.hostname} resolves to a non-public address")
    return url


async def _get(http: Http, url: str, resolve: Resolve) -> Any:
    """GET with redirects followed BY HAND, each hop re-checked as public and never onto a booking platform."""
    for _ in range(4):
        public_url(url, resolve)
        if platform_of(url):
            raise ReadRefused("platform_not_fetched", f"{url} is a booking platform; it is recorded, never fetched")
        r = await http("GET", url, headers={"user-agent": USER_AGENT, "accept": "text/html"})
        if r.status_code in (301, 302, 303, 307, 308) and r.headers.get("location"):
            url = urljoin(url, r.headers["location"])
            continue
        return url, r
    raise ReadRefused("too_many_redirects", "more than three redirects")


async def _allowed(http: Http, url: str, resolve: Resolve) -> bool:
    u = urlsplit(url)
    robots = f"{u.scheme}://{u.netloc}/robots.txt"
    try:
        _, r = await _get(http, robots, resolve)
    except ReadRefused:
        return False
    if r.status_code >= 500:
        return False           # robots unreadable because the server failed: do not assume permission
    if r.status_code != 200:
        return True            # no robots.txt: the web's convention is that everything is allowed
    rp = RobotFileParser()
    rp.parse(r.text.splitlines())
    return rp.can_fetch(USER_AGENT, url)


async def read_site(http: Http, url: str, country: Optional[str], now: datetime, resolve: Resolve = _resolve) -> Tuple[List[Fact], List[dict]]:
    facts: List[Fact] = []
    sources: List[dict] = []
    plat = platform_of(url)
    if plat:
        sources.append({"url": url, "result": "not fetched — a booking platform"})
        return [Fact("platform", plat, "site", url, "the link given for them", url, now.isoformat(), "", {"link": url})], sources
    queue, done = [url], set()
    while queue and len(done) < 1 + MAX_EXTRA_PAGES:
        page = queue.pop(0)
        if page in done:
            continue
        done.add(page)
        try:
            if not await _allowed(http, page, resolve):
                sources.append({"url": page, "result": "not fetched — robots.txt does not allow it"})
                continue
            final, r = await _get(http, page, resolve)
        except ReadRefused as e:
            sources.append({"url": page, "result": f"not fetched — {e}"})
            continue
        except Exception as e:
            sources.append({"url": page, "result": f"not fetched — {type(e).__name__}"})
            continue
        html = (r.text or "")[:MAX_BYTES]
        sources.append({"url": final, "result": f"HTTP {r.status_code}", "bytes": len(html),
                        "sha256": hashlib.sha256(html.encode("utf-8", "replace")).hexdigest(), "fetched_at": now.isoformat()})
        if r.status_code != 200:
            continue
        facts += [f for f in facts_from_html(html, final, country, now.isoformat()) if (f.kind, f.value) not in {(x.kind, x.value) for x in facts}]
        if page == url:
            queue += contact_links(html, final)
    return facts, sources


def places_key() -> str:
    return os.getenv("GOOGLE_PLACES_API_KEY", "").strip()


PLACE_URL = "https://places.googleapis.com/v1/places/{id}"
PLACE_FIELDS = ",".join(f.removeprefix("places.") for f in PLACES_FIELDS.split(","))
#: S-65 · what a candidate shows: its listing facts, nothing fetched from its own site yet
FIND_FIELDS = ("places.id,places.displayName,places.formattedAddress,places.internationalPhoneNumber,places.nationalPhoneNumber,"
               "places.websiteUri,places.addressComponents,places.primaryTypeDisplayName,places.businessStatus")
FIND_MAX = 5
_PLACE_ID = re.compile(r"[A-Za-z0-9_-]{10,300}")


def _country_of(pl: dict) -> Optional[str]:
    return next((c.get("shortText") for c in pl.get("addressComponents") or [] if "country" in (c.get("types") or [])), None)


def _place_facts(pl: dict, sha: str, now: datetime) -> Tuple[List[Fact], dict, Optional[str], Optional[str]]:
    """One Places listing → its facts, each with the listing's own words. (facts, listing, country, website)"""
    country = _country_of(pl)
    listing = {"name": (pl.get("displayName") or {}).get("text"), "address": pl.get("formattedAddress"), "place_id": pl.get("id")}
    link = f"https://www.google.com/maps/place/?q=place_id:{pl.get('id')}"
    facts = []
    phone_raw = pl.get("internationalPhoneNumber") or pl.get("nationalPhoneNumber")
    n = to_e164(phone_raw, country) if phone_raw else None
    # ⚠ the listing's own name and address go into the label, so the read-back says WHICH listing — a wrong match is
    # heard before the yes, never discovered after
    label = f"their Google listing ({listing['name']}, {listing['address']})"
    if n:
        facts.append(Fact("phone", n, "places", link, label, f'"internationalPhoneNumber": "{phone_raw}"',
                          now.isoformat(), sha, {"listing": listing}))
    # everything else the listing publishes, recorded the same way — the listing's own words, verbatim
    if pl.get("formattedAddress"):
        facts.append(Fact("address", pl["formattedAddress"], "places", link, label, f'"formattedAddress": "{pl["formattedAddress"]}"',
                          now.isoformat(), sha, {"listing": listing}))
    if pl.get("websiteUri"):
        facts.append(Fact("website", pl["websiteUri"], "places", link, label, f'"websiteUri": "{pl["websiteUri"]}"',
                          now.isoformat(), sha, {"listing": listing}))
    hours = (pl.get("regularOpeningHours") or {}).get("weekdayDescriptions")
    if isinstance(hours, list) and hours and all(isinstance(h, str) for h in hours):
        facts.append(Fact("hours", " · ".join(hours), "places", link, label, '"regularOpeningHours.weekdayDescriptions"',
                          now.isoformat(), sha, {"listing": listing, "weekday_descriptions": hours,
                                                 "periods": (pl.get("regularOpeningHours") or {}).get("periods")}))
    return facts, listing, country, pl.get("websiteUri")


async def read_places(http: Http, key: str, name: str, city: str, now: datetime) -> Tuple[List[Fact], List[dict], Optional[dict], Optional[str], Optional[str]]:
    """The venue's Google business listing: its phone and website. Returns (facts, sources, listing, country, website)."""
    body = {"textQuery": f"{name}, {city}", "maxResultCount": 1}
    try:
        r = await http("POST", PLACES_URL, headers={"X-Goog-Api-Key": key, "X-Goog-FieldMask": PLACES_FIELDS,
                                                    "content-type": "application/json"}, json=body)
        data = r.json()
    except Exception as e:
        return [], [{"url": PLACES_URL, "result": f"not read — {type(e).__name__}"}], None, None, None
    raw = json.dumps(data, sort_keys=True)
    sha = hashlib.sha256(raw.encode()).hexdigest()
    src = {"url": PLACES_URL, "query": body["textQuery"], "result": f"HTTP {r.status_code}", "sha256": sha, "fetched_at": now.isoformat()}
    places = data.get("places") if isinstance(data, dict) and r.status_code == 200 else None
    if not places:
        src["result"] += " — no listing" if r.status_code == 200 else f" — {str(data)[:200]}"
        return [], [src], None, None, None
    facts, listing, country, website = _place_facts(places[0], sha, now)
    return facts, [src], listing, country, website


async def read_place_id(http: Http, key: str, place_id: str, now: datetime) -> Tuple[List[Fact], List[dict], Optional[dict], Optional[str], Optional[str]]:
    """S-65 · the EXACT listing the guest picked from "Find venues" — never a fresh search that could land elsewhere."""
    url = PLACE_URL.format(id=place_id)
    try:
        r = await http("GET", url, headers={"X-Goog-Api-Key": key, "X-Goog-FieldMask": PLACE_FIELDS})
        data = r.json()
    except Exception as e:
        return [], [{"url": url, "result": f"not read — {type(e).__name__}"}], None, None, None
    sha = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
    src = {"url": url, "result": f"HTTP {r.status_code}", "sha256": sha, "fetched_at": now.isoformat()}
    if r.status_code != 200 or not isinstance(data, dict) or data.get("id") != place_id:
        src["result"] += f" — {str(data)[:200]}"
        return [], [src], None, None, None
    facts, listing, country, website = _place_facts(data, sha, now)
    return facts, [src], listing, country, website


class FindRefused(ReadRefused):
    pass


async def find_venues(http: Http, *, what: str, where: str, country: Optional[str], now: datetime) -> dict:
    """S-65 · "Find venues": a kind of place in a place ("tattoo studio", "Nairobi, KE") → up to five candidates, each
    with what its Google listing says. Search only: nothing is contacted, nothing is read from their sites until one is
    picked, and then it is the existing venue read on THAT listing."""
    if not isinstance(what, str) or not 2 <= len(what.strip()) <= 60:
        raise FindRefused("what_invalid", "what to look for is 2–60 characters (e.g. \"tattoo studio\")")
    if not isinstance(where, str) or not 2 <= len(where.strip()) <= 80:
        raise FindRefused("where_invalid", "where is 2–80 characters (e.g. \"Nairobi\")")
    country = country.strip().upper() if isinstance(country, str) and country.strip() else None
    if country and not re.fullmatch(r"[A-Z]{2}", country):
        raise FindRefused("country_invalid", "country is a two-letter code")
    key = places_key()
    if not key:
        raise FindRefused("places_not_configured", "GOOGLE_PLACES_API_KEY is not set, so there is nothing to search with")
    body = {"textQuery": f"{what.strip()} in {where.strip()}", "maxResultCount": FIND_MAX, **({"regionCode": country} if country else {})}
    try:
        r = await http("POST", PLACES_URL, headers={"X-Goog-Api-Key": key, "X-Goog-FieldMask": FIND_FIELDS,
                                                    "content-type": "application/json"}, json=body)
        data = r.json()
    except Exception as e:
        raise FindRefused("places_unreachable", f"Google Places could not be reached: {type(e).__name__}") from None
    if r.status_code != 200 or not isinstance(data, dict):
        raise FindRefused("places_refused", f"Google Places answered HTTP {r.status_code}: {str(data)[:200]}")
    sha = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
    out = []
    for pl in (data.get("places") or [])[:FIND_MAX]:
        if not isinstance(pl, dict) or not isinstance(pl.get("id"), str) or not _PLACE_ID.fullmatch(pl["id"]):
            continue
        c = _country_of(pl)
        raw = pl.get("internationalPhoneNumber") or pl.get("nationalPhoneNumber")
        out.append({"place_id": pl["id"], "name": (pl.get("displayName") or {}).get("text"), "address": pl.get("formattedAddress"),
                    "country": c, "phone": (to_e164(raw, c) if raw else None) or raw, "website": pl.get("websiteUri"),
                    "type": (pl.get("primaryTypeDisplayName") or {}).get("text"), "status": pl.get("businessStatus"),
                    "listing_url": f"https://www.google.com/maps/place/?q=place_id:{pl['id']}"})
    return {"query": body["textQuery"], "candidates": out,
            "source": {"url": PLACES_URL, "query": body["textQuery"], "result": f"HTTP 200 — {len(out)} listing(s)",
                       "sha256": sha, "fetched_at": now.isoformat()}}


async def read_venue(http: Http, *, name: str, city: str, country: Optional[str], website: Optional[str],
                     now: datetime, resolve: Resolve = _resolve, place_id: Optional[str] = None) -> VenueRead:
    if not isinstance(name, str) or not 2 <= len(name.strip()) <= 80:
        raise ReadRefused("name_invalid", "a venue name is 2–80 characters")
    if not isinstance(city, str) or not 2 <= len(city.strip()) <= 60:
        raise ReadRefused("city_invalid", "a city is 2–60 characters")
    country = country.upper() if isinstance(country, str) and country.strip() else None
    facts: List[Fact] = []
    sources: List[dict] = []
    listing = None
    key = places_key()
    if key:
        if place_id is not None and not (isinstance(place_id, str) and _PLACE_ID.fullmatch(place_id)):
            raise ReadRefused("place_id_invalid", "not a Google place id")
        f, s, listing, pc, site = (await read_place_id(http, key, place_id, now) if place_id
                                   else await read_places(http, key, name.strip(), city.strip(), now))
        facts += f
        sources += s
        country = country or pc
        website = website or site
    else:
        sources.append({"url": PLACES_URL, "result": "not read — GOOGLE_PLACES_API_KEY is not set"})
    if website:
        try:
            public_url(website, resolve)
            f, s = await read_site(http, website, country, now, resolve)
            facts += [x for x in f if (x.kind, x.value) not in {(y.kind, y.value) for y in facts}]
            sources += s
        except ReadRefused as e:
            sources.append({"url": website, "result": f"not fetched — {e}"})
    return VenueRead(name=name.strip(), country=country, facts=facts, sources=sources, listing=listing)
