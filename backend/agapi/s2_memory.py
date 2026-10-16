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
    t = re.sub(r"^for “([^”]*)” in ", r"\1 in ", t)   # Sasha 248 · the ribbon quotes the search: '5 for “Indian” in Madrid'
    return re.sub(r"\s*·\s*", ", ", t).strip(" ,")


def _question(reply: str) -> Optional[str]:
    parts = [p.strip() for p in re.split(r"(?<=[.!?])\s+", str(reply or "").strip()) if p.strip()]
    return parts[-1][:200] if parts and parts[-1].endswith("?") else None


def _card(c: dict) -> dict:
    return {k: c[k] for k in ("place_id", "name", "rating", "rating_count", "area", "address", "type", "open_at",
                              "website", "type_source", "google_type") if c.get(k) is not None}   # Sasha 248 · where its type came from


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
        m["decided"] = None   # Sasha 239 · a new search: nothing chosen from it (yet)
    if "read_booking_route" in ran or "hold_venue" in ran:   # Sasha 239 · THEY chose a place (a tap, or naming it): only then "decided"
        name = seen.get("held") or next((c.get("name") for c in ((m.get("screen") or {}).get("cards") or [])
                                          if seen.get("focus") and c.get("place_id") == seen.get("focus")), None)
        if name:
            m["decided"] = {"what": masked(str(name))[:120], "state": "chosen — not booked yet"}
    held = next((t for t, s in status.items() if s == "awaiting_yes"), None)
    if held:
        what = (seen.get("held") or (_thing_of_ribbon(seen["ribbon"]) if held == "hold_venue" and seen.get("ribbon") else None)
                or m.get("thing") or "your booking")
        m["pending"] = {"kind": "hold", "tool": held, "what": what, "at": NOW().isoformat()}
        m["thing"] = topic = f"{what} — it's ready, waiting for your yes" if held == "hold_venue" else what
        if held == "hold_venue" and seen.get("held"):
            m["decided"] = {"what": masked(str(seen["held"]))[:120], "state": "chosen and read back — waiting for their yes"}
    if any(status.get(t) in ("confirmed", "requested", "sent", "booked") for t in ("book_venue", "book", "send_email", "send_whatsapp")) \
            or re.search(r"✅\s*Booked", reply or ""):
        topic = topic or "done: " + (m.get("thing") or "your booking")
        m["thing"], m["pending"], m["decided"] = None, None, None
    q = _question(reply)
    if (m.get("pending") or {}).get("kind") == "question":
        m["pending"] = None   # a question is only unfinished until her next reply
    if q and not m.get("pending"):
        m["pending"] = {"kind": "question", "asked": masked(q), "at": NOW().isoformat()}
    if topic and masked(topic) != REMOVED:
        m["summary"] = ([s for s in m["summary"] if s != topic] + [topic])[-SUMMARY_MAX:]
    m["updated_at"] = NOW().isoformat()
    return m


async def _db_load(run, account: str) -> Optional[dict]:
    """The account's row in s2_memory (None: no row). Raises when the table can't be read."""
    row = await run(lambda c: c.fetchrow("select memory from s2_memory where account_id = $1", uuid.UUID(account)))
    if row:
        v = row["memory"]
        return json.loads(v) if isinstance(v, str) else dict(v)
    return None


async def _db_save(run, account: str, m: dict) -> None:
    await run(lambda c: c.execute(
        "insert into s2_memory (account_id, memory, updated_at) values ($1, $2::jsonb, now()) "
        "on conflict (account_id) do update set memory = excluded.memory, updated_at = now()",
        # Sasha 233 · the pool's jsonb codec encodes once — a json.dumps here stored a JSON STRING (it loaded fine, but SQL
        # saw text, not an object); rows written that way still load (the str branch in _db_load)
        uuid.UUID(account), json.loads(json.dumps(m, default=str))))


async def _load(account: str) -> Optional[dict]:
    run = _run()
    if run is not None and account not in _MEM:
        try:
            return await _db_load(run, account)
        except Exception as e:
            log.info("[memory] not read (%s) — memory", type(e).__name__)
    return _MEM.get(account)


async def _save(account: str, m: dict) -> None:
    run = _run()
    if run is not None and account not in _MEM:
        try:
            await _db_save(run, account, m)
            return
        except Exception as e:
            log.info("[memory] not stored (%s) — kept in memory", type(e).__name__)
    _MEM[account] = m


# ── Sasha 249 · ONE MEMORY (EU 245 step 9): what lived only in a process — the claim and case pointers ({case_id, target}), the
# read-backs waiting for a yes, the handover note, the cards on screen, the openers already said, the open outcomes, the space —
# is kept in the account's s2_memory row too, each under its own `kind` (memory.kinds.<kind>; no migration: s2_memory's jsonb).
# These read and write the TABLE only: with no table (tests, a store that's down) they answer {} / False and the caller's own
# process copy is the memory, exactly as before. Callers keep that copy (one worker, one replica) and read the table when the
# copy is empty — after a restart.

async def kinds(account: Optional[str]) -> Dict[str, Any]:
    """Every kind kept for this account ({} when the table isn't there or has nothing)."""
    run = _run()
    if run is None or not account:
        return {}
    try:
        return dict(((await _db_load(run, account)) or {}).get("kinds") or {})
    except Exception as e:
        log.info("[memory] kinds not read (%s)", type(e).__name__)
        return {}


async def kind(account: Optional[str], name: str) -> Any:
    return (await kinds(account)).get(name)


async def put_kinds(account: Optional[str], values: Dict[str, Any]) -> bool:
    """{kind: value, or None to forget it} into the account's row (the rest of its memory untouched). True when stored."""
    run = _run()
    if run is None or not account or not values:
        return False
    try:
        m = (await _db_load(run, account)) or {}
        k = dict(m.get("kinds") or {})
        for n, v in values.items():
            if v is None:
                k.pop(n, None)
            else:
                k[n] = v
        m["kinds"] = k
        await _db_save(run, account, m)
        return True
    except Exception as e:
        log.info("[memory] kinds not stored (%s) — this process keeps them", type(e).__name__)
        return False


async def put_kind(account: Optional[str], name: str, value: Any) -> bool:
    return await put_kinds(account, {name: value})


async def verified_history(account: str, session: Optional[str], history: List[dict]) -> List[dict]:
    """Sasha 249 · SERVER-BUILT HISTORY (one-truth-spec 1.14): the conversation the model hears is the one the SERVER kept, not
    whatever the browser sends back. The stored turns (this memory's `recent`, masked, the last KEEP messages) are the truth:
      · nothing stored for this conversation (a first turn, another session's memory, no table yet) → the client's history, as today
        (it keeps working when the server has nothing);
      · stored, and the client's last lines are those same lines (masked the same way) → the client's history (verified: it is the
        same conversation, and keeps the lines older than the stored window);
      · stored, and they differ → the stored turns: a history the server never said is never handed to the model (nor its amounts
        to the price guard)."""
    m = await _load(account) or {}
    n = int(m.get("session_lines") or 0)
    if not session or m.get("session") != session or n <= 0:
        return history
    stored = [x for x in (m.get("recent") or []) if x.get("role") in ("user", "assistant")][-n:]   # THIS conversation's lines only
    if not stored:
        return history
    client = [x for x in (history or []) if x.get("role") in ("user", "assistant") and str(x.get("content") or "").strip()]
    k = min(len(client), len(stored))
    mine = [(x["role"], masked(str(x.get("content") or ""))) for x in client[len(client) - k:]]
    if k and mine == [(x["role"], str(x.get("content") or "")) for x in stored[len(stored) - k:]]:
        return history
    log.info("[memory] the client's history isn't the stored conversation — the stored turns are used")
    return [{"role": x["role"], "content": str(x.get("content") or "")} for x in stored]


async def accounts_with(name: str) -> List[tuple]:
    """[(account, value)] for every account that has this kind kept (the outcomes sweep, after a restart)."""
    run = _run()
    if run is None:
        return []
    try:
        rows = await run(lambda c: c.fetch(
            "select account_id, memory -> 'kinds' -> $1 as v from s2_memory "
            "where jsonb_typeof(memory) = 'object' and memory -> 'kinds' ? $1", name))
    except Exception as e:
        log.info("[memory] %s not listed (%s)", name, type(e).__name__)
        return []
    out = []
    for r in rows or []:
        v = r["v"]
        out.append((str(r["account_id"]), json.loads(v) if isinstance(v, str) else v))
    return out


async def remember(account: str, session: Optional[str], said: str, reply: str, seen: dict) -> dict:
    if any(c.get("tool") == "hold_venue" and c.get("status") == "awaiting_yes" for c in seen.get("calls") or []):
        from agapi import venues as VN
        h = VN._HELD.get(account) or {}
        if h.get("venue"):   # the place she read back, by its name
            seen = {**seen, "held": str(h["venue"])[:120]}
    before = await _load(account) or {}
    m = fold(before, said, reply, seen)
    m["session"] = (session or "")[:64]
    # Sasha 249 · how many of `recent`'s lines are THIS conversation's (verified_history compares only those)
    same = bool(before) and before.get("session") == m["session"]
    m["session_lines"] = min(len(m["recent"]), (int(before.get("session_lines") or 0) if same else 0) + 2)
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
    d = m.get("decided") or {}
    if d.get("what") and d["what"] not in thing:   # Sasha 239 · a pick is said as theirs ONLY when they made it
        return f"Welcome back — you'd chosen {d['what']} ({thing}). Want to carry on?"
    return f"Welcome back — we were looking at {thing}. Want to carry on?"


def handover(m: dict) -> str:
    """Sasha 239 · what the model is told on return (found live: "Oven Mozzarella is the one you've picked" when nothing was picked).
    Decided only if they decided; otherwise they were looking — and it must not say they chose."""
    d = m.get("decided") or {}
    thing = m.get("thing") or "something"
    if d.get("what"):
        return (f"What you remember from before they left: they were looking at {thing}, and THEY chose {d['what']} "
                f"({d.get('state') or 'chosen'}). Nothing else was chosen or booked.")
    return (f"What you remember from before they left: they were looking at {thing}. They had NOT chosen or booked anything — never "
            f"say they picked or chose one; if it helps, ask which they'd like.")


# ── Sasha 246 · HOW SHE STARTS: every return, on /s2, /next and WhatsApp, only "Hey <first name>, what can I help you with?" —
# never mid-sentence, never the last topic. Memory and history are kept exactly as before; she uses them when THEY refer to them.
OPEN = "Hey {name}, what can I help you with?"
ASK_NAME = "Hi, I'm Sasha. What should I call you?"     # a new person, once
OPEN_NO_NAME = "Hey, what can I help you with?"         # asked once already, never told


def _clean_name(name: str) -> Optional[str]:
    n = re.sub(r"[^\w'’ -]", "", str(name or ""), flags=re.UNICODE).strip().split()
    return n[0][:40].capitalize() if n and not any(ch.isdigit() for ch in n[0]) else None


async def first_name(account: str) -> Optional[str]:
    """Their saved contact's first name, else the name they told her (remember_name)."""
    try:
        from booking_signer import contacts as CT
        row = await CT.STORE.get(account) if CT.STORE is not None else None
        n = _clean_name((row or {}).get("name") or "")
        if n:
            return n
    except Exception as e:
        log.info("[memory] no contact name: %s", type(e).__name__)
    return _clean_name(((await _load(account)) or {}).get("name") or "")


async def set_name(account: str, name: str) -> Optional[str]:
    n = _clean_name(name)
    if n:
        m = (await _load(account)) or {}
        m["name"] = n
        await _save(account, m)
    return n


async def opening(account: str) -> str:
    """The one opening line. A person she has no name for is asked once ("What should I call you?"), then never again."""
    n = await first_name(account)
    if n:
        return OPEN.format(name=n)
    m = (await _load(account)) or {}
    if m.get("name_asked"):
        return OPEN_NO_NAME
    m["name_asked"] = NOW().isoformat()
    await _save(account, m)
    return ASK_NAME


async def recall(account: str, session: Optional[str], surface: Optional[str] = None) -> dict:
    """On return: the opening line (Sasha 246), the recent conversation (masked), the cards she'd shown (on screen again, for this
    session) — what she remembers is kept and handed to the model, never recited.
    Sasha 273 · + last_at: the conversation's last turn (fold's updated_at) — /s2's rule 4 (lib/presence-rule.mjs reappear) greets only
    after 30 minutes, on a new day or with news; so on /s2 (surface "s2") the model is not told she greeted: it sees it in the history
    when she did."""
    m = await _load(account)
    line = line_for(m, account)
    opening_line = await opening(account)
    last_at = (m or {}).get("updated_at")
    if not m or not line:
        return {"line": opening_line, "recent": [], "screen": None, "summary": (m or {}).get("summary") or [], "last_at": last_at}
    scr = m.get("screen") or None
    if scr and scr.get("cards") and session:
        from app.agent import sasha as AG
        from agapi import venues as VN
        AG._SCREEN[session] = {"cards": scr["cards"], "ribbon": scr.get("ribbon"), "names": [c.get("name") for c in scr["cards"] if c.get("name")]}
        VN.remember_cards(account, scr["cards"])
    p = m.get("pending") or {}
    note = handover(m)
    if session:   # Sasha 239 · the model's first turn back hears exactly what was (and wasn't) decided
        from app.agent import sasha as AG
        AG._HANDOVER[session] = note + ((" They have just come back to the conversation — never bring this up yourself; use it only when "
                                          "THEY refer to it.") if surface == "s2" else
                                         (" They have just come back and you greeted them with \"" + opening_line + "\" — never bring "
                                          "this up yourself; use it only when THEY refer to it."))
        # Sasha 249 · ONE MEMORY: kept in the table too, so the first turn back hears it even if this process restarted between
        await put_kinds(account, {"handover": {"session": session, "note": AG._HANDOVER[session]},
                                  **({"screen": {"session": session, "cards": scr["cards"], "ribbon": scr.get("ribbon"),
                                                 "names": [c.get("name") for c in scr["cards"] if c.get("name")]}}
                                     if scr and scr.get("cards") else {})})
    return {"line": opening_line, "recent": m.get("recent") or [], "screen": scr, "summary": m.get("summary") or [], "handover": note,
            "last_at": last_at,
            "pending": ({"kind": "hold", "what": p.get("what"), "waiting": _hold_live(account, p)} if p.get("kind") == "hold" else
                        {"kind": "question", "asked": p.get("asked")} if p.get("kind") == "question" else None)}


# ── Sasha 265 · item 3 · NEW CHAT: the conversation is cleared in its ONE place — this record — for /s2, /next and WhatsApp alike.
# Its lines, its summary, what she was looking at / waiting on, the cards on screen, the handover and the openers go; the read-backs
# she showed in it are forgotten (a "yes" in the new chat can never land on them). Bookings, trips and receipts are not here (the trip
# record, the acts, the ledger) — nor are her name for them, or the kinds that track an act (venue_acts, prepared, outcomes_open …).
CONVERSATION = ("recent", "summary", "thing", "pending", "screen", "decided", "session", "session_lines")
CONVERSATION_KINDS = ("handover", "screen", "openers")


async def clear_conversation(account: str) -> dict:
    m = (await _load(account)) or {}
    gone = [k for k in CONVERSATION if m.get(k)]
    for k in CONVERSATION:
        m.pop(k, None)
    kept = {n: v for n, v in (m.get("kinds") or {}).items() if n not in CONVERSATION_KINDS}
    gone += [f"kinds.{n}" for n in (m.get("kinds") or {}) if n in CONVERSATION_KINDS]
    m["kinds"] = kept
    m["cleared_at"] = NOW().isoformat()
    await _save(account, m)
    from agapi import venues as VN, yes_gate as YG
    for store in (YG._RB, YG._APV):
        for key in [k for k in store if k[0] == account]:
            store.pop(key, None)
    VN._SHOWN.pop(account, None)
    from app.agent import voice as V
    V.forget_acks(account)   # Sasha 273 · item 8: a new chat is a new request
    return {"cleared": gone, "kept": sorted(kept)}


__all__ = ["remember", "closing", "recall", "fold", "line_for", "masked", "opening", "first_name", "set_name", "OPEN", "ASK_NAME",
           "kinds", "kind", "put_kinds", "put_kind", "accounts_with", "verified_history", "clear_conversation"]
