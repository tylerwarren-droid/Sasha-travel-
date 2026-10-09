"""DIVE's own SQLite store (its own Railway volume): operators, suppliers, channels, products, packages, bundles, legs, approvals,
evidence, keys, events. Nothing is shared with the sandbox's database."""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

SCHEMA = """
create table if not exists operators (id text primary key, slug text unique not null, name text not null, timezone text not null,
  languages text not null, site_url text, footer text, published text, sandbox_end_user text, created_at text not null);
create table if not exists suppliers (id text primary key, operator_id text not null, name text not null, kind text not null, status text not null,
  source text not null, evidence_of_source text, confidence int, contacts text, created_at text not null);
create table if not exists channels (id text primary key, supplier_id text not null, rung int not null, kind text not null, address text not null,
  verified int not null default 0, verified_at text, verified_how text, answer_timeout_s int not null, quiet_hours text, language text not null,
  verify_state text, created_at text not null);
create table if not exists products (id text primary key, operator_id text not null, supplier_id text not null, title text not null, unit text not null,
  price text not null, capacity int, duration_minutes int, policy text not null, cutoff text, created_at text not null);
create table if not exists packages (id text primary key, operator_id text not null, title text not null, description text, components text not null,
  price text not null, published int not null default 0, created_at text not null);
create table if not exists bundles (id text primary key, operator_id text not null, package_id text, party int not null, starts_at text not null,
  customer text not null, total text not null, lines text not null, payload text not null, read_back_id text not null,
  read_back_sha256 text not null, state text not null, key_id text, evidence_id text, expires_at text not null,
  created_at text not null, updated_at text not null);
create table if not exists legs (id text primary key, bundle_id text not null, product_id text not null, supplier_id text not null, channel_id text,
  required int not null, title text not null, starts_at text not null, state text not null, requested_at text, answer_by text, answered_at text,
  reply_id text, reply text, parse text, evidence_id text, reference text, external text, seq int not null);
create table if not exists approvals (id text primary key, bundle_id text not null, read_back_sha256 text not null, payload_sha256 text not null,
  said text, method text not null, state text not null, approved_at text not null, expires_at text not null);
create table if not exists approval_links (token_hash text primary key, bundle_id text not null, created_at text not null, expires_at text not null,
  csrf text, used_at text);
create table if not exists evidence (id text primary key, operator_id text not null, body text not null, created_at text not null);
create table if not exists op_keys (key_id text primary key, operator_id text not null, label text not null, secret_hmac text not null,
  state text not null, created_at text not null);
create table if not exists events (id integer primary key autoincrement, operator_id text not null, bundle_id text, leg_id text, kind text not null,
  line text not null, evidence_id text, at text not null);
create table if not exists idempotency (operator_id text not null, op text not null, idem_key text not null, request_sha256 text not null,
  response text, status int, primary key (operator_id, op, idem_key));
create table if not exists cancellations (id text primary key, bundle_id text not null, lines text not null, payload text not null,
  read_back_sha256 text not null, state text not null, created_at text not null, updated_at text not null);
create table if not exists captured (id integer primary key autoincrement, channel text not null, to_ text not null, body text not null,
  real int not null default 0, at text not null);
-- CR 67 · what arrived on the REAL channels (signed webhooks, allow-listed senders only) and who said STOP
create table if not exists inbound (id integer primary key autoincrement, channel text not null, address text not null, provider_id text unique not null,
  text text not null, subject text, received_at text not null);
-- CR 68 · demos built from a REAL operator's public website: private, test mode, nothing ever sent to anyone
create table if not exists site_ops (id text primary key, slug text unique not null, url text not null, host text not null, name text not null,
  state text not null, progress text, why text, coverage text, summary text, published int not null default 0, model text, created_at text not null,
  updated_at text not null);
create table if not exists site_items (id text primary key, site_id text not null, kind text not null, status text not null, data text not null,
  source_url text, quote text, quote_found int not null default 0, instruction_like int not null default 0, confidence int not null,
  added_by text not null, channel text, created_at text not null);
create table if not exists site_bookings (id text primary key, site_id text not null, item_id text not null, body text not null, created_at text not null);
create table if not exists login_links (token_hash text primary key, created_at text not null, expires_at text not null, used_at text);
create table if not exists opt_outs (channel text not null, address text not null, at text not null, said text, primary key (channel, address));
"""

ADDED = [("bundles", "notes"), ("bundles", "evidence_id"), ("operators", "sandbox_end_user")]
_LOCK = threading.RLock()


class Store:
    def __init__(self, path: str):
        self.path = path
        self.db = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        with _LOCK:
            self.db.execute("pragma journal_mode=wal")
            self.db.executescript(SCHEMA)
            for table, col in ADDED:   # CR 65 · columns added to a database made before them (the live volume) — additive only
                if col not in {r[1] for r in self.db.execute(f"pragma table_info({table})")}:
                    self.db.execute(f"alter table {table} add column {col} text")

    def q(self, sql: str, *a) -> List[Dict[str, Any]]:
        with _LOCK:
            return [dict(r) for r in self.db.execute(sql, a).fetchall()]

    def one(self, sql: str, *a) -> Optional[Dict[str, Any]]:
        rows = self.q(sql, *a)
        return rows[0] if rows else None

    def x(self, sql: str, *a) -> int:
        with _LOCK:
            return self.db.execute(sql, a).rowcount


def now() -> datetime:
    return datetime.now(timezone.utc)


def ts(d: Optional[datetime] = None) -> str:
    return (d or now()).astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def later(minutes: float) -> str:
    return ts(now() + timedelta(minutes=minutes))


def parse_ts(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def dumps(v: Any) -> str:
    return json.dumps(v, ensure_ascii=False, sort_keys=True)


def loads(s: Optional[str]) -> Any:
    return json.loads(s) if s else None
