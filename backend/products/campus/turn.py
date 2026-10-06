"""CR 1 · CampusMe on WhatsApp: ask → the schools' own calendars → cards → pick → the student's details (vault) → one
yes on the exact read-back → the hand-over (the school's form, prepared) → the parent presses → "REGISTERED" → the
visit in their bookings and calendar → the school's own confirmation pasted → "confirmed in their words".

⛔ No submit exists in this module. ⛔ No declaration or consent is ever ticked for anyone. The model is never called.
State lives in the guest's `pending` (kind "product") and, from the yes on, in a product case (store.py).
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import urllib.parse
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from booking_signer import yes as YS

from .. import store as ST
from . import handover as HV
from . import request as RQ
from . import schools as SC
from . import slate as SL
from .slate import Session

log = logging.getLogger("products.campus")

PROVIDER = "kanoe.ai"            # the vault names a provider by its address; the label says CampusMe
LABEL = "CampusMe student details"
APPROVAL_WINDOW = timedelta(minutes=15)
CARDS_PER_SCHOOL = (3, 2, 1)      # by how many schools were asked for
DAYS_READ_MAX = 4                 # days read per school per ask (each a request or three)

INTRO = ("CampusMe here 🎓 I read each university's own visit calendar, show you real sessions, prepare the school's "
         "registration form with your student's details, and you press Register. Tell me the schools and the month, e.g. "
         "\"Yale and Penn in November for my son\". Anything else — a booking, a flight — just ask; we'll come back to this.")
NO_SUBMIT = "I prepare the form; you press Register on the school's own page — CampusMe never submits it."


def web() -> str:
    return os.getenv("SASHA_WEB_URL", "https://project.kanoe.ai").rstrip("/")


def day_words(iso: str) -> str:
    return date.fromisoformat(iso).strftime("%a %-d %b")


def time_words(hhmm: str) -> str:
    h, m = map(int, hhmm.split(":"))
    return f"{(h % 12) or 12}:{m:02d} {'AM' if h < 12 else 'PM'}"


def _who(ask: dict) -> Tuple[str, str]:
    """('your son', 'his') — the family's own word; neutral when they didn't give one."""
    w = (ask or {}).get("who")
    if w in ("son", "grandson", "nephew"):
        return f"your {w}", "his"
    if w in ("daughter", "granddaughter", "niece"):
        return f"your {w}", "her"
    if w in ("myself", "me"):
        return "you", "your"
    return "the student", "the student's"


# ── reading the calendars ─────────────────────────────────────────────────────────────────────────────────────────────

async def find(ask: RQ.Ask, today: date, reader: Optional[SL.Reader] = None) -> List[dict]:
    """Per school: {school, sessions:[…], published_until, opened, why}. Schools are read in parallel (each host paced)."""
    start, end = ask.span(today)
    start = max(start, today)
    per = CARDS_PER_SCHOOL[min(len(ask.schools), 3) - 1] if ask.schools else 0
    attendees = 1 + ask.guests

    async def one(s: dict) -> dict:
        res = {"school": s["key"], "sessions": [], "published_until": None, "opened": False, "why": None}
        if not s.get("proven"):
            res["why"] = f"{s['name']} is on CampusMe's list but its calendar hasn't been read and checked yet"
            return res
        try:
            # one read from today to the end of the asked span: the month's days AND how far ahead the school publishes
            ds, _ = await SL.dates(s, today, max(end, today), reader)
            res["published_until"] = max((d for d, _ in ds), default=None)
            avail = [d for d, ok in ds if ok and start.isoformat() <= d <= end.isoformat()]
            res["opened"] = any(start.isoformat() <= d <= end.isoformat() for d, _ in ds)
            # the first open day's sessions first: every extra day is another paced read (three at Penn), and the room waits
            for d in avail[:DAYS_READ_MAX]:
                for x in await SL.sessions(s, d, attendees, reader):
                    if x.status == "open" and len(res["sessions"]) < per:
                        res["sessions"].append(x.as_dict())
                if len(res["sessions"]) >= per:
                    break
            if avail and not res["sessions"]:
                res["why"] = "every session I read on its open days was full"
        except SL.ReadRefused as e:
            res["why"] = str(e)
        except Exception as e:   # a school's page failing never sinks the other school's answer
            log.error("[campus] reading %s failed: %s: %s", s["key"], type(e).__name__, e)
            res["why"] = f"{s['name']}'s calendar couldn't be read just now ({type(e).__name__})"
        return res

    return list(await asyncio.gather(*(one(s) for s in ask.schools)))


def card_line(n: int, x: dict) -> str:
    s = SC.SCHOOLS[x["school"]]
    spaces = (f" · {x['spaces']} space{'s' if x['spaces'] != 1 else ''} left" if x.get("spaces") is not None else " · open")
    loc = f" · {x['location']}" if x.get("location") else ""
    return f"{n}. *{s['name']}* — {x['title'].split(' · ')[0]}\n{day_words(x['day'])}, {time_words(x['start'])}{loc}{spaces}"


# ── the turn ──────────────────────────────────────────────────────────────────────────────────────────────────────────

async def turn(ctx: dict, body: str, payload: str, *, entering: bool) -> None:
    pend = ctx["st"]["pending"]
    out = ctx["out"]
    step = pend.get("step")
    if entering and not body.strip():
        out.text(INTRO)
        pend["step"] = "ask"
        pend["intro_said"] = True
        return
    if step == "confirm":
        if await _answer_yes(ctx, body, payload):
            return
    if step == "profile":
        await _profile_answer(ctx, body)
        return
    if step == "save":
        await _save_answer(ctx, body, payload)
        return
    if step == "cards":
        pick = _pick(pend, body, payload)
        if pick is not None:
            await _picked(ctx, pick)
            return
        a = RQ.parse(body, ctx["now"].date())
        if not (a.schools or a.month or a.day or a.dom or a.unreadable) and (a.who or _PARTY.search(body)):
            # CR 30 · "for my son, 2 people" while sessions are on screen: noted, and the same sessions asked about again
            pend["ask"] = RQ.to_state(RQ.merge(RQ.from_state(pend.get("ask") or {}), a))
            n = len(pend.get("cards") or [])
            out.text(f"Noted{' — for your ' + a.who if a.who and a.who not in ('me', 'myself') else ''}. Which session? "
                     f"Reply with its number, 1–{n}, or a day (e.g. \"the 14th\").")
            return
    if step == "handed_over" and re.match(r"^\s*(registered|done|booked|i registered|we registered)\b", body, re.I):
        await _registered(ctx)
        return
    if step in ("registered", "handed_over") and await _pasted_confirmation(ctx, body):
        return
    await _new_ask(ctx, body)


async def _new_ask(ctx: dict, body: str) -> None:
    pend, out, now = ctx["st"]["pending"], ctx["out"], ctx["now"]
    today = now.date()
    a = RQ.parse(body, today)
    if pend.get("ask") and pend.get("step") in ("ask", "cards"):    # CR 30 · a day said over the list keeps the school and month
        a = RQ.merge(RQ.from_state(pend["ask"]), a)
    pend["ask"] = RQ.to_state(a)
    for why in a.unreadable:
        out.text(f"ⓘ {why}.")
    q = a.missing()
    if q:
        pend["step"] = "ask"
        # CR 30 · the intro once; after it, only the one thing still missing ("campus tours" used to bring the intro back)
        out.text(q if a.schools or a.unreadable or a.month or pend.get("intro_said") else INTRO)
        pend["intro_said"] = True
        return
    if not a.schools:
        pend["step"] = "ask"
        out.text("None of those are schools CampusMe reads yet. It reads Yale and Penn today.")
        return
    names = " and ".join(s["name"] for s in a.schools)
    await ctx["early"](f"Reading {names}'s own visit calendar{'s' if len(a.schools) > 1 else ''} for {a.when_words()}…")
    found = await find(a, today, ctx.get("reader"))
    cards: List[dict] = []
    notes: List[str] = []          # one message for every school without cards: the sandbox sends one every 3.1 s
    for f in found:
        s = SC.SCHOOLS[f["school"]]
        if not f["sessions"]:
            start, _ = a.span(today)
            if f["published_until"] and f["published_until"] < start.isoformat():
                notes.append(f"⏳ *{s['name']}* hasn't published {a.when_words()} yet — its calendar runs to "
                             f"{date.fromisoformat(f['published_until']).strftime('%-d %B %Y')}.")
                pend.setdefault("watch", []).append({"school": s["key"], "month": list(a.month) if a.month else None,
                                                     "since": now.isoformat()})
            else:
                notes.append(f"⚠ *{s['name']}*: {f['why'] or 'no open session in ' + a.when_words()}.")
            continue
        cards.extend(f["sessions"])
    if pend.get("watch"):
        notes.append(f"I'll check daily and message you the day {a.when_words().split()[0]} opens.")
    if notes:
        out.text("\n".join(notes))
    if pend.get("watch"):
        await _keep_watch(ctx, a)
    if not cards:
        pend["step"] = "ask"
        out.text("Want me to look at another month? Just name it, e.g. \"November\".")
        return
    srcs = sorted({SC.SCHOOLS[x['school']]['host'] for x in cards})
    n = len(cards)
    body = "\n\n".join(card_line(i, x) for i, x in enumerate(cards, 1)) + \
        f"\n\nRead just now from {', '.join(srcs)} — the schools' own calendars. Spaces change; I re-check before you register."
    nonce = hashlib.sha256(json.dumps(cards, sort_keys=True).encode()).hexdigest()[:8]
    if n <= 3:
        out.text(body)
        out.ask("Which one?", [(f"{i}. {SC.SCHOOLS[x['school']]['name']} {day_words(x['day']).split(' ', 1)[1]}", f"cm:{nonce}:{i - 1}")
                               for i, x in enumerate(cards, 1)])
    else:
        out.text(body + f"\n\nWhich one? Reply with a number, 1–{n}.")
    pend.update(step="cards", cards=cards, nonce=nonce, cards_at=now.isoformat())


def _pick(pend: dict, body: str, payload: str) -> Optional[int]:
    cards = pend.get("cards") or []
    m = re.match(rf"^cm:{pend.get('nonce')}:(\d+)$", payload or "")
    if m:
        i = int(m.group(1))
    else:
        m = re.match(r"^\s*#?(\d)\b", body or "")
        if not m:
            return None
        i = int(m.group(1)) - 1
    return i if 0 <= i < len(cards) else None


async def _vault_item(account: str) -> Optional[dict]:
    try:
        from booking_signer.vault import crypto as VC
        rows = await VC.STORE.list(account)
    except Exception as e:
        log.info("[campus] vault not readable: %s", type(e).__name__)
        return None
    return next((r for r in rows if is_profile(r)), None)


def is_profile(r: dict) -> bool:
    return (not r.get("revoked_at") and r.get("kind") == "identifier" and str(r.get("provider") or "").lower() == PROVIDER
            and str(r.get("label") or "").startswith(LABEL))


PROFILE_ASKS = [
    ("name", "What's {who}'s full name, as it should appear on the registration? (first and last)"),
    ("email", "{Their} email address? The school sends the confirmation there."),
    ("birthdate", "{Their} date of birth? (e.g. 14 March 2009)"),
    ("high_school", "Which high school does {who} attend?"),
    ("grad_year", "Which year does {who} graduate from high school? (e.g. 2028)"),
]


def _ask_profile(pend: dict, out) -> None:
    have = pend.get("profile") or {}
    who, their = _who(pend.get("ask"))
    for k, q in PROFILE_ASKS:
        if (k == "name" and not have.get("first")) or (k != "name" and not have.get(k)):
            pend["step"], pend["asking"] = "profile", k
            out.text(q.format(who=who, Their=their[:1].upper() + their[1:]))
            return
    pend["asking"] = None


async def _picked(ctx: dict, i: int) -> None:
    pend, out = ctx["st"]["pending"], ctx["out"]
    x = pend["cards"][i]
    pend["chosen"] = x
    item = await _vault_item(ctx["account"])
    if item:
        pend["vault"] = {"id": str(item["id"]), "label": item["label"]}
        await _read_back(ctx)
        return
    pend["profile"] = {}
    s = SC.SCHOOLS[x["school"]]
    out.text(f"{s['name']}, {day_words(x['day'])} at {time_words(x['start'])} — good. I don't have the student's details yet; "
             f"five quick questions (asked once — I can keep them in your vault for next time).")
    _ask_profile(pend, out)


_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[a-z]{2,}$", re.I)


def parse_birthdate(t: str) -> Optional[str]:
    t = t.strip()
    for fmt in ("%d %B %Y", "%B %d %Y", "%B %d, %Y", "%d %b %Y", "%b %d %Y", "%b %d, %Y", "%Y-%m-%d", "%m/%d/%Y"):
        try:
            d = datetime.strptime(t, fmt).date()
            return d.isoformat() if 1990 < d.year < 2020 else None
        except ValueError:
            continue
    return None


async def _profile_answer(ctx: dict, body: str) -> None:
    pend, out = ctx["st"]["pending"], ctx["out"]
    p = pend.setdefault("profile", {})
    k, t = pend.get("asking"), (body or "").strip()
    bad = None
    if k == "name":
        parts = t.split()
        if len(parts) >= 2:
            p["first"], p["last"] = parts[0], " ".join(parts[1:])
        else:
            bad = "First and last name, please — e.g. \"Sam Warren\"."
    elif k == "email":
        if _EMAIL.match(t):
            p["email"] = t
        else:
            bad = "That doesn't look like an email address — try again?"
    elif k == "birthdate":
        d = parse_birthdate(t)
        if d:
            p["birthdate"] = d
        else:
            bad = "Please write it like \"14 March 2009\"."
    elif k == "high_school":
        if len(t) >= 3:
            p["high_school"] = t
        else:
            bad = "The school's name, please."
    elif k == "grad_year":
        m = re.search(r"\b(20[2-3]\d)\b", t)
        if m and now_year(ctx) <= int(m.group(1)) <= now_year(ctx) + 6:
            p["grad_year"] = m.group(1)
        else:
            bad = "The graduation year, e.g. 2028."
    if bad:
        out.text(bad)
        return
    _ask_profile(pend, out)
    if pend.get("asking") is None:
        pend["step"] = "save"
        out.ask(f"Keep {p['first']}'s details in your vault (encrypted, deletable any time) so next time is one tap?",
                [("Yes, keep them", "cm:save:yes"), ("Just this once", "cm:save:no")])


def now_year(ctx: dict) -> int:
    return ctx["now"].year


async def _save_answer(ctx: dict, body: str, payload: str) -> None:
    pend, out = ctx["st"]["pending"], ctx["out"]
    keep = payload == "cm:save:yes" or (not payload and YS.is_yes(body))
    if keep:
        label = f"{LABEL} ({pend['profile']['first']})"
        try:
            from booking_signer.guest_whatsapp import api
            status, j = await api(ctx["account"], "POST", "/api/booking/vault",
                                  {"provider": PROVIDER, "label": label, "kind": "identifier",
                                   "fields": {"value": json.dumps(pend["profile"], sort_keys=True)}})
        except Exception as e:
            status, j = 0, {"message": type(e).__name__}
        if status in (200, 201):
            item_id = str(j.get("id") or (j.get("item") or {}).get("id") or "")
            if item_id:
                pend["vault"] = {"id": item_id, "label": label}
                pend["profile_saved"] = True
                out.text(f"Kept in your vault as “{label}”. It's opened only inside a registration you say yes to.")
        if not pend.get("vault"):
            out.text("I couldn't keep them in your vault just now — I'll use them for this registration only.")
    await _read_back(ctx)


def read_back_lines(x: dict, ask: dict, profile: Optional[dict], vault: Optional[dict], ref: str = "") -> List[str]:
    from booking_signer.vault.crypto import access_line
    s = SC.SCHOOLS[x["school"]]
    guests = int((ask or {}).get("guests", 1))
    who, _ = _who(ask)
    lines = []
    if vault and not profile:
        lines.append(access_line(PROVIDER, vault["label"], "identifier"))
    elif profile:
        lines.append(f"Student: {profile['first']} {profile['last']} · {profile['email']} · born "
                     f"{HV.birth_words(profile['birthdate'])} · {profile['high_school']} · graduating {profile['grad_year']}.")
    spaces = f", {x['spaces']} spaces left when read" if x.get("spaces") is not None else ""
    lines += [
        f"{s['full_name']}: {x['title'].split(' · ')[0]}, {date.fromisoformat(x['day']).strftime('%A %-d %B %Y')} at "
        f"{time_words(x['start'])} ({s['city']} time){spaces}.",
        f"Registering {who} as the prospective student, with {guests} guest{'s' if guests != 1 else ''}.",
        f"I'll prepare {s['name']}'s own registration form and stop before its Register button: you press it. "
        f"I send nothing to {s['name']}.",
        f"Registering creates a record for the student in {s['name']}'s admissions system, and the school will email them.",
    ]
    if ref:   # CR 2 · one vault use per yes is keyed by this read-back's hash: the same session asked twice must be two yeses
        lines.append(f"Ref {ref}.")
    return lines


async def _read_back(ctx: dict) -> None:
    pend, out = ctx["st"]["pending"], ctx["out"]
    profile = None if pend.get("profile_saved") else (pend.get("profile") or None)
    ref = "CM-" + hashlib.sha256(f"{ctx['account']}|{ctx['now'].isoformat()}".encode()).hexdigest()[:6].upper()
    lines = read_back_lines(pend["chosen"], pend.get("ask"), profile, pend.get("vault"), ref)
    sha = hashlib.sha256("\n".join(lines).encode()).hexdigest()
    out.text("Exactly what I'll do:\n" + "\n".join("• " + ln for ln in lines))
    out.ask("Prepare it?", [("Yes, prepare it", f"cmyes:{sha[:16]}"), ("No", f"cmno:{sha[:16]}")])
    pend.update(step="confirm", lines=lines, sha=sha, asked_at=ctx["now"].isoformat())


async def _answer_yes(ctx: dict, body: str, payload: str) -> bool:
    pend, out, now = ctx["st"]["pending"], ctx["out"], ctx["now"]
    sha = pend.get("sha") or ""
    if payload == f"cmno:{sha[:16]}" or (not payload and re.match(r"^\s*(no|nope|not now)\b", body, re.I)):
        pend["step"] = "cards" if pend.get("cards") else "ask"
        out.text("OK — nothing prepared. Pick another session, or name another month.")
        return True
    said_yes = payload == f"cmyes:{sha[:16]}" or (not payload and YS.is_yes(body))
    if payload and payload.startswith(("cmyes:", "cmno:")) and not said_yes:
        out.text("That button belonged to an earlier question — nothing was done.")
        return True
    if not said_yes:
        return False
    if now - datetime.fromisoformat(pend["asked_at"]) > APPROVAL_WINDOW:
        out.text("That yes came more than 15 minutes after I asked — spaces may have changed. Pick the session again?")
        pend["step"] = "cards"
        return True
    await _prepare(ctx, {"how": "whatsapp_button" if payload else "whatsapp_text", "said": body, "at": now.isoformat(),
                         "read_back_sha256": sha})
    return True


async def _open_profile(ctx: dict, pend: dict, approval: dict) -> Dict[str, str]:
    if pend.get("profile") and not pend.get("profile_saved"):
        return dict(pend["profile"])
    from booking_signer.vault import crypto as VC
    async with VC.use(ctx["account"], pend["vault"]["id"], approval=approval, approved_lines=pend["lines"],
                      action_kind="campusme_prepare", action_ref=f"campus-{pend['sha'][:12]}") as secret:
        return json.loads(secret.get("value") or "{}")


async def _prepare(ctx: dict, approval: dict) -> None:
    pend, out, now = ctx["st"]["pending"], ctx["out"], ctx["now"]
    x = pend["chosen"]
    s = SC.SCHOOLS[x["school"]]
    attendees = 1 + int((pend.get("ask") or {}).get("guests", 1))
    # the session is re-read first: spaces change, and a hand-over for a full session would waste the family's time
    try:
        fresh = [y for y in await SL.sessions(s, x["day"], attendees, ctx.get("reader"))
                 if y.start == x["start"] and y.title == x["title"]]
    except SL.ReadRefused as e:
        out.text(f"❌ Not prepared: {e}.")
        return
    if not fresh or fresh[0].status != "open":
        out.text(f"⚠ That session just filled up on {s['name']}'s calendar — nothing prepared. Pick another?")
        pend["step"] = "cards"
        return
    session = fresh[0]
    try:
        profile = await _open_profile(ctx, pend, approval)
    except Exception as e:
        out.text(f"❌ Not prepared: your saved student details couldn't be opened ({e}).")
        return
    try:
        questions, challenge, receipt, pages = await SL.form(session.form_url, ctx.get("reader"))
    except SL.ReadRefused as e:
        out.text(f"❌ Not prepared: {e}.")
        return
    from_vault = bool(pend.get("vault")) and (pend.get("profile_saved") or not pend.get("profile"))
    src = "your vault" if from_vault else "what you told me on WhatsApp"
    rows = HV.plan(questions, profile, session, attendees, src)
    case = {"school": s["key"], "session": session.as_dict(), "form_url": session.form_url, "form_read": receipt,
            "form_pages": pages, "challenge_seen": challenge, "rows": rows, "approval": approval, "lines": pend["lines"],
            "student_first": profile.get("first"), "status": "handed_over", "ask": pend.get("ask")}
    cid = await ST.STORE.put("campus", ctx["account"], ctx["ch"]["wa_id_sha256"], case)
    link = f"{web()}/campus-handover/{cid}"
    c = HV.counts(rows)
    out.text(f"✅ Prepared. {s['name']}'s form, answered question by question — {c.get('fill', 0) + c.get('choose', 0)} "
             f"filled from {src}, {c.get('you', 0)} for you to answer or tick yourself:\n{link}")
    tail = []
    if pages > 1:
        tail.append(f"The form has {pages} pages; I've read page 1 — page 2 shows after you continue.")
    if challenge:
        tail.append("Its page carries a CAPTCHA: that's yours to answer.")
    out.text("Open it, check each answer, then press Register on " + s["name"] + "'s own page. " + " ".join(tail) +
             "\nReply REGISTERED once you've pressed it.")
    pend.update(step="handed_over", case_id=cid)
    # CR 33 · the founder's own account: the school's real form, filled live in Sasha's browser; SUBMIT stays his
    from booking_signer import handover as HO
    if HO.founder_override(ctx["account"]) and s.get("variant") == "register" and HO.configured():
        out.text(f"I'm also filling {s['name']}'s own form for you in Sasha's browser — a link comes to your phone in about "
                 "20 seconds: tick “Yes, I understand”, then pressing SUBMIT is yours (or not). I send nothing to "
                 f"{s['name']}.")
        from booking_signer import guest_whatsapp as GW
        GW._spawn(_live(ctx["account"], ctx["ch"]["wa_id_sha256"], ctx["frm"], cid, session, dict(profile), attendees))


async def _live(account: str, wa: str, frm: str, cid: str, session, profile: dict, attendees: int) -> None:
    """CR 33 · in the background (filling takes seconds): the live hand-over, then ONE tap to the phone. The student's details
    live only in this task's memory and the cloud page; never stored."""
    from booking_signer import guest_whatsapp as GW, handover as HO
    from .. import whatsapp as PW
    from . import live as LV

    async def say(text: str) -> None:
        ch, _, number = await PW.reach(wa, frm, account)
        if ch:
            gst = await GW.STORE.get_state(ch["wa_id_sha256"])
            await GW.deliver(ch, number, GW.Out().text(text), gst.get("last_inbound_at"))
    try:
        rec = await LV.open_campus_handover(session=session, profile=profile, attendees=attendees, account=account,
                                            read_only=False, fictional=False)
    except HO.Refused as e:
        await say(f"I couldn't open the live form: {e.say}. The question-by-question page I sent still works.")
        return
    case = await ST.STORE.get(cid)
    if case:
        case["state"]["live_handover"] = {"id": rec["id"], "ready_ms": rec.get("ready_ms"), "at": rec.get("ready_at")}
        await ST.STORE.update(cid, case["state"])
    tap = await HO.tap_phone(account, rec)
    if not tap.get("sent"):
        await say(f"📲 {rec['venue']} is filled and waiting (10 minutes): {HO.view_url(rec)}")


async def _live_done(pub: dict) -> None:
    """The school's reply after the parent's own SUBMIT → the campus case (its words, not ours)."""
    for c in await ST.STORE.of_product("campus"):
        if (c["state"].get("live_handover") or {}).get("id") == pub.get("id"):
            st = c["state"]
            st["live_handover"].update(state=pub.get("state"), say=pub.get("say"), pressed_at=pub.get("pressed_at"))
            if pub.get("state") == "booked":
                st["status"] = "registered_by_you_on_their_page"
            await ST.STORE.update(c["id"], st)


def _hook() -> None:
    from . import live as LV
    if _live_done not in LV.CAMPUS_DONE:
        LV.CAMPUS_DONE.append(_live_done)


_hook()


async def _registered(ctx: dict) -> None:
    from . import visits as VS
    pend, out = ctx["st"]["pending"], ctx["out"]
    cid = pend.get("case_id")
    case = await ST.STORE.get(cid) if cid else None
    if not case:
        out.text("I can't find that registration any more — it may have expired.")
        return
    st = case["state"]
    x, s = st["session"], SC.SCHOOLS[st["school"]]
    item = await VS.record(ctx["account"], s, x, 1 + int((st.get("ask") or {}).get("guests", 1)))
    st.update(status="registered_on_your_word", registered_at=ctx["now"].isoformat(), trip_item_id=item)
    await ST.STORE.update(cid, st)
    out.text(f"Noted — registered on your word: {s['name']}, {date.fromisoformat(x['day']).strftime('%A %-d %B')} at "
             f"{time_words(x['start'])}. {'It’s in your bookings (You → My bookings), and I’ll remind you the day before. ' if item else ''}"
             f"I'll call it confirmed when {s['name']}'s own confirmation email says so — paste it here when it arrives.")
    out.text(f"📅 Add it to your calendar: {VS.google_link(s, x)}\nor download it: {web()}/api/products/campus/{cid}/visit.ics")
    pend["step"] = "registered"


async def _pasted_confirmation(ctx: dict, body: str) -> bool:
    from . import visits as VS
    pend, out = ctx["st"]["pending"], ctx["out"]
    cid = pend.get("case_id")
    if len(body or "") < 40 or not cid:
        return False
    case = await ST.STORE.get(cid)
    if not case:
        return False
    st = case["state"]
    x, s = st["session"], SC.SCHOOLS[st["school"]]
    d = date.fromisoformat(x["day"])
    says_school = any(a in body.lower() for a in s["aliases"] + [s["full_name"].lower()])
    says_day = bool(re.search(rf"\b{d.strftime('%B')}\s+{d.day}\b|\b{d.day}\s+{d.strftime('%B')}\b|{d.isoformat()}|\b{d.month}/{d.day}/", body, re.I))
    says_confirmed = bool(re.search(r"\b(confirm|registered|registration|see you|we look forward)", body, re.I))
    if not says_confirmed:
        return False
    if not (says_school and says_day):
        out.text(f"That reads like a confirmation, but it doesn't name {s['name']} and {d.strftime('%-d %B')} — so I've "
                 "left the visit as \"registered on your word\".")
        return True
    quote = re.sub(r"\s+", " ", body).strip()[:300]
    st.update(status="confirmed_in_writing", confirmation_quote=quote, confirmed_at=ctx["now"].isoformat())
    await ST.STORE.update(cid, st)
    await VS.confirm(st.get("trip_item_id"))
    out.text(f"✅ Confirmed in {s['name']}'s own words: “{quote[:200]}…”")
    pend["step"] = "done"
    return True


async def _keep_watch(ctx: dict, a: RQ.Ask) -> None:
    """The month isn't published: the watch is kept on a case, read daily by watch.tick (one read per school)."""
    pend = ctx["st"]["pending"]
    watch = {"open": True, "schools": [w["school"] for w in pend.get("watch") or []], "month": list(a.month) if a.month else None,
             "wa": ctx["ch"]["wa_id_sha256"], "number_from": ctx["frm"], "since": ctx["now"].isoformat()}
    try:
        await ST.STORE.put("campus", ctx["account"], ctx["ch"]["wa_id_sha256"], {"watch": watch, "ask": pend.get("ask"),
                                                                                  "status": "watching"})
    except Exception as e:
        log.error("[campus] the watch wasn't kept: %s", type(e).__name__)
    pend.pop("watch", None)


# ── CR 10 · one Sasha: is this message an answer to CampusMe's own question? And what context goes to Sasha ─────────

_PARTY = re.compile(r"(?i)\b(\d+|two|three|four)\s+(people|persons|of us|guests)\b")


def claims(pend: dict, body: str, payload: str, media: list) -> bool:
    step, t = pend.get("step"), (body or "").strip()
    if payload.startswith(("cm:", "cmyes:", "cmno:")):
        return True
    if step == "ask":
        a = RQ.parse(t, date.today())
        return bool(a.schools or a.unreadable or a.month or a.day or a.dom or re.search(r"(?i)\b(campus|tour|visit)", t))
    if step == "cards":
        a = RQ.parse(t, date.today())
        return _pick(pend, t, payload) is not None or bool(a.schools or a.month or a.day or a.dom or a.unreadable or a.who
                                                            or _PARTY.search(t))
    if step == "profile":
        k = pend.get("asking")
        return {"name": lambda: len(t.split()) >= 2 and not re.search(r"\d", t),
                "email": lambda: bool(_EMAIL.match(t)),
                "birthdate": lambda: bool(parse_birthdate(t)),
                "high_school": lambda: len(t) >= 3,
                "grad_year": lambda: bool(re.search(r"\b20[2-3]\d\b", t))}.get(k, lambda: False)()
    if step in ("save", "confirm"):
        return YS.is_yes(t) or bool(re.match(r"(?i)^\s*(no|nope|not now|just this once)\b", t))
    if step == "handed_over":
        return bool(re.match(r"(?i)^\s*(registered|done|booked|i registered|we registered)\b", t)) or \
            (len(t) >= 40 and bool(re.search(r"(?i)\b(confirm|registered|registration)", t)))
    if step == "registered":
        return len(t) >= 40 and bool(re.search(r"(?i)\b(confirm|registered|registration)", t))
    return False


def context(pend: dict) -> dict:
    a = RQ.from_state(pend["ask"]) if pend.get("ask") else None
    x = pend.get("chosen") or {}
    schools = [s["name"] for s in (a.schools if a else [])]
    cities = [SC.SCHOOLS[x["school"]]["city"]] if x.get("school") else [s["city"] for s in (a.schools if a else [])]
    dates = [x["day"]] if x.get("day") else ([a.when_words()] if a and (a.month or a.day) else [])
    return {"product": "campus", "city": ", ".join(dict.fromkeys(cities)) or None, "country": "United States",
            "dates": dates, "name": None, "line": f"[CampusMe: campus visits — {' and '.join(schools) or 'universities'}"
            + (f" ({'; '.join(dict.fromkeys(cities))})" if cities else "") + (f", {dates[0]}" if dates else "") + "]"}
