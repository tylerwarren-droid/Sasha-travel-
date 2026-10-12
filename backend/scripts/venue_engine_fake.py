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


def install() -> None:
    from agapi import venue_truth as VT
    VT.CALL = answer
    VT._CACHE.clear()
    print("VENUE ENGINE: saved answers (scripts/venue_engine_fake.py) — nothing fetched", flush=True)


__all__ = ["install", "answer", "CALLS"]
