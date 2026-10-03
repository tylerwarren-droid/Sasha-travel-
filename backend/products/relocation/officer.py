"""CR 8 · the CASE OFFICER's view of the relocation reviewer — what an administration, an NGO or a law firm would see:
a queue of FIVE FICTIONAL EX-01 applications, each run through the SAME code a real file is (ex01.rows + checker.review +
after.checklist), sorted by what needs attention, each with a one-click "return to applicant with this list".

No new checks and no new claims: every line an application shows is the existing checker's own sentence, or an item of
the London consulate's own checklist (after.CHECKLIST) the file doesn't include. The score is a COUNT of open items —
never a percentage (P807lu §2.5). "Return" RECORDS the message in the demo's case; nothing is sent to anyone.
CLICK-THROUGH: the people are invented; the form, the checks and the checklist are the real ones.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Dict, List, Optional

from . import after as AF
from . import checker as CK
from . import ex01 as E
from . import facts as F
from .turn import DEMO, applies

FICTIONAL = "fictional applicant (not a real person)"
DOC_KEYS = [k for k, _ in AF.CHECKLIST if k not in ("ex01", "visa_fee")]   # documents the applicant brings
_DOC = dict(AF.CHECKLIST)

# Five invented people. Each differs from the clean DEMO applicant only where a real file could go wrong.
APPLICATIONS = [
    {"id": "A-1042", "base": {"given_names": "Bruno", "surname_1": "Muestra", "surname_2": "", "sex": "H",
                              "nationality": "argentina", "birth_country": "Argentina", "birth_place": "Rosario",
                              "address_postcode": "08010", "address_province": "Madrid"},
     "missing": ["medical", "criminal_record"], "received": "2026-09-28"},
    {"id": "A-1043", "base": {"given_names": "Chen", "surname_1": "Prueba", "surname_2": "", "sex": "M",
                              "nationality": "china", "birth_country": "China", "birth_place": "Chengdu",
                              "nie": "X-0000000-A", "address_floor": "3º B izquierda interior"},
     "missing": [], "received": "2026-09-29"},
    {"id": "A-1044", "base": {"given_names": "Dana", "surname_1": "Ficticia", "surname_2": "", "sex": "M",
                              "nationality": "estadounidense", "birth_country": "Estados Unidos", "birth_place": "Austin",
                              "passport_expiry": "2027-01-15"},
     "missing": ["insurance"], "received": "2026-09-30"},
    {"id": "A-1045", "base": {"given_names": "Emil", "surname_1": "Ensayo", "surname_2": "", "sex": "H",
                              "nationality": "noruega", "birth_country": "Noruega", "birth_place": "Bergen"},
     "missing": ["photo", "means", "fee_790", "uk_permit"], "received": "2026-10-01"},
    {"id": "A-1046", "base": {}, "missing": [], "received": "2026-10-02"},          # Ana Ejemplo Prueba: complete
]


def _facts(base: dict, on: str) -> dict:
    v = {**DEMO, "address_floor": "2º", **base}      # a floor that fits its box, unless the application says otherwise
    return {"applicant": {k: F.fact(x, FICTIONAL, on) for k, x in v.items()},
            "choices": {k: F.fact(x, FICTIONAL, on) for k, x in
                        (("route", "initial"), ("resources", "self"), ("presenter", "self"), ("notices_to_own_address", "yes"))}}


def assess(app: dict, today: date) -> dict:
    """One application through the real code: its EX-01 rows, the checker's verdicts, the consulate checklist."""
    on = "received " + app["received"]
    f = _facts(app["base"], on)
    rows = CK.review(E.rows(f, applies(f)), f, today)
    items: List[dict] = []
    for r in rows:
        for c in r.get("checks") or []:
            if c["level"] in (CK.PROBLEM, CK.CHECK) and r["state"] != E.PREPARED:
                sec = (r.get("section") or "").split(")")[0]
                items.append({"level": c["level"], "field": f"{r['label']} (section {sec})" if sec.isdigit() else r["label"],
                              "why": c["why"], "from": "the form's checks"})
    seen = set()
    items = [i for i in items if not ((i["field"], i["why"]) in seen or seen.add((i["field"], i["why"])))]
    checklist = {i["key"]: i for i in AF.checklist(f, today, "united kingdom")}
    if checklist.get("passport", {}).get("status") == "problem":
        items.append({"level": CK.PROBLEM, "field": "Passport", "why": checklist["passport"]["why"], "from": "the consulate's checklist"})
    for k in app["missing"]:
        items.append({"level": "missing", "field": "Missing document", "why": _DOC[k], "from": "the consulate's checklist"})
    applicant = [r for r in rows if r["state"] == E.PREPARED]
    n = {"problem": sum(i["level"] == CK.PROBLEM for i in items), "missing": sum(i["level"] == "missing" for i in items),
         "check": sum(i["level"] == CK.CHECK for i in items)}
    status = ("return" if n["problem"] or n["missing"] else "check" if n["check"] else "complete")
    a = f["applicant"]
    return {"id": app["id"], "name": f"{a['given_names']['value']} {a['surname_1']['value']}".strip(),
            "nationality": a["nationality"]["value"], "received": app["received"], "status": status, "counts": n,
            "open_items": n["problem"] + n["missing"] + n["check"], "items": items,
            "left_for_applicant": len(applicant), "filled": E.counts(rows)["filled"], "fictional": True}


def queue(today: Optional[date] = None) -> List[dict]:
    """Most attention first: problems, then missing documents, then things to check; ties by date received."""
    today = today or datetime.now(timezone.utc).date()
    apps = [assess(a, today) for a in APPLICATIONS]
    return sorted(apps, key=lambda x: (-x["counts"]["problem"], -x["counts"]["missing"], -x["counts"]["check"], x["received"]))


def return_message(app: dict) -> str:
    """The message a case officer would send back — the open items, word for word from the checks. Nothing more."""
    lines = [f"Dear {app['name']},", "",
             f"Your EX-01 application ({app['id']}, received {app['received']}) is being returned to you before it is "
             "assessed, so that it arrives complete. Please correct or add the following and send it again:", ""]
    for k, i in enumerate((x for x in app["items"] if x["level"] in (CK.PROBLEM, "missing", CK.CHECK)), 1):
        lines.append(f"{k}. {i['field']}: {i['why']}")
    lines += ["", "Section 5, the Dehú consent and the signature remain yours to complete.", "",
              "This list was produced by the form's automatic checks and the consulate's own checklist."]
    return "\n".join(lines)
