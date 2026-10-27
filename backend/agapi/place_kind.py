"""Sasha 297 · "WHAT KIND OF PLACE?" — THE ONE PLACE S2 decides whether to ask before a restaurant search, and what the answer sends
(Tyler, 27 Oct: "can she ask us what type of restaurant are you looking for? budget, fine dining… or take away?").

  ask   a VAGUE restaurant ask (the search's `what` is only dining words: "restaurant", "somewhere for dinner"), no kind in the person's
        OWN words this turn, none held for this session, and not asked yet this session → her ONE question (voice.KIND_ASK) with three
        taps (voice.KIND_CHOICES); the search waits for the answer.
  go    otherwise — with what the kind sends to AgAPI venue.discover. Each maps onto AgAPI's OWN existing behaviour (AgAPI
        discovery_rules, read-only), never a ranking, list or venue of S2's:
          special  → nothing added: AgAPI already orders curated recognition first
          value    → "good value" leads the search's `what` — exactly where a person's own "cheap restaurant" goes: AgAPI reads its value
                     words there (venue_discover_in takes no other field for it — `notes` is refused) → its value ranking first
          takeaway → intent "takeaway" · delivery → intent "delivery": AgAPI's fits_intent keeps those places and labels them
The answer holds for the session; asked once, never again in that session — whatever the answer was. New chat = a new session.
The person's words are only READ here (to know they already said it); nothing here is shown, and nothing here names a place.
Called from ONE site: v0._discover (S2's only search), before venue.discover.
"""
from __future__ import annotations

import re
import time
from typing import Any, Dict, Optional, Tuple

KINDS = ("special", "value", "takeaway", "delivery")
#: the person's own words that already say the kind (read, never shown). Takeaway and delivery are NOT read here: they are the intent,
#: read in its ONE place (v0.intent_of, Sasha 291) and passed in.
SAID = (
    ("value", re.compile(r"(?i)\b(?:cheap(?:er|est)?|budget|good value|value for money|affordable|inexpensive|not too expensive|"
                         r"bib|barat[oa]s?|econ[oó]mic[oa]s?|men[uú] del d[ií]a|(?:buena relaci[oó]n )?calidad[- ]precio)\b")),
    ("special", re.compile(r"(?i)\b(?:something special|special (?:occasion|night|dinner|meal)|michelin|starred|\d\s*stars?|fine[- ]dining|"
                           r"fancy|upscale|high[- ]end|tasting menu|gastronomic|haute cuisine|celebrat\w*|anniversary|"
                           r"algo especial|alta cocina|con estrellas?|estrellas? michelin|ocasi[oó]n especial|aniversario|celebra\w*|"
                           r"men[uú] degustaci[oó]n)\b")),
)
#: a dining ask with nothing more in it: every word of the search's `what` is one of these, and one names a meal or a restaurant
_GENERIC = {"a", "an", "the", "some", "somewhere", "something", "place", "places", "spot", "good", "nice", "great", "decent", "lovely",
            "best", "local", "new", "to", "for", "of", "out", "eat", "dine", "dining", "food", "bite", "meal", "restaurant", "restaurants",
            "dinner", "lunch", "brunch", "breakfast", "supper", "table", "tonight", "today", "tomorrow", "go", "get",
            # Sasha 298 · the same, in Spanish
            "un", "una", "unos", "algo", "algún", "alguno", "sitio", "sitios", "lugar", "bueno", "buen", "buena", "para", "de", "donde",
            "comer", "cenar", "almorzar", "comida", "cena", "almuerzo", "desayuno", "mesa", "restaurante", "restaurantes", "esta",
            "noche", "hoy", "mañana", "salir"}
_MEAL = {"eat", "dine", "dining", "food", "meal", "restaurant", "restaurants", "dinner", "lunch", "brunch", "breakfast", "supper", "table",
         "comer", "cenar", "almorzar", "comida", "cena", "almuerzo", "desayuno", "mesa", "restaurante", "restaurantes"}
#: what settles it without asking: they said what they want to do (eat right now) — or the kind itself
SETTLED_INTENTS = ("takeaway", "delivery", "eat_now")


def tap_kind(said: Optional[str]) -> Optional[str]:
    """Their tap on one of her three answers (its words exactly, voice.KIND_CHOICES) → its kind; "Takeaway / delivery" is takeaway."""
    from app.agent import voice as V
    t = str(said or "").strip().rstrip(".!").lower()
    return next((k for labels in (V.KIND_CHOICES, V.KIND_CHOICES_ES)   # Sasha 298 · either language's taps
                 for c, k in zip(labels, ("special", "value", "takeaway")) if c.lower() == t), None)


def said_kind(said: Optional[str]) -> Optional[str]:
    """The kind the person's OWN words this turn already say (special · value), or None."""
    for kind, pat in SAID:
        if pat.search(str(said or "")):
            return kind
    return None


def vague(what: Optional[str]) -> bool:
    """A restaurant ask with nothing more in it ("restaurant", "somewhere for dinner") — never a cuisine, a dish, a style or a name."""
    words = re.findall(r"[a-záéíóúñ]+", str(what or "").lower())
    return bool(words) and all(w in _GENERIC for w in words) and any(w in _MEAL for w in words)


def decide(said: Optional[str], what: Optional[str], intent: str, held: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """→ {"ask": True} — her ONE question now; or {"ask": False, "kind": kind | None, "body": {what venue.discover gets for it},
    "hold": {the session's record now} | None}. `held`: this session's record ({"asked", "kind"}) or None."""
    h = held or {}
    k = tap_kind(said) or said_kind(said) or (intent if intent in ("takeaway", "delivery") else None)
    if k:   # said now: this search has it; it HOLDS for the session only as the answer to her question
        return {"ask": False, "kind": k, "body": body_for(k, what), "hold": {"asked": True, "kind": k} if h.get("asked") and not h.get("kind") else None}
    if h.get("kind") in KINDS:   # their answer holds for the session — but what they say they want to do NOW ("book…") wins
        b = body_for(h["kind"], what)
        return {"ask": False, "kind": h["kind"], "body": {} if "intent" in b and intent != "browse" else b, "hold": None}
    if h.get("asked") or intent in SETTLED_INTENTS or not vague(what):
        return {"ask": False, "kind": None, "body": {}, "hold": None}
    return {"ask": True, "hold": {"asked": True, "kind": None}}


VALUE_WORDS = "good value"


def body_for(kind: Optional[str], what: Optional[str] = None) -> Dict[str, Any]:
    """What venue.discover gets for this kind — AgAPI's own inputs only (venue_discover_in: what · intent · …)."""
    if kind == "value":
        return {} if said_kind(what) == "value" else {"what_prefix": VALUE_WORDS}   # their `what` already says it: nothing added
    if kind in ("takeaway", "delivery"):
        return {"intent": kind}
    return {}   # special (AgAPI's recognition-first order is its default) or none


# ── the session's record: this process first, the account's memory row (s2_memory kinds) behind it ──────────────────────────────
_HELD: Dict[Tuple[str, str], Tuple[float, Dict[str, Any]]] = {}
TTL_S = 12 * 3600
KEY = "place_kind"


async def held_for(account: str, session: Optional[str]) -> Optional[Dict[str, Any]]:
    if not account or not session:
        return None
    x = _HELD.get((account, session))
    if x and time.time() - x[0] < TTL_S:
        return x[1]
    from agapi import s2_memory as MEM
    rec = await MEM.kind(account, KEY)
    if isinstance(rec, dict) and rec.get("session") == session:
        v = {"asked": bool(rec.get("asked")), "kind": rec.get("kind") if rec.get("kind") in KINDS else None}
        _HELD[(account, session)] = (time.time(), v)
        return v
    return None


async def hold(account: str, session: Optional[str], rec: Dict[str, Any]) -> None:
    if not account or not session:
        return
    _HELD[(account, session)] = (time.time(), dict(rec))
    from agapi import s2_memory as MEM
    await MEM.put_kind(account, KEY, {"session": session, **rec})


__all__ = ["KINDS", "SAID", "tap_kind", "said_kind", "vague", "decide", "body_for", "held_for", "hold", "KEY"]
