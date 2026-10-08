"""CR 54 · CAMPUSME AS SASHA'S SKILL — the seven tools of skill "campus", on the AgAPI v0 contract (agapi/v0.py: Ctx, ToolError,
typed inputs, honest error codes, idempotent Austen), for Sasha's agent while the skill is open (agapi/skills.py) — and for any
outside client later. docs/sasha/mes-as-skills-design.md §1.1.

    Magellan  finds    find_schools · find_visit_sessions · plan_tour
    Austen    acts     save_student · prepare_registration              (idempotency_key required)
    Sherlock  checks   check_confirmation
    Pacioli   records  get_campus                                       (the ONLY source for "registered")

The engines are today's CampusMe, unchanged: the schools' own calendars (products/campus/slate.py, robots first, paced), the tour
planner (tour.py, drives from Google Routes), the cloud-browser hand-over (live.py + booking_signer/handover.py) and the
confirmation check (confirm.py). Visits land in the trip basket as kind 'visit' (booking_signer/basket_visits.py).

HARD RULES, in code (not the prompt):
  · There is NO tool that submits, signs, sends, ticks, pays, books or creates an account. prepare_registration fills the school's
    own form and STOPS before its Submit; the statement box and the Submit are the family's, on their phone.
  · A real student's details go through the cloud browser only under the signed DPA or the founder's own account (HO.dpa_ok).
    Otherwise: no fill — the school's own page and the details to copy. The caller can never mark a student "fictional".
  · "registered" exists only after check_confirmation matched the school's own reply (Pacioli writes it); guard_check holds
    Sasha's words to that, and to figures (times, prices, spaces, drive times) that came from these tools.
  · Every fact-bearing result carries `sources`; user-facing messages never carry internals (no exception names, no ids of ours).
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from agapi import v0 as V0
from agapi.v0 import DATE, Ctx, ToolError, _t

log = logging.getLogger("agapi.campus")
SKILL = "campus"
_IDEM: Dict[str, dict] = {}
DAYS_READ_MAX = 3            # find_visit_sessions: open days read per call (each is a paced read of the school's calendar)
SESSIONS_MAX = 12
CALENDAR_LOOKAHEAD_DAYS = 6

LEFT_FOR_FAMILY = ["the school's own statement box (it is yours to tick — CampusMe never ticks one)",
                   "the school's own Submit (pressing it registers the student; not pressing sends nothing)"]
STUDENT_FIELDS = ["parent_name", "student_name", "email", "mobile", "high_school", "grad_year", "major", "birthdate", "address",
                  "party"]


# ── the engines, imported late (tests swap their readers) ──────────────────────────────────────────────────────────────

def _engines():
    from products.campus import schools as SC, slate as SL, tour as TR, confirm as CF
    return SC, SL, TR, CF


def _school_rec(key: str) -> Optional[dict]:
    SC, _, TR, _ = _engines()
    return SC.SCHOOLS.get(key) or TR.PATTERNS.get(key)


def _resolve(names: List[str]) -> List[str]:
    """Names or keys → school keys, in the order given. Any name that isn't a school → school_unknown (said, never a guess)."""
    SC, _, TR, _ = _engines()
    keys, unknown = [], []
    for n in names:
        k = (n or "").strip().lower()
        if k in SC.SCHOOLS or k in TR.PATTERNS:
            hit = [k]
        else:
            hit = [s["key"] for s in SC.find_schools(n)] or [p for p in TR.PATTERNS if re.search(rf"\b{p}\b", k)]
        if not hit:
            unknown.append(n)
        keys += [h for h in hit if h not in keys]
    if unknown:
        raise ToolError("school_unknown", f"CampusMe doesn't know {', '.join(unknown)} yet — it reads only schools it has checked")
    return keys


def _source(label: str, url: Optional[str], at: Optional[str] = None) -> dict:
    return {"label": label, "url": url, "read_at": at}


# ── Magellan ───────────────────────────────────────────────────────────────────────────────────────────────────────────

async def find_schools(ctx: Ctx, a: dict) -> dict:
    SC, _, TR, _ = _engines()
    text = a["text"]
    found = [{"school": s["key"], "name": s["name"], "calendar_read": bool(s.get("proven")), "visit_page": s.get("visit_page")}
             for s in SC.find_schools(text)]
    seen = {f["school"] for f in found}
    for k, p in TR.PATTERNS.items():
        if k not in seen and re.search(rf"\b{k}\b", text.lower()):
            found.append({"school": k, "name": p["name"], "calendar_read": False, "visit_page": p["link"],
                          "why_not_read": p["why"]})
    if not found:
        raise ToolError("no_school_named", "no school CampusMe knows is named there")
    return {"schools": found, "sources": [_source(f"{f['name']}'s visit page", f["visit_page"]) for f in found]}


async def find_visit_sessions(ctx: Ctx, a: dict) -> dict:
    SC, SL, _, _ = _engines()
    (key,) = _resolve([a["school"]])
    s = SC.SCHOOLS.get(key)
    if not s:
        p = _school_rec(key)
        raise ToolError("site_refuses_agents", f"{p['name']}'s visit page can't be read by an assistant — {p['why']}. Its own page: {p['link']}")
    if not s.get("proven"):
        raise ToolError("calendar_not_checked", f"{s['name']}'s calendar hasn't been read and checked yet")
    start = _day(a["start_date"], "start_date")
    end = _day(a["end_date"], "end_date") if a.get("end_date") else start + timedelta(days=CALENDAR_LOOKAHEAD_DAYS)
    if end < start or (end - start).days > 31:
        raise ToolError("dates_invalid", "the end date must be within a month after the start date")
    attendees = max(1, min(int(a.get("attendees") or 2), 5))
    try:
        days, receipt = await SL.dates(s, start, end)
        open_days = [d for d, ok in days if ok and start.isoformat() <= d <= end.isoformat()]
        out = []
        for d in open_days[:DAYS_READ_MAX]:
            for x in await SL.sessions(s, d, attendees):
                out.append({"school": key, "day": x.day, "start": x.start, "end": x.end, "title": x.title.split(" · ")[0],
                            "location": x.location, "open": x.status == "open", "spaces": x.spaces, "register_page": x.form_url})
    except SL.ReadRefused:
        raise ToolError("site_refuses_agents", f"{s['name']}'s calendar can't be read by an assistant right now — its own page: {s['visit_page']}")
    except ToolError:
        raise
    except Exception as e:
        log.warning("[campus] %s calendar: %s", key, type(e).__name__)
        raise ToolError("calendar_unreadable", f"{s['name']}'s calendar couldn't be read just now — its own page: {s['visit_page']}")
    return {"school": key, "name": s["name"], "sessions": out[:SESSIONS_MAX],
            "published_until": max((d for d, _ in days), default=None), "days_read": open_days[:DAYS_READ_MAX],
            "sources": [_source(f"{s['name']}'s own visit calendar", s["visit_page"], receipt.get("at"))]}


async def plan_tour(ctx: Ctx, a: dict) -> dict:
    _, _, TR, _ = _engines()
    from booking_signer import basket_visits as BV, plan_store as PS
    keys = _resolve(a["schools"])
    if not 1 <= len(keys) <= 6:
        raise ToolError("schools_invalid", "a tour is one to six schools")
    start = _day(a["week_of"], "week_of")
    if start < _today():
        raise ToolError("week_of_past", "that week has passed")
    plan = await TR.schedule(keys, start)
    if not plan["visits"]:
        raise ToolError("no_visits", "none of those schools had a visit to plan that week")
    title = (a.get("title") or "").strip()[:80] or f"Campus tour · {start.strftime('%-d %b %Y')}"
    trip_id = await PS.save(ctx.account, TR.as_trip(plan, title), f"campus tour: {', '.join(keys)}", datetime.now(timezone.utc))
    if not trip_id:
        raise ToolError("tour_not_saved", "the tour couldn't be saved to your trips just now — nothing was changed")
    try:
        ids = await BV.suggest(ctx.account, trip_id, plan["visits"], _party(a.get("party")))
    except BV.BK.BasketError:
        raise ToolError("visits_not_saved", "the tour is saved, but its visits can't be kept as items yet")
    visits = [{"visit_id": i, "school": v["school"], "name": v["name"], "date": v["date"], "start": v["start"], "end": v.get("end"),
               "title": v["title"], "time_from_school": bool(v["read"] and v["start"]), "state": "suggested",
               "register_page": v["link"], "why_not_read": v.get("why")} for i, v in zip(ids, plan["visits"])]
    drives = [{"from": dr["from"], "to": dr["to"], "date": dr["date"], "drive": dr["words"], "source": dr["source"]}
              for d in plan["days"] for dr in d["drives"]]
    nights = [{"date": d["date"], "near": d["night"]["near"], "city": d["night"]["city"]} for d in plan["days"] if d.get("night")]
    srcs = [_source(f"{v['name']}'s own visit calendar" if v["read"] else f"{v['name']}'s published visit pattern", v["link"])
            for v in plan["visits"]]
    if drives:
        srcs.append(_source("Google Routes (driving)", None))
    return {"trip_id": trip_id, "title": title, "days": TR.compact(plan), "visits": visits, "drives": drives, "nights": nights,
            "sources": srcs}


# ── Austen ─────────────────────────────────────────────────────────────────────────────────────────────────────────────

# the student's details: the product store's CampusMe row under the AGENT's own key (never the WhatsApp conversation's), kept
# 30 days like every product conversation (products/store.py EXPIRES)
_STUDENT_KEY = "agent-student:{account}"
_STUDENT_PRODUCT = "campus"


async def _student(account: str) -> Dict[str, str]:
    from products import store as ST
    for r in await ST.STORE.conversations(_STUDENT_KEY.format(account=account)):
        if r.get("product") == _STUDENT_PRODUCT:
            return dict((((r.get("state") or {}).get("pending")) or {}).get("fam") or {})
    return {}


async def save_student(ctx: Ctx, a: dict) -> dict:
    _, _, TR, _ = _engines()
    from products import store as ST
    fam = await _student(ctx.account)
    invalid, today = [], datetime.now(timezone.utc).date()
    for k in STUDENT_FIELDS:
        v = (a.get("details") or {}).get(k)
        if v in (None, ""):
            continue
        trial: Dict[str, str] = {}
        why = TR.answer(k, str(v), trial, today)
        if why:
            invalid.append({"field": k, "why": why})
        else:
            fam.update(trial)
    await ST.STORE.put_conversation(_STUDENT_KEY.format(account=ctx.account), ctx.account, _STUDENT_PRODUCT, {"fam": fam})
    return {"saved": [k for k in STUDENT_FIELDS if k in fam], "missing": [k for k in STUDENT_FIELDS if k not in fam],
            "invalid": invalid}


async def prepare_registration(ctx: Ctx, a: dict) -> dict:
    _, _, TR, _ = _engines()
    from booking_signer import basket_visits as BV, handover as HO
    from products.campus.slate import Session
    v = await BV.get(ctx.account, a["visit_id"])
    if not v:
        raise ToolError("visit_not_found", "there's no such visit in your tours — plan_tour first")
    if v["state"] == "registered":
        raise ToolError("already_registered", "the school has already confirmed that visit")
    if v["state"] not in BV.PREPARABLE:
        raise ToolError("visit_not_preparable", f"that visit is {v['state'].replace('_', ' ')}")
    snap = v["snapshot"]
    fam = await _student(ctx.account)
    miss = [k for k in STUDENT_FIELDS if k not in fam]
    if miss:
        raise ToolError("student_details_missing", f"still needed first: {', '.join(m.replace('_', ' ') for m in miss)}")
    page = {"kind": "link", "url": snap.get("link"), "why": None}
    if not snap.get("session") or not TR.live_school(snap["school"]):
        page["why"] = f"{snap['name']}'s form isn't one CampusMe fills — register on its own page with the details below"
    elif not HO.dpa_ok(ctx.account):
        page["why"] = ("a real student's details don't go through Kanoe's cloud browser until Kanoe has a signed data agreement "
                       "— register on the school's own page with the details below")
    elif not HO.configured():
        page["why"] = "the filled-form hand-over isn't available just now — register on the school's own page with the details below"
    if page["why"]:
        return {"visit_id": v["id"], "filled": False, "state": v["state"], "handoff": page, "copy": TR.copy_messages(fam),
                "left_for_you": ["everything on the school's page, including its Submit"]}
    try:
        rec = await TR.open_live(snap["school"], Session(**snap["session"]), fam, ctx.account)
    except HO.Refused as e:
        raise ToolError(e.rule, e.say)
    tap = await HO.tap_phone(ctx.account, rec)
    row = await BV.prepared(ctx.account, v["id"], rec.get("id"))
    return {"visit_id": v["id"], "filled": True, "state": row["state"],
            "handoff": {"kind": "handover", "url": HO.view_url(rec), "sent_to_phone": bool(tap.get("sent")), "expires_minutes": 10,
                        "why": None},
            "left_for_you": LEFT_FOR_FAMILY}


# ── Sherlock ───────────────────────────────────────────────────────────────────────────────────────────────────────────

async def check_confirmation(ctx: Ctx, a: dict) -> dict:
    _, _, TR, CF = _engines()
    from booking_signer import basket_visits as BV
    v = await BV.get(ctx.account, a["visit_id"])
    if not v:
        raise ToolError("visit_not_found", "there's no such visit in your tours")
    if v["state"] == "registered":
        return {"visit_id": v["id"], "confirmed": True, "state": "registered", "number": v.get("booking_reference"),
                "status_line": v.get("status_line"), "missing": [], "mismatches": []}
    snap, fam = v["snapshot"], await _student(ctx.account)
    rec = _school_rec(snap["school"]) or {"name": snap["name"]}
    school = {"name": rec["name"], "aliases": TR._aliases(snap["school"]), "full_name": rec.get("full_name", "")}
    session = snap.get("session") or {"day": snap.get("date"), "start": snap.get("start")}
    exp = CF.expect(school, session, fam.get("student_first", ""), fam.get("student_last", ""))
    r = CF.read(a["text"], exp, from_page=bool(a.get("from_page")))
    line = CF.line(exp, r)
    check = CF.record(r, "the school's page" if a.get("from_page") else "the school's email", datetime.now(timezone.utc).isoformat())
    if r["confirmed"]:
        row = await BV.registered(ctx.account, v["id"], r["number"], line, check)
    else:
        row = await BV.not_confirmed(ctx.account, v["id"], line, check)
    return {"visit_id": v["id"], "confirmed": r["confirmed"], "state": row["state"], "number": r["number"], "status_line": line,
            "missing": r["missing"], "mismatches": r["mismatches"]}


# ── Pacioli ────────────────────────────────────────────────────────────────────────────────────────────────────────────

async def get_campus(ctx: Ctx, a: dict) -> dict:
    from booking_signer import basket_visits as BV
    rows = await BV.items(ctx.account, a.get("trip_id"))
    return {"visits": [{"visit_id": r["id"], "trip_id": r["trip_id"], "school": r["provider_ref"], "name": r["snapshot"].get("name"),
                        "date": r["day"], "start": r["snapshot"].get("start"), "state": r["state"], "status_line": r.get("status_line"),
                        "number": r.get("booking_reference") if r["state"] == "registered" else None,
                        "register_page": r["snapshot"].get("link")} for r in rows],
            "anything_registered": any(r["state"] == "registered" for r in rows)}


# ── helpers ────────────────────────────────────────────────────────────────────────────────────────────────────────────

def _today() -> date:
    return datetime.now(timezone.utc).date()


def _day(s: str, field: str) -> date:
    try:
        return date.fromisoformat(s)
    except (TypeError, ValueError):
        raise ToolError(f"{field}_invalid", f"{field.replace('_', ' ')} must be a date, YYYY-MM-DD")


def _party(x) -> Optional[int]:
    try:
        n = int(x)
    except (TypeError, ValueError):
        return None
    return n if 1 <= n <= 9 else None


VISIT = {"type": "object", "properties": {"visit_id": {"type": "string"}, "school": {"type": "string"}, "date": DATE,
                                          "start": {"type": ["string", "null"]}, "state": {"type": "string"}}}
SOURCES = {"type": "array", "items": {"type": "object", "properties": {"label": {"type": "string"}, "url": {"type": ["string", "null"]},
                                                                        "read_at": {"type": ["string", "null"]}}}}
HANDOFF = {"type": "object", "properties": {"kind": {"enum": ["handover", "link"]}, "url": {"type": "string"},
                                            "sent_to_phone": {"type": "boolean"}, "why": {"type": ["string", "null"]}}}

TOOLS: List[dict] = [
    _t("find_schools", "Magellan", find_schools, "Which schools are named in what the person said, and whether CampusMe reads each "
       "one's own visit calendar (or only its published pattern, with the reason).", {"text": {"type": "string", "maxLength": 500}},
       ["text"], {"type": "object", "properties": {"schools": {"type": "array"}, "sources": SOURCES}}, ["no_school_named"]),
    _t("find_visit_sessions", "Magellan", find_visit_sessions, "One school's real visit sessions between two dates, read from the "
       "school's own calendar (open or full as the school shows it). Times and spaces come only from here.",
       {"school": {"type": "string"}, "start_date": DATE, "end_date": DATE, "attendees": {"type": "integer", "minimum": 1, "maximum": 5}},
       ["school", "start_date"], {"type": "object", "properties": {"sessions": {"type": "array"}, "sources": SOURCES}},
       ["school_unknown", "site_refuses_agents", "calendar_not_checked", "calendar_unreadable", "dates_invalid", "start_date_invalid"]),
    _t("plan_tour", "Magellan", plan_tour, "THE TOUR: schools in one week, in a sensible order — each school's own session where its "
       "calendar is read, drives checked with Google, a night near each next school. Saved as a journey with each visit as an "
       "item (suggested). Nothing is registered.",
       {"schools": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 6}, "week_of": DATE,
        "party": {"type": "integer", "minimum": 1, "maximum": 9}, "title": {"type": "string", "maxLength": 80}},
       ["schools", "week_of"], {"type": "object", "properties": {"trip_id": {"type": "string"}, "days": {"type": "array"},
                                                                  "visits": {"type": "array", "items": VISIT}, "sources": SOURCES}},
       ["school_unknown", "schools_invalid", "week_of_invalid", "week_of_past", "no_visits", "tour_not_saved", "visits_not_saved"]),
    _t("save_student", "Austen", save_student, "The student's and family's details the schools' forms ask for — asked once, kept on "
       "this account. Each is checked; what's invalid or still missing is returned.",
       {"details": {"type": "object", "additionalProperties": False, "properties": {
           "parent_name": {"type": "string"}, "student_name": {"type": "string"}, "email": {"type": "string"},
           "mobile": {"type": "string"}, "high_school": {"type": "string"}, "grad_year": {"type": "string"}, "major": {"type": "string"},
           "birthdate": {"type": "string"}, "address": {"type": "string"}, "party": {"type": "string"}}}},
       ["details"], {"type": "object", "properties": {"saved": {"type": "array"}, "missing": {"type": "array"}, "invalid": {"type": "array"}}},
       [], austen=True),
    _t("prepare_registration", "Austen", prepare_registration, "One visit: the school's own registration form filled with the "
       "student's details and STOPPED before the school's Submit; the hand-over goes to the person's phone, where they tick the "
       "school's statement and press its Submit themselves. Where the form can't be filled, the school's own page and the "
       "details to copy instead.", {"visit_id": {"type": "string"}}, ["visit_id"],
       {"type": "object", "properties": {"filled": {"type": "boolean"}, "state": {"type": "string"}, "handoff": HANDOFF,
                                         "left_for_you": {"type": "array"}}},
       ["visit_not_found", "already_registered", "visit_not_preparable", "student_details_missing", "no_dpa",
        "cloud_browser_not_configured"], austen=True),
    _t("check_confirmation", "Sherlock", check_confirmation, "After the person pressed the school's Submit: the school's own "
       "confirmation (its page, or its email pasted in) checked against the visit — school, student, day, time. Only a match "
       "makes the visit registered.", {"visit_id": {"type": "string"}, "text": {"type": "string", "maxLength": 20000},
                                       "from_page": {"type": "boolean"}}, ["visit_id", "text"],
       {"type": "object", "properties": {"confirmed": {"type": "boolean"}, "state": {"type": "string"}, "number": {"type": ["string", "null"]},
                                         "status_line": {"type": "string"}}}, ["visit_not_found"]),
    _t("get_campus", "Pacioli", get_campus, "The tours' visits and each one's state (suggested, prepared, registered, not "
       "confirmed) — the ONLY source for whether a visit is registered.", {"trip_id": {"type": "string"}}, [],
       {"type": "object", "properties": {"visits": {"type": "array", "items": VISIT}, "anything_registered": {"type": "boolean"}}}, []),
]
BY_NAME = {t["name"]: t for t in TOOLS}


async def call(ctx: Ctx, name: str, args: dict) -> dict:
    """The skill's one entry, exactly v0.call's contract: {"ok": true, "result"} or {"ok": false, "error": {code, message}}."""
    t = BY_NAME.get(name)
    if not t:
        return {"ok": False, "error": {"code": "unknown_tool", "message": f"no tool {name} in CampusMe"}}
    if ctx.mode != "test":
        return {"ok": False, "error": {"code": "mode_not_available", "message": f"AgAPI {V0.VERSION} runs in TEST mode only"}}
    args = dict(args or {})
    miss = [k for k in t["input_schema"]["required"] if args.get(k) in (None, "", [])]
    if miss:
        return {"ok": False, "error": {"code": "missing_input", "message": f"missing: {', '.join(miss)}"}}
    extra = [k for k in args if k not in t["input_schema"]["properties"]]
    if extra:
        return {"ok": False, "error": {"code": "unknown_input", "message": f"not an input of {name}: {', '.join(sorted(extra))}"}}
    key = f"{ctx.account}:{name}:{args['idempotency_key']}" if t["idempotent"] else None
    if key and key in _IDEM:
        return {**_IDEM[key], "replayed": True}
    t0 = time.perf_counter()
    try:
        res = {"ok": True, "result": await t["fn"](ctx, args)}
    except ToolError as e:
        res = {"ok": False, "error": {"code": e.code, "message": e.message}}
    except Exception as e:
        log.error("[campus] %s failed: %s: %s", name, type(e).__name__, e)
        res = {"ok": False, "error": {"code": "internal", "message": "that couldn't be done just now — nothing was changed by it"}}
    ctx.calls.append({"tool": name, "ok": res["ok"], "agent": t["agent"], "skill": SKILL, "ms": int((time.perf_counter() - t0) * 1000)})
    if key and res["ok"]:
        _IDEM[key] = res
    return res


def tools_for_model() -> List[dict]:
    return [V0.schema_for_model(t) for t in TOOLS]


# ── the guards on Sasha's words while the skill is open ─────────────────────────────────────────────────────────────────

_REGISTERED = re.compile(r"(?i)\b(?:(?:is|are|been|now|all|you're|you are|i've|i have|has been|have been|successfully)\s+(?:registered|signed up)"
                         r"|registration (?:is |has been )?(?:complete|confirmed|done)|registered ✓|✅\s*registered|you're (?:all )?set for)")
_MONEY = re.compile(r"[$€£]\s?(\d[\d,]*(?:\.\d+)?)")
_CLOCK = re.compile(r"(?i)\b(\d{1,2})(?::(\d{2}))?\s*(a\.?m\.?|p\.?m\.?)|\b([01]?\d|2[0-3]):([0-5]\d)\b")
_SPACES = re.compile(r"(?i)\b(\d+)\s+(?:spaces?|spots?|seats?|places?)\b")
_DRIVE = re.compile(r"(?i)\b(\d+)\s*h(?:ours?|rs?)?\s*(\d{1,2})?\b")


def _hhmm(m: re.Match) -> str:
    if m.group(1):
        h = int(m.group(1)) % 12 + (12 if m.group(3).lower().startswith("p") else 0)
        return f"{h:02d}:{int(m.group(2) or 0):02d}"
    return f"{int(m.group(4)):02d}:{m.group(5)}"


def _given(results: List[Any]) -> Dict[str, set]:
    """Every figure the tools gave this conversation: amounts, clock times, counts, drive times."""
    blob = json.dumps(results, default=str)
    return {"money": {float(x.replace(",", "")) for x in re.findall(r"(?<![\w.])(\d[\d,]*(?:\.\d+)?)(?![\w])", blob)},
            "clock": {_hhmm(m) for m in _CLOCK.finditer(blob)},
            "count": {int(x) for x in re.findall(r"(?<![\w.:])(\d+)(?![\w:])", blob)},
            "drive": {(int(h), int(m or 0)) for h, m in re.findall(r"\b(\d+) h (\d{2})\b", blob)} |
                     {(int(h), 0) for h in re.findall(r"\b(\d+) h\b(?! \d)", blob)}}


def guard_check(text: str, results: List[Any], visits: List[dict]) -> List[str]:
    """What's wrong with Sasha's reply while CampusMe is open: a registration claimed that Pacioli hasn't recorded, or a figure
    (price, time, spaces, drive) that no tool gave. Empty = fine. (The agent loop rewrites once, then replaces — wiring note.)"""
    bad, t = [], text or ""
    registered = [v for v in visits if v.get("state") == "registered"]
    if _REGISTERED.search(t):
        names = {(v.get("name") or "").lower() for v in visits}
        said = {n for n in names if n and n in t.lower()}
        ok = {(v.get("name") or "").lower() for v in registered}
        if not registered or (said and not said <= ok):
            bad.append("claim: it says registered, but the school's confirmation hasn't been checked and recorded")
    g = _given(results)
    for m in _MONEY.findall(t):
        v = float(m.replace(",", ""))
        if not any(abs(v - x) <= max(0.5, x * 0.005) for x in g["money"]):
            bad.append(f"figure: {m} did not come from a tool")
    for m in _CLOCK.finditer(t):
        if _hhmm(m) not in g["clock"]:
            bad.append(f"figure: the time {m.group(0).strip()} did not come from a tool")
    for n in _SPACES.findall(t):
        if int(n) not in g["count"]:
            bad.append(f"figure: {n} spaces did not come from a tool")
    for h, m in _DRIVE.findall(t):
        if (int(h), int(m or 0)) not in g["drive"]:
            bad.append(f"figure: a {h} h drive did not come from a tool")
    return bad


def idem_key(account: str, name: str, args: dict, turn: str) -> str:
    """The idempotency key the agent loop fills for an Austen call (the model never supplies it): same turn, same call → same key."""
    return hashlib.sha256(f"{account}|{name}|{turn}|{json.dumps(args, sort_keys=True)}".encode()).hexdigest()[:40]
