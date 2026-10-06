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
MONTHS.update({m: i for i, m in enumerate(["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
                                            "septiembre", "octubre", "noviembre", "diciembre"], 1)})   # CR 40 · Spanish too
MONTHS["setiembre"] = 9
MONTHS.update({m.lower(): i for i, m in enumerate(calendar.month_abbr) if m})
MONTHS.update({"sept": 9})
_MONTH = re.compile(r"\b(" + "|".join(sorted(MONTHS, key=len, reverse=True)) + r")\b(?:\s+(\d{4}))?", re.I)
_DAY = re.compile(r"\b(" + "|".join(sorted(MONTHS, key=len, reverse=True)) + r")\s+(\d{1,2})(?:st|nd|rd|th)?\b", re.I)
_DAY_FIRST = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(?:de\s+|of\s+)?(" + "|".join(sorted(MONTHS, key=len, reverse=True)) + r")\b", re.I)
#: CR 30 · a day of the month on its own ("the 14th", "on the 3rd", "14th") — a day only with a month already given
_DOM = re.compile(r"(?i)^\s*(?:on\s+)?(?:the\s+)?(\d{1,2})(?:st|nd|rd|th)\b|\b(?:on\s+)?the\s+(\d{1,2})(?:st|nd|rd|th)?\b")
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
    dom: Optional[int] = None                     # CR 30 · "the 14th": a day of the month, made a date with the month known

    def missing(self) -> Optional[str]:
        if not self.schools and not self.unreadable:
            return "Which universities? For example: \"Yale and Brown\" (Yale, Brown and Penn are read live)."
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
    df = _DAY_FIRST.search(text) if not d else None          # CR 40 · "el 14 de octubre", "14th of October"
    if d or df:
        mon, dd = (d.group(1), d.group(2)) if d else (df.group(2), df.group(1))
        y, m = _next(MONTHS[mon.lower()], None, today)
        try:
            a.day = date(y, m, int(dd))
            if a.day < today:
                a.day = date(y + 1, m, int(dd))
        except ValueError:
            a.day = None
    if not a.day:
        dm = _DOM.search(text)
        if dm and 1 <= int(dm.group(1) or dm.group(2)) <= 31:
            a.dom = int(dm.group(1) or dm.group(2))
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
    if a.dom and a.month and not a.day:
        try:
            a.day = date(a.month[0], a.month[1], a.dom)
        except ValueError:
            pass
    return a


def merge(a: Ask, b: Ask) -> Ask:
    """A follow-up answers what was missing ("April"); what was already said stays."""
    month = b.month or a.month
    day = b.day
    if not day and b.dom and month:               # "the 14th" after "October": 14 October
        try:
            day = date(month[0], month[1], b.dom)
        except ValueError:
            day = None
    return Ask(schools=b.schools or a.schools, unreadable=b.unreadable or a.unreadable, month=month,
               day=day or (None if b.month and b.month != a.month else a.day), who=b.who or a.who,
               student_name=b.student_name or a.student_name, guests=b.guests if b.guests != 1 else a.guests)


def to_state(a: Ask) -> dict:
    return {"schools": [s["key"] for s in a.schools], "unreadable": a.unreadable,
            "month": list(a.month) if a.month else None, "day": a.day.isoformat() if a.day else None,
            "who": a.who, "student_name": a.student_name, "guests": a.guests}


def from_state(d: dict) -> Ask:
    return Ask(schools=[SC.SCHOOLS[k] for k in d.get("schools") or [] if k in SC.SCHOOLS], unreadable=d.get("unreadable") or [],
               month=tuple(d["month"]) if d.get("month") else None, day=date.fromisoformat(d["day"]) if d.get("day") else None,
               who=d.get("who"), student_name=d.get("student_name"), guests=int(d.get("guests", 1)))
