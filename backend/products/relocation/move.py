"""CR 35 · RELOCATEME ON THE BRIDGE: the move as ONE trip on the account — "Move to Madrid" — saved through Sasha's
plan_store (Sasha 165: never written here), so the bookings Sasha makes (Duffel TEST flights, the first nights' hotel) land
on its days by date, and "show me my itinerary" (WhatsApp, voice, the laptop's Trip panel) shows the whole move.

Its days are DATED (sparse — Sasha 167's plan days carry their own date): only the days that hold something, each from the
sheet or page it cites (after.reminders' sources: the consulate's own sheet, the cita previa page):
  · the certificates — no older than 3 months when you apply (≈ entry − 150 days: get them from about then);
  · the application window — from 90 days before entry (the London sheet);
  · the move — the flight to the new town on the entry date, then the first nights near the new address;
  · the TIE — book its cita about three weeks after entry; the sheet's deadline is one month from entry.
A US consulate: only what its own page states (the TIE months), as after.reminders does. Days already past are left out.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional

from . import after as AF

log = logging.getLogger("products.relocation.move")
TITLE = "Move to Madrid"


def _fact(f: dict, k: str) -> str:
    return ((f.get("applicant") or {}).get(k) or {}).get("value", "") or ""


def days(case: dict, origin: str, nights: int, today: date) -> List[dict]:
    """The move's dated days, oldest first: [{"date", "city", "title", "activities": [{"time", "name", "blurb"}]}]."""
    st = case["state"]
    f, after = st.get("facts") or {}, st.get("after") or {}
    entry = date.fromisoformat(after["entry_date"])
    town = _fact(f, "address_town") or "Madrid"
    street = " ".join(x for x in (_fact(f, "address_street"), _fact(f, "address_number")) if x)
    cons = after.get("consulate") or {}
    office = cons.get("office") or AF.CONSULATES["united kingdom"]["office"]
    out: Dict[date, dict] = {}

    def add(d: date, city: str, title: str, time: str, name: str, blurb: str) -> None:
        if d < today:
            return
        day = out.setdefault(d, {"date": d.isoformat(), "city": city, "title": title, "activities": []})
        day["activities"].append({"time": time, "name": name, "blurb": blurb})

    us = bool(cons.get("id"))                         # a US consulate: only what its own page says
    if not us:
        add(entry - timedelta(days=150), origin, "Paperwork", "Morning", "Get your certificates",
            "Criminal record and medical certificates — no older than 3 months when you apply (the consulate's sheet).")
        add(entry - timedelta(days=90), origin, "Paperwork", "Morning", "Your visa window opens",
            f"Apply from today — up to 90 days before entry. Book your appointment at the {office} (its own instructions). "
            "Bring your pack: the national visa form, the EX-01, the 790-052 — each signed by you.")   # CR 44
    add(entry, town, "The move", "Morning", f"Fly {origin} → {town}", "Your entry date.")
    add(entry, town, "The move", "Evening", "Check in — your first nights",
        f"A hotel near your new address{' (' + street + ')' if street else ''} for {nights} nights.")
    for i in range(1, nights):
        add(entry + timedelta(days=i), town, "First nights", "Afternoon", "Settle in", f"Near {street or town}.")
    # CR 44 · after arrival, in process order: padrón first (the fingerprint appointment often asks for it), then the TIE
    # (EX-17 + the 790-012 fee), then Social Security (TA.1), then the health card. Suggested days; the deadlines are the sheets'.
    from . import arrival as AR
    add(entry + timedelta(days=2), town, "Paperwork", "Morning", "Padrón: book your cita",
        f"In person, signed by hand there. Book at {AR.PADRON_CITA} or call 010. Say “after arrival” to me for your details "
        "ready to copy.")
    tie = [r for r in AF.reminders(after["entry_date"], today, cons) if "TIE" in r["text"]]
    if tie:
        add(date.fromisoformat(tie[0]["on"]), town, "Paperwork", "Morning", "Book your TIE appointment",
            f"Cita previa: {AF.CITA_EXTRANJERIA['url']} — bring the EX-17 (signed there) and the 790-012 fee "
            f"({AR.P790_012_FEE}, paid), your passport and a photo.")
    if not us:
        add(entry + timedelta(days=30), town, "Paperwork", "Morning", "TIE deadline",
            "One month from entry to request your TIE (the consulate's sheet).")
    add(entry + timedelta(days=35), town, "Paperwork", "Morning", "Social Security number: the TA.1",
        "Your TA.1, filled — in person at the TGSS. Say “after arrival” to me for the PDF.")
    add(entry + timedelta(days=40), town, "Paperwork", "Morning", "Health card (tarjeta sanitaria)",
        "Say “españa” to me: the 1449F1 is filled, and your centro de salud found.")
    return [out[d] for d in sorted(out)]


def plan(case: dict, origin: str, nights: int, today: date) -> dict:
    ds = days(case, origin, nights, today)
    for i, d in enumerate(ds, 1):
        d["day"] = i
    return {"title": TITLE, "days": ds, "kanoe": "relocation/1"}


async def save(account: str, case: dict, origin: str, nights: int, now: datetime) -> Optional[str]:
    """The plan through Sasha's plan_store → the trip's id (None: no store, or nothing dated ahead). Never raises."""
    from booking_signer import plan_store as PS
    p = plan(case, origin, nights, now.date())
    if not p["days"]:
        return None
    first = date.fromisoformat(p["days"][0]["date"])
    try:
        return await PS.save(account, p, f"from {first.day} {first.strftime('%b')} {first.year}", now)
    except Exception as e:                            # the trip is a convenience; the bookings never wait on it
        log.warning("[move] not saved: %s: %s", type(e).__name__, e)
        return None
