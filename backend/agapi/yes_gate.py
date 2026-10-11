"""CR 76 · THE ONE YES RULE on /s2 — every S2 act that spends, sends or cancels goes through agapi/yes_one (generated from AgAPI 1.3):
read-back (recorded here when the person is shown it) → their yes in a LATER turn (yes_one's explicit_yes, any language) → the act,
checked by yes_one.check at the act's own claim() and consumed there, once. S1 never comes here (ctx.surface != "s2").

The tools keep their own read-backs and shas (they re-derive the act and refuse if it changed); this gate binds the yes to the read-back
the person was SHOWN, in the contract's order (AP1–AP9), and is the one place an S2 act can be refused for the yes."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, Optional, Tuple

from agapi.yes_one import yes_one as YES

FAMILY = {"hold_booking": "book", "hold_venue": "book_venue"}   # a read-back shown by one tool, acted on by another
OPERATION = {n: "sasha." + n for n in ("book", "book_venue", "cancel_venue", "send_email", "send_whatsapp", "running_late",
                                       "change_booking", "cancel_booking")}
_RB: Dict[Tuple[str, str], dict] = {}    # (account, act) → the yes_one read-back the person was shown
_APV: Dict[Tuple[str, str], dict] = {}   # (account, act) → their yes to it (a later turn), until the act consumes it


def _held(act: str, account: str) -> Optional[dict]:
    """The tool's own prepared act (sha + when), as it stands NOW."""
    if act == "book":
        from agapi import v0 as M
        return M._HELD.get(account)
    if act == "book_venue":
        from agapi import venues as M
        return M._HELD.get(account)
    if act == "cancel_venue":
        from agapi import venues as M
        return M._CANCEL.get(account)
    if act == "send_email":
        from agapi import s2_tools as M
        return M._HELD.get(account)
    if act == "send_whatsapp":
        from agapi import s2_whatsapp as M
        return M._HELD.get(account)
    from agapi import s2_manage as M
    h = M._HELD.get(account)
    return h if h and h.get("tool") == act else None


def _turn(ctx) -> str:
    return ctx.started.isoformat()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _current(act: str, h: dict) -> dict:
    return {"intent_id": act, "operation": OPERATION[act], "lines": [], "payload": {"read_back_sha256": h["sha"]}}


def shown(ctx, name: str, result) -> None:
    """After an S2 tool answered: if it read an act back, record that read-back (once per sha — read again, it stays the first)."""
    act = FAMILY.get(name, name)
    if act not in OPERATION or not isinstance(result, dict) or not result.get("read_back"):
        return
    h = _held(act, ctx.account)
    if not h or not h.get("sha"):
        return
    key, rb = (ctx.account, act), _RB.get((ctx.account, act))
    if rb and rb["payload_sha256"] == YES.sha256(_current(act, h)["payload"]) and YES._t(rb["expires_at"]) > datetime.now(timezone.utc):
        return
    cur = _current(act, h)
    _RB[key] = YES.read_back(ctx.account, act, cur["operation"], cur["lines"], cur["payload"], ctx.account, _turn(ctx), _now())
    _APV.pop(key, None)


def heard(ctx, name: str, said: Optional[str]) -> None:
    """Before an S2 act runs: their words this turn, if a yes to a read-back from an EARLIER turn, are the approval."""
    key = (ctx.account, name)
    rb = _RB.get(key)
    if not rb or rb["presented_turn_id"] == _turn(ctx) or not said:
        return
    if YES.explicit_yes_any(said, YES.act_kind(rb["operation"]))[0]:
        _APV[key] = YES.approval(rb, ctx.account, _turn(ctx), _now(), said=said, channel="sasha_chat")


def check(ctx, name: str, said: Optional[str]) -> Tuple[str, Optional[str]]:
    """At the act (claim): yes_one.check, in the contract's order. Valid → the approval is consumed (never acts twice)."""
    key = (ctx.account, name)
    rb, h = _RB.get(key), _held(name, ctx.account)
    if not rb or not h:
        return "no_read_back", None
    apv = _APV.get(key) or YES.approval(rb, ctx.account, _turn(ctx), _now(), said=said or "", channel="sasha_chat")
    got = YES.check(rb, apv, _current(name, h), _now())
    if got[0] == "valid":
        apv["state"] = "consumed"
        _RB.pop(key, None)
        _APV.pop(key, None)
    return got


SAY = {"no_read_back": "read it back to them first — their yes is bound to a read-back they've heard",
       "approval_same_turn": "say the read-back and ask them to go ahead; act once they say yes (in their next message)",
       "no_explicit_yes": "that isn't an explicit yes to this — ask them, then act",
       "approval_expired": "that read-back or yes is too old — read it back again and ask",
       "approval_consumed": "that yes was already used once — it is never used twice",
       "approval_void": "it changed since they said yes — read it back again and ask",
       "approval_untrusted_origin": "that yes didn't come from them — ask them",
       "approval_not_found": "read it back to them first and ask"}
