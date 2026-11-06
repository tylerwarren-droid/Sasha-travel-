"""Sasha 351 · ONE vault per person: fold every second copy (a vault still owned by an old trip row) into its person's own vault.

Run ONCE in the Sasha service (it needs the Keep's key service and the database), AFTER sql/054 archived the copies:
    railway ssh -s <sasha service> -- python -m booking_signer.vault_fold
Prints counts only — never a value, a mask or an id. Idempotent: run again, it does nothing. Then sql/055 drops member_id.
"""
import asyncio
import json


async def main() -> dict:
    from agapi import s2_keep as KEEP
    return await KEEP.fold_second_copies()


if __name__ == "__main__":
    print(json.dumps(asyncio.run(main())))
