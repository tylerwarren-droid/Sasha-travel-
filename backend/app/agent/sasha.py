"""Sasha 203 · SASHA AS AN AI AGENT WITH TOOLS — the /next path, alongside the current Sasha (nothing in the current flow changes).

One capable model runs the whole conversation in Sasha's persona (the system prompt is the charter + sasha-persona.md, derived
into persona.AGENT_SYSTEM). No intent regexes, no step patterns: it listens, asks, suggests, decides. It acts ONLY through
AgAPI v0 (agapi/v0.py), called like any outside client — per account, TEST mode, idempotency keys filled here.

HARD GUARDS, in code (not the prompt):
  · book's approval is the REAL user message of this turn (agapi.v0.explicit_yes) — the model can't supply it.
  · prices: every € amount in her reply must have come from a tool result this conversation (or the basket now);
  · booked / paid / confirmed: only when Pacioli (get_status) has a booked row.
  A reply breaking either is sent back to the model once to rewrite; if it still breaks, the offending sentence is replaced.

POST /api/agent/turn {message, history, session_id} → text/event-stream:
  {"type":"text","delta"} · {"type":"tool","name","agent","ok"} · {"type":"trip_changed"} · {"type":"replace","text"}
  · {"type":"done","text","guard":[...],"ms":{...}}
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Dict, List, Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from agapi import v0 as API
from app.services import persona as P

log = logging.getLogger("agent.sasha")
router = APIRouter(prefix="/api/agent", tags=["agent"])
MODEL = os.getenv("SASHA_AGENT_MODEL", "claude-opus-5-5")               # tools and planning
FAST_MODEL = os.getenv("SASHA_AGENT_FAST_MODEL", "claude-sonnet-5-5")   # Sasha 204 · the first step of a turn (plain conversation)
QUIVER_AFTER_S = float(os.getenv("SASHA_QUIVER_AFTER_S", "0.9"))      # nothing said by then → one quiver line
MAX_STEPS = 8
_CHANGES_TRIP = {"propose_trip", "swap_stay", "choose_offer", "search_flights", "hold_booking", "book"}
_CLAIM = re.compile(r"(?i)\b(?:(?:is|are|been|all|now|it's|you're|you are|i've|i have|has been|have been|successfully|now)\s+(?:booked|paid|confirmed)"
                    r"|booking (?:is )?confirmed|payment (?:has )?(?:gone through|been received|received)|✅\s*booked|confirmation (?:email|number))")
_EUR = re.compile(r"€\s?(\d[\d,]*(?:\.\d+)?)")


def system_prompt(now: datetime) -> str:
    return (P.AGENT_SYSTEM + f"\n\n---\n\nToday is {now.strftime('%A %d %B %Y')}. Dates you pass to tools are YYYY-MM-DD. "
            "Prices and totals are in euros.")


def tools_for_model() -> List[dict]:
    return [API.schema_for_model(t) for t in API.TOOLS]


def _amounts(obj: Any, out: set) -> None:
    """Every number in a tool result (a price the model may then say)."""
    if isinstance(obj, dict):
        for v in obj.values():
            _amounts(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _amounts(v, out)
    elif isinstance(obj, (int, float)) and not isinstance(obj, bool):
        out.add(round(float(obj), 2))
    elif isinstance(obj, str):
        for m in re.findall(r"(?:€|EUR)\s?(\d[\d,]*(?:\.\d+)?)", obj):
            out.add(round(float(m.replace(",", "")), 2))


def guard_check(text: str, allowed: set, anything_booked: bool) -> List[str]:
    """What's wrong with a reply, if anything: unproven claims, prices no tool gave."""
    bad = []
    if _CLAIM.search(text or "") and not anything_booked:
        bad.append("claim: it says booked/paid/confirmed but Pacioli has nothing booked")
    for m in _EUR.findall(text or ""):
        v = float(m.replace(",", ""))
        if not any(abs(v - a) <= max(1.0, a * 0.005) for a in allowed):
            bad.append(f"price: €{m} did not come from a tool")
    return bad


def too_long(text: str) -> Optional[str]:
    """The charter's pace (rule 3): at most ~3 short sentences, each ≤ ~15 words, at most one question."""
    sents = [x for x in re.split(r"(?<=[.!?])\s+", (text or "").strip()) if x]
    long_ = [x for x in sents if len(x.split()) > 18]
    if len(sents) > 3 or long_ or (text or "").count("?") > 1:
        return f"too long: {len(sents)} sentences, {len(long_)} over 15 words, {(text or '').count('?')} questions"
    return None


def guard_strip(text: str, bad: List[str]) -> str:
    """Last resort: drop the offending sentences, say why honestly."""
    out = []
    for s in re.split(r"(?<=[.!?])\s+", text or ""):
        if _CLAIM.search(s) and any(b.startswith("claim") for b in bad):
            out.append("Not booked yet — I'll tell you the moment it is.")
        elif _EUR.search(s) and any(b.startswith("price") for b in bad):
            out.append("The panel shows the prices.")
        else:
            out.append(s)
    return " ".join(dict.fromkeys(out))


async def _anything_booked(ctx: API.Ctx) -> bool:
    r = await API.call(ctx, "get_status", {})
    return bool(r.get("ok") and r["result"].get("anything_booked"))


async def _basket_amounts(ctx: API.Ctx) -> set:
    out: set = set()
    for name in ("get_total", "get_trip"):
        r = await API.call(ctx, name, {})
        if r.get("ok"):
            _amounts(r["result"], out)
    return out


async def turn(account: str, message: str, history: List[dict], session: Optional[str]) -> AsyncIterator[dict]:
    """One turn: the model, its tools, the guards. Yields events (see the module doc)."""
    from app.services.llm import client
    t0 = time.perf_counter()
    first_text_ms = None
    ctx = API.Ctx(account=account, mode="test", user_said=message, session=session)
    msgs: List[dict] = [{"role": m["role"], "content": str(m.get("content") or "")} for m in (history or [])
                        if m.get("role") in ("user", "assistant") and str(m.get("content") or "").strip()][-40:]
    msgs.append({"role": "user", "content": message})
    allowed: set = set()
    for m in history or []:   # amounts she already said (from earlier tool results) stay sayable
        if m.get("role") == "assistant":
            _amounts(str(m.get("content") or ""), allowed)
    said: List[str] = []
    turn_key = hashlib.sha256(f"{session}:{len(history or [])}:{message}".encode()).hexdigest()[:16]
    system = system_prompt(datetime.now(timezone.utc))
    tools = tools_for_model()
    pending = ""          # Sasha 204 · text not yet a full sentence
    held = False          # a sentence failed the guard: nothing more is spoken this turn (the rewrite replaces it)
    booked_now = None

    async def sentences(flush: bool = False):
        """Complete sentences out of `pending`, each checked (claims, prices) before it may be spoken."""
        nonlocal pending, held, booked_now
        parts = re.split(r"(?<=[.!?])\s+", pending)
        done, pending = (parts, "") if flush else (parts[:-1], parts[-1])
        out = []
        for x in [p.strip() for p in done if p.strip()]:
            if held:
                continue
            if _CLAIM.search(x) and booked_now is None:
                booked_now = await _anything_booked(ctx)
            if guard_check(x, allowed, bool(booked_now)):
                held = True
                continue
            out.append(x)
        return out

    steps_run = 0
    for step in range(MAX_STEPS):
        steps_run = step + 1
        model = FAST_MODEL if step == 0 else MODEL   # Sasha 204 · fast for plain talk; the big model once tools are in play
        async with client.messages.stream(model=model, max_tokens=900, system=system, tools=tools, messages=msgs) as s:
            async for ev in s:
                if ev.type == "text":
                    if first_text_ms is None:
                        first_text_ms = int((time.perf_counter() - t0) * 1000)
                    said.append(ev.text)
                    yield {"type": "text", "delta": ev.text}
                    pending += ev.text
                    for x in await sentences():
                        yield {"type": "say", "text": x}
                elif ev.type == "content_block_start" and getattr(ev.content_block, "type", "") == "tool_use":
                    for x in await sentences(flush=True):
                        yield {"type": "say", "text": x}
                    yield {"type": "tool_start", "name": ev.content_block.name}
            final = await s.get_final_message()
        for x in await sentences(flush=True):
            yield {"type": "say", "text": x}
        msgs.append({"role": "assistant", "content": [b.model_dump(exclude_none=True) for b in final.content]})
        uses = [b for b in final.content if b.type == "tool_use"]
        if not uses:
            break
        if said and not said[-1].endswith((" ", "\n")):
            said.append(" ")
            yield {"type": "text", "delta": " "}
        results = []
        for u in uses:
            args = dict(u.input or {})
            t = API.BY_NAME.get(u.name)
            if t and t["idempotent"]:
                args["idempotency_key"] = f"{turn_key}:{u.name}:{hashlib.sha256(json.dumps(u.input, sort_keys=True).encode()).hexdigest()[:12]}"
            if u.name == "book":
                args["approval"] = {"said": message}   # the REAL words of this turn — never the model's
            r = await API.call(ctx, u.name, args)
            if r.get("ok"):
                _amounts(r["result"], allowed)
            yield {"type": "tool", "name": u.name, "agent": (t or {}).get("agent"), "ok": r.get("ok"),
                   **({"error": r["error"]["code"]} if not r.get("ok") else {})}
            if r.get("ok") and u.name in _CHANGES_TRIP:
                yield {"type": "trip_changed"}
            results.append({"type": "tool_result", "tool_use_id": u.id, "content": json.dumps(r, default=str)[:12000]})
        msgs.append({"role": "user", "content": results})
    text = "".join(said).strip()
    allowed |= await _basket_amounts(ctx)
    bad = guard_check(text, allowed, await _anything_booked(ctx))
    long_ = too_long(text)
    guard_log = list(bad) + ([long_] if long_ else [])
    if bad or long_:   # once: back to the model to rewrite — honestly, and short
        msgs.append({"role": "user", "content": "[guard] Your last reply can't be sent: " + "; ".join(guard_log)
                     + ". Rewrite it in the same voice: at most two short sentences (each 15 words or fewer) and at most one question; "
                       "only facts and prices from tool results; the panel shows the details. Reply with the rewritten text only."})
        r = await client.messages.create(model=MODEL, max_tokens=400, system=system, messages=msgs)
        new = "".join(b.text for b in r.content if b.type == "text").strip()
        bad2 = guard_check(new, allowed, await _anything_booked(ctx))
        text = new if not bad2 else guard_strip(new, bad2)
        guard_log += [f"rewritten{' then stripped: ' + '; '.join(bad2) if bad2 else ''}"]
        yield {"type": "replace", "text": text, "speak": bool(bad) or held}   # Sasha 204 · re-spoken only if facts were wrong
    ms = {"first_text": first_text_ms, "total": int((time.perf_counter() - t0) * 1000), "first_model": FAST_MODEL,
          "models": [FAST_MODEL] + ([MODEL] if steps_run > 1 else [])}
    log.info("[agent] turn %s ms first-text=%s total=%s tools=%s guard=%s", session, ms["first_text"], ms["total"],
             [c["tool"] for c in ctx.calls], guard_log)
    yield {"type": "done", "text": text, "guard": guard_log, "tools": ctx.calls, "ms": ms}


QUIVER = list(P.QUIVER)


def quiver_for(message: str, why: str, n: int) -> str:
    """Sasha 204 · a line from the fixed quiver (sasha-persona.md), chosen by what's happening — never a fact."""
    pick = lambda line: line if line in QUIVER else QUIVER[0]
    if why == "tool":
        return pick("Let me look into that.") if n == 0 else pick("Hold on one second while I sort that out.")
    m = (message or "").strip()
    if _TRIPPY.search(m):
        return pick("That sounds fun!")
    if m.endswith("?"):
        return pick("Good question.")
    if _ASKS.search(m):   # a request: she's about to do something
        return pick("Let me look into that.")
    if _HELLO.match(m):
        return pick("Lovely.")
    return pick("Got it.")   # an answer (a name, a number, a date): acknowledged, not "looked into"


_ASKS = re.compile(r"(?i)\b(show|find|search|look|change|swap|switch|book|make it|move|add|remove|cheaper|other|different|another|check)\b")
_HELLO = re.compile(r"(?i)^\s*(hi|hello|hey|hola|good (morning|afternoon|evening))\b")
_TRIPPY = re.compile(r"(?i)\b(go(?:ing)? to|trip|travel|visit|holiday|vacation|honeymoon|getaway)\b")


async def turn_with_quiver(account: str, message: str, history: List[dict], session: Optional[str]) -> AsyncIterator[dict]:
    """turn(), never silent: if nothing is said within QUIVER_AFTER_S, or a tool starts with nothing just said, a quiver
    line is spoken (at most two per turn, never twice in a row)."""
    import asyncio
    q: "asyncio.Queue" = asyncio.Queue()

    async def produce():
        try:
            async for ev in turn(account, message, history, session):
                await q.put(ev)
        except Exception as e:
            log.error("[agent] turn failed: %s: %s", type(e).__name__, e)
            await q.put({"type": "error", "message": "I hit a snag just now — could you say that again?"})
        await q.put(None)
    task = asyncio.create_task(produce())
    t0 = time.perf_counter()
    last_say, quivers, first_sound = None, 0, None
    try:
        while True:
            wait = None if (last_say is not None or quivers) else max(0.05, QUIVER_AFTER_S - (time.perf_counter() - t0))
            try:
                ev = await asyncio.wait_for(q.get(), timeout=wait)
            except asyncio.TimeoutError:   # nothing said yet: the first sound is a quiver line
                quivers += 1
                first_sound = first_sound or int((time.perf_counter() - t0) * 1000)
                yield {"type": "quiver", "text": quiver_for(message, "silence", 0), "why": "silence"}
                continue
            if ev is None:
                break
            now = time.perf_counter()
            if ev["type"] == "say":
                last_say = now
                first_sound = first_sound or int((now - t0) * 1000)
            elif ev["type"] == "tool_start" and quivers < 2 and (last_say is None or now - last_say > 4):
                yield {"type": "quiver", "text": quiver_for(message, "tool", quivers), "why": "tool"}
                quivers += 1
                last_say = now
                first_sound = first_sound or int((now - t0) * 1000)
            if ev["type"] == "done":
                ev = {**ev, "ms": {**(ev.get("ms") or {}), "first_sound_server": first_sound, "quivers": quivers}}
            yield ev
    finally:
        if not task.done():
            task.cancel()


TIMINGS: List[dict] = []


async def _keep_warm() -> None:
    """Sasha 204 · keep the model connections warm (a token count every 4 minutes: no generation, nothing billed but a call)."""
    import asyncio
    from app.services.llm import client
    while True:
        for m in {FAST_MODEL, MODEL}:
            try:
                await client.messages.count_tokens(model=m, messages=[{"role": "user", "content": "hi"}])
            except Exception as e:
                log.info("[agent] warm %s: %s", m, type(e).__name__)
        await asyncio.sleep(240)


@router.on_event("startup")
async def _start_warm() -> None:
    import asyncio
    if os.getenv("DATABASE_URL", "").strip() and os.getenv("SASHA_AGENT_WARM", "1") == "1":
        asyncio.create_task(_keep_warm())


@router.post("/timing")
async def agent_timing(request: Request):
    """Sasha 204 · the page's own measure of a voice turn: end of speech → first sound, → the full answer spoken."""
    from app.services.chat_account import chat_account, signed_in
    if not signed_in(await chat_account(request)):
        return JSONResponse({"ok": False}, status_code=403)
    b = await request.json()
    row = {k: b.get(k) for k in ("session", "first_sound_ms", "full_answer_ms", "first_sound_kind", "engine_first_text_ms", "tools")}
    row["at"] = datetime.now(timezone.utc).isoformat()
    TIMINGS.append(row)
    del TIMINGS[:-200]
    log.warning("[agent-timing] %s", json.dumps(row))
    return {"ok": True}


@router.post("/turn")
async def agent_turn(request: Request):
    from app.services.chat_account import chat_account, signed_in
    account = await chat_account(request)
    if not signed_in(account):
        return JSONResponse({"ok": False, "rule": "sign_in", "message": "Sasha's agent (/next) is for a signed-in account"}, status_code=403)
    body = await request.json()
    message = str(body.get("message") or "").strip()[:4000]
    if not message:
        return JSONResponse({"ok": False, "rule": "empty"}, status_code=400)

    async def events():
        try:
            async for ev in turn_with_quiver(account, message, body.get("history") or [], str(body.get("session_id") or "")[:64] or None):
                yield f"data: {json.dumps(ev, default=str)}\n\n"
        except Exception as e:
            log.error("[agent] turn failed: %s: %s", type(e).__name__, e)
            yield f"data: {json.dumps({'type': 'error', 'message': 'I hit a snag just now — could you say that again?'})}\n\n"
    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


__all__ = ["router", "turn", "turn_with_quiver", "quiver_for", "FAST_MODEL", "guard_check", "guard_strip", "tools_for_model", "system_prompt", "MODEL"]
