"""Sasha 132 · ONE YES COVERS THE ESCALATION (the founder's decision, 3 Oct).

The first read-back says the whole plan in plain words — "If you haven't booked on their page within 30 minutes, I'll
email them; if they don't reply within 24 hours, I'll call them. Your yes covers these steps — I'll ask you again only if
something changes (a new time, a deposit, a cost)." — and the guest's ONE yes approves it. A later step (the email, the
call) is then sent under that yes: its approval is {"how": "escalation_plan", "from": {"kind": "link"|"email", "id": …}}.

⛔ The server never takes that on trust. verify() checks, from its OWN records, that the cited step:
  · belongs to this account, and was itself approved (a link is only made after the yes; an email only counts once sent);
  · has a stored read-back that contains the plan line (MARK) — the words the yes was given to, hashed with them;
  · is for the SAME venue read as the step now being sent;
  · is recent (PLAN_DAYS).
Anything else is refused, and the step is asked for afresh. What the new step says is still bound by its own read-back.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

MARK = "Your yes covers these steps"
PLAN_DAYS = 7


def plan_line(first: str, then: Optional[str]) -> str:
    """'If …, I'll email them; if …, I'll call them. Your yes covers these steps — …'"""
    steps = first + (f"; {then[0].lower()}{then[1:]}" if then else "")
    return f"{steps}. {MARK} — I'll ask you again only if something changes (a new time, a deposit, a cost)."


def has_plan(lines) -> bool:
    return any(MARK in str(x) for x in (lines or []))


async def verify(account: str, approval: Any, read_id: Optional[str]) -> Optional[str]:
    """None when the cited earlier yes really covers this step; otherwise why not (said to the caller)."""
    from . import ladder_routes as LR
    src = (approval or {}).get("from") if isinstance(approval, dict) else None
    if not isinstance(src, dict) or src.get("kind") not in ("link", "email") or not src.get("id"):
        return "an escalation must name the earlier step whose yes covers it"
    if src["kind"] == "link":
        row = await LR.LADDER_STORE.get_link(account, str(src["id"]))
        approved = row is not None   # a one-tap link with a plan is only ever made after the guest's yes
    else:
        row = await LR.LADDER_STORE.get_email(account, str(src["id"]))
        approved = bool(row and (row.get("sent_at") or row.get("approved_at")))
    if not row or not approved:
        return "that earlier step isn't yours, or was never approved"
    if not has_plan(row.get("read_back_lines")):
        return "the earlier yes didn't cover further steps — it has to be asked"
    if str(row.get("read_id")) != str(read_id):
        return "the earlier yes was for a different venue"
    made = row.get("created_at")
    if isinstance(made, str):
        made = datetime.fromisoformat(made)
    if made and datetime.now(timezone.utc) - made > timedelta(days=PLAN_DAYS):
        return "the earlier yes is too old to cover this"
    return None


__all__ = ["MARK", "plan_line", "has_plan", "verify", "PLAN_DAYS"]
