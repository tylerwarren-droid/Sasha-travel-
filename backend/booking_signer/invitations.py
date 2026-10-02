"""S-80 · "BOOK DINNER WITH JON THIS WEEK" — two guests, one booking, consent on both sides. Path I first.

The rules (S-80 §0), enforced here:
  1. Sasha never writes first to someone who hasn't opted in. The INVITER sends the invitation from their own WhatsApp
     (a wa.me share link, no number given to us); Jon opens a web page. Only if Jon sends "INVITE {code}" himself does
     Sasha message him — about THIS invitation only (no general chat opens; S-75's scope gate still answers him).
  2. Jon's consent is his own and per invitation: picking a time shares only his choice with the inviter.
  3. Minimisation: Jon sees the inviter's FIRST NAME, the activity, the slots and the outcome — never a phone, an email,
     another booking or a calendar; the inviter sees Jon's first name and choice, never his number. Free/busy is
     combined here into slots; only the slots are shown.
  4. The booking is the INVITER's: their read-back, their yes, their name. Jon's choice picks a slot; it places nothing.
"""
from __future__ import annotations

import hashlib
import logging
import os
import re
import secrets
import time
import uuid
from collections import defaultdict, deque
from datetime import date, datetime, time as dtime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

from fastapi import APIRouter, BackgroundTasks, Request
from fastapi.responses import JSONResponse

from . import sentences as SN
from .store import StorageUnavailable

log = logging.getLogger("booking_signer.invitations")
NOW = lambda: datetime.now(timezone.utc)
TZ = "Europe/Madrid"
#: A-1 · the hours per activity (local); a slot is two hours from its start
HOURS = {"dinner": ((20, 30), (22, 30)), "lunch": ((13, 30), (15, 30)), "breakfast": ((9, 0), (10, 30)),
         "brunch": ((11, 0), (13, 0)), "drinks": ((19, 0), (22, 0))}
PREFERRED = {"dinner": (21, 0), "lunch": (14, 0), "breakfast": (9, 30), "brunch": (12, 0), "drinks": (20, 0)}
SLOT_LEN = timedelta(hours=2)
MAX_DAYS = 7
CONSENT_TEXT = ("Sasha by Kanoe (an AI assistant) is booking {activity} for {inviter} and you. Picking a time shares only "
                "your choice with {inviter}. Nothing else about you is stored unless you ask Sasha to message you.")
JOINED = "You'll hear from Sasha about this {activity} only. Reply STOP to stop."
BAD_INVITE = "That invitation code didn't work — it may have expired. Ask whoever invited you for a new link."


def web_base() -> str:
    return os.getenv("SASHA_WEB_URL", "https://project.kanoe.ai").rstrip("/")


# ── §4.1 · the intent ───────────────────────────────────────────────────────────────────────────────────────────────

_ACT = r"(dinner|lunch|breakfast|brunch|drinks|a table|cena|comida|almuerzo|desayuno)"
_NAME = r"((?-i:[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+)?))"   # a capitalised name, even under re.I
_WITH = re.compile(rf"\b{_ACT}\b[^.?!]*?\b(?:with|con)\s+{_NAME}", re.I)
_INVITE = re.compile(rf"\binvit(?:e|ar|a)\s+{_NAME}\s+(?:to|for|a)\s+(?:a\s+)?{_ACT}", re.I)
_ME_AND = re.compile(rf"\b{_ACT}\b[^.?!]*?\bfor\s+me\s+and\s+{_NAME}", re.I)
_ACT_EN = {"cena": "dinner", "comida": "lunch", "almuerzo": "lunch", "desayuno": "breakfast", "a table": "dinner"}
_NOT_NAMES = {"Me", "Us", "My", "Friends", "Friend", "The", "Him", "Her", "Them"}
_WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def window(message: str, now: datetime, tz: str = TZ) -> Optional[Tuple[date, date]]:
    """The days the guest means — or None (asked once). Never more than 7 days (A-3)."""
    t = (message or "").lower()
    today = now.astimezone(ZoneInfo(tz)).date()
    if re.search(r"\bthis week(end)?\b|\besta semana\b|\beste fin de semana\b", t):
        end = today + timedelta(days=6 - today.weekday())
        if "weekend" in t or "fin de semana" in t:
            return (max(today, end - timedelta(days=1)), end)
        return (today, end)
    if re.search(r"\bnext week\b|\bla semana que viene\b|\bla próxima semana\b", t):
        start = today + timedelta(days=7 - today.weekday())
        return (start, start + timedelta(days=6))
    if re.search(r"\btomorrow\b|\bmañana\b", t):
        return (today + timedelta(days=1),) * 2
    m = re.search(r"\b(" + "|".join(_WEEKDAYS) + r")\b", t)
    if m:
        d = today + timedelta(days=(_WEEKDAYS.index(m[1]) - today.weekday()) % 7)
        return (d, d)
    return None


def invite_request(message: str, now: Optional[datetime] = None) -> Optional[dict]:
    """{invitee, activity, window|None, area|None} when the message asks to book with someone — else None."""
    m = _INVITE.search(message or "")
    name, act = (m[1], m[2]) if m else (None, None)
    if not m:
        m = _WITH.search(message or "") or _ME_AND.search(message or "")
        if m:
            act, name = m[1], m[2]
    if not m or name.split()[0] in _NOT_NAMES:
        return None
    act = _ACT_EN.get(act.lower(), act.lower())
    w = window(message, now or NOW())
    area = re.search(r"\b(?:in|en|near|cerca de)\s+([A-ZÁÉÍÓÚÑ][\wáéíóúñ ]{2,40}?)(?=\s+(?:this|next|on|tomorrow|el|esta|la)\b|[,.?!]|$)", message or "")
    return {"invitee": name.strip(), "activity": act, "window": w, "area": area[1].strip() if area else None}


# ── §4.2 · the slots: different days first, nothing anyone is busy for ─────────────────────────────────────────────

def slots(days: Tuple[date, date], busy_a: List[Tuple[datetime, datetime]], busy_b: List[Tuple[datetime, datetime]],
          activity: str, now: datetime, tz: str = TZ, n: int = 3) -> List[dict]:
    z = ZoneInfo(tz)
    (h0, m0), (h1, m1) = HOURS.get(activity, HOURS["dinner"])
    pref = PREFERRED.get(activity, (h0, m0))
    busy = list(busy_a) + list(busy_b)
    out: List[dict] = []
    d = days[0]
    while d <= days[1] and len(out) < n:
        starts = [datetime.combine(d, dtime(*pref), tzinfo=z)]
        t = datetime.combine(d, dtime(h0, m0), tzinfo=z)
        while t <= datetime.combine(d, dtime(h1, m1), tzinfo=z):
            if t not in starts:
                starts.append(t)
            t += timedelta(minutes=30)
        for s in starts:
            e = s + SLOT_LEN
            if s <= now + timedelta(hours=2):
                continue
            if any(s < be and bs < e for bs, be in busy):
                continue
            out.append({"start": s.isoformat(), "end": e.isoformat(), "tz": tz})
            break                                                    # one per day: different days first
        d += timedelta(days=1)
    return out


def slot_words(s: dict) -> str:
    st = datetime.fromisoformat(s["start"])
    return f"{SN.day_words(st.date().isoformat())}, {st.strftime('%H:%M')}"


# ── the store: Memory for tests, Postgres (sql/023) for real ────────────────────────────────────────────────────────

class MemoryInviteStore:
    def __init__(self) -> None:
        self.rows: Dict[str, dict] = {}

    async def create(self, row):
        self.rows[row["code"]] = dict(row)

    async def get(self, code):
        return dict(self.rows[code]) if code in self.rows else None

    async def update(self, code, **kw):
        if code in self.rows:
            self.rows[code].update(kw)

    async def watching(self):
        return [dict(r) for r in self.rows.values() if r.get("trip_item_id") and r["status"] in ("chosen", "booked")]

    async def by_invitee(self, wa_sha):
        return [dict(r) for r in self.rows.values() if r.get("invitee_wa_sha256") == wa_sha]

    async def delete_account(self, account):
        ks = [k for k, r in self.rows.items() if r["inviter_account"] == account]
        for k in ks:
            del self.rows[k]
        return {"booking_invitations": len(ks)}


class PostgresInviteStore:
    def __init__(self, base) -> None:
        self._base = base

    async def _run(self, fn):
        try:
            return await self._base._run(fn)
        except StorageUnavailable as e:
            raise e.rehint("023_invitations.sql") from None

    @staticmethod
    def _r(r):
        if not r:
            return None
        d = dict(r)
        for k in ("id", "inviter_account", "invitee_account", "trip_item_id"):
            if d.get(k) is not None:
                d[k] = str(d[k])
        return d

    async def create(self, row):
        await self._run(lambda c: c.execute(
            "insert into booking_invitations (code, inviter_account, inviter_first_name, invitee_first_name, activity, area, party_size, "
            "slots, unseen, expires_at) values ($1,$2,$3,$4,$5,$6,$7,$8::jsonb,$9,$10)",
            row["code"], uuid.UUID(row["inviter_account"]), row["inviter_first_name"], row.get("invitee_first_name"), row["activity"],
            row.get("area"), row["party_size"], row["slots"], row["unseen"], row["expires_at"]))

    async def get(self, code):
        return self._r(await self._run(lambda c: c.fetchrow("select * from booking_invitations where code = $1", code)))

    async def update(self, code, **kw):
        cols = [k for k in kw if k in ("invitee_first_name", "invitee_wa_sha256", "invitee_number_e164", "chosen_slot", "chosen_at",
                                       "invitee_consent_at", "invitee_consent_text_sha256", "trip_item_id", "status", "told_status")]
        if not cols:
            return
        vals = [uuid.UUID(kw[k]) if k == "trip_item_id" and kw[k] else kw[k] for k in cols]
        sets = ", ".join(f"{k} = ${i + 2}" for i, k in enumerate(cols))
        await self._run(lambda c: c.execute(f"update booking_invitations set {sets} where code = $1", code, *vals))

    async def watching(self):
        rows = await self._run(lambda c: c.fetch(
            "select * from booking_invitations where trip_item_id is not null and status in ('chosen','booked')"))
        return [self._r(r) for r in rows]

    async def by_invitee(self, wa_sha):
        rows = await self._run(lambda c: c.fetch("select * from booking_invitations where invitee_wa_sha256 = $1", wa_sha))
        return [self._r(r) for r in rows]

    async def delete_account(self, account):
        n = await self._run(lambda c: c.execute("delete from booking_invitations where inviter_account = $1", uuid.UUID(account)))
        return {"booking_invitations": int(n.split()[-1])}


STORE: Any = None


def new_code() -> str:
    return "".join(secrets.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(8))


def invite_url(code: str) -> str:
    return f"{web_base()}/invite/{code}"


def share_link(inviter: str, activity: str, code: str) -> str:
    from urllib.parse import quote
    text = f"{inviter} invited you to {activity} — pick a time (booked by Sasha by Kanoe, an AI assistant): {invite_url(code)}"
    return "https://wa.me/?text=" + quote(text)


async def create(account: str, inviter_first: str, req: dict, now: datetime) -> dict:
    """The invitation and its 2–3 slots: the inviter's busy ranges if their calendar is connected (S-79), else
    'sensible' slots and the unseen flag (the message says so)."""
    from . import calendar_sync as CS
    days = req["window"]
    days = (days[0], min(days[1], days[0] + timedelta(days=MAX_DAYS - 1)))
    z = ZoneInfo(TZ)
    start = datetime.combine(days[0], dtime(0), tzinfo=z)
    end = datetime.combine(days[1] + timedelta(days=1), dtime(0), tzinfo=z)
    ranges = await CS.busy(account, start, end)
    busy_a = [(datetime.fromisoformat(a.replace("Z", "+00:00")), datetime.fromisoformat(b.replace("Z", "+00:00"))) for a, b in (ranges or [])]
    ss = slots(days, busy_a, [], req["activity"], now)
    row = {"code": new_code(), "inviter_account": account, "inviter_first_name": inviter_first, "invitee_first_name": req["invitee"],
           "activity": req["activity"], "area": req.get("area"), "party_size": 2, "slots": ss, "unseen": ranges is None,
           "expires_at": end, "status": "open"}
    if ss:
        await STORE.create(row)
    return row


# ── the public side (path I): Jon's page — rate-limited, no account, minimised ─────────────────────────────────────

router = APIRouter(prefix="/invite", tags=["booking-invite"])
_HITS: Dict[str, deque] = defaultdict(deque)
RATE = (30, 60)   # 30 requests a minute per address


def _limited(request: Request) -> bool:
    ip = (request.headers.get("x-forwarded-for") or (request.client.host if request.client else "?")).split(",")[0].strip()
    q, now = _HITS[ip], time.time()
    while q and q[0] < now - RATE[1]:
        q.popleft()
    q.append(now)
    return len(q) > RATE[0]


def _refuse(status: int, rule: str, message: str) -> JSONResponse:
    return JSONResponse({"ok": False, "rule": rule, "message": message}, status_code=status)


def consent_text(inv: dict) -> str:
    return CONSENT_TEXT.format(activity=inv["activity"], inviter=inv["inviter_first_name"])


async def public_view(inv: dict) -> dict:
    """Exactly what Jon may see (§0.3) — the key set is a test."""
    status = "expired" if inv["status"] == "open" and inv["expires_at"] < NOW() else inv["status"]
    view = {"inviter": inv["inviter_first_name"], "invitee": inv.get("invitee_first_name"), "activity": inv["activity"],
            "slots": [{"words": slot_words(s), "start": s["start"], "end": s["end"]} for s in inv["slots"]],
            "chosen": inv.get("chosen_slot"), "status": status, "consent": consent_text(inv),
            "consent_sha256": hashlib.sha256(consent_text(inv).encode()).hexdigest(),
            "whatsapp": f"https://wa.me/{(_number() or '').lstrip('+')}?text=INVITE%20{inv['code']}" if _number() else None}
    if inv["status"] == "booked" and inv.get("trip_item_id"):
        from . import guest_whatsapp as GW
        row = next((r for r in await GW._upcoming(inv["inviter_account"]) if r["id"] == inv["trip_item_id"]), None) if GW.STORE else None
        if row:   # the venue, the day and the time — no reference number (it is the inviter's booking)
            view["booked"] = {"venue": row["venue"], "day": SN.day_words(row.get("date")), "time": row.get("time")}
    return view


def _number() -> Optional[str]:
    from . import guest_whatsapp as GW
    ns = sorted(GW.guest_numbers())
    return ns[0] if ns else None


@router.get("/{code}")
async def invite_get(code: str, request: Request):
    if _limited(request):
        return _refuse(429, "slow_down", "too many requests — try again in a minute")
    if not re.fullmatch(r"[A-Z0-9]{8}", code) or STORE is None:
        return _refuse(404, "invite_unknown", "no such invitation")
    try:
        inv = await STORE.get(code)
    except StorageUnavailable as e:
        return _refuse(503, e.rule, e.detail)
    if inv is None:
        return _refuse(404, "invite_unknown", "no such invitation")
    return await public_view(inv)


@router.post("/{code}/choose")
async def invite_choose(code: str, request: Request, background: BackgroundTasks):
    if _limited(request):
        return _refuse(429, "slow_down", "too many requests — try again in a minute")
    try:
        body = await request.json()
    except Exception:
        body = {}
    inv = await STORE.get(code) if STORE is not None and re.fullmatch(r"[A-Z0-9]{8}", code) else None
    if inv is None:
        return _refuse(404, "invite_unknown", "no such invitation")
    if inv["status"] != "open" or inv["expires_at"] < NOW():
        return _refuse(409, "invite_closed", "this invitation is no longer open")
    if body.get("consent_sha256") != hashlib.sha256(consent_text(inv).encode()).hexdigest():
        return _refuse(422, "consent_stale", "tick the sentence shown — it must be the current one")
    i = body.get("slot")
    if not isinstance(i, int) or not 0 <= i < len(inv["slots"]):
        if body.get("none"):
            await STORE.update(code, status="declined", chosen_at=NOW(), invitee_consent_at=NOW(),
                               invitee_consent_text_sha256=body["consent_sha256"])
            background.add_task(_tell_inviter_logged, inv, None)
            return {"status": "declined", "say": f"OK — {inv['inviter_first_name']} will know none of these times work."}
        return _refuse(422, "slot_invalid", "pick one of the times shown")
    first = re.sub(r"[^\wáéíóúñü' -]", "", str(body.get("first_name") or ""))[:40].strip() or inv.get("invitee_first_name")
    now = NOW()
    await STORE.update(code, chosen_slot=i, chosen_at=now, status="chosen", invitee_first_name=first, invitee_consent_at=now,
                       invitee_consent_text_sha256=body["consent_sha256"])
    inv = await STORE.get(code)
    # Sasha 117 · Jon's tap is answered at once; the inviter is told (and searched for) after — it took 24 s live
    background.add_task(_tell_inviter_logged, inv, i)
    return {"status": "chosen", "say": f"Thanks — {inv['inviter_first_name']} will book it and you'll see it here."}


async def _tell_inviter_logged(inv: dict, i: Optional[int]) -> None:
    try:
        await _tell_inviter(inv, i)
    except Exception as e:   # after the response: nobody else would see it
        log.error("[invitations] telling the inviter failed: %s: %s", type(e).__name__, e)


async def _tell_inviter(inv: dict, i: Optional[int]) -> None:
    """The inviter hears Jon's choice — and, if they named an area, gets the cards for that slot at once."""
    from . import guest_whatsapp as GW
    ch = await GW.STORE.channel_of_account(inv["inviter_account"]) if GW.STORE else None
    if not ch or not _number():
        return
    st = await GW.STORE.get_state(ch["wa_id_sha256"])
    who = inv.get("invitee_first_name") or "Your guest"
    out = GW.Out()
    if i is None:
        out.text(f"{who} can't make any of those times. Tell me other days and I'll make a new invitation.")
        await GW.deliver(ch, _number(), out, st.get("last_inbound_at"))
        return
    s = inv["slots"][i]
    open_at = datetime.fromisoformat(s["start"]).strftime("%Y-%m-%dT%H:%M")
    out.text(f"{who} picked {slot_words(s)}. The booking is yours: I'll show you places, and nothing is booked until your yes.")
    from .chat_request import draft as draft_of
    what = draft_of(inv["activity"])["parts"].get("what")   # "dinner" → a table at a restaurant
    draft = {"how_many": {"count": inv["party_size"], "unit": "people"}, "when": {"mode": "at", "at": open_at},
             **({"what": what} if what else {})}
    if inv.get("area"):
        ctx = {"account": inv["inviter_account"], "ch": ch, "frm": _number(), "st": st, "now": NOW(), "out": out, "button_text": ""}
        f = HO_find(inv["activity"], inv["area"], open_at)
        await GW._find(ctx, f, {"parts": draft})
        if ctx["st"].get("pending"):
            ctx["st"]["pending"]["invite_code"] = inv["code"]
        await GW.STORE.put_state(ch["wa_id_sha256"], ctx["st"])
    else:
        out.text("Where should I look — an area, e.g. \"Chamberí\"?")
        st["pending"] = {"kind": "invite_where", "at": NOW().isoformat(), "invite_code": inv["code"], "activity": inv["activity"],
                         "open_at": open_at, "draft": draft}
        await GW.STORE.put_state(ch["wa_id_sha256"], st)
    await GW.deliver(ch, _number(), out, st.get("last_inbound_at"))


def HO_find(activity: str, area: str, open_at: str) -> dict:
    from . import handoff as HO
    f = HO.find_request(f"{activity} in {area}") or {"what": activity, "where": area}
    return {**f, "open_at": open_at}


# ── Jon's WhatsApp opt-in for THIS invitation (an unlinked sender: "INVITE ABCD2345") ────────────────────────────────

_INVITE_MSG = re.compile(r"^\s*invite\s+([A-Za-z0-9]{8})\s*$", re.I)


async def on_invite_message(sender: str, body: str) -> Optional[str]:
    """None: not an INVITE message. Else the one reply (TwiML) — and his number kept for this invitation only."""
    m = _INVITE_MSG.match(body or "")
    if not m or STORE is None:
        return None
    from . import guest_whatsapp as GW
    inv = await STORE.get(m[1].upper())
    if inv is None or inv["status"] in ("expired", "cancelled", "declined") or inv["expires_at"] < NOW():
        return BAD_INVITE
    await STORE.update(inv["code"], invitee_wa_sha256=GW.wa_key(sender), invitee_number_e164=sender)
    return JOINED.format(activity=inv["activity"])


async def on_invitee_stop(sender: str, body: str) -> Optional[str]:
    """Jon's STOP: no further messages for any invitation he joined; his number is dropped."""
    from . import guest_whatsapp as GW
    if STORE is None or not GW._STOP.match(body or "") or not hasattr(STORE, "by_invitee"):
        return None
    n = 0
    for inv in await STORE.by_invitee(GW.wa_key(sender)):
        await STORE.update(inv["code"], invitee_wa_sha256=None, invitee_number_e164=None)
        n += 1
    return "OK — no more messages about it." if n else None


# ── the watcher: the inviter's booking → Jon told (the page, and WhatsApp only if he opted in) ──────────────────────

async def tick() -> List[str]:
    """Called by the proactive loop each minute: a chosen invitation's booking confirmed or cancelled → Jon told once."""
    from . import guest_whatsapp as GW
    if STORE is None:
        return []
    done = []
    for inv in await STORE.watching():
        rows = await GW._upcoming(inv["inviter_account"]) if GW.STORE else []
        row = next((r for r in rows if r["id"] == inv["trip_item_id"]), None)
        status = row["status"] if row else "cancelled"
        if status == inv.get("told_status"):
            continue
        if status in ("confirmed", "guest_booked"):
            await STORE.update(inv["code"], status="booked", told_status=status)
            text = (f"Booked: {row['venue']}, {SN.day_words(row.get('date'))} at {row.get('time')} — under "
                    f"{inv['inviter_first_name']}'s name.")
        elif status == "cancelled":
            await STORE.update(inv["code"], status="cancelled", told_status=status)
            text = f"{inv['inviter_first_name']} cancelled the {inv['activity']}."
        else:
            continue
        if inv.get("invitee_number_e164") and _number():
            r = await GW.SENDER.send(_number(), inv["invitee_number_e164"], body=text)
            done.append(f"{inv['code']}: {r}")
    return done


__all__ = ["invite_request", "window", "slots", "create", "router", "tick", "on_invite_message", "public_view",
           "MemoryInviteStore", "PostgresInviteStore", "share_link", "invite_url"]
