"""S-66 · IS THE VENUE OPEN? — its listed hours, from its OWN SITE first, then its Google listing, each source kept.

Founder's rule (Sasha 53, after Calma rang out at 09:30: its site says 09:00, Google says Monday 10:00):
  · before any call, the venue's LOCAL time (its timezone) is checked against its listed hours;
  · where the sources disagree, the LATER opening is used (and the earlier closing): a call at the earlier time is the
    one that rings out. A day either source lists as closed is closed;
  · out of hours, the call is not placed now: it is scheduled for opening + 10 minutes, covered by the guest's single
    yes (the read-back says so), and — when the email rung is live and the venue has an address — the request is
    emailed now; a reply by email cancels the scheduled call.
Nothing is guessed: with no hours from any source, nothing is checked and the call goes as today — and says so.
"""
from __future__ import annotations

import re
from datetime import datetime, time, timedelta
from typing import Any, Dict, List, Mapping, Optional, Tuple
from zoneinfo import ZoneInfo

AFTER_OPENING = timedelta(minutes=10)
_DAYS = {"mo": 0, "tu": 1, "we": 2, "th": 3, "fr": 4, "sa": 5, "su": 6,
         "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6}

Week = Dict[int, List[Tuple[time, time]]]   # weekday (Monday 0) → open intervals; a day absent = closed


def _hm(s: str) -> Optional[time]:
    m = re.fullmatch(r"\s*(\d{1,2}):(\d{2})(?::\d{2})?\s*", str(s or ""))
    if not m or int(m[1]) > 24:
        return None
    return time(23, 59) if int(m[1]) == 24 else time(int(m[1]), int(m[2]))


def _day(tok: str) -> Optional[int]:
    t = str(tok).strip().lower().rsplit("/", 1)[-1]   # "https://schema.org/Monday" → "monday"
    return _DAYS.get(t) if t in _DAYS else _DAYS.get(t[:2])


def from_jsonld(data: Any) -> Week:
    """schema.org openingHours ("Mo-Fr 09:00-20:00") and openingHoursSpecification ({dayOfWeek, opens, closes})."""
    week: Week = {}

    def walk(node):
        if isinstance(node, list):
            for x in node:
                walk(x)
            return
        if not isinstance(node, dict):
            return
        oh = node.get("openingHours")
        for spec in ([oh] if isinstance(oh, str) else oh if isinstance(oh, list) else []):
            m = re.fullmatch(r"\s*([A-Za-z,\- ]+)\s+(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})\s*", str(spec))
            if not m:
                continue
            days: List[int] = []
            for part in m[1].replace(" ", "").split(","):
                if "-" in part:
                    a, b = (_day(x) for x in part.split("-", 1))
                    if a is not None and b is not None:
                        days += list(range(a, b + 1)) if a <= b else list(range(a, 7)) + list(range(0, b + 1))
                elif _day(part) is not None:
                    days.append(_day(part))
            o, c = _hm(m[2]), _hm(m[3])
            if o and c:
                for d in days:
                    week.setdefault(d, []).append((o, c))
        for s in (node.get("openingHoursSpecification") or []) if isinstance(node.get("openingHoursSpecification"), list) else \
                ([node["openingHoursSpecification"]] if isinstance(node.get("openingHoursSpecification"), dict) else []):
            dows = s.get("dayOfWeek")
            o, c = _hm(s.get("opens")), _hm(s.get("closes"))
            if not (o and c):
                continue
            for d in ([dows] if isinstance(dows, str) else dows or []):
                if _day(d) is not None:
                    week.setdefault(_day(d), []).append((o, c))
        for v in node.values():
            if isinstance(v, (dict, list)):
                walk(v)

    walk(data)
    return {d: sorted(set(iv)) for d, iv in week.items()}


def from_places_periods(periods: Any) -> Week:
    """Google's regularOpeningHours.periods: day 0 is SUNDAY there; Monday 0 here."""
    week: Week = {}
    for p in periods or []:
        o, c = (p or {}).get("open") or {}, (p or {}).get("close") or {}
        if "day" not in o:
            continue
        d = (int(o["day"]) + 6) % 7
        ot = time(int(o.get("hour", 0)), int(o.get("minute", 0)))
        if not c and len(periods) == 1 and ot == time(0, 0):   # Google's "open 24 hours": one period, no close
            return {x: [(time(0, 0), time(23, 59))] for x in range(7)}
        if c and "day" in c and c.get("day") != o.get("day"):
            # S-68 · past midnight (a bar, 20:00–02:00): the evening on its day, the small hours on the next
            week.setdefault(d, []).append((ot, time(23, 59)))
            ct = time(int(c.get("hour", 0)), int(c.get("minute", 0)))
            if ct > time(0, 0):
                week.setdefault((int(c["day"]) + 6) % 7, []).append((time(0, 0), ct))
            continue
        ct = time(int(c.get("hour", 23)), int(c.get("minute", 59))) if c else time(23, 59)
        week.setdefault(d, []).append((ot, ct))
    return {d: sorted(iv) for d, iv in week.items()}


def sources(read: Mapping[str, Any]) -> List[dict]:
    """Every hours source the read holds — the venue's own site first, then Google — with where it came from."""
    out = []
    for kind in ("site", "places"):
        for f in read.get("facts") or []:
            if f.get("kind") != "hours" or f.get("source_kind") != kind:
                continue
            ev = f.get("evidence") or f.get("detail") or {}
            week = {int(k): [(_hm(a), _hm(b)) for a, b in v] for k, v in (ev.get("week") or {}).items()} if ev.get("week") \
                else from_places_periods(ev.get("periods"))
            if week:
                out.append({"kind": kind, "label": f.get("source_label"), "week": week})
    return out


def _intersect(a: List[Tuple[time, time]], b: List[Tuple[time, time]]) -> List[Tuple[time, time]]:
    out = []
    for x0, x1 in a:
        for y0, y1 in b:
            lo, hi = max(x0, y0), min(x1, y1)
            if lo < hi:
                out.append((lo, hi))
    return sorted(out)


def merge(srcs: List[dict]) -> Tuple[Week, List[str]]:
    """One week from all sources: a time is OPEN only when EVERY source lists it open — so a split day stays split
    (Calma's 10:00–14:00 and 16:00–20:00: never "open" at 15:00), the later opening and the earlier closing win, and a
    day any source lists as closed is closed. Returns the week and the disagreements, in plain words."""
    if not srcs:
        return {}, []
    week: Week = {}
    notes: List[str] = []
    names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    fmt = lambda iv: ", ".join(f"{a:%H:%M}–{b:%H:%M}" for a, b in iv)
    for d in range(7):
        lists = [s["week"].get(d) for s in srcs]
        if not any(lists):
            continue
        if not all(lists):
            notes.append(f"{names[d]}: one source lists it closed — treated as closed")
            continue
        iv = lists[0]
        for other in lists[1:]:
            iv = _intersect(iv, other)
        if len({tuple(x) for x in lists}) > 1:
            notes.append(f"{names[d]}: sources disagree ({' / '.join(fmt(x) for x in lists)}) — using {fmt(iv) or 'closed'}")
        if iv:
            week[d] = iv
    return week, notes


def status(read: Mapping[str, Any], now: datetime, timezone: str) -> dict:
    """{known, open_now, local_now, opens_at (local, ISO), call_at (UTC, opening + 10 min), basis, notes}."""
    srcs = sources(read)
    week, notes = merge(srcs)
    local = now.astimezone(ZoneInfo(timezone))
    out = {"known": bool(srcs), "local_now": local.strftime("%Y-%m-%d %H:%M"), "notes": notes,
           "basis": [s["label"] for s in srcs], "open_now": None, "opens_at": None, "call_at": None}
    if not srcs:
        return out
    t = local.time()
    out["open_now"] = any(a <= t < b for a, b in week.get(local.weekday(), []))
    # the NEXT opening after now — when a closed venue is called (and what the read-back promises)
    for i in range(0, 8):
        day = (local + timedelta(days=i)).date()
        for a, _b in week.get(day.weekday(), []):
            start = datetime.combine(day, a, tzinfo=local.tzinfo)
            if start > local:
                out["opens_at"] = start.strftime("%Y-%m-%d %H:%M")
                out["call_at"] = (start + AFTER_OPENING).astimezone(now.tzinfo).isoformat()
                return out
    return out


def read_back_line(st: Mapping[str, Any], email_now: bool) -> Optional[str]:
    """The line the guest's yes also covers. None when no hours are known (then nothing is promised)."""
    if not st.get("known") or not st.get("opens_at"):
        return None
    opens = st["opens_at"]
    call = (datetime.fromisoformat(opens) + AFTER_OPENING).strftime("%H:%M")
    return (f"If they're closed when you say yes, I'll {'email them now and ' if email_now else ''}call when they open — "
            f"they open at {opens[11:]} on {opens[:10]}, so I'd call at {call}. Your yes covers that call.")


# ── S-68 step 4 · OPEN AT the time the guest asked for — a listing's hours, before anything is picked ─────────────

_DAY3 = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def open_at(week: Week, when: datetime) -> dict:
    """Is a venue open at `when` (its LOCAL time, naive) by these hours? Split days stay split: a time in the gap is
    closed. {known, open, words}: "Open Tue 17:00" · "Closed Tue 15:00 (opens 17:00)" · "Closed all day Tue" ·
    "Closed Tue 22:00 (no later opening that day)" · "hours not listed". ⚠ Open is not available: the card says so."""
    if not week:
        return {"known": False, "open": None, "words": "hours not listed"}
    d, t, day = when.weekday(), when.time(), _DAY3[when.weekday()]
    at = f"{day} {t:%H:%M}"
    intervals = week.get(d) or []
    if not intervals:
        return {"known": True, "open": False, "words": f"Closed all day {day}"}
    if any(a <= t < b for a, b in intervals):
        return {"known": True, "open": True, "words": f"Open {at}"}
    later = [a for a, _b in intervals if a > t]
    if later:
        return {"known": True, "open": False, "words": f"Closed {at} (opens {min(later):%H:%M})"}
    return {"known": True, "open": False, "words": f"Closed {at} (no later opening that day)"}
