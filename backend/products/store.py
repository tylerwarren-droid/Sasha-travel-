"""CR 1 · product cases — one row per CampusMe request or relocation file (sql/028_products.sql).

A case's id is a capability: 22 url-safe random characters, the only key to its hand-over or reviewer page (which a
parent opens from WhatsApp, often signed out). Cases expire after EXPIRES (personal data: a student's details, an
applicant's passport facts), and the daily retention job deletes them; an expired case is never served.
Until 028 is applied the memory store runs — a redeploy loses cases, and /api/booking/products/health says so.
"""
from __future__ import annotations

import copy
import json
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from booking_signer.store import StorageUnavailable

EXPIRES = timedelta(days=30)
NOW = lambda: datetime.now(timezone.utc)


PRODUCTS = ("campus", "relocation", "health")   # = 028's CHECK on product_cases.product (the memory store enforces it too)
SKILLS = ("trip", "diligence", "webstate")   # webstate: CR 16 · the web line's "which product asked last"                              # CR 13 · skills without their own product value: a conversation row is
                                                # stored under the product it serves, marked state.skill — no migration


def _column(product: str, pending: dict) -> str:
    return product if product in PRODUCTS else (pending.get("for") if pending.get("for") in PRODUCTS else "relocation")


def _named(r: dict) -> dict:
    """A conversation row as the router sees it: a skill's row under its own name."""
    if r and (r.get("state") or {}).get("skill"):
        r["product"] = r["state"]["skill"]
    return r


def new_id() -> str:
    return secrets.token_urlsafe(16)


class MemoryCaseStore:
    durable = False

    def __init__(self) -> None:
        self.rows: Dict[str, dict] = {}

    async def put(self, product: str, account: str, wa_key: str, state: dict) -> str:
        if product not in PRODUCTS:     # as Postgres's CHECK would: a memory-only pass must never hide it (CR 13 found it live)
            raise ValueError(f'new row violates check constraint "product_cases_product_check": {product!r}')
        cid = new_id()
        now = NOW()
        self.rows[cid] = {"id": cid, "product": product, "account_id": account, "wa_id_sha256": wa_key,
                          "state": copy.deepcopy(state), "created_at": now, "updated_at": now, "expires_at": now + EXPIRES}
        return cid

    async def get(self, cid: str) -> Optional[dict]:
        r = self.rows.get(cid or "")
        if not r or r["expires_at"] <= NOW():
            return None
        return copy.deepcopy(r)

    async def update(self, cid: str, state: dict) -> None:
        if cid in self.rows:
            self.rows[cid]["state"] = copy.deepcopy(state)
            self.rows[cid]["updated_at"] = NOW()

    async def of_account(self, account: str, product: str) -> List[dict]:
        now = NOW()
        return [copy.deepcopy(r) for r in self.rows.values()
                if r["account_id"] == account and r["product"] == product and r["expires_at"] > now]

    async def conversations(self, wa_key: str) -> List[dict]:
        """CR 10 · this WhatsApp number's set-aside product conversations (one row per product)."""
        now = NOW()
        return [_named(copy.deepcopy(r)) for r in self.rows.values() if r["wa_id_sha256"] == wa_key and r["expires_at"] > now
                and (r["state"] or {}).get("kind") == "conversation"]

    def _mine(self, r: dict, wa_key: str, product: str) -> bool:
        st = r["state"] or {}
        return r["wa_id_sha256"] == wa_key and st.get("kind") == "conversation" and (
            st.get("skill") == product if product in SKILLS else (r["product"] == product and not st.get("skill")))

    async def put_conversation(self, wa_key: str, account: str, product: str, pending: dict) -> None:
        state = {"kind": "conversation", "pending": copy.deepcopy(pending), **({"skill": product} if product in SKILLS else {})}
        for r in self.rows.values():
            if self._mine(r, wa_key, product):
                r["state"] = state
                r["updated_at"] = NOW()
                return
        await self.put(_column(product, pending), account, wa_key, state)

    async def drop_conversation(self, wa_key: str, product: str) -> None:
        for k in [k for k, r in self.rows.items() if self._mine(r, wa_key, product)]:
            del self.rows[k]

    async def of_product(self, product: str) -> List[dict]:
        now = NOW()
        return [copy.deepcopy(r) for r in self.rows.values() if r["product"] == product and r["expires_at"] > now]

    async def watching(self) -> List[dict]:
        now = NOW()
        return [copy.deepcopy(r) for r in self.rows.values()
                if r["product"] == "campus" and (r["state"].get("watch") or {}).get("open") and r["expires_at"] > now]


class PostgresCaseStore:
    durable = True

    def __init__(self, base) -> None:
        self._base = base

    async def _run(self, fn):
        try:
            return await self._base._run(fn)
        except StorageUnavailable as e:
            raise e.rehint("028_products.sql") from None

    @staticmethod
    def _row(r) -> Optional[dict]:
        if not r:
            return None
        d = dict(r)
        d["account_id"] = str(d["account_id"])
        d["state"] = json.loads(d["state"]) if isinstance(d["state"], str) else d["state"]
        return d

    async def put(self, product, account, wa_key, state):
        cid = new_id()
        await self._run(lambda c: c.execute(
            "insert into product_cases (id, product, account_id, wa_id_sha256, state, expires_at) "
            "values ($1, $2, $3, $4, $5::jsonb, now() + $6::interval)",
            cid, product, uuid.UUID(account), wa_key, state, EXPIRES))   # asyncpg encodes an interval from a timedelta only
        return cid

    async def get(self, cid):
        return self._row(await self._run(lambda c: c.fetchrow(
            "select * from product_cases where id = $1 and expires_at > now()", cid or "")))

    async def update(self, cid, state):
        await self._run(lambda c: c.execute(
            "update product_cases set state = $2::jsonb, updated_at = now() where id = $1", cid, state))

    async def of_account(self, account, product):
        rows = await self._run(lambda c: c.fetch(
            "select * from product_cases where account_id = $1 and product = $2 and expires_at > now() "
            "order by created_at desc limit 20", uuid.UUID(account), product))
        return [self._row(r) for r in rows]

    async def conversations(self, wa_key):
        rows = await self._run(lambda c: c.fetch(
            "select * from product_cases where wa_id_sha256 = $1 and state->>'kind' = 'conversation' and expires_at > now() "
            "order by updated_at desc", wa_key))
        return [_named(self._row(r)) for r in rows]

    # a skill's row: state.skill = its name (any product column); a product's own row: that product, no skill
    _MINE = ("wa_id_sha256 = $1 and state->>'kind' = 'conversation' and "
             "(case when $2 = any($3::text[]) then state->>'skill' = $2 else product = $2 and state->>'skill' is null end)")

    async def put_conversation(self, wa_key, account, product, pending):
        state = {"kind": "conversation", "pending": pending, **({"skill": product} if product in SKILLS else {})}
        n = await self._run(lambda c: c.execute(
            "update product_cases set state = $4::jsonb, updated_at = now(), expires_at = now() + $5::interval where " + self._MINE,
            wa_key, product, list(SKILLS), state, EXPIRES))
        if n.split()[-1] == "0":
            await self.put(_column(product, pending), account, wa_key, state)

    async def drop_conversation(self, wa_key, product):
        await self._run(lambda c: c.execute("delete from product_cases where " + self._MINE, wa_key, product, list(SKILLS)))

    async def of_product(self, product):
        rows = await self._run(lambda c: c.fetch(
            "select * from product_cases where product = $1 and expires_at > now() limit 500", product))
        return [self._row(r) for r in rows]

    async def watching(self):
        rows = await self._run(lambda c: c.fetch(
            "select * from product_cases where product = 'campus' and (state->'watch'->>'open')::boolean "
            "and expires_at > now() limit 200"))
        return [self._row(r) for r in rows]


STORE: Any = MemoryCaseStore()
BASE: Any = None   # booking_signer's Postgres base (trip_items for a registered visit), set by choose()


async def choose(base) -> str:
    """At startup: Postgres if 028 is applied there, else memory. Returns which, for /products/health."""
    global STORE, BASE
    BASE = base
    pg = PostgresCaseStore(base)
    try:
        await pg._run(lambda c: c.fetchval("select count(*) from product_cases where false"))
        STORE = pg
        return "postgres"
    except Exception as e:   # no DATABASE_URL, or 028 not applied yet
        STORE = MemoryCaseStore()
        return f"memory ({type(e).__name__}: {str(e)[:120]})"


async def expire_once() -> int:
    """Deletes expired cases; logs the count in retention_log (S-53's table) when it exists. Never deletes unlogged:
    without retention_log, nothing is deleted and the expired rows stay unserved (get() refuses them)."""
    if not getattr(STORE, "durable", False):
        now = NOW()
        gone = [k for k, r in STORE.rows.items() if r["expires_at"] <= now]
        for k in gone:
            del STORE.rows[k]
        return len(gone)

    async def fn(conn):
        if not await conn.fetchval("select to_regclass('public.retention_log') is not null"):
            return 0
        async with conn.transaction():
            n = await conn.fetchval("with d as (delete from product_cases where expires_at <= now() returning 1) select count(*) from d")
            await conn.execute("insert into retention_log (run_id, ran_at, rule, table_name, rows_affected, cutoff, note) "
                               "values ($1, now(), 'cr1_product_cases_30d', 'product_cases', $2, now(), 'CR 1 · cases expire after 30 days')",
                               uuid.uuid4(), n)
            return n
    return await STORE._run(fn)
