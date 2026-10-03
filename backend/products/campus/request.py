"""CR 1 · what a family asked for, in words: schools, a month (or a day), who's visiting. No model: a few patterns,
and when one thing is missing CampusMe asks for that one thing (as Sasha's ASK_ONE)."""
from __future__ import annotations

import calendar
import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import List, Optional, Tuple

from . import schools as SC

MONTHS = {m.lower(): i for i, m in enumerate(calendar.month_name) if m}
MONTHS.update({m.lower(): i for i, m in enumerate(calendar.month_abbr) if m})
MONTHS.update({"sept": 9})
_MONTH = re.compile(r"\b(" + "|".join(sorted(MONTHS, key=len, reverse=True)) + r")\b(?:\s+(\d{4}))?", re.I)
_DAY = re.compile(r"\b(" + "|".join(sorted(MONTHS, key=len, reverse=True)) + r")\s+(\d{1,2})(?:st|nd|rd|th)?\b", re.I)
_WHO = re.compile(r"\bfor\s+(?:my\s+)?(son|daughter|child|kid|student|niece|nephew|grandson|granddaughter|myself|me)\b"
                  r"(?:\s*,?\s*([A-Z][a-z]+))?", re.I)
_GUESTS = re.compile(r"\b(?:with|and)\s+(me|us|my\s+(?:wife|husband|partner)|both of us|my\s+(?:wife|husband|partner)\s+and\s+me)\b", re.I)


@dataclass
class Ask:
    schools: List[dict] = field(default_factory=list)
    unreadable: List[str] = field(default_factory=list)
    month: Optional[Tuple[int, int]] = None      # (year, month)
    day: Optional[date] = None
    who: Optional[str] = None                     # "son" / "daughter" / "myself" …
    student_name: Optional[str] = None
    guests: int = 1                               # parents coming along, besides the student

    def missing(self) -> Optional[str]:
        if not self.schools and not self.unreadable:
            return "Which universities? For example: \"Yale and Penn\"."
        if not self.month and not self.day:
            return "Which month would you like to visit?"
        return None

    def span(self, today: date) -> Tuple[date, date]:
        if self.day:
            return self.day, self.day
        y, m = self.month
        return date(y, m, 1), date(y, m, calendar.monthrange(y, m)[1])

    def when_words(self) -> str:
        if self.day:
            return self.day.strftime("%A %-d %B")
        return date(self.month[0], self.month[1], 1).strftime("%B %Y")


def _next(month: int, year: Optional[int], today: date) -> Tuple[int, int]:
    """April said in October means next April; the current month means this one."""
    if year:
        return int(year), month
    return (today.year if month >= today.month else today.year + 1), month


def parse(text: str, today: date) -> Ask:
    a = Ask(schools=SC.find_schools(text), unreadable=SC.unreadable_named(text))
    d = _DAY.search(text)
    if d:
        y, m = _next(MONTHS[d.group(1).lower()], None, today)
        try:
            a.day = date(y, m, int(d.group(2)))
            if a.day < today:
                a.day = date(y + 1, m, int(d.group(2)))
        except ValueError:
            a.day = None
    if not a.day:
        for m in _MONTH.finditer(text):
            # "may" is usually the verb ("may we visit"): a month only after in/during/for or before a year
            if m.group(1).lower() == "may" and not (m.group(2) or re.search(r"\b(in|during|for)\s+$", text[:m.start()], re.I)):
                continue
            a.month = _next(MONTHS[m.group(1).lower()], m.group(2), today)
            break
    w = _WHO.search(text)
    if w:
        a.who = w.group(1).lower()
        if w.group(2):
            a.student_name = w.group(2)
    g = _GUESTS.search(text)
    if g:
        a.guests = 2 if re.search(r"both|and me|wife|husband|partner", g.group(1), re.I) else 1
    if a.who in ("myself", "me"):
        a.guests = 0 if not g else a.guests
    return a


def merge(a: Ask, b: Ask) -> Ask:
    """A follow-up answers what was missing ("April"); what was already said stays."""
    return Ask(schools=b.schools or a.schools, unreadable=b.unreadable or a.unreadable, month=b.month or a.month,
               day=b.day or a.day, who=b.who or a.who, student_name=b.student_name or a.student_name,
               guests=b.guests if b.guests != 1 else a.guests)


def to_state(a: Ask) -> dict:
    return {"schools": [s["key"] for s in a.schools], "unreadable": a.unreadable,
            "month": list(a.month) if a.month else None, "day": a.day.isoformat() if a.day else None,
            "who": a.who, "student_name": a.student_name, "guests": a.guests}


def from_state(d: dict) -> Ask:
    return Ask(schools=[SC.SCHOOLS[k] for k in d.get("schools") or [] if k in SC.SCHOOLS], unreadable=d.get("unreadable") or [],
               month=tuple(d["month"]) if d.get("month") else None, day=date.fromisoformat(d["day"]) if d.get("day") else None,
               who=d.get("who"), student_name=d.get("student_name"), guests=int(d.get("guests", 1)))
