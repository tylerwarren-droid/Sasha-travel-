"""Sasha 231 · MEMORY ACROSS VISITS on /s2 — per account: the recent conversation, a short running summary, and anything unfinished
(a hold awaiting their yes, a question she asked). On return: "Welcome back — we were looking at <thing>. Want to carry on?"

Before 231 the conversation lived only in the open tab (S2App's history, sent back each turn): closing /s2 lost it. The holds
(_HELD in venues / v0 / s2_tools / s2_whatsapp / s2_manage) lived in the process for 15 minutes, with nothing on the page to say so.

  remember(account, session, said, reply, seen)   after each /s2 turn (awaited in the turn's stream — never fire-and-forget)
  closing(account)                                "thanks / bye": nothing to carry on unless a hold still waits for a yes
  recall(account, session)                        on return: {line, recent, screen, pending} — and the cards she showed are on
                                                  screen again for this new session (she may name them)
MASKS ONLY: every line is read through the chat's own guards (vault + Keep) before it's kept — a passport, card or ID value is never
stored; what the Keep shows is its mask ("Passport ES ••••456"). Photos are not kept on the cards (no photo fetch on return).
Stored in s2_memory (booking_signer/sql/041_s2_memory.sql); until it's applied, this process's memory (a restart forgets;
nothing fails). Kept OFFER_FOR (24 h) for the "carry on" line; replaced by the next visit's turns.
"""
from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

log = logging.getLogger("agapi.s2_memory")
NOW = lambda: datetime.now(timezone.utc)   # noqa: E731
KEEP = 20                                  # messages kept (user + Sasha)
LINE_MAX = 700
OFFER_FOR = timedelta(hours=24)
SUMMARY_MAX = 6
_MEM: Dict[str, dict] = {}                 # account → memory, until 041 is applied
RUN = "auto"                               # tests: None → memory
REMOVED = "[removed]"


def _run():
    if RUN != "auto":
        return RUN
    from booking_signer import plan_store as PS
    return PS._run()


def masked(text: str) -> str:
    """A line as it may be kept: a secret (card, password, passport/ID number) never — the whole line goes."""
    t = str(text or "")[:LINE_MAX]
    from booking_signer.vault import guard as G
    if G.looks_like_secret(t):
        return REMOVED
    try:
        from agapi import s2_keep as K
        if K.guard(t):
            return REMOVED
    except Exception:
        pass
    return t


def _thing_of_ribbon(ribbon: str) -> str:
    """'5 Indian restaurants in Madrid · tonight 21:00' → 'Indian restaurants in Madrid, tonight 21:00'."""
    t = re.sub(r"^\d+\s+", "", str(ribbon or "").strip())
    return re.sub(r"\s*·\s*", ", ", t).strip(" ,")


def _question(reply: str) -> Optional[str]:
    parts = [p.strip() for p in re.split(r"(?<=[.!?])\s+", str(reply or "").strip()) if p.strip()]
    return parts[-1][:200] if parts and parts[-1].endswith("?") else None


def _card(c: dict) -> dict:
    return {k: c[k] for k in ("place_id", "name", "rating", "rating_count", "area", "address", "type", "open_at") if c.get(k) is not None}


def fold(mem: Optional[dict], said: str, reply: str, seen: dict) -> dict:
    """The memory after one turn. `seen` is what the turn showed: {"ribbon", "cards", "focus", "calls": [{tool, ok, status}]}."""
    m = {"recent": [], "summary": [], "thing": None, "pending": None, "screen": None, **(mem or {})}
    m["recent"] = (list(m["recent"]) + [{"role": "user", "content": masked(said)}, {"role": "assistant", "content": masked(reply)}])[-KEEP:]
    calls = seen.get("calls") or []
    status = {c.get("tool"): c.get("status") for c in calls if c.get("ok")}
    ran = {c.get("tool") for c in calls if c.get("ok")}
    if seen.get("cards"):
        m["screen"] = {"cards": [_card(c) for c in seen["cards"] if c.get("place_id")][:8], "ribbon": seen.get("ribbon"), "focus": seen.get("focus")}
        for x in m["recent"]:
            x.pop("cards", None)
        m["recent"][-1]["cards"] = True   # Sasha 233 · the line that SHOWED them — restored there, not under the last line
    topic = None
    if "search_venues" in ran and seen.get("ribbon"):
        topic = _thing_of_ribbon(seen["ribbon"])
        m["thing"], m["pending"] = topic, None
    held = next((t for t, s in status.items() if s == "awaiting_yes"), None)
    if held:
        what = (seen.get("held") or (_thing_of_ribbon(seen["ribbon"]) if held == "hold_venue" and seen.get("ribbon") else None)
                or m.get("thing") or "your booking")
        m["pending"] = {"kind": "hold", "tool": held, "what": what, "at": NOW().isoformat()}
        m["thing"] = topic = f"{what} — it's ready, waiting for your yes" if held == "hold_venue" else what
    if any(status.get(t) in ("confirmed", "requested", "sent", "booked") for t in ("book_venue", "book", "send_email", "send_whatsapp")) \
            or re.search(r"✅\s*Booked", reply or ""):
        topic = topic or "done: " + (m.get("thing") or "your booking")
        m["thing"], m["pending"] = None, None
    q = _question(reply)
    if (m.get("pending") or {}).get("kind") == "question":
        m["pending"] = None   # a question is only unfinished until her next reply
    if q and not m.get("pending"):
        m["pending"] = {"kind": "question", "asked": masked(q), "at": NOW().isoformat()}
    if topic and masked(topic) != REMOVED:
        m["summary"] = ([s for s in m["summary"] if s != topic] + [topic])[-SUMMARY_MAX:]
    m["updated_at"] = NOW().isoformat()
    return m


async def _load(account: str) -> Optional[dict]:
    run = _run()
    if run is not None and account not in _MEM:
        try:
            row = await run(lambda c: c.fetchrow("select memory from s2_memory where account_id = $1", uuid.UUID(account)))
            if row:
                v = row["memory"]
                return json.loads(v) if isinstance(v, str) else dict(v)
            return None
        except Exception as e:
            log.info("[memory] not read (%s) — memory", type(e).__name__)
    return _MEM.get(account)


async def _save(account: str, m: dict) -> None:
    run = _run()
    if run is not None and account not in _MEM:
        try:
            await run(lambda c: c.execute(
                "insert into s2_memory (account_id, memory, updated_at) values ($1, $2::jsonb, now()) "
                "on conflict (account_id) do update set memory = excluded.memory, updated_at = now()",
                uuid.UUID(account), json.dumps(m, default=str)))
            return
        except Exception as e:
            log.info("[memory] not stored (%s) — kept in memory", type(e).__name__)
    _MEM[account] = m


async def remember(account: str, session: Optional[str], said: str, reply: str, seen: dict) -> dict:
    if any(c.get("tool") == "hold_venue" and c.get("status") == "awaiting_yes" for c in seen.get("calls") or []):
        from agapi import venues as VN
        h = VN._HELD.get(account) or {}
        if h.get("venue"):   # the place she read back, by its name
            seen = {**seen, "held": str(h["venue"])[:120]}
    m = fold(await _load(account), said, reply, seen)
    m["session"] = (session or "")[:64]
    await _save(account, m)
    return m


async def closing(account: str, said: str, reply: str) -> None:
    """They said thanks / that's all / bye: nothing to carry on — unless a hold still waits for their yes."""
    m = fold(await _load(account), said, reply, {})
    if not (m.get("pending") or {}).get("kind") == "hold":
        m["thing"], m["pending"] = None, None
    await _save(account, m)


def _hold_live(account: str, p: dict) -> bool:
    """A remembered hold is offered as waiting only while its read-back still stands (same tool, not yet expired)."""
    try:
        from agapi import yes_gate as YG
        h = YG._held({"hold_venue": "book_venue", "hold_booking": "book"}.get(p.get("tool"), p.get("tool")), account)
        if not h or not h.get("at"):
            return False
        from agapi.v0 import READ_BACK_TTL_S
        return (NOW() - h["at"]).total_seconds() <= READ_BACK_TTL_S
    except Exception:
        return False


def line_for(m: Optional[dict], account: str) -> Optional[str]:
    if not m or not m.get("thing"):
        return None
    try:
        if NOW() - datetime.fromisoformat(m["updated_at"]) > OFFER_FOR:
            return None
    except Exception:
        return None
    thing = m["thing"]
    p = m.get("pending") or {}
    if p.get("kind") == "hold" and not _hold_live(account, p):
        thing = p.get("what") or thing   # the read-back has lapsed: what it was, read back again if they carry on
    return f"Welcome back — we were looking at {thing}. Want to carry on?"


async def recall(account: str, session: Optional[str]) -> dict:
    """On return: the line, the recent conversation (masked), the cards she'd shown (on screen again, for this session)."""
    m = await _load(account)
    line = line_for(m, account)
    if not m or not line:
        return {"line": None, "recent": [], "screen": None, "summary": (m or {}).get("summary") or []}
    scr = m.get("screen") or None
    if scr and scr.get("cards") and session:
        from app.agent import sasha as AG
        from agapi import venues as VN
        AG._SCREEN[session] = {"cards": scr["cards"], "ribbon": scr.get("ribbon"), "names": [c.get("name") for c in scr["cards"] if c.get("name")]}
        VN.remember_cards(account, scr["cards"])
    p = m.get("pending") or {}
    return {"line": line, "recent": m.get("recent") or [], "screen": scr, "summary": m.get("summary") or [],
            "pending": ({"kind": "hold", "what": p.get("what"), "waiting": _hold_live(account, p)} if p.get("kind") == "hold" else
                        {"kind": "question", "asked": p.get("asked")} if p.get("kind") == "question" else None)}


__all__ = ["remember", "closing", "recall", "fold", "line_for", "masked"]
