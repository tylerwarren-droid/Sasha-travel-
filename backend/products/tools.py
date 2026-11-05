"""CR 165 · KANOE'S TOOLS ON WHATSAPP — ONE registry (Tyler, 4 Nov 13:53: "'say sasha' and 'send link' are confusing… a Kanoe menu and a
menu within each tool, always present").

  TOOLS        each tool once: its name, emoji, keyword, the product it opens, whether it is on, and its OWN menu from its OWN one list
               (Travel: agapi/s2_home.py CAPABILITIES · Diligence: AgAPI's ad_menu.ABILITIES, sent by AgAPI on AD's replies · the others:
               their own words). The welcome, the switch (a tap → the tool's keyword, through the ONE keyword switch in
               products/whatsapp.py), the Menu button on every reply and the hints are all read from here. Adding a tool = one entry.
  BACK         "← Everything I can do" (Sasha 343; was "← All tools"), id kanoe:tools — the first row of every tool's menu. AgAPI puts the SAME id first on AD's menu (its
               ad_menu.BACK): the webhook reads every tap first, so this id is answered here with the tools.
  NEVER        a sentence telling someone which word to type for another tool, or to type a link command — the Menu is always there
               instead; another tool is pointed to with go(): "tap Menu → 🇪🇸 España"
               (tests/test_cr165_tools.py scans for it).
"""
from __future__ import annotations

import os
import re
from typing import Any, Callable, Dict, List, Optional, Tuple

BACK = {"title": "← Everything I can do", "id": "kanoe:tools", "description": "Everything Sasha can help you with"}   # Sasha 343 (Tyler)
TOOL_ID = "kanoe:tool:"   # a tool's row id: kanoe:tool:<id>
MENU_BUTTON = "Menu"


def _travel_menu() -> List[Tuple[str, str, str]]:
    from agapi import s2_home as S2H   # Sasha's ONE capability list (Sasha 249): its chips, as typed
    return [(c[:24], "", f"kanoe:say:{c[:180]}") for c in S2H.CHIPS[:6]]


def _start_over(word: str) -> Callable[[], List[Tuple[str, str, str]]]:
    return lambda: [("Start again", "From the beginning", f"kanoe:say:start over {word}")]


# Sasha 343 (Tyler, 5 Nov 06:07 — DECIDED): Sasha IS the assistant on every channel; these are things SHE does. Each tool's name, its one
# question on switching ("Sasha · 🔍 Due diligence — who should I investigate?") and its row's line live HERE and nowhere else.
TOOLS: List[Dict[str, Any]] = [
    {"id": "travel", "emoji": "✈️", "name": "Travel", "ask": "where would you like to go?", "does": "Trips, flights, hotels and tables",
     "word": "sasha", "product": None, "menu": _travel_menu},
    {"id": "diligence", "emoji": "🔍", "name": "Due diligence", "ask": "who should I investigate?", "does": "Companies and people, checked (Applied Diligence)",
     "word": "diligence", "product": "diligence", "menu": None},   # AgAPI sends AD's own menu (ad_menu.ABILITIES, BACK first) on every AD reply
    {"id": "espana", "emoji": "🇪🇸", "name": "España", "ask": "what do you need done in Spain?", "does": "Spain's public services, done with you",
     "word": "españa", "product": "health", "menu": _start_over("españa")},
    {"id": "relocate", "emoji": "🏠", "name": "Relocation", "ask": "shall we start your move to Spain?", "does": "Your Spanish residence papers and the move",
     "word": "relocate", "product": "relocation", "menu": _start_over("relocate")},
    {"id": "campus", "emoji": "🎓", "name": "Campus visits", "ask": "which universities would you like to visit?", "does": "University visits, read live and planned",
     "word": "campus", "product": "campus", "menu": _start_over("campus")},
]
BY_ID = {t["id"]: t for t in TOOLS}
BY_PRODUCT = {t["product"]: t for t in TOOLS}


def on(tool: Dict[str, Any]) -> bool:
    """A tool is switched on unless KANOE_TOOLS_OFF names it (comma-separated ids). Travel is always on."""
    off = {x.strip().lower() for x in os.getenv("KANOE_TOOLS_OFF", "").split(",") if x.strip()}
    return tool["id"] == "travel" or tool["id"] not in off


def title(t: Dict[str, Any]) -> str:
    return f"{t['emoji']} {t['name']}"[:24]


def tools_rows() -> List[Tuple[str, str, str]]:
    """The Kanoe menu: (title ≤ 24, description ≤ 72, id) per switched-on tool."""
    return [(title(t), t["does"][:72], TOOL_ID + t["id"]) for t in TOOLS if on(t)]


def menu_rows(product: Optional[str]) -> Optional[List[Tuple[str, str, str]]]:
    """The Menu on a reply: the tools at the top level (travel, Sasha's default — then travel's own chips), else the tool's own menu with
    "← Everything I can do" first."""
    t = BY_PRODUCT.get(product)
    if t is None or t["id"] == "travel":
        return (tools_rows() + _travel_menu())[:10]
    back = [(BACK["title"], BACK["description"][:72], BACK["id"])]
    return back + (t["menu"]()[:9] if t["menu"] else [])   # Diligence: AgAPI's replies carry AD's own menu; Sasha's lines there, the way back


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w ←]", " ", (s or "").lower())).strip()


def tapped(body: str, payload: str) -> Optional[Tuple[str, Any]]:
    """("tools", None) for "← Everything I can do" · ("tool", <tool>) for a tool's row · ("say", <words>) for a menu row that is a sentence · None."""
    if payload == BACK["id"] or _norm(body) == _norm(BACK["title"]):
        return ("tools", None)
    if payload.startswith(TOOL_ID) and payload[len(TOOL_ID):] in BY_ID:
        return ("tool", BY_ID[payload[len(TOOL_ID):]])
    if payload.startswith("kanoe:say:"):
        return ("say", payload[len("kanoe:say:"):])
    for t in TOOLS:   # the row's title, typed or tapped without its id
        if not payload and _norm(body) == _norm(title(t)):
            return ("tool", t)
    return None


WELCOME = "Hi, I'm Sasha."
CAN = "I can help you with:"


def _all() -> str:
    return " · ".join(title(t) for t in TOOLS if on(t))


def welcome_text() -> str:
    """ "Hi, I'm Sasha. I can help you with: ✈️ Travel · 🔍 Due diligence · 🇪🇸 España · 🏠 Relocation · 🎓 Campus visits" (the rows: taps)."""
    return f"{WELCOME} {CAN} {_all()}"


def tools_text() -> str:
    return f"{CAN} {_all()}"


TOOLS_LINE = CAN   # the first line of the list (tests and AgAPI read it)


def name_of(product: Optional[str]) -> str:
    """A space's name, from the registry ("trip" and Sasha's own space are travel)."""
    t = BY_PRODUCT.get(None if product in (None, "sasha", "trip", "travel") else product)
    return title(t) if t else str(product)


def space_line(product: Optional[str], entering: bool = False) -> str:
    """Sasha 343 · the line on a reply in a space: "Sasha · 🔍 Due diligence" — and on the switch into it, its one question:
    "Sasha · 🔍 Due diligence — who should I investigate?". Sasha is always the one speaking."""
    t = BY_PRODUCT.get(None if product in (None, "sasha", "trip", "travel") else product)
    if t is None:
        return f"Sasha · {product}"
    return f"Sasha · {title(t)}" + (f" — {t['ask']}" if entering else "")


def go(tool_id: str) -> str:
    """CR 165 · how a reply points to another tool: the Menu, in the registry's own words — "tap Menu → 🇪🇸 España"."""
    return f"tap Menu → {title(BY_ID[tool_id])}"
