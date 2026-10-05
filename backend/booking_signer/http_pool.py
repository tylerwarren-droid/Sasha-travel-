"""Sasha 149 · ONE pooled HTTP client per event loop (keep-alive): a request to a host already reached reuses its open
connection instead of a new TCP + TLS handshake (measured from sfo: Routes 189 → 46 ms, Bland 59 → 39 ms). Per loop,
because a client is bound to the loop it was made on (each test makes its own). Timeouts stay per request."""
from __future__ import annotations

import asyncio
from typing import Any, Dict

_CLIENTS: Dict[int, Any] = {}


def client():
    import httpx
    loop = asyncio.get_running_loop()
    lc = _CLIENTS.get(id(loop))
    c = lc[1] if lc and lc[0] is loop else None
    if c is None or c.is_closed:
        for k in [k for k, (lp, v) in _CLIENTS.items() if lp.is_closed() or v.is_closed]:   # loops that ended (tests)
            _CLIENTS.pop(k, None)
        c = httpx.AsyncClient(follow_redirects=False,
                              limits=httpx.Limits(max_connections=50, max_keepalive_connections=20, keepalive_expiry=90.0))
        _CLIENTS[id(loop)] = (loop, c)
    return c


async def request(method: str, url: str, *, timeout: float, **kw):
    import httpx
    return await client().request(method, url, timeout=httpx.Timeout(timeout), **kw)


__all__ = ["client", "request"]
