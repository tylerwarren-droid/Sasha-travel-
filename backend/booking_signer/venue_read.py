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
import logging
import os
import re
import socket
from dataclasses import asdict, dataclass, field
from datetime import datetime
from html.parser import HTMLParser
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urljoin, urlsplit
from urllib.robotparser import RobotFileParser

log = logging.getLogger("booking_signer.venue_read")

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
    "KE": ("254", True, "en", "Africa/Nairobi"),   # S-64 §6.2 · Nairobi: national numbers are 07…/01…, trunk 0
}

#: Booking platforms, recognised from a LINK or an embed — never fetched.
PLATFORMS = {
    "thefork": "TheFork", "eltenedor": "TheFork", "lafourchette": "TheFork", "opentable": "OpenTable",
    "covermanager": "CoverManager", "sevenrooms": "SevenRooms", "resy.com": "Resy", "quandoo": "Quandoo",
    "tablein": "Tablein", "bookatable": "Bookatable", "resdiary": "ResDiary", "zenchef": "Zenchef",
    "guestonline": "Guestonline", "restoo": "Restoo", "booksy": "Booksy", "fresha": "Fresha",
    # Sasha 138 · HOTEL booking engines — recognised from the link or widget on the hotel's OWN site; like every platform here,
    # their pages are never fetched (the guest opens them, with one tap)
    "direct-book.com": "SiteMinder", "book-directonline.com": "SiteMinder", "thebookingbutton": "SiteMinder",
    "littlehotelier.com": "Little Hotelier", "cloudbeds.com": "Cloudbeds", "mews.com": "Mews", "mews.li": "Mews",
    "synxis.com": "SynXis", "secure-hotel-booking.com": "D-Edge", "d-edge.com": "D-Edge", "availpro.com": "D-Edge",
    "roiback.com": "Roiback", "neobookings.com": "Neobookings", "bookassist": "Bookassist", "guestcentric": "GuestCentric",
    "omnibees.com": "Omnibees", "simplebooking.it": "Simple Booking", "webhotelier.net": "WebHotelier", "ihotelier.com": "iHotelier",
    "hotetec.com": "Hotetec",
}
HOTEL_ENGINES = frozenset(("SiteMinder", "Little Hotelier", "Cloudbeds", "Mews", "SynXis", "D-Edge", "Roiback", "Neobookings",
                           "Bookassist", "GuestCentric", "Omnibees", "Simple Booking", "WebHotelier", "iHotelier", "Hotetec"))

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
        self.site_names: List[str] = []
        self.share_images: List[str] = []   # Sasha 88 · og:image / twitter:image: the picture the venue chose for its site
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
        if tag == "meta" and a.get("property", "").lower() == "og:site_name" and a.get("content", "").strip():
            self.site_names.append(a["content"].strip())   # Sasha 64 · the venue's name as its OWN site gives it
        if tag == "meta" and (a.get("property") or a.get("name") or "").lower() in ("og:image", "og:image:secure_url", "og:image:url", "twitter:image") \
                and a.get("content", "").strip():
            self.share_images.append(a["content"].strip())
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
            if kind == "platform" and detail:
                # Sasha 95 · EVERY link and embed to that platform is kept, not only the first: the first CoverManager link
                # on a page can be its gift-voucher shop (/eco/buy_products/…), the booking page a later one
                f0 = next(f for f in facts if f.kind == kind and f.value == value)
                for k, v in detail.items():
                    f0.detail.setdefault(k + "s", [f0.detail.get(k)] if f0.detail.get(k) else [])
                    if v not in f0.detail[k + "s"]:
                        f0.detail[k + "s"].append(v)
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
        # Sasha 64 · the venue's OWN name (schema.org): what the booking is stored under, never the listing's
        if isinstance(data, dict) and isinstance(data.get("name"), str) and data.get("@type") and 2 <= len(data["name"].strip()) <= 80:
            add("name", data["name"].strip(), f'"name": "{data["name"].strip()}"')
        # S-66 · the venue's OWN opening hours (schema.org), which the hours check reads before Google's
        from .hours import from_jsonld
        week = from_jsonld(data)
        if week:
            names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
            text = " · ".join(f"{names[d]} " + ", ".join(f"{a:%H:%M}–{b:%H:%M}" for a, b in week[d]) for d in sorted(week))
            add("hours", text, '"openingHours…" (schema.org)',
                {"week": {str(d): [[f"{a:%H:%M}", f"{b:%H:%M}"] for a, b in iv] for d, iv in week.items()}})
    for n in p.site_names:
        if 2 <= len(n) <= 80:
            add("name", n, f'<meta property="og:site_name" content="{n}">')
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
               "places.websiteUri,places.addressComponents,places.primaryTypeDisplayName,places.businessStatus,"
               # S-68 step 2 · what the ranking reads. The Enterprise SKU, which phone and website already reach
               # (docs/sasha/S-68-step1-places-terms.md): the cost of a search does not change
               "places.rating,places.userRatingCount,places.priceLevel,places.location,places.regularOpeningHours,"
               # Sasha 156 · the listing's first photo's NAME (Pro-tier field, inside the Enterprise SKU already paid):
               # the card's fallback picture when the venue's own site names none — resolved per shown card (google_photos)
               "places.photos")
#: S-68 · search wider, show fewer: 20 is Text Search's cap; the chat shows 3–5 of them
FIND_MAX = 20
SHOW_MAX = 5
#: Places' priceLevel → the € shown; UNSPECIFIED and anything unknown are "not listed", never guessed
PRICE_LEVELS = {"PRICE_LEVEL_FREE": 0, "PRICE_LEVEL_INEXPENSIVE": 1, "PRICE_LEVEL_MODERATE": 2,
                "PRICE_LEVEL_EXPENSIVE": 3, "PRICE_LEVEL_VERY_EXPENSIVE": 4}
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
    # Sasha 64 · the label is stored; the listing's name and address are not (places_terms) — the chat shows the listing
    label = "their Google Maps listing"
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


def _ranking_facts(pl: dict) -> dict:
    """S-68 step 2 · what the listing says that a ranking reads — each value exactly as Places gave it, or None when the
    listing doesn't say (or says something malformed). Nothing is defaulted: a missing rating is "no rating", not 0."""
    rating, count = pl.get("rating"), pl.get("userRatingCount")
    loc = pl.get("location") or {}
    lat, lng = loc.get("latitude"), loc.get("longitude")
    num = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)
    periods = (pl.get("regularOpeningHours") or {}).get("periods")
    return {
        "rating": float(rating) if num(rating) and 1 <= rating <= 5 else None,
        "rating_count": int(count) if num(count) and count >= 0 and int(count) == count else None,
        "price_level": PRICE_LEVELS.get(pl.get("priceLevel")),
        "location": {"lat": float(lat), "lng": float(lng)} if num(lat) and num(lng) and -90 <= lat <= 90 and -180 <= lng <= 180 else None,
        "hours_periods": periods if isinstance(periods, list) and periods else None,
    }


def how_she_books(c: dict) -> dict:
    """S-68 step 5 · BEFORE a pick, how Sasha would reach a candidate — from its listing alone, never claiming more.
    The real ladder comes from the venue read after the pick (its own site first). {how, words}:
      call · a listed phone, a call script in its country's language, and calls on;
      site · a website that is the venue's own (a booking platform's page is never counted, S-37);
      you  · otherwise — and why."""
    from .calls import LANGUAGES, calls_enabled
    lang = COUNTRIES.get(c.get("country") or "", (None, None, None, None))[2]
    site = c.get("website")
    plat = platform_of(site) if site else None
    if c.get("phone") and lang in LANGUAGES:
        if calls_enabled():
            return {"how": "call", "words": "Sasha can call them"}
        if not site or plat:
            return {"how": "you", "words": "a phone number is listed, but Sasha's calls are off right now — you'd phone them"}
    if site and not plat:
        return {"how": "site", "words": "Sasha will check their site for a form or an email"}
    if plat:
        return {"how": "you", "words": f"they book through {plat} — you'd book there; Sasha never books on a platform"}
    if c.get("phone"):
        return {"how": "you", "words": "a phone number is listed, but Sasha has no call script in their language yet — you'd phone them"}
    return {"how": "you", "words": "no phone or site listed — you'd contact them"}


#: S-68 step 3 · where "near" is: one Text Search for the place the guest named, its location only (the Pro SKU)
NEAR_FIELDS = "places.id,places.location"


def haversine_m(a: dict, b: dict) -> float:
    """Straight-line distance in metres between two {lat, lng}: never a walking or driving distance."""
    from math import asin, cos, radians, sin, sqrt
    la1, lo1, la2, lo2 = map(radians, (a["lat"], a["lng"], b["lat"], b["lng"]))
    h = sin((la2 - la1) / 2) ** 2 + cos(la1) * cos(la2) * sin((lo2 - lo1) / 2) ** 2
    return 2 * 6_371_000 * asin(sqrt(h))


def distance_words(m: Optional[float]) -> str:
    """"350 m away (straight line)" · "1.2 km away (straight line)" · "distance not known" — never "nearby"."""
    if m is None:
        return "distance not known"
    if m < 1000:
        return f"{max(10, int(round(m / 10.0)) * 10)} m away (straight line)"
    return f"{m / 1000:.1f} km away (straight line)"


#: "near my hotel" names no place: the guest is asked for it, never guessed (no itinerary holds a hotel today)
_NEAR_UNNAMED = re.compile(r"(?:my|our|the)\s+(?:hotel|apartment|airbnb|flat|place|accommodation)", re.I)


async def locate(http: Http, key: str, near: str, where: str, country: Optional[str]) -> dict:
    """The place the guest said ("Hotel Urban", "Calle Mayor 10") → {asked, found, location?, place_id?, why?}.
    Read for THIS search only, never stored (the Maps terms: no caching)."""
    out: Dict[str, Any] = {"asked": near, "found": False}
    if _NEAR_UNNAMED.fullmatch(near.strip()):
        out["why"] = "which hotel? — tell me its name or address and I'll measure from it"
        return out
    body = {"textQuery": f"{near.strip()}, {where.strip()}", "maxResultCount": 1, **({"regionCode": country} if country else {})}
    try:
        r = await http("POST", PLACES_URL, headers={"X-Goog-Api-Key": key, "X-Goog-FieldMask": NEAR_FIELDS,
                                                    "content-type": "application/json"}, json=body)
        data = r.json()
    except Exception as e:
        out["why"] = f"I couldn't look up {near!r}: {type(e).__name__}"
        return out
    pl = ((data.get("places") or [None])[0] if isinstance(data, dict) and r.status_code == 200 else None) or {}
    loc = _ranking_facts(pl)["location"] if isinstance(pl, dict) else None
    if not loc:
        out["why"] = f"Google Maps has no place matching {near!r} in {where}"
        return out
    return {**out, "found": True, "location": loc, "place_id": pl.get("id")}


COUNTRY_NAME = {"ES": "Spain", "PT": "Portugal", "FR": "France", "IT": "Italy", "DE": "Germany", "AT": "Austria", "GB": "United Kingdom",
                "IE": "Ireland", "VN": "Vietnam", "KE": "Kenya", "TH": "Thailand", "JP": "Japan", "KR": "South Korea", "US": "United States",
                "MX": "Mexico", "AR": "Argentina", "TR": "Turkey", "NL": "Netherlands", "BE": "Belgium", "GR": "Greece", "ID": "Indonesia",
                "KH": "Cambodia", "LA": "Laos", "MA": "Morocco", "PE": "Peru", "CO": "Colombia", "BR": "Brazil", "CH": "Switzerland"}


async def find_venues(http: Http, *, what: str, where: Optional[str], country: Optional[str], now: datetime,
                      near: Optional[str] = None, open_at: Optional[str] = None, named: bool = False) -> dict:
    """S-65 · "Find venues": a kind of place in a place ("tattoo studio", "Nairobi, KE") → up to twenty candidates (S-68; the chat shows `show` of them), each
    with what its Google listing says. Search only: nothing is contacted, nothing is read from their sites until one is
    picked, and then it is the existing venue read on THAT listing."""
    if not isinstance(what, str) or not 2 <= len(what.strip()) <= 60:
        raise FindRefused("what_invalid", "what to look for is 2–60 characters (e.g. \"tattoo studio\")")
    if named and not (isinstance(where, str) and where.strip()):
        where = None   # Sasha 158 · a venue by NAME: Google finds it wherever it is
    elif not isinstance(where, str) or not 2 <= len(where.strip()) <= 80:
        raise FindRefused("where_invalid", "where is 2–80 characters (e.g. \"Nairobi\")")
    country = country.strip().upper() if isinstance(country, str) and country.strip() else None
    if country and not re.fullmatch(r"[A-Z]{2}", country):
        raise FindRefused("country_invalid", "country is a two-letter code")
    key = places_key()
    if not key:
        raise FindRefused("places_not_configured", "GOOGLE_PLACES_API_KEY is not set, so there is nothing to search with")
    if near is not None and (not isinstance(near, str) or not 2 <= len(near.strip()) <= 120):
        raise FindRefused("near_invalid", "near is 2–120 characters (a hotel's name, or an address)")
    when = None
    if open_at is not None:   # S-68 step 4 · the venue's LOCAL time the guest asked for
        try:
            when = datetime.strptime(str(open_at), "%Y-%m-%dT%H:%M")
        except ValueError:
            raise FindRefused("open_at_invalid", "open_at is the local time as YYYY-MM-DDTHH:MM") from None
    # Sasha 169 · the country in the words too: from production's servers Google found 0 for "restaurant in Hoi An" and 20 for
    # "restaurant in Hoi An, Vietnam" (regionCode alone did not help; a laptop in Madrid got 19 either way)
    in_words = f"{where.strip()}, {COUNTRY_NAME[country]}" if where is not None and country and "," not in where and COUNTRY_NAME.get(country) \
        else (where.strip() if where is not None else None)
    body = {"textQuery": what.strip() if in_words is None else f"{what.strip()} in {in_words}",
            "maxResultCount": 5 if named else FIND_MAX, **({"regionCode": country} if country else {})}
    if named and where is None:   # Sasha 161 · a venue named with no city: near the guest's home first ("book Indian Accent"
        try:                      # found New Delhi's, then New York's) — SASHA_HOME_LATLNG, Madrid by default, 50 km
            lat, lng = (float(x) for x in (os.getenv("SASHA_HOME_LATLNG", "") or "40.4168,-3.7038").split(","))
            body["locationBias"] = {"circle": {"center": {"latitude": lat, "longitude": lng}, "radius": 50000.0}}
        except ValueError:
            pass
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
                    "listing_url": f"https://www.google.com/maps/place/?q=place_id:{pl['id']}", **_ranking_facts(pl),
                    **({"gphoto": g} if (g := _gphoto(pl)) else {})})
        out[-1]["books"] = how_she_books(out[-1])   # S-68 step 5
    if when is not None:
        from .hours import from_places_periods, open_at as _open_at
        for c in out:
            c["open_at"] = _open_at(from_places_periods(c["hours_periods"]), when)
    origin = await locate(http, key, near, where, country) if near else None
    if origin is not None:   # S-68 step 3 · straight-line distance from the place the guest named
        for c in out:
            m = haversine_m(origin["location"], c["location"]) if origin["found"] and c["location"] else None
            c["distance_m"] = int(round(m)) if m is not None else None
            c["distance"] = distance_words(m) if origin["found"] else None
    # S-68 step 6 · every chip's order, once: a re-sort in the chat is no new search
    from .ranking import price_words, rank, rating_words
    for c in out:
        c["rating_words"], c["price_words"] = rating_words(c), price_words(c)
    ranking = rank(out, open_at=when.strftime("%Y-%m-%dT%H:%M") if when is not None else None,
                   near_found=bool(origin and origin["found"]))
    return {"query": body["textQuery"], "candidates": out, "show": SHOW_MAX, "ranking": ranking,
            **({"near": {k: origin[k] for k in ("asked", "found", "why") if k in origin}} if origin is not None else {}),
            **({"open_at": when.strftime("%Y-%m-%dT%H:%M")} if when is not None else {}),
            "source": {"url": PLACES_URL, "query": body["textQuery"], "result": f"HTTP 200 — {len(out)} listing(s)",
                       "sha256": sha, "fetched_at": now.isoformat()}}


# ── Sasha 156 · Google Places photos: the fallback picture where the venue's own (og:image) is missing ──────────────

PHOTO_NAME = re.compile(r"places/[A-Za-z0-9_-]{10,}/photos/[A-Za-z0-9_-]{10,}")


def _gphoto(pl: dict) -> Optional[dict]:
    """The listing's first photo: its resource name and who took it (Google's terms: the author is shown with it)."""
    ph = (pl.get("photos") or [None])[0]
    if not isinstance(ph, dict) or not PHOTO_NAME.fullmatch(str(ph.get("name") or "")):
        return None
    by = [a.get("displayName") for a in ph.get("authorAttributions") or [] if isinstance(a, dict) and a.get("displayName")]
    return {"name": ph["name"], "by": by[:2]}


async def google_photo_uri(http: Http, name: str, width: int = 480) -> Optional[str]:
    """The photo's short-lived public URL (googleusercontent) — the key never leaves the server; nothing is stored."""
    key = places_key()
    if not key or not PHOTO_NAME.fullmatch(name or ""):
        return None
    url = f"https://places.googleapis.com/v1/{name}/media?maxWidthPx={max(100, min(int(width), 1200))}&skipHttpRedirect=true"
    try:
        r = await http("GET", url, headers={"X-Goog-Api-Key": key})
        j = r.json() if r.status_code == 200 else {}
    except Exception as e:
        log.info("[venue_read] google photo not resolved: %s", type(e).__name__)
        return None
    uri = (j or {}).get("photoUri")
    return uri if isinstance(uri, str) and uri.startswith("https://") else None


async def read_venue(http: Http, *, name: str, city: str, country: Optional[str], website: Optional[str],
                     now: datetime, resolve: Resolve = _resolve, place_id: Optional[str] = None,
                     asked_for: Optional[str] = None) -> VenueRead:
    if not isinstance(name, str) or not 2 <= len(name.strip()) <= 80:
        raise ReadRefused("name_invalid", "a venue name is 2–80 characters")
    if not isinstance(city, str) or not 2 <= len(city.strip()) <= 60:
        raise ReadRefused("city_invalid", "a city is 2–60 characters")
    country = country.upper() if isinstance(country, str) and country.strip() else None
    facts: List[Fact] = []
    places_facts: List[Fact] = []
    sources: List[dict] = []
    listing = None
    key = places_key()
    # Sasha 94 · OUR OWN test venue is never looked up on Google: its name could match a real place (1 Oct: "Sasha Test
    # Venue, Madrid" pulled Restaurante Sacha's listing and phone into the read). Its own site is the whole read.
    from .form_rung import is_test_venue
    if website and is_test_venue(website):
        key = None
        sources.append({"url": PLACES_URL, "result": "not read — our own test venue is never looked up on Google"})
    elif key:
        if place_id is not None and not (isinstance(place_id, str) and _PLACE_ID.fullmatch(place_id)):
            raise ReadRefused("place_id_invalid", "not a Google place id")
        f, s, listing, pc, site = (await read_place_id(http, key, place_id, now) if place_id
                                   else await read_places(http, key, name.strip(), city.strip(), now))
        places_facts = f
        sources += s
        country = country or pc
        website = website or site
    elif not key:
        sources.append({"url": PLACES_URL, "result": "not read — GOOGLE_PLACES_API_KEY is not set"})
    if website:
        try:
            public_url(website, resolve)
            f, s = await read_site(http, website, country, now, resolve)
            facts += f
            sources += s
        except ReadRefused as e:
            sources.append({"url": website, "result": f"not fetched — {e}"})
    # Sasha 64 · B · the venue's OWN site first: a number it publishes is the one called; the listing's only fills gaps
    facts += [x for x in places_facts if (x.kind, x.value) not in {(y.kind, y.value) for y in facts}]
    return VenueRead(name=stored_name(name, place_id, facts, asked_for, city), country=country, facts=facts,
                     sources=sources, listing=listing)


def stored_name(name: str, place_id: Optional[str], facts: List[Fact], asked_for: Optional[str], city: str) -> str:
    """Sasha 64 · A · the name a read, a reservation and an itinerary are STORED under — never the listing's.
    Typed by the guest (no place_id): their words. Picked from the Google Maps cards (place_id): the venue's own site's
    name, else what the guest asked for ("tattoo studio in Madrid")."""
    if not place_id:
        return name.strip()
    own = next((f.value for f in facts if f.kind == "name" and f.source_kind == "site"), None)
    if own:   # "Ink Sweet Tattoo Studio | Mejor estudio de tatuajes en Madrid" → its name, not its page title's tail
        head = re.split(r"\s+[|·–—]\s+", own, maxsplit=1)[0].strip()
        return head if len(head) >= 2 else own
    if isinstance(asked_for, str) and 2 <= len(asked_for.strip()) <= 60:
        return f"{asked_for.strip()} in {city.strip()}"[:80]
    return f"the place you picked in {city.strip()}"[:80]
