"""CR 46 · EspañaMe's health card, for the platform's 🇪🇸 tab (like products.relocation.package_status): READ-ONLY — where the
account's case got to, step by step: ID read → 1449F1 filled → centro de salud found → cita. Nothing is written or sent."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional


async def health_status(account: str) -> Optional[dict]:
    """→ {"steps": [{name, state: done|doing|todo|expired, note, pdf}], "next": str, "tab": "Health card", "case_id"} or None
    when the account has no health-card case and none under way. Never raises."""
    from .. import store as ST
    from .tarjeta import web
    try:
        rows = await ST.STORE.of_account(account, "health")
    except Exception:
        return None
    cases = [r for r in rows if (r["state"] or {}).get("kind") == "tarjeta"]
    convo = next((r["state"].get("pending") or {} for r in rows if (r["state"] or {}).get("kind") == "conversation"), {})
    under_way = str(convo.get("step") or "").startswith("ts_")
    if not cases and not under_way:
        return None
    case = max(cases, key=lambda c: str(c.get("created_at") or "")) if cases else None
    st = (case or {}).get("state") or {}
    now = datetime.now(timezone.utc)
    expired = bool(st.get("values_expire_at")) and datetime.fromisoformat(st["values_expire_at"]) < now
    cid = (case or {}).get("id")
    centre, cita = st.get("centre") or {}, st.get("cita") or {}
    steps = [
        {"name": "Your ID read", "state": "done" if case else "doing",
         "note": "your DNI or passport, read once and confirmed by you" if case else "send your DNI or passport photo", "pdf": None},
        {"name": "Health-card form (1449F1) filled", "state": "expired" if expired else "done" if case else "todo",
         "note": ("filled; its details were deleted after 24 hours — say “españa” to fill it again" if expired else
                  f"{len(st.get('rows') or [])} boxes filled; signature, date and §5–§6 are yours" if case else "after your ID"),
         "pdf": f"{web()}/api/products/health/{cid}/1449F1-prepared.pdf" if case and not expired else None},
        {"name": "Your centro de salud", "state": "done" if centre else "todo",
         "note": f"{centre.get('name')}, {centre.get('address', '')}".strip(", ") if centre else "say “find my centre”", "pdf": None},
        {"name": "Your cita", "state": "done" if cita else "todo",
         "note": f"{cita.get('place')}, {cita.get('on')} at {cita.get('at')} — booked by you" if cita else
                 "you book it on SERMAS's page or by phone; tell me the day and time", "pdf": None},
    ]
    nxt = next((s["note"] for s in steps if s["state"] in ("doing", "todo", "expired")), "hand in the form at your cita")
    return {"steps": steps, "next": nxt, "tab": "Health card", "case_id": cid,
            "fictional": bool(st.get("fictional"))}
