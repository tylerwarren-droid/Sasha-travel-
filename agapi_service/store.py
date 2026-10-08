"""Durable state: SQLite (a Railway volume in the sandbox; Postgres when it outgrows it). Every object row is keyed by its account,
so two customers never see — or collide with — each other's ids, keys or idempotency claims."""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from . import config

_SCHEMA = """
create table if not exists accounts (id text primary key, name text not null, created_at text not null);
create table if not exists api_keys (key_id text primary key, account text not null, mode text not null, prefix text not null,
  secret_hmac text not null unique, scopes text not null, budget_units int not null, rate_per_min int not null, label text,
  state text not null, created_at text not null, last_used_at text, revoked_at text);
create table if not exists end_users (account text not null, id text not null, external_ref text not null, created_at text not null,
  primary key (account, id), unique (account, external_ref));
create table if not exists destinations (account text not null, end_user text not null, channel text not null, value text not null,
  verified int not null default 0, otp_hmac text, otp_expires_at text, verify_token_hash text unique, attempts int not null default 0,
  created_at text not null, primary key (account, end_user, channel, value));
create table if not exists offers (account text not null, ref text not null, kind text not null, data text not null, created_at text not null,
  primary key (account, ref));
create table if not exists intents (account text not null, id text not null, operation text not null, end_user text not null,
  target_act text, state text not null, created_at text not null, primary key (account, id));
create table if not exists read_backs (account text not null, id text not null, intent_id text not null, operation text not null,
  lines text not null, payload text not null, payload_sha256 text not null, read_back_sha256 text not null, total text,
  presented_to text not null, presented_at text, presented_turn_id text, presented_via text, expires_at text not null,
  irreversible int not null, state text not null, created_at text not null, primary key (account, id));
create table if not exists holds (account text not null, id text not null, intent_id text not null, read_back_id text not null,
  items text not null, total text not null, expires_at text not null, created_at text not null, primary key (account, id));
create table if not exists approval_links (token_hash text primary key, account text not null, read_back_id text not null,
  end_user text not null, channel text not null, destination text not null, expires_at text not null, csrf_hash text,
  presented_at text, used_at text, outcome text, created_at text not null);
create table if not exists approvals (account text not null, id text not null, read_back_id text not null, intent_id text not null,
  read_back_sha256 text not null, payload_sha256 text not null, method text not null, said text, lang text, approved_by text not null,
  approved_at text not null, approved_turn_id text not null, device text not null, expires_at text not null, irreversible int not null,
  state text not null, consumed_by_request_id text, void_reason text, primary key (account, id));
create table if not exists acts (account text not null, id text not null, intent_id text not null, kind text not null,
  target_act text, hold_id text, end_user text not null, outcome text not null, refund text, evidence_id text,
  pay_token_hash text unique, magic text, created_at text not null, updated_at text not null, primary key (account, id));
create table if not exists evidence (account text not null, id text not null, body text not null, created_at text not null,
  primary key (account, id));
create table if not exists idempotency (account text not null, scope text not null, idem_key text not null, request_sha256 text not null,
  state text not null, status int, response text, act_id text, created_at text not null, primary key (account, scope, idem_key));
create table if not exists usage_records (request_id text not null, key_id text not null, account text not null, mode text not null,
  operation text not null, cost_class text not null, cost_units int not null, replayed int not null, ok int not null,
  error_code text, at text not null);
create index if not exists usage_by_key on usage_records (key_id, at);
create table if not exists messages (account text not null, end_user text, to_ text not null, channel text not null, sent_at text not null,
  body text not null, approval_link text);
create table if not exists webhook_endpoints (account text not null, id text not null, url text not null, secret text not null,
  state text not null, created_at text not null, primary key (account, id));
create table if not exists webhook_deliveries (id text primary key, account text not null, endpoint_id text not null, event text not null,
  body text not null, created_at text not null, attempts int not null default 0, next_at text not null, state text not null,
  last_status int);
"""

_LOCK = threading.RLock()


class Store:
    def __init__(self, path: Optional[str] = None):
        self.path = path or config.DB_PATH
        self.db = sqlite3.connect(self.path, check_same_thread=False, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("pragma journal_mode=wal")
        self.db.execute("pragma busy_timeout=5000")
        self.db.executescript(_SCHEMA)

    def q(self, sql: str, *a) -> List[Dict[str, Any]]:
        with _LOCK:
            return [dict(r) for r in self.db.execute(sql, a).fetchall()]

    def one(self, sql: str, *a) -> Optional[Dict[str, Any]]:
        r = self.q(sql, *a)
        return r[0] if r else None

    def x(self, sql: str, *a) -> int:
        with _LOCK:
            return self.db.execute(sql, a).rowcount

    def tx(self):
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


# ── time: RFC 3339 UTC 'Z', microsecond precision, one fixed width (so string comparison is time comparison) ──────────────

NOW_OVERRIDE: Optional[datetime] = None   # tests


def now() -> datetime:
    return NOW_OVERRIDE or datetime.now(timezone.utc)


def ts(d: Optional[datetime] = None) -> str:
    d = (d or now()).astimezone(timezone.utc)
    return d.strftime("%Y-%m-%dT%H:%M:%S.") + f"{d.microsecond:06d}Z"     # one fixed width: string order is time order


def parse_ts(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def later(minutes: float = 0, seconds: float = 0, base: Optional[datetime] = None) -> str:
    return ts((base or now()) + timedelta(minutes=minutes, seconds=seconds))


def dumps(o: Any) -> str:
    return json.dumps(o, separators=(",", ":"), sort_keys=True, ensure_ascii=False, default=str)


def loads(s: Optional[str]) -> Any:
    return json.loads(s) if s else None
