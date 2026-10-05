"""S-83 · PROACTIVE SASHA — the day before, the time to leave, "confirmed in writing", and the morning brief, on WhatsApp.

The rules, each enforced here (docs/sasha/S-83-proactive-sasha.md §1):
  1. Nothing for a booking that isn't confirmed except an HONEST status: never a "tomorrow" for unclear, proposed or
     requested. The status is re-read just before each send.
  2. Quiet hours 22:00–08:00 in the booking's own time zone: a message due then waits until 08:00; a leave_now is skipped.
  3. At most DAILY_MAX (4) a day per guest; over it, written_confirmation > leave_now > day_before/not_confirmed > brief.
  4. One of each kind per booking, ever (the ledger's unique index claims the send BEFORE it is delivered).
  5. Opt-out per guest and per kind (STOP REMINDERS, the settings); STOP turns all WhatsApp off (deliver refuses).
  6. Nothing beyond the guest's own booking.
  · Consent: only a guest linked under consent v3 or later gets reminders; a v2 guest gets only written confirmations
    (v2 covers "confirmations").
  · leave_now only with a starting point the guest SAVED and a route the Routes API computed — never a straight-line
    estimate presented as a travel time. Route durations are not stored.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import uuid
from datetime import date, datetime, time as dtime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from . import sentences as SN
from .store import StorageUnavailable

log = logging.getLogger("booking_signer.proactive")
NOW = lambda: datetime.now(timezone.utc)
TICK_S = 60
QUIET = (22, 8)                      # 22:00–08:00 local (the consent text says so: change both together)
DAY_BEFORE_AT = dtime(18, 0)
BRIEF_AT = dtime(9, 0)
LEAVE_MARGIN = timedelta(minutes=10)
#: Sasha 147 · Routes is a PAID call: asked at most this often per booking. The leave-now window is LEAVE_MARGIN (10 min)
#: long, so asking every 5 minutes always lands in it — 12 calls an hour in a booking's last 3 h, not 60.
ROUTES_EVERY = timedelta(minutes=5)
_ROUTED: Dict[str, datetime] = {}   # booking → when Routes was last asked (the time only, nothing of Google's)
CONFIRMED = ("confirmed", "guest_booked")
HONEST = ("requested", "attempting", "unclear", "proposed", "quoted", "waitlisted", "link_sent", "pending")
PRIORITY = {"written_confirmation": 0, "leave_now": 1, "day_before": 2, "not_confirmed": 2, "morning_brief": 3}
KINDS = tuple(PRIORITY)


def daily_max() -> int:
    try:
        return max(0, int(os.getenv("SASHA_PROACTIVE_DAILY_MAX", "4")))
    except ValueError:
        return 4


# ── the words (one owner) ───────────────────────────────────────────────────────────────────────────────────────────

def _ref(b: dict) -> str:
    return b.get("booking_reference") or b.get("sasha_reference") or "none given"


def _party(b: dict) -> str:
    n = b.get("party")
    return f"{n} {'person' if n == 1 else 'people'}" if n else "your party"


def status_words(status: str) -> str:
    from .routes import STATUS_WORDS
    return STATUS_WORDS.get(status, status)


def day_word(b: dict, now: Optional[datetime]) -> str:
    """Sasha 119 · "Tomorrow" only when it IS tomorrow: a day-before held by the quiet hours goes out at 08:00 on the day
    itself (live, 3 Oct 08:38: "Tomorrow, 21:00 at Hanakura" about that same evening) — then it is "Tonight" / "Today"."""
    start = starts_at(b) if now is not None else None
    if start is None:
        return "Tomorrow"
    days = (start.date() - now.astimezone(start.tzinfo).date()).days
    if days <= 0:
        return "Tonight" if start.hour >= 19 else "Today"
    return "Tomorrow" if days == 1 else SN.day_words(start.date().isoformat())


def render(kind: str, b: dict, extra: Optional[dict] = None, now: Optional[datetime] = None) -> str:
    """The in-session text. day_before for a booking that isn't confirmed is ALWAYS the honest status instead."""
    extra = extra or {}
    venue, hhmm = b.get("venue") or "the venue", b.get("time") or "—"
    day = day_word(b, now)
    if kind == "day_before" and b.get("status") not in CONFIRMED:
        kind = "not_confirmed"
    if kind == "day_before":
        return f"{day}: {venue}, {hhmm}, {_party(b)}, ref {_ref(b)}. Reply CANCEL {venue.split()[0]} to cancel."
    if kind == "not_confirmed":
        if b.get("status") == "proposed":
            return f"{day}, {hhmm} at {venue}: not confirmed yet. They offered another time; it's not booked until you say yes."
        return f"{day}, {hhmm} at {venue}: not confirmed yet. {status_words(b.get('status') or '')}. I'll tell you as soon as they answer."
    if kind == "leave_now":
        return (f"Time to leave for {venue}: {extra['minutes']} min {extra['mode_words']} from {extra['label']}, for {hhmm}.")
    if kind == "written_confirmation":
        when = f"{hhmm} {SN.day_words(b.get('date'))}".strip()
        if extra.get("result") == "proposed":
            return f"{venue} replied in writing: they offer another time. Not booked until you say yes."
        ref = f", ref {b['booking_reference']}" if b.get("booking_reference") else ""
        return f"{venue} confirmed in writing ✅: {when}, {_party(b)}{ref}."
    if kind == "morning_brief":
        items = extra["items"]
        return "Today: " + " · ".join(f"{x.get('time') or '—'} {x.get('venue')} ("
                                      + ("TEST booking" if (x.get("booking_reference") or "").startswith("TEST-") or "(TEST booking" in (x.get("venue") or "")
                                         else "confirmed" if x.get("status") in CONFIRMED else "not confirmed yet") + ")"
                                      for x in items)
    raise ValueError(kind)


#: S-83 §2 · the utility templates' variables, for production (outside the 24-hour window). The SIDs come from
#: SASHA_WA_TEMPLATES = '{"day_before": {"en": "HX…", "es": "HX…"}, …}' once Meta approves them; none in the sandbox.
def template_vars(kind: str, b: dict, extra: Optional[dict] = None) -> dict:
    extra = extra or {}
    if kind == "day_before":
        return {1: b.get("venue"), 2: b.get("time"), 3: _party(b), 4: _ref(b)}
    if kind == "not_confirmed":
        return {1: b.get("venue"), 2: f"{SN.day_words(b.get('date'))} {b.get('time')}", 3: status_words(b.get("status") or "")}
    if kind == "leave_now":
        return {1: b.get("venue"), 2: b.get("time"), 3: extra.get("minutes"), 4: extra.get("mode_words"), 5: extra.get("label")}
    if kind == "written_confirmation":
        return {1: b.get("venue"), 2: f"{SN.day_words(b.get('date'))} {b.get('time')}", 3: b.get("party"), 4: _ref(b)}
    return {1: render("morning_brief", b, extra)[len("Today: "):]}


def _template_sid(kind: str, lang: str = "en") -> Optional[str]:
    import json
    try:
        return (json.loads(os.getenv("SASHA_WA_TEMPLATES", "") or "{}").get(kind) or {}).get(lang)
    except ValueError:
        return None


# ── the clock ───────────────────────────────────────────────────────────────────────────────────────────────────────

def _zone(b: dict) -> ZoneInfo:
    try:
        return ZoneInfo(b.get("timezone") or "Europe/Madrid")
    except Exception:
        return ZoneInfo("Europe/Madrid")


def starts_at(b: dict) -> Optional[datetime]:
    if not (b.get("date") and b.get("time")):
        return None
    try:
        return datetime.combine(date.fromisoformat(b["date"]), dtime.fromisoformat(b["time"]), tzinfo=_zone(b))
    except ValueError:
        return None


def quiet(now: datetime, tz: ZoneInfo) -> bool:
    h = now.astimezone(tz).hour
    return h >= QUIET[0] or h < QUIET[1]


# ── Routes (leave_now) ──────────────────────────────────────────────────────────────────────────────────────────────

async def _routes_post(url: str, headers: dict, body: dict):
    from .http_pool import request   # Sasha 149 · pooled, kept alive
    r = await request("POST", url, timeout=15.0, headers=headers, json=body)
    return r.status_code, (r.json() if r.headers.get("content-type", "").startswith("application/json") else {})

ROUTES_HTTP = _routes_post   # tests replace it


async def travel(origin: str, destination: str, depart: datetime, mode: str) -> Optional[int]:
    """Seconds by the Routes API, or None — logged — when it can't say. Never a straight-line estimate."""
    key = os.getenv("GOOGLE_PLACES_API_KEY", "").strip()
    if not key or not origin or not destination:
        return None
    # Sasha 146 · "place_id:<id>" routes to a Google place without reading its listing
    dest = {"placeId": destination[9:]} if destination.startswith("place_id:") else {"address": destination}
    body = {"origin": {"address": origin}, "destination": dest, "travelMode": mode}
    if mode == "TRANSIT" or mode == "DRIVE":
        body["departureTime"] = depart.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    if mode == "DRIVE":   # Sasha 132 · Routes refuses a departure time for driving unless routing is traffic-aware (400, 3 Oct)
        body["routingPreference"] = "TRAFFIC_AWARE"
    try:
        status, j = await ROUTES_HTTP("https://routes.googleapis.com/directions/v2:computeRoutes",
                                      {"X-Goog-Api-Key": key, "X-Goog-FieldMask": "routes.duration,routes.distanceMeters"}, body)
    except Exception as e:
        log.warning("[proactive] Routes failed: %s", type(e).__name__)
        return None
    if status != 200 or not (j.get("routes") or []):
        log.warning("[proactive] Routes answered HTTP %s with no route — no leave_now (is the Routes API enabled on the key?)", status)
        return None
    m = re.fullmatch(r"(\d+)s", str(j["routes"][0].get("duration") or ""))
    return int(m[1]) if m else None


async def _place_dest(account: str, b: dict) -> str:
    """The booking's venue as a Routes destination without reading its Google listing: the place ID its venue read keeps
    (a place ID may be stored — the Maps terms). "" when there is none."""
    from . import ladder_routes as LR
    if not b.get("read_id") or LR.LADDER_STORE is None:
        return ""
    try:
        row = await LR.LADDER_STORE.get_read(account, str(b["read_id"]))
    except Exception as e:
        log.warning("[proactive] the venue read for leave_now could not be read: %s", type(e).__name__)
        return ""
    pid = (((row or {}).get("read") or {}).get("listing") or {}).get("place_id")
    return f"place_id:{pid}" if pid else ""


MODE_WORDS = {"TRANSIT": "by public transport", "WALK": "on foot", "DRIVE": "by car", "TWO_WHEELER": "by scooter"}


# ── the store: Memory for tests, Postgres (sql/026) for real ────────────────────────────────────────────────────────

class MemoryProactiveStore:
    def __init__(self) -> None:
        self.sent: List[dict] = []
        self.prefs: Dict[str, dict] = {}
        self.places: Dict[str, dict] = {}

    async def claim(self, row: dict) -> Optional[int]:
        dup = any(s for s in self.sent if (row["trip_item_id"] and s["trip_item_id"] == row["trip_item_id"] and s["kind"] == row["kind"])
                  or (row["kind"] == "morning_brief" and s["kind"] == "morning_brief" and s["account_id"] == row["account_id"]
                      and s["local_day"] == row["local_day"]))
        if dup:
            return None
        self.sent.append({**row, "id": len(self.sent) + 1})
        return len(self.sent)

    async def finish(self, sid: int, channel: str, outcome: str) -> None:
        self.sent[sid - 1].update(channel=channel, outcome=outcome)

    async def claimed(self, trip_item_id: str, kind: str) -> bool:
        """Sasha 146 · is there already a row for this booking and kind (proactive_once)? Read only."""
        return any(s.get("trip_item_id") == trip_item_id and s.get("kind") == kind for s in self.sent)

    async def sent_today(self, account: str, local_day: date) -> int:
        return sum(1 for s in self.sent if s["account_id"] == account and s["local_day"] == local_day and s.get("outcome") == "sent")

    async def get_prefs(self, account: str) -> Optional[dict]:
        return dict(self.prefs[account]) if account in self.prefs else None

    async def set_prefs(self, account: str, all_off: Optional[bool] = None, off_kinds: Optional[List[str]] = None) -> dict:
        p = self.prefs.setdefault(account, {"account_id": account, "off_kinds": [], "all_off": False})
        if all_off is not None:
            p["all_off"] = all_off
        if off_kinds is not None:
            p["off_kinds"] = list(off_kinds)
        return dict(p)

    async def default_place(self, account: str) -> Optional[dict]:
        return next((dict(p) for p in self.places.values() if p["account_id"] == account and p["is_default"]), None)

    async def save_place(self, account: str, label: str, address: str) -> dict:
        for p in self.places.values():
            if p["account_id"] == account:
                p["is_default"] = False
        pid = str(uuid.uuid4())
        self.places[pid] = {"id": pid, "account_id": account, "label": label, "address": address, "is_default": True}
        return dict(self.places[pid])

    async def delete_places(self, account: str) -> int:
        ks = [k for k, p in self.places.items() if p["account_id"] == account]
        for k in ks:
            del self.places[k]
        return len(ks)

    async def written(self, since: datetime) -> List[dict]:
        return list(getattr(self, "inbound", []))

    async def delete_account(self, account: str) -> Dict[str, int]:
        n = len([s for s in self.sent if s["account_id"] == account])
        self.sent = [s for s in self.sent if s["account_id"] != account]
        p = 1 if self.prefs.pop(account, None) else 0
        return {"proactive_sent": n, "proactive_prefs": p, "guest_places": await self.delete_places(account)}


class PostgresProactiveStore:
    def __init__(self, base) -> None:
        self._base = base

    async def _run(self, fn):
        try:
            return await self._base._run(fn)
        except StorageUnavailable as e:
            raise e.rehint("026_proactive.sql") from None

    async def claim(self, row):
        return await self._run(lambda c: c.fetchval(
            "insert into proactive_sent (account_id, trip_item_id, kind, local_day, status_at_send, channel, outcome) "
            "values ($1,$2,$3,$4,$5,'skipped','claimed') on conflict do nothing returning id",
            uuid.UUID(row["account_id"]), uuid.UUID(row["trip_item_id"]) if row.get("trip_item_id") else None, row["kind"],
            row["local_day"], row.get("status_at_send")))

    async def finish(self, sid, channel, outcome):
        await self._run(lambda c: c.execute("update proactive_sent set channel = $2, outcome = $3 where id = $1", sid, channel, outcome))

    async def claimed(self, trip_item_id, kind):
        try:
            tid = uuid.UUID(str(trip_item_id))
        except (ValueError, TypeError):
            return False
        return bool(await self._run(lambda c: c.fetchval(
            "select exists (select 1 from proactive_sent where trip_item_id = $1 and kind = $2)", tid, kind)))

    async def sent_today(self, account, local_day):
        return int(await self._run(lambda c: c.fetchval(
            "select count(*) from proactive_sent where account_id = $1 and local_day = $2 and outcome = 'sent'", uuid.UUID(account), local_day)))

    async def get_prefs(self, account):
        r = await self._run(lambda c: c.fetchrow("select * from proactive_prefs where account_id = $1", uuid.UUID(account)))
        return {**dict(r), "account_id": str(r["account_id"]), "off_kinds": list(r["off_kinds"] or [])} if r else None

    async def set_prefs(self, account, all_off=None, off_kinds=None):
        r = await self._run(lambda c: c.fetchrow(
            "insert into proactive_prefs (account_id, all_off, off_kinds) values ($1, coalesce($2::boolean, false), coalesce($3::text[], '{}'::text[])) "
            "on conflict (account_id) do update set all_off = coalesce($2::boolean, proactive_prefs.all_off), "
            "off_kinds = coalesce($3::text[], proactive_prefs.off_kinds), updated_at = now() returning *",
            uuid.UUID(account), all_off, off_kinds))
        return {**dict(r), "account_id": str(r["account_id"]), "off_kinds": list(r["off_kinds"] or [])}

    async def default_place(self, account):
        r = await self._run(lambda c: c.fetchrow("select id, label, address, is_default from guest_places where account_id = $1 and is_default",
                                                 uuid.UUID(account)))
        return {**dict(r), "id": str(r["id"])} if r else None

    async def save_place(self, account, label, address):
        async def go(c):
            async with c.transaction():
                await c.execute("update guest_places set is_default = false where account_id = $1", uuid.UUID(account))
                return await c.fetchrow("insert into guest_places (account_id, label, address, is_default) values ($1,$2,$3,true) "
                                        "returning id, label, address, is_default", uuid.UUID(account), label, address)
        r = await self._run(go)
        return {**dict(r), "id": str(r["id"])}

    async def delete_places(self, account):
        n = await self._run(lambda c: c.execute("delete from guest_places where account_id = $1", uuid.UUID(account)))
        return int(n.split()[-1])

    async def written(self, since):
        """Written confirmations (or offers) that landed on a reservation, with whose it is."""
        rows = await self._run(lambda c: c.fetch(
            "select i.trip_item_id, i.channel, i.reading->>'result' as result, i.received_at, t.owner_id as account_id "
            "from booking_inbound i join trip_items ti on ti.id = i.trip_item_id join trips t on t.id = ti.trip_id "
            "where i.trip_item_id is not null and i.channel in ('email','sms','whatsapp') "
            "and i.reading->>'result' in ('confirmed','proposed') and i.received_at > $1 "
            # Sasha 118 · a confirmation the guest forwarded on WhatsApp was answered there and then — not told twice
            "and not (i.channel = 'whatsapp' and coalesce(i.reading->>'forwarded_by', '') = 'guest') order by i.received_at", since))
        return [{**dict(r), "trip_item_id": str(r["trip_item_id"]), "account_id": str(r["account_id"])} for r in rows]

    async def delete_account(self, account):
        async def go(c):
            async with c.transaction():
                a = uuid.UUID(account)
                s = await c.execute("delete from proactive_sent where account_id = $1", a)
                p = await c.execute("delete from proactive_prefs where account_id = $1", a)
                g = await c.execute("delete from guest_places where account_id = $1", a)
                return {"proactive_sent": int(s.split()[-1]), "proactive_prefs": int(p.split()[-1]), "guest_places": int(g.split()[-1])}
        return await self._run(go)


STORE: Any = None   # routes.py sets the Postgres store; tests a memory one


# ── one tick ────────────────────────────────────────────────────────────────────────────────────────────────────────

def _due(kind: str, b: dict, now: datetime, extra: Optional[dict] = None) -> bool:
    start = starts_at(b)
    if start is None or now >= start:
        return False
    local = now.astimezone(start.tzinfo)
    if kind in ("day_before", "not_confirmed"):
        due = datetime.combine(start.date() - timedelta(days=1), DAY_BEFORE_AT, tzinfo=start.tzinfo)
        return now >= due
    if kind == "leave_now":
        leave = start - timedelta(seconds=extra["seconds"]) - LEAVE_MARGIN
        return leave <= now < start - timedelta(seconds=extra["seconds"])
    if kind == "morning_brief":
        return local.date() == start.date() and local.time() >= BRIEF_AT
    return False


async def _send(ch: dict, kind: str, b: Optional[dict], text, variables: Optional[dict], local_day: date, status: Optional[str]) -> str:
    """`text` may be an async `compose()` → (text, variables), run only AFTER the claim (Sasha 142): a message already sent
    costs no Google listing re-read for its name — every minute until the booking starts, that was ≈ 1 call a minute."""
    from . import guest_whatsapp as GW
    sid = await STORE.claim({"account_id": ch["account_id"], "trip_item_id": (b or {}).get("id") if kind != "morning_brief" else None,
                             "kind": kind, "local_day": local_day, "status_at_send": status})
    if sid is None:
        return "already sent"
    if callable(text):
        text, variables = await text()
    st = await GW.STORE.get_state(ch["wa_id_sha256"])
    last = st.get("last_inbound_at")
    frm = sorted(GW.guest_numbers())[0] if GW.guest_numbers() else None
    if not frm:
        await STORE.finish(sid, "skipped", "not sent: WhatsApp for guests is off")
        return "not sent: WhatsApp for guests is off"
    if last and NOW() - last <= GW.SESSION_WINDOW:
        out = ", ".join(await GW.deliver(ch, frm, GW.Out().text(text), last))
        await STORE.finish(sid, "whatsapp_session", "sent" if out == "sent" else out)
        return out
    tsid = _template_sid(kind)
    if not tsid or ch.get("opted_out_at"):
        await STORE.finish(sid, "skipped", "not sent: outside the 24-hour window and no approved template")
        log.info("[proactive] %s not sent: outside the 24-hour window and no approved template (sandbox)", kind)
        return "not sent: outside the 24-hour window"
    r = await GW.SENDER.send(frm, ch["number_e164"], content_sid=tsid, variables=variables)
    await STORE.finish(sid, "whatsapp_template", r)
    return r


async def tick(now: datetime, only_account: Optional[str] = None) -> List[dict]:
    """Every message due at `now`, sent within the rules. Returns what was done (the admin trigger shows it)."""
    from . import guest_whatsapp as GW
    if STORE is None or GW.STORE is None:
        return []
    done: List[dict] = []
    since = now - timedelta(days=2)
    written = {}
    for w in await STORE.written(since):
        k = w["trip_item_id"]
        if w["result"] == "confirmed" or k not in written:
            written[k] = w
    for ch in await GW.STORE.all_channels():
        account = ch["account_id"]
        if only_account and account != only_account:
            continue
        prefs = await STORE.get_prefs(account) or {"all_off": False, "off_kinds": []}
        reminders_ok = GW.consent_at_least(ch.get("consent_wording_version") or "v0", 3) and not prefs.get("all_off")
        rows = await GW._upcoming(account, names=False)   # Sasha 141 · names are re-read only for a message sent
        due: List[Tuple[int, str, Optional[dict], dict]] = []
        for b in rows:
            start = starts_at(b)
            if start is None:
                continue
            if b["id"] in written:                                  # v2 covers confirmations: no consent gate
                due.append((PRIORITY["written_confirmation"], "written_confirmation", b, {"result": written[b["id"]]["result"]}))
            if not reminders_ok:
                continue
            kind = "day_before" if b.get("status") in CONFIRMED else ("not_confirmed" if b.get("status") in HONEST else None)
            if kind and kind not in prefs.get("off_kinds", []) and _due(kind, b, now):
                due.append((PRIORITY[kind], kind, b, {}))
            if b.get("status") in CONFIRMED and "leave_now" not in prefs.get("off_kinds", []) and now >= start - timedelta(hours=3) \
                    and not (hasattr(STORE, "claimed") and await STORE.claimed(str(b["id"]), "leave_now")):   # Sasha 146 · once sent, no more Routes calls
                place = await STORE.default_place(account)
                last = _ROUTED.get(str(b["id"]))
                if place and not (last and timedelta(0) <= now - last < ROUTES_EVERY):
                    _ROUTED[str(b["id"])] = now
                    mode = os.getenv("SASHA_PROACTIVE_MODE", "TRANSIT")
                    dest = ", ".join(x for x in ((None if b.get("receipt") else b.get("venue")), b.get("address")) if x)
                    if not dest:   # Sasha 146 · a phone booking with no address: routed to its listing's place ID (stored, allowed) —
                        dest = await _place_dest(account, b)   # never a listing re-read each minute (≈ 1 Place Details a minute, 5 Oct)
                    secs = await travel(place["address"], dest, start, mode)
                    if secs and _due("leave_now", b, now, {"seconds": secs}):
                        due.append((PRIORITY["leave_now"], "leave_now", b, {"minutes": round(secs / 60), "mode_words": MODE_WORDS.get(mode, ""),
                                                                            "label": place["label"]}))
        today = [b for b in rows if starts_at(b) and starts_at(b).astimezone(starts_at(b).tzinfo).date() == now.astimezone(starts_at(b).tzinfo).date()]
        if reminders_ok and today and "morning_brief" not in prefs.get("off_kinds", []) and _due("morning_brief", today[0], now):
            due.append((PRIORITY["morning_brief"], "morning_brief", today[0], {"items": today}))
        for _, kind, b, extra in sorted(due, key=lambda d: d[0]):
            tz = _zone(b)
            local_day = now.astimezone(tz).date()   # the SENDING day: the cap counts per day sent; the dedupe is per booking
            if quiet(now, tz):
                if kind == "leave_now":
                    done.append({"kind": kind, "booking": b["id"], "outcome": "skipped: quiet hours"})
                continue                                            # deferred: the 08:00 tick sends it if still due
            if await STORE.sent_today(account, now.astimezone(tz).date()) >= daily_max():
                done.append({"kind": kind, "booking": b.get("id"), "outcome": "dropped: the daily cap"})
                continue
            # rule 1 · the status re-read at the send: cancelled at 17:59 never gets an 18:00 message
            fresh = next((r for r in await GW._upcoming(account, names=False) if r["id"] == b["id"]), None) if kind != "morning_brief" else b
            if fresh is None:
                done.append({"kind": kind, "booking": b["id"], "outcome": "skipped: no longer an active booking"})
                continue
            if kind in ("day_before", "not_confirmed"):
                kind = "day_before" if fresh.get("status") in CONFIRMED else "not_confirmed"
            said: Dict[str, Any] = {}

            async def compose(kind=kind, fresh=fresh, extra=extra):   # Sasha 141/142 · names re-read only for a message sent
                if kind == "morning_brief":
                    extra = {**extra, "items": await GW._with_names(account, [dict(x) for x in extra["items"]])}
                else:
                    fresh = (await GW._with_names(account, [dict(fresh)]))[0]
                said["text"] = render(kind, fresh, extra, now)
                return said["text"], template_vars(kind, fresh, extra)
            outcome = await _send(ch, kind, fresh, compose, None, local_day, fresh.get("status"))
            done.append({"kind": kind, "booking": fresh.get("id"), "outcome": outcome, "text": said.get("text")})
    return done


# ── Sasha 130 · EMAIL, THEN A CALL AT OPENING: no reply to Sasha's email → at their opening, the guest is ASKED ─────

def no_reply_call_on() -> bool:
    """On only once migration 028 lets the ledger hold 'no_reply_call' (the dedupe): until then nothing is promised."""
    return os.getenv("SASHA_NO_REPLY_CALL", "") == "1"


def tap_escalation_on() -> bool:
    """On only once migration 031 lets the ledger hold 'tap_expired'."""
    return os.getenv("SASHA_TAP_ESCALATION", "") == "1"


def _daytime(now: datetime, tz: str) -> bool:
    return 10 <= now.astimezone(ZoneInfo(tz)).hour < 20


async def no_reply_offers(now: datetime) -> List[dict]:
    """Sasha 131 · an email with no venue reply after SASHA_EMAIL_REPLY_HOURS (24 h) → ONE WhatsApp question: "shall I call
    them?" — when they're open (by their hours), else in the daytime when their hours aren't known."""
    from . import decide as D, guest_whatsapp as GW, hours as H, ladder_routes as LR
    if not no_reply_call_on() or STORE is None or GW.STORE is None or LR.LADDER_STORE is None:
        return []
    done: List[dict] = []
    for ch in await GW.STORE.all_channels():
        account = ch["account_id"]
        for b in await GW._upcoming(account, names=False):   # email bookings: no receipt name to re-read
            if b.get("channel") != "email" or b.get("status") not in ("requested", "attempting") or not b.get("read_id") or not b.get("requested_at"):
                continue
            if now - datetime.fromisoformat(b["requested_at"]) < timedelta(hours=D.reply_hours()):
                continue
            row = await LR.LADDER_STORE.get_read(account, str(b["read_id"]))
            read = (row or {}).get("read") or {}
            if not any(f.get("kind") == "phone" for f in read.get("facts") or []):
                continue
            tz = b.get("timezone") or "Europe/Madrid"
            try:
                st = H.status(read, now, tz)
            except Exception:
                st = {"known": False}
            if not (st.get("open_now") if st.get("known") else _daytime(now, tz)):
                continue
            sid = await STORE.claim({"account_id": account, "trip_item_id": b["id"], "kind": "no_reply_call",
                                     "local_day": now.astimezone(ZoneInfo(tz)).date(), "status_at_send": b.get("status")})
            if sid is None:
                continue
            from . import escalation as ESC
            email = await LR.LADDER_STORE.get_email(account, str(b.get("intent_id") or "")) if b.get("intent_id") else None
            if email and ESC.has_plan(email.get("read_back_lines")):   # Sasha 132 · the guest's one yes covered this call
                outcome = await GW.auto_call_from_email(ch, b, str(email["email_id"]))
            else:
                outcome = await GW.offer_no_reply_call(ch, b, row)
            await STORE.finish(sid, "whatsapp_session" if outcome == "sent" else "skipped", outcome)
            done.append({"kind": "no_reply_call", "booking": b["id"], "outcome": outcome})
    return done


async def tap_offers(now: datetime) -> List[dict]:
    """Sasha 131 · a one-tap page not pressed within SASHA_TAP_WINDOW_MIN → ONE question: email them (or, urgent, call and
    email; or, with no address, call). Its yes leads to that route's own read-back and yes."""
    from . import decide as D, guest_whatsapp as GW, ladder_routes as LR
    if not tap_escalation_on() or STORE is None or GW.STORE is None or LR.LADDER_STORE is None or not hasattr(LR.LADDER_STORE, "stale_links"):
        return []
    done: List[dict] = []
    chans = {c["account_id"]: c for c in await GW.STORE.all_channels()}
    for l in await LR.LADDER_STORE.stale_links(now - timedelta(minutes=D.tap_window_min())):
        ch = chans.get(l["account_id"])
        if not ch or not l.get("local_date"):
            continue
        row = await LR.LADDER_STORE.get_read(l["account_id"], l["read_id"])
        kinds = {f.get("kind") for f in ((row or {}).get("read") or {}).get("facts") or []}
        tz = l.get("local_timezone") or "Europe/Madrid"
        start = datetime.combine(l["local_date"], l["local_time"], tzinfo=ZoneInfo(tz))
        soon = (start - now) < timedelta(hours=D.urgent_hours())
        prefer = "call_email" if soon and {"phone", "email"} <= kinds else "email" if "email" in kinds else "call" if "phone" in kinds else None
        if prefer is None:
            continue
        sid = await STORE.claim({"account_id": l["account_id"], "trip_item_id": l["trip_item_id"], "kind": "tap_expired",
                                 "local_day": now.astimezone(ZoneInfo(tz)).date(), "status_at_send": "link_sent"})
        if sid is None:
            continue
        from . import escalation as ESC
        if ESC.has_plan(l.get("read_back_lines")) and "email" in kinds:   # Sasha 132 · the guest's one yes covered this email
            outcome = await GW.auto_email_from_link(ch, l, row)
            await STORE.finish(sid, "whatsapp_session" if outcome == "sent" else "skipped", f"auto: {outcome}")
            done.append({"kind": "tap_expired", "booking": l["trip_item_id"], "outcome": f"auto: {outcome}"})
            continue
        b = {"id": l["trip_item_id"], "venue": l["venue"], "date": l["local_date"].isoformat(), "time": l["local_time"].strftime("%H:%M"),
             "party": l.get("party_size"), "read_id": l["read_id"]}
        ask = {"email": ("email them instead", "Yes, prepare the email"), "call": ("call them instead", "Yes, prepare the call"),
               "call_email": ("call and email them now — it's soon", "Yes, prepare both")}[prefer]
        outcome = await GW.offer_escalation(ch, b, row, prefer, f"Not booked on {l['venue']}'s page yet for {SN.day_words(b['date'])} at "
                                            f"{b['time']}. Shall I {ask[0]}? I'll show you exactly what I'll send first.", ask[1])
        await STORE.finish(sid, "whatsapp_session" if outcome == "sent" else "skipped", outcome)
        done.append({"kind": "tap_expired", "booking": l["trip_item_id"], "outcome": outcome})
    return done


# ── the loop (the retention pattern) ────────────────────────────────────────────────────────────────────────────────

_task: Optional[asyncio.Task] = None


async def _forever() -> None:
    while True:
        try:
            await tick(NOW())
            for what in await no_reply_offers(NOW()) + await tap_offers(NOW()):   # Sasha 130/131 · the escalation policy
                log.info("[proactive] %s", what)
            from . import invitations as IV   # S-80 · an invitation's booking confirmed or cancelled → the invitee told
            for what in await IV.tick():
                log.info("[invite] %s", what)
        except StorageUnavailable as e:
            log.error("[proactive] not running: %s", e.detail)   # 026 not applied yet: said, every ten minutes
            await asyncio.sleep(600)
            continue
        except Exception as e:
            log.error("[proactive] tick failed: %s: %s", type(e).__name__, e)
        await asyncio.sleep(TICK_S)


def start() -> None:
    global _task
    if _task is None and os.getenv("SASHA_PROACTIVE_LOOP", "1") == "1" and os.getenv("DATABASE_URL", "").strip():
        _task = asyncio.create_task(_forever())


# ── the web side: prefs, the starting point, and the founder's demo trigger ─────────────────────────────────────────

router = APIRouter(prefix="/proactive", tags=["booking-proactive"])


def _refuse(status: int, rule: str, message: str) -> JSONResponse:
    return JSONResponse({"ok": False, "rule": rule, "message": message}, status_code=status)


@router.get("")
async def proactive_view(request: Request):
    from .account import account_for
    account = account_for(request)
    if STORE is None:
        return _refuse(503, "storage_not_provisioned", "reminders are not set up on this server")
    try:
        prefs = await STORE.get_prefs(account)
        place = await STORE.default_place(account)
    except StorageUnavailable as e:
        return _refuse(503, e.rule, e.detail)
    return {"prefs": prefs or {"all_off": False, "off_kinds": []}, "place": place, "kinds": list(KINDS)}


@router.put("/prefs")
async def proactive_prefs(request: Request):
    from .account import account_for
    account = account_for(request)
    body = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
    off = [k for k in (body.get("off_kinds") or []) if k in KINDS]
    try:
        return {"prefs": await STORE.set_prefs(account, all_off=bool(body.get("all_off")), off_kinds=off)}
    except StorageUnavailable as e:
        return _refuse(503, e.rule, e.detail)


@router.post("/place")
async def proactive_place(request: Request):
    """The starting point for "time to leave" — only what the guest types; never inferred, never geocoded and stored."""
    from .account import account_for
    from .vault.guard import looks_like_secret
    account = account_for(request)
    try:
        body = await request.json()
    except Exception:
        body = {}
    label = re.sub(r"\s+", " ", str(body.get("label") or "")).strip()[:40]
    address = re.sub(r"\s+", " ", str(body.get("address") or "")).strip()[:200]
    if not label or len(address) < 3:
        return _refuse(422, "place_invalid", "give it a name (e.g. \"my hotel\") and an address")
    if looks_like_secret(address) or looks_like_secret(label):
        return _refuse(422, "place_invalid", "that doesn't look like an address")
    try:
        return {"place": await STORE.save_place(account, label, address)}
    except StorageUnavailable as e:
        return _refuse(503, e.rule, e.detail)


@router.delete("/place")
async def proactive_place_delete(request: Request):
    from .account import account_for
    try:
        return {"deleted": await STORE.delete_places(account_for(request))}
    except StorageUnavailable as e:
        return _refuse(503, e.rule, e.detail)


@router.post("/run")
async def proactive_run(request: Request):
    """S-83 §8 · the founder's demo trigger: "send what is due as of {time}" for HIS account only — said on stage."""
    from .account import account_for
    from .identity import founder_account
    account = account_for(request)
    if account != founder_account():
        return _refuse(403, "founder_only", "this demo trigger is only for the founder's own account")
    try:
        body = await request.json()
        as_of = datetime.fromisoformat(str(body.get("as_of")))
        if as_of.tzinfo is None:
            raise ValueError
    except Exception:
        return _refuse(422, "as_of_invalid", "send {as_of: an ISO time with its offset, e.g. 2026-10-02T18:00:00+02:00}")
    try:
        return {"as_of": as_of.isoformat(), "done": await tick(as_of, only_account=account)}
    except StorageUnavailable as e:
        return _refuse(503, e.rule, e.detail)


def status() -> dict:
    return {"loop": _task is not None, "daily_max": daily_max(), "quiet": f"{QUIET[0]:02d}:00–{QUIET[1]:02d}:00",
            "templates": bool(os.getenv("SASHA_WA_TEMPLATES", "").strip()), "routes_key": bool(os.getenv("GOOGLE_PLACES_API_KEY", "").strip())}


__all__ = ["tick", "render", "start", "router", "status", "MemoryProactiveStore", "PostgresProactiveStore", "travel"]
