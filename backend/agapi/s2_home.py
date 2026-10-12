"""Sasha 225 · /s2's front-of-house: who she's greeting, what she can do (said honestly), and what she can't do YET.

    GET /api/agent/me           → {"name": their first name, or null}   (for "Hi {name}, I'm Sasha")
    what_i_can_do (tool)        → the capability card, grouped Book · Plan · Money · Messages · Your documents — only what /s2
                                  really does today (each line maps to a tool in S2_TOOLS; a test holds that)
    note_not_yet (tool)         → anything she can't do: logged, MASKED (digits, emails, phone numbers removed), for the founder;
                                  she says "I can't do that yet, but I've noted it — here's what I can do…", never a pretend attempt
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
CAPABILITIES: List[Dict] = [
    {"group": "Book", "items": [("A table at a restaurant", "search_venues"), ("A spa, salon or other place", "search_venues"),
                                ("Flights and hotels for a trip", "book")]},
    {"group": "Plan", "items": [("A weekend or a longer trip, day by day", "propose_trip"),
                                ("Swap a hotel or a flight in it", "swap_stay")]},
    {"group": "Money", "items": [("The total before you say yes", "get_total"),
                                 ("Pay on this screen — Apple Pay or Google Pay", "book")]},
    {"group": "Messages", "items": [("Email someone for you, after you've approved it", "send_email"),
                                    ("Put a booking in your calendar", "add_to_calendar"),
                                    ("Tell you everything I've done today", "get_activity")]},
    {"group": "Your documents", "items": [("Keep your passport and loyalty cards — I only ever see a mask", "keep_add")]},
    # Sasha 236 · every tool she has gets its line (EU 232 §2.1): each still backed by a tool /s2 has (tests/test_s2_225.py)
    {"group": "Your bookings", "items": [("Everything you've booked, in one place", "my_plans"),
                                         ("Change or cancel a booking", "change_booking"),
                                         ("Tell a restaurant or spa you're running late", "running_late"),
                                         ("Ask your hotel for an upgrade or a late check-out", "hotel_request")]},
    {"group": "Trips", "items": [("What you need to enter a country — and the form, prepared for you to submit", "entry_documents")]},
    {"group": "Cards & cover", "items": [("Which of your cards to pay with, and what it covers", "which_card"),
                                         ("Whether your card covers a rental car", "rental_cover")]},
    {"group": "If something goes wrong", "items": [("A car accident, step by step", "accident"),
                                                   ("A claim on your card's insurance, read back before it's filed", "file_claim")]},
    {"group": "Money back", "items": [("A delayed or cancelled flight", "flight_money_back"),
                                      ("A late, lost or damaged bag", "bag_money_back")]},
    {"group": "Subscriptions", "items": [("Find your subscriptions on a statement", "find_subscriptions"),
                                         ("Cancel one — by their own cancel page or an email, after your yes", "cancel_subscription")]},
]
SAY = ("I can book tables and trips, keep track of your bookings, sort out what you need to enter a country, get money back for "
       "flights and bags, help when something goes wrong, find and cancel subscriptions, email people for you, and keep your passport safe.")

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


async def note_not_yet(ctx, a: dict) -> dict:
    await note(ctx.account, str(a.get("asked") or ""))
    return {"noted": True, "say": "Say: \"I can't do that yet, but I've noted it — here's what I can do…\" and name two or three "
                                  "things from what_i_can_do that are closest to what they wanted. Never pretend to try it."}


def tools() -> List[dict]:
    from agapi.v0 import _t
    return [
        _t("what_i_can_do", "Pacioli", what_i_can_do, "What Sasha can do on this screen, grouped (Book · Plan · Money · Messages · Your "
           "documents) — for 'what can you do?'. Shows a card; say its SAY line, briefly.", {}, [],
           {"type": "object", "properties": {"groups": {"type": "array"}}}, []),
        _t("note_not_yet", "Pacioli", note_not_yet, "Anything they ask that you can't do (no tool does it): note it for the founder — "
           "pass what they asked in a few words — then say you can't do it YET and what you can do instead. Never pretend to try.",
           {"asked": {"type": "string", "maxLength": 300}}, ["asked"], {"type": "object", "properties": {"noted": {"type": "boolean"}}}, []),
        _t("remember_name", "Pacioli", remember_name, "When they tell you what to call them (their first name — e.g. after you asked "
           "\"What should I call you?\"), save it; you'll greet them by it from then on.",
           {"name": {"type": "string", "maxLength": 60}}, ["name"], {"type": "object", "properties": {"saved": {"type": "boolean"}}}, []),   # Sasha 246
    ]


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


__all__ = ["CAPABILITIES", "SAY", "mask", "note", "tools", "router", "what_i_can_do", "note_not_yet"]
