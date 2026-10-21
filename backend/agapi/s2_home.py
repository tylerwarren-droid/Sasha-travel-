"""Sasha 225 · /s2's front-of-house: who she's greeting, what she can do (said honestly), and what she can't do YET.

    GET /api/agent/me           → {"name": their first name, or null}   (for "Hi {name}, I'm Sasha")
    what_i_can_do (tool)        → the capability card, grouped Book · Plan · Money · Messages · Your documents — only what /s2
                                  really does today (each line maps to a tool in S2_TOOLS; a test holds that)
    note_not_yet (tool)         → what she TRIED and couldn't do (268: refused unless a tool tried this turn): logged, MASKED (digits,
                                  emails, phone numbers removed), for the founder; she says what she tried, found and CAN do
    GET /api/agent/not-yet      → the founder's list (founder only)

The log: s2_not_yet (sql/038_not_yet.sql) once applied; until then this process's memory and Railway's log ([s2-not-yet]).
"""
from __future__ import annotations

import hashlib
import logging
import re
import uuid
from collections import deque
from datetime import datetime, timezone
from typing import Dict, List, Optional

log = logging.getLogger("agapi.s2_home")

# what /s2 does today — every line backed by a tool in app/agent/s2.py S2_TOOLS (tests/test_s2_225.py checks the mapping)
# Sasha 249 · ONE CAPABILITY LIST (EU 245 §1.5 / T10): everything that says what she can do is generated from this list —
#   SAY (what_i_can_do's line) · prose()   (the S2 and S1 system prompts: app/agent/s2.py) · CHIPS (/s2 and /next, via the
#   generated frontend/lib/capabilities.generated.mjs) · wa_help / wa_linked / wa_onboard (WhatsApp, when the one brain answers).
#   Each group's "say" is its phrase in SAY; its optional "chip" is a request someone can tap, with the tool that answers it;
#   "more_chips" are further taps for the same group (Tyler, 12 Oct: a spa and a table tonight on both /s2 and /next).
CAPABILITIES: List[Dict] = [
    {"group": "Book", "say": "book tables, spas and trips", "chip": ("Book dinner", "search_venues"),
     "more_chips": [("A table for two tonight", "search_venues"), ("A spa on Saturday", "search_venues")],
     "items": [("A table at a restaurant", "search_venues"), ("Any place or service — a spa, a dog walker, a plumber…", "search_venues"),
               ("A flight or a hotel on its own — or a whole trip", "book")]},   # Sasha 280 · no packages: each on its own
    {"group": "Plan", "say": "plan a trip day by day", "chip": ("Plan a weekend", "propose_trip"),
     "items": [("A weekend or a longer trip, day by day", "propose_trip"),
               ("Swap a hotel or a flight in it", "swap_stay"),
               ("Add a place to a day of your trip, to book later", "add_to_trip"),   # Sasha 253 · G10
               ("Whether you've time to drive or fly somewhere between two times", "time_between")]},   # Sasha 253 · G9
    {"group": "Money", "say": "give you the total before you say yes",
     "items": [("The total before you say yes", "get_total"),
               ("Pay on this screen — Apple Pay or Google Pay", "book")]},
    {"group": "Messages", "say": "email people for you and put bookings in your calendar",
     "items": [("Email someone for you, after you've approved it", "send_email"),
               ("Put a booking in your calendar", "add_to_calendar"),
               ("Tell you everything I've done today", "get_activity")]},
    {"group": "Your documents", "say": "keep your passport safe", "chip": ("Add my passport", "keep_add"),
     "items": [("Keep your passport and loyalty cards — I only ever see a mask", "keep_add"),
               ("Keep your booking name and mobile — asked once", "save_contact")]},   # Sasha 253 · G5
    # Sasha 236 · every tool she has gets its line (EU 232 §2.1): each still backed by a tool /s2 has (tests/test_s2_225.py)
    {"group": "Your bookings", "say": "keep track of your bookings", "chip": ("What's coming up?", "my_plans"),
     "items": [("Everything you've booked, in one place", "my_plans"),
               ("Change or cancel a booking", "change_booking"),
               ("Tell a restaurant or spa you're running late", "running_late"),
               ("Ask your hotel for an upgrade or a late check-out", "hotel_request"),
               ("File a venue's confirmation you forward or paste to me", "file_confirmation"),   # Sasha 253 · G1
               ("Save something for later, not booked", "save_for_later")]},   # Sasha 253 · G13
    {"group": "Trips", "say": "sort out what you need to enter a country",
     "items": [("What you need to enter a country — and the form, prepared for you to submit", "entry_documents")]},
    {"group": "Cards & cover", "say": "tell you which card covers what",
     "items": [("Which of your cards to pay with, and what it covers", "which_card"),
               ("Whether your card covers a rental car", "rental_cover")]},
    {"group": "If something goes wrong", "say": "help when something goes wrong",
     "items": [("A car accident, step by step", "accident"),
               ("A claim on your card's insurance, read back before it's filed", "file_claim")]},
    {"group": "Money back", "say": "get money back for flights and bags",
     "items": [("A delayed or cancelled flight", "flight_money_back"),
               ("A late, lost or damaged bag", "bag_money_back")]},
    {"group": "Subscriptions", "say": "find and cancel subscriptions", "chip": ("What am I subscribed to?", "find_subscriptions"),
     "items": [("Find your subscriptions on a statement", "find_subscriptions"),
               ("Cancel one — by their own cancel page or an email, after your yes", "cancel_subscription")]},
]


def _and(parts: List[str]) -> str:
    return parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + ", and " + parts[-1]


# Sasha 249 · generated (it was a second, hand-written list beside CAPABILITIES)
SAY = "I can " + _and([g["say"] for g in CAPABILITIES]) + "."
# Sasha 249 · the chips on /s2 and /next (S1 = S2): "what can you do?" first (what_i_can_do), then each group's own request
ASK_CHIP = ("What can you do?", "what_i_can_do")
_CHIP_PAIRS = [c for g in CAPABILITIES if g.get("chip") for c in [g["chip"], *g.get("more_chips", [])]]
CHIPS: List[str] = [ASK_CHIP[0]] + [c[0] for c in _CHIP_PAIRS]
CHIP_TOOLS: Dict[str, str] = {ASK_CHIP[0]: ASK_CHIP[1], **{c[0]: c[1] for c in _CHIP_PAIRS}}


def prose() -> str:
    """Sasha 249 · the system prompts' capability section (S2's, and S1's with parity on) — the card's own groups, in a line each."""
    lines = [f"- **{g['group']}:** " + "; ".join(i for i, _ in g["items"]) + "." for g in CAPABILITIES]
    return ("## What she can do (the same list as `what_i_can_do`'s card; nothing else)\n\n" + "\n".join(lines) + "\n")


# Sasha 249 · WhatsApp's words when the one brain answers (booking_signer/wa_agent.on): from the same list. The old brain keeps its
# own HELP / LINKED / ONBOARD (booking_signer/guest_whatsapp.py) — they describe what IT does, and go with it.
def wa_help() -> str:
    return f"{SAY} Tell me what you need in one message — e.g. “{CHIPS[1]}” or “{CHIPS[-1]}”."


def wa_linked() -> str:
    return f"Linked. {SAY} Just ask — e.g. “{CHIPS[1]}”."


def wa_onboard() -> str:
    """With a {web} placeholder, as guest_whatsapp.ONBOARD. Sasha 253 · item 5 (Tyler, mailbox 807): an unlinked number gets ONE
    short line telling them how to link — never the old flow, never an automatic guest account."""
    return "Hi, I'm Sasha by Kanoe. To use me on WhatsApp, link this number once at {web} — it takes a minute."


def frontend_module() -> str:
    """Sasha 249 · frontend/lib/capabilities.generated.mjs, exactly (tests/test_s249_status_keep_caps.py holds the file to it;
    regenerate with: cd backend && python -m scripts.capabilities_out)."""
    import json
    groups = [{"group": g["group"], "items": [i for i, _ in g["items"]]} for g in CAPABILITIES]
    return ("// GENERATED from backend/agapi/s2_home.py CAPABILITIES (Sasha 249 · one capability list) — do not edit by hand.\n"
            "// Regenerate: cd backend && python -m scripts.capabilities_out\n"
            f"export const CHIPS = {json.dumps(CHIPS, ensure_ascii=False)}\n"
            f"export const SAY = {json.dumps(SAY, ensure_ascii=False)}\n"
            f"export const GROUPS = {json.dumps(groups, ensure_ascii=False)}\n")

_MEM: deque = deque(maxlen=500)   # until 038 is applied (and a copy for the founder's view)
RUN = None                        # tests: None → memory only


def mask(text: str) -> str:
    """What was asked, with anything personal taken out: emails, phone numbers and every run of digits."""
    t = re.sub(r"[\w.+-]+@[\w-]+\.[\w.]+", "[email]", str(text or ""))
    t = re.sub(r"\+?\d[\d\s().-]{5,}\d", "[number]", t)
    t = re.sub(r"\d", "•", t)
    return re.sub(r"\s+", " ", t).strip()[:200]


def _who(account: Optional[str]) -> str:
    return "acct:" + hashlib.sha256(str(account or "").encode()).hexdigest()[:10]


async def _run():
    if RUN is not None:
        return RUN
    from booking_signer import plan_store as PS
    return PS._run()


async def note(account: str, asked: str) -> dict:
    row = {"id": str(uuid.uuid4()), "who": _who(account), "asked": mask(asked), "at": datetime.now(timezone.utc)}
    _MEM.append(row)
    log.warning("[s2-not-yet] %s", row["asked"])   # masked: never a number, an address or an email
    run = await _run()
    if run is not None:
        try:
            await run(lambda c: c.execute("insert into s2_not_yet (id, who, asked, at) values ($1, $2, $3, $4)",
                                          uuid.UUID(row["id"]), row["who"], row["asked"], row["at"]))
        except Exception as e:   # 038 not applied yet: memory + the log hold it
            log.info("[s2-not-yet] not stored (%s) — kept in memory", type(e).__name__)
    return row


# ── tools ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────

async def what_i_can_do(ctx, a: dict) -> dict:
    return {"say": SAY, "groups": [{"group": g["group"], "items": [i for i, _ in g["items"]]} for g in CAPABILITIES],
            "how": "Say SAY in one or two sentences; the card shows the groups. Never add anything that isn't on it."}


async def remember_name(ctx, a: dict) -> dict:
    """Sasha 246 · what to call them (asked once on their first visit): kept with her memory, said in every opening after."""
    from agapi import s2_memory as MEM
    n = await MEM.set_name(ctx.account, str(a.get("name") or ""))
    return {"saved": bool(n), "name": n, "how": "Thank them by that name in a few words, then help with whatever they asked."
            if n else "That didn't look like a name — ask again, briefly."}


# Sasha 268 · item 7 (rows 954/955): "I can't" only AFTER the engine actually tried. A call with no attempt this turn is refused —
# nothing noted — and she is told to try first. The tools that count as a try: anything that reached for the business.
TRIED = ("search_venues", "read_booking_route", "hold_venue", "book_venue", "send_email", "send_whatsapp", "suggest_activities")


async def note_not_yet(ctx, a: dict) -> dict:
    tried = [c["tool"] for c in (getattr(ctx, "calls", None) or []) if c.get("tool") in TRIED]
    if not tried:
        return {"noted": False, "how": "Not yet — you haven't tried. Say \"Let me see what I can do\" and try it: search_venues for it "
                                      "where they are (ask the city once if you don't know it), then the cards and how they take bookings."}
    await note(ctx.account, str(a.get("asked") or ""))
    return {"noted": True, "tried": tried, "say": "Say what you tried and what you found, then two or three things from what_i_can_do "
                                                  "closest to what they wanted. Never pretend it worked."}


def tools() -> List[dict]:
    from agapi.v0 import _t
    return [
        _t("what_i_can_do", "Pacioli", what_i_can_do, "What Sasha can do on this screen, grouped (Book · Plan · Money · Messages · Your "
           "documents) — for 'what can you do?'. Shows a card; say its SAY line, briefly.", {}, [],
           {"type": "object", "properties": {"groups": {"type": "array"}}}, []),
        _t("note_not_yet", "Pacioli", note_not_yet, "Only AFTER you actually tried (search_venues or "
           "the business's own route) and it failed: note it for the founder — what they asked, in a few words — then say what you "
           "tried, what you found and what you CAN do. Never your first answer.",
           {"asked": {"type": "string", "maxLength": 300}}, ["asked"], {"type": "object", "properties": {"noted": {"type": "boolean"}}}, []),
        _t("remember_name", "Pacioli", remember_name, "When they tell you what to call them (their first name — e.g. after you asked "
           "\"What should I call you?\"), save it; you'll greet them by it from then on.",
           {"name": {"type": "string", "maxLength": 60}}, ["name"], {"type": "object", "properties": {"saved": {"type": "boolean"}}}, []),   # Sasha 246
        # Sasha 253 · the booking contact (G5): asked once, saved on the one person record (/api/booking/contact), with the consent
        _t("save_contact", "Pacioli", _VN().save_contact, _VN().SAVE_CONTACT_DESC,
           {"name": {"type": "string", "maxLength": 80, "description": "their name as they said it"},
            "mobile": {"type": "string", "description": "the mobile as they said it, ideally with its country code"},
            "this_number": {"type": "boolean", "description": "WhatsApp: they said 'this number'"},
            "country": {"type": "string", "description": "ISO-2 of the venue, if the mobile has no country code"}}, [],
           {"type": "object", "properties": {"saved": {"type": "boolean"}}},
           ["not_their_words", "name_missing", "mobile_missing", "mobile_unclear", "not_saved", "store_unreachable"]),
    ]


def _VN():
    from agapi import venues
    return venues


# ── routes (mounted under the agent router → /api/agent/…) ───────────────────────────────────────────────────────────────────

from fastapi import APIRouter, Request                       # noqa: E402
from fastapi.responses import JSONResponse                   # noqa: E402

router = APIRouter()


@router.get("/me")
async def me(request: Request):
    from app.services.chat_account import chat_account, signed_in
    account = await chat_account(request)
    if not signed_in(account):
        return JSONResponse({"ok": False, "rule": "sign_in"}, status_code=403)
    name = None
    try:
        from booking_signer import contacts as CT
        row = await CT.STORE.get(account) if CT.STORE is not None else None
        name = (str((row or {}).get("name") or "").strip().split() or [None])[0]
    except Exception as e:
        log.info("[s2-home] no name: %s", type(e).__name__)
    return {"ok": True, "name": name}


@router.get("/not-yet")
async def not_yet_list(request: Request):
    from app.services.chat_account import chat_account
    from app.services.accounts import is_founder   # Sasha 249 · the one founder decision
    if not is_founder(await chat_account(request)):
        return JSONResponse({"ok": False, "rule": "founder_only"}, status_code=403)
    rows: List[dict] = []
    run = await _run()
    if run is not None:
        try:
            rows = [dict(r) for r in await run(lambda c: c.fetch("select who, asked, at from s2_not_yet order by at desc limit 200"))]
        except Exception:
            rows = []
    if not rows:
        rows = [{k: r[k] for k in ("who", "asked", "at")} for r in reversed(_MEM)]
    return {"ok": True, "items": [{**r, "at": r["at"].isoformat() if hasattr(r["at"], "isoformat") else r["at"]} for r in rows]}


__all__ = ["CAPABILITIES", "SAY", "CHIPS", "CHIP_TOOLS", "prose", "wa_help", "wa_linked", "wa_onboard", "frontend_module",   # Sasha 249
           "mask", "note", "tools", "router", "what_i_can_do", "note_not_yet"]
