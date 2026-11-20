"""Sasha 394 (2) · 382 + 387(b) · A TRIP'S TO-DOS ARE PACIOLI'S — the one caller of trip.check and the one picker of what a reply shows.

CR 198 (agapi-live b8ea1634, contract 1.98.0): ONE checker reads the ONE trip record (the group movement) and answers its findings in ONE
shape {trip, traveller, booking, kind, rule_id, source, as_of, needed, who, form, status open|not_checked, say} + its own trip-level say.
It is idempotent and keeps its last run: calling it IS reading it.

THE ROOT (row 2069):
  · a finding exists only as Pacioli's — Sasha keeps none (no table, no memory kind, no prompt copy, no stand-in shape);
  · of_trip(account, movement_id) keeps only the findings whose `trip` IS the movement being shown (387(b): the finding's own identity)
    and of those only status "open" — each ONE to-do, `who` and `form` exactly as Pacioli gave them (the person does only their own step:
    a form is prepared by Austen, entry.prepare; they only sign / pay / submit);
  · "not checked" is never dropped into "nothing needed": AgAPI's own say carries it ("…; N not checked yet");
  · AgAPI not answering → said as that ("couldn't check"), never "nothing to sort";
  · passport facts reach the checker as Keep references only (Tyler, 20 Nov: CR 163 / 189) — until AgAPI takes them (FOR CR), no vault is
    passed: the consistency findings are checked, the documents are Pacioli's own "not checked".
"""
from __future__ import annotations

import logging
import secrets
from typing import Any, Dict, List, Optional

from kanoe_contract import ERR, OP

log = logging.getLogger("booking_signer.trip_findings")

UNCHECKED = "I couldn't check this trip just now — nothing here means it's all fine; ask me again in a minute."
#: Pacioli's `who` → whose step it is, in the organiser's words
WHO = {"organiser": "you", "traveller": "the traveller", "AgAPI": "Kanoe", "the door": "Kanoe"}


def todo(f: Dict[str, Any], names: Dict[str, str]) -> Dict[str, Any]:
    """ONE open finding → ONE to-do, in Pacioli's words: its say, what's needed, whose step, and its official form (prepared by Austen)."""
    form = f.get("form") if isinstance(f.get("form"), dict) else None
    who = str(f.get("who") or "")
    person = names.get(str(f.get("traveller") or "")) if who == "traveller" else None
    return {"say": str(f.get("say") or ""), "needed": f.get("needed"), "who": who, "for": person or WHO.get(who, who),
            "kind": f.get("kind"), "rule_id": f.get("rule_id"), "source": f.get("source"), "as_of": f.get("as_of"),
            **({"form": {"link": form.get("official_url"), "prepared": bool(form.get("prepare")),
                         "you_only": list(form.get("stops_at") or [])}} if form and form.get("official_url") else {})}


def pick(found: Dict[str, Any], movement_id: str, names: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """trip.check's answer → what the trip's card shows: ONLY this movement's findings (each carries its trip), only the open ones as to-dos,
    and AgAPI's own say (its count of open and of not-checked)."""
    mine = [f for f in found.get("findings") or [] if isinstance(f, dict) and str(f.get("trip")) == str(movement_id)]
    return {"todos": [todo(f, names or {}) for f in mine if f.get("status") == "open"], "say": str(found.get("say") or ""),
            "not_checked": sum(1 for f in mine if f.get("status") == "not_checked"), "checked_at": found.get("checked_at")}


async def of_trip(account: str, movement_id: Optional[str], names: Optional[Dict[str, str]] = None) -> Optional[Dict[str, Any]]:
    """THE one caller of trip.check (the organiser's end user, THIS movement). None: nothing booked on it yet (Pacioli has no trip to read)."""
    if not movement_id:
        return None
    from . import group_book as GB
    org = await GB._organiser(account)
    if not org:
        return {"todos": [], "say": UNCHECKED, "unchecked": True}
    # Sasha 394 · Tyler (20 Nov): passport facts only as Keep references — none passed until trip.check takes them (FOR CR 1)
    r = await GB._send(account, OP.TRIP_CHECK, {"trip_id": str(movement_id), "end_user": org, "travellers": []},
                       "s394_check_" + secrets.token_hex(12))
    if not r.get("ok"):
        code = (r.get("error") or {}).get("code")
        if code == ERR.NOT_FOUND:   # Pacioli: "No bookings on that trip for this organiser" — nothing to check yet, said by the list itself
            return None
        log.warning("[trip_findings] trip.check on …%s not answered: %s", str(movement_id)[-6:], code)
        return {"todos": [], "say": UNCHECKED, "unchecked": True}
    return pick(r.get("result") or {}, str(movement_id), names)


def lines(t: Optional[Dict[str, Any]]) -> List[str]:
    """The to-dos as lines (WhatsApp): Pacioli's say first, then one line per to-do — whose step, its words, its official form."""
    if not t:
        return []
    out = [t["say"]] if t.get("say") else []
    for d in t.get("todos") or []:
        ln = f"To do ({d['for']}): {d['say']}"
        if d.get("form"):
            ln += f" Official form: {d['form']['link']}" + (" — prepared for them; they only " + ", ".join(d["form"]["you_only"])
                                                           if d["form"]["prepared"] and d["form"]["you_only"] else "")
        out.append(ln)
    return out


__all__ = ["of_trip", "pick", "todo", "lines", "UNCHECKED"]
