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
QUIVER_AFTER_S = float(os.getenv("SASHA_QUIVER_AFTER_S", "0.9"))      # nothing said by then → one short acknowledgement
FILLER_MODEL = os.getenv("SASHA_FILLER_MODEL", "claude-haiku-4-5")      # Sasha 205 · the acknowledgements, written fresh
TRIM_CHARS = int(os.getenv("SASHA_TRIM_CHARS", "1200"))               # Sasha 205 · the only length limit: a safety trim
_WEIGH = {"search_flights", "search_stays", "search_venues", "read_booking_route"}
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


# Sasha 205 · EVERY tool result has a renderer in the UI, by type (tests/test_agapi_guards.py holds it)
RENDER = {"search_flights": "flights", "search_stays": "stays", "search_venues": "venues", "read_booking_route": "venue_route",
          "prepare_trip": "inline", "propose_trip": "trip", "swap_stay": "trip", "choose_offer": "trip", "check_offer": "inline",
          "save_travellers": "inline", "hold_booking": "read_back", "book": "trip", "get_status": "trip", "get_trip": "trip",
          "get_total": "inline"}
KINDS = {"flights", "stays", "venues", "venue_route", "read_back", "trip", "inline"}   # what the /next UI renders (SashaChat agentTurn)


def render(tool: str, res: dict, args: dict) -> Optional[dict]:
    """The UI event for a tool's result: {"type": "render", "kind", …payload} — or None for "inline" (it's in her words) and
    "trip" (the trip_changed event already refreshes the Trip view)."""
    kind = RENDER.get(tool, "inline")
    if kind == "flights":
        return {"type": "render", "kind": kind, "card": flight_card(res, args)}
    if kind == "stays":
        return {"type": "render", "kind": kind, "card": stays_card(res)}
    if kind == "venues" and res.get("find"):
        return {"type": "render", "kind": kind, "find": res["find"]}
    if kind == "venue_route":
        return {"type": "render", "kind": kind, "find": {"what": res.get("venue") or args.get("name"), "where": args.get("city"), "named": True,
                                                         **({"country": args["country"]} if args.get("country") else {}),
                                                         **({"open_at": args["at"]} if args.get("at") else {})}}
    if kind == "read_back":
        return {"type": "render", "kind": kind, "trip_book": {"from": args.get("origin") or "Madrid"}}
    return None


def stays_card(res: dict) -> dict:
    """search_stays' result as a Live Workspace card, each to CHOOSE (the Choose button says "the <name> one")."""
    return {"type": "hotel", "trip_pick": True, "title": f"Places to stay · {res.get('city')}",
            "options": [{"name": h["name"], "detail": " · ".join(x for x in [f"{h.get('stars')}★" if h.get("stars") else "", h.get("about") or ""] if x),
                         "price": f"about €{h['estimate_eur_per_night']:,}/night (estimate)" if h.get("estimate_eur_per_night") else ""}
                        for h in res.get("stays") or []]}


def flight_card(res: dict, args: dict) -> dict:
    """Sasha 205 · search_flights' result as the Live Workspace's flight card (the same shape the current UI renders),
    each to CHOOSE — the Choose button says "the <airline> one" to her."""
    fl = res.get("flights") or []
    party = int(args.get("passengers") or 2)
    opts = []
    for f in fl:
        hm = f["duration_minutes"]
        opts.append({"name": f["airline"], "provider": "duffel", "provider_offer_id": f["offer_id"],
                     "detail": " · ".join(x for x in [f"dep {str(f['departs'])[11:16]}", f"{f['from']}-{f['to']}", f"{hm // 60}h {hm % 60:02d}m",
                                                       "nonstop" if not f["stops"] else f"{f['stops']} stop{'s' if f['stops'] > 1 else ''}",
                                                       f["flights"]] if x),
                     "price": f"€{f['price_eur']:,.2f} total for {party} (TEST)", "dep": str(f["departs"])[11:16]})
    return {"type": "flight", "_provider": "duffel", "trip_pick": True, "options": opts,
            "title": f"Flights · {args.get('origin')} → {args.get('destination')}" + (" (home)" if res.get("leg") == "back" else "")}


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
    # Sasha 205 · PROMPT CACHING: her persona and the tool schemas are the same every call — cached, the model starts sooner
    system = [{"type": "text", "text": P.AGENT_SYSTEM, "cache_control": {"type": "ephemeral"}},
              {"type": "text", "text": system_prompt(datetime.now(timezone.utc))[len(P.AGENT_SYSTEM):]}]
    tools = tools_for_model()
    tools[-1] = {**tools[-1], "cache_control": {"type": "ephemeral"}}
    step_ms: List[dict] = []
    pending = ""          # Sasha 204 · text not yet a full sentence
    spoken_any = False    # Sasha 205 · has a phrase gone out this turn
    held = False          # a sentence failed the guard: nothing more is spoken this turn (the rewrite replaces it)
    booked_now = None

    async def sentences(flush: bool = False):
        """Sasha 205 · natural PHRASES to speak: complete sentences, gathered until there are two or ~25 words (or the step
        ends / a tool starts) — each checked (claims, prices) before it may be spoken."""
        nonlocal pending, held, booked_now, spoken_any
        parts = re.split(r"(?<=[.!?])\s+", pending)
        done, rest = (parts, "") if flush else (parts[:-1], parts[-1])
        if not flush and len(done) < 2 and sum(len(x.split()) for x in done) < 25 and spoken_any:
            return []   # wait for a fuller phrase (the FIRST sentence goes at once: she starts speaking as soon as she can)
        pending = rest
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
        if out:
            spoken_any = True
        return [" ".join(out)] if out else []

    steps_run = 0
    last_tools: set = set()
    for step in range(MAX_STEPS):
        steps_run = step + 1
        # Sasha 205 · the fast model talks and summarises (incl. a proposal, a total, a booking); the big one only weighs
        # search results (flights, stays, venues) to choose among them
        model = MODEL if last_tools & _WEIGH else FAST_MODEL
        t_step, ttft = time.perf_counter(), None
        async with client.messages.stream(model=model, max_tokens=900, system=system, tools=tools, messages=msgs) as s:
            async for ev in s:
                if ttft is None and ev.type in ("text", "content_block_start"):
                    ttft = int((time.perf_counter() - t_step) * 1000)
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
        u_ = getattr(final, "usage", None)
        step_ms.append({"model": model, "first_token": ttft, "ms": int((time.perf_counter() - t_step) * 1000),
                        "cached": getattr(u_, "cache_read_input_tokens", None)})
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
        last_tools = {u.name for u in uses}
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
            if r.get("ok"):
                ev = render(u.name, r["result"], args)
                if ev:
                    yield ev
            results.append({"type": "tool_result", "tool_use_id": u.id, "content": json.dumps(r, default=str)[:12000]})
        msgs.append({"role": "user", "content": results})
    text = "".join(said).strip()
    allowed |= await _basket_amounts(ctx)
    bad = guard_check(text, allowed, await _anything_booked(ctx))
    guard_log = list(bad)
    if bad:   # once: back to the model to rewrite — honestly (Sasha 205: no length rewrite; a safety trim below)
        msgs.append({"role": "user", "content": "[guard] Your last reply can't be sent: " + "; ".join(guard_log)
                     + ". Rewrite it in the same voice using only facts and prices from tool results. Reply with the rewritten text only."})
        r = await client.messages.create(model=FAST_MODEL, max_tokens=400, system=system, messages=msgs)
        new = "".join(b.text for b in r.content if b.type == "text").strip()
        bad2 = guard_check(new, allowed, await _anything_booked(ctx))
        text = new if not bad2 else guard_strip(new, bad2)
        guard_log += [f"rewritten{' then stripped: ' + '; '.join(bad2) if bad2 else ''}"]
        yield {"type": "replace", "text": text, "speak": bool(bad) or held}   # Sasha 204 · re-spoken only if facts were wrong
    if len(text) > TRIM_CHARS:   # Sasha 205 · the safety trim: a very long reply ends at a sentence
        cut = text[:TRIM_CHARS]
        text = cut[: max(cut.rfind(". "), cut.rfind("? "), cut.rfind("! ")) + 1] or cut
        guard_log.append(f"trimmed to {len(text)} characters")
        yield {"type": "replace", "text": text, "speak": False}
    ms = {"first_text": first_text_ms, "total": int((time.perf_counter() - t0) * 1000), "first_model": FAST_MODEL,
          "models": sorted({x["model"] for x in step_ms}), "steps": step_ms}
    log.info("[agent] turn %s ms first-text=%s total=%s tools=%s guard=%s", session, ms["first_text"], ms["total"],
             [c["tool"] for c in ctx.calls], guard_log)
    yield {"type": "done", "text": text, "guard": guard_log, "tools": ctx.calls, "ms": ms}


QUIVER = list(P.QUIVER)   # the safe fallback pool (sasha-persona.md)
FALLBACK = QUIVER + ["Ooh, lovely.", "Right, let me see.", "Good thinking.", "Leave it with me a second.", "Let me have a look.",
                     "Mm, let me check that.", "Nice — one second.", "On it.", "Let me take a look.", "Great, give me a moment."]
_FACTY = re.compile(r"(?i)[\d€$£]|\b(book(?:ed|ing)?|reserv\w*|confirm\w*|paid|payment|pay|price\w*|cost\w*|ticket\w*|cheap\w*|"
                    r"expensive|deal|guarantee\w*|promise\w*|euros?|dollars?|free)\b")
_USED: Dict[str, List[str]] = {}   # session → the acknowledgements already said (never twice in a conversation)


def _norm(t: str) -> str:
    return re.sub(r"[^a-z ]", "", (t or "").lower()).strip()


def filler_ok(line: str, used: List[str]) -> bool:
    """Sasha 205 · an acknowledgement may be said: short, no fact (no number, price, booking, confirmation, promise), new."""
    t = (line or "").strip()
    return bool(t) and len(t.split()) <= 16 and not _FACTY.search(t) and "?" not in t and _norm(t) not in {_norm(u) for u in used}


def _fallback(used: List[str]) -> str:
    for line in FALLBACK:
        if filler_ok(line, used):
            return line
    return ""   # every safe line used: say nothing rather than repeat


async def make_filler(message: str, doing: str, session: Optional[str]) -> str:
    """A short spoken acknowledgement written fresh from what the person just said (and what she's about to do) — checked:
    never a fact, never twice. Falls back to an unused safe line; empty if even those are spent."""
    from app.services.llm import client
    used = _USED.setdefault(session or "-", [])
    line = ""
    try:
        r = await client.messages.create(
            model=FILLER_MODEL, max_tokens=40,
            system=("You are Sasha, a warm, witty travel concierge, speaking. Write ONE short spoken acknowledgement (at most 12 words) "
                    "reacting to what the traveller just said, as you start on it. It can be playful and specific to the place or the "
                    "moment. Never a number, price, date, booking, payment, confirmation or promise. Not a question. Reply with the line only."
                    + (f" Don't reuse any of these: {' | '.join(used[-12:])}" if used else "")),
            messages=[{"role": "user", "content": f"Traveller: {message[:400]}\nYou're about to: {doing}"}])
        line = "".join(b.text for b in r.content if getattr(b, "type", "") == "text").strip().strip('"')
    except Exception as e:
        log.info("[agent] filler not written: %s", type(e).__name__)
    if not filler_ok(line, used):
        line = _fallback(used)
    if line:
        used.append(line)
        del used[:-60]
    return line


def _doing(why: str, tool: Optional[str]) -> str:
    return {"propose_trip": "put the whole trip together", "prepare_trip": "start getting the trip ready",
            "search_flights": "look at flights", "search_stays": "look at places to stay", "swap_stay": "change a hotel",
            "choose_offer": "swap the flight", "hold_booking": "check everything before booking", "book": "send the payment link",
            "get_total": "add it all up", "get_trip": "look at their trip", "search_venues": "look for places",
            }.get(tool or "", "think about it")


async def turn_with_quiver(account: str, message: str, history: List[dict], session: Optional[str]) -> AsyncIterator[dict]:
    """turn(), never silent: a short acknowledgement (written fresh, never a fact, never twice) if nothing is said within
    QUIVER_AFTER_S, or when a tool starts with nothing just said — at most two per turn."""
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
    first_filler = asyncio.create_task(make_filler(message, "think about it", session))   # written while she thinks
    t0 = time.perf_counter()
    last_say, fillers, first_sound = None, 0, None
    tool_filler: Optional["asyncio.Task"] = None
    try:
        while True:
            if tool_filler is not None and tool_filler.done():
                line, tool_filler = tool_filler.result(), None
                if line and fillers < 2 and (last_say is None or time.perf_counter() - last_say > 3):
                    fillers += 1
                    last_say = time.perf_counter()
                    first_sound = first_sound or int((last_say - t0) * 1000)
                    yield {"type": "filler", "text": line, "why": "tool"}
            wait = 0.1 if tool_filler is not None else (
                None if (last_say is not None or fillers) else max(0.05, QUIVER_AFTER_S - (time.perf_counter() - t0)))
            try:
                ev = await asyncio.wait_for(q.get(), timeout=wait)
            except asyncio.TimeoutError:
                if tool_filler is not None or last_say is not None or fillers:
                    continue
                try:   # nothing said yet: the first sound is the acknowledgement (give it a moment more if still being written)
                    line = await asyncio.wait_for(asyncio.shield(first_filler), timeout=0.6)
                except asyncio.TimeoutError:
                    line = _fallback(_USED.setdefault(session or "-", []))
                    if line:
                        _USED[session or "-"].append(line)
                fillers += 1
                if line:
                    last_say = time.perf_counter()
                    first_sound = first_sound or int((last_say - t0) * 1000)
                    yield {"type": "filler", "text": line, "why": "silence"}
                continue
            if ev is None:
                break
            now = time.perf_counter()
            if ev["type"] == "say":
                last_say = now
                first_sound = first_sound or int((now - t0) * 1000)
            elif ev["type"] == "tool_start" and fillers < 2 and tool_filler is None and (last_say is None or now - last_say > 3):
                tool_filler = asyncio.create_task(make_filler(message, _doing("tool", ev.get("name")), session))
            if ev["type"] == "done":
                ev = {**ev, "ms": {**(ev.get("ms") or {}), "first_sound_server": first_sound, "fillers": fillers}}
            yield ev
    finally:
        for t in (task, first_filler, tool_filler):
            if t is not None and not t.done():
                t.cancel()


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


__all__ = ["router", "turn", "turn_with_quiver", "make_filler", "filler_ok", "flight_card", "stays_card", "render", "RENDER", "KINDS", "FAST_MODEL", "guard_check", "guard_strip", "tools_for_model", "system_prompt", "MODEL"]
