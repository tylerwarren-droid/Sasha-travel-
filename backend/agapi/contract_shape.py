"""Sasha 374 · CR 186 · A TEST DOUBLE MAY NOT ANSWER A FIELD AgAPI DOESN'T PUBLISH. ONE helper, from THE generated contract
(kanoe_contract.OPERATION_TYPES: each operation's <Op>Out).

  assert_shape(op, answer)     an envelope {ok, result} or a bare result → AssertionError naming every key AgAPI's <Op>Out doesn't have
  shaped(fn)                   an AgAPI double (whatever its signature: the op is its first argument that names an operation) whose every
                               answer goes through assert_shape
  guard(module, *hooks)        the client module's test hooks (CALL / _call): ANY double assigned to them — mock.patch.object included —
                               is shaped; the module's own real client is never wrapped. Called once at the bottom of each AgAPI client.

The real AgAPI is never checked here (it IS the source); only Sasha's stand-ins for it.
"""
from __future__ import annotations

import functools
import sys
import types
from typing import Any, Callable, Dict

import kanoe_contract as KC


def out_fields(op: str):
    t = KC.OPERATION_TYPES.get(op)
    return set(getattr(t[1], "__annotations__", {}) or {}) if t else None


def assert_shape(op: str, answer: Any) -> Any:
    if op not in KC.OPERATIONS:
        raise AssertionError(f"{op!r} is not an AgAPI operation (kanoe_contract {KC.CONTRACT_VERSION})")
    if not isinstance(answer, dict):
        return answer
    if "ok" in answer:
        if not answer.get("ok"):
            code = (answer.get("error") or {}).get("code")
            if code and code not in KC.ERROR_CODES and code not in ("timeout", "unreachable", "not_configured"):   # the transport's own
                raise AssertionError(f"{op}: the double answers error code {code!r}, which AgAPI doesn't publish")
            return answer
        result = answer.get("result")
    else:
        result = answer
    fields = out_fields(op)
    if isinstance(result, dict) and fields:
        extra = sorted(set(result) - fields)
        if extra:
            raise AssertionError(f"{op}: the double answers {extra}, which AgAPI's {op} output doesn't publish (kanoe_contract {KC.CONTRACT_VERSION})")
    return answer


def _op_of(args, kwargs) -> str:
    for a in list(args) + [kwargs.get("op")]:
        if isinstance(a, str) and a in KC.OPERATIONS:
            return a
    return ""


def shaped(fn: Callable) -> Callable:
    if getattr(fn, "_shaped", False):
        return fn

    @functools.wraps(fn)
    async def call(*args, **kwargs):
        r = fn(*args, **kwargs)
        if hasattr(r, "__await__"):
            r = await r
        op = _op_of(args, kwargs)
        return assert_shape(op, r) if op else r
    call._shaped = True   # type: ignore[attr-defined]
    return call


class _Guarded(types.ModuleType):
    def __setattr__(self, name: str, value: Any) -> None:
        reals: Dict[str, Any] = self.__dict__.get("_CONTRACT_REAL", {})
        if name in reals and callable(value) and value is not reals[name]:
            value = shaped(value)
        super().__setattr__(name, value)


def guard(module_name: str, *hooks: str) -> None:
    m = sys.modules[module_name]
    m.__dict__["_CONTRACT_REAL"] = {h: getattr(m, h) for h in hooks}
    m.__class__ = _Guarded


__all__ = ["assert_shape", "shaped", "guard", "out_fields"]
