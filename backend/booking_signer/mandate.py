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


async def carry_out(account: str, said: str, who: Optional[List[str]] = None, over_ok: bool = False) -> Dict[str, Any]:
    """The instruction received: the whole job runs on its own (plan → hotel → book → finish). → {started, say} at once."""
    import secrets
    import time
    from . import group_book as GB
    if running(account):
        return {"started": False, "say": "I'm already on it — I'll tell you as it goes, and when it's done."}
    GB._JOBS[account] = {"id": "job_" + secrets.token_hex(8), "kind": "mandate", "state": "preparing", "total": 0, "ready": 0,
                         "at": time.time(), "result": None, "line": "Starting…"}
    _RUNS[account] = asyncio.ensure_future(_run(account, said, who, over_ok))
    await asyncio.sleep(0)
    return {"started": True, "say": "On it — I'm planning each person and the hotel, then booking within the company's limits. "
                                    "I'll tell you as it goes, and when it's done."}


async def finished(account: str) -> None:
    """Wait for the job running now (tests and the proof)."""
    t = _RUNS.get(account)
    if t is not None:
        await asyncio.shield(t)


async def _planning(account: str) -> None:
    """Each person's planning, reported as it lands ("Planning 3 of 6"), until everyone on the trip is planned (or why not)."""
    from . import groups as G
    last = None
    while True:
        v = await G.view(account)
        rows = v.get("rows") or []
        busy = sum(1 for r in rows if r["status"] in ("planning…", "not planned"))
        line = f"Planning {len(rows) - busy} of {len(rows)}"
        if line != last:
            _publish(account, "group_progress", line)
            last = line
        run = G._PLANS.get(account)
        if run is None or run.done():
            if busy == 0 or run is None:
                return
            await asyncio.shield(run)   # the last batch: its result, then one more read
            continue
        try:
            await asyncio.wait_for(asyncio.shield(run), POLL_S)
        except asyncio.TimeoutError:
            pass


async def _run(account: str, said: str, who: Optional[List[str]], over_ok: bool) -> None:
    from . import group_book as GB, group_outcome as GO, groups as G, live_events as LE
    try:
        await _planning(account)
        v = await G.view(account)
        if v.get("hotel_line"):
            _publish(account, "group_progress", v["hotel_line"])
        rows = [r for r in v.get("rows") or [] if not who or r["name"].lower() in {w.lower() for w in who}]
        inv = await G.invite_missing(account)   # every one without a passport: their secure link by email, now (ONE source: the list's ✓)
        held = [{"name": r["name"], "kind": GO.reason(r)} for r in rows if GO.reason(r) not in (None, "booked", "cancelled", "passport")]
        ready = [r["name"] for r in rows if GO.reason(r) is None]
        done: List[dict] = []
        if ready:
            _publish(account, "group_progress", f"Booking 0 of {len(ready)}")

            def prog(k: int, total: int) -> None:
                j = GB._JOBS.get(account) or {}
                j.update(ready=k, total=total)
            card = await GB.prepare(account, "book", ready, over_ok=over_ok, progress=prog)
            skipped = [{"name": x["name"], "kind": x.get("kind"), "code": x.get("code")} for x in card.get("skipped") or []
                       if x.get("kind") != "needs_vault"]   # invited above: said as done, never asked
            if card.get("status") == "awaiting_yes":   # the instruction IS the yes for everything inside the limits (its own words)
                n = len(card.get("read_back_id") and GB._CARDS.get(card["read_back_id"], {}).get("items") or [])

                def acted(k: int, total: int) -> None:
                    _publish(account, "group_progress", f"Booking {k} of {total}")
                res = await GB.confirm(account, card["read_back_id"], "group_yes", said, progress=acted, ask_once=True, also=held + skipped)
                fin = res.get("finish") or {}
                text = res.get("say") or fin.get("say") or "Done."
                done = res.get("done") or []
                log.info("[mandate] %s: %d booked of %d", account[:8], len(done), n)
            else:
                text = (await GB.finish(account, [], held + skipped, ask_once=True))["say"]
        else:
            text = (await GB.finish(account, [], held, ask_once=True))["say"]
        said_inv = invited_words(inv)   # done things first, the ONE question last
        text = text.replace(" Not booked — ", said_inv + " Not booked — ", 1) if " Not booked — " in text else text + said_inv
        _publish(account, "group_done", text)
        await LE.keep_news(account, f"group:{(v.get('movement') or {}).get('id')}", text)   # away: said when they're back
        j = GB._JOBS.get(account)
        if j is not None and j.get("kind") == "mandate":
            j.update(state="ready", result={"status": "done", "say": text, "done": done})
    except Exception as e:
        log.exception("[mandate] the job stopped: %s", type(e).__name__)
        _publish(account, "group_done", "I couldn't finish that just now — the master list shows what was done. Say “book them all” and "
                                        "I'll carry on from there.")
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


__all__ = ["wants_booking", "carry_out", "finished", "running", "invited_words"]
