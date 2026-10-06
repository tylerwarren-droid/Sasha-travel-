"""CR 45 · CampusMe CONFIRMATIONS: when the family presses Register, the school's OWN confirmation — the page it shows, or the
email it sends (pasted here) — is read and checked against what was prepared: the school, the student, the date, the time,
and its confirmation number. Only a confirmation that matches marks the visit "Registered ✓ — Yale, Mon 16 Nov 9:30,
confirmation #…". No confirmation, or one that doesn't match, is "Registration not confirmed" — never assumed.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Dict, List, Optional

_CONFIRMED = re.compile(r"(?i)\b(thank you for registering|you('| a)re (now )?registered|registration (is )?(complete|confirmed|"
                        r"received)|we look forward to (seeing|welcoming) you|your (visit|registration|event) (is|has been) confirmed|"
                        r"confirmation (number|#|code|id)|see you (on|soon))\b")
_NUMBER = re.compile(r"(?i)\b(?:confirmation|registration|reference|booking)\s*(?:number|no\.?|#|code|id)?\s*[:#]?\s*"
                     r"([A-Z0-9][A-Z0-9-]{3,})\b")
_NOT_A_NUMBER = {"EMAIL", "NUMBER", "CODE", "DETAILS", "PAGE", "FOR", "THE", "YOUR"}


def expect(school: dict, session: dict, student_first: str = "", student_last: str = "") -> dict:
    """What was prepared: the school, the student, the day, the time — what the confirmation must say back."""
    return {"name": school["name"], "aliases": [a.lower() for a in school.get("aliases", [])] + [school.get("full_name", "").lower()],
            "day": session.get("day") or session.get("date"), "start": session.get("start"),
            "first": (student_first or "").strip(), "last": (student_last or "").strip()}


def _says_day(text: str, d: date) -> bool:
    mon, mo3 = d.strftime("%B"), d.strftime("%b")
    pats = [rf"\b({mon}|{mo3})\.?\s+{d.day}\b", rf"\b{d.day}(st|nd|rd|th)?\s+(of\s+)?({mon}|{mo3})\b", re.escape(d.isoformat()),
            rf"\b0?{d.month}/0?{d.day}/(\d{{2}})?{str(d.year)[2:]}\b"]
    return any(re.search(p, text, re.I) for p in pats)


def _times(text: str) -> List[str]:
    """Every clock time the text states, as HH:MM (24h)."""
    out = []
    for m in re.finditer(r"(?i)\b(\d{1,2})(?::(\d{2}))?\s*(a\.?m\.?|p\.?m\.?)\b|\b([01]?\d|2[0-3]):([0-5]\d)\b", text):
        if m.group(1):
            h, mi = int(m.group(1)) % 12 + (12 if m.group(3).lower().startswith("p") else 0), int(m.group(2) or 0)
        else:
            h, mi = int(m.group(4)), int(m.group(5))
        out.append(f"{h:02d}:{mi:02d}")
    return out


def read(text: str, exp: dict, from_page: bool = False) -> dict:
    """→ {confirmed, number, mismatches: [..], missing: [..], quote}. `from_page`: the school's own page after the press (its
    host is the school's, so it need not name itself)."""
    t = " ".join((text or "").split())
    low = t.lower()
    missing, mismatches = [], []
    if not _CONFIRMED.search(t):
        missing.append("the school saying it's registered")
    if not from_page and not any(a and a in low for a in exp["aliases"]):
        missing.append(f"{exp['name']}'s name")
    if exp.get("first") and exp["first"].lower() not in low:
        missing.append("the student's name")
    d = date.fromisoformat(exp["day"]) if exp.get("day") else None
    if d and not _says_day(t, d):
        other = re.search(r"(?i)\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2}\b", t)
        (mismatches if other else missing).append(f"another day ({other.group(0)})" if other else "the day")
    times = _times(t)
    if exp.get("start") and times and exp["start"] not in times:
        mismatches.append(f"another time ({', '.join(sorted(set(times)))})")
    num = next((m.group(1) for m in _NUMBER.finditer(t) if m.group(1).upper() not in _NOT_A_NUMBER and re.search(r"\d", m.group(1))), None)
    m = _CONFIRMED.search(t)
    quote = t[max(0, m.start() - 40):m.start() + 160].strip() if m else t[:200]
    return {"confirmed": not missing and not mismatches, "number": num, "missing": missing, "mismatches": mismatches, "quote": quote}


def _when(exp: dict) -> str:
    d = date.fromisoformat(exp["day"])
    s = exp.get("start") or ""
    if re.fullmatch(r"\d{2}:\d{2}", s):
        h, mi = map(int, s.split(":"))
        s = f" {h % 12 or 12}:{mi:02d}{'am' if h < 12 else 'pm'}" if mi else f" {h % 12 or 12}{'am' if h < 12 else 'pm'}"
    return f"{d.strftime('%a %-d %b')}{s}"


def line(exp: dict, r: Optional[dict]) -> str:
    """The visit's status, in one line."""
    if r and r["confirmed"]:
        return f"Registered ✓ — {exp['name']}, {_when(exp)}" + (f", confirmation #{r['number']}" if r["number"] else
                                                                ", no confirmation number on it")
    if not r:
        return f"Registration not confirmed — no confirmation from {exp['name']} yet"
    if r["mismatches"]:
        return f"Registration not confirmed — {exp['name']}'s reply doesn't match what was prepared ({'; '.join(r['mismatches'])})"
    return (f"Registration not confirmed yet — {exp['name']}'s reply doesn't show {_and(r['missing'])}; its confirmation email "
            "decides (paste it here)")


def _and(xs: List[str]) -> str:
    return xs[0] if len(xs) == 1 else ", ".join(xs[:-1]) + " or " + xs[-1]


def record(r: dict, source: str, at: str) -> Dict[str, object]:
    """What's kept on the visit: the check's result in the school's words — never more than it says."""
    return {"confirmed": r["confirmed"], "number": r["number"], "source": source, "quote": r["quote"][:300],
            "mismatches": r["mismatches"], "missing": r["missing"], "at": at}
