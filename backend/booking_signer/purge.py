"""Sasha 236 · ACCOUNT DELETE = DELETE EVERYTHING (Tyler: "yes, we delete everything").

    purge(account) → {table: rows deleted}

The account's Keep (keep_fills, keep_items and keep_keys — the key goes, so every sealed value is shredded) and its /s2 records
(s2_acts, s2_wa_replies, s2_wa_contacts, s2_memory), from the database AND this process's memory. Called by the account's own
DELETE /api/booking/account/data (vault/gdpr.py). Found in 235: deleting a guest left its Keep and its Activity behind.
sql/042_account_purge.sql makes the same rows cascade from auth.users, so a deletion by any other path takes them too.

A table that isn't there yet counts 0; any other failure raises StorageUnavailable (the caller says the erasure is incomplete).
"""
from __future__ import annotations

import logging
import uuid
from typing import Dict

from .store import StorageUnavailable

log = logging.getLogger("sasha.purge")

# children first: a fill names its item
TABLES = ("keep_fills", "keep_items", "keep_keys", "s2_acts", "s2_wa_replies", "s2_wa_contacts", "s2_memory")
RUN = None   # tests replace it


def _run():
    if RUN is not None:
        return RUN
    from . import plan_store as PS
    return PS._run()


async def purge(account: str) -> Dict[str, int]:
    a = uuid.UUID(str(account))
    counts: Dict[str, int] = {}
    run = _run()
    for t in TABLES:
        if run is None:
            counts[t] = 0
            continue
        try:
            done = await run(lambda c, t=t: c.execute(f"delete from public.{t} where account_id = $1", a))
            counts[t] = int(str(done).split()[-1]) if done else 0
        except Exception as e:
            if type(e).__name__ == "UndefinedTableError" or getattr(e, "rule", "") in ("storage_not_configured", "storage_not_provisioned"):
                counts[t] = 0   # not applied / no database here: nothing of theirs is in it
                continue
            log.error("[purge] %s not purged: %s", t, type(e).__name__)
            raise StorageUnavailable("erasure_incomplete", f"{t} could not be deleted ({type(e).__name__})") from None
    _forget_in_memory(str(account))
    log.info("[purge] an account's Keep and /s2 records were deleted: %s", counts)
    return counts


def _forget_in_memory(account: str) -> None:
    """This process's copies (the fallbacks used before a table is applied)."""
    try:
        from agapi import s2_memory as MEM, s2_records as REC
        MEM._MEM.pop(account, None)
        REC.ACTS[:] = [r for r in REC.ACTS if r.get("account_id") != account]
        REC.REPLIES[:] = [r for r in REC.REPLIES if r.get("account_id") != account]
        for k in [k for k in REC.CONTACTS if k and k[0] == account]:
            REC.CONTACTS.pop(k, None)
    except Exception as e:
        log.info("[purge] memory not cleared: %s", type(e).__name__)


__all__ = ["purge", "TABLES"]
