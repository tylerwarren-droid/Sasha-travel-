"""Sasha 275 · S1 MEASURE (CTO plan, "Protecting Sasha" + S1) — OBSERVATION ONLY: nothing here changes how she behaves.

ONE SOURCE PER FACT (root test, scratchpad s275/root.md):
  · what happened in a booking  AgAPI's events as Sasha received them — every venue.* answer through the one transport
                                (agapi_route.post → agapi_op); after G1, its execution-event log, through events_of() alone
  · what Sasha did              her own records — each tool call (agapi.v0.call → tool), each turn (the /api/agent/turn stream
                                → observe), each model step's usage (sasha.turn → usage)
  · what the person experienced the page's own clock (POST /api/agent/timing → client)
THE STORE (public.sasha_measures, sasha-prod) IS A DERIVED COPY:
  · source  the refs above (ids, timestamps, enums) — never content, names, phones, emails or messages
  · version every row: mv = MEASURE_VERSION, sasha = the commit, agapi = the AgAPI target/version that served it
  · invalidated: a booking row is re-derived (derive()) whenever a newer event for it arrives, or MEASURE_VERSION changes; a turn
    row is written once, at the turn's end
  · NEVER AN AUTHORITY: nothing that decides her behaviour reads it (tests.test_s275 pins who may import read_*). Writes go on a
    queue drained by one background writer: a turn never waits on the store, and a failure is logged, never raised.
PRIVACY (counsel): every person/session/act id is hashed (sha256, a server-side pepper); the venue is its listing id (a business)
and its category word. Rows expire after RETENTION_DAYS (90); the daily job deletes them and says how many.
"""
from __future__ import annotations

import asyncio
import contextvars
import hashlib
import json
import logging
import os
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

log = logging.getLogger("agapi.measure")

MEASURE_VERSION = 1
RETENTION_DAYS = 90
STAGES = ("venue", "channel", "filled", "submitted", "confirmed")   # row 1054: how far she got
#: why she stopped — one word each (the booking rules' say_key, a tool's error code or result status, mapped here, once)
STOP_OF = {
    "prepared_link_captcha": "captcha", "captcha": "captcha", "needs_sign_in": "sign_in", "sign_in": "sign_in", "payment": "payment",
    "platform": "platform_handover", "page_link": "platform_handover", "handover": "platform_handover", "prepared_link": "prefilled_link",
    "not_a_booking_form": "unfamiliar_field", "unfamiliar_field": "unfamiliar_field", "cant_read": "unfamiliar_field",
    "no_channel": "no_channel", "no_route": "no_channel", "no_link": "no_channel",
    "platform_blocked": "platform_blocked", "blocked": "platform_blocked", "not_permitted": "policy_not_permitted",
    "not_allowed": "policy_not_permitted", "not_live": "policy_not_permitted", "no_real_sends": "policy_not_permitted",
    "draft_message": "guest_session", "guest": "guest_session", "calls_cap": "calls_cap", "too_soon": "too_soon",
    "declined": "venue_declined", "refused": "venue_declined", "failed": "failed", "cancelled": "cancelled",
    "no_answer": "no_answer", "expired": "unresolved", "unknown": "unresolved", "proposed": "venue_proposed_other",
}
FINAL_OUTCOME = {"confirmed": "confirmed", "booked": "confirmed", "declined": "refused", "refused": "refused", "failed": "refused",
                 "not_allowed": "refused", "cancelled": "cancelled", "expired": "unresolved", "unknown": "unresolved"}
BOOKING_TOOLS = ("read_booking_route", "hold_venue", "book_venue", "cancel_venue", "answer_card", "call_again")
SUBMIT_OPS = ("venue.submit_booking", "venue.call_again", "venue.prepare_booking")

_PEPPER: Optional[bytes] = None
_TURN: contextvars.ContextVar = contextvars.ContextVar("measure_turn", default=None)
_CID: contextvars.ContextVar = contextvars.ContextVar("measure_cid", default=None)
_BOOKINGS: Dict[str, dict] = {}       # cid → the booking row being derived (this process)
_OF: Dict[str, str] = {}              # (account|place) / prepared id / act id → cid
_LAST: Dict[str, str] = {}            # account → the cid of its latest booking request (a yes carries no place: it is THAT one's)
_Q: Optional[asyncio.Queue] = None
_WRITER: Optional[asyncio.Task] = None
_STATS = {"queued": 0, "written": 0, "failed": 0, "dropped": 0, "observe_us": 0, "observe_n": 0}


# ── ids, hashed ───────────────────────────────────────────────────────────────────────────────────────────────────────────────
def _pepper() -> bytes:
    global _PEPPER
    if _PEPPER is None:   # derived from a secret the service already holds — never printed, never stored
        seed = os.getenv("SASHA_MEASURE_PEPPER") or os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("DATABASE_URL") or "dev-only"
        _PEPPER = hashlib.sha256(("sasha-measure|" + seed).encode()).digest()
    return _PEPPER


def h(x: Any) -> Optional[str]:
    """An id as the measures keep it: sha256(pepper + id), 24 hex. None stays None."""
    if x is None or x == "":
        return None
    return hashlib.sha256(_pepper() + str(x).encode()).hexdigest()[:24]


def commit() -> str:
    return (os.getenv("RAILWAY_GIT_COMMIT_SHA") or os.getenv("SASHA_COMMIT") or "dev")[:12]


def _now() -> float:
    return time.time()


# ── the writer: one queue, one background task — a turn never waits on the store ─────────────────────────────────────────────
def _queue() -> Optional[asyncio.Queue]:
    global _Q, _WRITER
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return None
    if _Q is None or _WRITER is None or _WRITER.done():
        _Q = asyncio.Queue(maxsize=5000)
        _WRITER = loop.create_task(_drain())
    return _Q


def _put(kind: str, rid: str, data: dict, agapi: Optional[str] = None) -> None:
    q = _queue()
    if q is None:
        return
    row = {"id": rid, "kind": kind, "at": datetime.now(timezone.utc), "data": data, "mv": MEASURE_VERSION, "sasha": commit(),
           "agapi": agapi}
    try:
        q.put_nowait(row)
        _STATS["queued"] += 1
    except asyncio.QueueFull:
        _STATS["dropped"] += 1


WRITE: Any = None   # tests replace it: async (row) -> None


async def _write(row: dict) -> None:
    if WRITE is not None:
        return await WRITE(row)
    from agapi import s2_memory as M
    run = M._run()
    if run is None:   # never counted as written: no store is a failure the writer logs
        raise RuntimeError("no store")
    await run(lambda c: c.execute(
        "insert into sasha_measures (id, kind, at, day, data, mv, sasha, agapi, expires_at) "
        "values ($1, $2, $3, ($3 at time zone 'Europe/Madrid')::date, $4::jsonb, $5, $6, $7, $3 + make_interval(days => $8)) "
        "on conflict (id) do update set data = excluded.data, at = excluded.at, day = excluded.day, mv = excluded.mv, "
        "sasha = excluded.sasha, agapi = coalesce(excluded.agapi, sasha_measures.agapi)",
        row["id"], row["kind"], row["at"], json.loads(json.dumps(row["data"], default=str)), row["mv"], row["sasha"], row["agapi"],
        RETENTION_DAYS))


_rehydrating = False


async def _rehydrate(job: dict) -> None:
    global _rehydrating
    from agapi import s2_memory as M
    run = M._run()
    if run is None:
        return
    ha = h(job["act"])
    r = await run(lambda c: c.fetchrow("select data from sasha_measures where kind = 'booking' and data->'acts' ? $1 order by at desc limit 1", ha))
    if not r:
        return
    d = r["data"] if isinstance(r["data"], dict) else json.loads(r["data"])
    src = d.get("_src")
    if not isinstance(src, dict) or not src.get("cid"):
        return
    _BOOKINGS[src["cid"]] = {**src, "closed": False}
    for a in src.get("acts") or []:
        _OF["act:" + a] = src["cid"]
    if job.get("then"):
        job["then"](_BOOKINGS[src["cid"]])
        _save(_BOOKINGS[src["cid"]])
        return
    _rehydrating = True
    try:
        agapi_op(job["op"], job["body"], job["env"], job["ms"], job["url"], job["version"])
    finally:
        _rehydrating = False


async def _drain() -> None:
    warned = False
    while True:
        row = await _Q.get()
        try:
            if "_rehydrate" in row:
                await asyncio.wait_for(_rehydrate(row["_rehydrate"]), 5.0)
                continue
            await asyncio.wait_for(_write(row), 5.0)
            _STATS["written"] += 1
        except Exception as e:   # the store missing (before its SQL is applied), or down: logged once, never raised
            _STATS["failed"] += 1
            if not warned:
                log.warning("[measure] not stored (%s) — measuring goes on; nothing about her changes", type(e).__name__)
                warned = True


async def flush(timeout: float = 5.0) -> None:
    """Tests and the gate: wait until the queue is written."""
    end = time.time() + timeout
    while _Q is not None and not _Q.empty() and time.time() < end:
        await asyncio.sleep(0.02)
    await asyncio.sleep(0.05)


# ── TURNS: one row per turn, every surface, failed ones included ─────────────────────────────────────────────────────────────
def turn_start(account: Optional[str], session: Optional[str], surface: str, channel: Optional[str] = None) -> dict:
    t = {"tid": uuid.uuid4().hex[:16], "account": h(account), "session": h(session), "surface": surface,
         "channel": channel if channel in ("voice", "text", "tap", "chip") else "text", "t0": time.perf_counter(), "at": _now(),
         "first_visible_ms": None, "done_ms": None, "error": None, "tools": [], "usage": {}, "places": 0, "searches": 0,
         "cids": [], "agapi_ops": 0, "ops": []}   # Sasha 299 · ops: each AgAPI call's name, start and ms (the turn's timeline)
    _TURN.set(t)
    return t


def current() -> Optional[dict]:
    return _TURN.get()


def since() -> Optional[int]:
    """Sasha 299 · ms since this turn began (the timeline's clock), or None outside a turn."""
    t = _TURN.get()
    return int((time.perf_counter() - t["t0"]) * 1000) if t is not None else None


_VISIBLE = ('"type": "hold"', '"type": "text"', '"type": "replace"', '"type": "render"', '"type": "say"')


async def observe(stream, account: Optional[str], session: Optional[str], surface: str, channel: Optional[str] = None):
    """Wraps the /api/agent/turn stream: yields EXACTLY what it yields (byte for byte), noting when the first visible event left
    and when it ended; the row is queued after the last byte."""
    t = turn_start(account, session, surface, channel)
    try:
        async for chunk in stream:
            t0 = time.perf_counter()
            s = chunk if isinstance(chunk, str) else ""
            if t["first_visible_ms"] is None and any(k in s for k in _VISIBLE):
                t["first_visible_ms"] = int((t0 - t["t0"]) * 1000)
            if '"type": "error"' in s and t["error"] is None:
                t["error"] = "error"
            if '"type": "done"' in s:
                t["done_ms"] = int((t0 - t["t0"]) * 1000)
            _STATS["observe_us"] += int((time.perf_counter() - t0) * 1e6)
            _STATS["observe_n"] += 1
            yield chunk
    finally:
        turn_end(t)


def turn_end(t: dict) -> None:
    if t.get("_ended"):
        return
    t["_ended"] = True
    if t["done_ms"] is None:
        t["error"] = t["error"] or "no_done"
        t["done_ms"] = int((time.perf_counter() - t["t0"]) * 1000)
    data = {k: v for k, v in t.items() if not k.startswith("_") and k not in ("t0",)}
    _put("turn", "t:" + t["tid"], data)


def usage(model: Optional[str], u: Any) -> None:
    """One model step's tokens, for the turn running now (sasha.turn calls it after each step)."""
    t = _TURN.get()
    if t is None or u is None:
        return
    m = t["usage"].setdefault(str(model or "?"), {"calls": 0, "in": 0, "out": 0, "cw": 0, "cr": 0})
    m["calls"] += 1
    m["in"] += int(getattr(u, "input_tokens", 0) or 0)
    m["out"] += int(getattr(u, "output_tokens", 0) or 0)
    m["cw"] += int(getattr(u, "cache_creation_input_tokens", 0) or 0)
    m["cr"] += int(getattr(u, "cache_read_input_tokens", 0) or 0)
    for c in t["cids"]:   # cost per booking: the turn's tokens go to the bookings it worked on
        b = _BOOKINGS.get(c)
        if b is not None:
            bm = b["cost"]["tokens"].setdefault(str(model or "?"), {"in": 0, "out": 0, "cw": 0, "cr": 0})
            for k, f in (("in", "input_tokens"), ("out", "output_tokens"), ("cw", "cache_creation_input_tokens"), ("cr", "cache_read_input_tokens")):
                bm[k] += int(getattr(u, f, 0) or 0)


def places_read(n: int = 1) -> None:
    t = _TURN.get()
    if t is not None:
        t["places"] += n
        for c in t["cids"]:
            if c in _BOOKINGS:
                _BOOKINGS[c]["cost"]["places"] += n


def client(tid: str, body: dict, account: Optional[str]) -> None:
    """The page's own clock for one turn (end of speech → first audible; send → first visible; → reply done)."""
    if not tid or not isinstance(body, dict):
        return
    keep = {k: (int(body[k]) if isinstance(body.get(k), (int, float)) and 0 <= body[k] < 600000 else None)
            for k in ("first_audible_ms", "first_visible_ms", "done_ms")}
    data = {"tid": str(tid)[:32], "account": h(account), "channel": body.get("channel") if body.get("channel") in ("voice", "text", "tap", "chip") else None,
            "surface": "s2" if body.get("surface") == "s2" else "s1", **keep}
    _put("client", "c:" + str(tid)[:32], data)


# ── BOOKINGS: one row per request, from the person's request through the yes, the action and the outcome ────────────────────
def _key(account: Optional[str], place: Optional[str]) -> str:
    return f"{account}|{place or '?'}"


def _booking(account: Optional[str], place: Optional[str], venue_type: Optional[str], surface: str) -> dict:
    k = _key(account, place)
    cid = _OF.get(k)
    b = _BOOKINGS.get(cid) if cid else None
    if b is None or b.get("closed"):
        cid = uuid.uuid4().hex[:20]
        b = {"cid": cid, "account": h(account), "venue": place, "venue_type": venue_type, "surface": surface, "started": _now(),
             "stages": {}, "stop": None, "yes_at": None, "action_at": None, "outcome": None, "outcome_at": None, "acts": [],
             "submits": 0, "duplicates": 0, "cancel_at": None, "after_cancel": 0, "profile_ms": [], "submit_ms": [],
             "cost": {"tokens": {}, "places": 0, "searches": 0, "call_minutes": 0.0}, "closed": False, "agapi": None}
        _BOOKINGS[cid] = b
        _OF[k] = cid
    if venue_type and not b.get("venue_type"):
        b["venue_type"] = venue_type
    t = _TURN.get()
    if t is not None and cid not in t["cids"]:
        t["cids"].append(cid)
    return b


def _reach(b: dict, stage: str) -> None:
    if stage not in b["stages"]:
        b["stages"][stage] = _now()


def _stop(b: dict, why: Optional[str]) -> None:
    w = STOP_OF.get(str(why or ""), None) if why else None
    if w and not b.get("stop"):
        b["stop"] = {"why": w, "at": _now(), "after": max((s for s in STAGES if s in b["stages"]), key=STAGES.index, default=None)}


def _save(b: dict) -> None:
    # the derivation's own source state rides along (_src): after a restart, a later event for one of its acts re-derives it
    _put("booking", "b:" + b["cid"], {**derive(b), "_src": {k: v for k, v in b.items() if k != "closed"}}, agapi=b.get("agapi"))


def derive(b: dict) -> dict:
    """THE one derivation of a booking's measures from its kept refs — re-run whenever a newer event arrives (or mv changes)."""
    st = b["stages"]
    reached = [s for s in STAGES if s in st]
    out = {k: b[k] for k in ("cid", "account", "venue", "venue_type", "surface", "stop", "outcome", "submits", "duplicates",
                             "after_cancel", "cost")}
    out["acts"] = list(b["acts"])   # already hashed (_bind)
    out["furthest"] = reached[-1] if reached else None
    out["stages_ms"] = {s: int((st[s] - b["started"]) * 1000) for s in reached}
    out["yes_to_action_ms"] = int((b["action_at"] - b["yes_at"]) * 1000) if b.get("yes_at") and b.get("action_at") else None
    out["yes_to_outcome_s"] = int(b["outcome_at"] - b["yes_at"]) if b.get("yes_at") and b.get("outcome_at") else None
    out["profile_ms"] = b["profile_ms"][-5:]
    out["submit_ms"] = b["submit_ms"][-5:]
    out["submitted"] = "submitted" in st
    out["confirmed"] = b.get("outcome") == "confirmed"
    return out


def _venue_of(args: dict, out: Any) -> tuple:
    res = out if isinstance(out, dict) else {}
    card = res.get("card") if isinstance(res.get("card"), dict) else {}
    place = args.get("place_id") or card.get("place_id") or res.get("place_id")
    if not place:
        nm = args.get("name") or args.get("venue") or res.get("venue")
        place = ("name:" + h(str(nm).strip().lower())) if nm else None
    vtype = card.get("google_type") or card.get("type") if isinstance(card.get("type") or card.get("google_type"), str) else None
    return place, vtype


def tool(ctx: Any, name: str, args: dict, res: dict, ms: int) -> None:
    """agapi.v0.call, after every tool call (every surface). Bookings advance their stages; every call is on the turn."""
    try:
        t = _TURN.get()
        if t is not None:
            t["tools"].append({"tool": name, "ok": bool(res.get("ok")), "ms": ms,
                               **({"code": (res.get("error") or {}).get("code")} if not res.get("ok") else {})})
            if name == "search_venues":
                t["searches"] += 1
        if name not in BOOKING_TOOLS:
            return
        out = res.get("result") if res.get("ok") else None
        act0 = (args or {}).get("act_id") or ((out or {}).get("act_id") if isinstance(out, dict) else None)
        if name == "cancel_venue" and act0:   # a cancel names its booking by the act: the same request's row, never a new one
            status = (out or {}).get("status") if isinstance(out, dict) else None
            _with_act(act0, lambda b: _cancelled(b, status))
            return
        place, vtype = _venue_of(args or {}, out)
        acct = getattr(ctx, "account", None)
        last = _BOOKINGS.get(_LAST.get(str(acct)) or "")
        if place is None and name in ("book_venue", "answer_card", "call_again") and last is not None and not last.get("closed"):
            b = last   # their yes (or the card's tap) answers the read-back they were shown — the same request
        else:
            b = _booking(acct, place, vtype, getattr(ctx, "surface", "s1"))
        _LAST[str(acct)] = b["cid"]
        _CID.set(b["cid"])
        if t is not None and t["searches"]:
            b["cost"]["searches"] += t["searches"]
        _reach(b, "venue")
        status = (out or {}).get("status") if isinstance(out, dict) else None
        rules = (out or {}).get("rules") if isinstance(out, dict) else None
        say_key = (rules or {}).get("say_key") if isinstance(rules, dict) else None
        if not res.get("ok"):
            _stop(b, (res.get("error") or {}).get("code"))
        elif name == "read_booking_route":
            b["profile_ms"].append(ms)
            if (out or {}).get("routes"):
                _reach(b, "channel")
            else:
                _stop(b, "no_channel")
        elif name == "hold_venue":
            _reach(b, "channel")
            if status in ("awaiting_yes", "yes_heard"):
                _reach(b, "filled")
            elif status in ("draft_message",):
                _reach(b, "filled")
                _stop(b, "draft_message")
            elif status in ("page_link", "prepared"):
                _stop(b, say_key or "page_link")
            elif status == "refused":
                _stop(b, say_key or "not_permitted")
            if say_key in ("not_live", "no_real_sends", "no_channel", "platform", "prepared_link_captcha", "calls_cap", "too_soon"):
                _stop(b, say_key)
        elif name in ("book_venue", "answer_card", "call_again"):
            b["yes_at"] = b.get("yes_at") or _now()
            if status in ("sent", "requested", "calling", "confirmed", "call_and_email", "booked"):
                _reach(b, "channel"); _reach(b, "filled"); _reach(b, "submitted")
                b["submit_ms"].append(ms)
                if b.get("cancel_at"):
                    b["after_cancel"] += 1
            if status == "confirmed":
                _reach(b, "confirmed")
                b["outcome"], b["outcome_at"] = "confirmed", _now()
            elif status in ("nothing_waiting",):
                pass
            act = (out or {}).get("act_id") if isinstance(out, dict) else None
            if act:
                _bind(b, act)
        elif name == "cancel_venue":
            b["cancel_at"] = b.get("cancel_at") or _now()
            if status in ("cancelled", "sent", "requested"):
                b["outcome"], b["outcome_at"] = "cancelled", _now()
        _save(b)
    except Exception as e:   # observation only: never in her way
        log.info("[measure] tool not measured: %s", type(e).__name__)


def _bind(b: dict, act: str) -> None:
    ha = h(act)
    if ha not in b["acts"]:
        b["acts"].append(ha)
    _OF["act:" + ha] = b["cid"]


def _cancelled(b: dict, status: Optional[str]) -> None:
    b["cancel_at"] = b.get("cancel_at") or _now()
    if status in ("cancelled", "sent", "requested", "confirmed"):
        b["outcome"], b["outcome_at"] = "cancelled", _now()


def _with_act(act: str, fn) -> None:
    """Apply fn to the booking row of this act — from this process, or (after a restart) found in the store by the writer."""
    cid = _OF.get("act:" + str(h(act)))
    b = _BOOKINGS.get(cid) if cid else None
    if b is not None:
        fn(b)
        _save(b)
        return
    q = _queue()
    if q is not None:
        try:
            q.put_nowait({"_rehydrate": {"act": act, "then": fn}})
        except asyncio.QueueFull:
            _STATS["dropped"] += 1


def _is_link(u: Any) -> bool:
    return str(u or "").startswith(("https://", "http://", "mailto:", "tel:"))


def decision_of(op: str, result: dict) -> dict:
    """Sasha 289 · the first real booking (Mano Santa, 26 Oct) reached the floor and S2 kept no copy of what AgAPI had decided — it had
    to be replayed. AgAPI's decision as received, on the booking's row: route, channel, sender, how far, and WHETHER each way to take
    it carried a link (never the link itself, never a number)."""
    d = result.get("decision") or {}
    b = d.get("button") if isinstance(d.get("button"), dict) else {}
    out = {"op": op, **{k: d.get(k) for k in ("route", "channel", "sender", "how_far")}, "button_link": _is_link(b.get("link")),
           "button_sends": bool(b.get("sends")),
           "option_links": sum(1 for o in d.get("options") or [] if isinstance(o, dict) and _is_link(o.get("link")))}
    if op == "venue.prepare_booking":
        out["person_send"] = _is_link((result.get("person_send") or {}).get("whatsapp"))
    return out


def agapi_op(op: str, body: dict, env: Any, ms: int, url: str, version: Optional[str] = None) -> None:
    """agapi_route.post, after EVERY AgAPI call (the one transport). Bookings see their acts' events here: a submit (and its
    duplicates), a status (the outcome), a profile lookup; an action after the person cancelled is counted."""
    try:
        t = _TURN.get()
        if t is not None:
            t["agapi_ops"] += 1
            if len(t.setdefault("ops", [])) < 40:   # Sasha 299 · the timeline: which AgAPI call, when it began, how long (no contents)
                t["ops"].append({"op": op, "at": int((time.perf_counter() - t["t0"]) * 1000) - ms, "ms": ms})
        if not op.startswith("venue."):
            return
        result = env.get("result") if isinstance(env, dict) and env.get("ok") else None
        act = (body or {}).get("act_id") or ((result or {}).get("act_id") if isinstance(result, dict) else None)
        cid = _OF.get("act:" + str(h(act))) if act else None
        cid = cid or _CID.get()
        b = _BOOKINGS.get(cid) if cid else None
        if b is None:
            if act and not _rehydrating:   # an act from before a restart: its row is found by the writer, then this event applied
                q = _queue()
                if q is not None:
                    try:
                        q.put_nowait({"_rehydrate": {"act": act, "op": op, "body": body, "env": env, "ms": ms, "url": url, "version": version}})
                    except asyncio.QueueFull:
                        _STATS["dropped"] += 1
            return
        b["agapi"] = version or ("sandbox" if "sandbox" in (url or "") else "live")
        if act:
            _bind(b, act)
        if op in ("venue.submit_booking", "venue.call_again") and isinstance(env, dict) and env.get("ok"):
            b["submits"] += 1
            b["action_at"] = b.get("action_at") or _now()
            if b["submits"] > 1 and op == "venue.submit_booking":
                b["duplicates"] += 1   # a second submit for the same request — should never happen (must be 0)
            if b.get("cancel_at"):
                b["after_cancel"] += 1
        if op == "venue.booking_status" and isinstance(result, dict):
            state = str(result.get("state") or "")
            if state in ("sent", "replied", "calling"):
                _reach(b, "submitted")
            fin = FINAL_OUTCOME.get(state)
            if fin and b.get("outcome") != fin:
                b["outcome"], b["outcome_at"] = fin, _now()
                if fin == "confirmed":
                    _reach(b, "confirmed")
                else:
                    _stop(b, state)
            elif state == "no_answer":
                _stop(b, "no_answer")
        if op == "venue.profile":
            b["profile_ms"].append(ms)
        if op in ("venue.profile", "venue.prepare_booking") and isinstance(result, dict) and isinstance(result.get("decision"), dict):
            b["decisions"] = (b.get("decisions") or [])[-4:] + [decision_of(op, result)]   # Sasha 289 · read on the row, never replayed
        if op == "venue.cancel_booking" and isinstance(env, dict) and env.get("ok") and (body or {}).get("act_id"):
            _cancelled(b, (result or {}).get("status") or (result or {}).get("state"))
        _save(b)
    except Exception as e:
        log.info("[measure] agapi op not measured: %s", type(e).__name__)


# ── READING (the founder page, the daily summary) — never by code that decides behaviour ─────────────────────────────────────
def _pct(xs: List[float], p: float) -> Optional[int]:
    xs = sorted(x for x in xs if isinstance(x, (int, float)))
    if not xs:
        return None
    return int(xs[min(len(xs) - 1, max(0, int(round(p / 100 * len(xs) + 0.5)) - 1))])


def summarise(rows: List[dict]) -> dict:
    """The week's (or a day's) table from stored rows: responsiveness p50/p95/p99, submission/outcome timings, the two rates,
    how far she got by venue type and by stop reason, duplicates and actions after a cancel, cost per (confirmed) booking."""
    turns = [r["data"] for r in rows if r["kind"] == "turn"]
    clients = {r["data"].get("tid"): r["data"] for r in rows if r["kind"] == "client"}
    books = [r["data"] for r in rows if r["kind"] == "booking"]
    p3 = lambda xs: {"p50": _pct(xs, 50), "p95": _pct(xs, 95), "p99": _pct(xs, 99), "n": len([x for x in xs if x is not None])}
    voice = [c.get("first_audible_ms") for c in clients.values() if c.get("channel") == "voice"]
    text_vis = [c.get("first_visible_ms") for c in clients.values() if c.get("channel") != "voice"] or [t.get("first_visible_ms") for t in turns]
    routine = [t.get("done_ms") for t in turns if not any(x["tool"] in BOOKING_TOOLS for x in t.get("tools") or [])]
    submitted = [b for b in books if b.get("submitted")]
    confirmed = [b for b in books if b.get("confirmed")]
    by = lambda key: {k: {"n": len(v), "furthest": {s: sum(1 for b in v if b.get("furthest") == s) for s in STAGES}}
                      for k, v in _group(books, key).items()}
    stops: Dict[str, int] = {}
    for b in books:
        w = (b.get("stop") or {}).get("why")
        if w:
            stops[w] = stops.get(w, 0) + 1
    tokens: Dict[str, Dict[str, int]] = {}
    for t in turns:
        for m, u in (t.get("usage") or {}).items():
            tm = tokens.setdefault(m, {"in": 0, "out": 0, "cw": 0, "cr": 0, "calls": 0})
            for k in tm:
                tm[k] += int(u.get(k, 0) or 0)
    return {
        "turns": len(turns), "bookings": len(books),
        "responsiveness": {"first_audible_voice_ms": p3(voice), "first_visible_text_ms": p3(text_vis), "routine_done_ms": p3(routine)},
        "submission": {"yes_to_action_ms": p3([b.get("yes_to_action_ms") for b in books]),
                       "profile_lookup_ms": p3([x for b in books for x in b.get("profile_ms") or []]),
                       "submit_ms": p3([x for b in books for x in b.get("submit_ms") or []])},
        "outcome": {"yes_to_outcome_s": p3([b.get("yes_to_outcome_s") for b in books]),
                    "states": {k: sum(1 for b in books if b.get("outcome") == k) for k in ("confirmed", "refused", "cancelled", "unresolved")}},
        "rates": {"submission_success": round(len(submitted) / len(books), 3) if books else None,
                  "venue_confirmation": round(len(confirmed) / len(submitted), 3) if submitted else None},
        "how_far_by_venue_type": by("venue_type"), "stop_reasons": dict(sorted(stops.items(), key=lambda kv: -kv[1])),
        "duplicates_sent": sum(int(b.get("duplicates") or 0) for b in books), "actions_after_cancel": sum(int(b.get("after_cancel") or 0) for b in books),
        "cost": {"tokens_by_model": tokens, "places_reads": sum(int(t.get("places") or 0) for t in turns),
                 "searches": sum(int(t.get("searches") or 0) for t in turns),
                 "call_minutes": round(sum(float((b.get("cost") or {}).get("call_minutes") or 0) for b in books), 1),
                 "per_booking_tokens": _per(books, tokens, len(books)), "per_confirmed_tokens": _per(books, tokens, len(confirmed))},
        "measuring_overhead_us_per_event": int(_STATS["observe_us"] / _STATS["observe_n"]) if _STATS["observe_n"] else None,
    }


def _group(books: List[dict], key: str) -> Dict[str, List[dict]]:
    g: Dict[str, List[dict]] = {}
    for b in books:
        g.setdefault(str(b.get(key) or "unknown"), []).append(b)
    return g


def _per(books: List[dict], tokens: Dict[str, Dict[str, int]], n: int) -> Optional[Dict[str, int]]:
    if not n:
        return None
    return {m: int((u["in"] + u["out"] + u["cw"] + u["cr"]) / n) for m, u in tokens.items()}


async def read_rows(days: int = 7) -> List[dict]:
    from agapi import s2_memory as M
    run = M._run()
    if run is None:
        return []
    rows = await run(lambda c: c.fetch("select kind, at, day, data, mv, sasha, agapi from sasha_measures where at > now() - make_interval(days => $1) "
                                       "and kind in ('turn','client','booking') order by at", int(days)))
    return [{"kind": r["kind"], "at": r["at"], "day": str(r["day"]), "data": r["data"] if isinstance(r["data"], dict) else json.loads(r["data"]),
             "mv": r["mv"], "sasha": r["sasha"], "agapi": r["agapi"]} for r in rows]


async def call_minutes(days: int = 7) -> Dict[str, float]:
    """Call minutes by day (Madrid) — from Sasha's own call records (booking_calls: Bland's call_length), never copied in."""
    from agapi import s2_memory as M
    run = M._run()
    if run is None:
        return {}
    rows = await run(lambda c: c.fetch("select (created_at at time zone 'Europe/Madrid')::date as d, "
                                       "coalesce(sum(nullif(bland_details->>'call_length','')::float), 0) as m from booking_calls "
                                       "where created_at > now() - make_interval(days => $1) group by 1", int(days)))
    return {str(r["d"]): round(float(r["m"] or 0), 1) for r in rows}


async def read_week(days: int = 7) -> dict:
    rows = await read_rows(days)
    by_day: Dict[str, List[dict]] = {}
    for r in rows:
        by_day.setdefault(r["day"], []).append(r)
    try:
        mins = await call_minutes(days)
    except Exception:
        mins = {}
    week = summarise(rows)
    week["cost"]["call_minutes"] = round(sum(mins.values()), 1)
    days_out = {}
    for d, rs in sorted(by_day.items()):
        days_out[d] = summarise(rs)
        days_out[d]["cost"]["call_minutes"] = mins.get(d, 0.0)
    dailies = []
    try:
        from agapi import s2_memory as M
        run = M._run()
        if run is not None:
            ds = await run(lambda c: c.fetch("select data from sasha_measures where kind = 'daily' order by day desc limit $1", int(days)))
            dailies = [{"day": (d["data"] if isinstance(d["data"], dict) else json.loads(d["data"])).get("day"),
                        "line": (d["data"] if isinstance(d["data"], dict) else json.loads(d["data"])).get("line")} for d in ds]
    except Exception:
        dailies = []
    return {"week": week, "by_day": days_out, "daily": dailies,
            "versions": sorted({(r["sasha"], r["agapi"] or "") for r in rows}), "mv": MEASURE_VERSION, "rows": len(rows)}


# ── DAILY: the summary kept in sasha-prod (and shown on the founder page — the chat reads it there) + the 90-day deletion ───────
# Sasha 275 · the chat (16 Oct 16:37): NOTHING in AD's project — no function, no secret, no AD key; no cross-project write path.
def summary_line(day: str, s: dict) -> str:
    r, sub, out = s["responsiveness"], s["submission"], s["outcome"]
    f = lambda d: f"{d['p50']}/{d['p95']}/{d['p99']} ms (n {d['n']})" if d and d.get("n") else "no data"
    stops = ", ".join(f"{k} {v}" for k, v in list(s["stop_reasons"].items())[:4]) or "none"
    rates = s["rates"]
    return (f"SASHA MEASURE · {day} (Madrid) · S1 daily summary (observation only). {s['turns']} turns, {s['bookings']} bookings. "
            f"Voice end-of-speech→first audible p50/p95/p99 {f(r['first_audible_voice_ms'])}; first visible text {f(r['first_visible_text_ms'])}; "
            f"routine reply done {f(r['routine_done_ms'])}. Yes→action {f(sub['yes_to_action_ms'])}; profile lookup {f(sub['profile_lookup_ms'])}. "
            f"Outcomes: {out['states']}. Submission success {rates['submission_success']}, venue confirmation {rates['venue_confirmation']}. "
            f"Biggest stop reasons: {stops}. Duplicates sent {s['duplicates_sent']}, actions after a cancel {s['actions_after_cancel']} (both must be 0). "
            f"Cost: {s['cost']['places_reads']} Places reads, {s['cost']['searches']} searches, {s['cost']['call_minutes']} call minutes. "
            f"Founder page: /founder/measures.")[:1990]


async def daily(day: Optional[str] = None) -> dict:
    """Yesterday (Madrid) → its summary row (id d:<day>: the summary and its one-paragraph line); then the rows past
    RETENTION_DAYS go. Kept in sasha-prod only and shown on the founder page — never sent to another project."""
    from zoneinfo import ZoneInfo
    from agapi import s2_memory as M
    run = M._run()
    if run is None:
        return {"ok": False, "why": "no store"}
    mad = datetime.now(ZoneInfo("Europe/Madrid"))
    day = day or (mad - timedelta(days=1)).strftime("%Y-%m-%d")
    rows = await run(lambda c: c.fetch("select kind, at, day, data, mv, sasha, agapi from sasha_measures where day = $1::date and kind in ('turn','client','booking')", datetime.strptime(day, "%Y-%m-%d").date()))
    rs = [{"kind": r["kind"], "data": r["data"] if isinstance(r["data"], dict) else json.loads(r["data"])} for r in rows]
    s = summarise(rs)
    try:
        s["cost"]["call_minutes"] = (await call_minutes(3)).get(day, 0.0)
    except Exception:
        pass
    gone = await run(lambda c: c.execute("delete from sasha_measures where expires_at < now()"))
    await _write({"id": "d:" + day, "kind": "daily", "at": datetime.now(timezone.utc), "data": {"day": day, "summary": s, "line": summary_line(day, s),
                  "deleted": str(gone)}, "mv": MEASURE_VERSION, "sasha": commit(), "agapi": None})
    log.info("[measure] daily %s: %s turns, %s bookings, retention %s", day, s["turns"], s["bookings"], gone)
    return {"ok": True, "day": day, "line": summary_line(day, s), "deleted": str(gone), "turns": s["turns"], "bookings": s["bookings"]}


async def daily_forever() -> None:
    """Once an hour: after 07:00 Madrid, yesterday's summary (if not yet made)."""
    from zoneinfo import ZoneInfo
    await asyncio.sleep(60)
    while True:
        try:
            if datetime.now(ZoneInfo("Europe/Madrid")).hour >= 7:
                await daily()
        except Exception as e:
            log.warning("[measure] daily not made: %s", type(e).__name__)
        await asyncio.sleep(3600)


def stats() -> dict:
    return dict(_STATS)


__all__ = ["MEASURE_VERSION", "RETENTION_DAYS", "STAGES", "STOP_OF", "h", "observe", "turn_start", "turn_end", "usage", "places_read",
           "client", "tool", "agapi_op", "derive", "summarise", "read_week", "read_rows", "daily", "daily_forever", "summary_line", "flush", "stats"]
