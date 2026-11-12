"""Sasha 248 · THE VENUE ENGINE, REPLAYED for the gate and the suites: agapi/venue_truth's engine call answered from saved
dive.onboard results (scripts/fixtures/venue_engine/<host>.json) — nothing is fetched, no AgAPI call. A site with no saved answer
is "not read", as the real engine says when it can't read one."""
from __future__ import annotations
from kanoe_contract import ERR, OP  # Sasha 374 · THE ONE generated contract (CR 186)

import json
import os
from typing import Any, Dict

HERE = os.path.join(os.path.dirname(__file__), "fixtures", "venue_engine")
CALLS: list = []


async def answer(op: str, body: dict) -> Dict[str, Any]:
    """Sasha 374 · every saved answer is checked against AgAPI's published output (kanoe_contract: assert_shape)."""
    from agapi.contract_shape import assert_shape
    return assert_shape(op, await _answer(op, body))


async def _answer(op: str, body: dict) -> Dict[str, Any]:
    from agapi import venue_truth as VT
    host = VT._host(body.get("url") or (body.get("place") or {}).get("website"))
    CALLS.append((op, host))
    if op == OP.VENUE_PREPARE_BOOKING:   # CR 89 · ready to confirm on their phone; nothing submitted
        return {"ok": True, "result": {"venue_id": "ven_fake", "submitted": False, "link": f"https://agapi.test/prepared/{host}",
                                       "human_step": "Tap Confirm on their page — that's yours to press.", "say": "It's ready on your phone.",
                                       "missing": []}}
    path = os.path.join(HERE, f"{host}.json")
    if not os.path.exists(path):
        return {"ok": False, "error": {"code": "not_found", "message": f"{host} has no saved read (venue_engine_fake)"}}
    saved = json.load(open(path, encoding="utf-8"))
    saved.pop("fixture", None)   # Sasha 374 · the file's own provenance note — never part of AgAPI's answer
    return {"ok": True, "result": saved}


async def submit_answer(op: str, body: dict, approval=None, account=None) -> dict:
    from agapi.contract_shape import assert_shape
    return assert_shape(op, await _submit_answer(op, body, approval, account))


async def _submit_answer(op: str, body: dict, approval=None, account=None) -> dict:
    """Sasha 254 · AgAPI's booking sender (venue.prepare_booking / submit_booking, CR 90) as it answers — saved, so no suite ever
    reaches the live service (found by the gate: her_voice_suite's booking check reached agapi-live's submit_booking)."""
    CALLS.append(op)
    if op == OP.USERS_REGISTER:
        return {"ok": True, "result": {"end_user_id": "eu_gate"}}
    if op == OP.MESSAGES_WHATSAPP_INBOUND:   # Sasha 285 · CR 118 (b): a suite's numbers were never written to by Kanoe
        return {"ok": True, "result": {"matched": False, "kept": False}}
    if op == OP.VENUE_PREPARE_BOOKING:
        # Sasha 378 · CR 188 · prepare answers with venue.profile's ONE decision for this place (as AgAPI does) — never one of the fake's
        from agapi import venue_truth as VT
        dec = VT.decision({k: v for k, v in (body.get("place") or {}).items() if k in ("place_id", "website", "name")})
        return {"ok": True, "result": {"venue_id": "v_gate", "venue": str((body.get("place") or {}).get("name") or "the venue"), "submitted": False,
                                       "prepared_id": "vpr_gate", "zero_touch_allowed": True, "link": "https://agapi.test/prepared/gate", "say": "ready",
                                       **({"decision": dec} if dec else {})}}
    if op == OP.VENUE_SUBMIT_BOOKING and not approval:
        return {"ok": False, "error": {"code": "approval_required", "message": "the person's yes first", "retryable": False,
                                       "details": {"read_back_id": "rbk_gate", "read_back": {"lines": [
                                           "I'll send their own booking form with your details.", "Nothing is booked until they confirm."]}}}}
    if op == OP.SANDBOX_SIMULATE_APPROVAL:
        return {"ok": True, "result": {"approval_id": "apv_gate"}}
    if op == OP.APPROVALS_REQUEST:
        return {"ok": True, "result": {"read_back_id": "rbk_gate", "presentation": {"channel": body.get("channel")}}}
    if op == OP.APPROVALS_STATUS:
        return {"ok": True, "result": {"read_back_id": "rbk_gate", "approval": {"approval_id": "apv_gate", "state": "valid"}}}
    if op == OP.VENUE_SUBMIT_BOOKING and body.get("route") == "call":   # Sasha 319 · the call act: AgAPI's plan, simulated (never dialled)
        return {"ok": True, "result": {"prepared_id": "vpr_gate", "status": "calling", "submitted": True, "act_id": "act_gate_call",
                                       "say": "On it — I'll call them now and let you know.",
                                       "call_plan": {"call_id": "cpl_gate", "phone": "+34910000000", "simulate": True}}}
    if op == OP.VENUE_SUBMIT_BOOKING:
        return {"ok": True, "result": {"prepared_id": "vpr_gate", "status": "sent", "submitted": True, "act_id": "act_gate", "say": "Sent."}}
    if op == OP.VENUE_CANCEL_BOOKING and not approval:   # Sasha 319 · a cancellation is AgAPI's act too: its read-back first
        return {"ok": False, "error": {"code": "approval_required", "message": "the person's yes first", "retryable": False,
                                       "details": {"read_back_id": "rbk_gate_c", "read_back": {"lines": [
                                           "Cancel: the booking, by the route it was made."]}}}}
    if op == OP.VENUE_CANCEL_BOOKING:
        return {"ok": True, "result": {"status": "sent", "cancel_act_id": "act_gate_c", "say": "I've asked them to cancel it."}}
    if op == OP.VENUE_BOOKING_STATUS:
        return {"ok": True, "result": {"act_id": body.get("act_id"), "state": "sent", "say": "sent"}}
    if op == OP.VENUE_MANAGE_OPTIONS:   # Sasha 374 · a venue (not a train): AgAPI keeps no fare rules for it — its own published shape
        return {"ok": True, "result": {"act_id": body.get("act_id"), "kind": "venue", "known": False, "options": []}}
    return {"ok": False, "error": {"code": ERR.UNKNOWN_OPERATION, "message": op}}   # AgAPI's own code, never one of the fake's


def install(submit: bool = False) -> None:
    """The venue engine's saved answers; `submit=True` (the deploy gate, her_voice_suite) also the booking sender — opt-in, so a
    unit test that runs a suite in-process never inherits a fake sender."""
    from agapi import venue_truth as VT, venue_submit as VS
    VT.CALL = answer
    VT._CACHE.clear()
    if submit:
        VS.CALL = submit_answer   # Sasha 254 · no suite ever reaches AgAPI's live submit_booking
    print("VENUE ENGINE: saved answers (scripts/venue_engine_fake.py) — nothing fetched, nothing sent", flush=True)


__all__ = ["install", "answer", "CALLS"]
