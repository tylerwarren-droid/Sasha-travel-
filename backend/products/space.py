"""Sasha 249 · ONE SPACE (EU 245 step 9, one-truth-spec row 1.4, T11) — which space an account is in: Sasha (travel), CampusMe,
RelocateMe or EspañaMe. Before this, five places decided it (the WhatsApp product state, me3, switching, products.web's webstate, the
web tab's mode) under three names for EspañaMe ("espana", "health", "españa"), and sasha.turn (/next, /s2, WhatsApp's one brain) did
not know it at all.

  current_space(account)            → "sasha" | "campus" | "relocation" | "espana" — the one answer, for every surface
  set_space(account, space, cause)  → the space now (old names accepted: see ALIASES); `cause` says who moved it ("whatsapp", "web",
                                      "s2", "next", …)

ONE NAME PER SPACE: "espana" for EspañaMe. The products keep their own internal keys (product_cases.product = "health", the WhatsApp
word "españa", the web's OPEN map) — `engine_key()` translates; every old name is still accepted here (ALIASES).

Stored per account in s2_memory (kind "space"; s2_memory's jsonb row — no migration). With no table (tests, a store that's down) this
process keeps it (_SPACE). The surfaces' own engines still run their product turns (WhatsApp's keywords "campus" / "relocate" /
"españa" and "sasha" to return work exactly as before — Tyler's rule, Sasha 246); after each turn they write the space they ended in
here, and sasha.turn reads it at the start of its turn and passes it in its context.
"""
from __future__ import annotations

import logging
import re
import time
from typing import Dict, Optional

log = logging.getLogger("products.space")

SPACES = ("sasha", "campus", "relocation", "espana")
NAME = {"sasha": "Sasha (travel)", "campus": "CampusMe", "relocation": "RelocateMe", "espana": "EspañaMe"}
#: every name a space has had anywhere (the products' keys, me3's modes, the WhatsApp words, the web tab's modes) → the one name
ALIASES = {"sasha": "sasha", "travel": "sasha", "trip": "sasha", "diligence": "sasha", "": "sasha",
           "campus": "campus", "campusme": "campus",
           "relocation": "relocation", "relocate": "relocation", "relocateme": "relocation", "move": "relocation",
           "espana": "espana", "españa": "espana", "health": "espana", "espaname": "espana", "españame": "espana"}
#: the one name → the products' own internal key (product_cases.product, the WhatsApp state's pending.product)
ENGINE = {"campus": "campus", "relocation": "relocation", "espana": "health"}
_SPACE: Dict[str, dict] = {}   # account → {space, cause, at} — this process's copy (the memory when there's no table)


def normalize(space: Optional[str]) -> str:
    """Any name a space has had → the one name ("sasha" for anything unknown)."""
    k = re.sub(r"\s+", "", str(space or "").strip().lower())
    return ALIASES.get(k, "sasha")


def engine_key(space: Optional[str]) -> Optional[str]:
    """The products' internal key for a space (None for Sasha)."""
    return ENGINE.get(normalize(space))


async def current_space(account: Optional[str]) -> str:
    """The space this account is in now ("sasha" when nothing was ever set)."""
    return (await current(account)).get("space") or "sasha"


async def current(account: Optional[str]) -> dict:
    """{space, cause, at} — this process's copy, else the one kept in s2_memory (after a restart)."""
    if not account:
        return {"space": "sasha"}
    if account in _SPACE:
        return dict(_SPACE[account])
    try:
        from agapi import s2_memory as M
        kept = await M.kind(account, "space")
    except Exception as e:
        log.info("[space] not read: %s", type(e).__name__)
        kept = None
    if isinstance(kept, dict) and kept.get("space"):
        _SPACE[account] = {**kept, "space": normalize(kept["space"])}
        return dict(_SPACE[account])
    return {"space": "sasha"}


async def set_space(account: Optional[str], space: Optional[str], cause: str) -> str:
    """Move the account to a space (any old name accepted). Kept in s2_memory, awaited. → the space now."""
    s = normalize(space)
    if not account:
        return s
    now = await current(account)
    if now.get("space") == s and account in _SPACE:
        return s   # unchanged: nothing written
    rec = {"space": s, "cause": str(cause or "")[:40], "at": time.time()}
    _SPACE[account] = rec
    try:
        from agapi import s2_memory as M
        await M.put_kind(account, "space", rec)
    except Exception as e:
        log.warning("[space] not kept: %s", type(e).__name__)
    return s


def from_pending(pending: Optional[dict]) -> str:
    """A product engine's state (WhatsApp's guest_wa_state / the web's webstate `pending`) → the space it is in."""
    p = pending or {}
    return normalize(p.get("product")) if p.get("kind") == "product" else "sasha"


_RETURN = re.compile(r"^\s*(?:(?:switch|go|get|take me)\s+(?:me\s+)?(?:back\s+)?to\s+|back\s+to\s+)?sasha\s*[.!]?\s*$", re.I)


def asked(message: str) -> Optional[str]:
    """A message that names a space to go to ("switch to RelocateMe", "back to the campus tour", "sasha") → that space, else None.
    The same words me3 and the WhatsApp line already understand; nothing new is recognised."""
    from booking_signer import me3
    m = me3.asked(message or "") or me3.back(message or "")
    if m:
        return normalize(m)
    return "sasha" if _RETURN.match(message or "") else None


def context_line(rec: dict) -> str:
    """What sasha.turn tells the model about the space (nothing when they're in Sasha)."""
    s = normalize(rec.get("space"))
    if s == "sasha":
        return ""
    return (f"\n\nTheir space now: {NAME[s]} (the space they chose). {NAME[s]}'s own steps run in its own tab on the web and by its "
            f"word on WhatsApp; here, help with whatever they ask. If they want travel again, saying “sasha” brings them back.")


__all__ = ["SPACES", "NAME", "ALIASES", "normalize", "engine_key", "current_space", "current", "set_space", "from_pending", "asked",
           "context_line"]
