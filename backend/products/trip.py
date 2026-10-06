"""CR 13 · the products and Sasha's travel, acting together: "book my flights" inside a relocation, "plan the trip around
the visits" inside CampusMe → ONE plan, in order, each booking done by SASHA'S OWN travel flow (the Sasha tab owns it):

  relocation: ✈ flights from the origin (asked once) to the new town on the entry date → 🏨 a hotel for the first nights
              near the new address → 📋 one itinerary: the bookings, the consulate appointment, every document deadline;
  campus:     ✈ flights into the first visit's city the day before → 🏨 a hotel near campus the night before each visit,
              with the drive between campuses checked for time (Google Routes, through Sasha's proactive.travel —
              never a second routing client; rail is NOT checked: no timetable has been read at source) → 📋 one itinerary.

How a booking happens: this skill hands Sasha a plain SENTENCE her own intents parse ("flights from London to Madrid on
2027-03-01 for 1", "a hotel in …, Spain from … to … for 1") — the hand-off line in guest_whatsapp.turn() marked "CR 13
products". Her flow then asks its one yes per booking, with its TEST labels, exactly as if the person had typed it.
Nothing is booked here. "Next" (or the button) moves to the following step.
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime, timedelta
from typing import List, Optional
from zoneinfo import ZoneInfo

from . import store as ST

log = logging.getLogger("products.trip")
FIRST_NIGHTS = 3          # relocation: "a hotel for the first nights" — said to the person, changeable by "for N nights"
SLACK_MIN = 30            # campus: a drive is feasible with at least this much time to spare before the next visit

TRIGGER = re.compile(r"(?i)\b(book|find|get|sort(?: out)?|search|organi[sz]e)\b[\w\s']{0,20}\b(flights?|trip|travel)\b|"
                     r"\bplan\b[\w\s']{0,25}\b(trip|travel|move|journey|visits?)\b")
_NEXT = re.compile(r"(?i)^\s*(next|continue|go on|carry on|ok,? next|the hotel|hotel next|siguiente)\b")
_CAMPUS_WORDS = re.compile(r"(?i)\b(visits?|campus|college|universit|tour)")


def wants_plan(body: str) -> bool:
    """A trip request without its own from/to (a complete "flights from X to Y on …" is Sasha's, as typed)."""
    from booking_signer import guest_whatsapp as GW
    return bool(TRIGGER.search(body or "")) and not GW.FLIGHT.search(body or "") and not GW.HOTEL.search(body or "")


async def which(account: str, body: str, asked_last: Optional[str], waiting: List[str]) -> Optional[str]:
    """Which product the plan is for: the one named, the one asked last, the one set aside most recently — and only if
    the account has something to plan from (a relocation file with a consulate, or a campus visit)."""
    have = {"relocation": bool(await _relocation(account)), "campus": bool(await _visits(account))}
    order = (["campus"] if _CAMPUS_WORDS.search(body or "") else []) + \
        ([asked_last] if asked_last in have else []) + [w for w in waiting if w in have] + ["relocation", "campus"]
    return next((p for p in order if have.get(p)), None)


async def _relocation(account: str) -> Optional[dict]:
    rows = [c for c in await ST.STORE.of_account(account, "relocation")
            if c["state"].get("kind") != "conversation" and not c["state"].get("showcase") and c["state"].get("facts")]
    return rows[0] if rows else None     # newest first


async def _visits(account: str) -> List[dict]:
    from .campus import schools as SC
    out, today = [], date.today().isoformat()
    for c in await ST.STORE.of_account(account, "campus"):
        st = c["state"]
        x = st.get("session") or {}
        s = SC.SCHOOLS.get(st.get("school") or "")
        if st.get("kind") == "conversation" or st.get("showcase") or not s or not x.get("day") or x["day"] < today:
            continue
        if st.get("status") not in ("handed_over", "registered_on_your_word", "confirmed_in_writing"):
            continue
        party = 1 + int((st.get("ask") or {}).get("guests", 1))
        out.append({"school": s["key"], "name": s["name"], "full_name": s["full_name"], "city": s["city"], "tz": s["tz"],
                    "day": x["day"], "start": x["start"], "end": x.get("end"), "location": x.get("location"),
                    "title": x.get("title"), "status": st.get("status"), "party": party})
    out.sort(key=lambda v: (v["day"], v["start"]))
    return out


def _fact(f: dict, k: str) -> str:
    return ((f.get("applicant") or {}).get(k) or {}).get("value") or ""


def _day(iso: str) -> str:
    return date.fromisoformat(iso).strftime("%a %-d %b %Y")


def _city(c: str) -> str:
    """'New Haven, CT' → 'New Haven' (Duffel resolves the airport for the city)."""
    return c.split(",")[0].strip()


def _hm(seconds: int) -> str:
    h, m = divmod(round(seconds / 60), 60)
    return f"{h} h {m:02d}" if h else f"{m} min"


async def legs(visits: List[dict]) -> List[dict]:
    """Each consecutive pair of visits: leave when the first ends, drive (Google Routes via Sasha's proactive.travel), arrive
    before the next starts with SLACK_MIN to spare? Feasible only on a real answer — never a straight-line guess."""
    from booking_signer import proactive as PR
    from .campus import visits as VS
    out = []
    for a, b in zip(visits, visits[1:]):
        if a["school"] == b["school"]:
            continue
        tz = ZoneInfo(a["tz"])
        start = datetime.combine(date.fromisoformat(a["day"]), datetime.strptime(a["start"], "%H:%M").time(), tzinfo=tz)
        leave = start + timedelta(minutes=VS._minutes({"start": a["start"], "end": a.get("end")}))
        arrive_by = datetime.combine(date.fromisoformat(b["day"]), datetime.strptime(b["start"], "%H:%M").time(),
                                     tzinfo=ZoneInfo(b["tz"]))
        o = f"{a['location'] + ', ' if a.get('location') else ''}{a['full_name']}, {a['city']}, United States"
        d = f"{b['location'] + ', ' if b.get('location') else ''}{b['full_name']}, {b['city']}, United States"
        try:
            secs = await PR.travel(o, d, leave, "DRIVE")
        except Exception as e:
            log.error("[trip] drive time failed: %s: %s", type(e).__name__, e)
            secs = None
        leg = {"from": a["name"], "to": b["name"], "leave": leave.isoformat(), "arrive_by": arrive_by.isoformat(),
               "seconds": secs, "source": "Google Routes (driving, traffic-aware)"}
        head = (f"{a['name']} {date.fromisoformat(a['day']).strftime('%a')} {a['start']} → "
                f"{b['name']} {date.fromisoformat(b['day']).strftime('%a')} {b['start']}")
        if secs is None:
            leg.update(ok=None, line=f"{head}: drive time unavailable — Google Routes didn't answer, so I won't guess.")
        else:
            spare = (arrive_by - (leave + timedelta(seconds=secs))).total_seconds() / 60
            ok = spare >= SLACK_MIN
            leg.update(ok=ok, spare_min=round(spare),
                       line=f"{head}: {'yes' if ok else 'NO'}, {_hm(secs)} by car (leaving {leave.strftime('%-d %b %H:%M')}, "
                            f"after the visit)" + ("" if ok else f" — you'd arrive {abs(round(spare))} min "
                                                   f"{'late' if spare < 0 else 'with under ' + str(SLACK_MIN) + ' min to spare'}"))
        out.append(leg)
    return out


def _steps_relocation(case: dict, origin: str, party: int, nights: int) -> List[dict]:
    st = case["state"]
    f, after = st.get("facts") or {}, st.get("after") or {}
    entry = after.get("entry_date")
    town = _fact(f, "address_town") or "Madrid"
    street = " ".join(x for x in (_fact(f, "address_street"), _fact(f, "address_number")) if x)
    near = f"{street}, {town}" if street else town
    out_d = (date.fromisoformat(entry) + timedelta(days=nights)).isoformat()
    return [
        {"what": "flight", "say": f"✈ Flights {origin} → {town}, {_day(entry)} (your entry date), {party} adult{'s' if party > 1 else ''}",
         "sentence": f"flights from {origin} to {town} on {entry} for {party}"},
        {"what": "hotel", "say": f"🏨 A hotel near your new address ({near}) for your first {nights} nights, {_day(entry)} → {_day(out_d)}",
         "sentence": f"a hotel in {town}, Spain from {entry} to {out_d} for {party}", "near": near},
    ]


def _steps_campus(visits: List[dict], origin: str, legs_: List[dict]) -> List[dict]:
    party = max(v["party"] for v in visits)
    first = visits[0]
    arrive = (date.fromisoformat(first["day"]) - timedelta(days=1)).isoformat()
    steps = [{"what": "flight", "say": f"✈ Flights {origin} → {_city(first['city'])}, {_day(arrive)} (the day before {first['name']}), "
              f"{party} adult{'s' if party > 1 else ''} — into the airport Duffel finds for {_city(first['city'])}",
              "sentence": f"flights from {origin} to {_city(first['city'])} on {arrive} for {party}"}]
    by_leg = {l["to"]: l for l in legs_}
    seen = set()
    for v in visits:
        night = (date.fromisoformat(v["day"]) - timedelta(days=1)).isoformat()
        if (v["school"], night) in seen:
            continue
        seen.add((v["school"], night))
        if v["name"] in by_leg:
            steps.append({"what": "leg", "say": "🚗 " + by_leg[v["name"]]["line"]})
        steps.append({"what": "hotel", "say": f"🏨 A hotel near {v['full_name']}, the night before the visit ({_day(night)})",
                      "sentence": f"a hotel in {_city(v['city'])}, United States from {night} to {v['day']} for {party}",
                      "near": f"{v['full_name']}, {v['city']}"})
    return steps


async def turn(ctx: dict, body: str, payload: str, *, entering: bool) -> Optional[bool]:
    """The plan's own steps. ctx["handoff"] = a sentence → the router hands it to Sasha's flow (returns False there)."""
    pend, out = ctx["st"]["pending"], ctx["out"]
    from booking_signer import handoff as HO
    if entering or pend.get("step") is None:
        pend["for"] = pend.get("for") or ctx.get("plan_for")
        if pend["for"] == "relocation":
            case = await _relocation(ctx["account"])
            after = (case or {}).get("state", {}).get("after") or {}
            if not case or not after:
                out.text("Your relocation file isn't at the travel stage yet — once it's signed and I know your consulate, "
                         "I'll plan the flights and the first nights around your entry date.")
                pend["step"] = "done"
                return True
            pend["case_id"] = case["id"]
            if not after.get("entry_date"):
                pend["step"] = "entry"
                out.text("When do you plan to enter Spain? (a date, e.g. 1 March 2027) — I plan the flights around it.")
                return True
        else:
            vs = await _visits(ctx["account"])
            if not vs:
                out.text("No campus visit prepared or registered yet — choose one first (say “campus …”), then I'll plan the trip around it.")
                pend["step"] = "done"
                return True
        return await _ask_origin(ctx, pend, out)
    step = pend.get("step")
    if step == "entry":
        from .relocation import facts as F
        d = F.parse_date(body)
        if not d or d <= ctx["now"].date().isoformat():
            out.text("A future date please, like 1 March 2027.")
            return True
        case = await ST.STORE.get(pend["case_id"])
        if case:
            case["state"].setdefault("after", {})["entry_date"] = d
            await ST.STORE.update(case["id"], case["state"])
        return await _ask_origin(ctx, pend, out)
    if step == "origin":
        m = re.match(r"(?i)^\s*(?:from\s+)?([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ .'-]{1,40}?)(?:\s*,.*|\s+for\s+.*)?\s*$", body or "")
        if not m or re.search(r"\d", m.group(1)):
            out.text("The city you'll fly from, please — e.g. London (add “for 2” if others fly with you).")
            return True
        pend["origin"] = m.group(1).strip().title()
        pend["party"] = HO.plain_party(body) or None
        return await _plan(ctx, pend, out)
    if step == "handed" and (payload == "tp:next" or _NEXT.match(body or "")):
        return await _next(ctx, pend, out)
    if step == "handed" and (payload == "tp:stop" or re.match(r"(?i)^\s*stop (the )?plan\b", body or "")):
        out.text("OK — the plan stops here. What's booked stays booked.")
        pend["step"] = "done"
        return True
    return False   # not the plan's: Sasha's own flow answers


async def _ask_origin(ctx, pend, out) -> bool:
    pend["step"] = "origin"
    out.text("Which city will you fly from? (asked once — e.g. London; add “for 2” if others fly with you)")
    return True


async def _plan(ctx, pend, out) -> bool:
    if pend["for"] == "relocation":
        case = await ST.STORE.get(pend["case_id"])
        steps = _steps_relocation(case, pend["origin"], pend.get("party") or 1, FIRST_NIGHTS)
        head = "Your move, in order — one yes per booking, as always (TEST bookings stay TEST):"
        legs_ = []
        pend["until"] = (date.fromisoformat(case["state"]["after"]["entry_date"]) + timedelta(days=FIRST_NIGHTS)).isoformat()
        from .relocation import move as MV            # CR 35 · the move as ONE trip on the account, before the first booking
        tid = await MV.save(ctx["account"], case, pend["origin"], FIRST_NIGHTS, ctx["now"])
        if tid:
            pend["trip_id"] = tid
            head += (f"\n(Your “{MV.TITLE}” trip is on your account — its paperwork deadlines are dated in it, and each booking "
                     "lands on its day. Say “show me my itinerary” any time.)")
    else:
        vs = await _visits(ctx["account"])
        legs_ = await legs(vs)
        if pend.get("party"):
            for v in vs:
                v["party"] = pend["party"]
        steps = _steps_campus(vs, pend["origin"], legs_)
        pend["until"] = vs[-1]["day"]
        head = (f"Your trip around {len(vs)} visit{'s' if len(vs) != 1 else ''} — one yes per booking, as always (TEST bookings stay TEST). "
                "Drive times from Google Routes; rail not checked (no timetable read at source):")
    pend.update(steps=steps, legs=legs_, i=0)
    lines = "\n".join(f"{n}. {s['say']}" for n, s in enumerate(steps, 1)) + f"\n{len(steps) + 1}. 📋 Everything in one itinerary"
    out.text(f"{head}\n{lines}")
    return await _next(ctx, pend, out)


async def _next(ctx, pend, out) -> bool:
    steps, i = pend.get("steps") or [], pend.get("i", 0)
    while i < len(steps) and steps[i]["what"] == "leg":
        i += 1
    if i >= len(steps):
        pend["i"] = i
        await itinerary(ctx, pend, out)
        pend["step"] = "done"
        return True
    s = steps[i]
    pend.update(i=i + 1, step="handed")
    # typed words, not buttons: Sasha's hand-off line never rewrites a button's answer (CR 13, her rule)
    out.text(f"Step {i + 1}: {s['say']}. Sasha takes it from here — one yes for the booking. When it's done, say NEXT "
             f"(or STOP PLAN).")
    ctx["handoff"] = s["sentence"]
    return False


async def itinerary(ctx, pend, out) -> None:
    """ONE itinerary: Sasha's bookings (flights, hotels, appointments, visits — the trip items) and the products' dated
    deadlines (agenda), by day, from today to a week after the trip."""
    from .agenda import agenda
    rows = await _bookings(ctx["account"])
    today = ctx["now"].date()
    last = max([r["on"] for r in rows] + [today.isoformat(), pend.get("until") or today.isoformat()])
    items = [{"on": r["on"], "time": r["time"], "text": r["text"]} for r in rows]
    items += [{"on": a["on"], "time": a["time"], "text": ("📋 " if a["kind"] != "visit" else "🎓 ") + a["text"].split(" — ")[0]}
              for a in await agenda(ctx["account"], today, date.fromisoformat(last) + timedelta(days=45))
              if not (a["kind"] == "visit" and any("campus visit" in r["text"] for r in rows if r["on"] == a["on"]))]
    for leg in pend.get("legs") or []:
        items.append({"on": leg["leave"][:10], "time": leg["leave"][11:16], "text": "🚗 " + leg["line"]})
    items.sort(key=lambda x: (x["on"], x["time"] or "99:99"))
    if not items:
        out.text("Nothing dated yet in your itinerary.")
        return
    days, cur = [], None
    for x in items:
        if x["on"] != cur:
            cur = x["on"]
            days.append(f"*{_day(cur)}*")
        days.append(f"  {x['time'] + ' ' if x['time'] else ''}{x['text']}")
    out.text("📋 Your itinerary — bookings, appointments and paperwork deadlines together:\n" + "\n".join(days)[:3500] +
             "\nIt's all in You → My bookings and You → Reminders, and S-83 reminds you the day before each booking.")


async def _bookings(account: str) -> List[dict]:
    """The account's upcoming trip items in "Sasha bookings" — read-only, the same rows "You → My bookings" shows."""
    if ST.BASE is None:
        return []
    import uuid
    from booking_signer.call_store import BOOKINGS_TRIP_TITLE as title

    async def fn(conn):
        return await conn.fetch(
            "select ti.type, ti.status, ti.provider_name, ti.booking_reference, "
            "(ti.date_time at time zone coalesce(ti.local_timezone, 'UTC')) as at from trip_items ti join trips t on t.id = ti.trip_id "
            "where t.owner_id = $1 and t.title = $2 and ti.status not in ('pending', 'cancelled') and ti.date_time >= now() - interval '1 day' "
            "order by ti.date_time", uuid.UUID(account), title)
    try:
        rows = await ST.BASE._run(fn)
    except Exception as e:
        log.error("[trip] bookings not read: %s: %s", type(e).__name__, e)
        return []
    icon = {"flight": "✈", "hotel": "🏨", "visa": "🏛", "doctor": "🩺", "experience": "🎓"}
    words = {"guest_booked": "booked by you", "confirmed": "confirmed", "requested": "requested — not confirmed yet"}
    return [{"on": r["at"].date().isoformat(), "time": r["at"].strftime("%H:%M"),
             "text": f"{icon.get(r['type'], '•')} {r['provider_name']} ({words.get(r['status'], r['status'])})"} for r in rows]


def claims(pend: dict, body: str, payload: str, media: list) -> bool:
    step, t = pend.get("step"), (body or "").strip()
    if payload.startswith("tp:"):
        return True
    if step == "entry":
        from .relocation import facts as F
        return bool(F.parse_date(t))
    if step == "origin":
        return 0 < len(t.split()) <= 6 and not re.search(r"\d{3,}", t)
    if step == "handed":
        return bool(_NEXT.match(t)) or bool(re.match(r"(?i)^\s*stop (the )?plan\b", t))
    return False


def context(pend: dict) -> dict:
    return {"product": "trip", "city": None, "country": None, "dates": [], "name": None,
            "line": f"[Trip plan for {pend.get('for')}: step {pend.get('i', 0)} of {len(pend.get('steps') or [])}]"}


async def web_turn(account: str, message: str, now: Optional[datetime] = None) -> Optional[dict]:
    """The same plan on the web chat (Sasha's conduct() calls this first — her wiring): None when the message isn't the
    plan's; else {"agent": "products_trip", "response": text, "handoff": sentence|None}. With a hand-off, conduct() answers
    the sentence with its own travel flow and shows it under this text — her one yes, her TEST labels, unchanged.
    The plan's state is a product conversation keyed "web:<account>" (30-day expiry, like every case)."""
    from booking_signer.guest_whatsapp import Out
    from datetime import timezone
    now = now or datetime.now(timezone.utc)
    from booking_signer import guest_whatsapp as GW
    if GW.FLIGHT.search(message or "") or GW.HOTEL.search(message or ""):
        return None                     # a hand-off sentence (or a complete request) is Sasha's: never loops back here
    key = f"web:{account}"
    saved = next((r["state"].get("pending") for r in await ST.STORE.conversations(key) if r["product"] == "trip"), None)
    plan_for = None
    if wants_plan(message):
        plan_for = await which(account, message, None, [])
        if not plan_for:
            return None
        pend, entering = {"kind": "product", "product": "trip", "step": None}, True
    elif saved and saved.get("step") not in (None, "done") and claims(saved, message, "", []):
        pend, entering = saved, False
    else:
        return None
    out = Out()
    ctx = {"account": account, "ch": {"wa_id_sha256": key, "account_id": account}, "st": {"pending": pend}, "now": now,
           "out": out, "plan_for": plan_for, "early": None}
    await turn(ctx, message, "", entering=entering)
    pend["touched"] = now.isoformat()
    if pend.get("step") in (None, "done"):
        await ST.STORE.drop_conversation(key, "trip")
    else:
        await ST.STORE.put_conversation(key, account, "trip", pend)
    text = "\n\n".join(str(i[1]) for i in out.items if i[0] in ("text", "ask"))
    return {"agent": "products_trip", "response": text.replace("say NEXT", "type NEXT"), "handoff": ctx.get("handoff")}
