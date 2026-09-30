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

from dataclasses import dataclass
from datetime import date, time
from typing import Dict, Optional
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


def platform_page(read: dict) -> Optional[tuple]:
    """(platform, page URL, source label) from a READ platform fact whose link is on that platform's own host, https."""
    for f in read.get("facts") or []:
        if f.get("kind") != "platform":
            continue
        link = (f.get("detail") or {}).get("link")
        if not isinstance(link, str):
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
        lines = [f"{venue} takes bookings through {link.platform}. I can't book there for you, but here's their {link.platform} page.",
                 f"Pick {when}, for {party}, there — it's booked in your name, and {link.platform} sends the confirmation to you."]
    lines.append(f"I found their page on {link.source_label}. Nothing is reserved until you press their button.")
    if forward_to:
        lines.append(f"When the confirmation arrives, forward it to {forward_to} and I'll put it in your trip.")
    else:
        lines.append("When you've booked, tell me and I'll note it in your trip.")
    return lines
