"""
Tenant-resolution middleware.

Resolution order:
  1. X-API-Key header  (server-to-server callers)
  2. Host header       (browser/frontend requests)

On success, sets request.state.client to a ClientConfig.
On failure (unrecognised domain/key), sets request.state.client = None
and continues — individual routes decide whether to gate on tenancy.

Skipped for health/docs paths so infrastructure tooling always works.
"""

import logging

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.services.tenant import resolve_by_api_key, resolve_by_domain

logger = logging.getLogger("kanoe.tenant")

_SKIP_PATHS = {"/", "/health", "/docs", "/openapi.json", "/redoc"}


def _bare_host(host_header: str) -> str:
    """Strip port from Host header: 'example.com:8080' → 'example.com'."""
    return host_header.split(":")[0].lower() if host_header else ""


class TenantMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        if request.url.path in _SKIP_PATHS:
            request.state.client = None
            return await call_next(request)

        client = None

        # 1. API key takes priority (server-to-server callers)
        raw_key = request.headers.get("X-API-Key", "").strip()
        if raw_key:
            try:
                client = await resolve_by_api_key(raw_key)
            except Exception:
                logger.exception("API-key tenant resolution failed")

        # 2. Fall back to Host header (browser / frontend)
        if client is None:
            host = _bare_host(request.headers.get("host", ""))
            if host:
                try:
                    client = await resolve_by_domain(host)
                except Exception:
                    logger.exception("Domain tenant resolution failed for %r", host)

        request.state.client = client
        return await call_next(request)
