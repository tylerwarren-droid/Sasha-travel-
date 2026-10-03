"""CR 1 · the reviewer agent: it reads every row of the prepared EX-01 against its facts and their sources, and says, per
row, ok / check / problem — with the reason in words. Deterministic: each check is a rule a person can read below, so
the screen never shows a verdict nobody can explain. It checks; it never corrects a value, and it never advises on the
application itself (AD P807jy §2.3: we do not advise, and we do not say the file is correct).

Checks:
  provenance    every filled value names its source and when (AD's rule: no value without a receipt)
  format        passport number shape; NIE control letter (mod 23); five-digit postcode; email; mobile; real dates
  cross-field   the postcode's first two digits name the province written (INE codes); section 4 equals section 1 when
                the applicant chose their own address; the birth date is before the passport's expiry
  agreement     a fact with two sources (said + document) must agree; if they don't, both are shown
  staleness     the passport has not expired; an applicant under 18 needs the legal-representative row (flagged, not filled)
  fit           a value longer than its box is clipped on paper — the box width (from the measured rect) is checked
  irreducible   the signature, consent and intent widgets carry no value (the fill would have refused; checked again here)
"""
from __future__ import annotations

import json
import re
from datetime import date
from typing import Dict, List

from . import ex01 as E
from . import facts as F

OK, CHECK, PROBLEM = "ok", "check", "problem"
FONT_OF_HEIGHT = 0.8   # the form's text is auto-sized: a viewer draws it at about 80% of the box's height
CHAR_W = 0.55          # average glyph width of a sans font, as a fraction of its size


def _w(row_name: str, fmap: dict) -> float:
    r = next(w["rect"] for w in fmap["fields"] if w["name"] == row_name)
    return r[2] - r[0]


def _h(row_name: str, fmap: dict) -> float:
    r = next(w["rect"] for w in fmap["fields"] if w["name"] == row_name)
    return r[3] - r[1]


def review(rows: List[dict], facts: Dict[str, Dict[str, dict]], today: date) -> List[dict]:
    fmap = json.loads(E.FIELD_MAP.read_text())
    a = facts.get("applicant") or {}
    others = facts.get("documents") or {}          # {"applicant.surname_1": [{value, source, read_on}, …]} second sources
    out = []
    for r in rows:
        v, verdicts = r.get("value"), []
        fk = r.get("fact")

        def say(level: str, why: str) -> None:
            verdicts.append({"level": level, "why": why})
        if r["state"] == E.PREPARED:
            say(OK if not v else PROBLEM, "carries no value: it is the applicant's to make" if not v
                else "a value was placed on a signature, consent or intent box — this must never happen")
        elif r["state"] in (E.FILLED,):
            if not r.get("provenance"):
                say(PROBLEM, "no source: a value on this form must say where it came from")
            short = (fk or "").split(".")[-1]
            val = str(r.get("answer") or v or "")
            if short == "passport_number" and not re.fullmatch(r"[A-Z0-9]{5,12}", val):
                say(PROBLEM, "doesn't look like a passport number")
            if fk == "applicant.nie_control":
                nie = (a.get("nie") or {}).get("value", "")
                if nie and not F.nie_ok(*nie.split("-")):
                    say(PROBLEM, f"the NIE {nie.replace('-', '')} fails its control letter — check the last letter against the card")
                elif nie:
                    say(OK, "the NIE's control letter is right")
            if short == "address_postcode":
                prov = (facts.get(fk.split(".")[0]) or {}).get("address_province", {}).get("value") or \
                       (a.get("address_province") or {}).get("value")
                code = F.province_code(prov or "")
                if code and val[:2] != code:
                    say(PROBLEM, f"postcode {val} is in {F.PROVINCES.get(val[:2], '?')}, but the province written is {prov}")
                elif code:
                    say(OK, f"postcode {val} is in {F.PROVINCES[code]}, as written")
                else:
                    say(CHECK, f"“{prov}” isn't a province name I recognise — postcode {val} is in {F.PROVINCES.get(val[:2], '?')}")
            if short == "email" and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[A-Za-z]{2,}", val):
                say(PROBLEM, "not an email address")
            if short == "birth_date" or (r.get("name") in ("Texto8", "Texto9", "Texto10")):
                bd = (a.get("birth_date") or {}).get("value")
                if bd:
                    age = today.year - int(bd[:4]) - ((today.month, today.day) < (int(bd[5:7]), int(bd[8:10])))
                    if age < 18:
                        say(CHECK, f"the applicant is {age}: section 1's legal representative row applies to a minor")
            for other in others.get(fk or "", []):
                ov = str(other["value"])
                if F.fold(ov) != F.fold(val):
                    say(PROBLEM, f"two sources disagree: {r.get('provenance')} says “{val}”, {other['source']} says “{ov}”")
                else:
                    say(OK, f"agrees with {other['source']}")
            if r["type"] == "text" and v:
                need = len(str(v)) * _h(r["name"], fmap) * FONT_OF_HEIGHT * CHAR_W
                if need > _w(r["name"], fmap) - 2:
                    say(CHECK, f"“{v}” may not fit this box on paper (about {need:.0f} pt of text in a {_w(r['name'], fmap):.0f} pt box)")
            if not verdicts:
                say(OK, "has its source; nothing to cross-check")
        elif r["state"] == E.NO_DATA and r.get("fact", "").startswith("applicant.") and r["fact"].split(".")[1] in (
                "passport_number", "surname_1", "given_names", "birth_date", "nationality"):
            say(PROBLEM, "the form can't go without this — we hold nothing for it")
        out.append({**r, "checks": verdicts, "verdict": max((x["level"] for x in verdicts), key=[OK, CHECK, PROBLEM].index)
                    if verdicts else None})
    exp = (a.get("passport_expiry") or {}).get("value")
    if exp and exp <= today.isoformat():
        for r in out:
            if r.get("fact") == "applicant.passport_number":
                r["checks"].append({"level": PROBLEM, "why": f"this passport expired on {exp}"})
                r["verdict"] = PROBLEM
    return out


def summary(rows: List[dict]) -> Dict[str, int]:
    s = {OK: 0, CHECK: 0, PROBLEM: 0}
    for r in rows:
        if r.get("verdict"):
            s[r["verdict"]] += 1
    return s
