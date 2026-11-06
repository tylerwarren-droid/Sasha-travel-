"""Sasha 353 · a surface's WHOLE tool set and prompt — what it CAN offer — for the tests that check surfaces against each other (S1 vs S2,
WhatsApp, parity). The per-turn need selection (app/agent/tool_need) is set aside here; tests/test_s353_gateway.py tests it."""
from unittest import mock

_P = []


def start():
    from app.agent import tool_need as TN
    p = mock.patch.multiple(TN, select=lambda tools, *a, **k: tools, system_for=lambda text, offered: text)
    p.start()
    _P.append(p)


def stop():
    while _P:
        _P.pop().stop()
