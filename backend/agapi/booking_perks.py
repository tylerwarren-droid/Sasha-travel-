"""Sasha 301 · PERKS — his own cards' perks and loyalty numbers that apply to a booking, from his Keep (masked), each said as
"as you told me" (KANOE B-Q3: never an entitlement or a guarantee). Nothing matched is nothing said.

Sasha 424 · the venue-terms half of Sasha 301 is DELETED: a booking's terms are AgAPI's facts
(facts.answer) or they are not said. Perks are not terms of a booking — they are what he told her about his own cards.
"""
from __future__ import annotations

from typing import Any, Dict, List

# ── PERKS: his Keep, matched to the booking by a fixed list (never a guess) ──────────────────────────────────────────────────

CATEGORY = {"dinner": "restaurant", "restaurant": "restaurant", "spa": "spa", "hotel": "hotel", "flight": "flight", "car": "car"}


def _brand_names(where: str) -> List[str]:
    """A chain he named ("Marriott") → the names its programme covers (the fixed list), else the words themselves."""
    from booking_signer import loyalty as LY
    w = where.strip().lower()
    names = [w] if w else []
    for key, (_, covered) in LY.PROGRAMS.items():
        if w and (w in key or w in LY.NAMES.get(key, "").lower() or w in covered or LY.ALIASES.get(w) == key):
            names += list(covered)
    return names


def perks_for(kind: str, title: str, wallet: List[dict]) -> List[Dict[str, Any]]:
    """The loyalty numbers and card perks from his Keep that apply to this booking → [{kind, item_id, line}]. Masks only."""
    from booking_signer import loyalty as LY
    cat = CATEGORY.get(kind or "", kind or "")
    name = (title or "").lower()
    out: List[Dict[str, Any]] = []
    for w in wallet or []:
        if w.get("type") == "loyalty" and w.get("program") and LY.matches(w["program"], title or "", cat):
            tail = str(w.get("masked") or "").rsplit(" ", 1)[-1]
            out.append({"kind": "loyalty", "item_id": w["item_id"],
                        "line": f"Use your {w['program']} number" + (f" ({tail})." if tail.startswith("•") else ".")})
        elif w.get("type") == "my_card" and w.get("perk") and w.get("perk_for") in (cat, "any"):
            where = str(w.get("perk_where") or "")
            if where and not any(n and n in name for n in _brand_names(where)):
                continue
            out.append({"kind": "card", "item_id": w["item_id"],
                        "line": f"Your {w['name']} (••••{w['last4']}) includes {w['perk']} — as you told me."})
    return out


__all__ = ["perks_for", "CATEGORY"]
