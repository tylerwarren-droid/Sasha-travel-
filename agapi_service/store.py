"""Durable state (SQLite here; the same tables move to Postgres on the service): keys (hashed), idempotency, offers, holds,
approvals, bookings, the proof log (hash-chained), usage. Every row is scoped to its API key."""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from . import config

_SCHEMA = """
create table if not exists api_keys (id text primary key, customer text not null, secret_sha256 text not null,
  created_at text not null, revoked_at text);
create table if not exists idempotency (key_id text not null, idem_key text not null, method text not null, path text not null,
  request_sha256 text not null, status int not null, response text not null, created_at text not null,
  primary key (key_id, idem_key));
create table if not exists offers (id text primary key, key_id text not null, kind text not null, data text not null,
  created_at text not null);
create table if not exists holds (id text primary key, key_id text not null, kind text not null, offer_id text, booking_id text,
  read_back text not null, read_back_sha256 text not null, status text not null, expires_at text not null, created_at text not null);
create table if not exists approvals (id text primary key, key_id text not null, hold_id text not null, token_sha256 text not null,
  read_back_sha256 text not null, status text not null, end_user text not null, created_at text not null, presented_at text,
  decided_at text, expires_at text not null, decision text, consumed_at text, void_reason text);
create table if not exists bookings (id text primary key, key_id text not null, hold_id text not null, approval_id text not null,
  kind text not null, status text not null, provider text not null, provider_ref text, data text not null,
  created_at text not null, updated_at text not null);
create table if not exists proof (key_id text not null, subject text not null, seq int not null, at text not null,
  type text not null, actor text not null, data text not null, prev_sha256 text not null, sha256 text not null,
  primary key (subject, seq));
create table if not exists usage (key_id text not null, day text not null, calls int not null default 0, finds int not null default 0,
  primary key (key_id, day));
"""

_LOCK = threading.RLock()


class Store:
    def __init__(self, path: Optional[str] = None):
        self.path = path or config.DB_PATH
        self.db = sqlite3.connect(self.path, check_same_thread=False, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("pragma journal_mode=wal")
        self.db.executescript(_SCHEMA)

    def q(self, sql: str, *a) -> list:
        with _LOCK:
            return [dict(r) for r in self.db.execute(sql, a).fetchall()]

    def one(self, sql: str, *a) -> Optional[Dict[str, Any]]:
        r = self.q(sql, *a)
        return r[0] if r else None

    def x(self, sql: str, *a) -> int:
        with _LOCK:
            return self.db.execute(sql, a).rowcount

    def tx(self):
        """`with store.tx():` — one atomic unit (BEGIN IMMEDIATE … COMMIT)."""
        store = self

        class _T:
            def __enter__(self):
                _LOCK.acquire()
                store.db.execute("begin immediate")

            def __exit__(self, et, ev, tb):
                try:
                    store.db.execute("rollback" if et else "commit")
                finally:
                    _LOCK.release()
                return False
        return _T()


def now() -> datetime:
    return datetime.now(timezone.utc)


def iso(d: datetime) -> str:
    return d.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def dumps(o: Any) -> str:
    return json.dumps(o, separators=(",", ":"), sort_keys=True, default=str)
