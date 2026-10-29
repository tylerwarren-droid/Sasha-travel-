"""Sasha 237 · WHATSAPP ON THE ONE BRAIN (EU 232 spec §1.1–1.2): a WhatsApp message goes to the same agent as /s2 —
sasha.turn_with_quiver(surface="wa"): S2's tools, wrappers, persona (+ S2.WA_NOTE), guards and the ONE yes rule — and its events
are drawn for WhatsApp here (render). guest_whatsapp keeps identity, STOP/START, reminders words, products and the 24-hour rule.

Sasha 253 · item 5: the brain answers EVERY linked account's WhatsApp — no switch (SASHA_WA_BRAIN and its agent_for list are retired).

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


# Sasha 253 · ONE BRAIN FOR EVERYONE (Tyler, mailbox 807/809): every account's WhatsApp goes to agent_turn below. The per-account
# switch (SASHA_WA_BRAIN = old | agent | agent_for:<ids>, with mode() / on()) is retired — there is no old path to switch back to.


GREETING = re.compile(r"(?i)^\s*(?:(?:hi|hello|hey|hiya|hola|buenas|ola|good\s+(?:morning|afternoon|evening))(?:\s+(?:there|sasha))?|sasha)\s*[!.,?]*\s*$")   # Sasha 246


def ours(payload: str) -> bool:
    """A button from THIS brain (not an in-flight one from the old flows, which finish there)."""
    return payload.startswith(("pick:", "say:", "yn:", "photo:", "keep:"))


# ── Sasha 238 · the agent's own WhatsApp state ──
# Sasha 252 · G3: it lives in its OWN key, st["agent"] — never in st["pending"], which holds only Sasha's own open question (a
# no-reply offer, a Gmail find, the deposit, their page sent, an invitation's question) or nothing. guest_wa_state keeps only its
# columns, so the store carries st["agent"] inside the pending column under "_agent" (pack_pending / unpack_state) — one place.
AGENT = "wa_agent"        # the pending kind it used to ride in (read once, then moved: migration on read)
STORED = "_agent"         # its key inside the pending column


def unpack_state(st: dict) -> dict:
    """Sasha 252 · the state as stored → st["pending"] (Sasha's own question, or None) + st["agent"] (the brain's own). An old
    {"kind": "wa_agent"} pending is moved to st["agent"] once, so a live conversation keeps what it had."""
    p = st.get("pending")
    if isinstance(p, dict):
        if p.get("kind") == AGENT:
            st["agent"] = {**{k: v for k, v in p.items() if k != "kind"}, **(st.get("agent") or {})}
            st["pending"] = None
        elif STORED in p:
            p = dict(p)
            st["agent"] = {**(p.pop(STORED) or {}), **(st.get("agent") or {})}
            st["pending"] = p if p.get("kind") else None
    return st


def pack_pending(st: dict):
    """Sasha 252 · what the pending column holds: Sasha's question, with the brain's own state alongside under "_agent"."""
    p, a = st.get("pending"), st.get("agent")
    if not a:
        return p
    return {**(p or {}), STORED: a}


def agent_state(st: dict) -> dict:
    """{photo_for, dormant, last_seen, photo, shots, asked} — a copy (st["agent"]; an old "wa_agent" pending is moved there)."""
    unpack_state(st)
    return dict(st.get("agent") or {})


def set_agent_state(st: dict, **kw) -> dict:
    a = {**agent_state(st), **kw}
    st["agent"] = {k: v for k, v in a.items() if v is not None}
    return st["agent"]


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
    if payload and not ours(payload):   # Sasha 249 · a button only an old flow understood (every button reaches her now): never a bare
        # "Yes" — that could read as the yes to HER read-back — and never empty (the model refuses an empty message)
        return f"[they tapped an old “{button_text or body or 'button'}” button from an earlier message — it no longer applies to anything]"
    return body


# ── the renderer: every render kind → WhatsApp (a test fails if a kind isn't here) ──────────────────────────────────────────

def _places(ev: dict, out) -> None:
    """Sasha 252 · things to do as the ONE place shape (agapi/venue_truth.text — the same as a tapped venue on WhatsApp)."""
    from agapi import venue_truth as VT
    for c in (ev.get("cards") or [])[:5]:
        out.text(VT.text(c.get("place") or c))
    if ev.get("unread"):
        out.text("Couldn't check on their own sites: " + ", ".join(ev["unread"][:4]))


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
    if not lines and ev.get("ask") and ev.get("choices"):   # Sasha 314 · the SHORT read-back: its one line IS the card, with Yes / No
        out.ask(str(ev["ask"])[:1000], [("Yes", "yn:yes"), ("No", "yn:no")])
        return
    if not lines:
        return
    if ev.get("status") in ("sent", "not_sent"):   # an outcome card, not a question
        out.text("\n".join(lines))
        return
    # Sasha 309 · ONE message: the request as it goes (AgAPI's lines), her one line, and its buttons — a tap or a typed yes sends it once
    body = "\n".join(lines) + (f"\n\n{ev['ask']}" if ev.get("ask") else "")
    out.ask(body[:1000], [("Yes", "yn:yes"), ("No", "yn:no")])


def _card(ev: dict, out, title: str) -> None:
    """notice / claim_status / accident / counter_card / my_cards / activities / plans: a few key lines + its /s2 page."""
    lines: List[str] = []
    k = ev.get("kind")
    if k == "notice":
        lines = [ev.get("title") or ""] + list(ev.get("lines") or [])[:4]
    elif k == "plans":
        for it in (ev.get("items") or [])[:8]:
            lines.append(" · ".join(x for x in (str(it.get("when") or "")[:16].replace("T", " "), it.get("title"), it.get("status")) if x))
        for u in ev.get("calendar_updates") or []:   # Sasha 312 · a cancelled / changed booking's calendar update
            lines.append(f"{u.get('venue') or 'A booking'}: {u.get('line')} {u.get('url')}")
        lines.append("Change or cancel: just say which.")
    elif k == "my_cards":
        lines = [f"{c.get('product')} · {c.get('network') or ''}".strip(" ·") for c in (ev.get("cards") or [])[:6]]
    elif k == "claim_status":
        c = ev.get("claim") or {}
        lines = [x for x in (c.get("state"), *(d.get("say") for d in (c.get("deadlines") or [])[:3])) if x]
    elif k == "counter_card":
        c = ev.get("card") or {}
        lines = [x for x in (c.get("card"), c.get("framing"), c.get("say")) if x]
    elif k == "accident":   # Sasha 238 · her words and, at the photos step, the shots to send here (never the raw step name)
        v = ev.get("view") or {}
        lines = [v.get("say") or ""] + ([f"Send here: {s.get('say')}" for s in (v.get("shots") or []) if not s.get("taken")][:6]
                                        if v.get("step") == "photos" else [])
    elif k == "subscriptions":   # Sasha 243 · CR 84's list as text: service · price · renews ("expected" when the email doesn't say)
        per = {"monthly": "a month", "yearly": "a year", "weekly": "a week", "quarterly": "a quarter"}
        for b in (ev.get("items") or [])[:12]:
            lines.append(" · ".join(x for x in (b.get("service"), " ".join(x for x in (b.get("price"), per.get(b.get("how_often") or "", "")) if x),
                                                 f"renews {b['renews']}" + (" (expected)" if b.get("expected") else "") if b.get("renews") else "",
                                                 b.get("not_yet") or "") if x))
        if not (ev.get("items") or []):   # Sasha 246 · none found: its own heading and the empty line — never a list's "say which"
            title = "No subscriptions found"
            lines = ["No subscription receipts found" + (f" — read from {ev['source']}." if ev.get("source") else ".")]
        elif ev.get("total"):
            lines.append(f"About {ev['total']} a month. To cancel one, say which.")
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
    if ev.get("update"):   # Sasha 312 · a booking cancelled / changed: the SAME event's update, as a file to open
        out.text(f"{ev.get('title') or 'Your calendar update'}\n{links.get('apple')}")
        return
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
    set_agent_state(st, photo_for={"kind": "loyalty" if ev.get("what") == "loyalty" else "passport", "at": now.isoformat()})


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
    "claim_status": lambda ev, out: _card(ev, out, "Your claim"), "accident": "accident",   # Sasha 238 · keeps the shots it asks for
    "counter_card": lambda ev, out: _card(ev, out, "At the counter"), "my_cards": lambda ev, out: _card(ev, out, "Your cards"),
    "activities": lambda ev, out: _places(ev, out),   # Sasha 252 · things to do are places: the one place text + link
    "subscriptions": lambda ev, out: _card(ev, out, "Your subscriptions"),   # Sasha 243
    "prepared": lambda ev, out: None if ev.get("on_phone") else out.text(   # Sasha 248 · already sent here when on_phone
        "\n".join([f"📝 {ev.get('venue')} — ready to copy:"] + [f"{f.get('label')}: {f.get('value')}" for f in ev.get("fields") or []]
                  + [f"Their page: {ev.get('url')}"])),
    "keep_capture": "keep_capture",          # sets st["photo_for"] (needs the state)
    "keep_handoff": _nothing,                # WhatsApp takes the photo directly
    "focus": _nothing, "trip": _nothing, "inline": _nothing,
    "kind_ask": _nothing,   # Sasha 297 · her one question before a vague search: /s2's page only (v0._discover via "page") — never on WhatsApp
    "discover": _nothing,   # Sasha 276 · never reaches WhatsApp: its brain searches via "wa" (its list cards) until Sasha 277 — tests.test_s276
}


def render(ev: dict, out, st: dict, now) -> None:
    k = ev.get("kind")
    f = KIND_MAP.get(k)
    if f is None:
        log.warning("[wa_agent] no WhatsApp drawing for render kind %s — dropped", k)
        return
    if f == "keep_capture":
        _keep_capture(ev, out, st, now)
    elif f == "accident":
        v = ev.get("view") or {}
        set_agent_state(st, shots=[x.get("shot") for x in (v.get("shots") or []) if x.get("shot") and not x.get("taken")]
                        if v.get("step") == "photos" else None)
        _card(ev, out, "The accident")
    else:
        f(ev, out)


CARD_KINDS = {"accident", "claim_status", "notice", "counter_card", "my_cards", "activities", "plans", "capabilities", "calendar", "subscriptions"}


def last_of_each_card(renders: List[dict]) -> List[dict]:
    """Sasha 238 · a card shown twice in one turn (the tool called again) is drawn once, as it stands at the end (found live:
    the accident card twice, the first one stale)."""
    last = {ev.get("kind"): i for i, ev in enumerate(renders) if ev.get("kind") in CARD_KINDS}
    return [ev for i, ev in enumerate(renders) if ev.get("kind") not in CARD_KINDS or last[ev.get("kind")] == i]


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

async def agent_turn(ch: dict, body: str, payload: str, st: dict, out, now, button_text: str = "", voice_in: bool = False) -> str:
    """One WhatsApp message → the agent (surface "wa") → `out`. Saves the history and her memory (awaited). Returns the reply.
    Sasha 238 · a photo's purpose tapped (photo:<kind>:<sid>) or a Keep save answered (keep:yes|no, or a typed yes/no while a
    scanned item waits) is handled first; after 6 hours away she opens with what she remembers (s2_memory — /s2 and WhatsApp
    share it); a voice note in gets a voice note back."""
    from agapi import s2_closing as CL, s2_keep as KEEP, s2_memory as MEM
    from app.agent import sasha as AG
    account, key = ch["account_id"], ch["wa_id_sha256"]
    if payload.startswith("photo:"):
        return await _photo_purpose(ch, payload, st, out, now)
    said_keep = await _keep_answer(account, body, payload, st, out, now)
    if said_keep is not None:
        return said_keep
    message = message_of(account, body, payload, button_text)
    if payload.startswith("pick:"):   # Sasha 248 · ONE PLACE CARD on WhatsApp: the tapped place's detail — as text + its link — first
        await place_detail(account, payload[5:], out)
    history = [m for m in (st.get("history") or []) if m.get("role") in ("user", "assistant")]
    a = agent_state(st)
    last = a.get("last_seen")
    away = (not history) or (last and _hours(now, last) > AWAY_HOURS)
    set_agent_state(st, last_seen=now.isoformat(), dormant=None)   # the next message wakes her
    if away:   # Sasha 238 · memory across visits AND screens: what she remembers from /s2 or WhatsApp
        try:
            rec = await MEM.recall(account, "wa:" + key)
        except Exception as e:
            log.info("[wa_agent] no recall: %s", type(e).__name__)
            rec = {}
        if rec.get("line") and not CL.closing(message):
            # Sasha 246 · HOW SHE STARTS: a greeting back gets only "Hey <first name>, what can I help you with?"; a request is
            # simply answered. What she remembers comes back as history (used when THEY refer to it) — never recited, and the
            # old cards are not sent again.
            history = [m for m in (rec.get("recent") or []) if m.get("role") in ("user", "assistant")][-12:] or history
            if GREETING.match(message or ""):
                out.text(rec["line"])
                _remember_history(st, body or message, rec["line"])
                return rec["line"]
    # a password, card or passport number never reaches the model — checked on THEIR words (a tap's composed message carries a
    # place_id, which is no secret: Sasha 249, found live — every card tap on WhatsApp was answered with the password warning)
    held = KEEP.chat_guard(body if payload else message)
    if held:
        out.text(held)
        return held
    history = KEEP.clean_history(history)
    lang = CL.closing(message) if history else None      # "thanks / bye" after a conversation → she rests
    if lang:
        bye = CL.line(lang)
        out.text(bye)
        set_agent_state(st, dormant=now.isoformat())   # resting until their next message: no re-asking, no nudges
        try:
            await MEM.closing(account, message, bye)
        except Exception as e:
            log.warning("[wa_agent] closing not kept: %s", type(e).__name__)
        _remember_history(st, body or message, bye)
        return bye
    over = await AG.over_budget(account)
    if over:
        out.text(over)
        return over
    text, renders, seen = "", [], {}
    from app.agent import voice as V
    steps = V.STEPS.get()   # Sasha 264 · item 1: _brain_turn's progress lines speak for the step running now
    async for ev in AG.turn_with_quiver(account, message, history, "wa:" + key, surface="wa"):
        if steps is not None:
            steps.see(ev)
        t = ev.get("type")
        if t == "text":
            text += str(ev.get("delta") or "")
        elif t == "replace":
            text = str(ev.get("text") or "")
        elif t == "render":
            renders.append(ev)
            if ev.get("kind") == "venues" and ev.get("preset"):
                seen.update(cards=(ev["preset"].get("cards") or []), ribbon=ev.get("ribbon"))
            if ev.get("kind") in ("focus", "venues") and ev.get("focus"):   # Sasha 239 · the place they chose (memory says it as theirs)
                seen["focus"] = ev["focus"]
        elif t == "error":
            text = str(ev.get("message") or text)
        elif t == "done":
            text = str(ev.get("text") or text)
            seen["calls"] = ev.get("tools") or []
    rb_ev = next((ev for ev in renders if ev.get("kind") == "read_back" and (ev.get("read_back") or (ev.get("ask") and ev.get("choices")))), None)
    shown = text
    if rb_ev:   # Sasha 309 · found live (DiverXO): an image card and "See the places" came with the read-back for a venue already chosen
        renders = [ev for ev in renders if ev.get("kind") != "venues"]
        if rb_ev.get("ask") and text.strip() == str(rb_ev["ask"]).strip():
            shown = ""   # her line is on the read-back's own message (one message, not two); her history keeps it
    for part in split(shown):
        out.text(part)
    if voice_in and text.strip():   # Sasha 238 · a voice note in → her answer as a voice note too (text in → text out only)
        url = await tts_note(text)
        if url:
            out.media("🔊", url)
    mark = len(out.items)
    for ev in last_of_each_card(renders):
        render(ev, out, st, now)
    if any(it[0] in ("ask", "list") for it in out.items[mark:]):
        # Sasha 252 · she asked her OWN question (a read-back's Yes/No, a list to pick from) after Sasha's open one: a bare typed
        # "yes" or "the first one" is hers now (guest_whatsapp.answers_sashas_question); a tap still answers its own question
        set_agent_state(st, asked=now.isoformat())
    _remember_history(st, body or message, text)
    try:   # awaited, in the turn — never fire-and-forget
        await MEM.remember(account, "wa:" + key, message[:4000], text, seen)
    except Exception as e:
        log.warning("[wa_agent] turn not kept in memory: %s", type(e).__name__)
    return text


async def place_detail(account: str, place_id: str, out, budget_s: float = 20.0) -> Optional[str]:
    """Sasha 248 · the same detail as /s2's and /next's sheet (agapi/venue_truth): what it is, hours, prices — each from its own
    site, or labelled Google's — rating, how it books, and its site. A read not back in time: the listing's, labelled."""
    import asyncio
    from agapi import venue_truth as VT, venues as VN
    card = VN.card_of(account, place_id)
    if not card:
        return None
    try:
        p = await asyncio.wait_for(VT.profile(card), timeout=budget_s)
    except Exception:
        p = VT.shape(card, VT.cached(card))
    t = VT.text(p)
    out.text(t)
    return t


def _remember_history(st: dict, user: str, reply: str) -> None:
    from .guest_whatsapp import HISTORY_KEEP
    st["history"] = ((st.get("history") or []) + [{"role": "user", "content": user}]
                     + ([{"role": "assistant", "content": reply}] if reply else []))[-HISTORY_KEEP:]


AWAY_HOURS = 6
PHOTO_FOR_MIN = 30
HOLD_MIN = 10
KEEP_KINDS = {"passport": "passport", "loyalty": "loyalty"}
_HELD_PHOTOS: Dict[str, dict] = {}   # MessageSid → {account, raw, mime, at}: a photo waiting for "What's this?" (memory, 10 min)


def _hours(now, iso: str) -> float:
    from datetime import datetime
    try:
        return (now - datetime.fromisoformat(iso)).total_seconds() / 3600
    except (TypeError, ValueError):
        return 1e9


def is_photo(p: Dict[str, str]) -> bool:
    try:
        n = int(p.get("NumMedia") or 0)
    except ValueError:
        n = 0
    return n > 0 and str(p.get("MediaContentType0") or "").startswith("image/")


async def _fetch(p: Dict[str, str]) -> Optional[bytes]:
    """Twilio's media, once, with our own credentials (the same retries as voice notes); never written to disk."""
    import asyncio, base64
    from .http_pool import request
    sid, token = os.getenv("TWILIO_ACCOUNT_SID", "").strip(), os.getenv("TWILIO_AUTH_TOKEN", "").strip()
    if not (sid and token and p.get("MediaUrl0")):
        return None
    auth = {"authorization": "Basic " + base64.b64encode(f"{sid}:{token}".encode()).decode()}
    try:
        r = await request("GET", p["MediaUrl0"], timeout=20.0, follow_redirects=True, headers=auth)
        for wait in (1.0, 1.5, 2.5):
            if r.status_code != 404:
                break
            await asyncio.sleep(wait)
            r = await request("GET", p["MediaUrl0"], timeout=20.0, follow_redirects=True, headers=auth)
        return r.content if r.status_code == 200 and r.content else None
    except Exception as e:
        log.warning("[wa_agent] photo not fetched: %s", type(e).__name__)
        return None


FETCH = _fetch   # tests replace it

_PURPOSE = [("passport", r"passport|pasaporte|photo page|dni|id card"), ("loyalty", r"loyalty|frequent|avios|iberia plus|bonvoy|miles|wallet|membership"),
            ("statement", r"statement|receipt|bank|extracto|subscriptions?|recibo"), ("damage", r"damage|dent|scratch|accident|crash|golpe|da[nñ]o")]


def purpose_of(caption: str) -> Optional[str]:
    t = (caption or "").lower()
    return next((k for k, rx in _PURPOSE if re.search(rx, t)), None)


async def photo_intake(ch: dict, p: Dict[str, str], st: dict, out, now) -> str:
    """Sasha 238 · EU 232 §1.4: a photo on WhatsApp → the SAME handlers as /s2 (no new reading code). Its purpose, in order: the
    one she asked for (keep_capture, within 30 min), the caption, else one question [Passport] [Loyalty card] [Something else]."""
    account = ch["account_id"]
    raw = await FETCH(p)
    mime = str(p.get("MediaContentType0") or "image/jpeg").split(";")[0]
    if not raw:
        out.text("I couldn't open that photo — could you send it again?")
        return "photo not fetched"
    want = agent_state(st).get("photo_for") or {}
    kind = want.get("kind") if want and _hours(now, want.get("at") or "") * 60 <= PHOTO_FOR_MIN else None
    kind = kind or purpose_of(p.get("Body") or "")
    if not kind:
        sid = str(p.get("MessageSid") or "") or __import__("secrets").token_hex(8)
        _sweep(now)
        _HELD_PHOTOS[sid] = {"account": account, "raw": raw, "mime": mime, "at": now}
        out.ask("What's this?", [("Passport", f"photo:passport:{sid}"), ("Loyalty card", f"photo:loyalty:{sid}"),
                                 ("Something else", f"photo:other:{sid}")])
        return "asked what it is"
    return await _handle_photo(ch, kind, raw, mime, st, out, now)


def _sweep(now) -> None:
    for k in [k for k, v in _HELD_PHOTOS.items() if (now - v["at"]).total_seconds() > HOLD_MIN * 60]:
        _HELD_PHOTOS.pop(k, None)


async def _photo_purpose(ch: dict, payload: str, st: dict, out, now) -> str:
    parts = payload.split(":", 2)
    kind, sid = (parts[1], parts[2]) if len(parts) == 3 else ("", "")
    _sweep(now)
    held = _HELD_PHOTOS.pop(sid, None)
    if not held or held["account"] != ch["account_id"]:
        out.text("That photo has gone from my memory — could you send it again?")
        return "photo expired"
    if kind == "other":
        out.text("Got it. For now I can read a passport, a loyalty card, a bank statement or photos of damage — tell me which, "
                 "or ask me something else.")
        return "other"
    return await _handle_photo(ch, kind, held["raw"], held["mime"], st, out, now)


async def _handle_photo(ch: dict, kind: str, raw: bytes, mime: str, st: dict, out, now) -> str:
    account = ch["account_id"]
    set_agent_state(st, photo_for=None)
    if kind in KEEP_KINDS:   # the Keep's own reader (keep_scan.scan — what /s2's picker posts to): masked, saved only on "yes"
        from agapi import keep_scan as SCAN
        try:
            got = await SCAN.scan(account, KEEP_KINDS[kind], raw, mime)
        except SCAN.ScanRefused as e:
            out.text(e.message)
            return e.rule
        finally:
            raw = b""
        set_agent_state(st, photo={"token": got["token"], "masked": got["masked"], "at": now.isoformat()})
        out.ask("\n".join(got["shown"]) + "\nSave it to your Keep? It's kept encrypted; the photo isn't kept.",
                [("Yes, save it", "keep:yes"), ("No", "keep:no")])
        return got["masked"]
    if kind == "statement":   # the /s2 statement handler's own function (subscriptions)
        from agapi import s2_subscriptions as SUBS
        try:
            ref = SUBS.keep_statement(account, raw, mime)
        except ValueError as e:
            out.text(str(e))
            return "statement refused"
        return await agent_turn(ch, f"[they sent a photo of a statement — statement_ref {ref}: find their subscriptions with it]", "", st, out, now)
    if kind == "damage":      # the /s2 accident card's photo function (sealed, hashed evidence at AgAPI), as its NEXT shot
        import base64
        from agapi import s2_fine_print as FP
        shots = list(agent_state(st).get("shots") or [])
        if not shots:   # the case takes photos at its photos step (found live: a photo sent earlier was refused)
            out.text("I'll take the photos at the photo step of the accident — tell me what happened (or that you're ready) and I'll "
                     "ask for each one.")
            return "not at the photos step"
        r = await FP.accident_photo(account, shots[0], mime, base64.b64encode(raw).decode())
        if not r.get("ok"):
            out.text(((r.get("error") or {}).get("message") or "That photo wasn't saved to the case.") + " Could you send it again?")
            return "photo refused"
        set_agent_state(st, shots=shots[1:] or None)
        return await agent_turn(ch, f"[they sent the accident photo '{shots[0]}' — saved to the case as evidence"
                                    f"{'; still to send: ' + ', '.join(shots[1:]) if shots[1:] else '; that was the last one'}]", "", st, out, now)
    out.text("I can read a passport, a loyalty card, a bank statement or photos of damage — which is this?")
    return "unknown"


async def _keep_answer(account: str, body: str, payload: str, st: dict, out, now) -> Optional[str]:
    """A scanned item waits: [Yes, save it] / a typed yes saves it (keep_scan.confirm); no discards it. Else None."""
    a = agent_state(st)
    ph = a.get("photo") or {}
    if not ph:
        return None
    if _hours(now, ph.get("at") or "") * 60 > HOLD_MIN:
        set_agent_state(st, photo=None)
        return None
    from agapi.v0 import explicit_yes
    yes = payload == "keep:yes" or (not payload and explicit_yes(body))
    no = payload == "keep:no" or (not payload and re.fullmatch(r"\s*(no|nope|don'?t|cancel)\b.*", body or "", re.I))
    if not (yes or no):
        return None
    set_agent_state(st, photo=None)
    if no:
        out.text("OK — not saved, and the photo isn't kept.")
        return "not saved"
    from agapi import keep_scan as SCAN
    try:
        got = await SCAN.confirm(account, ph["token"])
    except SCAN.ScanRefused as e:
        out.text(e.message)
        return e.rule
    out.text(f"Saved to your Keep: {got['item']}. I'll only ever see that mask.")
    return got["item"]


# ── Sasha 238 · voice out: her answer as an mp3 at a short-lived, unguessable URL (memory only, 1 hour) ─────────────────────
NOTE_TTL_S = 3600
_NOTES: Dict[str, dict] = {}


async def _tts(text: str) -> Optional[bytes]:
    from app.api.voice_conductor import text_to_speech
    return await text_to_speech(text)


TTS = _tts   # tests replace it


async def tts_note(text: str) -> Optional[str]:
    import secrets, time
    try:
        audio = await TTS(text[:1500])
    except Exception as e:
        log.warning("[wa_agent] no voice note: %s", type(e).__name__)
        return None
    if not audio:
        return None
    now = time.time()
    for k in [k for k, v in _NOTES.items() if now - v["at"] > NOTE_TTL_S]:
        _NOTES.pop(k, None)
    token = secrets.token_urlsafe(24)
    _NOTES[token] = {"audio": audio, "at": now}
    from .form_rung import public_base
    return f"{public_base()}/api/agent/voice/note/{token}.mp3"


def note_audio(token: str) -> Optional[bytes]:
    import time
    n = _NOTES.get(token)
    return n["audio"] if n and time.time() - n["at"] <= NOTE_TTL_S else None


__all__ = ["ours", "message_of", "render", "KIND_MAP", "agent_turn", "split", "photo_intake", "tts_note", "note_audio",
           "agent_state", "set_agent_state", "unpack_state", "pack_pending", "purpose_of", "is_photo"]
