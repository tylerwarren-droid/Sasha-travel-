"""Sasha 131 (3) · LOYALTY NUMBERS from the Keep (the vault: You → My accounts, kind "Membership or loyalty number").

A saved number is added to a booking it MATCHES — and only inside that booking's yes: the read-back names it
(vault.crypto.access_line, kind identifier: "I'll use your saved … from your vault."), the number itself is opened only
when the booking is sent, once, and the use is logged (vault_uses, action_kind "loyalty_number"). It goes in WRITTEN
channels only (a form's comments box), never said on a call.

Which programme matches which booking is a fixed list, never a guess: a Marriott number on a Marriott hotel, never on a
restaurant. Today Sasha books restaurants and a spa, so of the three fictional numbers the founder saved only the
test club matches anything (our test venue and our demo spa) — the others wait for flights and hotels.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

#: programme (the vault item's provider, as saved) → (what it applies to, names it matches — lower-case substrings)
PROGRAMS: Dict[str, Tuple[str, Tuple[str, ...]]] = {
    "iberia.com": ("flight", ("iberia",)),
    "marriott.com": ("hotel", ("marriott", "westin", "sheraton", "ritz-carlton", "st. regis", "w hotel", "ac hotel", "renaissance",
                                  "courtyard", "moxy", "aloft", "le méridien", "le meridien", "four points", "edition")),
    "club.kanoe.ai": ("any", ("sasha test venue", "kanoe demo spa")),   # OUR fictional test club
}
#: the vault names a site by its address (vault/api._clean); a programme's name is accepted too
ALIASES = {"iberia plus": "iberia.com", "marriott bonvoy": "marriott.com", "kanoe test club": "club.kanoe.ai"}
NAMES = {"iberia.com": "Iberia Plus", "marriott.com": "Marriott Bonvoy", "club.kanoe.ai": "Kanoe Test Club"}

TOKEN = "⟨your number, added from your vault when it's sent⟩"


def matches(provider: str, venue: str, category: Optional[str] = None) -> bool:
    key = (provider or "").strip().lower()
    p = PROGRAMS.get(ALIASES.get(key, key))
    if not p:
        return False
    kind, names = p
    if kind not in ("any", category or ""):
        return False
    v = (venue or "").lower()
    return any(n in v for n in names)


async def find_for(account: str, venue: str, category: Optional[str] = None) -> Optional[dict]:
    """The one saved, unrevoked loyalty number that matches this booking — or None."""
    from .vault import crypto as VC
    try:
        rows = await VC.STORE.list(account) if VC.STORE else []
    except Exception as e:   # a loyalty number is a nicety: never a reason a booking can't be prepared
        import logging
        logging.getLogger("booking_signer.loyalty").info("[loyalty] vault not read: %s", type(e).__name__)
        return None
    return next((r for r in rows if r.get("kind") == "identifier" and not r.get("revoked_at")
                 and matches(str(r.get("provider") or ""), venue, category)), None)


def comment_with(value: str, provider: str) -> str:
    key = (provider or "").strip().lower()
    line = f"{NAMES.get(ALIASES.get(key, key), provider)}: {TOKEN}"
    return f"{value} · {line}" if value else line


__all__ = ["PROGRAMS", "TOKEN", "matches", "find_for", "comment_with"]
