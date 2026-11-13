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
import logging
from typing import Any, Callable, Dict, List, Optional, Tuple

log = logging.getLogger("products.tools")

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


#: Sasha 344 · the back row's title on AD's menu is AgAPI's (ad_menu.BACK) and still reads "← All tools" — the SAME id, kanoe:tools. A tap
#: is matched by its id first; this title only when Twilio sent no id. PATCH (said): dropped when CR retitles ad_menu.BACK (Sasha 343's ask).
BACK_TITLES_SEEN = ("← All tools",)


def tap_fields(p: Dict[str, Any]) -> Tuple[str, str]:
    """Sasha 344 · a tap → (its EXACT words, its id), from whatever field Twilio put it in. A list-picker row (every tool's Menu, Sasha's
    and AD's): ListId and ListTitle — Twilio's Body there is the row's title AND its description joined ("Show my cases\nYour cases, and
    the status of the one you pick"), so a list row is NEVER read from Body. A quick-reply button: ButtonPayload (its words in Body). A typed message: Body. The ONE reader every path uses."""
    if p.get("ListId") or p.get("ListTitle"):
        title = str(p.get("ListTitle") or "").strip() or str(p.get("Body") or "").split("\n", 1)[0].strip()
        return title, str(p.get("ListId") or "").strip()
    return str(p.get("Body") or ""), str(p.get("ButtonPayload") or "").strip()   # a button's words are its Body, as before


OWN = "kanoe:"   # Sasha's own ids (the back row, a tool's row, a sentence row); any other id is its tool's (AD's "ad_…")


def own_id(p: Dict[str, Any]) -> str:
    """The tap's id when it is SASHA's (kanoe:…) — her switch and her rows; another tool's row reaches it as its exact title (and its id
    stays in Twilio's own field, ListId, for that tool)."""
    pid = tap_fields(p)[1]
    return pid if pid.startswith(OWN) or not (p.get("ListId") or p.get("ListTitle")) else ""


def normalized(p: Dict[str, Any]) -> Dict[str, Any]:
    """Sasha 344 · the message as what was TAPPED, once, where it enters (the webhook and the turn): Body = the row's EXACT title (never
    Twilio's joined title + description). Twilio's ListId / ListTitle stay as they came, for the tool whose row it is."""
    if not (p.get("ListId") or p.get("ListTitle")):
        return p
    return {**p, "Body": tap_fields(p)[0]}


def switch_tap(p: Dict[str, Any]) -> Optional[Tuple[str, Any]]:
    """Sasha 344 · THE ONE SWITCH, before any tool's door (AgAPI's inbound included): the back row or a tool's row → ("tools", None) /
    ("tool", <tool>); anything else → None (the message goes on as before)."""
    tap = tapped(*tap_fields(p))
    return tap if tap and tap[0] in ("tools", "tool") else None


def tapped(body: str, payload: str) -> Optional[Tuple[str, Any]]:
    """("tools", None) for "← Everything I can do" · ("tool", <tool>) for a tool's row · ("say", <words>) for a menu row that is a sentence · None."""
    if payload == BACK["id"] or (not payload and _norm(body) in {_norm(x) for x in (BACK["title"],) + BACK_TITLES_SEEN}):
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


# ── Sasha 361 → Sasha 379b (CR 192) · WHICH PRODUCT a WhatsApp message is for is decided ONCE, by AgAPI, on the webhook's first call ─
# (messages.whatsapp_inbound): AD's own reading of THESE words (conversation_role.ad_intent), read with every question of AD's still open —
# AD's → AgAPI routes it to AD (matched: true) and nothing of Sasha's answers; anything else is Sasha's. Sasha decides nothing about AD:
# no memory of a "choice" (rule 2, `chose`), no ONE question of her own, no `space`. Her own tools are still picked by their word (route).

#: the products another service answers (their tools' ids); every other tool is Sasha's own
OTHER_PRODUCTS = ("diligence",)


def _keyword_tool(body: str) -> Optional[Dict[str, Any]]:
    """The tool the message EXPLICITLY names: its keyword at the start (the ONE keyword switch, products/whatsapp's matchers) — "ad" only
    alone ("ad hoc …" is a word)."""
    from . import whatsapp as PW
    b = body or ""
    if PW._EXIT.match(b):
        return BY_ID["travel"]
    for t in TOOLS:
        rx = PW._KEYWORD.get(t["product"]) if t["product"] else None
        if rx is not None and rx.match(b):
            if t["id"] == "diligence" and PW._AD_SHORT.match(b) and PW._AD_SHORT.sub("", b, count=1).strip(" :,"):
                continue
            return t
    return None


def product_of(tool: Dict[str, Any]) -> str:
    return tool["id"] if tool["id"] in OTHER_PRODUCTS else "sasha"


def route(body: str, conversation_role: Optional[Dict[str, Any]]) -> str:
    """Sasha 379b · a message AgAPI did NOT take (unmatched) → the product of Sasha's that answers it: one of her own tools named by its
    word, else Sasha (travel). AD's words never reach here — AgAPI took them on the first call; one that did ("ad" yet unmatched) is a
    contract breach: logged loudly, never rerouted by Sasha."""
    cr = conversation_role if isinstance(conversation_role, dict) else {}
    if cr.get("ad_intent") == "ad":
        log.error("[tools] AgAPI left a message unmatched that AD read as AD's (ad_intent \"ad\") — never rerouted here (CR 192)")
    kw = _keyword_tool(body)
    return product_of(kw) if kw is not None else "sasha"


def switched_to(p: Dict[str, Any]) -> Optional[str]:
    """Sasha 383 · CR 202 · the product a WhatsApp message EXPLICITLY switches the conversation to — the registry's recognition, and only
    it: the back row ("← Everything I can do") or a tool's row (tapped or typed as its title), or a tool's keyword at the start ("sasha",
    "diligence …", "campus …") → the tool's product ("travel" for Sasha's own); anything else → None. Which product the conversation IS
    in is AgAPI's record (messages.whatsapp_switch), never kept here."""
    tap = switch_tap(p)
    if tap is not None:
        t = tap[1] if tap[0] == "tool" else None
        return (t or {}).get("product") or "travel"
    kw = _keyword_tool(tap_fields(p)[0] if (p.get("ListId") or p.get("ListTitle")) else str(p.get("Body") or ""))
    return (kw.get("product") or "travel") if kw is not None else None


def keyword_rest(body: str) -> str:
    """The words after an explicit keyword ("diligence do 1-3 on Halfords" → "do 1-3 on Halfords")."""
    from . import whatsapp as PW
    t = _keyword_tool(body)
    if t is None:
        return body or ""
    rx = PW._EXIT if t["id"] == "travel" else PW._KEYWORD[t["product"]]
    return rx.sub("", body or "", count=1).strip(" :,")
