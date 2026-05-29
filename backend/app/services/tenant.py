"""
Tenant resolution service.

Resolves a ClientConfig from either a bare hostname or a hashed API key
using the Supabase REST API (works from any environment; no direct DB port
needed). Results are TTL-cached in-process for TTL_SECONDS.
"""

import hashlib
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Optional

import httpx
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("kanoe.tenant")

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")
TTL_SECONDS = 300

_domain_cache: dict[str, tuple[Optional["ClientConfig"], float]] = {}
_key_cache: dict[str, tuple[Optional["ClientConfig"], float]] = {}

_HEADERS = {
    "apikey": SUPABASE_SERVICE_KEY,
    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
}


@dataclass
class ClientConfig:
    id: str
    slug: str
    display_name: str
    allowed_domains: list[str]
    config: dict
    resolution_method: str  # "domain" | "api_key"
    extra: dict = field(default_factory=dict)

    @property
    def persona_name(self) -> str:
        return self.config.get("persona_name", "Sasha")

    @property
    def feature_flags(self) -> dict:
        return self.config.get("feature_flags", {})

    def feature_enabled(self, flag: str) -> bool:
        return bool(self.feature_flags.get(flag, False))


def _hash_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode()).hexdigest()


def _from_row(row: dict, method: str) -> "ClientConfig":
    return ClientConfig(
        id=str(row["id"]),
        slug=row["slug"],
        display_name=row["display_name"],
        allowed_domains=list(row.get("allowed_domains") or []),
        config=dict(row.get("config") or {}),
        resolution_method=method,
    )


async def resolve_by_domain(host: str) -> Optional[ClientConfig]:
    """Return the ClientConfig whose allowed_domains contains *host*, or None."""
    now = time.monotonic()
    cached, expiry = _domain_cache.get(host, (None, 0.0))
    if expiry > now:
        return cached

    config = None
    try:
        async with httpx.AsyncClient() as http:
            r = await http.get(
                f"{SUPABASE_URL}/rest/v1/clients",
                params={
                    "select": "id,slug,display_name,allowed_domains,config",
                    "is_active": "eq.true",
                    # PostgREST array-contains filter: cs.{"hostname"}
                    "allowed_domains": f'cs.{{"{host}"}}',
                    "limit": "1",
                },
                headers=_HEADERS,
                timeout=5,
            )
        rows = r.json() if r.status_code == 200 else []
        config = _from_row(rows[0], "domain") if rows else None
    except Exception:
        logger.warning("Domain tenant lookup failed for %r", host)

    _domain_cache[host] = (config, now + TTL_SECONDS)
    if config:
        logger.debug("Resolved client %r via domain %r", config.slug, host)
    return config


async def resolve_by_api_key(raw_key: str) -> Optional[ClientConfig]:
    """Return the ClientConfig for *raw_key*, or None."""
    key_hash = _hash_key(raw_key)
    now = time.monotonic()
    cached, expiry = _key_cache.get(key_hash, (None, 0.0))
    if expiry > now:
        return cached

    config = None
    try:
        async with httpx.AsyncClient() as http:
            # Fetch key row with embedded client via PostgREST resource embedding
            r = await http.get(
                f"{SUPABASE_URL}/rest/v1/client_api_keys",
                params={
                    "select": "id,clients(id,slug,display_name,allowed_domains,config)",
                    "key_hash": f"eq.{key_hash}",
                    "is_active": "eq.true",
                    "limit": "1",
                },
                headers=_HEADERS,
                timeout=5,
            )
            rows = r.json() if r.status_code == 200 else []

            if rows and rows[0].get("clients"):
                client_row = rows[0]["clients"]
                config = _from_row(client_row, "api_key")
                # Fire-and-forget last_used_at stamp
                await http.patch(
                    f"{SUPABASE_URL}/rest/v1/client_api_keys",
                    params={"id": f"eq.{rows[0]['id']}"},
                    json={"last_used_at": "now()"},
                    headers=_HEADERS,
                    timeout=3,
                )
    except Exception:
        logger.warning("API-key tenant lookup failed")

    _key_cache[key_hash] = (config, now + TTL_SECONDS)
    if config:
        logger.debug("Resolved client %r via API key", config.slug)
    return config


def invalidate_domain(host: str) -> None:
    _domain_cache.pop(host, None)


def invalidate_all() -> None:
    _domain_cache.clear()
    _key_cache.clear()
