"""CR 44 · for Sasha 178 (3), "what's missing in my relocation package?": READ-ONLY — the account's latest RelocateMe file,
form by form (filled · signed · missing · waiting), its next dated step on the "Move to Madrid" trip, and that tab's title.
Nothing is written, sent or asked here."""
from __future__ import annotations

from datetime import date
from typing import Optional


# CR 45 · where each form goes next, and its PDF one tap away (None: there is no PDF — prepared values, or not here yet)
NEXT = {"National visa application": "signed, to your consulate appointment with the pack",
        "EX-01": "signed, to your consulate appointment",
        "Modelo 790-052": "two signed copies, paid at the consulate",
        "EX-17 (TIE)": "to your fingerprint appointment (Policía), signed there",
        "Modelo 790-012 (TIE fee)": "paid at a bank or online, then to your fingerprint appointment",
        "Padrón": "your Línea Madrid office, in person, with a cita",
        "TA.1 (Social Security number)": "a TGSS office, in person",
        "Health card (1449F1)": "your centro de salud, in person"}
PDF = {"National visa application": "visa-form.pdf", "EX-01": "EX-01-prepared.pdf", "Modelo 790-052": "790-052.pdf",
       "EX-17 (TIE)": "EX-17.pdf", "TA.1 (Social Security number)": "TA-1.pdf"}


def _with_links(forms: list, cid: Optional[str]) -> list:
    from .turn import web
    for f in forms:
        name = PDF.get(f["name"])
        f["pdf"] = f"{web()}/api/products/relocation/{cid}/{name}" if cid and name and f["state"] in ("filled", "signed") else None
        f["next"] = NEXT.get(f["name"])
    return forms


def _forms(st: dict) -> list:
    from . import arrival as AR
    after = st.get("after") or {}
    con = (after.get("consulate") or {}).get("three")
    signed = st.get("status") == "signed_on_your_word"
    pick = "choose your consulate first (tell me where you live)"
    return [
        {"name": "National visa application", "state": "filled" if con else "missing",
         "note": "place, date, signature and photo are yours" if con else pick},
        {"name": "EX-01", "state": "signed" if signed else "filled",
         "note": "signed, on your word" if signed else "section 5, the Dehú consent, place, date and signature are yours"},
        {"name": "Modelo 790-052", "state": "filled" if con else "missing",
         "note": "sign both copies; payment at the consulate" if con else pick},
        {"name": "EX-17 (TIE)", "state": "filled" if AR.ex17_ready() else "waiting",
         "note": "you sign it at your fingerprint appointment" if AR.ex17_ready() else "waiting for the official PDF"},
        {"name": "Modelo 790-012 (TIE fee)", "state": "missing",
         "note": f"{AR.P790_012_FEE}; every value ready to copy — the police's form has a CAPTCHA, so you fill it"},
        {"name": "Padrón", "state": "missing", "note": "in person with a cita (servpub PAD or 010); every value ready to copy"},
        {"name": "TA.1 (Social Security number)", "state": "filled", "note": "in person at the TGSS; signature yours"},
        {"name": "Health card (1449F1)", "state": "missing", "note": "say “españa” — it fills from this file"},
    ]


async def package_status(account: str, today: Optional[date] = None) -> Optional[dict]:
    """→ {"forms": [{name, state, note, pdf, next}], "next_deadline": {on, text} | None, "tab": "Move to Madrid", "case_id"},
    or None (no file). `pdf` is one tap to the filled form (None when there is none to open); `next` is where it goes."""
    from .. import store as ST
    from . import move as MV
    from .three import CONSULATES
    try:
        cases = [c for c in await ST.STORE.of_account(account, "relocation") if (c["state"] or {}).get("rows")]
    except Exception:
        return None
    if not cases:
        return None
    case = max(cases, key=lambda c: str(c.get("created_at") or ""))
    st = case["state"]
    after = st.get("after") or {}
    nxt = None
    if after.get("entry_date"):
        con = CONSULATES.get((after.get("consulate") or {}).get("three") or "", {})
        try:
            days = MV.days(case, con.get("city", "home"), 3, today or date.today())
            if days and days[0]["activities"]:
                nxt = {"on": days[0]["date"], "text": days[0]["activities"][0]["name"]}
        except Exception:
            nxt = None
    a = (st.get("facts") or {}).get("applicant") or {}
    town = (a.get("address_town") or {}).get("value") or "Madrid"
    street = " ".join(x for x in ((a.get("address_street") or {}).get("value"), (a.get("address_number") or {}).get("value")) if x)
    getting = {"title": "Getting there", "say": "book my flights",                       # CR 50 · Sasha books it, here
               "text": f"Flights to {town}" + (f" for {after['entry_date']}" if after.get("entry_date") else "") +
                       f" and your first nights{' near ' + street if street else ''} — Sasha books them right here; each lands "
                       f"on this trip with the visa deadlines.",
               "entry_date": after.get("entry_date"), "to": town}
    return {"forms": _with_links(_forms(st), case.get("id")), "next_deadline": nxt, "tab": MV.TITLE, "case_id": case.get("id"),
            "getting_there": getting}
