"""Sasha 248 · THE VENUE ENGINE, REPLAYED for the gate and the suites: agapi/venue_truth's engine call answered from saved
dive.onboard results (scripts/fixtures/venue_engine/<host>.json) — nothing is fetched, no AgAPI call. A site with no saved answer
is "not read", as the real engine says when it can't read one."""
from __future__ import annotations

import json
import os
from typing import Any, Dict

HERE = os.path.join(os.path.dirname(__file__), "fixtures", "venue_engine")
CALLS: list = []


async def answer(op: str, body: dict) -> Dict[str, Any]:
    from agapi import venue_truth as VT
    host = VT._host(body.get("url") or (body.get("place") or {}).get("website"))
    CALLS.append((op, host))
    if op == "venue.prepare_booking":   # CR 89 · ready to confirm on their phone; nothing submitted
        return {"ok": True, "result": {"venue_id": "ven_fake", "submitted": False, "link": f"https://agapi.test/prepared/{host}",
                                       "human_step": "Tap Confirm on their page — that's yours to press.", "say": "It's ready on your phone.",
                                       "missing": []}}
    path = os.path.join(HERE, f"{host}.json")
    if not os.path.exists(path):
        return {"ok": False, "error": {"code": "not_found", "message": f"{host} has no saved read (venue_engine_fake)"}}
    return {"ok": True, "result": json.load(open(path, encoding="utf-8"))}


async def submit_answer(op: str, body: dict, approval=None, account=None) -> dict:
    """Sasha 254 · AgAPI's booking sender (venue.prepare_booking / submit_booking, CR 90) as it answers — saved, so no suite ever
    reaches the live service (found by the gate: her_voice_suite's booking check reached agapi-live's submit_booking)."""
    CALLS.append(op)
    if op == "users.register":
        return {"ok": True, "result": {"end_user_id": "eu_gate"}}
    if op == "venue.prepare_booking":
        return {"ok": True, "result": {"venue_id": "v_gate", "venue": str((body.get("place") or {}).get("name") or "the venue"), "submitted": False,
                                       "prepared_id": "vpr_gate", "zero_touch_allowed": True, "link": "https://agapi.test/prepared/gate", "say": "ready"}}
    if op == "venue.submit_booking" and not approval:
        return {"ok": False, "error": {"code": "approval_required", "message": "the person's yes first", "retryable": False,
                                       "details": {"read_back_id": "rbk_gate", "read_back": {"lines": [
                                           "I'll send their own booking form with your details.", "Nothing is booked until they confirm."]}}}}
    if op == "sandbox.simulate_approval":
        return {"ok": True, "result": {"approval_id": "apv_gate"}}
    if op == "approvals.request":
        return {"ok": True, "result": {"read_back_id": "rbk_gate", "presentation": {"channel": body.get("channel")}}}
    if op == "approvals.status":
        return {"ok": True, "result": {"read_back_id": "rbk_gate", "approval": {"approval_id": "apv_gate", "state": "valid"}}}
    if op == "venue.submit_booking":
        return {"ok": True, "result": {"prepared_id": "vpr_gate", "status": "sent", "submitted": True, "act_id": "act_gate", "say": "Sent."}}
    if op == "venue.booking_status":
        return {"ok": True, "result": {"act_id": body.get("act_id"), "state": "sent", "say": "sent"}}
    return {"ok": False, "error": {"code": "unknown_op", "message": op}}


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
