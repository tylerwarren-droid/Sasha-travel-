"""Sasha 323 · CR 152 (AgAPI v1.52.0) WIRED — a booking he made himself (a Renfe / Iryo / OUIGO España train) becomes one Sasha can manage.

  from_mail(account, email)  an email from his own inbox (the mailbox sync's narrow search; {from, subject, date, text}) → AgAPI's ONE reader,
                             venue.confirmation with no act_id: a known seller's confirmation (AgAPI's kind table decides whose — Sasha keeps
                             no list of sellers or domains) OPENS THE booking record. Sasha keeps the act on his trip ("Renfe · Madrid → …").
                             Not a known seller's → None (nothing kept, nothing said).
  manage(account, act_id)    venue.manage_options: what can be changed or cancelled under its fare (ONE fare table, AgAPI's), and WHERE — the
                             operator's own manage page with the reference to copy, filled never. None when AgAPI gives no page (a booking
                             AgAPI sent itself: its own cancel / change acts answer, as before).
  answer(res, action)        the fare's line for that action + the page as one button. Nothing is sent: he does it there.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

log = logging.getLogger("agapi.self_booked")


async def from_mail(account: str, email: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    from agapi import venue_submit as VS
    uid = await VS.end_user(account)
    if not uid:
        return None
    r = await VS._call(account, "venue.confirmation", {"end_user": uid, "emails": [{k: str(email.get(k) or "") for k in ("from", "subject", "date", "text")}]})
    if not r.get("ok"):   # invalid_input = not a confirmation from a seller AgAPI knows; anything else = AgAPI not answering
        code = (r.get("error") or {}).get("code")
        if code != "invalid_input":
            log.info("[self_booked] venue.confirmation not read: %s", code)
        return None
    res = r.get("result") or {}
    if not res.get("matched") or not res.get("act_id"):
        return {"matched": False, "say": res.get("say_text")} if res.get("say_text") else None
    t = res.get("trip") or {}
    leg = " → ".join(x for x in (t.get("origin"), t.get("destination")) if x)
    label = f"{t.get('operator') or 'Train'}" + (f" · {leg}" if leg else "")
    when = f"{t['date']}T{t['departs']}" if t.get("date") and t.get("departs") else (t.get("date") or "")
    await VS._remember(account, {"act_id": res["act_id"], "venue": label, "when": when, "party": t.get("passengers") or 1, "state": "confirmed",
                                 "reference": t.get("reference"), "kind": res.get("kind") or "train", "self_booked": True})
    return {"matched": True, "act_id": res["act_id"], "kind": res.get("kind"), "trip": t, "label": label, "say": res.get("say_text"),
            "already": bool(res.get("already"))}


async def manage(account: str, act_id: str) -> Optional[Dict[str, Any]]:
    from agapi import venue_submit as VS
    uid = await VS.end_user(account)
    if not uid or not act_id:
        return None
    r = await VS._call(account, "venue.manage_options", {"end_user": uid, "act_id": act_id})
    if not r.get("ok"):
        return None
    res = r.get("result") or {}
    return res if (res.get("where") or {}).get("page") else None


def answer(res: Dict[str, Any], action: str) -> Dict[str, Any]:
    op = res.get("operator") or "the operator"
    where = res.get("where") or {}
    opt = next((o for o in res.get("options") or [] if o.get("action") == action), None)
    head = (opt or {}).get("say") or res.get("say_text") or ""
    ref = where.get("reference")
    say = f"{head} It's done on {op}'s own page" + (f" — your reference is {ref}" if ref else "") + "."
    return {"status": "their_page", "venue": op, "sent": False, "say": say.strip(), "fare": res.get("fare"),
            "option": opt, "known": bool(res.get("known")), "reference": ref,
            "button": {"label": f"Open {op}", "link": where["page"]}, "open": where["page"],
            "how": "Say `say` as it is, once — nothing was sent or cancelled; the button opens their page. Never offer to do it yourself."}


__all__ = ["from_mail", "manage", "answer"]
