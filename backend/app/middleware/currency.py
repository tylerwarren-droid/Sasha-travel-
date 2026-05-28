"""
Currency enforcement middleware.

Rejects any request that explicitly passes a non-USD currency.
All searches and bookings on this platform are USD-only; this guard
prevents accidental multi-currency state from reaching RateHawk.
"""

import json
import logging
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

logger = logging.getLogger("kanoe.currency")

CURRENCY_PATHS = ("/search/hotels", "/search/hotel/rates")


class CurrencyEnforcementMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.method == "POST" and request.url.path in CURRENCY_PATHS:
            try:
                body_bytes = await request.body()
                if body_bytes:
                    payload = json.loads(body_bytes)
                    currency = payload.get("currency")
                    if currency is not None and currency.upper() != "USD":
                        logger.warning(
                            "Rejected non-USD currency %r on %s",
                            currency,
                            request.url.path,
                        )
                        return JSONResponse(
                            status_code=422,
                            content={
                                "detail": f"Currency must be USD (received {currency!r}). "
                                          "This platform operates in USD only."
                            },
                        )
            except (json.JSONDecodeError, UnicodeDecodeError):
                pass  # malformed bodies fall through to normal validation

        return await call_next(request)
