"""CR 22 · THE PREFILL LIBRARY — per booking engine: which fields a link can carry, in which format, and the taps left.

DATA for the Sasha tab's slot_link.py (S-37 Recipe / Sasha 138 HOTEL_PREFILL), which wires build_* to it. Every entry was
written from the engine's PUBLIC docs or from links venues publish on their own sites (docs/products/cr22/, 5 Oct 2026),
robots first; no platform's booking page was ever opened or probed. ⚠ An entry is UNVERIFIED (`verified=None`) until
the founder opens one real link once — 5 Oct 2026: FILLED TableCheck, SevenRooms, Cloudbeds, SiteMinder, Omnibees;
Guestcentric rebuilt from the engine's own search (CR 26), its new link awaiting his check (engine_check: "1 filled / 2 not filled / 3 wrong page") — until then Sasha never
says "it's filled in", only "I've added the dates to the link; check them there".

Nothing here sends a request anywhere: build() only adds query parameters to a venue page string we already hold.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, time
from typing import Callable, Dict, List, Optional, Tuple
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


@dataclass(frozen=True)
class Engine:
    name: str
    kind: str                                  #: "restaurant" | "hotel" | "spa"
    basis: str                                 #: "documented" | "seen_in_links" | "none"
    source: str                                #: where the parameters were read
    params: Dict[str, str] = field(default_factory=dict)   #: our field → the engine's parameter
    date_fmt: str = "%Y-%m-%d"
    time_fmt: str = "%H:%M"
    fixed: Tuple[Tuple[str, str], ...] = ()    #: parameters the engine needs alongside (e.g. SiteMinder infants=0)
    omit_zero: Tuple[str, ...] = ()            #: our fields left out when 0 (SynXis: "&Child=0" is incorrect)
    taps_after: int = 0                        #: taps left after opening a link that carries every `params` field
    taps_page: int = 0                         #: taps left from the venue's page with nothing prefilled
    terms: str = ""                            #: what its terms say about automation / framing (live hand-over)
    verified: Optional[str] = None             #: who opened a real link and saw it filled, and when — None until then
    not_filled: Optional[str] = None           #: who opened a real link and saw it NOT filled, and when — the link then
                                               #: carries nothing (the guest picks the slot on the page)
    entry: Optional[Callable[[str], Optional[str]]] = None   #: the engine's own entry from a venue page string, or None
                                               #: when that page isn't the engine (then nothing is carried)

    @property
    def prefills(self) -> List[str]:
        return list(self.params)


def _split_date(prefix: str) -> Callable[[date], Dict[str, str]]:
    return lambda d: {f"{prefix}_day": f"{d.day:02d}", f"{prefix}_month": f"{d.month:02d}", f"{prefix}_year": str(d.year)}


LIBRARY: Dict[str, Engine] = {e.name: e for e in (
    # ── restaurants ──
    Engine("TableCheck", "restaurant", "documented", "TableCheck API docs 'Web Booking v1' (updated 2026-01-21)",
           {"date": "start_date", "time": "start_time", "party": "pax"}, taps_after=6, taps_page=9,
           terms="audience includes concierge services; guest-details prefill only via a whitelisted partner SSO",
           verified="the founder, 5 Oct 2026: The Hill Station (Hoi An) link opened once — filled (via the Sasha tab's engine_check)"),
    Engine("SevenRooms", "restaurant", "seen_in_links", "booking URLs indexed from venues (London, Madrid, Lisbon)",
           {"date": "date", "party": "party_size", "time": "start_time"}, taps_after=7, taps_page=9,
           verified="the founder, 5 Oct 2026: EVOK Brach (Madrid) link opened once — filled (via the Sasha tab's engine_check)",
           terms="ToS bans robots/scrapers and framing without written permission — link only, never a cloud session"),
    Engine("CoverManager", "restaurant", "none", "40 Madrid venues' own links (Sasha 95) — no prefill seen", taps_page=9),
    Engine("TheFork", "restaurant", "none", "TheFork widget install guide — no parameters", taps_page=9,
           terms="terms ban robots, spiders, scrapers and automatic devices"),
    Engine("OpenTable", "restaurant", "none", "help article unreadable; partner programme exists", taps_page=8),
    Engine("Zenchef", "restaurant", "none", "venue pages only; JS SDK openWith({day,pax}) unverified", taps_page=9),
    Engine("Restoo", "restaurant", "none", "venue portal only (Casa Suecia, Madrid)", taps_page=9),
    # ── hotels ──
    Engine("Mews", "hotel", "documented", "docs.mews.com booking-engine-standalone/deeplinks",
           {"checkin": "mewsStart", "checkout": "mewsEnd", "adults": "mewsAdultCount", "children": "mewsChildCount",
            "promo": "mewsVoucherCode"}, taps_after=11, taps_page=15),
    Engine("SynXis", "hotel", "documented", "SynXis Booking Engine Linking Instructions (PDF)",
           {"checkin": "arrive", "checkout": "depart", "adults": "adult", "children": "child", "rooms": "rooms",
            "promo": "promo"}, omit_zero=("children",), taps_after=11, taps_page=15),
    Engine("Cloudbeds", "hotel", "documented", "Cloudbeds Booking Engine Immersive Experience 2.0 (help centre)",
           {"checkin": "checkin", "checkout": "checkout", "adults": "adults", "children": "kids", "promo": "promo"},
           taps_after=11, taps_page=15, verified="the founder, 5 Oct 2026: Fuse Old Town (Hoi An) link opened once — filled (via the Sasha tab's engine_check)"),
    Engine("SiteMinder", "hotel", "seen_in_links", "direct-book / book-directonline links published by hotels",
           {"checkin": "checkInDate", "checkout": "checkOutDate", "adults": "items[0][adults]",
            "children": "items[0][children]"}, fixed=(("items[0][infants]", "0"),), taps_after=11, taps_page=15,
           verified="the founder, 5 Oct 2026: ÊMM Hotel (Hoi An) link opened once — filled (via the Sasha tab's engine_check)"),
    Engine("WebHotelier", "hotel", "documented", "docs.webhotelier.net/integration-site-availability",
           {"checkin": "checkin", "checkout": "checkout", "adults": "adults", "children": "children", "rooms": "rooms"},
           taps_after=11, taps_page=15),
    Engine("Bookassist", "hotel", "documented", "Bookassist booking-platform installation guide",
           {"checkin": "date_in", "checkout": "date_out", "rooms": "rms", "adults": "adults", "children": "children",
            "promo": "promo_code"}, taps_after=11, taps_page=15),
    Engine("Guestcentric", "hotel", "documented+observed",
           "help.guestcentric.com 'custom hotel Booking Engine URL' (startDay yyyy-mm-dd, nrNights, amount, nrAdults, nrChildren); "
           "CR 26 (5 Oct 2026), the engine's OWN search run read-only on book.smallportuguesehotels.com and book.memmoalfama.com "
           "(HyperCommerce, same version): book.php?apikey=… redirects to /search with every parameter kept and opens on the rates, "
           "filled. The 5 Oct 'not filled' was the group's MARKETING page (property-details: no apikey, the engine never sees it)",
           {"checkin": "startDay", "nights": "nrNights", "rooms": "amount", "adults": "nrAdults", "children": "nrChildren"},
           taps_after=11, taps_page=15, entry=lambda page: _guestcentric_entry(page)),
    Engine("Omnibees", "hotel", "seen_in_links", "book.omnibees.com links published for Lisbon hotels",
           {"checkin": "CheckIn", "checkout": "CheckOut", "rooms": "NRooms", "adults": "ad", "children": "ch"},
           date_fmt="%d%m%Y", taps_after=11, taps_page=15, verified="the founder, 5 Oct 2026: Masa Hotel Campo Grande (Lisbon) link opened once — filled (via the Sasha tab's engine_check)"),
    Engine("Simple Booking", "hotel", "seen_in_links", "simplebooking.it ibe2 links published by hotels",
           {"checkin": "in", "checkout": "out", "promo": "coupon"}, taps_after=12, taps_page=15),
    Engine("Little Hotelier", "hotel", "none", "help centre: only promocode and room_type", {"promo": "promocode"},
           taps_after=15, taps_page=15),
    Engine("D-Edge", "hotel", "none", "no public parameters", taps_page=15),
    Engine("Neobookings", "hotel", "none", "no public deep links; vendor advertises an MCP/API for AI agents", taps_page=15),
    Engine("Avirato", "hotel", "none", "PMS link generator, no URL parameters published", taps_page=15),
    # ── spas ──
    Engine("Fresha", "spa", "none", "Link builder preselects a service (venue-made); no date/time", taps_page=8,
           terms="terms ban scraping; robots disallows booking paths"),
    Engine("Treatwell", "spa", "none", "widget only", taps_page=8),
    Engine("Booksy", "spa", "none", "account required", taps_page=8),
)}

#: our test venue (ours): the live hand-over prototype filled every field and left only Book (CR 22, measured)
TEST_VENUE_TAPS = 1


def _guestcentric_entry(page: str) -> Optional[str]:
    """The hotel's own HyperCommerce engine from a link it publishes: book.php?apikey=… (kept: it redirects with every
    parameter) or the SPA's ?gc=… (→ /search). A marketing page (no apikey, no gc) is not the engine → None."""
    u = urlsplit(page)
    q = dict(parse_qsl(u.query, keep_blank_values=True))
    if u.path.endswith("/book.php") and q.get("apikey"):
        return page
    if q.get("gc"):
        keep = [(k, q[k]) for k in ("gc", "l", "channelKey") if q.get(k)]
        return urlunsplit((u.scheme, u.netloc, "/search", urlencode(keep), ""))
    return None


def https(url: str) -> str:
    """A link Sasha sends is never http:// — phones block it as an unsafe connection (CR 22: link 6, 5 Oct 2026)."""
    return "https://" + url[len("http://"):] if (url or "").lower().startswith("http://") else url


def build(engine: str, venue_page: str, **slot) -> Tuple[str, List[str]]:
    """The venue's own engine page with the slot added → (url, the fields carried). Unknown engine or no template: the page
    unchanged, nothing carried. slot: date/time (date/time objects), party, checkin/checkout (dates), nights, adults,
    children, rooms, promo."""
    venue_page = https(venue_page)
    e = LIBRARY.get(engine)
    if not e or not e.params or e.not_filled:      # a link the founder saw NOT fill carries nothing: the page as it is
        return venue_page, []
    if e.entry is not None:
        entry = e.entry(venue_page)
        if entry is None:                          # not the engine's own page (CR 26: a marketing page): carry nothing
            return venue_page, []
        venue_page = entry
    if "nights" in e.params and slot.get("nights") is None and slot.get("checkin") and slot.get("checkout"):
        slot = {**slot, "nights": (slot["checkout"] - slot["checkin"]).days}
    add: List[Tuple[str, str]] = []
    carried: List[str] = []
    for ours, theirs in e.params.items():
        v = slot.get(ours)
        if v is None or (ours in e.omit_zero and v == 0):
            continue
        if isinstance(v, date):
            v = v.strftime(e.date_fmt)
        elif isinstance(v, time):
            v = v.strftime(e.time_fmt)
        add.append((theirs, str(v)))
        carried.append(ours)
    if not add:
        return venue_page, []
    u = urlsplit(venue_page)
    names = {k for k, _ in add} | {k for k, _ in e.fixed}
    keep = [(k, v) for k, v in parse_qsl(u.query, keep_blank_values=True) if k not in names]
    return urlunsplit((u.scheme, u.netloc, u.path, urlencode(keep + add + list(e.fixed)), u.fragment)), carried


def taps_to_book(engine: Optional[str], carried: Optional[List[str]] = None, *, test_venue: bool = False) -> dict:
    """The guest's taps from opening Sasha's link to the venue's confirmation (open + selections + fields + checkboxes + Book).
    → {"taps": n, "how": "measured"|"estimated", "why": …}. Measured only where it was (our test venue's hand-over, or a
    founder-verified recipe); otherwise the library's estimate for that engine, said as one."""
    if test_venue:
        return {"taps": TEST_VENUE_TAPS, "how": "measured", "why": "our test venue: Sasha filled its form, the guest presses Book"}
    e = LIBRARY.get(engine or "")
    if not e:
        return {"taps": None, "how": "unknown", "why": "engine not in the library"}
    full = bool(carried) and set(e.params) <= set(carried)
    n = e.taps_after if full else e.taps_page
    # a founder-verified link FILLS (that is what engine_check asks); the taps after it are still counted from the page
    return {"taps": n, "how": "estimated",
            "why": f"{e.name}: " + (("the link fills the slot (verified)" if e.verified else "the link carries the slot")
                                    if full else "the guest picks the slot on the page")}


def per_engine(rows: List[dict]) -> List[dict]:
    """The ops log's per-engine summary from per-booking rows [{"engine", "taps", "how"}]: count and median taps."""
    from statistics import median
    by: Dict[str, List[int]] = {}
    for r in rows:
        if r.get("taps") is not None:
            by.setdefault(r.get("engine") or "unknown", []).append(int(r["taps"]))
    return [{"engine": k, "bookings": len(v), "median_taps": median(v)} for k, v in sorted(by.items())]
