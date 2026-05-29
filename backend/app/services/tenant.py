"""
Tenant resolution service.

Resolves a ClientConfig from either a bare hostname or a hashed API key.
Results are cached in-process for TTL_SECONDS to avoid a DB round-trip on
every request; the cache is keyed separately for domains vs. key hashes so
a key rotation invalidates only key entries.
"""

import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy import text

from app.db import SessionLocal

logger = logging.getLogger("kanoe.tenant")

TTL_SECONDS = 300  # 5-minute cache

# Cache entries: value is (ClientConfig | None, expiry_epoch)
_domain_cache: dict[str, tuple[Optional["ClientConfig"], float]] = {}
_key_cache: dict[str, tuple[Optional["ClientConfig"], float]] = {}


@dataclass
class ClientConfig:
    id: str
    slug: str
    display_name: str
    allowed_domains: list[str]
    config: dict
    resolution_method: str  # "domain" | "api_key"
    extra: dict = field(default_factory=dict)

    # Convenience helpers -------------------------------------------------------

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


def _row_to_config(row, method: str) -> ClientConfig:
    return ClientConfig(
        id=str(row.id),
        slug=row.slug,
        display_name=row.display_name,
        allowed_domains=list(row.allowed_domains or []),
        config=dict(row.config or {}),
        resolution_method=method,
    )


async def resolve_by_domain(host: str) -> Optional[ClientConfig]:
    """Return the ClientConfig whose allowed_domains contains *host*, or None."""
    now = time.monotonic()
    cached, expiry = _domain_cache.get(host, (None, 0.0))
    if expiry > now:
        return cached

    async with SessionLocal() as db:
        result = await db.execute(
            text(
                "SELECT id, slug, display_name, allowed_domains, config "
                "FROM clients "
                "WHERE is_active AND :host = ANY(allowed_domains) "
                "LIMIT 1"
            ),
            {"host": host},
        )
        row = result.fetchone()

    config = _row_to_config(row, "domain") if row else None
    _domain_cache[host] = (config, now + TTL_SECONDS)

    if config:
        logger.debug("Resolved client %r via domain %r", config.slug, host)
    else:
        logger.debug("No client for domain %r", host)

    return config


async def resolve_by_api_key(raw_key: str) -> Optional[ClientConfig]:
    """Return the ClientConfig for *raw_key*, or None if not found / inactive."""
    key_hash = _hash_key(raw_key)
    now = time.monotonic()
    cached, expiry = _key_cache.get(key_hash, (None, 0.0))
    if expiry > now:
        return cached

    async with SessionLocal() as db:
        result = await db.execute(
            text(
                "SELECT c.id, c.slug, c.display_name, c.allowed_domains, c.config, "
                "       k.id AS key_id "
                "FROM client_api_keys k "
                "JOIN clients c ON c.id = k.client_id "
                "WHERE k.key_hash = :kh AND k.is_active AND c.is_active "
                "LIMIT 1"
            ),
            {"kh": key_hash},
        )
        row = result.fetchone()

        if row:
            # Fire-and-forget last_used_at update — don't block the request
            await db.execute(
                text(
                    "UPDATE client_api_keys SET last_used_at = now() "
                    "WHERE id = :kid"
                ),
                {"kid": str(row.key_id)},
            )
            await db.commit()

    config = _row_to_config(row, "api_key") if row else None
    _key_cache[key_hash] = (config, now + TTL_SECONDS)

    if config:
        logger.debug("Resolved client %r via API key", config.slug)

    return config


def invalidate_domain(host: str) -> None:
    _domain_cache.pop(host, None)


def invalidate_all() -> None:
    _domain_cache.clear()
    _key_cache.clear()
