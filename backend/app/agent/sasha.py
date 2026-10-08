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
QUIVER_AFTER_S = float(os.getenv("SASHA_QUIVER_AFTER_S", "1.5"))      # Sasha 210 · nothing ready by then → one short acknowledgement
STILL_AFTER_S = float(os.getenv("SASHA_STILL_AFTER_S", "8"))       # Sasha 210 · silent this long while working → ONE "nearly there"
SPLIT_AFTER_S = float(os.getenv("SASHA_SPLIT_AFTER_S", "3.0"))      # Sasha 210 · a step still writing by then: its whole sentences go out
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


_CONDITIONAL = re.compile(r"(?i)\b(?:once|when|after|as soon as|until|the moment)\b[^.!?]*\b(?:pa(?:y|id)|tap|go(?:ne)? through)|\bnot (?:yet )?(?:booked|paid|confirmed)|\bnothing'?s? (?:is )?(?:booked|paid|confirmed)")


def _claims(text: str) -> bool:
    """A booked/paid/confirmed claim — not a sentence saying it WILL be, once they pay (Sasha 210), nor saying it isn't yet."""
    return any(_CLAIM.search(x) and not _CONDITIONAL.search(x) for x in re.split(r"(?<=[.!?])\s+", text or ""))


def guard_check(text: str, allowed: set, anything_booked: bool) -> List[str]:
    """What's wrong with a reply, if anything: unproven claims, prices no tool gave."""
    bad = []
    if _claims(text) and not anything_booked:
        bad.append("claim: it says booked/paid/confirmed but Pacioli has nothing booked")
    for m in _EUR.findall(text or ""):
        v = float(m.replace(",", ""))
        if not any(abs(v - a) <= max(1.0, a * 0.005) for a in allowed):
            bad.append(f"price: €{m} did not come from a tool")
    return bad


# Sasha 205 · EVERY tool result has a renderer in the UI, by type (tests/test_agapi_guards.py holds it)
RENDER = {"search_flights": "flights", "search_stays": "stays", "search_venues": "venues", "read_booking_route": "venue_route",
          "prepare_trip": "inline", "propose_trip": "flights", "swap_stay": "trip", "choose_offer": "flight_chosen", "check_offer": "inline",
          "save_travellers": "inline", "hold_booking": "read_back", "book": "trip", "get_status": "trip", "get_trip": "trip",
          "get_total": "inline"}
KINDS = {"flights", "flight_chosen", "stays", "venues", "venue_route", "read_back", "trip", "inline"}   # what the /next UI renders (SashaChat agentTurn)


def render(tool: str, res: dict, args: dict) -> Optional[dict]:
    """The UI event for a tool's result: {"type": "render", "kind", …payload} — or None for "inline" (it's in her words) and
    "trip" (the trip_changed event already refreshes the Trip view)."""
    kind = RENDER.get(tool, "inline")
    if tool == "propose_trip":   # Sasha 210 · the proposal arrives WITH its flights: a card per leg, the chosen one marked
        opts = res.get("flight_options") or {}
        cards = [flight_card({"flights": opts[leg], "leg": leg}, {"origin": (opts[leg][0] or {}).get("from"),
                                                                  "destination": (opts[leg][0] or {}).get("to"), "passengers": res.get("party")})
                 for leg in ("out", "back") if opts.get(leg)]
        return {"type": "render", "kind": kind, "cards": cards} if cards else None
    if kind == "flight_chosen":
        ch = res.get("chosen") or {}
        return {"type": "render", "kind": kind, "offer_id": ch.get("offer_id")} if ch.get("offer_id") else None
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
    leg = res.get("leg") or args.get("leg") or "out"
    opts = []
    for f in fl:
        hm = f["duration_minutes"]
        dep = str(f["departs"])[11:16]
        opts.append({"name": f["airline"], "provider": "duffel", "provider_offer_id": f["offer_id"],
                     "detail": " · ".join(x for x in [f.get("tag") or "", f"dep {dep}", f"{f['from']}-{f['to']}", f"{hm // 60}h {hm % 60:02d}m",
                                                       "nonstop" if not f["stops"] else f"{f['stops']} stop{'s' if f['stops'] > 1 else ''}",
                                                       f["flights"]] if x),
                     "price": f"€{f['price_eur']:,.2f} total for {party} · TEST", "dep": dep, "chosen": bool(f.get("chosen")),
                     # Sasha 210 · a tap says exactly which flight (two options can share an airline)
                     "pick": f"the {f['airline']} flight {'home' if leg == 'back' else 'out'} at {dep}"})
    return {"type": "flight", "_provider": "duffel", "trip_pick": True, "options": opts, "leg": leg,
            "title": f"Flights · {args.get('origin')} → {args.get('destination')}" + (" (home)" if leg == "back" else "")}


def guard_strip(text: str, bad: List[str]) -> str:
    """Last resort: drop the offending sentences, say why honestly."""
    out = []
    for s in re.split(r"(?<=[.!?])\s+", text or ""):
        if _claims(s) and any(b.startswith("claim") for b in bad):
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


# ── Sasha 210 · ONE VOICE: openers never repeated, the acknowledgement continued, never her internals or a test disclaimer ──

# an OPENER is an interjection at the start of an utterance ("Lovely —", "Great!", "Ooh,", "Great choice!") — never twice in
# a conversation, and never right after the acknowledgement she has just said (the answer CONTINUES it)
OPENER_WORDS = ("lovely|great|perfect|wonderful|brilliant|fantastic|amazing|awesome|ooh|oh|ah|okay|ok|right|sure|absolutely|nice|"
                "gorgeous|excellent|fab|fabulous|alright|yes|yay|splendid|marvellous|superb|beautiful|good|cool|wow|hello|hi|hey|well|so")
_OPENER = re.compile(r"(?i)^\s*(?P<w>" + OPENER_WORDS + r")\b(?:\s+(?:choice|stuff|news|timing|idea|call|question|thinking|pick|plan|one|"
                     r"lovely|great|perfect|then|there))?\s*(?:[,!.…:;]+|\s*[—–]|\s-\s)\s*")
# an acknowledgement never starts the way her answers do (so the answer that follows it never sounds like a second greeting)
_ANSWER_STYLE = {"lovely", "great", "perfect", "wonderful", "brilliant", "fantastic", "amazing", "awesome", "absolutely", "excellent",
                 "gorgeous", "nice", "good", "sure", "okay", "ok", "hello", "hi", "hey"}
_OPENERS: Dict[str, set] = {}   # session → the openers already said (fillers and answers)

# her internals — her process, errors, the system — and test disclaimers: never in what she says (the cards carry a TEST tag)
_INTERNAL = re.compile(
    r"(?i)\bi (?:got|was|am|'m|get) (?:a (?:bit|little) )?(?:mixed|muddled|confused|tangled)|\bmix(?:ed)?[- ]?up\b|"
    r"\bi don'?t want to (?:pass on|give you|tell you) (?:bad|wrong|incorrect|outdated)|\bbad info|"
    r"\b(?:technical|system|server)\s+(?:issue|problem|error|glitch|hiccup|trouble)|\bglitch|\berror\b|\bhiccup|\bsnag\b|"
    r"\bmy (?:tools?|system|search tool|database)\b|\bthe (?:tool|system|api|database|backend|server)\b|\btool(?:s)?\b|"
    r"\bapologi[sz]e for the confusion|\bsorry (?:about|for) (?:that|the) (?:confusion|mix)|\blet me (?:try|check|do) (?:that|this|it) again\b|"
    r"\bexpired\b|\boffer id\b|\bre-?quot|\btimed? out\b|\bread-?back\b|"
    r"\bcorrection\b|\bi (?:said|told you|mentioned) (?:before|earlier)|\bi misspoke\b|\bi was wrong\b|\bscratch that\b|"
    r"(?:\bnot|n['’]t)\s+(?:actually\s+|really\s+)?(?:a\s+)?real\b|\btests?\b|\bdemo\b|\bsandbox\b|\bplaceholder\b|\bpretend\b|\bno real\b|"
    r"\bnothing (?:is|will be|gets|'s|has been) (?:actually |really )?(?:charged|taken|paid|reserved)\b|\bwon'?t (?:actually |really )?be charged\b")


def opener_of(text: str) -> Optional[str]:
    m = _OPENER.match(text or "")
    return ({"okay": "ok"}.get(m.group("w").lower(), m.group("w").lower())) if m else None


def strip_openers(text: str) -> str:
    """Every interjection at the start ("Ooh, lovely — let me look." → "Let me look.")."""
    t = text or ""
    for _ in range(3):
        m = _OPENER.match(t)
        if not m or not t[m.end():].strip():
            break
        t = t[m.end():]
    t = t.lstrip()
    return t[:1].upper() + t[1:] if t else t


def _history_openers(history: List[dict]) -> set:
    return {o for m in history or [] if m.get("role") == "assistant" for o in [opener_of(str(m.get("content") or ""))] if o}


def internal_sentences(text: str) -> List[str]:
    return [x for x in re.split(r"(?<=[.!?])\s+", text or "") if x.strip() and _INTERNAL.search(x)]


def spoken_prose(text: str) -> str:
    """Sasha 210 · she's speaking: no markdown, and a list becomes plain sentences (never "dash, bold, Hotels")."""
    out = []
    for line in (text or "").replace("**", "").replace("__", "").split("\n"):
        line = re.sub(r"^\s*(?:[-*•]|\d+[.)])\s+", "", line).strip()
        if line:
            out.append(line if re.search(r"[.!?:…]$", line) else line + ".")
    return " ".join(re.sub(r"([.!?])?\s+-\s+(?=[A-Z])", lambda m: (m.group(1) or ".") + " ", x) if x.count(" - ") > 1 else x
                    for x in out)


def drop_internal(text: str) -> str:
    keep = [x for x in re.split(r"(?<=[.!?])\s+", text or "") if x.strip() and not _INTERNAL.search(x)]
    return " ".join(keep)


_TEST_TAG = [(re.compile(r"\s*\((?:Duffel )?TEST[^)]*\)"), ""), (re.compile(r",?\s*marked TEST,?"), ","), (re.compile(r"\bDuffel TEST\b"), "Duffel"),
             (re.compile(r"\bTEST\s+"), ""), (re.compile(r"\s*\bTEST\b"), "")]
_MODEL_DROP_KEYS = {"note", "notes", "prices", "test", "prefetched", "flight_note", "total_note"}


def clean_for_model(obj: Any) -> Any:
    """A tool result as the MODEL sees it: no TEST notes or disclaimers (the person sees the TEST tag on the cards and the
    checkout), nothing internal — so she can't say it."""
    if isinstance(obj, dict):
        return {k: clean_for_model(v) for k, v in obj.items() if k not in _MODEL_DROP_KEYS}
    if isinstance(obj, list):
        return [clean_for_model(v) for v in obj if not (isinstance(v, str) and v.lstrip().startswith("⚠"))]
    if isinstance(obj, str):
        for rx, to in _TEST_TAG:
            obj = rx.sub(to, obj)
        return obj.replace(" ,", ",").strip()
    return obj


_ERROR_HINT = ("This is for you only — never mention it, never explain your process. Fix it with your tools if you can (another "
               "search, the nearest date, a re-check); if it truly can't be done, say ONE short plain line and offer the next step.")


def model_result(r: dict) -> dict:
    if r.get("ok"):
        return {"ok": True, "result": clean_for_model(r["result"])}
    e = r.get("error") or {}
    return {"ok": False, "error": {"code": e.get("code"), "message": clean_for_model(e.get("message") or "")}, "how_to_handle": _ERROR_HINT}


async def turn(account: str, message: str, history: List[dict], session: Optional[str],
               voice: Optional[dict] = None) -> AsyncIterator[dict]:
    """One turn: the model, its tools, the guards. Yields events (see the module doc). Sasha 210 · each model step is spoken
    as ONE utterance (no gaps between her phrases); `voice` is shared with turn_with_quiver: the acknowledgement she said
    while this turn worked ({"filler"}), and its request to speak what's ready ({"flush_now"})."""
    from app.services.llm import client
    voice = voice if voice is not None else {}
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
    used_openers = _OPENERS.setdefault(session or "-", set())
    used_openers |= _history_openers(history)
    said: List[str] = []      # what she says (cleaned) — the reply
    raw: List[str] = []       # what the model wrote — the guards read it
    turn_key = hashlib.sha256(f"{session}:{len(history or [])}:{message}".encode()).hexdigest()[:16]
    tools = tools_for_model()
    tools[-1] = {**tools[-1], "cache_control": {"type": "ephemeral"}}
    step_ms: List[dict] = []
    pending = ""          # this step's text, not yet spoken
    spoken_any = False
    held = False          # a sentence failed the claim/price guard: nothing more is spoken this turn (the rewrite replaces it)
    booked_now = None
    internal_log: List[str] = []

    def system_now() -> list:
        # Sasha 205 · PROMPT CACHING: her persona is the same every call (cached); the rest is per turn
        extra = system_prompt(datetime.now(timezone.utc))[len(P.AGENT_SYSTEM):]
        if used_openers:
            extra += (f"\n\nOpeners you've already used in this conversation — never start with them again: "
                      f"{', '.join(sorted(used_openers))}.")
        if voice.get("filler"):
            extra += (f"\n\nWhile you worked you already said aloud: “{voice['filler']}”. Carry straight on from it — no greeting, "
                      "no reaction word, never its opening words again.")
        return [{"type": "text", "text": P.AGENT_SYSTEM, "cache_control": {"type": "ephemeral"}}, {"type": "text", "text": extra}]

    async def speakable(chunk: str) -> str:
        """The part of this chunk she may say: claims and prices checked (a failure holds the rest of the turn), her internals
        and test disclaimers dropped, an opener she's used — or any opener right after her acknowledgement — taken off."""
        nonlocal held, booked_now
        out = []
        for x in [p.strip() for p in re.split(r"(?<=[.!?])\s+", spoken_prose(chunk)) if p.strip()]:
            if held:
                break
            if _INTERNAL.search(x):
                internal_log.append(x[:80])
                continue
            if _claims(x) and booked_now is None:
                booked_now = await _anything_booked(ctx)
            if guard_check(x, allowed, bool(booked_now)):
                held = True
                break
            out.append(x)
        text = " ".join(out)
        if not text:
            return ""
        first_of_turn = not said
        o = opener_of(text)
        if o and ((first_of_turn and voice.get("filler")) or o in used_openers):
            text = strip_openers(text)
            o = opener_of(text)
        if o:
            used_openers.add(o)
        return text

    async def flush(only_sentences: bool = False):
        """Speak what's pending — all of it (a tool starts, the step ends), or (asked to, because nothing has been said for a
        while) its complete sentences."""
        nonlocal pending, spoken_any
        if only_sentences:
            parts = re.split(r"(?<=[.!?])\s+", pending)
            if len(parts) < 2:
                return []
            chunk, pending = " ".join(parts[:-1]), parts[-1]
        else:
            chunk, pending = pending, ""
        text = await speakable(chunk)
        if not text:
            return []
        spoken_any = True
        said.append(text)
        return [{"type": "text", "delta": text + " "}, {"type": "say", "text": text}]

    last_tools: set = set()
    for step in range(MAX_STEPS):
        # Sasha 205 · the fast model talks and summarises (incl. a proposal, a total, a booking); the big one only weighs
        # search results (flights, stays, venues) to choose among them
        model = MODEL if last_tools & _WEIGH else FAST_MODEL
        t_step, ttft = time.perf_counter(), None
        async with client.messages.stream(model=model, max_tokens=900, system=system_now(), tools=tools, messages=msgs) as s:
            async for ev in s:
                if ttft is None and ev.type in ("text", "content_block_start"):
                    ttft = int((time.perf_counter() - t_step) * 1000)
                if ev.type == "text":
                    if first_text_ms is None:
                        first_text_ms = int((time.perf_counter() - t0) * 1000)
                    voice["text_started"] = True
                    raw.append(ev.text)
                    pending += ev.text
                    if voice.get("flush_now") and not spoken_any and time.perf_counter() - t0 > SPLIT_AFTER_S:
                        for e in await flush(only_sentences=True):
                            yield e
                elif ev.type == "content_block_start" and getattr(ev.content_block, "type", "") == "tool_use":
                    for e in await flush():
                        yield e
                    yield {"type": "tool_start", "name": ev.content_block.name}
            final = await s.get_final_message()
        u_ = getattr(final, "usage", None)
        step_ms.append({"model": model, "first_token": ttft, "ms": int((time.perf_counter() - t_step) * 1000),
                        "cached": getattr(u_, "cache_read_input_tokens", None)})
        for e in await flush():
            yield e
        msgs.append({"role": "assistant", "content": [b.model_dump(exclude_none=True) for b in final.content]})
        uses = [b for b in final.content if b.type == "tool_use"]
        if not uses:
            break
        raw.append(" ")
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
            results.append({"type": "tool_result", "tool_use_id": u.id, "content": json.dumps(model_result(r), default=str)[:12000]})
        msgs.append({"role": "user", "content": results})
    text = " ".join(said).strip()
    allowed |= await _basket_amounts(ctx)
    bad = guard_check("".join(raw), allowed, await _anything_booked(ctx))
    guard_log = list(bad) + [f"internal dropped: {x}" for x in internal_log]
    if bad:   # once: back to the model to rewrite — honestly (Sasha 205: no length rewrite; a safety trim below)
        spoken = " ".join(said).strip()
        msgs.append({"role": "user", "content": "[guard] Your last reply can't be sent: " + "; ".join(bad)
                     + ". Rewrite it in the same voice using only facts and prices from tool results."
                     + (f" You have ALREADY said aloud: “{spoken}”. Reply with ONLY what you say next, carrying on from it (nothing "
                        "it already says) — or an empty reply if that's enough." if spoken else " Reply with the rewritten text only.")})
        r = await client.messages.create(model=FAST_MODEL, max_tokens=400, system=system_now(), messages=msgs)
        new = drop_internal("".join(b.text for b in r.content if b.type == "text").strip())
        bad2 = guard_check(new, allowed, await _anything_booked(ctx))
        new = new if not bad2 else guard_strip(new, bad2)
        if said and opener_of(new):
            new = strip_openers(new)
        # Sasha 210 · what she said stays said: the rewrite only carries on from it (never a sentence twice)
        already = {_norm(x) for t_ in said for x in re.split(r"(?<=[.!?])\s+", t_)}
        rest = " ".join(x for x in re.split(r"(?<=[.!?])\s+", new) if x.strip() and _norm(x) not in already) if spoken else new
        text = f"{spoken} {rest}".strip() if spoken else new
        guard_log += [f"rewritten{' then stripped: ' + '; '.join(bad2) if bad2 else ''}"]
        yield {"type": "replace", "text": text, "speak": bool(held and rest), "say": rest}
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


_FACTY = re.compile(r"(?i)[\d€$£]|\b(book(?:ed|ing)?|reserv\w*|confirm\w*|paid|payment|pay|price\w*|cost\w*|ticket\w*|cheap\w*|"
                    r"expensive|deal|guarantee\w*|promise\w*|euros?|dollars?|free)\b")
_USED: Dict[str, List[str]] = {}   # session → the acknowledgements already said (never twice in a conversation)


def _norm(t: str) -> str:
    return re.sub(r"[^a-z ]", "", (t or "").lower()).strip()


def filler_ok(line: str, used: List[str], openers: Optional[set] = None) -> bool:
    """Sasha 205/210 · an acknowledgement may be said: short, no fact (no number, price, booking, confirmation, promise), new,
    never her internals or a disclaimer, never opening the way her answers do, never with an opener already used."""
    t = (line or "").strip()
    o = opener_of(t)
    first = (re.match(r"[A-Za-z']+", t) or [""])[0].lower()
    return (bool(t) and len(t.split()) <= 16 and not _FACTY.search(t) and "?" not in t and not _INTERNAL.search(t)
            and first not in _ANSWER_STYLE and not (o and o in (openers or set()))
            and _norm(t) not in {_norm(u) for u in used})


# Sasha 210 · the acknowledgement fits what she's doing — short and plain, never a promise or a performance
FILLERS = {
    "propose_trip": ["Let me put that together.", "Give me a moment to pull it all together.", "Let me sketch that out.", "Bear with me while I put it together."],
    "search_flights": ["Let me look at the flights.", "Let me see what's flying.", "One moment, checking the flights."],
    "choose_offer": ["Let me swap that in.", "One moment, changing that.", "Swapping that in now."],
    "swap_stay": ["Let me change that.", "Changing the stay now."],
    "search_stays": ["Let me look at places to stay.", "Let me see where you could stay."],
    "hold_booking": ["Let me check everything.", "One moment while I check it all.", "Let me go over everything."],
    "save_travellers": ["Noting those down.", "One moment, saving those."],
    "book": ["Sending it to your phone.", "On its way to your phone now."],
    "get_total": ["Let me add it up.", "One moment, adding it up."],
    "get_status": ["Let me check.", "Let me take a look."],
    "get_trip": ["Let me take a look.", "Let me check."],
    "search_venues": ["Let me find some places.", "Let me see what's around."],
    "": ["One moment.", "Let me see.", "Mm, let me think.", "Bear with me a second.", "Let me have a look."],
    "still": ["Nearly there.", "Almost there.", "Just pulling the last bits together."],   # a long piece of work, once
}


async def make_filler(message: str, doing: str, session: Optional[str]) -> str:
    """The acknowledgement for what she's about to do (a tool's name, or "" while she thinks): never twice in a
    conversation, never an opener she's used; empty when every fitting line is spent (silence over repetition)."""
    used = _USED.setdefault(session or "-", [])
    openers = _OPENERS.setdefault(session or "-", set())
    for line in FILLERS.get(doing or "", []) + (FILLERS[""] if doing != "still" else []):
        if filler_ok(line, used, openers):
            used.append(line)
            del used[:-60]
            return line
    return ""


async def turn_with_quiver(account: str, message: str, history: List[dict], session: Optional[str]) -> AsyncIterator[dict]:
    """turn(), never silent — and ONE voice (Sasha 210): if nothing is ready to say after QUIVER_AFTER_S, what she has
    written so far is spoken if it holds a full sentence; otherwise ONE short acknowledgement (written fresh, never a fact,
    never twice, never an opener she's used), which the answer then continues (turn() is told it was said)."""
    import asyncio
    q: "asyncio.Queue" = asyncio.Queue()
    voice: dict = {}
    sess = session or "-"

    async def produce():
        try:
            async for ev in turn(account, message, history, session, voice):
                await q.put(ev)
        except Exception as e:
            log.error("[agent] turn failed: %s: %s", type(e).__name__, e)
            await q.put({"type": "error", "message": "Sorry — could you say that once more?"})
        await q.put(None)
    task = asyncio.create_task(produce())
    t0 = time.perf_counter()
    first_sound, decided, last_sound, still = None, False, None, False
    try:
        while True:
            now = time.perf_counter()
            wait = (max(0.05, QUIVER_AFTER_S - (now - t0)) if not decided
                    else max(0.05, STILL_AFTER_S - (now - last_sound)) if (last_sound and not still and voice.get("working")) else None)
            try:
                ev = await asyncio.wait_for(q.get(), timeout=wait)
            except asyncio.TimeoutError:
                if decided:   # a long piece of work after she spoke: ONE plain "nearly there", never more
                    still = True
                    line = await make_filler(message, "still", session)
                    if line:
                        last_sound = time.perf_counter()
                        yield {"type": "filler", "text": line, "why": "still working"}
                    continue
                decided = True
                if voice.get("text_started"):   # she's already writing: her own words go out as soon as a sentence is whole
                    voice["flush_now"] = True
                    continue
                line = await make_filler(message, voice.get("tool") or "", session)   # nothing written yet: what she's doing, said plainly
                if line and not voice.get("spoke"):
                    voice["filler"] = line
                    o = opener_of(line)
                    if o:
                        _OPENERS.setdefault(sess, set()).add(o)
                    first_sound = first_sound or int((time.perf_counter() - t0) * 1000)
                    last_sound = time.perf_counter()
                    yield {"type": "filler", "text": line, "why": "silence"}
                continue
            if ev is None:
                break
            if ev["type"] == "tool_start":
                voice["tool"], voice["working"] = ev.get("name"), True
            elif ev["type"] == "tool":
                voice["working"] = False
            if ev["type"] == "say":
                decided = True
                last_sound = time.perf_counter()
                voice["spoke"] = True
                first_sound = first_sound or int((time.perf_counter() - t0) * 1000)
            if ev["type"] == "done":
                ev = {**ev, "ms": {**(ev.get("ms") or {}), "first_sound_server": first_sound, "fillers": int(bool(voice.get("filler")))}}
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
            yield f"data: {json.dumps({'type': 'error', 'message': 'Sorry — could you say that once more?'})}\n\n"
    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


__all__ = ["router", "turn", "turn_with_quiver", "make_filler", "filler_ok", "opener_of", "strip_openers", "clean_for_model", "drop_internal", "flight_card", "stays_card", "render", "RENDER", "KINDS", "FAST_MODEL", "guard_check", "guard_strip", "tools_for_model", "system_prompt", "MODEL"]
