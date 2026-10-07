"""Sasha 167 · WHATSAPP DOES EVERYTHING THE WEB DOES — no "open Sasha at …" dead end.

The founder's live test: a voice note, transcribed perfectly ("I want a romantic location that has great Vietnamese food"),
got the canned "On WhatsApp I can book, change or cancel… for anything else, open Sasha at …". Now:

  · placeless()  — a request for a kind of place with NO place named ("a romantic spot with great Vietnamese food") is a search;
  · context()    — its place comes from the ACTIVE TRIP (one city → that city; a date or city said → that day; several → ONE
                   short question, "In Hanoi, Hoi An or Ho Chi Minh City?"), else the home city. The words said ("romantic",
                   "great Vietnamese food") shape the search;
  · a card picked from a trip search is ADDED to the trip on its day (a plan, not a booking — nothing is sent); "book it at 8"
    then runs the normal ladder (read-back, one yes);
  · web_turn()   — anything else goes to the web chat's own brain (conductor.conduct), rendered for WhatsApp: a trip plan is
                   built and saved on the account exactly as on the web;
  · ask_contact()— "add your name at {web}" became a question here: the name, with this WhatsApp number, under the consent
                   sentence shown;
  · reset the demo (founder only, after a yes): the TEST bookings and the places added on the demo are cleared.
"""
from __future__ import annotations

import logging
import re
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import List, Optional

log = logging.getLogger("booking_signer.wa_brain")

# ── a place asked for with no place named ────────────────────────────────────────────────────────────────────────────

_WANT = re.compile(r"\b(?:i(?:'d| would)?\s+(?:like|love|want|need|fancy)|we(?:'d| would)?\s+(?:like|love|want|need|fancy)|"
                   r"looking for|find\s+(?:me|us)|find\s+(?:an?|some)|show me|recommend|suggest|where (?:can|should|could) (?:i|we)|"
                   r"know (?:an?|any)|any (?:good|nice|great)|somewhere|quiero|busco|buscamos|recomi[eé]nda\w*)\b", re.I)
_PLACE = re.compile(r"\b(place|location|spot|somewhere|restaurant|bar|caf[eé]|bistro|food|dinner|lunch|brunch|breakfast|eat|meal|"
                    r"spa|massage|cocktails?|rooftop|wine|sitio|restaurante|cena|comida)s?\b", re.I)
#: a place said: "in Hoi An", "near the river in Hanoi" — that's handoff.find_request's, not ours
_SAID_WHERE = re.compile(r"\b(?:in|near|around|en|cerca de)\s+(?:the\s+)?[A-ZÁÉÍÓÚ]")
_NOT_PLACE = re.compile(r"\b(trip|itinerary|plan|flights?|fly|hotels?|stay|visa|weather|history|recipe|cook(?:ing)? at home|how to)\b", re.I)


def placeless(body: str) -> Optional[dict]:
    """{"what", "kind"} for a request for a kind of place with no place said — else None."""
    from .guest_whatsapp import CUISINE
    from . import handoff as HO
    t = body or ""
    cu = CUISINE.search(t)
    # Sasha 174 · or said BARE, as a voice note does: "a spa for two on the 13th at 4 in the afternoon" (no city: the trip's)
    bare = re.match(r"^\s*(?:(?:an?|some|una?|el|la)\s+)?(?:[a-záéíóúñ]+\s+){0,2}?(?:spa|massage|masaje|dinner|lunch|brunch|"
                    r"restaurant|table|cena|mesa|tattoo|cooking class|class)s?\b", t, re.I)
    # Sasha 186 · a cuisine said bare ("Indian food tonight", "sushi for 2 tonight") is a restaurant request too
    bare = bare or (cu and re.match(r"^\s*(?:(?:some|an?|una?)\s+)?\w+\s+(?:food|restaurant|place|dinner|lunch|tonight|for\s+\d)\b", t, re.I))
    if not (_WANT.search(t) or bare) or not (_PLACE.search(t) or cu or bare) or _SAID_WHERE.search(t) or _NOT_PLACE.search(t):
        return None
    low = t.lower()
    if re.search(r"\btattoo", low):
        kind = "tattoo studio"
    elif re.search(r"\bcooking class", low):
        kind = "cooking class"
    elif re.search(r"\b(spa|massage|masaje)\b", low):
        kind = "spa"
    elif re.search(r"\b(cocktails?|bar|wine|rooftop)\b", low) and not re.search(r"\b(food|dinner|lunch|eat|meal|restaurant)\b", low):
        kind = "cocktail bar" if "cocktail" in low else ("rooftop bar" if "rooftop" in low else ("wine bar" if "wine" in low else "bar"))
    else:
        kind = "restaurant"
    quals = HO.qualities(t)
    cuisine = cu[1].capitalize() if cu and kind == "restaurant" else None
    what = " ".join(x for x in (*quals, cuisine, kind) if x)
    return {"what": what, "kind": kind}


# ── where: the active trip, else home ────────────────────────────────────────────────────────────────────────────────

def home_city() -> tuple:
    """No account stores a home city yet: SASHA_HOME_CITY ("Madrid, ES"), Madrid by default — said as such."""
    import os
    raw = os.getenv("SASHA_HOME_CITY", "Madrid, ES")
    city, _, cc = raw.partition(",")
    return city.strip() or "Madrid", (cc.strip().upper() or "ES")


def _country_of(title: str, cities: List[str]) -> Optional[str]:
    from .handoff import COUNTRY_NAMES
    for w in re.findall(r"[A-Za-zÀ-ÿ]+(?:\s+[A-Za-zÀ-ÿ]+)?", title or ""):
        if w.lower() in COUNTRY_NAMES:
            return COUNTRY_NAMES[w.lower()]
    for w in (title or "").split():
        if w.lower().strip(",.") in COUNTRY_NAMES:
            return COUNTRY_NAMES[w.lower().strip(",.")]
    return None


def _days(p: dict) -> List[dict]:
    from . import plan_store as PS
    return PS.merge(p, []).get("days") or []


def _pick_day(days: List[dict], city: str, kind: str) -> Optional[dict]:
    """The first day in that city — preferring one with no booking of that kind yet."""
    there = [d for d in days if (d.get("city") or "").lower() == city.lower()]
    if not there:
        return None
    free = [d for d in there if not any((b.get("type") or "") == ("restaurant" if kind == "restaurant" else "beauty") for b in d.get("bookings") or [])]
    return (free or there)[0]


async def context(account: Optional[str], body: str, kind: str, now: datetime) -> dict:
    """{"where", "country", "trip"?} — or {"ask": [cities], "trip"} when only the guest can say which city."""
    from . import plan_store as PS, itinerary_q as IQ
    p = await PS.latest(account, body)
    end = p.get("end") if p else None
    if isinstance(end, str):
        end = date.fromisoformat(end)
    live = p and (p.get("plan") or {}).get("days") and (end is None or end >= now.date())
    if not live:
        city, cc = home_city()
        return {"where": city, "country": cc, "home": True}
    days = _days(p)
    cities = list(dict.fromkeys(d.get("city") for d in days if d.get("city")))
    cc = _country_of(p.get("title") or "", cities)
    trip = {"trip_id": p["trip_id"], "title": p.get("title")}

    def at(d: dict) -> dict:
        return {"where": d.get("city"), "country": cc, "trip": {**trip, "day": d.get("day"), "date": d.get("date"), "city": d.get("city")}}
    said = IQ.day_of(body, now)
    if said:
        d = next((x for x in days if x.get("date") == said.isoformat()), None)
        if d:
            return at(d)
    od = _ORD_DAY.search(ordinals_as_digits(body or ""))   # Sasha 174 · "on the 13th" (no month): the trip's 13th, and its city
    if od:
        d = next((x for x in days if x.get("date") and int(str(x["date"])[8:10]) == int(od[1])), None)
        if d:
            return at(d)
    named = [c for c in cities if re.search(rf"\b{re.escape(c)}\b", body or "", re.I)]
    if len(named) == 1:
        return at(_pick_day(days, named[0], kind))
    if len(cities) == 1:
        return at(_pick_day(days, cities[0], kind))
    return {"ask": cities, "country": cc, "trip": trip}


def _or_list(xs: List[str]) -> str:
    return xs[0] if len(xs) == 1 else ", ".join(xs[:-1]) + " or " + xs[-1]


async def search(ctx: dict, want: dict, body: str) -> None:
    """The search with its place from context, or the ONE question."""
    from . import guest_whatsapp as GW, handoff as HO
    c = await context(ctx["account"], body, want["kind"], ctx["now"])
    draft = HO._draft(body, ctx["now"])
    if c.get("ask"):
        nonce = uuid.uuid4().hex[:6]
        q = f"In {_or_list(c['ask'])}?"
        if len(c["ask"]) <= 3:
            ctx["out"].ask(q, [(x, f"where:{nonce}:{i}") for i, x in enumerate(c["ask"])])
        else:
            ctx["out"].text(q)
        ctx["st"]["pending"] = {"kind": "trip_where", "at": ctx["now"].isoformat(), "nonce": nonce, "want": want, "body": body,
                                "options": c["ask"], "country": c.get("country"), "trip": c["trip"], "draft": draft.get("parts") or {}}
        return
    await _run(ctx, want, c, draft.get("parts") or {}, body)


async def _run(ctx: dict, want: dict, c: dict, parts: dict, body: str = "") -> None:
    from . import guest_whatsapp as GW
    f = {"what": want["what"], "where": c["where"], "priority": "rated", **({"country": c["country"]} if c.get("country") else {}),
         **({"trip": c["trip"]} if c.get("trip") else {})}
    if c.get("home"):
        ctx["out"].text(f"No trip on now, so I looked near home ({c['where']}) — tell me a city for anywhere else.")
    await gate(ctx, f, parts, body, ["trip"])


async def answer(ctx: dict, pend: dict, body: str, payload: str) -> bool:
    """The answer to OUR open questions (trip_where · trip_added · contact_name · demo_reset). False: not an answer."""
    kind, out, st = pend["kind"], ctx["out"], ctx["st"]
    if kind == "trip_where":
        i = None
        if payload.startswith(f"where:{pend['nonce']}:"):
            i = int(payload.rsplit(":", 1)[1])
        else:
            hits = [k for k, x in enumerate(pend["options"]) if re.search(rf"\b{re.escape(x)}\b", body or "", re.I)]
            i = hits[0] if len(hits) == 1 else None
        if i is None or not 0 <= i < len(pend["options"]):
            return False
        st["pending"] = None
        from . import plan_store as PS
        p = await PS.latest(ctx["account"], pend["options"][i])
        d = _pick_day(_days(p), pend["options"][i], pend["want"]["kind"]) if p else None
        trip = {**pend["trip"], **({"day": d.get("day"), "date": d.get("date"), "city": d.get("city")} if d else {})}
        await _run(ctx, pend["want"], {"where": pend["options"][i], "country": pend.get("country"), "trip": trip}, pend.get("draft") or {}, pend.get("body") or "")
        return True
    if kind == "trip_added":
        m = re.search(r"\b(?:book|reserve|res[eé]rva)\b", body or "", re.I)
        if not m:
            return False
        st["pending"] = None
        await book_added(ctx, pend, body)
        return True
    if kind == "gate":
        return await _gate_answer(ctx, pend, body, payload)
    if kind == "contact_name":
        return await _contact_answer(ctx, pend, body)
    if kind == "demo_reset":
        from .guest_whatsapp import NO
        if payload == f"yes:{pend['nonce']}" or re.fullmatch(r"\s*(yes|yes please|s[ií]|ok|reset)\s*[.!]?\s*", body or "", re.I):
            st["pending"] = None
            n = await reset_demo(ctx["account"], dry=False)
            st["history"] = []   # Sasha 179 · the conversation starts fresh too
            out.text(f"Done — the demo is reset: {n['bookings']} TEST booking{'s' if n['bookings'] != 1 else ''}, "
                     f"{n['added']} added place{'s' if n['added'] != 1 else ''}, {n.get('saved', 0)} saved "
                     f"search{'es' if n.get('saved') != 1 else ''} and {n.get('plans', 0)} "
                     f"plan{'s' if n.get('plans') != 1 else ''}/journey{'s' if n.get('plans') != 1 else ''} cancelled"
                     + (f", {n['modes']} open product conversation{'s' if n.get('modes') != 1 else ''} closed" if n.get("modes") else "")
                     + ". No tabs — ready from zero. Real bookings stay in Receipts.")
            return True
        if payload == f"no:{pend['nonce']}" or NO.fullmatch(body or ""):
            st["pending"] = None
            out.text("OK — nothing was cleared.")
            return True
        return False
    return False


# ── a clear request leaves any product mode (Sasha 167, live: a stale CampusMe took a Hoi An dinner) ────────────────────

def sasha_clear(body: str, history: list, now) -> bool:
    """A booking, a search, a flight, a hotel or the itinerary — said plainly enough that no product question is its answer."""
    from . import guest_whatsapp as GW, handoff as HO, itinerary_q as IQ
    t = body or ""
    if not t.strip():
        return False
    try:
        h = HO.booking_handoff(t, [], now)
        # a place to book, said as such — "check TotalEnergies in France" is AD's, not a search
        bookable = HO._BOOKABLE.search(t) or GW.CUISINE.search(t) or HO._LOOSE_ASK.search(t)
        if h and (h.get("booking_cancel") or ((h.get("booking_find") or {}).get("where") and bookable)):
            return True
        if GW.FLIGHT.search(t) or GW.HOTEL.search(t) or IQ.TRIP.search(t) or placeless(t):
            return True
    except Exception as e:   # a detector's failure never takes the guest's turn
        log.warning("[wa_brain] sasha_clear failed: %s: %s", type(e).__name__, e)
    return False


# ── before a search: the hour (morning or night?) and the day (inside the trip?) ───────────────────────────────────

_HHMM = re.compile(r"\b(0?[1-9]|1[01])[:.h]([0-5]\d)\b(?!\s*(?:am|pm|a\.m|p\.m))", re.I)
_NIGHT = re.compile(r"\b(at night|tonight|in the evening|evening|pm|p\.m|de la noche|por la noche|noche|night)\b", re.I)
_MORNING = re.compile(r"\b(in the morning|morning|am|a\.m|de la ma[nñ]ana|breakfast|brunch|desayuno|coffee)\b", re.I)
_EVENINGISH = re.compile(r"\b(dinner|supper|romantic|restaurant|table|cena|drinks|cocktails?|bar|date night)\b", re.I)


def hour_said(body: str) -> Optional[tuple]:
    """(hour, minute, "night" | "morning" | None) for an HH:MM under 12 said without am/pm — None when there is none."""
    m = _HHMM.search(body or "")
    if not m:
        return None
    side = "night" if _NIGHT.search(body) else "morning" if _MORNING.search(body) else None
    return int(m[1]), int(m[2]), side


def _set_time(f: dict, parts: dict, hh: int, mm: int) -> None:
    day = (f.get("open_at") or ((parts.get("when") or {}).get("at")) or "")[:10]
    if not day:
        return
    at = f"{day}T{hh:02d}:{mm:02d}"
    f["open_at"] = at
    parts["when"] = {"mode": "at", "at": at}


async def gate(ctx: dict, f: dict, parts: dict, body: str, done: Optional[list] = None) -> None:
    """The questions before a search, each asked at most once, then the search itself (GW._find)."""
    from . import guest_whatsapp as GW, plan_store as PS, sentences as SN
    done = list(done or [])
    nonce = uuid.uuid4().hex[:6]
    hs = hour_said(body) if "hour" not in done and not f.get("named") else None
    if hs and (f.get("open_at") or (parts.get("when") or {}).get("at")):
        h, mi, side = hs
        if side == "night":
            _set_time(f, parts, h + 12, mi)          # "08:00 at night" → 20:00, never asked
        elif side is None and _EVENINGISH.search(f"{body} {f.get('what') or ''}"):
            ctx["out"].ask(f"{h} in the morning or {h} at night?", [(f"{h} in the morning", f"am:{nonce}"), (f"{h} at night", f"pm:{nonce}")])
            ctx["st"]["pending"] = {"kind": "gate", "q": "hour", "at": ctx["now"].isoformat(), "nonce": nonce, "f": f, "parts": parts,
                                    "body": body, "done": done + ["hour"], "hm": [h, mi]}
            return
    done.append("hour")
    if "ordinal" not in done:
        done.append("ordinal")
        await _ordinal_day(ctx, f, parts, body)
    if not f.get("open_at") and not (parts.get("when") or {}).get("at") and parts.get("day") and spoken_time(body):
        # Sasha 170 · "… on the 13th at 4 in the afternoon": the time said aloud, with the day (it asked "What time?")
        f["open_at"] = f"{parts['day']}T{spoken_time(body)}"
        parts["when"] = {"mode": "at", "at": f["open_at"]}
    day = (f.get("open_at") or (parts.get("when") or {}).get("at") or parts.get("day") or "")[:10]
    if not f.get("country") and f.get("where"):   # a city on the trip: its country, in Google's words too (venue_read.find_venues)
        pc = await PS.latest(ctx["account"], f"{f.get('where') or ''} {body}")
        if pc and any(c and c.lower() in f["where"].lower() for c in (pc.get("cities") or [])):
            cc = _country_of(pc.get("title") or "", [])
            if cc:
                f["country"] = cc
    if "trip" not in done and day and not f.get("trip") and _DATE_SAID.search(ordinals_as_digits(body)):
        p = await PS.latest(ctx["account"], f"{f.get('where') or ''} {body}")
        if p and p.get("start") and p.get("end"):
            start, end = (date.fromisoformat(str(x)[:10]) for x in (p["start"], p["end"]))
            cities = [c for c in (p.get("cities") or []) if c and c.lower() in (f.get("where") or "").lower()]
            if cities and not f.get("country"):
                cc = _country_of(p.get("title") or "", cities)
                if cc:
                    f["country"] = cc
            d = date.fromisoformat(day)
            if cities and not start <= d <= end:
                ctx["out"].ask(f"{SN.day_words(day)} is outside your trip ({SN.day_words(start.isoformat())} to "
                               f"{SN.day_words(end.isoformat())}). Add it to the trip, or keep it separate?",
                               [("Add to my trip", f"tripadd:{nonce}"), ("Keep it separate", f"tripkeep:{nonce}")])
                ctx["st"]["pending"] = {"kind": "gate", "q": "trip", "at": ctx["now"].isoformat(), "nonce": nonce, "f": f, "parts": parts,
                                        "body": body, "done": done + ["trip"], "trip_id": p["trip_id"], "city": cities[0], "day": day}
                return
    await GW._find(ctx, f, {"parts": parts})


_ORD_UNITS = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6, "seventh": 7, "eighth": 8, "ninth": 9}
_ORD_TEENS = {"tenth": 10, "eleventh": 11, "twelfth": 12, "thirteenth": 13, "fourteenth": 14, "fifteenth": 15, "sixteenth": 16,
              "seventeenth": 17, "eighteenth": 18, "nineteenth": 19, "twentieth": 20, "thirtieth": 30}


def ordinals_as_digits(t: str) -> str:
    """Sasha 171 · a voice note's "on the sixteenth" → "on the 16th" (Deepgram writes the words; the date was lost, live)."""
    # Sasha 174 · Spanish: "el 16" (a day, not "el 16 de noviembre", which has its month) → "the 16th"
    t = re.sub(r"\bel\s+(\d{1,2})\b(?!\s*(?:de\s+[a-z]|personas|people|h\b|:))", lambda m: f"the {m[1]}th", t or "", flags=re.I)
    t = re.sub(r"\b(twenty|thirty)[\s-](" + "|".join(_ORD_UNITS) + r")\b",
               lambda m: f"{(20 if m[1].lower() == 'twenty' else 30) + _ORD_UNITS[m[2].lower()]}th", t or "", flags=re.I)
    t = re.sub(r"\b(" + "|".join(_ORD_TEENS) + r")\b", lambda m: f"{_ORD_TEENS[m[1].lower()]}th", t, flags=re.I)
    return re.sub(r"\bthe\s+(" + "|".join(_ORD_UNITS) + r")\b(?!\s+(?:one|place|card|restaurant|option))",
                  lambda m: f"the {_ORD_UNITS[m[1].lower()]}th", t, flags=re.I)


#: a date the guest SAID (else "outside your trip?" is never asked — live it asked about today, which nobody had said)
_DATE_SAID = re.compile(r"\b(today|tonight|tomorrow|monday|tuesday|wednesday|thursday|friday|saturday|sunday|"
                        r"jan(?:uary)?|feb(?:ruary)?|march|apr(?:il)?|may|june?|july?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|"
                        r"dec(?:ember)?|\d{1,2}(?:st|nd|rd|th)|\d{1,2}[/.-]\d{1,2}|hoy|ma[nñ]ana|lunes|martes|mi[eé]rcoles|jueves|viernes|"
                        r"s[aá]bado|domingo)\b", re.I)


_ORD_DAY = re.compile(r"\b(?:on\s+)?the\s+(\d{1,2})(?:st|nd|rd|th)\b", re.I)
_MONTH_WORD = re.compile(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\b", re.I)


_WORDNUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
            "twelve": 12}
_SPOKEN = re.compile(r"\b(\d{1,2}|" + "|".join(_WORDNUM) + r")(?:[:.](\d{2}))?\s*(?:o'?clock\s*)?"
                     r"(in the morning|am|a\.m\.?|in the afternoon|in the evening|at night|tonight|pm|p\.m\.?|de la ma[nñ]ana|de la tarde|de la noche)",
                     re.I)


def spoken_time(body: str) -> Optional[str]:
    """Sasha 169 · a time as it is SAID: "10 in the morning", "eight at night", "3 in the afternoon" → HH:MM."""
    m = _SPOKEN.search(body or "")
    if not m:
        return None
    h = int(m[1]) if m[1].isdigit() else _WORDNUM[m[1].lower()]
    if not 1 <= h <= 12:
        return None
    pm = re.search(r"afternoon|evening|night|tonight|pm|p\.m|tarde|noche", m[3], re.I)
    h = (h % 12) + (12 if pm else 0)
    return f"{h:02d}:{int(m[2] or 0):02d}"


async def _ordinal_day(ctx: dict, f: dict, parts: dict, body: str) -> None:
    """Sasha 169 · "on the 16th", no month: the trip's 16th when a trip covers one, else the next 16th — never today (it was)."""
    from . import plan_store as PS
    body = ordinals_as_digits(body or "")
    m = _ORD_DAY.search(body)
    if not m or _MONTH_WORD.search(body):
        return
    n, today = int(m[1]), ctx["now"].date()
    pick = None
    p = await PS.latest(ctx["account"], f"{f.get('where') or ''} {body}")
    if p and p.get("start") and p.get("end"):
        a, b = (date.fromisoformat(str(x)[:10]) for x in (p["start"], p["end"]))
        pick = next((a + timedelta(days=i) for i in range((b - a).days + 1) if (a + timedelta(days=i)).day == n), None)
    if pick is None:
        y, mo = today.year, today.month
        for _ in range(3):
            try:
                c = date(y, mo, n)
                if c >= today:
                    pick = c
                    break
            except ValueError:
                pass
            y, mo = (y + 1, 1) if mo == 12 else (y, mo + 1)
    if pick is None:
        return
    at = f.get("open_at") or (parts.get("when") or {}).get("at")
    if at:
        _set_time(f, parts, int(at[11:13]), int(at[14:16]))
        f["open_at"] = f"{pick.isoformat()}{f['open_at'][10:]}"
        parts["when"] = {"mode": "at", "at": f["open_at"]}
    else:
        parts["day"] = pick.isoformat()


async def _gate_answer(ctx: dict, pend: dict, body: str, payload: str) -> bool:
    from . import plan_store as PS, sentences as SN
    n, t = pend["nonce"], body or ""
    if pend["q"] == "hour":
        h, mi = pend["hm"]
        pm = payload == f"pm:{n}" or (not payload and bool(_NIGHT.search(t) or re.search(r"\b(dinner|cena|evening)\b", t, re.I)))
        am = payload == f"am:{n}" or (not payload and bool(_MORNING.search(t)))
        if pm == am:
            return False
        _set_time(pend["f"], pend["parts"], h + 12 if pm else h, mi)
    else:
        add = payload == f"tripadd:{n}" or (not payload and bool(re.search(r"\b(add|yes|trip|a[nñ]ade)\b", t, re.I)))
        keep = payload == f"tripkeep:{n}" or (not payload and bool(re.search(r"\b(separate|keep|no|aparte)\b", t, re.I)))
        if add == keep:
            return False
        if add:
            ok = await PS.add_day(ctx["account"], pend["trip_id"], pend["day"], pend["city"])
            ctx["out"].text(f"Added {SN.day_words(pend['day'])} in {pend['city']} to your trip." if ok
                            else "I couldn't add that day to your trip — I'll book it on its own.")
    ctx["st"]["pending"] = None
    await gate(ctx, pend["f"], pend["parts"], pend["body"], pend["done"])
    return True


async def trip_day_words(account: str, day: str, venue: str) -> str:
    """Sasha 171 · "Added to your Vietnam trip (Day 5, Mon 16 Nov)" — only when that day IS on the plan (merge puts it there
    by its date); else "It's in your bookings"."""
    from . import plan_store as PS
    try:
        p = await PS.latest(account, venue)
        if p and day:
            d = next((x for x in PS.merge(p, []).get("days") or [] if x.get("date") == day), None)
            if d:
                dd = date.fromisoformat(day)
                cc = _country_of(p.get("title") or "", [])
                from .venue_read import COUNTRY_NAME
                trip = f"{COUNTRY_NAME.get(cc)} trip" if cc and COUNTRY_NAME.get(cc) else "trip"
                return f"Added to your {trip} (Day {d.get('day')}, {dd.strftime('%a')} {dd.day} {dd.strftime('%b')})"
    except Exception as e:
        log.warning("[wa_brain] trip day not named: %s: %s", type(e).__name__, e)
    return "It's in your bookings"


# ── a card picked from a trip search → on the trip, on its day ───────────────────────────────────────────────────────

async def add_to_trip(ctx: dict, pend: dict, card: dict) -> None:
    from . import plan_store as PS, sentences as SN
    f, trip = pend["find"], pend["find"]["trip"]
    part = "Evening" if f.get("what", "").endswith("restaurant") or "bar" in f.get("what", "") else "Afternoon"
    ok = await PS.add_place(ctx["account"], trip["trip_id"], trip.get("day"), {
        "name": card.get("name"), "time": part, "place_id": card.get("place_id"), "added": True,
        "blurb": f"{f.get('what')} — picked on WhatsApp; not booked yet"})
    if not ok:
        ctx["out"].text(f"I couldn't add {card.get('name')} to your trip just now — nothing was booked. Say “book {card.get('name')}” to book it.")
        return
    on = f"Day {trip.get('day')} · {SN.day_words(trip['date'])}" if trip.get("date") else f"Day {trip.get('day')}"
    ctx["out"].text(f"Added {card.get('name')} to {on} in {trip.get('city') or f.get('where')} — {trip.get('title') or 'your trip'}. "
                    f"Nothing is booked yet: say “book it at 8” and I'll ask them for a table.")
    ctx["st"]["pending"] = {"kind": "trip_added", "at": ctx["now"].isoformat(), "card": card, "find": f, "draft": pend.get("draft") or {}}


async def book_added(ctx: dict, pend: dict, body: str) -> None:
    """"book it at 8 for 2" → the venue's own route (the read-back and one yes), on the trip's day."""
    from . import guest_whatsapp as GW, handoff as HO
    f = {k: v for k, v in pend["find"].items() if k != "trip"}
    day = (pend["find"].get("trip") or {}).get("date")
    at = HO.plain_open_at(body, ctx["now"])
    hm = re.search(r"\bat\s+(\d{1,2})(?::(\d{2}))?\b", body or "", re.I)
    if day and hm and not re.search(r"\d\s*(?:am|pm)|\d:\d", body or "", re.I) and 1 <= int(hm[1]) <= 12:
        at = HO.restaurant_time({"day": day, "hour": int(hm[1]), "minute": int(hm[2] or 0)})
    elif day and at:
        at = f"{day}T{at[11:16]}"
    if at:
        f["open_at"] = at
    parts = dict(pend.get("draft") or {})
    n = HO.plain_party(body or "")
    if n:
        parts["how_many"] = {"count": n, "unit": "people"}
    await GW._picked_card(ctx, {"find": f, "draft": parts}, pend["card"])


# ── the web chat's brain, for everything else ────────────────────────────────────────────────────────────────────────

def wa_markdown(s: str) -> str:
    s = re.sub(r"\*\*(.+?)\*\*", r"*\1*", s or "")
    s = re.sub(r"^#{1,6}\s*", "", s, flags=re.M)
    s = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r"\1: \2", s)
    return s.strip()


def chunks(lines: List[str], size: int = 1400) -> List[str]:
    out, cur = [], ""
    for ln in lines:
        while len(ln) > size:
            cut = ln.rfind("\n", 0, size)
            cut = cut if cut > 200 else size
            if cur:
                out.append(cur)
                cur = ""
            out.append(ln[:cut])
            ln = ln[cut:].lstrip("\n")
        if cur and len(cur) + len(ln) + 2 > size:
            out.append(cur)
            cur = ""
        cur = f"{cur}\n\n{ln}" if cur else ln
    return out + ([cur] if cur else [])


CONDUCT = None   # tests replace it


async def web_turn(ctx: dict, body: str) -> bool:
    """The web chat's answer, on WhatsApp. False only when the brain itself failed."""
    from . import guest_whatsapp as GW
    conduct = CONDUCT
    if conduct is None:
        from app.services.conductor import conduct
    hist = [h for h in (ctx["st"].get("history") or []) if h.get("role") in ("user", "assistant")][-12:]
    try:
        r = await conduct(body, hist, user_id=ctx["account"], signed_in=True,
                          session_id=f"wa-{(ctx.get('ch') or {}).get('wa_id_sha256', '')[:16]}")
    except Exception as e:
        log.error("[wa_brain] the web brain failed on WhatsApp: %s: %s", type(e).__name__, e)
        return False
    out = ctx["out"]
    if r.get("booking_find"):
        await GW._find(ctx, r["booking_find"], r.get("reservation_draft") or {})
        return True
    for c in chunks([wa_markdown(r.get("response") or "")]):
        out.text(c)
    for b in r.get("bookings") or []:   # Sasha 198 R5 · the guided trip's flights, as the web shows them: numbered, to CHOOSE
        if isinstance(b, dict) and b.get("trip_pick"):
            out.text("\n".join(f"{i}. {o.get('name')} — {o.get('price') or ''} · {o.get('detail') or ''}".strip(" ·")
                                for i, o in enumerate([o for o in b.get("options") or [] if not o.get("fallback")][:4], 1))
                     + "\n\nReply with its number or airline to add it to your itinerary.")
    shown = 0
    for ph in r.get("photos") or []:
        url = ph.get("url") if isinstance(ph, dict) else ph if isinstance(ph, str) else None
        if url and url.startswith("https://") and shown < 3:
            out.media((ph.get("caption") or ph.get("title") or "📷") if isinstance(ph, dict) else "📷", url)
            shown += 1
    if r.get("itinerary") and (r["itinerary"] or {}).get("days"):
        from . import plan_store as PS, itinerary_q as IQ
        p = await PS.latest(ctx["account"])
        if p:
            from . import journeys as JN
            await JN.file(ctx["account"])
            for c in chunks(PS.text(await PS.view(ctx["account"], p, JN.for_journey(await IQ._rows(ctx["account"]), p.get("trip_id"))))):
                out.text(c)
            out.text("It's saved on your account — it's the same plan on the web. Ask for a place (“a romantic dinner in Hoi An”) and I'll add it to its day.")
    links = [l for l in r.get("links") or [] if isinstance(l, dict) and str(l.get("url", "")).startswith("https://")][:3]
    for l in links:
        out.text(f"{l.get('title') or l.get('label') or 'Link'}: {l['url']}")
    return True


# ── the name to book under, asked here ───────────────────────────────────────────────────────────────────────────────

async def ask_contact(ctx: dict, resume: Optional[dict]) -> None:
    from .contacts import consent
    num = ctx.get("wa_number")
    if not num:
        ctx["out"].text("Whose name should I book under? Tell me the name and a mobile with its country code, e.g. “Tyler Warren +34 600 000 000”. "
                        + consent()["text"])
    else:
        ctx["out"].text(f"Whose name should I book under? I'll give them that name and this WhatsApp number. {consent()['text']} Reply with the name.")
    ctx["st"]["pending"] = {"kind": "contact_name", "at": ctx["now"].isoformat(), "resume": resume}


async def _contact_answer(ctx: dict, pend: dict, body: str) -> bool:
    from . import guest_whatsapp as GW
    from .contacts import consent, e164
    t = " ".join((body or "").split())
    phone = re.search(r"\+?\d[\d\s().-]{7,}\d", t)
    mobile = e164(phone[0]) if phone else e164(ctx.get("wa_number"))
    name = (t[:phone.start()] + t[phone.end():]).strip(" ,.") if phone else t.strip(" .")
    if not 1 <= len(name) <= 80 or len(name.split()) > 6 or re.search(r"[?@]|\b(book|cancel|find|show|what|where)\b", name, re.I):
        return False   # not a name: a new request
    if not mobile:
        ctx["out"].text("And a mobile with its country code, e.g. +34 600 000 000?")
        return True
    c = consent()
    s, j = await GW.api(ctx["account"], "PUT", "/api/booking/contact",
                        {"name": name, "mobile": mobile, "consent_version": c["version"], "consent_sha256": c["sha256"]})
    if s != 200:
        ctx["st"]["pending"] = None
        ctx["out"].text(f"I couldn't save that — {GW.refusal_words(j, s)}. Nothing was booked.")
        return True
    ctx["st"]["pending"] = None
    ctx["out"].text(f"Saved — bookings go under {name}.")
    resume = pend.get("resume")
    if resume and resume.get("kind") == "need":
        resume["at"] = ctx["now"].isoformat()
        await GW._prepare_or_ask(ctx, resume)
    elif resume is None:
        ctx["out"].text("Now, what shall I book?")
    return True


# ── reset the demo (founder only) ────────────────────────────────────────────────────────────────────────────────────

RESET = re.compile(r"^\s*(?:please\s+)?(?:reset|clear)\s+(?:the\s+|my\s+)?demo\s*[.!]?\s*$", re.I)
_TEST_SQL = ("(ti.provider_name ilike 'Sasha Test Venue%' or ti.provider_name ilike '%(TEST booking%' or ti.booking_reference like 'TEST-%' "
             "or ti.provider_name ilike '%(TEST stand-in)%' "
             "or ti.booking_reference like 'TV-%')")


def is_test(b: dict) -> bool:
    v, ref = b.get("venue") or "", b.get("ref") or b.get("booking_reference") or ""
    return bool(re.match(r"Sasha Test Venue", v) or "(TEST booking" in v or "(TEST stand-in)" in v or re.match(r"(TEST|TV)-", ref)
                or re.search(r"their ref TV-", b.get("status_words") or ""))


async def reset_demo(account: str, dry: bool) -> dict:
    """{"bookings": n, "added": n}: the founder's TEST bookings from today on (status → cancelled; nothing is deleted) and the
    places added to his latest plan on WhatsApp."""
    from . import plan_store as PS
    run = PS._run()
    if run is None:
        return {"bookings": 0, "added": 0}

    async def fn(conn):
        where = (f"from trip_items ti join trips t on t.id = ti.trip_id where t.owner_id = $1 and {_TEST_SQL} "
                 "and ti.status not in ('cancelled', 'failed') and (ti.date_time >= now() - interval '1 day' or ti.date_time is null)")   # Sasha 186 · undated quote requests too
        if dry:
            return await conn.fetchval(f"select count(*) {where}", uuid.UUID(account))
        ids = [r["id"] for r in await conn.fetch(f"select ti.id {where}", uuid.UUID(account))]
        if ids:
            await conn.execute("update trip_items set status = 'cancelled', updated_at = now() where id = any($1::uuid[])", ids)
        return len(ids)
    n = await run(fn)
    added = await PS.clear_added(account, dry=dry)

    async def clean(conn):   # Sasha 179 · a clean slate: saved searches, and stray plans (no dates, nothing in them) go too
        a = uuid.UUID(account)
        saved = await conn.fetch("select ti.id from trip_items ti join trips t on t.id = ti.trip_id where t.owner_id = $1 "
                                 "and ti.status = 'pending' and ti.escalation_notes = $2", a, SAVED_NOTE())
        # Sasha 181 · EVERY plan/journey (dated too) is cancelled — the demo starts from zero tabs; nothing is deleted
        stray = await conn.fetch("select t.id from trips t where t.owner_id = $1 and t.destinations ? 'plan' "
                                 "and t.status in ('draft', 'active')", a)
        if not dry:
            if saved:
                await conn.execute("update trip_items set status = 'cancelled', updated_at = now() where id = any($1::uuid[])",
                                   [r["id"] for r in saved])
            if stray:
                await conn.execute("update trips set status = 'cancelled', updated_at = now() where id = any($1::uuid[])",
                                   [r["id"] for r in stray])
            # the reset's marker (a cancelled row, never a tab): product tabs stay hidden until that product is used again
            await conn.execute("insert into trips (owner_id, title, status, destinations) values ($1, $2, 'cancelled', $3)",
                               a, RESET_MARK, {"demo_reset_at": datetime.now(timezone.utc).isoformat()})
        return len(saved), len(stray)
    saved_n, stray_n = await run(clean)

    async def unpaid(conn):   # Sasha 186 · a "Tap to pay" never paid: its link expires and its row is cancelled
        from .paid_watch import MARK
        return await conn.fetch("select ti.id, ti.escalation_notes from trip_items ti join trips t on t.id = ti.trip_id where t.owner_id = $1 "
                                "and ti.status = 'pending' and ti.escalation_notes like $2", uuid.UUID(account), MARK + "%")
    waiting = await run(unpaid)
    if not dry and waiting:
        import json as _json
        from . import test_deposit as TD
        from .paid_watch import MARK
        for w in waiting:
            sid = (_json.loads(w["escalation_notes"][len(MARK):]) or {}).get("sid")
            try:
                if sid and not await TD.session_paid(sid):
                    await TD.HTTP("POST", f"/checkout/sessions/{sid}/expire", {})
            except Exception as e:
                log.warning("[wa_brain] a test payment link not expired: %s", type(e).__name__)
        await run(lambda c: c.execute("update trip_items set status = 'cancelled', escalation_notes = 'Sasha 186 · reset: the unpaid TEST link expired', "
                                      "updated_at = now() where id = any($1::uuid[])", [w["id"] for w in waiting]))
    if not dry:   # Sasha 194 · a clean start: no quote, flight list, offer or pick from before the reset may come back
        try:
            from . import trip_book as _TB
            _TB._QUOTES.pop(account, None)
            from app.services import chat_store as _CS
            for _s in await _CS.list_sessions(account):
                await _CS.clear_session_cards(_s.get("id"))
        except Exception as e:
            log.warning("[wa_brain] cached searches not cleared: %s: %s", type(e).__name__, e)
    modes = 0
    if not dry:   # CR 39 · the open CampusMe / RelocateMe / EspañaMe conversations close too (their files are kept)
        try:
            from products import whatsapp as PW
            if hasattr(PW, "reset_modes"):
                modes = int(await PW.reset_modes(account) or 0)
        except Exception as e:
            log.warning("[wa_brain] product modes not reset: %s: %s", type(e).__name__, e)
    return {"bookings": int(n or 0), "added": added, "modes": modes, "saved": saved_n, "plans": stray_n, "links": len(waiting)}


RESET_MARK = "Sasha · demo reset"


def SAVED_NOTE() -> str:
    from .journeys import SAVED
    return SAVED


async def start_reset(ctx: dict) -> None:
    # Sasha 179 · any account (a guest too): it only ever touches that account's OWN TEST bookings, saved searches, added
    # places, empty undated plans and open conversation — real bookings, dated plans and files are never touched
    n = await reset_demo(ctx["account"], dry=True)
    nonce = uuid.uuid4().hex[:6]
    bits = [f"{n['bookings']} TEST booking{'s' if n['bookings'] != 1 else ''}", f"{n['added']} added place{'s' if n['added'] != 1 else ''}",
            f"{n.get('saved', 0)} saved search{'es' if n.get('saved') != 1 else ''}",
            f"{n.get('plans', 0)} plan{'s' if n.get('plans') != 1 else ''}/journey{'s' if n.get('plans') != 1 else ''}"]
    ctx["out"].ask(f"That clears {', '.join(bits)} — every tab goes (real bookings stay, in Receipts; nothing is deleted). Reset?",
                   [("Reset", f"yes:{nonce}"), ("Keep them", f"no:{nonce}")])
    ctx["st"]["pending"] = {"kind": "demo_reset", "at": ctx["now"].isoformat(), "nonce": nonce}


# ── Sasha 178 · PARK AND SWITCH ─────────────────────────────────────────────────────────────────────────────────────────

PARK = re.compile(r"\b(?:not ready to book|not ready yet|not yet|hold (?:it|that|on to it)|save (?:it|that|this)(?: for later)?|keep it for later|"
                  r"later,? (?:please|thanks)|maybe later|park (?:it|that))\b", re.I)
START = re.compile(r"^\s*(?:ok(?:ay)?[,.!]?\s+)?(?:let me |let'?s |i(?:'d| would) like to |i want to )?start (?:another(?: one)?|something else|a new one)"
                   r"\s*[:,.-]?\s*(?P<rest>.*)$", re.I)
PARKABLE = ("cards", "confirm", "need", "gate", "trip_added")


async def save_item(account: str, name: str, at: Optional[str], city: Optional[str]) -> Optional[str]:
    """A saved, unbooked item on the account's list (filed like any booking, shown 'Saved — not booked yet')."""
    from . import plan_store as PS, journeys as JN
    from .store import BOOKINGS_TRIP_TITLE
    run = PS._run()
    if run is None:
        return None
    tz = "Asia/Ho_Chi_Minh" if city and city.split(",")[0].strip().lower() in __import__("booking_signer.handoff", fromlist=["VN_CITIES"]).VN_CITIES else "Europe/Madrid"

    async def go(conn):
        a = uuid.UUID(account)
        trip = await conn.fetchval("select id from trips where owner_id = $1 and title = $2 limit 1", a, BOOKINGS_TRIP_TITLE)
        if trip is None:
            trip = await conn.fetchval("insert into trips (owner_id, title) values ($1,$2) returning id", a, BOOKINGS_TRIP_TITLE)
        dt = datetime.fromisoformat(at).replace(tzinfo=__import__("zoneinfo").ZoneInfo(tz)) if at and "T" in at else \
            (datetime.fromisoformat(f"{at[:10]}T00:00").replace(tzinfo=__import__("zoneinfo").ZoneInfo(tz)) if at else None)
        return await conn.fetchval("insert into trip_items (trip_id, type, status, provider_name, date_time, local_timezone, location_name, "
                                   "escalation_notes) values ($1,'other','pending',$2,$3,$4,$5,$6) returning id",
                                   trip, name[:200], dt, tz, (city or "")[:120] or None, JN.SAVED)
    try:
        tid = await run(go)
        await JN.file(account)
        return str(tid)
    except Exception as e:
        log.warning("[wa_brain] not saved: %s: %s", type(e).__name__, e)
        return None


async def tab_of(account: str, city: Optional[str], at: Optional[str]) -> str:
    """The tab a saved item lands in, in words."""
    from . import journeys as JN, plan_store as PS
    for p in await PS.plans(account):
        pl = {**p, "country": JN.country_of_plan(p["title"], p.get("cities") or [])}
        if at and JN.fits({"date": at[:10], "read_city": city}, pl):
            return JN.label(pl)
    home = JN.home_label()
    if not city or JN._fold(city.split(",")[-1].strip()) in (JN._fold(home.replace(" (home)", "")), "madrid"):
        return home
    return city.split(",")[-1].strip() if "," in city else city


async def park(ctx: dict, pend: dict) -> str:
    """"I'm not ready to book that yet": what's open is SAVED (unbooked) in its tab; the open question closes. → its words."""
    f = pend.get("find") or (pend.get("read") and {"what": pend["read"].get("venue"), "where": None}) or {}
    name = (pend.get("venue") or (pend.get("read") or {}).get("venue") or
            (f"{f.get('what')} in {f.get('where')}" if f.get("where") else f.get("what")) or "your request")
    from .guest_whatsapp import plain_venue
    name = plain_venue(name)
    at = f.get("open_at") or ((pend.get("draft") or {}).get("when") or {}).get("at") or (pend.get("draft") or {}).get("day")
    city = f.get("where")
    ctx["st"]["pending"] = None
    tid = await save_item(ctx["account"], f"{name} (saved)", at, city)
    if not tid:
        return "I couldn't save it just now — nothing was booked."
    return f"Saved, not booked: {name} — it's in your {await tab_of(ctx['account'], city, at)} tab and in Requests."


async def start_another(ctx: dict, rest: str) -> None:
    """"let me start another: a restaurant in Madrid tonight, a spa in Paris on Saturday" → each saved into its tab;
    a city that's neither home nor on a trip is asked about ONCE."""
    from . import handoff as HO, plan_store as PS
    parts = [x.strip(" .") for x in re.split(r",|;|\s+and\s+(?=(?:an?|some|the)\s)", rest or "") if x.strip(" .")]
    finds = []
    for part in parts:
        h = HO.booking_handoff(part, [], ctx["now"])
        f = (h or {}).get("booking_find")
        if f and f.get("where"):
            d = (h.get("reservation_draft") or {}).get("parts") or {}
            g, gp = dict(f), dict(d)
            await _ordinal_day(ctx, g, gp, part)
            finds.append((g, gp, part))
    if not finds:
        ctx["out"].text("Tell me what to start, e.g. “a restaurant in Madrid tonight”.")
        return
    trip_cities = {JN_fold(c) for p in await PS.plans(ctx["account"]) for c in (p.get("cities") or [])}
    if len(finds) == 1:   # one thing: its search — Sasha 179 (2) · a city that's neither home nor on a trip is asked about ONCE first
        f, gp, part = finds[0]
        city = f["where"].split(",")[-1].strip()
        at = f.get("open_at") or gp.get("day")
        if JN_fold(city) not in trip_cities and JN_fold(city) != "madrid" and \
                await tab_of(ctx["account"], f["where"], at) not in [JN_label(p) for p in await PS.plans(ctx["account"])] and \
                not (ctx["st"].get("city_asked") or {}).get(JN_fold(city)):
            nonce = uuid.uuid4().hex[:6]
            ctx["out"].ask(f"{f['what'].capitalize()} in {city} — is that a one-off, or part of a trip?",
                           [("A one-off", f"oneoff:{nonce}"), ("Part of a trip", f"tripq:{nonce}")])
            ctx["st"]["pending"] = {"kind": "city_q", "at": ctx["now"].isoformat(), "nonce": nonce, "city": city,
                                    "then": {"f": f, "gp": gp, "part": part}}
            return
        await gate(ctx, f, gp, part)
        return
    lines, new_city = [], None
    for f, gp, part in finds:
        at = f.get("open_at") or gp.get("day")
        await save_item(ctx["account"], f"{HO.found_line(f)[len('Here are the best-rated '):].rstrip('.')} (saved)"
                        if f["what"] else part, at, f["where"])
        tab = await tab_of(ctx["account"], f["where"], at)
        lines.append(f"• {f['what']} in {f['where']}{(' — ' + SN_day(at)) if at else ''} → {tab}")
        city = f["where"].split(",")[-1].strip()
        if not new_city and JN_fold(city) not in trip_cities and JN_fold(city) not in ("madrid",):
            new_city = city
    ctx["out"].text("Started, both saved (nothing booked yet):\n" + "\n".join(lines) + "\nSay “show me the places for …” to see them.")
    if new_city:
        nonce = uuid.uuid4().hex[:6]
        ctx["out"].ask(f"Is {new_city} part of a trip, or a one-off?", [("A one-off", f"oneoff:{nonce}"), ("Part of a trip", f"tripq:{nonce}")])
        ctx["st"]["pending"] = {"kind": "city_q", "at": ctx["now"].isoformat(), "nonce": nonce, "city": new_city}


async def web_park(account: str, history: list, now) -> Optional[str]:
    """The web chat and the avatar: "not ready to book that yet" saves the LAST search asked for (its words, re-read)."""
    from . import handoff as HO
    for h in reversed(history or []):
        if h.get("role") != "user":
            continue
        hf = HO.booking_handoff(str(h.get("content") or ""), [], now)
        f = (hf or {}).get("booking_find")
        if f and f.get("where"):
            g, gp = dict(f), dict(((hf.get("reservation_draft") or {}).get("parts") or {}))
            await _ordinal_day({"account": account, "now": now}, g, gp, str(h.get("content") or ""))
            at = g.get("open_at") or gp.get("day")
            name = f"{g['what']} in {g['where']}"
            if not await save_item(account, f"{name} (saved)", at, g["where"]):
                return "I couldn't save it just now — nothing was booked."
            return f"Saved, not booked: {name} — it's in your {await tab_of(account, g['where'], at)} tab and in Requests."
    return None


async def web_start(account: str, rest: str, now) -> tuple:
    """The web chat and the avatar: "let me start another: …" → (the sentence, a booking_find for ONE request or None)."""
    from . import handoff as HO
    parts = [x.strip(" .") for x in re.split(r",|;|\s+and\s+(?=(?:an?|some|the)\s)", rest or "") if x.strip(" .")]
    hs = [(p, HO.booking_handoff(p, [], now)) for p in parts]
    hs = [(p, h) for p, h in hs if (h or {}).get("booking_find", {}).get("where")]
    if len(hs) == 1:
        return hs[0][1]["response"], hs[0][1]
    if not hs:
        return None, None
    lines = []
    for p, h in hs:
        g, gp = dict(h["booking_find"]), dict(((h.get("reservation_draft") or {}).get("parts") or {}))
        await _ordinal_day({"account": account, "now": now}, g, gp, p)
        at = g.get("open_at") or gp.get("day")
        await save_item(account, f"{g['what']} in {g['where']} (saved)", at, g["where"])
        lines.append(f"• {g['what']} in {g['where']}{(' — ' + SN_day(at)) if at else ''} → {await tab_of(account, g['where'], at)}")
    return "Started, both saved (nothing booked yet):\n" + "\n".join(lines), None


def JN_label(p: dict) -> str:
    from . import journeys as JN
    return JN.label(p)


def JN_fold(s: str) -> str:
    from . import journeys as JN
    return JN._fold(s)


def SN_day(at: str) -> str:
    from . import sentences as SN
    return SN.day_words(at[:10]) + (f" at {at[11:16]}" if "T" in at else "")


async def city_answer(ctx: dict, pend: dict, body: str, payload: str) -> bool:
    n = pend["nonce"]
    one = payload == f"oneoff:{n}" or (not payload and re.search(r"\bone[- ]?off|\bjust\b|\bno\b", body or "", re.I))
    trip = payload == f"tripq:{n}" or (not payload and re.search(r"\b(?:part of|trip|yes)\b", body or "", re.I))
    if not (one or trip):
        return False
    ctx["st"]["pending"] = None
    ctx["st"].setdefault("city_asked", {})[JN_fold(pend["city"])] = "oneoff" if one else "trip"   # asked once
    ctx["out"].text(f"OK — a one-off: it goes in a new 📍 {pend['city']} tab." if one else
                    f"OK — when you're ready, say “plan me 3 days in {pend['city']}” and I'll build the trip and file this in it. "
                    f"Until then it's in a 📍 {pend['city']} tab.")
    then = pend.get("then")
    if then:   # Sasha 179 (2) · then straight into the search it was asked for — the CURRENT request (a later "not ready" saves this one)
        await gate(ctx, then["f"], then["gp"], then["part"])
    return True


__all__ = ["placeless", "context", "search", "answer", "add_to_trip", "web_turn", "ask_contact", "reset_demo", "start_reset",
           "is_test", "RESET", "wa_markdown", "chunks", "sasha_clear", "gate", "hour_said"]
