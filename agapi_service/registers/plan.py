"""registry.obtain_plan's ranking (EU 214 api.md §2) — deterministic and pure; spec/ext/vectors/registry-plan.json pins it.

  1. drop routes this actor can't use (a resident eID when AgAPI has none; the subject's own routes outside lane S)
  2. a route whose robots.txt disallows automated readers (or can't be read, or is on AD's never-fetch list) is NOT automated: it stays,
     as human_only — a person can still use the site
  3. tiers: api with a certified rail · web_form with an enabled route policy · web_form without one, or an uncertified api ("needs a
     decision") · human_only
  4. within a tier: cheaper, then faster, then the fresher claims
  5. each route: requires[] and obtainable_by_agapi (yes · with_human · no), said plainly; a document with no route stated by any
     source is "unknown", never "no"
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

ACTORS = ("agapi", "person", "subject")
NOT_AUTOMATED = ("disallowed", "unreadable", "never_fetch")
_REQ_BY_CHANNEL = {"eid": "eid", "account": "account", "post": "postal_address", "in_person": "in_person", "apostille": "apostille",
                   "intermediary": "intermediary"}
TIER_SAYS = {1: "certified instant rail", 2: "attended route with an enabled route policy", 3: "needs a decision first", 4: "a person must do it"}


def turnaround_rank(t: Optional[str]) -> int:
    if not t:
        return 10_000
    if t == "instant":
        return 0
    if t == "minutes":
        return 1
    if t.startswith("days:"):
        try:
            return 2 + int(t.split(":", 1)[1])
        except ValueError:
            return 10_000
    return 10_000


def _requires(r: dict, automation: str) -> List[str]:
    req = list(r.get("requires") or [])
    ch = r.get("channel")
    if ch in _REQ_BY_CHANNEL:
        req.append(_REQ_BY_CHANNEL[ch])
    if r.get("actor") == "resident_eid":
        req.append("eid")
    if r.get("actor") == "account_holder":
        req.append("account")
    if r.get("actor") == "subject":
        req.append("the_subject_applies")
    if (r.get("cost_minor") or 0) > 0:
        req.append("payment")
    if automation == "human_only" and ch in ("free_web", "paid_web"):
        req.append("a_person_uses_the_site")
    return sorted(set(req))


def rank(routes: List[Dict[str, Any]], actor: str = "agapi") -> Dict[str, Any]:
    """routes: [{route_id, channel, actor, automation, certified_rail, rail_withdrawn?, policy_enabled, robots_verdict, cost_minor,
    turnaround, freshest_read_at, who_may_obtain, requires?}] → {routes: ranked, excluded, obtainable_by_agapi}."""
    if actor not in ACTORS:
        raise ValueError("actor")
    keep, excluded = [], []
    for r in routes:
        ra = r.get("actor") or "anyone"
        who = r.get("who_may_obtain")
        if (ra == "subject" or who == "subject_only") and actor != "subject":
            excluded.append({"route_id": r["route_id"], "why": "only the subject can obtain it (lane S: the subject applies)"})
            continue
        if who == "authority_only":
            excluded.append({"route_id": r["route_id"], "why": "only an authority can obtain it"})
            continue
        if ra == "resident_eid" and actor == "agapi":
            excluded.append({"route_id": r["route_id"], "why": "needs a resident eID; AgAPI has none (a person with one can use it)"})
            continue
        automation, notes = r.get("automation") or "unknown", []
        if ra in ("account_holder", "intermediary") and automation != "human_only":
            automation = "human_only"
            notes.append("needs an account: AgAPI never logs in for anyone, so a person does this" if ra == "account_holder"
                         else "goes through an intermediary: a person arranges it")
        if (r.get("robots_verdict") in NOT_AUTOMATED) and automation in ("api", "web_form"):
            automation = "human_only"
            notes.append(f"robots.txt: {r['robots_verdict'].replace('_', ' ')} for automated readers — not automated; a person can still use it")
        if ra == "subject" or who == "subject_only":     # lane S: the subject applies themselves; AgAPI can only ask them to
            automation = "human_only"
        if automation == "api" and r.get("certified_rail") and not r.get("rail_withdrawn"):
            tier = 1
        elif automation == "web_form" and r.get("policy_enabled"):
            tier = 2
        elif automation in ("web_form", "api"):
            tier = 3
            notes.append("needs a route policy decision before AgAPI may run it" if automation == "web_form" else
                         ("its certified rail is withdrawn in AD's catalogue" if r.get("rail_withdrawn") else "no certified rail yet"))
        else:
            tier = 4
            if automation == "unknown":
                notes.append("the source doesn't say how it's obtained (channel unknown): treated as a person's job")
        obtainable = "yes" if tier in (1, 2) else ("no" if ra == "subject" or who == "subject_only" else "with_human")
        keep.append({**{k: r[k] for k in ("route_id",) if k in r}, "tier": tier, "tier_says": TIER_SAYS[tier], "automation": automation,
                     "obtainable_by_agapi": obtainable, "requires": _requires(r, automation), "notes": notes,
                     "_sort": (tier, r.get("cost_minor") if r.get("cost_minor") is not None else 10 ** 12, turnaround_rank(r.get("turnaround")),
                               not r.get("freshest_read_at"), "".join(chr(0x10FFFF - ord(c)) for c in (r.get("freshest_read_at") or "")),
                               r["route_id"])})   # fresher first; a route with no dated claim last
    keep.sort(key=lambda x: x["_sort"])
    for i, x in enumerate(keep, 1):
        x.pop("_sort")
        x["rank"] = i
    best = ("yes" if any(x["obtainable_by_agapi"] == "yes" for x in keep) else
            "with_human" if any(x["obtainable_by_agapi"] == "with_human" for x in keep) else
            "no" if keep or excluded else "unknown")    # no route stated by any source: unknown, never "no"
    return {"routes": keep, "excluded": excluded, "obtainable_by_agapi": best}
