"""CR 38 · CAMPUSME, A FOUR-SCHOOL TOUR — "Ivy tour week of 15 Nov: Yale, Harvard, Princeton, Brown" (EU 167, docs/campusme/
four-schools.md, read 6 Oct 2026).

  1. INTAKE ONCE: the family's details asked one by one, once — then kept in the Keep (the vault), opened only under a yes.
  2. THE SCHEDULE from what is really published: Yale and Brown read LIVE from their own calendars (open sessions, at
     their own times); Princeton and Harvard are NOT fetched (Princeton's robots refuse AI agents and its page blocked our
     read; Harvard's terms forbid automated access) — only their published general pattern (search summaries ◐), labelled
     "check on their page", with the exact link. Order: south-west to north-east (Princeton → Yale → Brown → Harvard).
     Drives checked with Google Routes (never a straight-line guess); a night near the next morning's campus.
  3. THE REGISTRATIONS: Yale and Brown — their own forms filled in Kanoe's browser for the family's press (founder override +
     tap to finish; never SUBMIT); Princeton and Harvard — the exact registration link + each detail its own message.
  4. THE FINISHED DOCUMENT: one itinerary (days, visits, addresses, drives, hotels, each registration's status) as a card +
     PDF in the chat, and the same trip on the account (Sasha's plan_store: the laptop's Trip panel, "show me my itinerary").
"""
from __future__ import annotations

import asyncio
import hashlib
import io
import json
import logging
import re
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

from booking_signer import yes as YS

from .. import store as ST
from . import schools as SC
from . import slate as SL

log = logging.getLogger("products.campus.tour")
ET = ZoneInfo("America/New_York")
ORDER = ["princeton", "yale", "brown", "harvard"]            # south-west → north-east along I-95 (EU 167 §3)
LABEL = "CampusMe tour details"
PROVIDER = "kanoe.ai"

# Princeton and Harvard: NOT read — their published pattern only (search summaries, EU 167), always "check on their page"
PATTERNS = {
    "princeton": {"name": "Princeton", "full_name": "Princeton University", "city": "Princeton, NJ",
                  "link": "https://apply.princeton.edu/portal/tours_info",
                  "address": "Admission Information Center, 36 University Place, Princeton, NJ",
                  "pattern": "weekdays: an information session + student-led tour; weekends: tours only; about 1 h each",
                  "days": "all", "why": SC.NOT_READABLE["princeton"]},
    "harvard": {"name": "Harvard", "full_name": "Harvard University", "city": "Cambridge, MA",
                "link": "https://apply.college.harvard.edu/portal/campus-visit",
                "address": "Agassiz House, 5 James St, Cambridge, MA",
                "pattern": "Information Session + Tour, Monday–Friday, starting at 9:30 am",
                "days": "weekdays", "why": SC.NOT_READABLE["harvard"]},
}
READ_PLACES = {"yale": "Yale Visitor Center, New Haven, CT",
               "brown": "Manning Hall, Admission Welcome Center, 21 Prospect St, Providence, RI"}
HOTEL_NEAR = {"princeton": "Princeton", "yale": "New Haven", "brown": "Providence", "harvard": "Cambridge"}

_TOUR = re.compile(r"(?i)\b(tour week|week of|ivy tour|college tour|road trip|tour of)\b")
_MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


def named(text: str) -> List[str]:
    t = (text or "").lower()
    keys = [s["key"] for s in SC.find_schools(text)]
    keys += [k for k in PATTERNS if re.search(rf"\b{k}\b", t) and k not in keys]
    return [k for k in ORDER if k in keys] + [k for k in keys if k not in ORDER]


def is_tour(text: str) -> bool:
    """Two or more schools AND a tour cue ("week of …", "tour week", "Ivy tour"…): the tour. Without the cue, several schools
    on one day or month stay the one-session flow ("Yale and Penn in April" — its sessions as cards)."""
    return len(named(text)) >= 2 and bool(_TOUR.search(text or ""))


def week_of(text: str, today: date) -> Optional[date]:
    m = re.search(r"(?i)\b(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?([a-z]{3})[a-z]*\b", text or "") or \
        re.search(r"(?i)\b([a-z]{3})[a-z]*\.?\s+(\d{1,2})(?:st|nd|rd|th)?\b", text or "")
    if not m:
        return None
    a, b = m.groups()
    day, mon = (a, b) if a.isdigit() else (b, a)
    mon = _MONTHS.get(mon.lower()[:3])
    if not mon:
        return None
    y = today.year + (1 if mon < today.month else 0)
    try:
        return date(y, mon, int(day))
    except ValueError:
        return None


# ── 1 · the intake, once ────────────────────────────────────────────────────────────────────────────────────────

ASKS = [("parent_name", "Who's coming with the student? (a parent's name)"),
        ("student_name", "The student's first and last name?"),
        ("email", "The student's email?"),
        ("mobile", "A mobile number for the days of the visits?"),
        ("high_school", "The student's high school?"),
        ("grad_year", "The student's graduation year? (e.g. 2027)"),
        ("major", "Intended major? (or UNDECIDED)"),
        ("birthdate", "The student's birthdate? (e.g. 14 March 2009)"),
        ("address", "Your mailing address? (street, city, state ZIP — e.g. 100 Main St, Princeton, NJ 08540)"),
        ("party", "How many of you, including the student? (Brown allows three in all; Yale up to three guests)")]
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[a-z]{2,}$", re.I)
_ADDR = re.compile(r"^\s*[^,]+,\s*[^,]+,\s*[A-Za-z .]+?\s+\d{5}(?:-\d{4})?\s*$")


def answer(k: str, t: str, fam: Dict[str, str], today: date) -> Optional[str]:
    """Stores a valid answer → None; else what to say (asked again, once)."""
    t = (t or "").strip()
    if k in ("parent_name", "high_school") and len(t) >= 3:
        fam[k] = t
    elif k == "student_name" and len(t.split()) >= 2:
        fam["student_first"], fam["student_last"] = t.split()[0], " ".join(t.split()[1:])
        fam[k] = t
    elif k == "email" and _EMAIL.match(t):
        fam[k] = t
    elif k == "mobile" and 10 <= len(re.sub(r"\D", "", t)) <= 15:
        fam[k] = re.sub(r"[^\d+]", "", t)
    elif k == "grad_year" and re.fullmatch(r"20[2-3]\d", t) and today.year <= int(t) <= today.year + 6:
        fam[k] = t
    elif k == "major" and t:
        fam[k] = t
    elif k == "birthdate":
        from .turn import parse_birthdate
        d = parse_birthdate(t)
        if not d:
            return "Please write it like \"14 March 2009\"."
        fam[k] = d
    elif k == "address" and _ADDR.match(t):
        fam[k] = t
    elif k == "party" and re.fullmatch(r"[1-4]", re.sub(r"\D", "", t) or "x"):
        fam[k] = re.sub(r"\D", "", t)
    else:
        return {"student_name": "First and last name, please.", "email": "That doesn't look like an email.",
                "mobile": "A phone number, please — e.g. 202 555 0123.", "grad_year": "The graduation year, e.g. 2027.",
                "address": "Street, city, state ZIP — e.g. 100 Main St, Princeton, NJ 08540.",
                "party": "A number from 1 to 4, including the student."}.get(k, "Could you say that again?")
    return None


def next_ask(fam: Dict[str, str]) -> Optional[str]:
    return next((k for k, _ in ASKS if k not in fam), None)


# ── 2 · the schedule ────────────────────────────────────────────────────────────────────────────────────────────

def _allowed(k: str, d: date) -> bool:
    return PATTERNS[k]["days"] == "all" or d.weekday() < 5


def _hm(sec: Optional[int]) -> str:
    if sec is None:
        return "drive time not available"
    h, m = divmod(round(sec / 60), 60)
    return f"{h} h {m:02d}" if h else f"{m} min"


async def schedule(keys: List[str], start: date, reader=None, travel=None) -> dict:
    """The days, in the schools' geographic order: read schools at their own open times, unread ones on a day their published
    pattern allows (one per day, "check on their page"), each drive checked with Google."""
    if travel is None:
        from booking_signer import proactive as PR
        travel = PR.travel
    days: Dict[str, dict] = {}
    visits: List[dict] = []
    day, busy_until, prev = start, None, None
    for k in [x for x in ORDER if x in keys] + [x for x in keys if x not in ORDER]:
        if k in PATTERNS:
            p = PATTERNS[k]
            d = day if not (visits and visits[-1]["date"] == day.isoformat()) else day + timedelta(days=1)
            while not _allowed(k, d):
                d += timedelta(days=1)
            visits.append({"school": k, "name": p["name"], "date": d.isoformat(), "start": None, "end": None, "title": p["pattern"],
                           "place": p["address"], "read": False, "link": p["link"], "status": "yours to register — link sent",
                           "why": p["why"]})
            day, busy_until, prev = d + timedelta(days=1), None, k
            continue
        s = SC.SCHOOLS.get(k)
        if not s or not s.get("proven"):
            continue
        chosen = None
        for i in range(6):
            d = day + timedelta(days=i)
            earliest = None
            if prev and visits and visits[-1]["date"] == d.isoformat() and busy_until:
                secs = await _drive(travel, _place(prev), _place(k), busy_until)
                earliest = busy_until + timedelta(seconds=(secs or 0) + 30 * 60) if secs is not None else None
                if secs is None:                      # can't check the drive: never two schools the same day on a guess
                    continue
            try:
                sessions = await SL.sessions(s, d.isoformat(), 2, reader)
            except SL.ReadRefused as e:
                log.warning("[tour] %s: %s", k, e)
                break
            for x in sessions:
                if x.status != "open" or ("Science and Engineering" in x.title):
                    continue
                at = datetime.combine(d, datetime.strptime(x.start, "%H:%M").time(), ET)
                if earliest and at < earliest:
                    continue
                chosen = (d, x)
                break
            if chosen:
                break
        if not chosen:
            visits.append({"school": k, "name": s["name"], "date": day.isoformat(), "start": None, "end": None,
                           "title": "no open session found that week", "place": _place(k), "read": True, "link": s["visit_page"],
                           "status": "nothing open — look at its calendar", "why": None})
            continue
        d, x = chosen
        end = x.end or (datetime.strptime(x.start, "%H:%M") + timedelta(hours=2)).strftime("%H:%M")
        visits.append({"school": k, "name": s["name"], "date": d.isoformat(), "start": x.start, "end": end,
                       "end_estimated": not x.end, "title": x.title.split(" · ")[0], "place": _place(k), "read": True,
                       "link": x.form_url, "session": x.as_dict(), "spaces": x.spaces, "status": "to prepare", "why": None})
        day, prev = d, k
        busy_until = datetime.combine(d, datetime.strptime(end, "%H:%M").time(), ET)
    drives, nights = [], []
    for a, b in zip(visits, visits[1:]):
        leave = datetime.combine(date.fromisoformat(a["date"]), datetime.strptime(a["end"] or "12:00", "%H:%M").time(), ET)
        secs = await _drive(travel, a["place"], b["place"], leave)
        drives.append({"from": a["name"], "to": b["name"], "date": a["date"], "leave": (a["end"] or "after the visit"),
                       "seconds": secs, "words": _hm(secs), "source": "Google Routes (driving)" if secs is not None else None})
        if b["date"] != a["date"]:
            nights.append({"date": a["date"], "city": HOTEL_NEAR.get(b["school"], b["name"]), "near": b["name"],
                           "why": f"{b['name']} the next morning"})
    for v in visits:
        days.setdefault(v["date"], {"date": v["date"], "visits": [], "drives": [], "night": None})["visits"].append(v)
    for dr in drives:
        days[dr["date"]]["drives"].append(dr)
    for n in nights:
        days[n["date"]]["night"] = n
    return {"start": start.isoformat(), "days": [days[k] for k in sorted(days)], "visits": visits}


def _place(k: str) -> str:
    return READ_PLACES.get(k) or PATTERNS.get(k, {}).get("address") or SC.SCHOOLS.get(k, {}).get("city", k)


async def _drive(travel, a: str, b: str, when: datetime) -> Optional[int]:
    try:
        return await travel(a, b, when, "DRIVE")
    except Exception as e:
        log.warning("[tour] drive time: %s", type(e).__name__)
        return None


# ── 4 · the finished document ───────────────────────────────────────────────────────────────────────────────────

def _t12(hhmm: Optional[str]) -> str:
    if not hhmm:
        return "time: check on their page"
    h, m = map(int, hhmm.split(":"))
    return f"{(h % 12) or 12}:{m:02d} {'AM' if h < 12 else 'PM'}"


def lines(plan: dict, fam: Dict[str, str], plain: bool = False) -> List[str]:
    """The tour, line by line — with emoji for the chat; plain words for the card and the PDF (their font has no emoji)."""
    out = []
    for d in plan["days"]:
        out.append(f"■ {date.fromisoformat(d['date']).strftime('%A %-d %B')}")
        for v in d["visits"]:
            out.append(f"   {v['name']} — {v['title']} · {_t12(v['start'])}{' (from its own calendar)' if v['read'] and v['start'] else ''}")
            out.append(f"      {v['place']} · registration: {v['status']}")
            if not v["read"]:
                out.append(f"      not read ({v['why']}) — check on their page: {v['link']}")
        for dr in d["drives"]:
            out.append(f"   🚗 {dr['from']} → {dr['to']}: {dr['words']}" + (f" ({dr['source']})" if dr["source"] else ""))
        if d["night"]:
            out.append(f"   🏨 Night near {d['night']['near']} — {d['night']['city']} ({d['night']['why']})")
    if plain:
        out = [x.replace("■ ", "").replace("🚗 ", "Drive: ").replace("🏨 ", "").replace(" → ", " to ") for x in out]
    return out


def compact(plan: dict) -> List[str]:
    """CR 52 · the tour in one line per day: the visits and their times, and where the night is. The full plan is a tap away."""
    out = []
    for d in plan["days"]:
        vs = ", ".join(f"{v['name']}" + (f" {_t12(v['start'])}" if v["read"] and v["start"] else " (check its page)") for v in d["visits"])
        night = f" · night near {d['night']['near']}" if d.get("night") else ""
        out.append(f"{date.fromisoformat(d['date']).strftime('%a %-d %b')}: {vs}{night}")
    return out


def pdf(plan: dict, fam: Dict[str, str], title: str) -> bytes:
    from ..relocation.three import _text_page, DPI
    who = f"{fam.get('student_name', 'the student')} with {fam.get('parent_name', 'family')} · party of {fam.get('party', '?')}"
    page = _text_page(title, [who, ""] + lines(plan, fam, plain=True) + ["", sources_line(plan)])
    buf = io.BytesIO()
    page.save(buf, "PDF", resolution=DPI)
    return buf.getvalue()


def card(plan: dict, fam: Dict[str, str], title: str) -> bytes:
    from ..relocation.three import _text_page
    ls = lines(plan, fam, plain=True)
    im = _text_page(title, ls)
    w, h = im.size
    cut = min(h, 170 + 52 * (len(ls) + 2))
    im = im.crop((0, 0, w, cut)).resize((w // 2, cut // 2))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=85)
    return buf.getvalue()


def as_trip(plan: dict, title: str) -> dict:
    """The same days for Sasha's plan_store (dated days; each visit, drive and night an activity)."""
    from booking_signer.plan_store import _part
    days = []
    for i, d in enumerate(plan["days"], 1):
        acts = [{"time": _part(v["start"] or "10:00"), "name": f"{v['name']} — {v['title'][:60]}",
                 "blurb": f"{_t12(v['start'])} · {v['place']} · registration: {v['status']}"} for v in d["visits"]]
        acts += [{"time": "Afternoon", "name": f"Drive {dr['from']} → {dr['to']}", "blurb": dr["words"]} for dr in d["drives"]]
        if d["night"]:
            acts.append({"time": "Evening", "name": f"Stay near {d['night']['near']}", "blurb": d["night"]["city"]})
        city = (d["visits"][0]["place"].split(",")[-2].strip() if d["visits"] else "")
        days.append({"day": i, "date": d["date"], "city": city, "title": " · ".join(v["name"] for v in d["visits"]), "activities": acts})
    return {"title": title, "days": days, "kanoe": "campus-tour/1"}


def copy_messages(fam: Dict[str, str]) -> List[str]:
    b = fam.get("birthdate", "")
    bd = f"{b[5:7]}/{b[8:10]}/{b[:4]}" if re.fullmatch(r"\d{4}-\d{2}-\d{2}", b) else b
    vals = [fam.get("student_first"), fam.get("student_last"), fam.get("email"), fam.get("mobile"), bd, fam.get("high_school"),
            fam.get("grad_year"), fam.get("major"), fam.get("address"), fam.get("party")]
    return [v for v in vals if v]


# ── the conversation (called from campus.turn) ───────────────────────────────────────────────────────────────────

def _title(start: date) -> str:
    return f"Campus tour — week of {start.day} {start.strftime('%b')}"


async def _vault_item(account: str) -> Optional[dict]:
    try:
        from booking_signer.vault import crypto as VC
        rows = await VC.STORE.list(account)
    except Exception:
        return None
    return next((r for r in rows if r.get("label") == LABEL and not r.get("deleted_at")), None)


async def start(ctx: dict, body: str) -> None:
    pend, out = ctx["st"]["pending"], ctx["out"]
    keys = named(body)
    wk = week_of(body, ctx["now"].date())
    if not wk:
        out.text(f"Which week? (e.g. \"week of 15 Nov\") — I'll plan {', '.join(SC.SCHOOLS.get(k, PATTERNS.get(k, {})).get('name', k) for k in keys)}.")
        pend.update(step="tour_week", tour={"keys": keys})
        return
    pend["tour"] = {"keys": keys, "start": wk.isoformat(), "fam": {}}
    item = await _vault_item(ctx["account"])
    if item:
        pend["tour"]["vault"] = {"id": str(item["id"]), "label": item["label"]}
        out.text(f"I'll use your kept details (“{item['label']}”) — opened only under your yes.")
        await _plan(ctx)
        return
    out.text("I'll ask each thing once, and keep it in your vault if you'd like, so next time is one yes.")
    pend["step"] = "tour_ask"
    out.text(dict(ASKS)[next_ask({})])


async def on_message(ctx: dict, body: str, payload: str) -> bool:
    pend, out = ctx["st"]["pending"], ctx["out"]
    from .. import steps as STP
    if STP.is_more(payload or "", "cm:"):                 # CR 52 · a step's details, by its own button
        STP.show(pend, STP.is_more(payload, "cm:"), out)
        return True
    step, t = pend.get("step"), (body or "").strip()
    tr = pend.setdefault("tour", {})
    if step == "tour_week":
        wk = week_of(t, ctx["now"].date())
        if not wk:
            out.text("A date please — e.g. \"week of 15 Nov\".")
            return True
        return await start(ctx, f"{' '.join(tr.get('keys') or [])} week of {wk.day} {wk.strftime('%b')}") or True
    if step == "tour_ask":
        k = next_ask(tr["fam"])
        bad = answer(k, t, tr["fam"], ctx["now"].date())
        if bad:
            out.text(bad)
            return True
        k = next_ask(tr["fam"])
        if k:
            out.text(dict(ASKS)[k])
            return True
        pend["step"] = "tour_keep"
        out.ask("Keep these details in your vault (encrypted, deletable any time) so the next tour is one yes?",
                [("Yes, keep them", "cm:tkeep:yes"), ("Just this once", "cm:tkeep:no")])
        return True
    if step == "tour_keep":
        if payload == "cm:tkeep:yes" or (not payload and YS.is_yes(t)):
            try:
                from booking_signer.guest_whatsapp import api
                st, j = await api(ctx["account"], "POST", "/api/booking/vault",
                                  {"provider": PROVIDER, "label": LABEL, "kind": "identifier",
                                   "fields": {"value": json.dumps(tr["fam"], sort_keys=True)}})
                if st in (200, 201):
                    out.text(f"Kept in your vault as “{LABEL}”.")
            except Exception as e:
                log.warning("[tour] keep: %s", type(e).__name__)
        await _plan(ctx)
        return True
    if step == "tour_confirm":
        sha = tr.get("sha", "")
        if payload == f"cm:tno:{sha}" or (not payload and re.match(r"(?i)^\s*no\b", t)):
            pend["step"] = "tour_done"
            out.text("OK — nothing prepared. The plan stays here; say “campus” any time.")
            return True
        if payload == f"cm:tyes:{sha}" or (not payload and YS.is_yes(t)):
            await _prepare(ctx, {"how": "whatsapp_button" if payload else "whatsapp_text", "said": t, "at": ctx["now"].isoformat(),
                                 "read_back_sha256": hashlib.sha256("\n".join(approved_lines(tr)).encode()).hexdigest()})
            return True
        out.text("Yes or no?")
        return True
    if step == "tour_ready":
        if len(t) >= 60 and re.search(r"(?i)confirm|registered|registration|look forward|see you", t):   # CR 45 · its email, pasted
            v = next((v for v in tr["plan"]["visits"] if v.get("session") and any(a in t.lower() for a in _aliases(v["school"]))), None)
            if v:
                await _confirm_visit(ctx, tr, v, t, "the school's email, pasted here")
                return True
        m = re.match(r"(?i)^\s*(registered|booked|done)\b\s*(?:at\s+|for\s+)?(\w+)?", t)
        k = next((x for x in tr.get("keys") or [] if m and m.group(2) and x.startswith(m.group(2).lower()[:4])), None)
        if m and k:
            name = SC.SCHOOLS.get(k, PATTERNS.get(k, {})).get("name", k)
            for v in tr["plan"]["visits"]:
                if v["school"] == k:                         # CR 45 · never assumed: not confirmed until its confirmation says so
                    v["status"] = f"Registration not confirmed — you said you registered; {name}'s confirmation decides"
            await _save(ctx)
            out.text(f"Noted that you registered at {name} — I'll mark it registered when its confirmation says so. Paste "
                     f"{name}'s confirmation email here and I'll check it against what was prepared (student, date, time).")
            return True
        return False
    return False


async def _plan(ctx: dict) -> None:
    pend, out = ctx["st"]["pending"], ctx["out"]
    tr = pend["tour"]
    readable = [SC.SCHOOLS[k]["name"] for k in tr["keys"] if k in SC.SCHOOLS]   # CR 43 · the tour's own schools, never a fixed pair
    await ctx["early"](f"Reading {_and([n + chr(39) + 's' for n in readable]) or 'each school'}{' own calendars' if len(readable) > 1 else ' own calendar' if readable else ' page'}, "
                       "and checking each drive with Google…")
    plan = await schedule(tr["keys"], date.fromisoformat(tr["start"]), ctx.get("reader"))
    tr["plan"] = plan
    ls = lines(plan, tr["fam"])
    sha = hashlib.sha256("\n".join(ls).encode()).hexdigest()[:16]
    tr["sha"] = sha
    pend["step"] = "tour_confirm"
    from .. import steps as STP                           # CR 52 · one line per day; the full plan and what "yes" does behind a tap
    STP.stash(pend, "plan", ["Your tour, from what's really published:\n" + "\n".join(ls), promise(plan, ctx["account"])])
    keep = f"\n{approved_lines(tr)[0]}" if tr.get("vault") else ""   # CR 48 · the yes names the kept item it opens
    out.ask("Your tour:\n" + "\n".join(compact(plan)) + keep + "\nPrepare it?",
            [("Yes, prepare it", f"cm:tyes:{sha}"), ("No", f"cm:tno:{sha}"), STP.more("cm:", "plan", "Full plan")])


def approved_lines(tr: dict) -> List[str]:
    """CR 48 · what the family's yes covers, as the vault checks it: the kept item's own access line (its label — shown in the
    read-back before "Prepare it?") and the plan's fingerprint. The approval is the full sha256 of these lines (vault.use)."""
    lines = [tr["sha"]]
    if tr.get("vault"):
        from booking_signer.vault import crypto as VC
        lines.insert(0, VC.access_line(PROVIDER, tr["vault"]["label"], "identifier"))
    return lines


async def _open_fam(ctx: dict, tr: dict, approval: dict) -> Dict[str, str]:
    if tr.get("fam"):
        return dict(tr["fam"])
    from booking_signer.vault import crypto as VC
    async with VC.use(ctx["account"], tr["vault"]["id"], approval=approval, approved_lines=approved_lines(tr),
                      action_kind="campusme_tour", action_ref=f"tour-{tr['sha']}") as secret:
        return json.loads(secret.get("value") or "{}")


async def _prepare(ctx: dict, approval: dict) -> None:
    from booking_signer import guest_whatsapp as GW
    from booking_signer import handover as HO
    from .. import formcard as FC
    pend, out = ctx["st"]["pending"], ctx["out"]
    tr = pend["tour"]
    try:
        fam = await _open_fam(ctx, tr, approval)
    except Exception as e:
        out.text(f"❌ Your kept details couldn't be opened ({type(e).__name__}). Nothing was prepared.")
        return
    plan = tr["plan"]
    owner = HO.founder_override(ctx["account"])                     # CR 43 · the founder's own account: the live hand-over
    founder = owner and HO.configured()
    title = _title(date.fromisoformat(tr["start"]))
    cid = await ST.STORE.put("campus", ctx["account"], ctx["ch"]["wa_id_sha256"],
                             {"kind": "tour", "title": title, "plan": plan, "fam_name": fam.get("student_name"),
                              "approval": approval, "status": "prepared"})
    tr["case_id"] = cid
    web = __import__("products.campus.turn", fromlist=["web"]).web()
    from .. import steps as STP                         # CR 52 · one line per school; details to copy behind a tap
    status, notes = [], []
    for v in plan["visits"]:
        name = v["name"]
        fillable = bool(v["read"] and v.get("session") and live_school(v["school"]))
        if fillable and founder:
            v["status"] = "filling in Kanoe's browser — a tap to finish comes to your phone"
            status.append(f"🎓 {name}: filling its own form — “Tap to finish” comes to your phone")
            GW._spawn(_live(ctx["account"], ctx["ch"]["wa_id_sha256"], ctx["frm"], cid, v, fam))
        else:
            v["status"] = "yours to register — link sent" if not v["read"] else "yours to register on its own page — link sent"
            status.append(f"🎓 {name}: register here — {v['link']}" + (" (I couldn't open the filled page: the cloud browser isn't set up)"
                                                                         if fillable and owner else ""))   # CR 43 · never silent
            notes.append(f"{name}: " + (f"not read by Kanoe ({v['why']}); its published pattern: {v['title']} — check on its page."
                                         if not v["read"] else f"{v['title']}, {date.fromisoformat(v['date']).strftime('%a %-d %b')} "
                                                               f"{_t12(v['start'])}."))
    STP.stash(pend, "details", ["Your details, each ready to copy:"] + copy_messages(fam) + notes)
    out.text("\n".join(status))
    await _save(ctx)
    FC.show(out, f"Your {title} — one itinerary: the visits, the drives, the nights, each registration's status.",
            f"{web}/api/products/campus/{cid}/tour-card.jpg", f"{web}/api/products/campus/{cid}/tour.pdf")
    try:
        from booking_signer import plan_store as PS
        tid = await PS.save(ctx["account"], as_trip(plan, title), f"from {date.fromisoformat(tr['start']).day} "
                                                                    f"{date.fromisoformat(tr['start']).strftime('%b')}", ctx["now"])
        if tid:
            tr["trip_id"] = tid
            STP.stash(pend, "plan", ((pend.get("more") or {}).get("plan") or {}).get("texts", []) +
                      ["It's on your account as a trip too — the laptop's Trip panel, or say “show me my itinerary”."])
    except Exception as e:
        log.warning("[tour] trip not saved: %s", type(e).__name__)
    pend["step"] = "tour_ready"
    out.ask("When you've registered somewhere, tell me (e.g. \"registered Princeton\") — or paste its confirmation email.",
            [STP.more("cm:", "details", "Copy my details"), STP.more("cm:", "plan", "Full plan")])


async def _save(ctx: dict) -> None:
    tr = ctx["st"]["pending"].get("tour") or {}
    cid = tr.get("case_id")
    case = await ST.STORE.get(cid) if cid else None
    if case:
        case["state"]["plan"] = tr["plan"]
        await ST.STORE.update(cid, case["state"])


async def _live(account: str, wa: str, frm: str, cid: str, v: dict, fam: Dict[str, str]) -> None:
    """In the background: the school's own form, filled; then ONE tap to the phone. The family presses."""
    from booking_signer import guest_whatsapp as GW
    from booking_signer import handover as HO
    from .. import whatsapp as PW
    from . import live as LV
    from .slate import Session

    async def say(text: str) -> None:
        ch, _, number = await PW.reach(wa, frm, account)
        if ch:
            gst = await GW.STORE.get_state(ch["wa_id_sha256"])
            await GW.deliver(ch, number, GW.Out().text(text), gst.get("last_inbound_at"))
    try:
        rec = await open_live(v["school"], Session(**v["session"]), fam, account)
    except Exception as e:                                          # CR 43 · said, never a silent fall-back to a bare link
        why = e.say if isinstance(e, HO.Refused) else f"the cloud browser failed ({type(e).__name__})"
        log.warning("[tour] %s live hand-over not opened: %s", v["school"], getattr(e, "rule", type(e).__name__))
        await say(f"🎓 {v['name']}: I couldn't open the filled page — {why}. Here's the link and your details:\n{v['link']}")
        for m in copy_messages(fam):
            await say(m)
        await _status(cid, v["school"], f"not filled ({getattr(e, 'rule', 'error')}) — register on its own page")
        return
    await _status(cid, v["school"], "filled — waiting for your press (link on your phone)", rec["id"])
    tap = await HO.tap_phone(account, rec)
    if not tap.get("sent"):
        await say(f"📲 {rec['venue']} is filled and waiting (10 minutes): {HO.view_url(rec)}")


def sources_line(plan: dict) -> str:
    """CR 43 · the PDF's footer, from THIS tour's schools (it named Yale/Brown and Princeton/Harvard whatever the tour was)."""
    read = [v["name"] for v in plan["visits"] if v["read"]]
    pattern = [v["name"] for v in plan["visits"] if not v["read"]]
    out = []
    if read:
        out.append(f"Times from {_and([n + chr(39) + 's' for n in read])} own calendar{'s' if len(read) > 1 else ''}, read today")
    if pattern:
        out.append(f"{_and(pattern)}: {'their' if len(pattern) > 1 else 'its'} published pattern only — check on {'their' if len(pattern) > 1 else 'its'} page")
    return "; ".join(out) + ". Drives: Google Routes. Nothing was registered by Kanoe: the family presses."


def _and(xs: List[str]) -> str:
    return xs[0] if len(xs) == 1 else ", ".join(xs[:-1]) + " and " + xs[-1] if xs else ""


def promise(plan: dict, account: Optional[str]) -> str:
    """CR 43 · what "yes" does, school by school, for THIS tour and THIS account: on the founder's account the schools whose own
    form the live hand-over fills; every other school's own page with the details ready to copy."""
    from booking_signer import handover as HO
    owner = HO.founder_override(account)
    pos = lambda n: n + "'s"
    filled = [v["name"] for v in plan["visits"] if owner and v["read"] and v.get("session") and live_school(v["school"])]
    linked = [v["name"] for v in plan["visits"] if v["name"] not in filled]
    parts = []
    if filled:
        parts.append(f"I fill {_and([pos(n) for n in filled])} own registration form{'s' if len(filled) > 1 else ''} in Kanoe's browser "
                     "for you to check and press (“Tap to finish” on your phone for each — you press Submit, I never do)")
    if linked:
        parts.append(f"{'I give you' if not filled else 'give you'} {_and([pos(n) for n in linked])} own registration "
                     f"page{'s' if len(linked) > 1 else ''} with each of your details ready to copy")
    return "If you say yes: " + ", and ".join(parts) + ". Then the whole tour goes in your itinerary, with a PDF."


def live_school(school: str) -> bool:
    """CR 43 · the schools whose own form the live hand-over fills: Yale and Brown (CR 38), and the one-page "register" forms
    (Penn, CR 33) — before, a tour sent only Yale and Brown, so Penn in a tour came as a bare link."""
    from . import live as LV
    return school in LV.TOUR_FIRST or (SC.SCHOOLS.get(school) or {}).get("variant") == "register"


def as_profile(fam: Dict[str, str]) -> Dict[str, str]:
    """The tour's details in the shape the one-page hand-over (Penn) takes."""
    return {"first": fam.get("student_first") or "", "last": fam.get("student_last") or "", "email": fam.get("email") or "",
            "birthdate": fam.get("birthdate") or "", "grad_year": fam.get("grad_year") or "", "high_school": fam.get("high_school") or "",
            "mobile": fam.get("mobile") or ""}


async def open_live(school: str, session, fam: Dict[str, str], account: str, read_only: bool = False, fictional: bool = False) -> dict:
    """The school's own form, filled in Kanoe's cloud browser — Yale/Brown's (CR 38) or the one-page register form (Penn)."""
    from . import live as LV
    if school in LV.TOUR_FIRST:
        return await LV.open_tour_handover(school=school, session=session, fam=fam, account=account, read_only=read_only,
                                           fictional=fictional)
    party = max(1, min(int(re.sub(r"\D", "", str(fam.get("party") or "")) or 1), 4))
    return await LV.open_campus_handover(session=session, profile=as_profile(fam), attendees=party, account=account,
                                         read_only=read_only, fictional=fictional)


def _aliases(school: str) -> List[str]:
    s = SC.SCHOOLS.get(school) or PATTERNS.get(school) or {}
    return [x.lower() for x in s.get("aliases", [])] + ([s["full_name"].lower()] if s.get("full_name") else []) + \
        ([s["name"].lower()] if s.get("name") else [])


def _student(fam_name: str) -> str:
    return (fam_name or "").split(" ")[0]


async def _confirm_visit(ctx: Optional[dict], tr: Optional[dict], v: dict, text: str, source: str, from_page: bool = False,
                         at: str = "", fam_name: str = "") -> str:
    """CR 45 · a visit's confirmation, checked against what was prepared; its status line set from the result."""
    from . import confirm as CF
    school = SC.SCHOOLS.get(v["school"]) or {"name": v["name"], "aliases": _aliases(v["school"])}
    fam = (tr or {}).get("fam") or {}
    exp = CF.expect(school, v["session"], fam.get("student_first") or _student(fam_name))
    r = CF.read(text, exp, from_page=from_page)
    v["status"] = CF.line(exp, r)
    v["confirmation"] = CF.record(r, source, at or (ctx["now"].isoformat() if ctx else ""))
    if ctx is not None:
        await _save(ctx)
        ctx["out"].text(("✅ " if r["confirmed"] else "⚠ ") + v["status"] + ("" if r["confirmed"] else ". I haven't marked it registered."))
    return v["status"]


async def _live_done(pub: dict) -> None:
    """CR 45 · after the family's own press in a tour's hand-over: the school's page, checked, on that visit."""
    for c in await ST.STORE.of_product("campus"):
        st = c["state"]
        if st.get("kind") != "tour":
            continue
        v = next((v for v in (st.get("plan") or {}).get("visits") or [] if v.get("handover_id") == pub.get("id")), None)
        if v:
            await _confirm_visit(None, None, v, pub.get("answer_text") or "", "the school's page after your press", from_page=True,
                                 at=pub.get("answered_at") or "", fam_name=st.get("fam_name") or "")
            await ST.STORE.update(c["id"], st)


def _hook() -> None:
    from . import live as LV
    if _live_done not in LV.CAMPUS_DONE:
        LV.CAMPUS_DONE.append(_live_done)


_hook()


async def _status(cid: str, school: str, status: str, hid: Optional[str] = None) -> None:
    case = await ST.STORE.get(cid)
    if not case:
        return
    for v in case["state"]["plan"]["visits"]:
        if v["school"] == school:
            v["status"] = status
            if hid:
                v["handover_id"] = hid
    await ST.STORE.update(cid, case["state"])


def claims(pend: dict, body: str, payload: str, media: list) -> bool:
    step, t = pend.get("step"), (body or "").strip()
    if payload.startswith(("cm:tkeep:", "cm:tyes:", "cm:tno:", "cm:more:")):
        return True
    if step in ("tour_ask", "tour_week"):
        return bool(t) and not t.endswith("?")
    if step in ("tour_keep", "tour_confirm"):
        return YS.is_yes(t) or bool(re.match(r"(?i)^\s*no\b|just this once", t))
    if step == "tour_ready":
        return bool(re.match(r"(?i)^\s*(registered|booked|done)\b", t)) or \
            (len(t) >= 60 and bool(re.search(r"(?i)confirm|registered|registration|look forward|see you", t)))   # CR 45 · its email
    return False
