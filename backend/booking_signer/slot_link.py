"""S-37 · THE SLOT LINK — Sasha prepares the booking; the guest confirms it on the platform with their own press.

No platform terms are accepted by us, nothing is automated on the platform's side, and ⛔ NOTHING HERE SENDS A REQUEST
TO A BOOKING PLATFORM. The link is built from two strings we already hold:

  · the venue's page on its platform — the "Reserve" link Magellan READ on the venue's own website (a `platform` fact's
    `detail.link`). A venue whose site does not link its platform page gets no link; a URL is never guessed.
  · a RECIPE for that platform — which query parameters carry date, time and party — written from URLs the founder
    copied from his own browser, and verified by him once. With no verified recipe the link is the venue's platform
    page as linked, and Sasha says "pick Thursday at 8 there", never "your table is filled in".

⚠ Sasha never knows whether a slot is free: only the platform's page, opened by the guest, shows it. She says so.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, time
from typing import Dict, List, Optional
from urllib.parse import urlencode, urlsplit, urlunsplit, parse_qsl

from .venue_read import platform_of


@dataclass(frozen=True)
class Recipe:
    """How one platform's venue page takes a booking in its URL. ⚠ Data with provenance, never inferred."""

    platform: str
    date_param: str
    time_param: str
    party_param: str
    date_format: str           #: strftime for the date, e.g. "%Y-%m-%d"
    time_format: str           #: strftime for the time, e.g. "%H:%M"
    observed: str              #: whose browser, when, which captures
    verified: Optional[str]    #: who opened a built link and saw the slot filled, and when — None until then


#: ⚠ EMPTY ON PURPOSE. Each entry needs the founder's captures (S-35 §3.2) and his one-time check (S-37 §2). Until a
#: platform has a VERIFIED recipe, its links open the venue's page without the slot, and the words say so.
RECIPES: Dict[str, Recipe] = {}


@dataclass(frozen=True)
class SlotLink:
    platform: str
    url: str
    slot_filled: bool          #: True only with a VERIFIED recipe
    source_label: str          #: where the venue's platform page was read: "their website, lacontra.es"


class LinkRefused(Exception):
    def __init__(self, rule: str, message: str) -> None:
        super().__init__(f"{rule}: {message}")
        self.rule = rule


# ── Sasha 95 · CoverManager: which of its URLs is a venue's BOOKING page ────────────────────────────────────────
#
# From the links 40 Madrid venues publish on their own sites (2 Oct 2026; covermanager.com itself never requested):
#   booking:   /reservation/module_restaurant/<slug>/<language>  ·  /reserve/module_restaurant/<slug>/<language>
#              /go/<slug>/<xx>   (a short link the venue publishes)
#   NOT booking: /js/… (the widget's script) · /eco/buy_products/… (gift vouchers) · /marketplace/… · /reserve/gtmcrossdomain/…
# Query strings seen were tracking (fbclid, source, utm_*) or widget display (day=1…7, timefix, template): never a booking
# pre-fill — those are dropped. No date/party pre-fill was seen anywhere; that needs the founder's capture (RECIPES).

_CM_MODULE = re.compile(r"^/(?:reservation|reserve)/module_restaurant/([A-Za-z0-9._-]+)(?:/([a-z]+))?/?$")
_CM_GO = re.compile(r"^/go/([A-Za-z0-9._-]+)/([a-z]{2})/?$")


def covermanager_page(url: str) -> Optional[str]:
    """The canonical booking page for a CoverManager URL a venue published, or None if it isn't a booking page."""
    u = urlsplit(url.replace("&quot;", "").replace("&quot", "").replace("&amp;", "&"))
    if not (u.hostname or "").endswith("covermanager.com"):
        return None
    m = _CM_MODULE.match(u.path)
    if m:
        return f"https://www.covermanager.com/reservation/module_restaurant/{m.group(1)}/{m.group(2) or 'spanish'}"
    m = _CM_GO.match(u.path)
    if m:
        return f"https://www.covermanager.com/go/{m.group(1)}/{m.group(2)}"
    return None


def _slug(page: str) -> str:
    return urlsplit(page).path.split("/")[-2].lower()


def _candidates(f: dict) -> List[tuple]:
    """(url, how) for every link (an <a>) and embed (an iframe/script) the read kept for this platform fact."""
    d = f.get("detail") or {}
    out = [(u, "link") for u in ([d.get("link")] + list(d.get("links") or [])) if isinstance(u, str)]
    out += [(u, "embed") for u in ([d.get("embed")] + list(d.get("embeds") or [])) if isinstance(u, str)]
    return out


def platform_page(read: dict) -> Optional[tuple]:
    """(platform, page URL, source label) — the venue's booking page on its platform, from what its own site links.
    CoverManager: only a booking page (never its gift shop or script), cleaned of tracking; a linked page before an
    embedded one; several DIFFERENT restaurants linked (a group's site) and none chosen → None, never a guess.
    Other platforms: a link on the platform's own host, https, as before."""
    for f in read.get("facts") or []:
        if f.get("kind") != "platform":
            continue
        if f["value"] == "CoverManager":
            pages = [(covermanager_page(u), how) for u, how in _candidates(f)]
            pages = [(p, how) for p, how in pages if p]
            for how in ("link", "embed"):
                slugs = {_slug(p) for p, h in pages if h == how}
                if len(slugs) == 1:
                    return f["value"], next(p for p, h in pages if h == how), f["source_label"]
                if len(slugs) > 1:
                    return None    # a group's restaurants: which one is THIS venue is the guest's to say
            continue
        for link, how in _candidates(f):
            if how != "link":
                continue
            u = urlsplit(link)
            if u.scheme == "https" and u.hostname and platform_of(link) == f["value"]:
                return f["value"], link, f["source_label"]
    return None


def build(read: dict, on: date, at: time, party: int, recipes: Optional[Dict[str, Recipe]] = None) -> SlotLink:
    found = platform_page(read)
    if found is None:
        plats = sorted({f["value"] for f in read.get("facts") or [] if f.get("kind") == "platform"})
        if plats:
            raise LinkRefused("platform_page_not_linked",
                              f"they book through {', '.join(plats)}, but their site doesn't link their page there")
        raise LinkRefused("no_platform", "no booking platform was read for this venue")
    platform, page, label = found
    recipe = (recipes if recipes is not None else RECIPES).get(platform)
    if recipe is None or not recipe.verified:
        return SlotLink(platform, page, False, label)
    u = urlsplit(page)
    keep = [(k, v) for k, v in parse_qsl(u.query, keep_blank_values=True)
            if k not in (recipe.date_param, recipe.time_param, recipe.party_param)]
    q = urlencode(keep + [(recipe.date_param, on.strftime(recipe.date_format)),
                          (recipe.time_param, at.strftime(recipe.time_format)),
                          (recipe.party_param, str(party))])
    return SlotLink(platform, urlunsplit((u.scheme, u.netloc, u.path, q, "")), True, label)


def _when(on: date, at: time) -> str:
    h = at.hour % 12 or 12
    return f"{on.strftime('%A')} {on.day} {on.strftime('%B')} at {h}{':' + format(at.minute, '02d') if at.minute else ''} {'pm' if at.hour >= 12 else 'am'}"


def read_back(venue: str, link: SlotLink, on: date, at: time, party: int, forward_to: Optional[str]) -> list:
    """What she says. Always: who books (the guest), who confirms (the platform, to the guest), nothing reserved yet."""
    when = _when(on, at)
    if link.slot_filled:
        lines = [f"{venue} takes bookings through {link.platform}. I can't book there for you, but here's their {link.platform} page "
                 f"with {when}, for {party}, already filled in.",
                 f"If it's free, press Reserve and it's booked in your name — {link.platform} sends the confirmation to you. "
                 f"If that time isn't free, their page will show you what is."]
    else:
        lines = [f"{venue} takes bookings only through {link.platform}, so you make the final press — I can't press their button for you.",
                 f"Here's their {link.platform} page: pick {when}, for {party}, there. It's booked in your name, and "
                 f"{link.platform} sends the confirmation to you."]
    lines.append(f"I found their page on {link.source_label}. Nothing is reserved until you press their button.")
    if forward_to:
        lines.append(f"When the confirmation arrives, forward it to {forward_to} and I'll put it in your trip.")
    else:
        lines.append("When you've booked, tell me and I'll note it in your trip.")
    return lines
