"""Sasha 419 · THE LUXURY READER, for Julia: AgAPI's offseason.deltas (DESIGN §3.1), the ONE source of every figure she says.

Read with Sasha's own key (§3.1 (b); KANOE 13:29) through the one route (agapi_route's pinned family "offseason", live) and the one
transport (agapi_route.post). Typed by the vendored contract (kanoe_contract 1.104.0): the op by OP, the request's fields and levels by
OffseasonDeltasIn. A failed call (not configured, timeout, non-200, unknown_operation until CR 229) is UNREAD — never "nothing measured".
"""
from __future__ import annotations

import typing
from typing import Any, Dict, List, Mapping

import kanoe_contract as KC

FAMILY = "offseason"
TIMEOUT_S = 10.0
#: Phase 1 (Sasha 419): no live "check my dates" — the stay level (one stay, check_in + nights) is not offered to Julia yet
PHASE1_LEVELS = ("destination", "hotel")
_STAY_ONLY = ("check_in", "nights")


def _hints() -> Dict[str, Any]:
    return typing.get_type_hints(KC.OffseasonDeltasIn)


def tool_input_schema() -> Dict[str, Any]:
    """The tool's input, FROM the published request type: its levels (Phase 1's) and its fields (the stay-only ones held back)."""
    h = _hints()
    levels = [lv for lv in typing.get_args(h["level"]) if lv in PHASE1_LEVELS]
    props: Dict[str, Any] = {"level": {"type": "string", "enum": levels}}
    for name in h:
        if name != "level" and name not in _STAY_ONLY:
            props[name] = {"type": "string"}
    return {"type": "object", "properties": props, "required": ["level"]}


def request_body(args: Mapping[str, Any]) -> Dict[str, Any]:
    """The model's tool input → the request AgAPI reads: only the published fields Phase 1 offers, strings only."""
    schema = tool_input_schema()["properties"]
    level = args.get("level")
    body: Dict[str, Any] = {"level": level if level in schema["level"]["enum"] else PHASE1_LEVELS[0]}
    for k in schema:
        v = args.get(k)
        if k != "level" and isinstance(v, str) and v.strip():
            body[k] = v.strip()
    return body


async def deltas(args: Mapping[str, Any]) -> Dict[str, Any]:
    """{"ok": True, "result": the reader's answer} or {"ok": False, "why": a code}. Nothing else is ever returned."""
    from agapi import agapi_route as AR
    url, key = await AR.client_for(FAMILY)
    if not key:
        return {"ok": False, "why": "not_configured"}
    h = {"Authorization": f"Bearer {key}", "content-type": "application/json"}
    env = await AR.post(url, key, KC.OP.OFFSEASON_DELTAS, request_body(args), h, TIMEOUT_S)
    res = env.get("result") if isinstance(env, dict) and env.get("ok") else None
    if not isinstance(res, dict) or not isinstance(res.get("items"), list):
        return {"ok": False, "why": str(((env or {}).get("error") or {}).get("code") or "unreadable")}
    return {"ok": True, "result": res}


def has_observation(i: Mapping[str, Any]) -> bool:
    """The site's <Claim> rule (DESIGN §4, R5), for speech: a gap needs both sides observed; a closure its own window's side."""
    ids, at = i.get("observation_ids"), i.get("measured_at")
    if not isinstance(ids, Mapping) or not isinstance(at, Mapping):
        return False
    if i.get("kind") == "gap":
        return bool(ids.get("high")) and bool(ids.get("low")) and bool(at.get("high")) and bool(at.get("low"))
    c = i.get("closure")
    if i.get("kind") == "closure" and isinstance(c, Mapping) and c.get("window") in ("high", "low"):
        return bool(ids.get(c["window"])) and bool(at.get(c["window"]))
    return False


def items(outputs: List[Mapping[str, Any]]) -> List[Mapping[str, Any]]:
    return [i for o in outputs for i in (o.get("items") or []) if isinstance(i, Mapping)]


__all__ = ["FAMILY", "PHASE1_LEVELS", "tool_input_schema", "request_body", "deltas", "has_observation", "items"]
