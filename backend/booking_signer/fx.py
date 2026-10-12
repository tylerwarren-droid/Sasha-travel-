"""Sasha 249 · ONE RATE (docs/sasha/one-truth-spec.md §1.8, §2 row 1.7–1.9) — every conversion into euros, in one place, at ONE
dated rate. Before this, five places each decided their own USD→EUR (world_itinerary, basket.sync_stays, conductor._eur190,
route_costs.usd_eur, and a hard-coded 0.92 in agapi/v0.search_stays), and a flight priced in any other currency was not converted
at all: it fell back to the planner's dollar estimate on the Trip tab (€496 in the chat vs $1,520 on the tab).

    rate(currency)        euros per one unit: EUR 1.0; USD the dated default unless SASHA_USD_EUR sets it; any other currency
                          only when SASHA_<CUR>_EUR sets it (no rate is ever guessed) — else None
    to_eur(amount, cur)   the amount in euros (2 dp), or None when there is no rate
    stamp(cur)            {"currency", "rate", "as_of"} — said beside a converted price, so a converted figure is never unexplained

`configured_only=True` (route_costs, the ops cost report): a rate counts only when it is SET — an unset rate is unknown there,
never the default (Sasha 131: "an unset rate is unknown, never zero")."""
from __future__ import annotations

import os
from typing import Any, Dict, Optional

AS_OF = "2026-10-12"            # the date the default rate below was set (SASHA_FX_AS_OF overrides it with the setting)
DEFAULT: Dict[str, float] = {"USD": 0.92}   # euros per unit — the one dated default (it was 0.92 in all five places)


def _env(currency: str) -> Optional[float]:
    v = os.getenv(f"SASHA_{currency.upper()}_EUR", "").strip()
    try:
        x = float(v) if v else None
    except ValueError:
        return None
    return x if x and x > 0 else None


def rate(currency: Optional[str], configured_only: bool = False) -> Optional[float]:
    """Euros per one unit of `currency`; None when there is no rate (never a guess)."""
    cur = (currency or "").strip().upper()
    if cur == "EUR":
        return 1.0
    if not cur:
        return None
    got = _env(cur)
    if got is not None or configured_only:
        return got
    return DEFAULT.get(cur)


def as_of() -> str:
    return os.getenv("SASHA_FX_AS_OF", "").strip() or AS_OF


def to_eur(amount: Any, currency: Optional[str], configured_only: bool = False) -> Optional[float]:
    """`amount` in `currency` → euros (2 dp); None when the amount isn't a number or there's no rate."""
    try:
        a = float(amount)
    except (TypeError, ValueError):
        return None
    r = rate(currency, configured_only)
    return None if r is None else round(a * r, 2)


def stamp(currency: Optional[str]) -> Dict[str, Any]:
    """What a converted price says about itself: the currency it came in, the rate, the rate's date."""
    return {"currency": (currency or "").upper(), "rate": rate(currency), "as_of": as_of()}


__all__ = ["AS_OF", "DEFAULT", "rate", "as_of", "to_eur", "stamp"]
