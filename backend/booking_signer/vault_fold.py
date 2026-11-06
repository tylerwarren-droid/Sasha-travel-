"""Sasha 351 · ONE vault per person: fold every second copy (a vault still owned by an old trip row) into its person's own vault.

Run ONCE with the Sasha service's environment (its database and the Keep's key service), AFTER sql/054 archived the copies:
    railway run -s <sasha service> python3 -m booking_signer.vault_fold
It reads DATABASE_URL itself (never printed), runs s2_keep.fold_second_copies in ONE transaction (all folded, or none), and prints counts
only — never a value, a mask or an id. Idempotent: run again, it does nothing. Then sql/055 drops member_id.
"""
import asyncio
import json
import os


async def main() -> dict:
    import asyncpg
    from agapi import s2_keep as KEEP
    url = os.getenv("DATABASE_URL", "").replace("postgresql+asyncpg://", "postgresql://", 1)
    if not url:
        raise SystemExit("DATABASE_URL is not set — nothing was changed")
    c = await asyncpg.connect(url, statement_cache_size=0)
    try:
        async def run(fn):
            return await fn(c)
        KEEP.STORE = KEEP.PostgresKeepStore(run)
        async with c.transaction():
            return await KEEP.fold_second_copies()
    finally:
        await c.close()


if __name__ == "__main__":
    print(json.dumps(asyncio.run(main())))
