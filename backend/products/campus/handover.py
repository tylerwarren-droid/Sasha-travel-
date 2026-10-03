"""CR 1 · the hand-over: the school's own registration form, question by question, with what CampusMe would enter and
where each answer came from. Nothing here submits — the parent opens the school's page and presses Register.

Mapping is by Slate's standard export keys (sys:first, sys:email, sys:birthdate, sys:field:term …), the same on every
Slate school (read 3 Oct 2026 on Yale's and Penn's forms). A question we can't place is shown as theirs to answer; a
statement the registrant makes ("By submitting this form, you understand…", an SMS opt-in) is ALWAYS theirs to tick —
CampusMe never makes a declaration or a consent for anyone (the 8-irreducible rule, AD visa-form.ts).
"""
from __future__ import annotations

import re
from datetime import date
from typing import Dict, List, Optional

from .slate import Question, Session

# row actions — the hand-over page draws each differently
FILL, YOU, CHOOSE, SKIP, NOT_YOU = "fill", "you", "choose", "skip", "not_you"

PROFILE_KEYS = ("first", "last", "email", "birthdate", "high_school", "grad_year", "mobile", "ceeb")
_STATEMENT = re.compile(r"\b(understand|agree|consent|acknowledge|certify|opt[- ]?in|text message|sms|terms|privacy)\b", re.I)


def _opt(q: Question, *want: str) -> Optional[str]:
    for w in want:
        for o in q.options:
            if o.strip().lower() == w.lower():
                return o
    for w in want:
        for o in q.options:
            if w.lower() in o.lower():
                return o
    return None


def birth_words(iso: str) -> str:
    d = date.fromisoformat(iso)
    return d.strftime("%-d %B %Y")


def plan(questions: List[Question], profile: Dict[str, str], session: Session, attendees: int, src: str) -> List[dict]:
    """One row per question, in the form's order: {label, required, action, answer, source, note}."""
    guests = max(0, attendees - 1)
    rows = []
    for q in questions:
        e = (q.export or "").lower()
        lab = q.label or "(no label)"
        row = {"label": lab, "required": q.required, "action": SKIP, "answer": None, "source": None, "note": None, "type": q.type}

        def fill(v: Optional[str], source: str = src) -> None:
            if v:
                row.update(action=FILL, answer=v, source=source)
            else:
                row.update(action=YOU if q.required else SKIP, note="we hold nothing for this" if q.required else "optional")

        if e.startswith("contact_") or e in ("counselorschoolorg", "org_address", "persontype", "otherdetail") or "educator" in lab.lower():
            row.update(action=NOT_YOU, note="for educators and counsellors only — leave it")
        elif q.type in ("checkbox", "radio", "select") and _STATEMENT.search(lab + " " + e):
            row.update(action=YOU, note="a statement or a consent: read it and tick it yourself — CampusMe never ticks one for you")
        elif e == "sys:first":
            fill(profile.get("first"))
        elif e == "sys:last":
            fill(profile.get("last"))
        elif e in ("sys:email", "sys:email2"):
            fill(profile.get("email"))
        elif e == "sys:birthdate":
            fill(birth_words(profile["birthdate"]) if profile.get("birthdate") else None)
        elif e == "sys:mobile":
            fill(profile.get("mobile"))
        elif e in ("sys:school:name", "schoolname"):
            fill(profile.get("high_school"))
        elif e == "sys:school:key":
            fill(profile.get("ceeb"))
        elif e == "sys:field:term":
            fill(_opt(q, f"Fall {profile.get('grad_year')}") if profile.get("grad_year") else None,
                 f"{src} (graduating {profile.get('grad_year')})")
        elif e in ("sys:field:type", "sys:field:prospect_type"):
            fill(_opt(q, "First-Year", "First-year"), "a high-school student applies as a first-year")
        elif e == "registranttype" or "i am a visiting" in lab.lower():
            fill(_opt(q, "Prospective Student/Parent", "Prospective Student"), "you're registering a prospective student")
        elif e == "sys:attendees":
            fill(_opt(q, str(attendees)), f"the student and {guests} guest{'s' if guests != 1 else ''}")
        elif e == "sys:guests":
            fill(_opt(q, str(guests)), f"{guests} guest{'s' if guests != 1 else ''} besides the student")
        elif e in ("preferred_opt_in",):
            fill(_opt(q, "No"), "no different preferred name given")
        elif q.type == "plugin:event":
            kind = session.title.split(" · ", 1)[-1].lower() if " · " in session.title else ""
            stem = "science and engineering" in session.title.lower()
            if (kind and lab.lower().startswith(kind.split(" (")[0])) or \
               (not kind and "tour" in lab.lower() and (("stem" in lab.lower()) == stem)):
                h, mi = map(int, session.start.split(":"))
                row.update(action=CHOOSE, answer=f"{session.title.split(' · ')[0]} — {(h % 12) or 12}:{mi:02d} {'AM' if h < 12 else 'PM'}",
                           source="the session you picked")
            else:
                row.update(action=SKIP, note="optional — another session type")
        elif q.required:
            row.update(action=YOU, note="CampusMe can't place this one: answer it yourself")
        else:
            row.update(action=SKIP, note="optional")
        rows.append(row)
    return rows


def counts(rows: List[dict]) -> Dict[str, int]:
    c: Dict[str, int] = {}
    for r in rows:
        c[r["action"]] = c.get(r["action"], 0) + 1
    return c
