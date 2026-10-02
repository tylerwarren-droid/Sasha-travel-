"""S-78 §6–§10 · the vault's tables (sql/021): items (sealed), uses (one per approval), events. Memory for tests.

Metadata reads never return a secret's bytes; the one read of a sealed item is crypto.SEALED_SQL, run through
fetch_sealed() on crypto's behalf.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from ..store import StorageUnavailable

META = ("id", "provider", "label", "kind", "special_category", "consent_at", "consent_wording_version", "created_at",
        "updated_at", "last_used_at", "revoked_at")
_SEALED = ("ciphertext", "nonce", "wrapped_dek", "kek_version")


def _meta(r: dict) -> dict:
    return {k: (str(r[k]) if k == "id" else r.get(k)) for k in META}


class MemoryVaultStore:
    def __init__(self) -> None:
        self.items: Dict[str, dict] = {}
        self.uses: Dict[str, dict] = {}
        self.events: List[dict] = []

    async def create(self, row: dict) -> None:
        self.items[row["id"]] = dict(row)

    async def reseal(self, account: str, item_id: str, sealed: dict, now: datetime) -> bool:
        r = self.items.get(item_id)
        if not r or r["account_id"] != account or r.get("revoked_at"):
            return False
        r.update(sealed, updated_at=now)
        return True

    async def list(self, account: str) -> List[dict]:
        return [_meta(r) for r in sorted(self.items.values(), key=lambda r: r["created_at"]) if r["account_id"] == account]

    async def get(self, account: str, item_id: str) -> Optional[dict]:
        r = self.items.get(item_id)
        return _meta(r) if r and r["account_id"] == account else None

    async def fetch_sealed(self, sql: str, item_id: str, account: str) -> Optional[dict]:
        r = self.items.get(item_id)
        return dict(r) if r and r["account_id"] == account else None

    async def revoke(self, account: str, item_id: str, now: datetime) -> Optional[dict]:
        r = self.items.get(item_id)
        if not r or r["account_id"] != account or r.get("revoked_at"):
            return None
        r.update({k: None for k in _SEALED}, revoked_at=now)
        for u in self.uses.values():
            if u["item_id"] == item_id and u["status"] == "pending":
                u["status"] = "cancelled"
        return _meta(r)

    async def claim_use(self, account, item_id, action_kind, action_ref, approval_sha256, now) -> Optional[str]:
        if any(u["item_id"] == item_id and u["approval_sha256"] == approval_sha256 for u in self.uses.values()):
            return None
        uid = str(uuid.uuid4())
        self.uses[uid] = {"id": uid, "account_id": account, "item_id": item_id, "action_kind": action_kind, "action_ref": action_ref,
                          "approval_sha256": approval_sha256, "status": "in_use", "started_at": now, "ended_at": None, "outcome_words": None}
        self.items[item_id]["last_used_at"] = now
        return uid

    async def end_use(self, use_id: str, status: str, words: Optional[str], now: datetime) -> None:
        self.uses[use_id].update(status=status, outcome_words=words, ended_at=now)

    async def uses_of(self, account: str, item_id: Optional[str] = None) -> List[dict]:
        return [dict(u) for u in sorted(self.uses.values(), key=lambda u: u["started_at"])
                if u["account_id"] == account and (item_id is None or u["item_id"] == item_id)]

    async def event(self, account: str, item_id: Optional[str], event: str, detail: dict, now: datetime) -> None:
        self.events.append({"account_id": account, "item_id": item_id, "event": event, "at": now, "detail": detail})

    async def events_of(self, account: str) -> List[dict]:
        return [dict(e) for e in self.events if e["account_id"] == account]

    async def delete_account(self, account: str) -> Dict[str, int]:
        n_items = [k for k, r in self.items.items() if r["account_id"] == account]
        for k in n_items:
            del self.items[k]
        n_uses = [k for k, u in self.uses.items() if u["account_id"] == account]
        for k in n_uses:
            del self.uses[k]
        before = len(self.events)
        self.events = [e for e in self.events if e["account_id"] != account]
        return {"vault_items": len(n_items), "vault_uses": len(n_uses), "vault_events": before - len(self.events)}


class PostgresVaultStore:
    def __init__(self, base) -> None:
        self._base = base

    async def _run(self, fn):
        try:
            return await self._base._run(fn)
        except StorageUnavailable as e:
            raise e.rehint("021_vault.sql") from None

    async def create(self, row):
        await self._run(lambda c: c.execute(
            "insert into vault_items (id, account_id, provider, label, kind, ciphertext, nonce, wrapped_dek, kek_version, "
            "special_category, consent_at, consent_wording_version, consent_text_sha256, created_at, updated_at) "
            "values ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$14)",
            uuid.UUID(row["id"]), uuid.UUID(row["account_id"]), row["provider"], row["label"], row["kind"], row.get("ciphertext"),
            row.get("nonce"), row.get("wrapped_dek"), row.get("kek_version"), bool(row.get("special_category")), row.get("consent_at"),
            row.get("consent_wording_version"), row.get("consent_text_sha256"), row["created_at"]))

    async def reseal(self, account, item_id, sealed, now):
        r = await self._run(lambda c: c.execute(
            "update vault_items set ciphertext = $3, nonce = $4, wrapped_dek = $5, kek_version = $6, updated_at = $7 "
            "where id = $1 and account_id = $2 and revoked_at is null",
            uuid.UUID(item_id), uuid.UUID(account), sealed["ciphertext"], sealed["nonce"], sealed["wrapped_dek"], sealed["kek_version"], now))
        return r.endswith(" 1")

    async def list(self, account):
        rows = await self._run(lambda c: c.fetch(f"select {', '.join(META)} from vault_items where account_id = $1 order by created_at",
                                                 uuid.UUID(account)))
        return [_meta(dict(r)) for r in rows]

    async def get(self, account, item_id):
        r = await self._run(lambda c: c.fetchrow(f"select {', '.join(META)} from vault_items where id = $1 and account_id = $2",
                                                 uuid.UUID(item_id), uuid.UUID(account)))
        return _meta(dict(r)) if r else None

    async def fetch_sealed(self, sql, item_id, account):
        r = await self._run(lambda c: c.fetchrow(sql, uuid.UUID(item_id), uuid.UUID(account)))
        return {**dict(r), "id": str(r["id"]), "account_id": str(r["account_id"])} if r else None

    async def revoke(self, account, item_id, now):
        async def go(c):
            async with c.transaction():
                r = await c.fetchrow(
                    f"update vault_items set ciphertext = null, nonce = null, wrapped_dek = null, kek_version = null, revoked_at = $3 "
                    f"where id = $1 and account_id = $2 and revoked_at is null returning {', '.join(META)}",
                    uuid.UUID(item_id), uuid.UUID(account), now)
                if r:
                    await c.execute("update vault_uses set status = 'cancelled' where item_id = $1 and status = 'pending'", uuid.UUID(item_id))
                return r
        r = await self._run(go)
        return _meta(dict(r)) if r else None

    async def claim_use(self, account, item_id, action_kind, action_ref, approval_sha256, now):
        async def go(c):
            async with c.transaction():
                r = await c.fetchrow(
                    "insert into vault_uses (account_id, item_id, action_kind, action_ref, approval_sha256, status, started_at) "
                    "values ($1,$2,$3,$4,$5,'in_use',$6) on conflict (item_id, approval_sha256) do nothing returning id",
                    uuid.UUID(account), uuid.UUID(item_id), action_kind, action_ref, approval_sha256, now)
                if r:
                    await c.execute("update vault_items set last_used_at = $2 where id = $1", uuid.UUID(item_id), now)
                return r
        r = await self._run(go)
        return str(r["id"]) if r else None

    async def end_use(self, use_id, status, words, now):
        await self._run(lambda c: c.execute("update vault_uses set status = $2, outcome_words = $3, ended_at = $4 where id = $1",
                                             uuid.UUID(use_id), status, words, now))

    async def uses_of(self, account, item_id=None):
        rows = await self._run(lambda c: c.fetch(
            "select * from vault_uses where account_id = $1 and ($2::uuid is null or item_id = $2) order by started_at",
            uuid.UUID(account), uuid.UUID(item_id) if item_id else None))
        return [{**dict(r), "id": str(r["id"]), "account_id": str(r["account_id"]), "item_id": str(r["item_id"])} for r in rows]

    async def event(self, account, item_id, event, detail, now):
        await self._run(lambda c: c.execute(
            "insert into vault_events (account_id, item_id, event, at, detail) values ($1,$2,$3,$4,$5::jsonb)",
            uuid.UUID(account), uuid.UUID(item_id) if item_id else None, event, now, json.dumps(detail)))

    async def events_of(self, account):
        rows = await self._run(lambda c: c.fetch("select item_id, event, at, detail from vault_events where account_id = $1 order by at",
                                                 uuid.UUID(account)))
        return [{**dict(r), "item_id": str(r["item_id"]) if r["item_id"] else None,
                 "detail": json.loads(r["detail"]) if isinstance(r["detail"], str) else r["detail"]} for r in rows]

    async def delete_account(self, account):
        async def go(c):
            async with c.transaction():
                a = uuid.UUID(account)
                u = await c.execute("delete from vault_uses where account_id = $1", a)
                e = await c.execute("delete from vault_events where account_id = $1", a)
                i = await c.execute("delete from vault_items where account_id = $1", a)
                return {"vault_items": int(i.split()[-1]), "vault_uses": int(u.split()[-1]), "vault_events": int(e.split()[-1])}
        return await self._run(go)


__all__ = ["MemoryVaultStore", "PostgresVaultStore", "META"]
