"""CR 62 · S2's own records: what it did (s2_acts — the Activity view's emails, WhatsApps and calendar adds, each with its proof),
the numbers it wrote to for someone (s2_wa_contacts: WhatsApp's 24-hour window, STOP) and what they wrote back (s2_wa_replies —
their words, never instructions). Postgres when booking_signer/sql/036_s2_activity_whatsapp.sql is applied; memory until then,
said in the log once. Every function is account-scoped; none raises for a missing table.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from agapi import powers as P

log = logging.getLogger("agapi.s2.records")
NOW = lambda: datetime.now(timezone.utc)
ACTS: List[dict] = []                                 # memory fallback (until 036 is applied)
CONTACTS: Dict[tuple, dict] = {}                      # (account, number) → contact
REPLIES: List[dict] = []
RUN = None                                            # tests set a runner; otherwise the ladder store's
_warned = set()


def _run():
    if RUN is not None:
        return RUN
    from booking_signer import plan_store as PS
    return PS._run()


async def _db(fn, what: str):
    """→ (True, result) from Postgres, or (False, None) when there is no database or 036 isn't applied (memory is used)."""
    run = _run()
    if run is None:
        return False, None
    try:
        return True, await run(fn)
    except Exception as e:
        if what not in _warned:
            _warned.add(what)
            log.warning("[s2] %s kept in memory — apply 036_s2_activity_whatsapp.sql (%s)", what, type(e).__name__)
        return False, None


def proof_sha256(proof: dict) -> str:
    return P.sha256(proof)


def verified(row: dict) -> bool:
    """The proof still hashes to what was stored, and names a provider reference (a message id, an event's sha256)."""
    proof = row.get("proof") or {}
    return proof_sha256(proof) == row.get("proof_sha256") and bool(proof.get("reference"))


def _iso(v) -> str:
    return v.isoformat() if hasattr(v, "isoformat") else str(v)


def _plain(r) -> dict:
    d = dict(r)
    for k, v in list(d.items()):
        if isinstance(v, uuid.UUID):
            d[k] = str(v)
        elif isinstance(v, datetime):
            d[k] = v.isoformat()
        elif k == "proof" and isinstance(v, str):
            d[k] = json.loads(v)
    return d


# ── what S2 did ──────────────────────────────────────────────────────────────────────────────────────────────────────────────

async def record(account: str, kind: str, state: str, proof: dict, about: Optional[str] = None) -> dict:
    """One Activity row. `proof` holds only facts we have: reference, at, said, read_back_sha256, body_sha256, …"""
    row = {"id": str(uuid.uuid4()), "account_id": account, "kind": kind, "state": state, "about": (about or "")[:300] or None,
           "proof": proof, "proof_sha256": proof_sha256(proof), "at": NOW().isoformat()}

    async def put(conn):
        await conn.execute("insert into s2_acts (id, account_id, kind, state, about, proof, proof_sha256, at) "
                           "values ($1::uuid, $2::uuid, $3, $4, $5, $6::jsonb, $7, $8::timestamptz)", row["id"], account, kind, state,
                           row["about"], json.dumps(proof), row["proof_sha256"], NOW())
    ok, _ = await _db(put, "S2 activity")
    if not ok:
        ACTS.append(row)
    return row


async def acts(account: str, since: Optional[str] = None) -> List[dict]:
    async def get(conn):
        return await conn.fetch("select * from s2_acts where account_id = $1::uuid and ($2::timestamptz is null or at >= $2::timestamptz) "
                                "order by at desc limit 200", account, datetime.fromisoformat(since) if since else None)
    ok, rows = await _db(get, "S2 activity")
    mem = [r for r in ACTS if r["account_id"] == account and (not since or r["at"] >= since)]
    return ([_plain(r) for r in rows] if ok else []) + mem


# ── WhatsApp: the people S2 wrote to, and what they wrote back ───────────────────────────────────────────────────────────────

async def contact(account: str, number: str) -> Optional[dict]:
    async def get(conn):
        return await conn.fetchrow("select * from s2_wa_contacts where account_id = $1::uuid and number_e164 = $2", account, number)
    ok, row = await _db(get, "WhatsApp contacts")
    if ok and row:
        return _plain(row)
    return CONTACTS.get((account, number))


async def wrote_to(account: str, number: str, name: Optional[str], on_behalf_of: Optional[str]) -> None:
    async def put(conn):
        await conn.execute("insert into s2_wa_contacts (account_id, number_e164, name, on_behalf_of) values ($1::uuid, $2, $3, $4) "
                           "on conflict (account_id, number_e164) do update set name = coalesce(excluded.name, s2_wa_contacts.name), "
                           "on_behalf_of = coalesce(excluded.on_behalf_of, s2_wa_contacts.on_behalf_of)", account, number, name, on_behalf_of)
    ok, _ = await _db(put, "WhatsApp contacts")
    if not ok:
        c = CONTACTS.setdefault((account, number), {"account_id": account, "number_e164": number, "first_contact_at": NOW().isoformat(),
                                                    "last_inbound_at": None, "opted_out_at": None})
        c["name"] = name or c.get("name")
        c["on_behalf_of"] = on_behalf_of or c.get("on_behalf_of")


async def contacts_for_number(number: str) -> List[dict]:
    """Every account Sasha wrote to this number for (newest first) — the inbound hook's question."""
    async def get(conn):
        return await conn.fetch("select * from s2_wa_contacts where number_e164 = $1 order by first_contact_at desc", number)
    ok, rows = await _db(get, "WhatsApp contacts")
    mem = sorted((c for (a, n), c in CONTACTS.items() if n == number), key=lambda c: c["first_contact_at"], reverse=True)
    return ([_plain(r) for r in rows] if ok else []) + mem


async def replied(account: str, number: str, body: str, stop: bool) -> dict:
    """Their reply: kept as their words; opens the 24-hour window; STOP is final (never undone by a later message)."""
    now = NOW()
    row = {"id": str(uuid.uuid4()), "account_id": account, "number_e164": number, "body": body[:4096], "received_at": now.isoformat()}

    async def put(conn):
        await conn.execute("insert into s2_wa_replies (id, account_id, number_e164, body, received_at) values ($1::uuid, $2::uuid, $3, $4, $5)",
                           row["id"], account, number, row["body"], now)
        await conn.execute("update s2_wa_contacts set last_inbound_at = $3, opted_out_at = coalesce(opted_out_at, $4) "
                           "where account_id = $1::uuid and number_e164 = $2", account, number, now, now if stop else None)
    ok, _ = await _db(put, "WhatsApp replies")
    if not ok:
        REPLIES.append(row)
        c = CONTACTS.get((account, number))
        if c:
            c["last_inbound_at"] = now.isoformat()
            c["opted_out_at"] = c.get("opted_out_at") or (now.isoformat() if stop else None)
    return row


async def replies(account: str, since: Optional[str] = None) -> List[dict]:
    async def get(conn):
        return await conn.fetch("select r.*, c.name from s2_wa_replies r left join s2_wa_contacts c on c.account_id = r.account_id "
                                "and c.number_e164 = r.number_e164 where r.account_id = $1::uuid "
                                "and ($2::timestamptz is null or r.received_at >= $2::timestamptz) order by r.received_at desc limit 100",
                                account, datetime.fromisoformat(since) if since else None)
    ok, rows = await _db(get, "WhatsApp replies")
    mem = [{**r, "name": (CONTACTS.get((account, r["number_e164"])) or {}).get("name")} for r in REPLIES
           if r["account_id"] == account and (not since or r["received_at"] >= since)]
    return ([_plain(r) for r in rows] if ok else []) + mem


def clear_memory() -> None:
    ACTS.clear()
    CONTACTS.clear()
    REPLIES.clear()
    _warned.clear()
