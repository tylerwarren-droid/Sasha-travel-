"""Sasha 179 · AUTOMATIC SWITCHING, quick and obvious.

(1) Name another journey or place ("my Vietnam trip", "flights to Hanoi", "a spa in Paris") → Sasha switches to it and says ONE
    line, "↪ Switching to your Vietnam trip.", with a "Back to <previous>" button.
(2) Only when it's genuinely ambiguous ("book my flights" while a relocation is open AND a Sasha trip exists) → ONE question,
    two buttons: "Vietnam trip" / "Move to Madrid".
(3) The current mode is a small label on every reply ("_Now: ✈️ Vietnam, Nov_"); a product mode exits after 30 min idle.

guest_wa_state holds only four columns, so the journey mode is read back from the label on Sasha's last reply in the history;
a product's mode is its open `pending`.
"""
from __future__ import annotations

import re
import uuid
from datetime import timedelta
from typing import List, Optional, Tuple

PRODUCT_IDLE = timedelta(minutes=30)
PRODUCT_LABEL = {"relocation": "🏠 Move to Madrid", "campus": "🎓 CampusMe", "health": "🇪🇸 EspañaMe", "trip": "✈️ Trip planning"}
_LABEL = re.compile(r"^_Now: (?P<l>[^_\n]+)_\n?")
_TO = re.compile(r"\b(?:flights?|fly(?:ing)?|hotels?|vuelos?)\b[^.?!]*?\bto\s+(?P<d>[A-ZÁÉÍÓÚ][\wáéíóúñ'-]*(?:\s+[A-Z][\wáéíóúñ'-]*)?)")
_IN = re.compile(r"\b(?:in|en)\s+(?P<d>[A-ZÁÉÍÓÚ][\wáéíóúñ'-]*(?:\s+[A-Z][\wáéíóúñ'-]*)?)")
_MY = re.compile(r"\bmy (?P<t>[\w ,]+?) (?:trip|journey|itinerary|plan)\b", re.I)
_AMBIG = re.compile(r"^\s*(?:please\s+)?(?:book|find|get|sort(?: out)?)\s+(?:me\s+)?(?:my|the)\s+(?:flights?|hotels?|trip)\s*[.!?]*\s*$", re.I)


def on(account: Optional[str]) -> bool:
    """Tonight: the founder's account (the demo); everyone with SASHA_SWITCHING=all."""
    import os
    from .guest_accounts import founder
    return bool(account) and (os.getenv("SASHA_SWITCHING", "") == "all" or founder(account))


def label_of(text: str) -> Optional[str]:
    m = _LABEL.match(text or "")
    return m["l"].strip() if m else None


def strip_label(text: str) -> str:
    return _LABEL.sub("", text or "", count=1)


def before(st: dict, now) -> Optional[dict]:
    """The mode this turn starts in: an open product (unless idle 30 min), else the label on Sasha's last reply."""
    pend = st.get("pending") or {}
    if pend.get("kind") == "product" and pend.get("product"):
        return {"k": "p", "p": pend["product"], "label": PRODUCT_LABEL.get(pend["product"], pend["product"])}
    for h in reversed(st.get("history") or []):
        if h.get("role") == "assistant":
            lb = label_of(str(h.get("content") or ""))
            return {"k": "j", "label": lb} if lb else None
    return None


async def _dated_first(account: str) -> List[dict]:
    """The account's plans, the dated ones first (an undated "Vietnam" stub never wins over "Vietnam, Nov")."""
    from . import plan_store as PS
    ps = await PS.plans(account)
    return [p for p in ps if p.get("start")] + [p for p in ps if not p.get("start")]


async def _journey_for_city(account: str, city: str, at: Optional[str]) -> str:
    """The tab a place belongs to: a trip whose cities hold it, else its own 📍 tab (home is home)."""
    from . import journeys as JN, plan_store as PS
    c = JN._fold(city.split(",")[0].strip())
    for p in await _dated_first(account):
        if any(JN._fold(str(x)) == c for x in (p.get("cities") or [])) or c in JN._fold(p.get("title") or ""):
            return JN.badged(JN.product_of(p["title"]), JN.label(p))
    home = JN.home_label().replace(" (home)", "")
    if c in (JN._fold(home), "madrid"):
        return JN.badged("sasha", JN.home_label())
    return f"📍 {city.split(',')[0].strip()}"


async def after(account: str, body: str, st: dict) -> Optional[dict]:
    """The mode the turn ended in, or None (nothing named: the mode stays)."""
    pend = st.get("pending") or {}
    if pend.get("kind") == "product" and pend.get("product"):
        return {"k": "p", "p": pend["product"], "label": PRODUCT_LABEL.get(pend["product"], pend["product"])}
    from . import plan_store as PS, journeys as JN
    m = _MY.search(body or "")
    if m and not re.match(r"(?i)move|campus", m["t"]):
        want = JN._fold(m["t"].strip())
        for p in await _dated_first(account):
            if want and (want in JN._fold(p.get("title") or "") or any(want == JN._fold(str(c)) for c in p.get("cities") or [])):
                return {"k": "j", "label": JN.badged(JN.product_of(p.get("title") or ""), JN.label(p))}
    f = pend.get("find") or {}
    city = f.get("where")
    if not city:
        mm = _TO.search(body or "") or _IN.search(body or "")
        city = mm["d"] if mm else None
    if city:
        return {"k": "j", "label": await _journey_for_city(account, city, f.get("open_at"))}
    return None


def _short(label: str) -> str:
    return re.sub(r"^\W+\s*", "", label)


def announce(out_items: List[tuple], old: Optional[dict], new: Optional[dict], lead: int) -> Optional[dict]:
    """(1) The one-line switch with its Back button, put FIRST (after "🎙 I heard"). Returns the mode now in force."""
    cur = new or old
    if old and new and old["label"] != new["label"]:
        back = f"Back to {_short(old['label'])}"
        back = back if len(back) <= 20 else (f"↩ {_short(old['label'])}"[:20])   # WhatsApp's button: 20 characters
        to = re.sub(r",\s*\w{3}$", "", _short(new["label"]))   # "Vietnam, Nov" → "your Vietnam trip"
        words = f"your {to} trip" if new["k"] == "j" and not to.startswith(("Madrid", "Move")) and "📍" not in new["label"] \
            else (to if "📍" in new["label"] else f"your {to}" if not to.endswith("Me") else to)
        payload = f"mback:p:{old['p']}" if old["k"] == "p" else f"mback:j:{old['label']}"[:200]
        out_items.insert(lead, ("ask", f"↪ Switching to {words}.", [(back, payload)]))
    return cur


def label_first(out_items: List[tuple], mode: Optional[dict]) -> None:
    """(3) The small label on the reply's first text."""
    if not mode:
        return
    for i, it in enumerate(out_items):
        if it[0] in ("text", "ask") and not it[1].startswith("🎙"):
            out_items[i] = (it[0], f"_Now: {mode['label']}_\n{strip_label(it[1])}", *it[2:])
            return


def back_to(payload: str) -> Optional[Tuple[str, str]]:
    """A Back tap → ("p", product) or ("j", label)."""
    m = re.match(r"mback:(p|j):(.+)$", payload or "")
    return (m[1], m[2]) if m else None


async def ambiguous(account: str, body: str, waiting: List[str], asked_last: Optional[str]) -> Optional[Tuple[str, list]]:
    """(2) "book my flights" with a product's journey open AND a Sasha trip ahead → (the question, its buttons); else None."""
    if not _AMBIG.match(body or ""):
        return None
    prods = [x for x in ([asked_last] if asked_last else []) + waiting if x in ("relocation", "campus")]
    if not prods:
        return None
    from . import plan_store as PS, journeys as JN
    trips = [p for p in await PS.plans(account) if JN.product_of(p.get("title") or "") == "sasha" and p.get("start")]
    if not trips:
        return None
    t = trips[0]
    n = uuid.uuid4().hex[:6]
    tl = f"{JN.label(t).split(',')[0]} trip"[:20]
    pl = {"relocation": "Move to Madrid", "campus": "Campus visits"}[prods[0]]
    return (f"Which one is that for — your {JN.label(t)} trip or your {pl.lower() if prods[0] == 'campus' else pl}?",
            [(tl, f"amb:{n}:s:{t['trip_id']}"), (pl, f"amb:{n}:p:{prods[0]}")])


async def flights_for(account: str, trip_id: str) -> Optional[str]:
    """The Sasha sentence for a trip's flights: "flights from Madrid to Hanoi on 2026-11-11"."""
    from . import plan_store as PS
    p = await PS.by_id(account, trip_id)
    if not p:
        return None
    days = (p.get("plan") or {}).get("days") or []
    cities = [d.get("city") for d in days if d.get("city")]
    start = p.get("start") or (days[0].get("date") if days else None)
    if not cities or not start:
        return None
    return f"flights from Madrid to {cities[0].split(',')[0]} on {str(start)[:10]}"


__all__ = ["before", "after", "announce", "label_first", "back_to", "ambiguous", "flights_for", "PRODUCT_IDLE", "strip_label"]
