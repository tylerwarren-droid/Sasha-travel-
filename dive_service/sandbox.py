"""DIVE's ONLY way into AgAPI: the sandbox's PUBLIC API (POST /v1/{operation}), with DIVE's OWN test key, like any partner.
No import of agapi_service, no shared database. Every call returns the AgAPI envelope as is; a transport failure is an outage."""
from __future__ import annotations

import json
import secrets
from typing import Any, Awaitable, Callable, Dict, Optional, Tuple

from . import config


async def _http(op: str, body: dict, headers: dict) -> Tuple[int, dict]:
    import httpx
    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as c:
        r = await c.post(f"{config.SANDBOX_URL}/v1/{op}", content=json.dumps(body), headers=headers)
    return r.status_code, r.json()


TRANSPORT: Callable[[str, dict, dict], Awaitable[Tuple[int, dict]]] = _http      # tests: a fake sandbox


async def call(op: str, body: Optional[dict] = None, *, approval: Optional[str] = None, idem: bool = False) -> Dict[str, Any]:
    if not config.SANDBOX_KEY:
        return {"ok": False, "error": {"code": "upstream_unreachable", "message": "DIVE has no sandbox key set (DIVE_SANDBOX_KEY)."}}
    h = {"Authorization": f"Bearer {config.SANDBOX_KEY}", "Content-Type": "application/json", "AgAPI-Version": "1.1"}
    if idem:
        h["Idempotency-Key"] = "dive-" + secrets.token_hex(12)
    if approval:
        h["AgAPI-Approval-Id"] = approval
    try:
        _, env = await TRANSPORT(op, body or {}, h)
        return env
    except Exception as e:
        return {"ok": False, "error": {"code": "upstream_unreachable", "message": f"the AgAPI sandbox didn't answer ({type(e).__name__})."}}
