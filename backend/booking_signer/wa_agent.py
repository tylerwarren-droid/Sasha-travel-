"""Sasha 237 · WHATSAPP ON THE ONE BRAIN (EU 232 spec §1.1–1.2): a WhatsApp message goes to the same agent as /s2 —
sasha.turn_with_quiver(surface="wa"): S2's tools, wrappers, persona (+ S2.WA_NOTE), guards and the ONE yes rule — and its events
are drawn for WhatsApp here (render). guest_whatsapp keeps identity, STOP/START, reminders words, products and the 24-hour rule.

    SASHA_WA_BRAIN = old (default: today's path exactly) | agent (everyone) | agent_for:<account id>,<account id>…

Taps come back as the same turns /s2 sends:
    pick:<place_id>   a venue row in the list picker → the row's name + pick_hint (that card's place_id)
    say:<words>       a flight / stay row → its words, as /next's Choose button says them ("the Iberia flight out at 10:35")
    yn:yes / yn:no    the [Yes] [No] under a read-back → "yes" / "no" — in a LATER turn than the read-back, as on /s2

Never a card on "your screen": every card is text (and, where it helps, its /s2 page).
"""
from __future__ import annotations

import logging
import os
import re
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger("sasha.wa_agent")
MAX_MSG = 1400          # a WhatsApp message (split at sentence ends past this)
LIST_ROWS = 10          # WhatsApp's list picker: 10 rows at most
TITLE, DESC = 24, 72    # its row title / description limits


# ── the flag ─────────────────────────────────────────────────────────────────────────────────────────────────────────────

def mode() -> str:
    return os.getenv("SASHA_WA_BRAIN", "old").strip() or "old"


def on(account: Optional[str]) -> bool:
    m = mode()
    if m == "agent":
        return True
    if m.startswith("agent_for:"):
        ids = {x.strip().lower() for x in m.split(":", 1)[1].split(",") if x.strip()}
        return str(account or "").lower() in ids
    return False


def ours(payload: str) -> bool:
    """A button from THIS brain (not an in-flight one from the old flows, which finish there)."""
    return payload.startswith(("pick:", "say:", "yn:"))


def s2_link(path: str = "") -> str:
    return os.getenv("SASHA_WEB_URL", "https://project.kanoe.ai").rstrip("/") + "/s2" + path


# ── a tap → the turn /s2 would have sent ─────────────────────────────────────────────────────────────────────────────────

def message_of(account: str, body: str, payload: str, button_text: str = "") -> str:
    if payload.startswith("pick:"):
        from app.agent.sasha import pick_hint
        return pick_hint(account, payload[5:], button_text or body or "This one")
    if payload.startswith("say:"):
        return payload[4:] or button_text or body
    if payload == "yn:yes":
        return "Yes"
    if payload == "yn:no":
        return "No"
    return body


# ── the renderer: every render kind → WhatsApp (a test fails if a kind isn't here) ──────────────────────────────────────────

def _cut(s: Any, n: int) -> str:
    s = re.sub(r"\s+", " ", str(s or "")).strip()
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def _venues(ev: dict, out) -> None:
    cards = ((ev.get("preset") or {}).get("cards") or [])[:LIST_ROWS]
    if not cards:
        return
    lines = [f"{i}. {c.get('name')}" + (f" · ★{c['rating']}" if c.get("rating") else "") + (f" · {c.get('area')}" if c.get("area") else "")
             for i, c in enumerate(cards, 1)]
    for c in cards[:3]:
        if c.get("photo"):
            out.media(_cut(c.get("name"), 60), c["photo"])
    out.pick("\n".join(lines), "See the places",
             [(_cut(c.get("name"), TITLE), _cut(" · ".join(x for x in (f"★{c['rating']}" if c.get("rating") else "", c.get("area") or c.get("type") or "") if x), DESC),
               f"pick:{c.get('place_id')}") for c in cards if c.get("place_id")])


def _options(ev: dict, out) -> None:
    card = ev.get("card") or {}
    cards = [card] if card else []
    cards += [c for c in ev.get("cards") or [] if isinstance(c, dict)]
    for c in cards:
        opts = c.get("options") or []
        if not opts:
            continue
        rows = [(_cut(o.get("name"), TITLE), _cut(" · ".join(x for x in (o.get("price"), o.get("detail")) if x), DESC),
                 "say:" + _cut(o.get("pick") or f"the {o.get('name')} one", 190)) for o in opts[:LIST_ROWS]]
        more = f"\nAll options: {s2_link()}" if len(opts) > LIST_ROWS else ""
        out.pick(_cut(c.get("title") or "The options", 200) + more, "See the options", rows)


def _read_back(ev: dict, out) -> None:
    lines = [l for l in ev.get("read_back") or [] if str(l).strip() and not str(l).lstrip().startswith("⚠")]
    if not lines:
        return
    if ev.get("status") in ("sent", "not_sent"):   # an outcome card, not a question
        out.text("\n".join(lines))
        return
    out.ask("\n".join(lines)[:1000], [("Yes", "yn:yes"), ("No", "yn:no")])


def _card(ev: dict, out, title: str) -> None:
    """notice / claim_status / accident / counter_card / my_cards / activities / plans: a few key lines + its /s2 page."""
    lines: List[str] = []
    k = ev.get("kind")
    if k == "notice":
        lines = [ev.get("title") or ""] + list(ev.get("lines") or [])[:4]
    elif k == "plans":
        for it in (ev.get("items") or [])[:8]:
            lines.append(" · ".join(x for x in (str(it.get("when") or "")[:16].replace("T", " "), it.get("title"), it.get("status")) if x))
        lines.append("Change or cancel: just say which.")
    elif k == "my_cards":
        lines = [f"{c.get('product')} · {c.get('network') or ''}".strip(" ·") for c in (ev.get("cards") or [])[:6]]
    elif k == "claim_status":
        c = ev.get("claim") or {}
        lines = [x for x in (c.get("state"), *(d.get("say") for d in (c.get("deadlines") or [])[:3])) if x]
    elif k == "counter_card":
        c = ev.get("card") or {}
        lines = [x for x in (c.get("card"), c.get("framing"), c.get("say")) if x]
    elif k == "accident":
        v = ev.get("view") or {}
        lines = [x for x in (v.get("say"), v.get("step")) if x]
    elif k == "activities":
        for c in (ev.get("cards") or [])[:5]:
            when = ((c.get("event") or {}).get("title") or (c.get("open") or {}).get("hours") or "")
            price = (c.get("price") or {}).get("text") or ""
            lines.append(" · ".join(x for x in (c.get("name"), when, price, c.get("ticket_url") or c.get("official_url")) if x))
        if ev.get("unread"):
            lines.append("Couldn't check on their own sites: " + ", ".join(ev["unread"][:4]))
    lines = [_cut(l, 300) for l in lines if str(l or "").strip()]
    if lines:
        out.text("\n".join([f"*{title}*"] + lines + [f"See the card: {s2_link()}"]))


def _capabilities(ev: dict, out) -> None:
    lines = []
    for g in ev.get("groups") or []:
        lines.append(f"*{g.get('group')}*: " + "; ".join(g.get("items") or []))
    if lines:
        out.text("\n".join(lines))


def _calendar(ev: dict, out) -> None:
    links = ev.get("links") or {}
    if links.get("google") or links.get("apple"):
        out.text("\n".join(x for x in (f"Google: {links.get('google')}" if links.get("google") else "",
                                       f"Apple / other (.ics): {links.get('apple')}" if links.get("apple") else "") if x))


def _pay(ev: dict, out) -> None:
    if ev.get("already_paid"):
        out.text("Already paid — nothing more to pay.")
    elif ev.get("url"):
        out.text(f"Pay here (Apple Pay opens on the page): {ev['url']}")


def _handover(ev: dict, out) -> None:
    if ev.get("url"):
        out.text(f"Tap to finish: {ev['url']}")


def _keep_capture(ev: dict, out, st: dict, now) -> None:
    what = "loyalty card" if ev.get("what") == "loyalty" else "passport's photo page"
    out.text(f"Send me a photo of your {what} here.")
    st["photo_for"] = {"kind": "loyalty" if ev.get("what") == "loyalty" else "passport", "at": now.isoformat()}


def _wa_open(ev: dict, out) -> None:
    if ev.get("text") or ev.get("open"):
        out.text("\n".join(x for x in (ev.get("text"), ev.get("open")) if x))


def _line(ev: dict, out) -> None:
    """flight_chosen / total: one line."""
    t = ev.get("total") or {}
    eur = t.get("total_eur") if isinstance(t, dict) else None
    out.text(f"Chosen. The total, all in: €{eur:,.2f}" if isinstance(eur, (int, float)) else "Chosen — it's in your trip.")


def _nothing(ev: dict, out) -> None:
    return None


KIND_MAP = {
    "venues": _venues, "flights": _options, "stays": _options, "flight_chosen": _line, "total": _line, "read_back": _read_back,
    "pay": _pay, "pay_here": _pay, "handover": _handover, "calendar": _calendar, "capabilities": _capabilities, "wa_open": _wa_open,
    "plans": lambda ev, out: _card(ev, out, "Your plans"), "notice": lambda ev, out: _card(ev, out, "Update"),
    "claim_status": lambda ev, out: _card(ev, out, "Your claim"), "accident": lambda ev, out: _card(ev, out, "The accident"),
    "counter_card": lambda ev, out: _card(ev, out, "At the counter"), "my_cards": lambda ev, out: _card(ev, out, "Your cards"),
    "activities": lambda ev, out: _card(ev, out, "Things to do"),
    "keep_capture": "keep_capture",          # sets st["photo_for"] (needs the state)
    "keep_handoff": _nothing,                # WhatsApp takes the photo directly
    "focus": _nothing, "trip": _nothing, "inline": _nothing,
}


def render(ev: dict, out, st: dict, now) -> None:
    k = ev.get("kind")
    f = KIND_MAP.get(k)
    if f is None:
        log.warning("[wa_agent] no WhatsApp drawing for render kind %s — dropped", k)
        return
    if f == "keep_capture":
        _keep_capture(ev, out, st, now)
    else:
        f(ev, out)


def split(text: str, n: int = MAX_MSG) -> List[str]:
    """One message, or several at sentence ends — never a word cut in two."""
    text = (text or "").strip()
    parts: List[str] = []
    while len(text) > n:
        cut = max(text.rfind(". ", 0, n), text.rfind("? ", 0, n), text.rfind("! ", 0, n), text.rfind("\n", 0, n))
        cut = cut + 1 if cut > n // 3 else n
        parts.append(text[:cut].strip())
        text = text[cut:].strip()
    return parts + ([text] if text else [])


# ── the turn ─────────────────────────────────────────────────────────────────────────────────────────────────────────────

async def agent_turn(ch: dict, body: str, payload: str, st: dict, out, now, button_text: str = "") -> str:
    """One WhatsApp message → the agent (surface "wa") → `out`. Saves the history and her memory (awaited). Returns the reply."""
    from agapi import s2_closing as CL, s2_keep as KEEP, s2_memory as MEM
    from app.agent import sasha as AG
    account, key = ch["account_id"], ch["wa_id_sha256"]
    message = message_of(account, body, payload, button_text)
    history = [m for m in (st.get("history") or []) if m.get("role") in ("user", "assistant")]
    held = KEEP.chat_guard(message)                      # a password, card or passport number never reaches the model
    if held:
        out.text(held)
        return held
    history = KEEP.clean_history(history)
    lang = CL.closing(message) if history else None      # "thanks / bye" after a conversation → she rests
    if lang:
        bye = CL.line(lang)
        out.text(bye)
        st["dormant"] = now.isoformat()
        try:
            await MEM.closing(account, message, bye)
        except Exception as e:
            log.warning("[wa_agent] closing not kept: %s", type(e).__name__)
        _remember_history(st, body or message, bye)
        return bye
    st.pop("dormant", None)                              # the next message wakes her
    over = await AG.over_budget(account)
    if over:
        out.text(over)
        return over
    text, renders, seen = "", [], {}
    async for ev in AG.turn_with_quiver(account, message, history, "wa:" + key, surface="wa"):
        t = ev.get("type")
        if t == "text":
            text += str(ev.get("delta") or "")
        elif t == "replace":
            text = str(ev.get("text") or "")
        elif t == "render":
            renders.append(ev)
            if ev.get("kind") == "venues" and ev.get("preset"):
                seen.update(cards=(ev["preset"].get("cards") or []), ribbon=ev.get("ribbon"))
        elif t == "error":
            text = str(ev.get("message") or text)
        elif t == "done":
            text = str(ev.get("text") or text)
            seen["calls"] = ev.get("tools") or []
    for part in split(text):
        out.text(part)
    for ev in renders:
        render(ev, out, st, now)
    _remember_history(st, body or message, text)
    try:   # awaited, in the turn — never fire-and-forget
        await MEM.remember(account, "wa:" + key, message[:4000], text, seen)
    except Exception as e:
        log.warning("[wa_agent] turn not kept in memory: %s", type(e).__name__)
    return text


def _remember_history(st: dict, user: str, reply: str) -> None:
    from .guest_whatsapp import HISTORY_KEEP
    st["history"] = ((st.get("history") or []) + [{"role": "user", "content": user}]
                     + ([{"role": "assistant", "content": reply}] if reply else []))[-HISTORY_KEEP:]


__all__ = ["on", "mode", "ours", "message_of", "render", "KIND_MAP", "agent_turn", "split"]
