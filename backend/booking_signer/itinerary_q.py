"""Sasha 132 · ASK YOUR ITINERARY — on WhatsApp and the web, deterministic (no model): the answer comes from the guest's
own bookings, Google's Routes API (driving) and Duffel's TEST schedules (flying). Nothing is guessed: when the bookings
don't say where they'll be, the answer says so.

  "where am I on the 5th?" · "what do I have tomorrow?"
  "do I have time to drive to Toledo between 13:00 and 18:00 on the 5th?"
  "do I have time to fly to Lisbon between 9 and 14 on 12 November?"
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import List, Optional, Tuple
from zoneinfo import ZoneInfo

from . import handoff as HO, sentences as SN

_ORD = re.compile(r"\bthe\s+(\d{1,2})(?:st|nd|rd|th)\b", re.I)
_TIME = re.compile(r"\b(\d{1,2})(?:[:.h](\d{2}))?\s*(am|pm)?\b", re.I)
_BETWEEN = re.compile(r"\bbetween\s+(?P<a>[0-9:.h apm]+?)\s+and\s+(?P<b>[0-9:.h apm]+?)(?=\s|$|[,.?!])", re.I)
_TO = re.compile(r"\b(?:drive|fly|go|get)\b.*?\bto\s+(?P<x>[A-ZÁÉÍÓÚ][\wáéíóúñ .'-]*?)(?=\s+(?:between|and|on|by|from)\b|[,.?!]|$)")
_FROM = re.compile(r"\bfrom\s+(?P<x>[A-ZÁÉÍÓÚ][\wáéíóúñ .'-]*?)(?=\s+(?:between|and|on|to)\b|[,.?!]|$)")


_COUNTRY = {"ES": "Spain", "PT": "Portugal", "FR": "France", "IT": "Italy", "DE": "Germany", "AT": "Austria", "GB": "United Kingdom",
            "IE": "Ireland", "VN": "Vietnam", "KE": "Kenya"}


def qualified(place: str, hint: Optional[str] = None) -> str:
    """'Toledo' alone is Ohio to Google: a bare name gets its country — its own if known, else the other end's (Spain by
    default). An address with a comma is used as said."""
    if "," in place:
        return place
    kp = HO.known_place(place)
    cc = (kp[2] if kp else None) or hint or "ES"
    city = f"{kp[0]}, {kp[1]}" if kp and kp[1] else place
    return f"{city}, {_COUNTRY.get(cc, cc)}"


def day_of(text: str, now: datetime) -> Optional[date]:
    d = HO.plain_date(text or "", now)
    if d:
        return date.fromisoformat(d)
    m = _ORD.search(text or "")
    if m:
        today = now.astimezone(ZoneInfo("Europe/Madrid")).date()
        day = int(m[1])
        y, mo = today.year, today.month
        if day < today.day:   # "the 5th" said on the 20th is next month's
            y, mo = (y + 1, 1) if mo == 12 else (y, mo + 1)
        try:
            return date(y, mo, day)
        except ValueError:
            return None
    return None


def _hm(s: str) -> Optional[Tuple[int, int]]:
    m = _TIME.search(s or "")
    if not m:
        return None
    h, mi = int(m[1]), int(m[2] or 0)
    if m[3] and m[3].lower() == "pm" and h < 12:
        h += 12
    return (h, mi) if 0 <= h < 24 and 0 <= mi < 60 else None


def _start(r: dict) -> Optional[datetime]:
    if not r.get("date"):
        return None
    tz = ZoneInfo(r.get("timezone") or "Europe/Madrid")
    return datetime.fromisoformat(f"{r['date']}T{r.get('time') or '00:00'}").replace(tzinfo=tz)


def _what(r: dict) -> str:
    t = r.get("time") or ""
    if r.get("type") == "flight":
        return f"{t} {r.get('venue')}"
    # Sasha 157 · its state, in the venue's own terms: a request is never shown as if it were booked
    state = f" — {r['status_words']}" if r.get("status_words") and r.get("status") not in ("guest_booked",) else ""
    return f"{t} {r.get('venue')}" + (f", {r.get('party')} people" if r.get("party") else "") + state


async def _rows(account: str) -> List[dict]:
    from . import guest_whatsapp as GW
    status, j = await GW.api(account, "GET", "/api/booking/reservations")
    if status != 200:
        return []
    from . import plan_store as PS
    return PS.truthful([r for r in j.get("reservations") or [] if r.get("status") not in ("cancelled", "failed")])   # Sasha 157 · declined is shown, said so


def where_on(rows: List[dict], d: date) -> List[str]:
    """What's booked that day, and — from the flights — where they'll be. Never guessed."""
    on = sorted([r for r in rows if r.get("date") == d.isoformat()], key=lambda r: r.get("time") or "")
    flights = sorted([r for r in rows if r.get("type") == "flight" and _start(r)], key=_start)
    before = [f for f in flights if _start(f).date() <= d]
    where = None
    if before:
        f = before[-1]
        city = (f.get("venue") or "").split("→")[-1].replace("(TEST booking)", "").strip()
        where = (f"You fly to {city} that day ({f.get('location') or ''}, departing {f.get('time')} local)." if _start(f).date() == d
                 else f"Your last flight before then goes to {city} — that's where your bookings put you.")
    lines = [f"{SN.day_words(d.isoformat())}:"]
    lines += [f"• {_what(r)}" for r in on] or ["• Nothing booked that day."]
    lines.append(where or "Your bookings don't say where you'll be that day (no flight or hotel in them).")
    return lines


async def time_for(account: str, text: str, rows: List[dict], now: datetime) -> List[str]:
    """'do I have time to drive/fly to X between Y and Z' — Routes API for driving, Duffel TEST schedules for flying."""
    from . import proactive as PR, travel as TR
    tx, bw = _TO.search(text or ""), _BETWEEN.search(text or "")
    if not tx or not bw:
        return ["Ask it like: “do I have time to drive to Toledo between 13:00 and 18:00 on the 5th?”"]
    a, b = _hm(bw["a"]), _hm(bw["b"])
    d = day_of(text, now) or now.astimezone(ZoneInfo("Europe/Madrid")).date()
    if not a or not b:
        return ["I need both times, e.g. “between 13:00 and 18:00”."]
    tz = ZoneInfo("Europe/Madrid")
    start, end = datetime(d.year, d.month, d.day, *a, tzinfo=tz), datetime(d.year, d.month, d.day, *b, tzinfo=tz)
    window = int((end - start).total_seconds() // 60)
    clash = [r for r in rows if r.get("date") == d.isoformat() and r.get("time") and a <= tuple(int(x) for x in r["time"].split(":")) < b]
    note = [f"Note: you have {_what(clash[0])} in that window."] if clash else []
    dest = tx["x"].strip()
    if re.search(r"\bfly\b", text or "", re.I):
        fm = _FROM.search(text or "")
        origin = fm["x"].strip() if fm else None
        if not origin:
            return ["From where? e.g. “… fly from Madrid to Lisbon between 9 and 14 on 12 November”."]
        got = await TR.search(origin, dest, d.isoformat(), 1, limit=50)   # the whole schedule, not only the cheapest
        if "why" in got:
            return [f"I can't check flights right now — {got['why']}."]
        fits = []
        for c in got.get("cards") or []:
            dep, arr = datetime.fromisoformat(c["departs"]), datetime.fromisoformat(c["arrives"])
            if (dep.hour, dep.minute) >= a and arr.date() == d and (arr.hour, arr.minute) <= b:
                fits.append(c)
        if not fits:
            return [f"No flight from {origin} to {dest} leaves after {bw['a'].strip()} and lands by {bw['b'].strip()} on "
                    f"{SN.day_words(d.isoformat())} (Duffel's TEST schedules)."] + note
        best = min(fits, key=lambda c: datetime.fromisoformat(c["arrives"]))
        return [f"Yes — {TR.card_line(best)}, within your {window // 60}h {window % 60:02d}m window (Duffel TEST schedules"
                f"{f'; {len(fits)} flights fit' if len(fits) > 1 else ''})."] + note
    fm = _FROM.search(text or "")
    origin = fm["x"].strip() if fm else None   # "… drive from Madrid to Toledo …": said, it wins
    prior = [r for r in rows if r.get("date") == d.isoformat() and r.get("time") and tuple(int(x) for x in r["time"].split(":")) <= a]
    if not origin and prior and (prior[-1].get("address") or prior[-1].get("location")):
        origin = prior[-1].get("address") or prior[-1].get("location")
    if not origin and PR.STORE is not None:
        place = await PR.STORE.default_place(account)
        origin = (place or {}).get("address")
    if not origin:
        return ["From where? Save a starting point in You → WhatsApp, or say “from …”."]
    hint = (HO.known_place(origin) or (None, None, None))[2] if "," not in origin else None
    secs = await PR.travel(qualified(origin, hint), qualified(dest, hint), start, "DRIVE")
    if secs is None:
        return [f"The Routes API couldn't give a driving time to {dest}."]
    mins = secs // 60
    there_back = 2 * mins
    verdict = (f"Yes: {mins // 60}h {mins % 60:02d}m each way by car (Routes API, leaving {bw['a'].strip()}), "
               f"so {window - there_back} min there after the round trip." if there_back < window else
               f"Not really: {mins // 60}h {mins % 60:02d}m each way by car (Routes API) — {there_back} min of driving in a {window}-min window.")
    return [verdict] + note


WEEK = re.compile(r"\bwhat do i (?:need|have) to do (?:this|next) week\b|\bwhat(?:'s| is) (?:on )?(?:for )?(?:this|next) week\b"
                  r"|\bmy week\b|\bwhat do i have (?:this|next) week\b", re.I)
#: Sasha 165 · the whole trip: the plan (the builder's, now on the account) with every booking slotted into its day
#: Sasha 178 · ASK SASHA ANYTHING over the one record (web, avatar and WhatsApp): a reservation by its venue, a trip's day,
#: the relocation package
ASK_WHEN = re.compile(r"\bwhen(?:'s| is| was)? (?:my |the )?(?:reservation|booking|table|appointment|dinner|lunch)\s+(?:at|with|for|in)\s+(?P<v>.+?)\s*\??$", re.I)
ASK_DAY = re.compile(r"\bwhat(?:'s| is| do i have)? (?:on|in) my (?P<t>[\w ]+?) (?:trip|journey|tour)?\s*on the (?P<d>\d{1,2}(?:st|nd|rd|th)|[a-z]+(?:st|nd|rd|th))\b", re.I)
ASK_PACKAGE = re.compile(r"\b(?:what(?:'s| is)? (?:missing|left|still to do)|what do i still need)\b.*\b(?:relocation|move|package|file|forms?)\b|"
                         r"\b(?:relocation|move) (?:package|file|forms?) status\b", re.I)
#: Sasha 177 · the journeys on WhatsApp: "show me my trips", "my requests", "my receipts", "my move to Madrid", "my campus tour"
TRIPS = re.compile(r"\b(?:show (?:me )?|what are |list )?my (?:trips|journeys)\b|\bmy (?:requests|receipts)\b", re.I)
TRIP = re.compile(r"\bshow (?:me )?my (?:\w+ )?(?:itinerary|trip|plan)\b|\bwhat does my (?:\w+ )?trip look like\b|"
                  r"\b(?:show (?:me )?)?my (?:move to \w+|campus tour|\w+ trip)\b|"
                  r"^\s*(?:my )?(?:\w+ )?itinerary\s*[?.!]*\s*$|\bwhat was i doing\b|^\s*carry on\s*[.!]*\s*$", re.I)
QUESTION = re.compile(TRIPS.pattern + "|" + ASK_WHEN.pattern + "|" + ASK_DAY.pattern + "|" + ASK_PACKAGE.pattern + "|" + TRIP.pattern + r"|\bwhere (?:am i|are we|will i be)\b|\bdo i have time\b|\bwhat(?:'s| is) (?:on )?my (?:itinerary|plan|schedule)\b"
                      r"|\bwhat do i have (?:on|tomorrow|today|this)\b|\bwhere do i (?:sleep|stay)\b|" + WEEK.pattern, re.I)


async def ask_anything(account: str, text: str, rows: List[dict], now: datetime) -> Optional[List[str]]:
    """Sasha 178 · answers that cite the item and its tab. None: not one of these questions."""
    from . import journeys as JN
    t = text or ""
    m = ASK_WHEN.search(t)
    if m:
        want = {w for w in re.findall(r"[a-z0-9]+", JN._fold(m["v"])) if len(w) > 2 and w not in ("the", "restaurant", "spa")}
        hits = [r for r in rows if r.get("status") not in ("cancelled", "failed") and want and want <= set(re.findall(r"[a-z0-9]+", JN._fold(r.get("venue") or "")))]
        if not hits:
            hits = [r for r in rows if r.get("status") not in ("cancelled", "failed") and want and want & set(re.findall(r"[a-z0-9]+", JN._fold(r.get("venue") or "")))]
        if not hits:
            return [f"I don't see a booking at {m['v'].strip(' ?')} on your account."]
        j = await JN.journeys(account, rows)
        out = []
        for r in hits[:3]:
            tab = next((x["label"] for x in j["journeys"] if str(r.get("trip_id")) == x["key"]), None) or j["home"]["label"]
            when = f"{SN.day_words(r['date'])}{' at ' + r['time'] if r.get('time') else ''}" if r.get("date") else "no day set yet"
            from . import plan_store as PS
            out.append(f"{str(r.get('venue') or '').replace(' (TEST stand-in)', '')}: {when} — {PS.short_status(r)}"
                       f"{' · ref ' + r['booking_reference'] if r.get('booking_reference') and r['booking_reference'] not in PS.short_status(r) else ''} (in your {tab} tab)")
        return out
    m = ASK_DAY.search(t)
    if m:
        from . import plan_store as PS, wa_brain as WB
        p = await PS.latest(account, m["t"])
        if not p:
            return [f"There's no {m['t']} trip on your account."]
        dd = WB.ordinals_as_digits(f"the {m['d']}")
        n = int(re.search(r"\d+", dd)[0])
        cands = [p] + [q for q in await PS.plans(account) if q.get("trip_id") != p.get("trip_id")
                       and JN._fold(m["t"].strip()) in JN._fold(q.get("title") or "")]
        plan, day = None, None
        for c in cands:   # Sasha 179 (1) · two plans share the word: the one that HAS that day (never an undated stub's "no 16th")
            full = c if c.get("days") is not None else (await PS.by_id(account, c["trip_id"]) or {})
            if not full:
                continue
            plan = PS.merge(full, JN.for_journey(rows, full.get("trip_id")))
            day = next((d for d in plan.get("days") or [] if d.get("date") and int(d["date"][8:10]) == n), None)
            if day:
                p = full
                break
        if not day:
            return [f"Your {JN.label(p)} trip has no {m['d']} in it."]
        lines = [f"{JN.label(p)} · Day {day.get('day')} · {SN.day_words(day['date'])} — {day.get('city')}:"]
        for b in sorted(day.get("bookings") or [], key=lambda x: x.get("time") or ""):
            lines.append(f"• {b.get('time') or ''} {str(b.get('venue') or '').replace(' (TEST stand-in)', '')}: {PS.short_status(b)}".replace("•  ", "• "))
        for a in [a for a in day.get("activities") or [] if not a.get("replaced_by")][:3]:
            lines.append(f"· {a.get('time')}: {a.get('name')}")
        return ["\n".join(lines)]
    if ASK_PACKAGE.search(t):
        try:
            from products.relocation import package_status
        except ImportError:
            return ["I can't read your relocation file just now."]
        ps = await package_status(account)
        if not ps:
            return ["You don't have a relocation file yet — say “relocate” to start."]
        icon = {"filled": "✏️ filled", "signed": "✅ signed", "missing": "❗ missing", "waiting": "⏳ waiting"}
        lines = [f"🏠 Your relocation package (in your {ps.get('tab') or 'Move to Madrid'} tab):"]
        for fm in ps.get("forms") or []:
            lines.append(f"• {fm.get('name')}: {icon.get(fm.get('state'), fm.get('state'))}{' — ' + fm['note'] if fm.get('note') else ''}")
        nd = ps.get("next_deadline")
        if nd:
            lines.append(f"Next deadline: {SN.day_words(nd['on'])} — {nd.get('text')}")
        return ["\n".join(lines)]
    return None


def _line(r: dict) -> str:
    when = f"{SN.day_words(r['date'])}{' at ' + r['time'] if r.get('time') else ''}" if r.get("date") else "no day yet"
    return f"• {when} — {str(r.get('venue') or '').replace(' (TEST stand-in)', '')}: {r.get('status_words') or r.get('status')}"


def trips_text(j: dict, text: str) -> List[str]:
    """Sasha 177 · "show me my trips" → one line per tab; "my requests" / "my receipts" → that list."""
    if re.search(r"\brequests\b", text or "", re.I):
        rq = j["requests"]
        return ["⏳ Waiting on a reply:\n" + "\n".join(_line(r) for r in rq[:12])] if rq else ["Nothing is waiting on a reply."]
    if re.search(r"\breceipts\b", text or "", re.I):
        rc = j["receipts"]
        return ["🧾 Booked:\n" + "\n".join(_line(r) for r in rc[:15])] if rc else ["No bookings with receipts yet."]
    if not j["journeys"] and not j["home"]["items"]:   # Sasha 181 · after "reset the demo"
        return ["No tabs — ready from zero." + (f" {len(j['receipts'])} real booking{'s' if len(j['receipts']) != 1 else ''} in Receipts "
                                               "(say “my receipts”)." if j["receipts"] else "")]
    lines = ["🗂 Your trips:"]
    for t in j["journeys"]:
        dates = f" ({SN.day_words(t['start'])} – {SN.day_words(t['end'])})" if t.get("start") and t.get("end") else ""
        lines.append(f"• {t['label']}{dates} — {t['count']} booking{'s' if t['count'] != 1 else ''}")
    if j["home"]["items"]:
        lines.append(f"• {j['home']['label']} — {len(j['home']['items'])} outside any trip")
    lines.append(f"• Requests — {len(j['requests'])} waiting on a reply")
    # Sasha 179 (1) · the hint names only tabs that exist
    names = list(dict.fromkeys(re.sub(r",.*$", "", re.sub(r"^\W+\s*", "", t["label"])) for t in j["journeys"]))[:2]
    say = [f"“my {n} trip”" if not re.match(r"(?i)move to|campus|españa|health", n) else f"“my {n.lower()}”" for n in names]
    lines.append(f"Say {', '.join(say + ['“my requests”'])} for one of them." if say else "Say “my requests” to see what's waiting on a reply.")
    return ["\n".join(lines)]


async def week(account: str, text: str, rows: List[dict], now: datetime) -> List[str]:
    """CR 13 · "what do I need to do this week?" — Sasha's bookings AND the products' dated deadlines (products.agenda, read-only),
    in one list by day, each product item with its source. Next week = next Monday to Sunday."""
    today = now.astimezone(ZoneInfo("Europe/Madrid")).date()
    if re.search(r"\bnext week\b", text or "", re.I):
        start = today + timedelta(days=7 - today.weekday())
        end, label = start + timedelta(days=6), "Next week"
    else:
        start, end, label = today, today + timedelta(days=6 - today.weekday()), "This week"
    items: List[Tuple[str, str, str]] = []
    for r in rows:
        if r.get("date") and start.isoformat() <= r["date"] <= end.isoformat():
            items.append((r["date"], r.get("time") or "", f"{_what(r)}" + (" — TEST" if (r.get("booking_reference") or "").startswith("TEST-") else "")))
    try:
        from products.agenda import agenda
        for a in await agenda(account, start, end):
            if a.get("kind") == "visit" and any("campus visit" in (r.get("venue") or "") and r.get("date") == a["on"] for r in rows):
                continue   # the same visit is already a booking
            items.append((a["on"], a.get("time") or "", f"{(a.get('time') + ' ') if a.get('time') else ''}{a['text']} ({a['product']}; source: {a['source']})"))
    except Exception as e:   # the products' list missing never hides the bookings — and is said
        items.append((end.isoformat(), "99", f"(Your paperwork deadlines couldn't be read just now: {type(e).__name__}.)"))
    if not items:
        return [f"{label}: nothing booked and nothing due."]
    out, day = [f"{label}:"], None
    for d, t, line in sorted(items):
        if d != day:
            out.append(f"{SN.day_words(d)}:")
            day = d
        out.append(f"• {line}")
    return out


async def web_turn(message: str, user_id: Optional[str], history: list) -> Optional[dict]:
    """The web chat's turn for an itinerary question (conductor, before any model): the same answer as on WhatsApp."""
    if not QUESTION.search(message or ""):
        return None
    from datetime import timezone
    if not user_id:
        lines = ["Sign in, and I'll answer from your own bookings."]
    else:
        try:
            lines = await answer(str(user_id), message, datetime.now(timezone.utc))
        except Exception as e:   # never a model's guess instead: say it couldn't be read
            lines = [f"I couldn't read your bookings just now ({type(e).__name__})."]
    response = "\n".join(lines)
    return {"response": response, "intents": ["itinerary"], "photos": [], "tools_used": [], "links": [], "hotels": [], "bookings": [],
            "itinerary": None, "action": None, "booking_ref": None, "itinerary_id": None, "payment_item": None, "saved_card": None,
            "messages": list(history or []) + [{"role": "user", "content": message}, {"role": "assistant", "content": response}]}


async def answer(account: str, text: str, now: datetime) -> List[str]:
    from . import journeys as JN, paid_watch as PWT
    await PWT.sweep(account)   # Sasha 183 · a payment waiting is booked before anything is shown
    await JN.file(account)   # Sasha 177 · each booking in its journey before anything is shown
    rows = await _rows(account)
    if TRIPS.search(text or ""):
        return trips_text(await JN.journeys(account, rows), text)
    asked = await ask_anything(account, text, rows, now)
    if asked:
        return asked
    m = re.search(r"\bmy (move to \w+|campus (?:tour|visits))\b", text or "", re.I)
    if m:   # Sasha 177 · a product's journey on WhatsApp: its items (and its bookings), each with its source
        j = await JN.journeys(account, rows)
        t = next((x for x in j["journeys"] if m[1].split()[0].lower() in x["label"].lower()), None)
        if t and (t.get("virtual") or not t.get("start")):
            items = t.get("extras") or []
            return [f"🗂 {t['label']}:\n" + ("\n".join(_line(r) for r in items[:20]) if items else "Nothing dated yet.")]
        if not t:   # never another journey in its place (it showed the campus tour)
            what = m[1].lower()
            return [f"There's no {'move' if what.startswith('move') else 'campus'} journey on your account yet — "
                    + ("RelocateMe starts it: say “relocation”." if what.startswith("move") else "CampusMe starts it: say “campus”.")]
    if TRIP.search(text or ""):   # Sasha 165 · the plan + the bookings, day by day — when there is a plan
        from . import plan_store as PS
        p = await PS.latest(account, text)
        if p:
            return PS.text(PS.merge(p, JN.for_journey(rows, p.get("trip_id"))))   # its OWN bookings only
    if WEEK.search(text or ""):
        return await week(account, text, rows, now)
    if re.search(r"\bdo i have time\b", text or "", re.I):
        return await time_for(account, text, rows, now)
    d = day_of(text, now)
    if d is None:
        if re.search(r"\btomorrow\b", text or "", re.I):
            d = now.astimezone(ZoneInfo("Europe/Madrid")).date() + timedelta(days=1)
        else:
            d = now.astimezone(ZoneInfo("Europe/Madrid")).date()
    return where_on(rows, d)


__all__ = ["answer", "where_on", "time_for", "day_of", "web_turn", "QUESTION"]
