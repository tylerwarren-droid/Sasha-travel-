"""CR 70 · AgAPI PHASE 2: Sasha's real providers behind the adapter interfaces (agapi_service/adapters.py). Used ONLY on agapi-live, and a
kind answers only once it is in AGAPI_CONNECTED_LIVE there. Each adapter calls Sasha's own code (booking_signer — imported, never copied) and
has a smoke() that spends nothing and contacts nobody (run through the signed /admin/smoke)."""
from __future__ import annotations

from typing import Any, Callable, Dict, Optional

STORE: Optional[Callable[[], Any]] = None      # app.py binds the store getter (daily caps, provider call counts)

import contextvars  # noqa: E402
# CR 71 · S2's guest: their own Sasha sign-in token (X-Sasha-Guest-Token), accepted ONLY from the sasha product's live key, for this
# request only — the ladder then acts as THAT guest at Sasha's booking routes (else Sasha's demo account)
GUEST_TOKEN: contextvars.ContextVar = contextvars.ContextVar("agapi_sasha_guest_token", default=None)


def bind(store_getter) -> None:
    global STORE
    STORE = store_getter


async def http(method: str, url: str, headers: Optional[dict] = None, json: Any = None, data: Any = None, timeout: float = 30.0, **kw):
    """The real HTTP Sasha's code expects (method, url, headers=, json=) → an httpx Response. The live network guard allows only
    config.LIVE_HOSTS."""
    import httpx
    async with httpx.AsyncClient(timeout=httpx.Timeout(timeout)) as c:
        return await c.request(method, url, headers=headers, json=json, data=data)


from .calendar import LiveCalendar  # noqa: E402
from .email import LiveEmail  # noqa: E402
from .flights import LiveFlights  # noqa: E402
from .ladder import LiveLadder  # noqa: E402
from .whatsapp import LiveWhatsApp  # noqa: E402
from .payments import LivePayments  # noqa: E402
from .places import LivePlaces  # noqa: E402

ADAPTERS: Dict[str, Any] = {"places": LivePlaces(), "flights": LiveFlights(), "payments": LivePayments(), "calendar": LiveCalendar(),
                           "email": LiveEmail(), "whatsapp": LiveWhatsApp(), "venue_ladder": LiveLadder()}
