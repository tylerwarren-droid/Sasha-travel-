"""CR 75 step 6 · WHEN SASHA SPEAKS UP (EU 216 §6): one line + a card, ONLY when it saves money or prevents a mistake; at most one per event;
each moment can be turned off.

  rental_booked     a rental is booked (or its confirmation forwarded) → which card to pay with + decline / keep / optional — said only when a
                    card's quoted terms cover it (decline saves money) or need a check before declining (prevents a mistake); silent otherwise
  pickup_tomorrow   the day before pickup → the counter card + the documents to bring + the claims line — said when there's a counter card to give
  which_card        on demand → the ranked cards (cards.which)
  rental_returned   the final charge differs from the quote → the line-by-line difference + [Draft a dispute]; silent when they match
Every line rests on quotes (the counter card's, the ranking's); the moment's own words are fixed templates, never generated."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

MOMENTS = ("rental_booked", "pickup_tomorrow", "which_card", "rental_returned")
TOLERANCE_MINOR = 50          # a difference under 0.50 isn't worth a word


def _money(minor: int, cur: str) -> str:
    return f"{cur} {minor / 100:,.2f}"


def rental_line(counter: Dict[str, Any], where: str, company: str) -> Optional[Dict[str, Any]]:
    c = counter
    if c["counter"]["decline"]:
        return {"line": f"Pay this rental with your {c['card']}: its terms cover damage and theft{(' in ' + where) if where else ''} if you decline "
                        f"{company}'s CDW. Here's what to decline, keep and consider.", "why": "saves_money"}
    if c["counter"]["check"] and c.get("card"):
        return {"line": f"Before you decline {company}'s cover: your {c['card']}'s terms need one check first. Here's the counter card.",
                "why": "prevents_mistake"}
    return None


def pickup_line(counter: Dict[str, Any], when: str, place: str) -> Optional[Dict[str, Any]]:
    c = counter
    if not (c["counter"]["decline"] or c["counter"]["check"] or c["bring"] or c["report"]):
        return None
    head = ", ".join(x for x in (f"Tomorrow {when}".strip(), place) if x)
    return {"line": f"{head}: here's your counter card — what to decline, keep and bring, and the claims line.", "why": "prevents_mistake"}


def returned_diff(quoted: List[dict], final: List[dict], currency: str) -> Optional[Dict[str, Any]]:
    """quoted / final: [{label, amount_minor}] → the line-by-line difference, or None when they match."""
    q = {x["label"].strip().lower(): x for x in quoted}
    f = {x["label"].strip().lower(): x for x in final}
    rows = []
    for k in list(dict.fromkeys(list(q) + list(f))):
        a, b = (q.get(k) or {}).get("amount_minor", 0), (f.get(k) or {}).get("amount_minor", 0)
        rows.append({"label": (f.get(k) or q.get(k))["label"], "quoted_minor": a, "charged_minor": b, "difference_minor": b - a})
    tq, tf = sum(x["amount_minor"] for x in quoted), sum(x["amount_minor"] for x in final)
    if abs(tf - tq) < TOLERANCE_MINOR:
        return None
    extra = [r["label"] for r in rows if r["difference_minor"] >= TOLERANCE_MINOR]
    more = tf > tq
    line = (f"The final charge is {_money(abs(tf - tq), currency)} {'more' if more else 'less'} than the quote"
            + (f" ({' + '.join(extra)})" if extra and more else "") + "." + (" Want me to draft a dispute?" if more else ""))
    return {"line": line, "why": "saves_money" if more else "information", "rows": rows, "quoted_total_minor": tq, "charged_total_minor": tf,
            "currency": currency, "can_dispute": more}
