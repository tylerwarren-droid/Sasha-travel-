"""S-68 step 6 · RANKING the 20 a search returns — every chip's order computed once, so a re-sort is no new search.

The rules (docs/sasha/S-68-discovery-ranking.md §2):
  · best rated ranks ONLY among listings with ≥ 20 Google reviews; fewer → after them, marked "too few to rank";
    no rating → after those. Never "the best": it is Google's rating, said as such;
  · a time the guest STATED is a filter shown as groups, never a silent removal: open then · hours not listed ·
    closed then — and the count says "3 of 11 open at 17:00";
  · a temporarily closed listing is greyed with that word; a permanently closed one is never a card;
  · each chip sorts the same 20; ties go to the higher rating (≥ 20 reviews), then the closer place, then Google's order;
  · no blended score, no number of ours: a "Sasha score" would be false precision.
The explainer line says the factors in play, as the Maps policies recommend for search in Europe.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

MIN_REVIEWS = 20
CHIPS = {"rated": "★ Best rated", "closest": "📍 Closest", "price": "€ Price", "open": "🕑 Open then"}


def rating_words(c: Dict[str, Any]) -> str:
    """"★ 4.8 (312 Google reviews)" · "★ 5.0 (6 Google reviews — too few to rank)" · "no rating"."""
    r, n = c.get("rating"), c.get("rating_count")
    if r is None:
        return "no rating"
    reviews = f"{n} Google review{'s' if n != 1 else ''}" if n is not None else "Google reviews, count not given"
    return f"★ {r:.1f} ({reviews}{' — too few to rank' if (n or 0) < MIN_REVIEWS else ''})"


def price_words(c: Dict[str, Any]) -> str:
    p = c.get("price_level")
    return "price level not listed" if p is None else ("free" if p == 0 else "€" * p)


def _rated_key(c: Dict[str, Any]):
    r, n = c.get("rating"), c.get("rating_count") or 0
    tier = 0 if r is not None and n >= MIN_REVIEWS else 1 if r is not None else 2
    return (tier, -(r or 0))


def _tie(c: Dict[str, Any]):
    d = c.get("distance_m")
    return (_rated_key(c), d is None, d or 0, c["_i"])


def _group(c: Dict[str, Any], timed: bool) -> str:
    if c.get("status") == "CLOSED_PERMANENTLY":
        return "gone"
    if c.get("status") == "CLOSED_TEMPORARILY":
        return "closed_temporarily"
    if not timed:
        return "main"
    oa = c.get("open_at") or {}
    return "main" if oa.get("open") is True else "closed_then" if oa.get("open") is False else "hours_unknown"


def rank(candidates: List[Dict[str, Any]], *, open_at: Optional[str], near_found: bool) -> dict:
    """{default, chips, orders: {chip: [place_id, …]}, groups: {place_id: group}, count, explainers}."""
    cs = [{**c, "_i": i} for i, c in enumerate(candidates)]
    timed = open_at is not None
    groups = {c["place_id"]: _group(c, timed) for c in cs}
    keys = {
        "rated": _tie,
        "price": lambda c: (c.get("price_level") is None, c.get("price_level") or 0, _tie(c)),
        "open": _tie,   # within "open then", best rated; the groups do the filtering
    }
    if near_found:
        keys["closest"] = lambda c: (c.get("distance_m") is None, c.get("distance_m") or 0, _rated_key(c), c["_i"])
    order_of_groups = ("main", "hours_unknown", "closed_then", "closed_temporarily")
    orders = {}
    for chip, key in keys.items():
        if chip == "open" and not timed:
            continue
        orders[chip] = [c["place_id"] for g in order_of_groups for c in sorted((x for x in cs if groups[x["place_id"]] == g), key=key)]
    hhmm = open_at[11:16] if timed else None
    live = [c for c in cs if groups[c["place_id"]] != "gone"]
    main = sum(1 for c in live if groups[c["place_id"]] == "main")
    count = (f"{main} of {len(live)} open at {hhmm} by their listed hours" if timed
             else f"{len(live)} place{'s' if len(live) != 1 else ''} found")
    tie = "ties go to the higher Google rating (20+ reviews), then the closer place" if near_found else \
          "ties go to the higher Google rating (20+ reviews)"
    explain = {
        "rated": f"Ordered by Google rating, counted only with {MIN_REVIEWS}+ reviews (fewer reviews come after); "
                 + ("ties go to the closer place." if near_found else "ties keep Google’s own order."),
        "closest": "Ordered by straight-line distance from the place you named; ties go to the higher Google rating (20+ reviews).",
        "price": f"Ordered by Google’s price level, cheapest first; “price level not listed” comes last; {tie}.",
        "open": f"Only places open at {hhmm} by their listed hours come first, best rated first; hours not listed, then closed, after.",
    }
    if timed:
        for chip in ("rated", "closest", "price"):
            explain[chip] += f" Places not open at {hhmm} by their listed hours come after."
    return {"default": "rated", "chips": {k: CHIPS[k] for k in CHIPS if k in orders}, "orders": orders,
            "groups": {k: v for k, v in groups.items() if v != "gone"}, "count": count,
            "explainers": {k: v for k, v in explain.items() if k in orders}}


__all__ = ["rank", "rating_words", "price_words", "MIN_REVIEWS", "CHIPS"]
