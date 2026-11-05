"""Sasha 346 · EVERY organiser action answers — ONE place. docs/sasha/S-346-every-button-answers.md

Found live (Tyler, 5 Nov ~18:20 Madrid, /group): "Swap" didn't take and "Book all planned" did nothing — no request reached Sasha at all.
The page's buttons were greyed until their fields were filled (a grey button says nothing), and the invoice opened a pop-up after an await
(blocked: nothing). The class: an action that can end without saying what happened.

  run(account, action, args) → {done, say, missing?, taps?, …}

Every button on /group and the chat's same tools (group_book · group_swap · group_cancel · group_invite_vault · group_invoice ·
group_upload) come HERE, and nothing else decides what an action needs:
  1 what it needs from the organiser — NEEDS, each field by its name on the page ("who leaves", "who comes", "their home city")
  2 what it needs from the record — the master list as it is now (groups.view: the trips, AgAPI's booking record, the vault marks)
  3 the action itself (group_book · traveller_vault · groups) — its own answer, said
`say` is never empty (answered() holds it; a test holds answered()). Nothing here is a second copy of the list: it is read each time.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

log = logging.getLogger("booking_signer.group_outcome")

ACTIONS = ("book", "swap", "cancel", "invite", "invoice", "add")
VERB = {"book": "Book", "swap": "Swap", "cancel": "Cancel", "invite": "Invite", "invoice": "The invoice", "add": "Add these"}
#: what each action needs from the organiser, by the field's name ON THE PAGE (the same words in the chat)
NEEDS = {
    "swap": (("who", "who leaves"), ("to", "who comes")),
    "cancel": (("who", "who to cancel"),),
    "add": (("rows", "the list — paste it (Name, home city, out, back, grade — one per line) or choose a file"),),
}
NO_MOVEMENT = "There's no group movement yet — tell Sasha the company, where, when and the hotel area first."
PLAN_ONE_S = 75.0   # a swapped-in newcomer is planned while the organiser waits (one person); longer → the row fills in on its own


def _and(xs: List[str]) -> str:
    xs = [x for x in xs if x]
    return xs[0] if len(xs) == 1 else ", ".join(xs[:-1]) + " and " + xs[-1] if xs else ""


def _people(n: int) -> str:
    return f"{n} {'person' if n == 1 else 'people'}"


def answered(action: str, out: Dict[str, Any]) -> Dict[str, Any]:
    """The ONE exit: an outcome always says something — what was done, or exactly why not. An empty say is a bug, logged and said."""
    say = str(out.get("say") or out.get("why") or out.get("message") or "").strip()
    if not say:
        log.error("[group_outcome] %s answered without words: %s", action, sorted(out))
        say = f"{VERB.get(action, action)}: Sasha has no answer to show — nothing was changed. Try again."
    return {**out, "action": action, "done": bool(out.get("done")), "say": say}


def _no(say: str, **more: Any) -> Dict[str, Any]:
    return {"done": False, "say": say, **more}


def missing(action: str, a: Dict[str, Any]) -> List[str]:
    """The organiser's fields this action still needs (their names on the page) — empty when none."""
    out = []
    for key, words in NEEDS.get(action, ()):
        v = a.get(key)
        if v is None or (isinstance(v, str) and not v.strip()) or (isinstance(v, list) and not [x for x in v if str(x).strip()]):
            out.append(words)
    return out


async def run(account: str, action: str, a: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    a = dict(a or {})
    if action not in ACTIONS:
        return answered(action, _no(f"Sasha doesn't know the action “{action}”."))
    need = missing(action, a)
    if need:
        return answered(action, _no(f"{VERB[action]} needs {_and(need)}.", missing=need))
    try:
        return answered(action, await _HOW[action](account, a))
    except Exception as e:   # said as what it is — never silence, never a fake success
        log.error("[group_outcome] %s failed: %s", action, type(e).__name__)
        return answered(action, _no(f"{VERB[action]} didn't go through ({type(e).__name__}) — nothing was changed. Try again."))


async def _view(account: str) -> Dict[str, Any]:
    from . import groups as G
    return await G.view(account)


def _pick(rows: List[dict], who: Optional[List[str]]) -> tuple:
    if not who:
        return rows, []
    by = {r["name"].lower(): r for r in rows}
    by_id = {r["member_id"]: r for r in rows}
    got = [by.get(str(w).strip().lower()) or by_id.get(str(w)) for w in who]
    return [r for r in got if r], [str(w) for w, r in zip(who, got) if not r]


# ── book ──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────

def reason(r: dict) -> Optional[str]:
    """Why this worker can't be booked now (from the master list's own row), or None when they can be tried (over the limit included:
    its own tap, "Book anyway", comes from AgAPI's read-back)."""
    if r["status"] in ("booked", "cancelled", "not planned"):
        return r["status"]
    if not (r.get("vault") or {}).get("passport"):
        return "passport"
    return None


def held(rows: List[dict]) -> List[Dict[str, Any]]:
    """THE reasons the record gives for each worker who can't be booked now — as taps: `say` (counted) and, where there is one, the
    button (`label`). The job's card carries these SAME taps (group_book.start(held=…)) — never a second classification."""
    by: Dict[str, List[dict]] = {}
    for r in rows:
        by.setdefault(reason(r) or "", []).append(r)
    taps: List[Dict[str, Any]] = []
    if by.get("passport"):
        n = len(by["passport"])
        taps.append({"label": "Invite", "say": f"{n} {'is' if n == 1 else 'are'} waiting for their passport",
                     "invite": [r["member_id"] for r in by["passport"]]})
    if by.get("not planned"):
        n = len(by["not planned"])
        taps.append({"say": f"{n} {'isn’t' if n == 1 else 'aren’t'} planned yet (no flight or hotel on their trip) — ask Sasha to plan them"})
    if by.get("booked"):
        taps.append({"say": f"{len(by['booked'])} already booked"})
    if by.get("cancelled"):
        taps.append({"say": f"{len(by['cancelled'])} cancelled"})
    return taps


async def _book(account: str, a: Dict[str, Any]) -> Dict[str, Any]:
    from . import group_book as GB
    v = await _view(account)
    if v.get("why"):
        return _no(NO_MOVEMENT)
    if not v["rows"]:
        return _no("0 can be booked: nobody is on the list yet — add the list first.")
    rows, unknown = _pick(v["rows"], a.get("who"))
    if unknown:
        return _no(f"{_and(unknown)} {'isn’t' if len(unknown) == 1 else 'aren’t'} on the list — check the name.", missing=["who"])
    ready = [r for r in rows if reason(r) is None]
    taps = held([r for r in rows if reason(r) is not None])
    words = [t["say"] for t in taps]
    if not ready:
        return _no("0 can be booked: " + "; ".join(words) + ".", taps=taps)
    # the job prepares exactly the workers the record says can be tried; the held ones' reasons ride on its card (ONE classification)
    job = await GB.start(account, [r["name"] for r in ready], bool(a.get("over_ok")), held=taps)
    return {"done": True, "status": "preparing", **job,
            "say": f"Preparing {len(ready)} to book — AgAPI's read-backs come on ONE card; nothing is booked until you tap Yes."
                   + (f" Not in this booking: {'; '.join(words)}." if words else ""), "taps": taps}


# ── swap ──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────

async def _swap(account: str, a: Dict[str, Any]) -> Dict[str, Any]:
    from . import group_book as GB, groups as G
    v = await _view(account)
    if v.get("why"):
        return _no(NO_MOVEMENT)
    out_name = str((a["who"] if isinstance(a["who"], list) else [a["who"]])[0]).strip()
    in_name = str(a["to"]).strip()
    leaver, _ = _pick(v["rows"], [out_name])
    if not leaver:
        return _no(f"{out_name} isn't on the list — check the name of who leaves.", missing=["who leaves"])
    leaver = leaver[0]
    comer = next((r for r in v["rows"] if r["name"].lower() == in_name.lower()), None)
    city, grade = str(a.get("to_city") or "").strip(), str(a.get("to_grade") or "").strip()
    if not comer and not city:
        return _no(f"Swap needs {in_name}'s home city — they're not on the list yet (their grade too, or they take {leaver['name']}'s: "
                   f"{leaver.get('grade') or 'none'}).", missing=["their home city"])
    if leaver["status"] == "booked":   # a booking to swap: AgAPI's swap (its read-back on ONE card) — group_book.prepare, unchanged
        out = await GB.prepare(account, "swap", [leaver["name"]], in_name, bool(a.get("over_ok")),
                               newcomer={"city": city, "grade": grade or leaver.get("grade") or "worker"} if city else None)
        return {**out, "done": out.get("status") in ("awaiting_yes", "needs_vault")}
    # nothing booked for who leaves: the swap is the LIST's — who leaves comes off, who comes goes on in their place, planned now
    if comer:
        return _no(f"{comer['name']} is already on the list and {leaver['name']} has nothing booked — there's nothing to swap.")
    if leaver["status"] == "cancelled":
        return _no(f"{leaver['name']}'s booking was cancelled — it stays on the invoice. Add {in_name} to the list instead.")
    org = await GB._organiser(account)
    if not org:
        return _no("AgAPI's sandbox didn't answer, so Sasha can't check nothing is booked for "
                   f"{leaver['name']} — nothing changed. Try again.")
    if GB._latest(await GB._records(account), leaver["member_id"]):
        return _no(f"AgAPI has a booking record for {leaver['name']} — reload the list; the swap goes through the booking.")
    st = G.store()
    mv = await st.movement(account)
    line = ", ".join([in_name, city, str(leaver.get("out") or mv.get("starts_on") or ""), str(leaver.get("back") or mv.get("ends_on") or ""),
                      grade or str(leaver.get("grade") or "worker")])   # they take the leaver's dates, and grade unless one is given
    up = await G.upload(account, G.read_text(line), mv["id"])
    if not up.get("added"):
        return _no(f"{in_name} couldn't go on the list — {up.get('ask') or 'check the name and city'}. Nothing changed.")
    await st.remove_member(mv["id"], leaver["member_id"])
    new = next((m for m in await st.members(mv["id"]) if m["name"].lower() == in_name.lower()), None)
    planned = False
    if new:
        try:
            p = await asyncio.wait_for(G.plan(account, mv["id"], only=[new["id"]]), PLAN_ONE_S)
            planned = bool(p.get("planned"))
        except asyncio.TimeoutError:
            pass
    row = next((r for r in (await _view(account))["rows"] if new and r["member_id"] == new["id"]), None)
    said = (f"Swapped on the list: {leaver['name']} is off (nothing was booked for them); {in_name} is on — "
            f"{(row or {}).get('grade') or grade or 'no grade'}, from {city}.")
    if row and planned:
        said += f" Planned: {row.get('transport') or 'flight'}" + (f", €{row['price_eur']:.0f}" if row.get("price_eur") else "") + f" — {row['status']}."
    else:
        said += " Planning them now — their row fills in on the list."
    return {"done": True, "status": "swapped_on_list", "row": row, "say": said}


# ── cancel ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────

async def _cancel(account: str, a: Dict[str, Any]) -> Dict[str, Any]:
    from . import group_book as GB
    v = await _view(account)
    if v.get("why"):
        return _no(NO_MOVEMENT)
    rows, unknown = _pick(v["rows"], a["who"])
    if unknown:
        return _no(f"{_and(unknown)} {'isn’t' if len(unknown) == 1 else 'aren’t'} on the list — check the name.", missing=["who to cancel"])
    none = [r["name"] for r in rows if r["status"] != "booked"]
    if len(none) == len(rows):
        return _no(f"0 can be cancelled: {_and(none)} {'has' if len(none) == 1 else 'have'} no booking.")
    out = await GB.prepare(account, "cancel", [r["name"] for r in rows if r["status"] == "booked"])
    return {**out, "done": out.get("status") == "awaiting_yes",
            "say": out.get("say") or (f"Not cancelled: {_and(none)} — no booking." if none else "")}


# ── invite ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────

async def _invite(account: str, a: Dict[str, Any]) -> Dict[str, Any]:
    from . import traveller_vault as TV
    v = await _view(account)
    if v.get("why"):
        return _no(NO_MOVEMENT)
    if not v["rows"]:
        return _no("Nobody is on the list yet — add the list first, then invite them.")
    rows, unknown = _pick(v["rows"], a.get("who"))
    if unknown:
        return _no(f"{_and(unknown)} {'isn’t' if len(unknown) == 1 else 'aren’t'} on the list — check the name.")
    if not a.get("who"):   # everyone → everyone still without a passport
        rows = [r for r in rows if not (r.get("vault") or {}).get("passport")]
        if not rows:
            return _no(f"Nobody to invite: all {_people(len(v['rows']))} have their passport in the vault.")
    r = await TV.invite(account, [x["member_id"] for x in rows])
    if r.get("why"):
        return _no(r["why"])
    e, f = r.get("emailed") or [], r.get("forward") or []
    say = f"Invited {_people(len(e) + len(f))}: " + ("; ".join(x for x in [
        f"emailed {_and(e)}" if e else "",
        f"{len(f)} {'has' if len(f) == 1 else 'have'} no email on the list — their secure links are below to forward" if f else ""] if x))
    return {"done": True, "emailed": e, "forward": f, "links": f, "say": say + ". They add their passport there; you'll see a ✓, never the numbers."}


# ── the invoice ───────────────────────────────────────────────────────────────────────────────────────────────────────────────

async def _invoice(account: str, a: Dict[str, Any]) -> Dict[str, Any]:
    from . import group_book as GB, groups as G
    inv = await GB.invoice(account)
    if inv.get("why"):
        return _no(NO_MOVEMENT)
    if not inv["lines"] and not inv["adjustments"]:
        return _no("Nothing is booked yet — the invoice lists each booking, so there's nothing on it to show. Book first.", invoice=inv)
    mv = await G.store().movement(account)
    link = GB.invoice_link(account, mv["id"])
    n = len(inv["lines"])
    return {"done": True, **inv, "link": link,
            "say": f"The invoice {inv['number']} for {inv['to']}: {_people(n)} booked"
                   + (f", {len(inv['adjustments'])} adjustment{'s' if len(inv['adjustments']) != 1 else ''}" if inv["adjustments"] else "")
                   + f", total {inv['total']}{' (TEST)' if inv.get('test') else ''}."}


# ── add these (the list) ──────────────────────────────────────────────────────────────────────────────────────────────────────

async def _add(account: str, a: Dict[str, Any]) -> Dict[str, Any]:
    from . import groups as G
    rows = a["rows"]
    if not rows:
        return _no("No one could be read from that — one person per line: Name, home city, out, back, grade.", missing=["the list"])
    r = await G.upload(account, rows, a.get("movement") or None)
    if r.get("why"):
        return _no(NO_MOVEMENT)
    n = r.get("added") or 0
    if not n:
        return _no("0 added. " + (r.get("ask") or "No row could be read — Name, home city, out, back, grade."), ask=r.get("ask"))
    return {"done": True, **r, "say": f"Added {_people(n)} to the list." + (f" {r['ask']}" if r.get("ask") else "")}


_HOW = {"book": _book, "swap": _swap, "cancel": _cancel, "invite": _invite, "invoice": _invoice, "add": _add}

__all__ = ["run", "answered", "missing", "held", "NEEDS", "ACTIONS"]
