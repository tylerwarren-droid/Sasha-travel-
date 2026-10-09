"""Durable state: SQLite (a Railway volume in the sandbox) — or, CR 69, Postgres when AGAPI_DATABASE_URL is set (a Railway Postgres in the
agapi-sandbox project; the same SQL, translated in one place: ? placeholders, insert-or-replace/ignore → on conflict). Every object row is keyed by its account,
so two customers never see — or collide with — each other's ids, keys or idempotency claims."""
from __future__ import annotations

import hashlib
import json
import logging
import re
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
create table if not exists calendar_files (token_hash text primary key, account text not null, act_id text not null, ics text not null,
  created_at text not null);
create table if not exists webhook_endpoints (account text not null, id text not null, url text not null, secret text not null,
  state text not null, created_at text not null, events text, primary key (account, id));
create table if not exists webhook_deliveries (id text primary key, account text not null, endpoint_id text not null, event text not null,
  body text not null, created_at text not null, attempts int not null default 0, next_at text not null, state text not null,
  last_status int);
create table if not exists keep_keys (account text not null, end_user text not null, wrapped_dek blob not null, kek_version text not null,
  created_at text not null, primary key (account, end_user));
create table if not exists keep_items (account text not null, id text not null, end_user text not null, type text not null, tier text not null,
  masked text not null, fingerprint text not null, nonce blob not null, ciphertext blob not null, created_at text not null,
  last_used_at text, primary key (account, id));
create table if not exists keep_fills (account text not null, token_hash text primary key, item_id text not null, end_user text not null,
  purpose text not null, hold_id text, line text, state text not null, expires_at text not null, created_at text not null, used_at text);
create table if not exists keep_events (account text not null, id text not null, end_user text not null, kind text not null,
  item_id text not null, masked text not null, evidence_id text, at text not null, primary key (account, id));
create table if not exists wa_contacts (account text not null, number text not null, end_user text not null, name text,
  first_contact_at text not null, last_inbound_at text, opted_out_at text, primary key (account, number));
create table if not exists wa_replies (account text not null, id text not null, number text not null, body text not null,
  received_at text not null, primary key (account, id));
"""

_LOCK = threading.RLock()

# CR 69 · columns added after a database was made (both engines; additive only): (table, column, type)
ADDED = [("usage_records", "ms", "int"), ("accounts", "product", "text")]


_PK: Dict[str, List[str]] = {}


def _primary_keys() -> Dict[str, List[str]]:
    """Each table's primary key, read from the schema itself (for insert-or-replace → on conflict (pk) do update)."""
    if not _PK:
        for name, body in re.findall(r"create table if not exists (\w+) \((.*?)\);", _SCHEMA, re.S):
            m = re.search(r"primary key \(([^)]*)\)", body)
            cols = [c.strip() for c in m.group(1).split(",")] if m else [c.split()[0] for c in body.split(",") if "primary key" in c][:1]
            _PK[name] = cols
    return _PK


def pg_sql(sql: str) -> str:
    """SQLite's dialect, as Postgres reads it. Only what this service uses: ? → %s (a literal % doubled first), insert or ignore,
    insert or replace (an upsert on the table's primary key), blob → bytea."""
    out = sql.replace("%", "%%")
    m = re.match(r"\s*insert or (ignore|replace) into (\w+) \(([^)]*)\)(.*)$", out, re.S | re.I)
    if m:
        kind, table, cols, rest = m.group(1).lower(), m.group(2), [c.strip() for c in m.group(3).split(",")], m.group(4).rstrip().rstrip(";")
        out = f"insert into {table} ({', '.join(cols)}){rest}"
        if kind == "ignore":
            out += " on conflict do nothing"
        else:
            pk = _primary_keys().get(table) or []
            upd = [c for c in cols if c not in pk]
            out += f" on conflict ({', '.join(pk)}) do " + (("update set " + ", ".join(f"{c} = excluded.{c}" for c in upd)) if upd else "nothing")
    out = re.sub(r"\bblob\b", "bytea", out)
    return out.replace("?", "%s")


class Store:
    def __init__(self, path: Optional[str] = None, url: Optional[str] = None):
        url = url if url is not None else config.DATABASE_URL
        self.kind = "postgres" if url else "sqlite"
        if url:   # CR 69 · production: Postgres. A test's Store(path) gets its OWN schema, so tests stay isolated on one server.
            self.path = path
            self.schema = ("t_" + hashlib.sha256(path.encode()).hexdigest()[:16]) if path else (config.DB_SCHEMA or None)   # CR 70: agapi-live → "live"
            self._url = url
            self._connect()
            self._script(_SCHEMA)
            self.x("alter table webhook_endpoints add column if not exists events text")
            for table, col, typ in ADDED:
                self.x(f"alter table {table} add column if not exists {col} {typ}")
            return
        self.path = path or config.DB_PATH
        self.db = sqlite3.connect(self.path, check_same_thread=False, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("pragma journal_mode=wal")
        self.db.execute("pragma busy_timeout=5000")
        self.db.executescript(_SCHEMA)
        for col in ("alter table webhook_endpoints add column events text",):   # v1.0 columns on a database made before them
            try:
                self.db.execute(col)
            except sqlite3.OperationalError:
                pass
        for table, col, typ in ADDED:                                          # CR 69 columns, additive
            if col not in {r[1] for r in self.db.execute(f"pragma table_info({table})")}:
                self.db.execute(f"alter table {table} add column {col} {typ}")

    # ── Postgres ──────────────────────────────────────────────────────────────────────────────────────────────────────

    def _connect(self) -> None:
        import psycopg
        from psycopg.rows import dict_row
        self.db = psycopg.connect(self._url, autocommit=True, row_factory=dict_row, connect_timeout=10)
        if self.schema:
            self.db.execute(f"create schema if not exists {self.schema}")
            self.db.execute(f"set search_path to {self.schema}")

    def _script(self, script: str) -> None:
        with _LOCK:
            for stmt in [x.strip() for x in script.split(";") if x.strip()]:
                self.db.execute(pg_sql(stmt).replace("%%", "%"))

    def _pg(self, sql: str, a):
        import psycopg
        with _LOCK:
            for attempt in (1, 2):
                try:
                    return self.db.execute(pg_sql(sql), a)
                except psycopg.OperationalError:
                    if attempt == 2 or self._in_tx:
                        raise
                    logging.getLogger("agapi").warning("postgres connection lost; reconnecting")
                    self._connect()

    _in_tx = False

    def q(self, sql: str, *a) -> List[Dict[str, Any]]:
        if self.kind == "postgres":
            with _LOCK:
                cur = self._pg(sql, a)
                return [dict(r) for r in cur.fetchall()] if cur.description else []
        with _LOCK:
            return [dict(r) for r in self.db.execute(sql, a).fetchall()]

    def one(self, sql: str, *a) -> Optional[Dict[str, Any]]:
        r = self.q(sql, *a)
        return r[0] if r else None

    def x(self, sql: str, *a) -> int:
        if self.kind == "postgres":
            with _LOCK:
                return self._pg(sql, a).rowcount
        with _LOCK:
            return self.db.execute(sql, a).rowcount

    def raw_dump(self) -> bytes:
        """Every byte this store holds (tests prove a secret is NOWHERE): SQLite → the file (+ its WAL); Postgres → every row of every
        table in this store's schema, each value as text or raw bytes."""
        if self.kind == "sqlite":
            self.x("pragma wal_checkpoint(full)")
            raw = b""
            for suffix in ("", "-wal", "-shm"):
                try:
                    with open(self.path + suffix, "rb") as f:
                        raw += f.read()
                except FileNotFoundError:
                    pass
            return raw
        out = []
        for t in [r["table_name"] for r in self.q("select table_name from information_schema.tables where table_schema = current_schema()")]:
            for row in self.q(f"select * from {t}"):
                for v in row.values():
                    out.append(bytes(v) if isinstance(v, (bytes, memoryview)) else str(v).encode())
        return b"\n".join(out)

    def tx(self):
        store = self

        class _T:
            def __enter__(self):
                _LOCK.acquire()
                store.db.execute("begin" if store.kind == "postgres" else "begin immediate")
                store._in_tx = True

            def __exit__(self, et, ev, tb):
                try:
                    store.db.execute("rollback" if et else "commit")
                finally:
                    store._in_tx = False
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


# ── CR 69 · the one-time move of the SQLite data into Postgres (the same rows; the SQLite file is left as it was) ────────

def import_sqlite(sqlite_path: str, pg: "Store") -> Optional[Dict[str, Any]]:
    """Copies every table's rows from the SQLite file into an EMPTY Postgres, once (marker: agapi_migrations 'sqlite_import'), and
    checks the counts match table by table. → the counts, or None if already done / nothing to import."""
    import os
    pg.x("create table if not exists agapi_migrations (name text primary key, at text not null, detail text not null)")
    if pg.one("select 1 as y from agapi_migrations where name = 'sqlite_import'") or not os.path.exists(sqlite_path):
        return None
    src = sqlite3.connect(sqlite_path)
    src.row_factory = sqlite3.Row
    tables = [r[0] for r in src.execute("select name from sqlite_master where type = 'table' and name not like 'sqlite_%'")]
    counts: Dict[str, Any] = {}
    with pg.tx():
        for t in tables:
            if not pg.one("select 1 as y from information_schema.tables where table_name = ? and table_schema = current_schema()", t):
                pg.x(f"create table {t} (" + ", ".join(f"{r[1]} {r[2] or 'text'}" for r in src.execute(f"pragma table_info({t})")) + ")")
            have = {r["column_name"] for r in pg.q("select column_name from information_schema.columns where table_name = ? and "
                                                     "table_schema = current_schema()", t)}
            cols = [r[1] for r in src.execute(f"pragma table_info({t})") if r[1] in have]
            if pg.one(f"select count(*) as n from {t}")["n"]:
                raise RuntimeError(f"postgres table {t} isn't empty — the import runs only into an empty database")
            n = 0
            for row in src.execute(f"select {', '.join(cols)} from {t}"):
                pg.x(f"insert into {t} ({', '.join(cols)}) values ({', '.join('?' for _ in cols)})", *[row[c] for c in cols])
                n += 1
            counts[t] = n
        for t, n in counts.items():
            got = pg.one(f"select count(*) as n from {t}")["n"]
            if got != n:
                raise RuntimeError(f"{t}: {n} rows read, {got} in postgres")
        pg.x("insert into agapi_migrations (name, at, detail) values ('sqlite_import', ?, ?)", ts(), dumps({"from": sqlite_path, "counts": counts}))
    src.close()
    return counts
