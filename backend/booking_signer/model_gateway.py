"""Sasha 353 · THE MODEL GATEWAY — every model call Sasha makes, through ONE place (Tyler, 6 Nov 19:01: "drastic measures to cut this").

Found (STEP 1, measured with Anthropic's count_tokens on the requests the code builds, docs/sasha/S-353-model-gateway.md): 1.98 billion input
tokens in 30 days on Sasha's keys. Every step of a turn re-sent ~26,000 tokens (78 tool definitions ≈ 19,800 + the system prompt ≈ 6,400),
and the deploy gate ran ~400 live calls (≈ 8 M tokens) on the service's own key, 20 times on 6 Nov alone.

install() wraps the Anthropic SDK's own methods (Messages.create / .stream, sync and async, beta too) — so EVERY call, from any module, the
CTO's included, passes here; there is no client that bypasses it (tests/test_s353_gateway.py scans for any other way to reach the API).
On each call, in order:
  1 THE CAPS — a global daily cap and a per-account daily budget (tokens: input + cache write + cache read + output), kept on the record
    (sasha_measures, kind model_day — a restart never resets them); a call over either is REFUSED, loudly (ModelBudgetExceeded, logged
    as an error) — never sent.
  2 THE MODEL — Opus only where it's allowed (SASHA_MODEL_ALLOW_OPUS); every other call that asked for it runs on Sonnet.
  3 ONLY WHAT IT NEEDS — the history is the recent turns (HISTORY_TURNS), never the whole record (the running summary is the caller's,
    in its system prompt); the fixed parts (the system prompt's first block, the tool list) carry the cache mark.
  4 THE GATE'S REPLAY — SASHA_MODEL_REPLAY=replay answers from RECORDED replies (on the record: sasha_measures, kind model_replay),
    never the API — but for the gate's one tiny live check (model_health's 1-token Haiku call); =record makes them (one live run); a
    request with no recording is refused loudly.
  5 THE METER — every call's usage, by model, caller (module) and account, added to the day's record and logged.
"""
from __future__ import annotations

import asyncio
import contextvars
import hashlib
import inspect
import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

log = logging.getLogger("booking_signer.model_gateway")

ACCOUNT: contextvars.ContextVar = contextvars.ContextVar("sasha_model_account", default=None)   # set by the turn (whose call)
HISTORY_TURNS = int(os.getenv("SASHA_MODEL_HISTORY_TURNS", "8"))    # the recent turns a call carries (a turn = their message onwards)
SONNET = os.getenv("SASHA_MODEL_SONNET", "claude-sonnet-5-5")


class ModelBudgetExceeded(RuntimeError):
    """A cap was hit: the call was NOT sent. Its message says which cap, and how to raise it."""


class ReplayMissing(RuntimeError):
    """The gate replays recorded replies; this request has none (record once with SASHA_MODEL_REPLAY=record)."""


def _cap(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def global_cap() -> int:
    return _cap("SASHA_MODEL_DAILY_TOKENS", 25_000_000)


def account_cap() -> int:
    return _cap("SASHA_MODEL_ACCOUNT_DAILY_TOKENS", 2_000_000)


# ── the day's record ────────────────────────────────────────────────────────────────────────────────────────────────────

_DAY: Dict[str, Any] = {"day": None, "total": 0, "accounts": {}, "models": {}, "callers": {}, "loaded": False}   # THIS process's use
_OTHERS: Dict[str, Any] = {"total": 0, "accounts": {}, "at": None}   # every other process's use today (the service, the gate…), re-read
OTHERS_EVERY_S = 30.0
PROC = __import__("uuid").uuid4().hex[:12]   # this process's own row: processes never overwrite each other's counts
_DIRTY = {"since": None}
STORE: Any = None   # tests replace it: an object with async load(day, proc) -> [day records of OTHER processes] and save(day, proc, data)


def _today() -> str:
    return datetime.now(ZoneInfo("Europe/Madrid")).date().isoformat()


def _acct_key(account: Optional[str]) -> str:
    if not account:
        return "-"
    from agapi import measure as MS
    return MS.h(account) or "-"


async def _db(fn):
    """The gateway's OWN connection (DATABASE_URL) — never the app's store, which suites replace with fakes (found by the recording run:
    199 of 319 recordings made inside such suites had nowhere to go). One connection per use: the gate's suites run in several event
    loops, and these are few (a recording run's ~300, a usage save at most every 5 s)."""
    import asyncpg
    url = os.getenv("DATABASE_URL", "").strip().replace("postgresql+asyncpg://", "postgresql://", 1)
    if not url:
        raise RuntimeError("DATABASE_URL is not set")
    c = await asyncpg.connect(url, statement_cache_size=0, timeout=10)
    try:
        return await fn(c)
    finally:
        await c.close()


class _PgStore:
    """One row per process and day (model_day:<day>:<process>) — found live: the service and the gate each saved the whole day, the
    last writer erasing the other's use. The caps count every row."""

    async def load(self, day: str, proc: str) -> List[dict]:
        rows = await _db(lambda c: c.fetch("select data from sasha_measures where kind = 'model_day' and day = $1 and id <> $2",
                                           __import__("datetime").date.fromisoformat(day), f"model_day:{day}:{proc}"))
        return [json.loads(r["data"]) if isinstance(r["data"], str) else r["data"] for r in rows]

    async def save(self, day: str, proc: str, data: dict) -> None:
        await _db(lambda c: c.execute(
            "insert into sasha_measures (id, kind, at, day, data, mv, sasha, agapi, expires_at) values ($1, 'model_day', now(), $2::date, "
            "$3::jsonb, 0, $4, null, now() + interval '400 days') on conflict (id) do update set data = excluded.data, at = excluded.at",
            f"model_day:{day}:{proc}", __import__("datetime").date.fromisoformat(day), json.dumps(data),
            os.getenv("RAILWAY_GIT_COMMIT_SHA", "")[:12]))


def _store():
    return STORE if STORE is not None else _PgStore()


async def _ensure_day() -> None:
    d = _today()
    if _DAY["day"] != d:
        _DAY.update(day=d, total=0, accounts={}, models={}, callers={}, loaded=False)
        _OTHERS.update(total=0, accounts={}, at=None)
    if _OTHERS["at"] is None or time.monotonic() - _OTHERS["at"] >= OTHERS_EVERY_S or not _DAY["loaded"]:   # None: never read
        _DAY["loaded"] = True
        _OTHERS["at"] = time.monotonic()
        try:   # a restart, another process: the caps count what every process used today
            rows = await _store().load(d, PROC)
        except Exception as e:
            log.warning("[model_gateway] the day's other records weren't read (%s) — counting this process only", type(e).__name__)
            return
        tot, acc = 0, {}
        for r in rows or []:
            tot += int((r or {}).get("total") or 0)
            for k, v in ((r or {}).get("accounts") or {}).items():
                acc[k] = acc.get(k, 0) + int(v)
        _OTHERS.update(total=tot, accounts=acc)


def _check(account_k: str) -> None:
    g, a = global_cap(), account_cap()
    total = _DAY["total"] + _OTHERS["total"]
    if total >= g:
        msg = f"the global daily model cap is reached ({total:,} of {g:,} tokens today) — nothing was sent (SASHA_MODEL_DAILY_TOKENS)"
        log.error("[model_gateway] REFUSED: %s", msg)
        raise ModelBudgetExceeded(msg)
    used = _DAY["accounts"].get(account_k, 0) + _OTHERS["accounts"].get(account_k, 0)
    if account_k != "-" and used >= a:
        msg = (f"this account's daily model budget is reached ({used:,} of {a:,} tokens today) — nothing was sent "
               "(SASHA_MODEL_ACCOUNT_DAILY_TOKENS)")
        log.error("[model_gateway] REFUSED: %s", msg)
        raise ModelBudgetExceeded(msg)


def _meter(model: str, usage: Any, caller: str, account_k: str) -> None:
    if usage is None:
        return
    g = lambda k: int(getattr(usage, k, 0) or (usage.get(k, 0) if isinstance(usage, dict) else 0) or 0)
    parts = {"in": g("input_tokens"), "cw": g("cache_creation_input_tokens"), "cr": g("cache_read_input_tokens"), "out": g("output_tokens")}
    n = sum(parts.values())
    _DAY["total"] += n
    _DAY["accounts"][account_k] = _DAY["accounts"].get(account_k, 0) + n
    for part, key in (("models", model), ("callers", caller)):
        cur = _DAY[part].setdefault(key, {})
        cur["calls"] = cur.get("calls", 0) + 1
        for k, v in parts.items():
            cur[k] = cur.get(k, 0) + v
    log.info("[model_gateway] %s · %s · in %d · cache write %d · cache read %d · out %d · today %s", caller, model, parts["in"], parts["cw"],
             parts["cr"], parts["out"], f"{_DAY['total']:,}")
    _flush_soon()


def _flush_soon() -> None:
    if _DIRTY["since"] is not None:
        return
    _DIRTY["since"] = time.monotonic()
    try:
        asyncio.get_running_loop().call_later(5.0, lambda: asyncio.ensure_future(_flush()))
    except RuntimeError:
        _DIRTY["since"] = None


async def _flush() -> None:
    _DIRTY["since"] = None
    try:
        await _store().save(_DAY["day"], PROC, {k: _DAY[k] for k in ("total", "accounts", "models", "callers")})
    except Exception as e:
        log.warning("[model_gateway] the day's record wasn't saved (%s)", type(e).__name__)


def today() -> Dict[str, Any]:
    return {k: _DAY[k] for k in ("day", "accounts", "models", "callers")} | {"total": _DAY["total"] + _OTHERS["total"], "this_process": _DAY["total"],
                                                                           "global_cap": global_cap(), "account_cap": account_cap()}


# ── what a call carries ─────────────────────────────────────────────────────────────────────────────────────────────────

def _is_turn_start(m: dict) -> bool:
    """A user message that is their words (not a tool result) — where a turn begins, and where history may be cut."""
    if m.get("role") != "user":
        return False
    c = m.get("content")
    if isinstance(c, str):
        return True
    return isinstance(c, list) and not any(isinstance(b, dict) and b.get("type") == "tool_result" for b in c)


def trim_history(messages: List[dict], turns: Optional[int] = None) -> List[dict]:
    """The recent turns only — never the whole record. Cut only where a turn begins (a tool_use always keeps its tool_result)."""
    turns = HISTORY_TURNS if turns is None else turns
    starts = [i for i, m in enumerate(messages or []) if isinstance(m, dict) and _is_turn_start(m)]
    if len(starts) <= turns:
        return messages
    return messages[starts[-turns]:]


def _marks(x: Any) -> int:
    return json.dumps(x, default=str).count('"cache_control"')


def with_cache(kw: dict) -> dict:
    """The fixed parts carry the cache mark: the tool list's last tool, and the system prompt's first block (its fixed part) — when
    the caller hasn't marked them. Never more than Anthropic's four marks."""
    kw = dict(kw)
    total = _marks(kw.get("tools")) + _marks(kw.get("system")) + _marks(kw.get("messages"))
    tools = kw.get("tools")
    if isinstance(tools, list) and tools and not _marks(tools) and total < 4:
        kw["tools"] = list(tools[:-1]) + [{**tools[-1], "cache_control": {"type": "ephemeral"}}]
        total += 1
    sysm = kw.get("system")
    if isinstance(sysm, str) and len(sysm) > 4000 and total < 4:
        kw["system"] = [{"type": "text", "text": sysm, "cache_control": {"type": "ephemeral"}}]
    elif isinstance(sysm, list) and sysm and not _marks(sysm) and isinstance(sysm[0], dict) and total < 4:
        kw["system"] = [{**sysm[0], "cache_control": {"type": "ephemeral"}}] + list(sysm[1:])
    return kw


def choose_model(model: Optional[str]) -> Optional[str]:
    """Opus only where allowed; never "measured necessary" yet — Sonnet does those steps."""
    if model and "opus" in str(model) and os.getenv("SASHA_MODEL_ALLOW_OPUS", "").strip() != "1":
        return SONNET
    return model


def prepare(kw: dict) -> dict:
    kw = dict(kw)
    kw["model"] = choose_model(kw.get("model"))
    if isinstance(kw.get("messages"), list):
        kw["messages"] = trim_history(kw["messages"])
    return with_cache(kw)


# ── the gate's replay ───────────────────────────────────────────────────────────────────────────────────────────────────

_MONTHS = r"January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Oct|Nov|Dec"
_VOLATILE = re.compile(rf"\b(?:{_MONTHS}|Mon|Tue|Wed|Thu|Fri|Sat|Sun)[a-z]*\b|[0-9a-f]{{8}}-[0-9a-f-]{{27}}|\b[A-Za-z0-9_]{{16,}}\b|\d+")


def _asked(kw: dict) -> dict:
    """What the request ASKS, without what changes from run to run: the tools offered (names); each message's words, and of a tool's
    call its name and inputs, of its result only ok / error — a tool's output (ids, timings, "checked two minutes ago") runs for real
    in a replay, and the model's reply follows the conversation, not those bytes (found by the first replay: 23 of the gate's requests
    differed only in tool output). Dates, times, numbers and ids masked.
    Sasha 364 · AND what the request is ANSWERED UNDER — found by the recording deploy (10 Nov): a changed persona and a tool that now
    returns its payment were answered from replies recorded under the old ones ("Pay here, or on your phone?"), so a recording run
    could never record them again. So: her persona (the system's FIRST block — the cached one; the per-turn rest, with the day's date,
    never), each tool's description, and each tool result's SHAPE (its top-level keys, never their values)."""
    def shape(c: Any) -> str:
        raw = c if isinstance(c, str) else " ".join(str(x.get("text") or "") for x in c if isinstance(x, dict)) if isinstance(c, list) else ""
        try:
            got = json.loads(raw)
        except (TypeError, ValueError):
            return ""
        return ":" + ",".join(sorted(got)) if isinstance(got, dict) else ""

    def block(b: Any) -> str:
        if not isinstance(b, dict):
            return str(b)
        t = b.get("type")
        if t == "tool_result":
            return "result:" + ("error" if b.get("is_error") else "ok") + shape(b.get("content"))
        if t == "tool_use":
            return "call:" + str(b.get("name")) + ":" + json.dumps(b.get("input") or {}, sort_keys=True)
        return str(b.get("text") or "")

    def text(c: Any) -> str:
        return c if isinstance(c, str) else " ".join(block(b) for b in c) if isinstance(c, list) else str(c or "")
    sysv = kw.get("system")
    persona = sysv if isinstance(sysv, str) else (str((sysv[0] or {}).get("text") or "") if isinstance(sysv, list) and sysv and isinstance(sysv[0], dict) else "")
    digest = lambda x: hashlib.sha256(x.encode()).hexdigest()[:16]
    return {"tools": sorted(t.get("name", "") for t in kw.get("tools") or [] if isinstance(t, dict)),
            "contract": digest(json.dumps(sorted((str(t.get("name", "")), str(t.get("description", ""))) for t in kw.get("tools") or []
                                               if isinstance(t, dict)))),
            "persona": digest(_VOLATILE.sub("#", persona)),
            "messages": [[m.get("role"), _VOLATILE.sub("#", text(m.get("content")))] for m in kw.get("messages") or []]}


def replay_key(kw: dict) -> str:
    return hashlib.sha256(json.dumps(_asked(kw), sort_keys=True).encode()).hexdigest()[:24]


def replay_mode() -> str:
    return os.getenv("SASHA_MODEL_REPLAY", "").strip().lower()


class _PgReplays:
    """The gate's recorded replies, on the record (Railway's containers forget their files): sasha_measures, kind model_replay, kept a
    year. Keyed by replay_key; the message as Anthropic returned it."""

    async def get(self, key: str) -> Optional[dict]:
        r = await _db(lambda c: c.fetchval("select data from sasha_measures where id = $1", f"replay:{key}"))
        return json.loads(r) if isinstance(r, str) else r

    async def put(self, key: str, data: dict) -> None:
        await _db(lambda c: c.execute(
            "insert into sasha_measures (id, kind, at, day, data, mv, sasha, agapi, expires_at) values ($1, 'model_replay', now(), "
            "(now() at time zone 'Europe/Madrid')::date, $2::jsonb, 0, $3, null, now() + interval '365 days') "
            "on conflict (id) do update set data = excluded.data, at = excluded.at", f"replay:{key}", json.dumps(data),
            os.getenv("RAILWAY_GIT_COMMIT_SHA", "")[:12]))

    async def passed(self, build: str) -> bool:
        """Sasha 381f · did this deploy's gate PASS (scripts/gate.py marked it)?"""
        return bool(await _db(lambda c: c.fetchval("select 1 from sasha_measures where id = $1", f"gate_pass:{build}")))

    async def mark_passed(self, build: str) -> None:
        # Sasha 383 · kind 'model_replay' (id gate_pass:<build>): sasha_measures' CHECK allows only MEASURE_KINDS — 381f wrote kind
        # 'gate_pass', the database refused it (CheckViolationError on every pass), no build was ever marked, and every recording made
        # since was unusable (ReplayMissing on every push). The pass mark is one of the replay store's records.
        await _db(lambda c: c.execute(
            "insert into sasha_measures (id, kind, at, day, data, mv, sasha, agapi, expires_at) values ($1, 'model_replay', now(), "
            "(now() at time zone 'Europe/Madrid')::date, $2::jsonb, 0, $3, null, now() + interval '365 days') on conflict (id) do nothing",
            f"gate_pass:{build}", json.dumps({"build": build}), os.getenv("RAILWAY_GIT_COMMIT_SHA", "")[:12]))


#: Sasha 383 · the kinds sasha_measures' CHECK (sasha_measures_kind_check, in the database) accepts — every insert's kind is one of them
#: (tests/test_s383_gate_pass_mark holds every literal kind written to the table against this list)
MEASURE_KINDS = ("turn", "client", "booking", "daily", "avatar", "model_day", "model_replay")

REPLAYS: Any = None   # tests replace it: async get(key) / put(key, data)


def _replays():
    return REPLAYS if REPLAYS is not None else _PgReplays()


def build() -> str:
    """Sasha 381f · the deploy this process is (Railway's deployment id) — every recording carries it."""
    return os.getenv("RAILWAY_DEPLOYMENT_ID", "").strip()


async def _usable(got: Any) -> bool:
    """Sasha 381f · A RECORDING FROM A BUILD WHOSE GATE FAILED IS NEVER REPLAYED (found by 381d/381e: a failed recording run's refusals were
    replayed by every later run — record mode fills only what's missing). Usable: this build's own (the run that's recording now), a build
    whose gate PASSED (marked by scripts/gate.py), or one from before builds were marked (all of those were deploys that passed)."""
    b = got.get("build") if isinstance(got, dict) else None
    if not b or b == build():
        return True
    store = _replays()
    return bool(await store.passed(b)) if hasattr(store, "passed") else True


async def mark_build_passed() -> None:
    """Sasha 381f · scripts/gate.py, on PASS only: this build's recordings may be replayed from now on."""
    b, store = build(), _replays()
    if b and hasattr(store, "mark_passed"):
        await store.mark_passed(b)


async def _record(key: str, msg: Any, kw: Optional[dict] = None) -> None:
    data = msg.model_dump(mode="json") if hasattr(msg, "model_dump") else msg
    try:   # the reply, and what was asked (masked) — a later miss can be told apart from its nearest recording
        await _replays().put(key, {"reply": data, "asked": _asked(kw) if kw else None, "build": build()})   # Sasha 381f · whose it is
    except Exception as e:
        log.error("[model_gateway] RECORD: %s not kept (%s)", key, type(e).__name__)


async def _replayed(kw: dict):
    key = replay_key(kw)
    got = await _replays().get(key)
    if got is not None and not await _usable(got):   # Sasha 381f · recorded by a build whose gate failed: as good as none
        log.error("[model_gateway] REPLAY: the recording for %s came from a build whose gate failed — not replayed", key)
        got = None
    if got is None:
        msg = f"no recorded reply for this request ({key}) — record once with SASHA_MODEL_REPLAY=record; nothing was sent"
        log.error("[model_gateway] REPLAY: %s", msg)
        raise ReplayMissing(msg)
    from anthropic.types import Message
    return Message.model_validate(got.get("reply", got) if isinstance(got, dict) and "reply" in got else got)


_INFLIGHT: Dict[str, Any] = {}   # key → the live call recording it now (identical requests at once share it: the gate's loops start alike)


async def _recording(kw: dict, live):
    """RECORD = fill what's missing: a request already recorded is answered from its recording (so the recording run follows exactly the
    path a replay will — found by the first replay: loops starting alike got different live replies, one kept, the others' next requests
    never recorded); a new one goes live once, recorded; the same request at the same moment waits for that one call."""
    from anthropic.types import Message
    key = replay_key(kw)
    got = await _replays().get(key)
    if got is not None and await _usable(got):   # Sasha 381f · a failed build's recording is re-recorded, never followed
        return Message.model_validate(got.get("reply", got) if isinstance(got, dict) and "reply" in got else got), False
    fut = _INFLIGHT.get(key)
    if fut is not None and fut.get_loop() is asyncio.get_running_loop():
        return await asyncio.shield(fut), False
    fut = asyncio.get_running_loop().create_future()
    _INFLIGHT[key] = fut
    try:
        msg = await live()
        await _record(key, msg, kw)
        fut.set_result(msg)
        return msg, True
    except BaseException as e:
        fut.set_exception(e)
        fut.exception()   # retrieved: a waiter re-raises it, nothing is left unobserved
        raise
    finally:
        _INFLIGHT.pop(key, None)


LIVE_IN_REPLAY = ("app.services.model_health",)   # the gate's ONE tiny live check (a 1-token Haiku call), never replayed


class _ReplayStream:
    """The shape of an SDK message stream, from a recorded message: its text as events, then the final message."""

    def __init__(self, msg):
        self._msg = msg

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    def __aiter__(self):
        async def gen():
            import types
            for b in self._msg.content:
                if b.type == "text":
                    yield types.SimpleNamespace(type="text", text=b.text)
                elif b.type == "tool_use":
                    yield types.SimpleNamespace(type="content_block_start", content_block=b)
        return gen()

    @property
    def text_stream(self):
        async def gen():
            for b in self._msg.content:
                if b.type == "text":
                    yield b.text
        return gen()

    async def get_final_message(self):
        return self._msg

    async def until_done(self):
        return None


# ── the one entry: the SDK's own methods, wrapped ───────────────────────────────────────────────────────────────────────

def _caller() -> str:
    for fr in inspect.stack()[2:12]:
        mod = fr.frame.f_globals.get("__name__", "")
        if mod and not mod.startswith(("anthropic", "booking_signer.model_gateway", "asyncio", "contextlib", "scripts.gate_cost")):
            return mod
    return "?"


_INSTALLED = {"on": False}


def install() -> bool:
    """Every model call through here — idempotent. Called where the service starts (booking_signer, imported by app.main's mount) and
    by the gate (scripts/gate.py) before any client is built."""
    if _INSTALLED["on"]:
        return False
    from anthropic.resources.messages import AsyncMessages, Messages
    orig = {"acreate": AsyncMessages.create, "astream": AsyncMessages.stream, "screate": Messages.create}

    async def acreate(self, *a, **kw):
        caller, acct = _caller(), _acct_key(ACCOUNT.get())
        await _ensure_day()
        _check(acct)
        kw = prepare(kw)
        if replay_mode() == "replay" and not kw.get("stream") and caller not in LIVE_IN_REPLAY:
            return await _replayed(kw)
        if replay_mode() == "record" and not kw.get("stream") and caller not in LIVE_IN_REPLAY:
            r, went = await _recording(kw, lambda: orig["acreate"](self, *a, **kw))
            if went:
                _meter(getattr(r, "model", kw.get("model")), getattr(r, "usage", None), caller, acct)
            return r
        r = await orig["acreate"](self, *a, **kw)
        if not kw.get("stream"):
            _meter(getattr(r, "model", kw.get("model")), getattr(r, "usage", None), caller, acct)
        return r

    def astream(self, *a, **kw):
        caller, acct = _caller(), _acct_key(ACCOUNT.get())
        kw = prepare(kw)
        if replay_mode() == "replay":
            return _GatedReplay(kw, acct)
        if replay_mode() == "record":
            async def live(this=self):
                async with orig["astream"](this, *a, **kw) as st:
                    m = await st.get_final_message()
                _meter(getattr(m, "model", kw.get("model")), getattr(m, "usage", None), caller, acct)
                return m
            return _GatedRecord(kw, acct, live)
        mgr = orig["astream"](self, *a, **kw)
        return _GatedStream(mgr, kw, caller, acct)

    def screate(self, *a, **kw):
        caller, acct = _caller(), _acct_key(ACCOUNT.get())
        if _DAY["day"] != _today():
            _DAY.update(day=_today(), total=0, accounts={}, models={}, callers={}, loaded=True)
            _OTHERS.update(total=0, accounts={}, at=time.monotonic())
        _check(acct)
        kw = prepare(kw)
        r = orig["screate"](self, *a, **kw)
        if not kw.get("stream"):
            _meter(getattr(r, "model", kw.get("model")), getattr(r, "usage", None), caller, acct)
        return r

    AsyncMessages.create, AsyncMessages.stream, Messages.create = acreate, astream, screate
    try:   # the beta namespace (docread, tarjeta): the same gate
        from anthropic.resources.beta.messages import AsyncMessages as BAsync
        borig = BAsync.create

        async def bcreate(self, *a, **kw):
            caller, acct = _caller(), _acct_key(ACCOUNT.get())
            await _ensure_day()
            _check(acct)
            kw = prepare(kw)
            r = await borig(self, *a, **kw)
            _meter(getattr(r, "model", kw.get("model")), getattr(r, "usage", None), caller, acct)
            return r
        BAsync.create = bcreate
    except Exception as e:
        log.warning("[model_gateway] the beta namespace wasn't wrapped: %s", type(e).__name__)
    _INSTALLED["on"] = True
    log.info("[model_gateway] installed: caps %s / day, %s / account / day; history %d turns; replay %s", f"{global_cap():,}",
             f"{account_cap():,}", HISTORY_TURNS, replay_mode() or "off")
    return True


class _GatedStream:
    """The SDK's stream manager with the caps checked on entry and the usage metered from its final message."""

    def __init__(self, mgr, kw, caller, acct):
        self._mgr, self._kw, self._caller, self._acct, self._s = mgr, kw, caller, acct, None

    async def __aenter__(self):
        await _ensure_day()
        _check(self._acct)
        self._s = await self._mgr.__aenter__()
        orig_final = self._s.get_final_message

        async def final():
            m = await orig_final()
            if not getattr(self._s, "_sasha_metered", False):
                self._s._sasha_metered = True
                _meter(getattr(m, "model", self._kw.get("model")), getattr(m, "usage", None), self._caller, self._acct)
            return m
        self._s.get_final_message = final
        return self._s

    async def __aexit__(self, *a):
        return await self._mgr.__aexit__(*a)


class _GatedRecord:
    """Record mode's stream: the recording (or the one live call that makes it), as a stream."""

    def __init__(self, kw, acct, live):
        self._kw, self._acct, self._live = kw, acct, live

    async def __aenter__(self):
        await _ensure_day()
        _check(self._acct)
        msg, _ = await _recording(self._kw, self._live)
        return _ReplayStream(msg)

    async def __aexit__(self, *a):
        return False


class _GatedReplay:
    def __init__(self, kw, acct):
        self._kw, self._acct = kw, acct

    async def __aenter__(self):
        await _ensure_day()
        _check(self._acct)
        return _ReplayStream(await _replayed(self._kw))

    async def __aexit__(self, *a):
        return False


__all__ = ["install", "ACCOUNT", "ModelBudgetExceeded", "ReplayMissing", "trim_history", "with_cache", "choose_model", "replay_key", "today"]
