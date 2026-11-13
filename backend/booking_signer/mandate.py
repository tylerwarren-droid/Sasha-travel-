"""Sasha 365 · THE MANAGER'S INSTRUCTION IS THE APPROVAL — the ONE source for "may I act" on a group trip.

Found (Tyler, 10 Nov 07:32–07:36): "if I say book all executives, she should just do it, then tell us when she is finished — she doesn't need
to keep asking for permission." She asked at every step ("Make the London trip with these 6?", "Book these 6?", "try six rooms?"), and
"planning…" showed no sign of work until he asked.

The rule, held here and nowhere else:
  · an instruction naming who / where / when (the chat), "book them all" on the open trip, or the Group page's Book all tap IS the yes for
    everything INSIDE the company's limits on the record (rules.limits, each person's passport in their vault): plan → the group's hotel →
    book → the ONE finish (group_book.finish);
  · she asks ONLY for a missing fact (groups.propose: where / when / who, a name it can't match) or an item OUTSIDE the limits (over a
    limit, a fare only the airline can cancel, a missing passport) — ONE grouped question, after everything inside the limits is done;
  · she reports unasked: live progress from the trip record ("Planning 3 of 6", "Hotel: 6 rooms at …", "Booking 2 of 6"), then the finish.

    carry_out(account, said, who=None, over_ok=False) → starts it (never waits); finished(account) waits (tests, the proof).
"""
from __future__ import annotations
from kanoe_contract import ERR  # Sasha 374 · THE ONE generated contract (CR 186)

import asyncio
import logging
import re
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)

_BOOK = re.compile(r"(?i)\b(?:book|reserve)\w*\b")
_NOT_YET = re.compile(r"(?i)\b(?:don'?t|do not|not yet|no booking|without booking|just plan|only plan|hold off)\b")


def wants_booking(said: Optional[str]) -> bool:
    """The instruction's own words ask to book (never the model's flag): "Book all executives to London…", "book them all"."""
    t = said or ""
    return bool(_BOOK.search(t)) and not _NOT_YET.search(t)


_RUNS: Dict[str, "asyncio.Task[Any]"] = {}
POLL_S = 1.0   # how often the planning is read for its progress line


def _publish(account: str, kind: str, text: str, **more: Any) -> None:
    from . import group_book as GB, live_events as LE
    LE.publish(account, {"type": kind, "text": text, **more})
    j = GB._JOBS.get(account)
    if j is not None and j.get("kind") == "mandate":   # the Group page follows the same line (its job view)
        j["line"] = text


def running(account: str) -> bool:
    t = _RUNS.get(account)
    return bool(t is not None and not t.done())


# ── Sasha 366 · THE MANDATE IS ON THE TRIP RECORD; ONE SERVER WORKER CARRIES IT ─────────────────────────────────────────────────
# Found (Tyler, 10 Nov 19:35, WhatsApp): the trip was planned, then nothing — the mandate told only the S2 page's stream, and lived only in
# this process's memory. Now: carry_out writes it onto the trip (rules.mandate: the words, who, the door that started it, its state);
# sweep() — the ONE worker, every few seconds from the app's start and at once for a new one — carries every open mandate through,
# whatever door started it and whether or not any page is open; a restart finds it on the record and carries on.

async def carry_out(account: str, said: str, who: Optional[List[str]] = None, over_ok: bool = False, door: str = "s2",
                    proof: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """The instruction received → Sasha 367: registered ONCE at AgAPI as a signed mandate (its id on the trip's record — an id, never a
    token), then the worker takes it. A missing fact (the company's limits) is asked; a refusal is said. → {started, say} at once."""
    import time
    from . import agapi_mandate as AM, groups as G
    if running(account):
        return {"started": False, "say": "I'm already on it — I'll tell you as it goes, and when it's done."}
    mv = await G.store().movement(account)
    if not mv:
        return {"started": False, "say": "There's no group trip yet — tell me who's going, where and when."}
    members = G.pick(await G.store().members(mv["id"]), who)[0]   # Sasha 376 · the one person resolver
    reg = await AM.register(account, said, mv, members, proof)
    m = {"said": (said or "")[:500], "who": who or None, "over_ok": bool(over_ok), "door": door if door in ("s2", "wa") else "s2",
         "state": "running" if reg.get("mandate_id") else ("waiting" if reg.get("code") == "limits_needed" else "stopped"), "at": time.time(),
         **({"agapi": {"mandate_id": reg["mandate_id"], "expires_at": reg.get("expires_at")}} if reg.get("mandate_id") else {"why": reg.get("code")}),
         **({"proof": proof} if proof and reg.get("code") == "limits_needed" else {})}   # waiting for the missing fact: the proof's IDS kept
    if reg.get("mandate_id"):   # the runner that takes it holds it (no other process runs it beside this one)
        m["lease"] = {"by": RUNNER, "until": time.time() + LEASE_S}
    await G.store().set_rule(account, str(mv["id"]), "mandate", m)
    if not reg.get("mandate_id"):
        return {"started": False, "say": reg["why"]}
    _start(account, str(mv["id"]), m)
    await asyncio.sleep(0)
    return {"started": True, "say": "On it — I'm planning each person and the hotel, then booking within the company's limits. "
                                    "I'll tell you as it goes, and when it's done."}


async def resume_waiting(account: str) -> Optional[str]:
    """Sasha 367 · the missing fact given (the company's limits): the instruction waiting on the open trip is registered now — with ITS
    own proof (ids kept on the record) — and carried through by the worker. → what she says, or None (nothing was waiting)."""
    import time
    from . import agapi_mandate as AM, groups as G
    mv = await G.store().movement(account)
    m = ((mv or {}).get("rules") or {}).get("mandate") or {}
    if m.get("state") != "waiting":
        return None
    members = G.pick(await G.store().members(mv["id"]), m.get("who"))[0]   # Sasha 376 · the one person resolver
    reg = await AM.register(account, m.get("said") or "", mv, members, m.get("proof"))
    if not reg.get("mandate_id"):
        return reg["why"]
    m = {**{k: v for k, v in m.items() if k not in ("proof", "why")}, "state": "running", "at": time.time(),
         "agapi": {"mandate_id": reg["mandate_id"], "expires_at": reg.get("expires_at")}, "lease": {"by": RUNNER, "until": time.time() + LEASE_S}}
    await G.store().set_rule(account, str(mv["id"]), "mandate", m)
    _start(account, str(mv["id"]), m)
    return "Thanks — I'm carrying on with your instruction now, within those limits. I'll tell you as it goes, and when it's done."


def _start(account: str, movement_id: str, m: Dict[str, Any]) -> None:
    """The worker's ONE way to run a mandate in this process (never twice at once for an account)."""
    import secrets
    import time
    from . import group_book as GB
    if running(account):
        return
    GB._JOBS[account] = {"id": "job_" + secrets.token_hex(8), "kind": "mandate", "state": "preparing", "total": 0, "ready": 0,
                         "at": time.time(), "result": None, "line": "Starting…"}
    _RUNS[account] = asyncio.ensure_future(_run(account, movement_id, m))


LEASE_S = 900   # a runner holds a mandate this long (a job takes a minute or two); a runner that died is taken over after it
RUNNER = f"{__import__('socket').gethostname()}:{__import__('os').getpid()}"


async def _claim(owner: str, mid: str, m: Dict[str, Any]) -> bool:
    """Sasha 367 · ONE runner per mandate across processes (a deploy's two containers, a proof's process): the lease on the record."""
    import time
    from . import groups as G
    lease = m.get("lease") or {}
    if lease.get("by") not in (None, RUNNER) and float(lease.get("until") or 0) > time.time():
        return False
    await G.store().set_rule(owner, mid, "mandate", {**m, "lease": {"by": RUNNER, "until": time.time() + LEASE_S}})
    fresh = ((await G.store().movement(owner, mid)) or {}).get("rules", {}).get("mandate") or {}
    return (fresh.get("lease") or {}).get("by") == RUNNER   # the last writer holds it; the other sees it and stands back


async def sweep(account: Optional[str] = None) -> int:
    """THE ONE WORKER's pass: every open mandate on the record (an account's, or all) not running here, and not held by another
    runner's lease → claimed, then run. → how many."""
    from . import groups as G
    n = 0
    try:
        for owner, mid, m in await G.store().open_mandates():
            if (account is None or owner == account) and not running(owner) and await _claim(owner, mid, m):
                _start(owner, mid, m)
                n += 1
    except Exception as e:
        log.warning("[mandate] the sweep didn't read the open mandates: %s", type(e).__name__)
    return n


_task: Optional["asyncio.Task[Any]"] = None
SWEEP_S = 5.0


async def _forever() -> None:
    while True:
        await asyncio.sleep(SWEEP_S)
        await sweep()


def start() -> None:
    """The server's own loop (started with the app; SASHA_MANDATE_LOOP=0 turns it off; tests call sweep())."""
    import os
    global _task
    if _task is None and os.getenv("SASHA_MANDATE_LOOP", "1") == "1" and os.getenv("DATABASE_URL", "").strip():
        _task = asyncio.ensure_future(_forever())


async def finished(account: str) -> None:
    """Wait for this account's mandate to be carried through (tests and the proof): the worker's pass, then its run."""
    if not running(account):
        await sweep(account)
    t = _RUNS.get(account)
    if t is not None:
        await asyncio.shield(t)


async def _report(account: str, door: str, text: str) -> None:
    """A STAGE of the work, said unasked to the door that started it: the S2 live line always (the page, when open); their WhatsApp when
    the instruction came from WhatsApp (work in progress goes to the phone only then — booking_signer.channel, Sasha 326)."""
    from . import channel as CH
    _publish(account, "group_progress", text)
    await CH.progress(account, door, text)


async def _planning(account: str, movement_id: str) -> None:
    """Each person's planning, reported as it lands ("Planning 3 of 6"), until everyone on the trip is planned (or why not). Anyone not
    planned with no planning running here (a restart lost it) is planned now — from the record, never from a page."""
    from . import groups as G
    last, resumed = None, False
    while True:
        v = await G.view(account, movement_id)
        rows = v.get("rows") or []
        busy = [r for r in rows if r["status"] in ("planning…", "not planned")]
        line = f"Planning {len(rows) - len(busy)} of {len(rows)}"
        if line != last:
            _publish(account, "group_progress", line)
            last = line
        run = G._PLANS.get(account)
        if (run is None or run.done()) and busy and not resumed:
            resumed = True
            await G.plan(account, movement_id, only=[r["member_id"] for r in busy])
            continue
        if run is None or run.done():
            return
        try:
            await asyncio.wait_for(asyncio.shield(run), POLL_S)
        except asyncio.TimeoutError:
            pass


async def _close(account: str, movement_id: str, m: Dict[str, Any], state: str, text: str) -> None:
    import time
    from . import groups as G
    try:
        await G.store().set_rule(account, movement_id, "mandate", {**m, "state": state, "finished_at": time.time(), "said_back": text[:2000]})
    except Exception as e:
        log.error("[mandate] the record wasn't closed: %s", type(e).__name__)


async def _run(account: str, movement_id: str, m: Dict[str, Any]) -> None:
    from . import channel as CH, group_book as GB, group_outcome as GO, groups as G
    said, who, over_ok, door = m.get("said") or "", m.get("who"), bool(m.get("over_ok")), m.get("door") or "s2"
    card = None
    try:
        await _planning(account, movement_id)
        v = await G.view(account, movement_id)
        rows = G.pick(v.get("rows") or [], who)[0]   # Sasha 376 · the one person resolver
        planned = sum(1 for r in rows if r["status"] not in ("planning…", "not planned"))
        await _report(account, door, f"Planned {planned} of {len(rows)}." + (f" {v['hotel_line']}." if v.get("hotel_line") else ""))
        inv = await G.invite_missing(account, movement_id)   # every one without a passport: their secure link by email, now (ONE source)
        held = [{"name": r["name"], "kind": GO.reason(r)} for r in rows if GO.reason(r) not in (None, "booked", "cancelled", "passport")]
        ready = [r["name"] for r in rows if GO.reason(r) is None]
        done: List[dict] = []
        if ready:
            await _report(account, door, f"Booking {len(ready)} now — the flights and the hotel, within the company's limits.")

            def prog(k: int, total: int) -> None:
                j = GB._JOBS.get(account) or {}
                j.update(ready=k, total=total)
            mid = ((m.get("agapi") or {}).get("mandate_id"))
            if not mid:   # Sasha 367 · nothing is booked without the manager's mandate at AgAPI (its id on the record)
                raise RuntimeError("no mandate on the record")

            def acted(k: int, total: int) -> None:
                prog(k, total)
                _publish(account, "group_progress", f"Booking {k} of {total}")
            got = await GB.book_under_mandate(account, mid, ready, movement_id, over_ok=over_ok, progress=acted)
            asks = [x for x in got["asks"] if x.get("kind") != "needs_vault"] + got["outside"]   # invited above: said as done, never asked
            card = got["card"]
            fin = None
            if any(x.get("code") == ERR.APPROVAL_EXPIRED for x in got["asks"]):
                text = "Your instruction expired before I could book everyone — say it again and I'll carry on from the master list."
            else:
                fin = await GB.finish(account, movement_id, got["done"], held + asks, ask_once=True)
                text = fin["say"]
            done = got["done"]
        else:
            card, fin = None, await GB.finish(account, movement_id, [], held, ask_once=True)
            text = fin["say"]
        # Sasha 385 · THE ONE FINISH, to the door that started it (channel.tell: their last turn's channel — WhatsApp, or the S2 page / its
        # news): the "so what" line; ONE question — the mandate's own card for anyone outside the instruction (its explicit tap), else the
        # list's grouped question; and the report's link. The passport invitations are on the report (its "fix"), never a second paragraph.
        try:   # Sasha 385 · each passport link that went, on the trip: the report says it (never a second paragraph here)
            from . import group_report as GR
            await GR.invited(account, movement_id, list(inv.get("emailed") or []), rows)
        except Exception as e:
            log.warning("[mandate] the invitations weren't kept on the trip: %s", type(e).__name__)
        ask = card or (fin or {}).get("card")
        url = (fin or {}).get("report_url")
        await CH.tell(account, text, wa_text=text + (f"\nFull report → {url}" if url else ""),
                      event={"type": "group_done", "text": text, **({"card": ask} if ask else {}),
                             **({"report": url, "list": fin["list"]} if fin and url else {})},
                      news_key=f"group:{movement_id}", card=ask)
        await _close(account, movement_id, m, "done", text)
        j = GB._JOBS.get(account)
        if j is not None and j.get("kind") == "mandate":
            j.update(state="ready", result={"status": "done", "say": text, "done": done})
    except Exception as e:
        log.exception("[mandate] the job stopped: %s", type(e).__name__)
        stop = "I couldn't finish that just now — the master list shows what was done. Say “book them all” and I'll carry on from there."
        await CH.tell(account, stop, event={"type": "group_done", "text": stop}, news_key=f"group:{movement_id}")
        await _close(account, movement_id, m, "stopped", stop)
        j = GB._JOBS.get(account)
        if j is not None and j.get("kind") == "mandate":
            j.update(state="failed", why="Stopped — the master list shows what was done.")


def invited_words(inv: Dict[str, Any]) -> str:
    """The passport invitations, said as DONE (from invite_missing — the same names the master list marks)."""
    names = inv.get("invited") or []
    if not names:
        return ""
    emailed = [n for n in names if n in (inv.get("emailed") or [])]
    rest = [n for n in names if n not in emailed]
    out = ""
    if emailed:
        out += f" I've emailed {len(emailed)} {'person' if len(emailed) == 1 else 'people'} their secure link for their passport ({_and(emailed)}) — they're booked once it's in."
    if rest:
        out += f" No email on the list for {_and(rest)} — their passport link is on the Group page to forward."
    return out


def _and(xs: List[str]) -> str:
    return xs[0] if len(xs) == 1 else ", ".join(xs[:-1]) + " and " + xs[-1]


__all__ = ["wants_booking", "carry_out", "finished", "running", "invited_words", "sweep", "start"]
