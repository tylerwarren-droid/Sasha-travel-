"""S-54 · THE REFUSAL CHECK — a venue that told Sasha to stop is never contacted by Sasha again, on any channel.

S-49 §4–§5, the smallest part first. Every SASHA-initiated send asks `check_send` before it acts:
  · ⛔ a venue whose most recent opt-in record is a WITHDRAWAL is refused on EVERY channel ("any stop on any channel
    ends every channel") — until it opts in again, which is a new row with new evidence;
  · ⛔ WhatsApp Mode B and form submission (`whatsapp`, `web_submit`) also need an ACTIVE opt-in whose scope is the
    same number or URL that was read — a number that changed does not inherit the consent;
  · phone and email need no opt-in (S-49 §4, "as today"), only the absence of a withdrawal.

Not Sasha-initiated, so not checked here: the slot link and WhatsApp Mode A (the guest presses the button themselves).

It is checked twice: when the read-back is prepared (so a withdrawn venue is never offered with a "Yes" that cannot
act), and again at the send (a withdrawal can land in between).

The record is `venue_optins` (sql/008), append-only in the database itself.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import urlsplit

#: channels that need a live opt-in before Sasha may use them; the rest need only the absence of a withdrawal
NEEDS_OPTIN = {"whatsapp", "web_submit"}
#: every channel Sasha may initiate on
SASHA_CHANNELS = {"phone", "email", "whatsapp", "web_submit"}


def host_id(url: str) -> Optional[str]:
    host = (urlsplit(url if "//" in url else f"https://{url}").hostname or "").lower().removeprefix("www.")
    return f"host:{host}" if host else None


def name_id(name: str, country: Optional[str]) -> str:
    folded = re.sub(r"\s+", " ", str(name or "")).strip().casefold()
    return f"name:{folded}|{(country or '').upper()}"


def venue_ids_of(read: Dict[str, Any]) -> List[str]:
    """EVERY name the venue goes by: its Google place id, each host its own site was read from, and its name and country.
    S-55 · a venue that opts in on the page is known by its website (or its name) — never by a place id — so the check
    must match a read on any of them, or a withdrawal made on the page would not reach a read keyed by its listing."""
    ids: List[str] = []
    listing = read.get("listing") or {}
    if listing.get("place_id"):
        ids.append(f"places:{listing['place_id']}")
    for f in read.get("facts") or []:
        if f.get("source_kind") == "site" and f.get("source_url"):
            h = host_id(f["source_url"])
            if h and h not in ids:
                ids.append(h)
    ids.append(name_id(read.get("name"), read.get("country")))
    return ids


def venue_id_of(read: Dict[str, Any]) -> str:
    """The venue's first name (place id, else its own site's host, else its name and country)."""
    return venue_ids_of(read)[0]


@dataclass(frozen=True)
class Refusal:
    rule: str
    message: str


def check_send(rows: List[Dict[str, Any]], channel: str, scope: Optional[str] = None) -> Optional[Refusal]:
    """`rows` are ALL of the venue's opt-in records, under every id it goes by. None = Sasha may send; else why not."""
    if channel not in SASHA_CHANNELS:
        return Refusal("channel_unknown", f"{channel!r} is not a channel Sasha sends on")
    ordered = sorted(rows, key=lambda r: (r["recorded_at"], r["id"]))
    if ordered and ordered[-1]["status"] == "withdrawn":
        w = ordered[-1]
        when = w["withdrawn_at"].date().isoformat() if isinstance(w.get("withdrawn_at"), datetime) else str(w.get("withdrawn_at"))
        return Refusal("venue_opted_out", f"This venue asked Sasha to stop contacting them ({w['channel']}, {when}, "
                                          f"\"{w.get('withdrawn_how') or 'stop'}\"). Sasha won't contact them on any channel; "
                                          "you can still contact them yourself.")
    if channel in NEEDS_OPTIN:
        latest: Dict[tuple, Dict[str, Any]] = {}
        for r in ordered:
            latest[(r["channel"], r["scope"])] = r
        live = latest.get((channel, scope))
        if not live or live["status"] != "active":
            return Refusal("no_active_optin", f"This venue has not opted in to Sasha using {channel} at {scope or 'this address'}, "
                                              "so she may not initiate it. A published number or form is not consent.")
    return None


class MemoryOptinStore:
    def __init__(self) -> None:
        self.rows: List[Dict[str, Any]] = []

    async def add(self, row: Dict[str, Any]) -> None:   # tests only; production rows arrive through the opt-in flows
        self.rows.append({"id": len(self.rows) + 1, **row})

    async def rows_for(self, venue_ids: List[str]) -> List[Dict[str, Any]]:
        return [dict(r) for r in self.rows if r["venue_id"] in venue_ids]


class PostgresOptinStore:
    def __init__(self, base) -> None:
        self._base = base

    async def rows_for(self, venue_ids: List[str]) -> List[Dict[str, Any]]:
        from .store import StorageUnavailable, _row
        try:
            rows = await self._base._run(lambda c: c.fetch(
                "select id, venue_id, channel, scope, status, recorded_at, withdrawn_at, withdrawn_how "
                "from venue_optins where venue_id = any($1::text[])", list(venue_ids)))
        except StorageUnavailable as e:
            raise e.rehint("008_venue_optins.sql") from None
        return [_row(r) for r in rows]


OPTIN_STORE: Any = None   # set by routes.py


async def refusal_for(venue_ids: Optional[List[str]], channel: str, scope: Optional[str] = None) -> Optional[Refusal]:
    """The check, against the store. ⚠ No venue ids (the test line) is checked as nothing withdrawn — the record it
    would need does not exist for it."""
    if not venue_ids or OPTIN_STORE is None:
        return None
    return check_send(await OPTIN_STORE.rows_for(list(venue_ids)), channel, scope)
