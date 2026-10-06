"""CR 44 · ONE RELOCATION KEEP RECORD: the mover's own details — passport data, birth, parents' names, Spanish address, phone,
email, home address abroad, occupation, the passport's issue date and issuer — asked ONCE and fed to every form (the national
visa form, the EX-01, the EX-17, the padrón sheet, the TA.1, the health card). Never asked again:

  · within a file, every form reads the same facts (the case's `facts.applicant`);
  · across files, the person may keep them in their vault (encrypted, deletable any time — the same vault as CampusMe's), and
    a new file opens them only under that person's yes, every use logged (booking_signer.vault.crypto.use).

A fictional (DEMO) applicant is never kept.
"""
from __future__ import annotations

import hashlib
import json
import logging
from typing import Dict, List, Optional

log = logging.getLogger("products.relocation.keep")
LABEL = "RelocateMe details"
PROVIDER = "kanoe.ai"
SOURCE = "your Keep (vault)"
NOT_KEPT = ("school_age_children_in_spain",)          # about this file, not about the person


def keepable(f: dict) -> Dict[str, str]:
    """The person's own facts, as values — only what they gave us themselves (never a fictional one)."""
    from .turn import FICTIONAL
    a = (f or {}).get("applicant") or {}
    return {k: x.get("value", "") for k, x in a.items() if k not in NOT_KEPT and x.get("source") != FICTIONAL}


async def item(account: str) -> Optional[dict]:
    try:
        from booking_signer.vault import crypto as VC
        rows = await VC.STORE.list(account)
    except Exception:
        return None
    return next((r for r in rows if r.get("label") == LABEL and not r.get("deleted_at") and not r.get("revoked_at")), None)


async def save(account: str, f: dict) -> bool:
    """Into the vault, through its own route (the same as CampusMe's keep). True when kept."""
    vals = keepable(f)
    if not vals:
        return False
    try:
        from booking_signer.guest_whatsapp import api
        st, _ = await api(account, "POST", "/api/booking/vault",
                          {"provider": PROVIDER, "label": LABEL, "kind": "identifier", "fields": {"value": json.dumps(vals, sort_keys=True)}})
        return st in (200, 201)
    except Exception as e:
        log.warning("[keep] not kept: %s", type(e).__name__)
        return False


def lines() -> List[str]:
    from booking_signer.vault import crypto as VC
    return [VC.access_line(PROVIDER, LABEL, "identifier"), "It fills your RelocateMe forms; you check each one before signing."]


def approval(now, how: str, said: str) -> dict:
    return {"how": how, "said": said, "at": now.isoformat(), "read_back_sha256": hashlib.sha256("\n".join(lines()).encode()).hexdigest()}


async def open_into(account: str, item_id: str, f: dict, appr: dict, read_on: str) -> int:
    """Under the person's yes: the kept values into this file's facts (never over an answer already given). → how many."""
    from booking_signer.vault import crypto as VC
    from . import facts as F
    async with VC.use(account, item_id, approval=appr, approved_lines=lines(), action_kind="relocateme_fill",
                      action_ref=f"keep-{appr['read_back_sha256'][:12]}") as secret:
        vals = json.loads(secret.get("value") or "{}")
    a = f.setdefault("applicant", {})
    n = 0
    for k, v in vals.items():
        if k not in a and isinstance(v, str):
            a[k] = F.fact(v, SOURCE, read_on)
            n += 1
    return n


def where_from(f: dict) -> str:
    """CR 45 · a card's caption names the TRUE source: "your Keep" only when values came out of the vault — a DEMO (fictional)
    applicant is never kept, and a first file's answers are this file's."""
    a = (f or {}).get("applicant") or {}
    return "your Keep" if any(x.get("source") == SOURCE for x in a.values()) else "this file's answers"

