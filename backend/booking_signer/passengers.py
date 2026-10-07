"""Sasha 198 · R7 · THE PASSENGERS — asked once, saved, reused (public.saved_passengers, 033_trip_basket.sql).

The airline needs each traveller's full name, title, gender and date of birth. Sasha asks ONCE, at the first "book it" with
a flight in the basket, in one line; the answer is read here (no model), saved on the account, and every later booking reuses
it — never asked again. Duffel's TEST placeholders (travel.PLACEHOLDERS) are used only when nothing is saved, and only in
TEST mode (travel.token() accepts a duffel_test_ token alone).

    "Alex Smith, Mr, 12 March 1985; Sam Smith, Ms, 02/05/1987"  →  two passengers
"""
from __future__ import annotations

import logging
import re
import uuid
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

ASK = "Before I book: each traveller's full name, title and date of birth?"   # Sasha 199 · ≤ 15 words, asked once
MARK = "each traveller's full name, title and date of birth"
_TITLE = {"mr": ("mr", "m"), "mister": ("mr", "m"), "ms": ("ms", "f"), "mrs": ("mrs", "f"), "miss": ("miss", "f"),
          "dr": ("dr", None)}
_MON = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


def _date(t: str) -> Tuple[Optional[date], str]:
    """(the date of birth in it, the text without it)."""
    pats = [(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", lambda m: date(int(m[1]), int(m[2]), int(m[3]))),
            (r"\b(\d{1,2})[/.](\d{1,2})[/.](\d{4})\b", lambda m: date(int(m[3]), int(m[2]), int(m[1]))),   # day first (Spain, UK)
            (r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?([A-Za-z]{3,9})\.?,?\s+(\d{4})\b",
             lambda m: date(int(m[3]), _MON[m[2][:3].lower()], int(m[1]))),
            (r"\b([A-Za-z]{3,9})\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})\b",
             lambda m: date(int(m[3]), _MON[m[1][:3].lower()], int(m[2])))]
    for p, f in pats:
        m = re.search(p, t)
        if m:
            try:
                d = f(m)
            except (KeyError, ValueError):
                continue
            if date(1900, 1, 1) <= d <= date.today():
                return d, (t[:m.start()] + " " + t[m.end():])
    return None, t


def parse(text: str) -> Dict[str, Any]:
    """{passengers: [...complete...], missing: ["Sam Smith: date of birth", ...]}."""
    out, missing = [], []
    for chunk in [c for c in re.split(r"[;\n]+|\s+and\s+(?=(?:mr|ms|mrs|miss|dr)\b|[A-Z])", text or "") if c.strip()]:
        born, rest = _date(chunk)
        tm = re.search(r"\b(mr|mister|ms|mrs|miss|dr)\b\.?", rest, re.I)
        title, gender = _TITLE[tm[1].lower()] if tm else (None, None)
        if tm:
            rest = rest[:tm.start()] + " " + rest[tm.end():]
        g = re.search(r"\b(male|female|man|woman)\b", rest, re.I)
        if g:
            gender = "m" if g[1].lower() in ("male", "man") else "f"
            rest = rest[:g.start()] + " " + rest[g.end():]
        words = [w for w in re.split(r"[\s,]+", rest) if re.fullmatch(r"[A-Za-zÀ-ÿ'’-]{1,40}", w)
                 and w.lower() not in ("born", "dob", "on", "the", "is", "and", "me", "my", "wife", "husband", "partner", "i'm", "im", "uh",
                                       "um", "er", "okay", "ok", "so", "well", "yes", "sure", "sasha", "please", "it's", "its", "of")]
        if len(words) < 2:
            if born or title:
                missing.append(f"{' '.join(words) or 'one traveller'}: full name (first and last)")
            continue
        p = {"given_name": " ".join(words[:-1]).title(), "family_name": words[-1].title(), "born_on": born, "title": title, "gender": gender}
        lack = [k for k, v in (("date of birth", born), ("title (Mr/Ms)", title), ("gender", gender)) if not v]
        if lack:
            missing.append(f"{p['given_name']} {p['family_name']}: " + ", ".join(lack))
            continue
        out.append(p)
    return {"passengers": out, "missing": missing}


def _run():
    from . import plan_store as PS
    return PS._run()


async def saved(account: str) -> List[Dict[str, Any]]:
    run = _run()
    if run is None or not account:
        return []

    async def fn(conn):
        return await conn.fetch("select given_name, family_name, born_on, title, gender, email, phone_e164 from saved_passengers "
                                "where account_id = $1 order by is_account_holder desc, created_at", uuid.UUID(account))
    try:
        return [dict(r) for r in await run(fn)]
    except Exception as e:
        log.error("[passengers] not read: %s: %s", type(e).__name__, e)
        return []


async def save(account: str, people: List[Dict[str, Any]]) -> int:
    """Each new traveller once (the same full name and birthday is not saved twice); the first is the account holder."""
    run = _run()

    async def fn(conn):
        n = 0
        async with conn.transaction():
            has_holder = await conn.fetchval("select count(*) from saved_passengers where account_id = $1 and is_account_holder", uuid.UUID(account))
            for i, p in enumerate(people):
                dup = await conn.fetchval("select 1 from saved_passengers where account_id = $1 and lower(given_name) = lower($2) "
                                          "and lower(family_name) = lower($3) and born_on is not distinct from $4",
                                          uuid.UUID(account), p["given_name"], p["family_name"], p["born_on"])
                if dup:
                    continue
                await conn.execute("insert into saved_passengers (account_id, is_account_holder, given_name, family_name, born_on, title, gender) "
                                   "values ($1,$2,$3,$4,$5,$6,$7)", uuid.UUID(account), (i == 0 and not has_holder), p["given_name"],
                                   p["family_name"], p["born_on"], p["title"], p["gender"])
                n += 1
        return n
    return await run(fn)


def for_order(people: List[Dict[str, Any]], passenger_ids: List[str], email: str, phone: Optional[str]) -> Optional[List[dict]]:
    """Duffel's passengers for an offer, from the saved ones — None when there are fewer saved than seats."""
    if len(people) < len(passenger_ids):
        return None
    return [{"id": pid, "type": "adult", "given_name": p["given_name"], "family_name": p["family_name"],
             "born_on": str(p["born_on"]), "title": p["title"], "gender": p["gender"],
             "email": p.get("email") or email or "guest@example.com", "phone_number": p.get("phone_e164") or phone or "+34600000000"}
            for pid, p in zip(passenger_ids, people)]


__all__ = ["ASK", "MARK", "parse", "saved", "save", "for_order"]
