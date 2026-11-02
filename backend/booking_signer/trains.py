"""Sasha 327 · TRAINS ARE TRAINS — a ticket he bought himself is a TRAIN on his ONE trip record (trip_items, type 'train').

  THE READER   the ONE Gmail reader (mailbox.sync) hands a seller's email to AgAPI's ONE reader (venue.confirmation, CR 152, through
               agapi.self_booked.from_mail). AgAPI decides whose it is and what it says; Sasha keeps no operator list and no rail parser.
  THE RECORD   keep(account, got) writes AgAPI's answer onto trip_items, under the account's bookings trip: type 'train', status
               'confirmed', provider_name = the operator, booking_reference = the localizador, date_time = departure (Europe/Madrid),
               duration_minutes = arrival − departure, location_name = "Origin → Destination", party_size = passengers,
               price_usd NULL (it never holds euros; the price stays on AgAPI's act), escalation_notes = "agapi_act:<act_id>" — the
               link to AgAPI's booking record. One act, one item: the same email (or the same act) never makes a second one.
  NOT YET      before sql/046 the database refuses type 'train' (trip_items_type_check): the refusal is caught and logged, the ticket
               stays on AgAPI's act and on the mailbox find (its facts carry act_id), and reread() writes it once the SQL is in —
               never lost, never stored as 'other'.
  THE VIEW     view(account, rows): a train row gets its every field — AgAPI's live answer (venue.manage_options: operator, fare,
               departure, the change/cancel rules and the operator's own manage page), and the rest of AgAPI's reader's answer as the
               mailbox find kept it (train number, coach, seat, arrival, passengers, price). Read on view, never copied onto the item.
  RE-READ      reread(account): an 'other' item tied to AgAPI's train record — its act link, its reference on a train act AgAPI
               answered, or the mailbox find AgAPI read for it — becomes 'train'. Not tied → left as it is, and the log says why
               (never a guess from its name).
"""
from __future__ import annotations

import logging
import re
import time
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

log = logging.getLogger("booking_signer.trains")

ZONE = "Europe/Madrid"
MARK = "agapi_act:"
_ACT = re.compile(r"agapi_act:(act_[0-9A-Za-z]+)")
#: AgAPI's reader's answer (confirmations.rail) as the mailbox find keeps it — every field but the card
TRIP_KEYS = ("operator", "kind", "origin", "destination", "date", "departs", "arrives", "train", "coach", "seat", "reference",
             "passengers", "fare", "price_eur")


class TypeNotAllowed(Exception):
    """The database's trip_items_type_check has no 'train' yet (sql/046 not applied)."""


def link(act_id: str) -> str:
    return f"{MARK}{act_id}"


def act_of(notes: Optional[str]) -> Optional[str]:
    m = _ACT.search(notes or "")
    return m.group(1) if m else None


def find_facts(got: Dict[str, Any]) -> Dict[str, Any]:
    """The mailbox find's facts for a ticket AgAPI read: its answer's fields (no card, no body) and the act it opened."""
    t = got.get("trip") or {}
    return {**{k: t.get(k) for k in TRIP_KEYS}, "kind": got.get("kind") or t.get("kind") or "train", "act_id": got.get("act_id")}


def _minutes(dep: Optional[str], arr: Optional[str]) -> Optional[int]:
    try:
        d, a = datetime.strptime(dep or "", "%H:%M"), datetime.strptime(arr or "", "%H:%M")
    except ValueError:
        return None
    if a < d:
        a += timedelta(days=1)   # an overnight train arrives the next day
    return int((a - d).total_seconds() // 60)


def fields(got: Dict[str, Any]) -> Dict[str, Any]:
    """AgAPI's answer → the trip item's columns (existing columns only, each used for what it means)."""
    t = got.get("trip") or {}
    at = None
    if t.get("date") and t.get("departs"):
        at = datetime.fromisoformat(f"{t['date']}T{t['departs']}").replace(tzinfo=ZoneInfo(ZONE))
    leg = f"{t['origin']} → {t['destination']}" if t.get("origin") and t.get("destination") else None
    return {"type": "train", "status": "confirmed", "provider_name": (t.get("operator") or "Train")[:200], "booking_reference": t.get("reference"),
            "date_time": at, "duration_minutes": _minutes(t.get("departs"), t.get("arrives")), "location_name": leg, "party_size": t.get("passengers"),
            "price_usd": None,   # never euros in a dollar column: the price is on AgAPI's act
            "currency": "EUR" if t.get("price_eur") is not None else None, "local_timezone": ZONE, "escalation_notes": link(got["act_id"])}


def is_train(got: Optional[Dict[str, Any]]) -> bool:
    """AgAPI's kind decides (its kind table) — never Sasha's guess."""
    return bool(got and got.get("act_id") and (got.get("kind") or (got.get("trip") or {}).get("kind") or "train") == "train")


# ── the store: Memory for tests, Postgres for real ──────────────────────────────────────────────────────────────────────

class MemoryTrainStore:
    def __init__(self, allow_train: bool = True) -> None:
        self.items: Dict[str, dict] = {}
        self.allow_train = allow_train   # False: the database before sql/046

    async def item_of_act(self, account, act_id):
        return next((dict(i) for i in self.items.values() if i["account_id"] == account and act_of(i.get("escalation_notes")) == act_id), None)

    async def add(self, account, f):
        if f["type"] == "train" and not self.allow_train:
            raise TypeNotAllowed("trip_items_type_check")
        iid = str(uuid.uuid4())
        self.items[iid] = {"id": iid, "account_id": account, **f}
        return iid

    async def others(self, account):
        return [dict(i) for i in self.items.values() if i["account_id"] == account and i["type"] == "other"]

    async def retype(self, account, item_id, act_id):
        i = self.items.get(item_id)
        if not i or i["account_id"] != account or i["type"] != "other":
            return False
        if not self.allow_train:
            raise TypeNotAllowed("trip_items_type_check")
        i["type"] = "train"
        if not act_of(i.get("escalation_notes")):
            i["escalation_notes"] = " · ".join(x for x in (i.get("escalation_notes"), link(act_id)) if x)
        return True


class PostgresTrainStore:
    def __init__(self, base) -> None:
        self._base = base

    async def _run(self, fn):
        import asyncpg
        try:
            return await self._base._run(fn)
        except asyncpg.exceptions.CheckViolationError as e:
            if "trip_items_type_check" in str(e):
                raise TypeNotAllowed("trip_items_type_check") from None
            raise

    async def item_of_act(self, account, act_id):
        r = await self._run(lambda c: c.fetchrow(
            "select ti.id, ti.type from trip_items ti join trips t on t.id = ti.trip_id where t.owner_id = $1 and ti.escalation_notes like $2 "
            "order by ti.created_at limit 1", uuid.UUID(account), f"%{link(act_id)}%"))
        return {"id": str(r["id"]), "type": r["type"]} if r else None

    async def add(self, account, f):
        from .store import BOOKINGS_TRIP_TITLE

        async def go(c):
            async with c.transaction():
                trip = await c.fetchval("select id from trips where owner_id = $1 and title = $2 limit 1", uuid.UUID(account), BOOKINGS_TRIP_TITLE)
                if trip is None:
                    trip = await c.fetchval("insert into trips (owner_id, title) values ($1,$2) returning id", uuid.UUID(account), BOOKINGS_TRIP_TITLE)
                return await c.fetchval(
                    "insert into trip_items (trip_id, type, status, provider_name, booking_reference, date_time, duration_minutes, location_name, "
                    "party_size, price_usd, currency, local_timezone, escalation_notes) values ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13) returning id",
                    trip, f["type"], f["status"], f["provider_name"], f["booking_reference"], f["date_time"], f["duration_minutes"],
                    f["location_name"], f["party_size"], f["price_usd"], f["currency"], f["local_timezone"], f["escalation_notes"])
        return str(await self._run(go))

    async def others(self, account):
        rows = await self._run(lambda c: c.fetch(
            "select ti.id, ti.provider_name, ti.booking_reference, ti.escalation_notes from trip_items ti join trips t on t.id = ti.trip_id "
            "where t.owner_id = $1 and ti.type = 'other'", uuid.UUID(account)))
        return [{**dict(r), "id": str(r["id"])} for r in rows]

    async def retype(self, account, item_id, act_id):
        n = await self._run(lambda c: c.execute(
            "update trip_items ti set type = 'train', updated_at = now(), escalation_notes = case when ti.escalation_notes like '%' || $3 || '%' "
            "then ti.escalation_notes else concat_ws(' · ', nullif(ti.escalation_notes, ''), $3) end "
            "from trips t where t.id = ti.trip_id and ti.id = $1 and t.owner_id = $2 and ti.type = 'other'",
            uuid.UUID(item_id), uuid.UUID(account), link(act_id)))
        return str(n).endswith(" 1")


STORE: Any = None


# ── keep: AgAPI's answer → the ONE trip record ──────────────────────────────────────────────────────────────────────────

async def keep(account: str, got: Dict[str, Any]) -> Optional[str]:
    """The ticket AgAPI read → its train item (the existing one for that act, else a new one). None: not a train, no store, or the
    database can't hold 'train' yet (logged; the ticket stays on AgAPI's act and the mailbox find)."""
    if STORE is None or not is_train(got):
        return None
    act = got["act_id"]
    had = await STORE.item_of_act(account, act)
    if had:
        return had["id"]
    try:
        iid = await STORE.add(account, fields(got))
    except TypeNotAllowed:
        log.warning("[trains] the database has no trip type 'train' yet (run booking_signer/sql/046_train_items.sql): the ticket stays on "
                    "AgAPI's act %s and the mailbox find; it is written as a train once the SQL is in", act)
        return None
    log.info("[trains] AgAPI's act %s is a train on the trip (item %s)", act, iid)
    return iid


# ── the view: every field, read when shown ─────────────────────────────────────────────────────────────────────────────

_OPTIONS: Dict[str, tuple] = {}   # act → (when read, venue.manage_options' answer): the Trip tab polls every 6 s
OPTIONS_FOR_S = 300


async def options(account: str, act_id: str) -> Optional[dict]:
    from agapi import self_booked as SB
    hit = _OPTIONS.get(act_id)
    if hit and time.time() - hit[0] < OPTIONS_FOR_S:
        return hit[1]
    try:
        res = await SB.manage(account, act_id)
    except Exception as e:   # AgAPI not answering: the row still shows what is known
        log.info("[trains] manage options not read for %s: %s", act_id, type(e).__name__)
        return hit[1] if hit else None
    _OPTIONS[act_id] = (time.time(), res)
    return res


async def _facts_by_act(account: str) -> Dict[str, dict]:
    from . import mailbox as MB
    if MB.STORE is None:
        return {}
    try:
        finds = await MB.STORE.list_finds(account)
    except Exception as e:
        log.info("[trains] mailbox finds not read: %s", type(e).__name__)
        return {}
    return {(f.get("facts") or {}).get("act_id"): f["facts"] for f in finds
            if f.get("parsed_by") == "agapi" and (f.get("facts") or {}).get("act_id")}


def train_of(row: dict, facts: Optional[dict], opts: Optional[dict]) -> dict:
    """The train as the trip shows it: AgAPI's live answer first, its reader's answer (the find) for the rest, the item's own last."""
    f, o = facts or {}, opts or {}
    where = o.get("where") or {}
    loc = str(row.get("location") or row.get("where") or "")   # the trip item's "Origin → Destination" (the itinerary calls it where)
    o_d = [x.strip() for x in loc.split("→", 1)] if "→" in loc else [None, None]
    dep = str(o.get("departs_at") or "")
    when = str(row.get("when") or "")
    return {"operator": o.get("operator") or f.get("operator") or row.get("venue") or row.get("title"), "number": f.get("train"),
            "origin": f.get("origin") or o_d[0], "destination": f.get("destination") or o_d[1],
            "date": dep[:10] or f.get("date") or row.get("date") or when[:10] or None,
            "departs": dep[11:16] or f.get("departs") or row.get("time") or when[11:16] or None,
            "arrives": f.get("arrives"), "coach": f.get("coach"), "seat": f.get("seat"),
            "reference": where.get("reference") or f.get("reference") or row.get("booking_reference") or row.get("reference"),
            "passengers": f.get("passengers") or row.get("party"), "fare": o.get("fare") or f.get("fare"), "price_eur": f.get("price_eur"),
            "manage": ({"page": where["page"], "label": "Manage your ticket", "how": where.get("how"),
                        "options": [{"action": x.get("action"), "say": x.get("say"), "open_now": x.get("open_now")} for x in o.get("options") or []]}
                       if where.get("page") else None)}


async def view(account: Optional[str], rows: List[dict]) -> List[dict]:
    """Each train row (type 'train', its AgAPI act) with `train`: every field, read now. Other rows as they are."""
    trains = [r for r in rows if "train" in (r.get("type"), r.get("kind")) and r.get("agapi_act")]
    if not account or not trains:
        return rows
    facts = await _facts_by_act(account)
    for r in trains:
        r["train"] = train_of(r, facts.get(r["agapi_act"]), await options(account, r["agapi_act"]))
        if r["train"].get("manage"):
            r["url"] = r["train"]["manage"]["page"]
    return rows


def one_row(rows: List[dict]) -> List[dict]:
    """One booking, one row: the train item IS the ticket — its AgAPI act's own row (venue.bookings) is not shown again."""
    acts = {str(r["agapi_act"]) for r in rows if r.get("type") == "train" and r.get("agapi_act")}
    return [r for r in rows if not (r.get("type") != "train" and str(r.get("id") or "") in acts)]


# ── the reminder's words ───────────────────────────────────────────────────────────────────────────────────────────────

def leg(b: dict) -> str:
    t = b.get("train") or {}
    if t.get("origin") and t.get("destination"):
        return f"{t['origin']} → {t['destination']}"
    return str(b.get("location") or "")


def line(b: dict, day: str) -> str:
    """"Tomorrow: your <operator> train <number> <origin> → <destination> at <time>, coach X, seat Y, ref R. Manage your ticket: <page>"."""
    t = b.get("train") or {}
    op = t.get("operator") or b.get("venue") or "your"
    head = f"{day}: your {op} train" + (f" {t['number']}" if t.get("number") else "") + (f" {leg(b)}" if leg(b) else "")
    at = t.get("departs") or b.get("time")
    seat = ", ".join(x for x in ((f"coach {t['coach']}" if t.get("coach") else ""), (f"seat {t['seat']}" if t.get("seat") else "")) if x)
    ref = t.get("reference") or b.get("booking_reference")
    page = (t.get("manage") or {}).get("page")
    return (head + (f" at {at}" if at else "") + (f", {seat}" if seat else "") + (f", ref {ref}" if ref else "") + "."
            + (f" Manage your ticket: {page}" if page else ""))


# ── the re-read: an 'other' item that is AgAPI's train ────────────────────────────────────────────────────────────────

async def _train_acts(account: str, finds: List[dict]) -> Dict[str, dict]:
    """The acts AgAPI answered as trains: the mailbox finds AgAPI read (kind train), and the act pointers kept from its answers."""
    out: Dict[str, dict] = {}
    for f in finds:
        x = f.get("facts") or {}
        act = x.get("act_id") or (f["trip_item_id"] if str(f.get("trip_item_id") or "").startswith("act_") else None)   # a 323 find
        if f.get("parsed_by") == "agapi" and act and (x.get("kind") or f.get("kind")) == "train":
            out[act] = {"reference": x.get("reference"), "find": f}
    try:
        from agapi import venue_submit as VS
        for a in await VS.acts_of(account):
            if a.get("act_id") and a.get("kind") == "train" and a["act_id"] not in out:
                out[a["act_id"]] = {"reference": a.get("reference"), "find": None}
    except Exception as e:
        log.info("[trains] AgAPI's act pointers not read: %s", type(e).__name__)
    return out


async def reread(account: str) -> Dict[str, list]:
    """Once per mailbox sync, idempotent: (1) an 'other' item tied to AgAPI's train record → 'train'; (2) a ticket AgAPI read that has
    no item yet (the SQL wasn't in, or a 323 find) → its train item. → {retyped, added, left: [(item, why)]}."""
    from . import mailbox as MB
    done: Dict[str, list] = {"retyped": [], "added": [], "left": []}
    if STORE is None:
        return done
    finds = await MB.STORE.list_finds(account) if MB.STORE is not None else []
    acts = await _train_acts(account, finds)
    by_ref = {str(v["reference"]).upper(): k for k, v in acts.items() if v.get("reference")}
    for it in await STORE.others(account):
        act = act_of(it.get("escalation_notes"))
        why = None
        if act and act in acts:
            pass
        elif it.get("booking_reference") and str(it["booking_reference"]).upper() in by_ref:
            act = by_ref[str(it["booking_reference"]).upper()]
        else:
            act = next((k for k, v in acts.items() if v.get("find") and str(v["find"].get("trip_item_id")) == str(it["id"])), None)
        if not act:
            why = ("its act " + act_of(it.get("escalation_notes")) + " is not one AgAPI answered as a train") if act_of(it.get("escalation_notes")) \
                else "no AgAPI train record ties to it (no act link, no reference on a train act, no find AgAPI read for it)"
        elif (await STORE.item_of_act(account, act) or {}).get("id") not in (None, it["id"]):
            why = f"AgAPI's act {act} already has its train item"
        if why:
            log.info("[trains] 'other' item %s left as it is: %s", it["id"], why)
            done["left"].append((it["id"], why))
            continue
        try:
            if await STORE.retype(account, it["id"], act):
                log.info("[trains] 'other' item %s is AgAPI's train (act %s): re-read as a train", it["id"], act)
                done["retyped"].append(it["id"])
        except TypeNotAllowed:
            log.warning("[trains] 'other' item %s is a train (act %s) but the database has no type 'train' yet (sql/046): left for now",
                        it["id"], act)
            done["left"].append((it["id"], "sql/046 not applied"))
    for act, v in acts.items():
        f = v.get("find")
        if not f or (f.get("trip_item_id") and not str(f["trip_item_id"]).startswith("act_")):
            continue
        x = f.get("facts") or {}
        iid = await keep(account, {"act_id": act, "kind": x.get("kind") or "train", "trip": x})
        if iid:
            await MB.STORE.set_find(f["id"], trip_item_id=iid,
                                    facts={**x, "act_id": act} if not x.get("act_id") else x)
            done["added"].append(iid)
    return done


__all__ = ["keep", "view", "one_row", "reread", "line", "fields", "find_facts", "act_of", "link", "TRIP_KEYS", "TypeNotAllowed",
           "MemoryTrainStore", "PostgresTrainStore"]
