"""CR 70 · AgAPI PHASE 2: Sasha's real providers behind the adapter interfaces (agapi_service/adapters.py). Used ONLY on agapi-live, and a
kind answers only once it is in AGAPI_CONNECTED_LIVE there. Each adapter calls Sasha's own code (booking_signer — imported, never copied) and
has a smoke() that spends nothing and contacts nobody (run through the signed /admin/smoke)."""
from __future__ import annotations

from typing import Any, Callable, Dict, Optional

STORE: Optional[Callable[[], Any]] = None      # app.py binds the store getter (daily caps, provider call counts)


def bind(store_getter) -> None:
    global STORE
    STORE = store_getter


async def http(method: str, url: str, headers: Optional[dict] = None, json: Any = None, data: Any = None, timeout: float = 30.0, **kw):
    """The real HTTP Sasha's code expects (method, url, headers=, json=) → an httpx Response. The live network guard allows only
    config.LIVE_HOSTS."""
    import httpx
    async with httpx.AsyncClient(timeout=httpx.Timeout(timeout)) as c:
        return await c.request(method, url, headers=headers, json=json, data=data)


from .flights import LiveFlights  # noqa: E402
from .places import LivePlaces  # noqa: E402

ADAPTERS: Dict[str, Any] = {"places": LivePlaces(), "flights": LiveFlights()}
