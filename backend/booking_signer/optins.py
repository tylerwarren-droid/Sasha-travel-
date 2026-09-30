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


def venue_id_of(read: Dict[str, Any]) -> str:
    """The venue as the ladder knows it: its Google place id, else its own site's host, else its name and country."""
    listing = read.get("listing") or {}
    if listing.get("place_id"):
        return f"places:{listing['place_id']}"
    for f in read.get("facts") or []:
        if f.get("source_kind") == "site" and f.get("source_url"):
            host = (urlsplit(f["source_url"]).hostname or "").removeprefix("www.")
            if host:
                return f"host:{host}"
    name = re.sub(r"\s+", " ", str(read.get("name") or "")).strip().casefold()
    return f"name:{name}|{(read.get('country') or '').upper()}"


@dataclass(frozen=True)
class Refusal:
    rule: str
    message: str


def check_send(rows: List[Dict[str, Any]], channel: str, scope: Optional[str] = None) -> Optional[Refusal]:
    """`rows` are ALL of the venue's opt-in records. None = Sasha may send; else why she may not."""
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

    async def rows_for(self, venue_id: str) -> List[Dict[str, Any]]:
        return [dict(r) for r in self.rows if r["venue_id"] == venue_id]


class PostgresOptinStore:
    def __init__(self, base) -> None:
        self._base = base

    async def rows_for(self, venue_id: str) -> List[Dict[str, Any]]:
        from .store import StorageUnavailable, _row
        try:
            rows = await self._base._run(lambda c: c.fetch(
                "select id, venue_id, channel, scope, status, recorded_at, withdrawn_at, withdrawn_how "
                "from venue_optins where venue_id = $1", venue_id))
        except StorageUnavailable as e:
            raise e.rehint("008_venue_optins.sql") from None
        return [_row(r) for r in rows]


OPTIN_STORE: Any = None   # set by routes.py


async def refusal_for(venue_id: Optional[str], channel: str, scope: Optional[str] = None) -> Optional[Refusal]:
    """The check, against the store. ⚠ No venue id (a call prepared before S-54) is checked as nothing withdrawn — the
    record it would need does not exist for it."""
    if not venue_id or OPTIN_STORE is None:
        return None
    return check_send(await OPTIN_STORE.rows_for(venue_id), channel, scope)
