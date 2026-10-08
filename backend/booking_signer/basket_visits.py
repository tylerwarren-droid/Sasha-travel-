"""CR 54 · CAMPUS VISITS AS BASKET ITEMS — kind 'visit' in public.trip_basket_items (035_basket_visits.sql), one row per school
visit of a campus tour, the tour being the journey (its `trips` row).

    suggested ──prepare_registration──▶ prepared ──check_confirmation──▶ registered
        │                                   └──────────────────────────▶ not_confirmed  (a reply that doesn't match; can be re-checked)
        └──▶ cancelled

Who writes what (the AgAPI roles, as basket.py names them):
    MAGELLAN  suggest()                        the tour's visits, as `suggested`
    AUSTEN    prepared()                       the school's own form filled, the hand-over sent to the phone
    PACIOLI   registered(), not_confirmed()    ONLY from the school's own confirmation, matched (products/campus/confirm.py) —
                                               the only writer of a visit's status line; the model never writes one

basket.py is not changed: this module uses its runner and row shape. Every read and write is scoped to the account.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import date, datetime
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from . import basket as BK

log = logging.getLogger(__name__)

KIND = "visit"
PROVIDER = "campus"
STATES = ("suggested", "prepared", "registered", "not_confirmed", "cancelled")
PREPARABLE = ("suggested", "prepared", "not_confirmed")     # a hand-over can be opened again until the school confirms
CHECKABLE = ("suggested", "prepared", "not_confirmed")       # a pattern school (no form of ours) is checked straight from suggested
ET = ZoneInfo("America/New_York")                            # the schools' local time (every CampusMe school today is US East)


class VisitError(BK.BasketError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


def _starts(v: dict) -> Optional[datetime]:
    if not v.get("date"):
        return None
    if not v.get("start"):
        return None
    return datetime.combine(date.fromisoformat(v["date"]), datetime.strptime(v["start"], "%H:%M").time(), ET)


def _ends(v: dict) -> Optional[datetime]:
    s = _starts(v)
    if not s or not v.get("end"):
        return None
    return datetime.combine(s.date(), datetime.strptime(v["end"], "%H:%M").time(), ET)


def _snap(v: dict) -> dict:
    """What the family was shown for this visit — the school's own session, where it was read."""
    keep = ("school", "name", "date", "start", "end", "title", "place", "read", "link", "session", "spaces", "status", "why")
    return {k: v.get(k) for k in keep}


class MemoryVisits:
    """The same contract without a database (tests, and a server with no store)."""

    def __init__(self) -> None:
        self.rows: Dict[str, Dict[str, Any]] = {}

    async def suggest(self, account: str, trip_id: str, visits: List[dict], party: Optional[int]) -> List[str]:
        for k in [k for k, r in self.rows.items() if r["account_id"] == account and r["trip_id"] == trip_id and r["state"] == "suggested"]:
            del self.rows[k]
        ids = []
        for v in visits:
            i = str(uuid.uuid4())
            s = _starts(v)
            self.rows[i] = {"id": i, "trip_id": trip_id, "account_id": account, "kind": KIND, "state": "suggested",
                            "day": v.get("date"), "starts_at": s.isoformat() if s else None, "party": party, "provider": PROVIDER,
                            "provider_ref": v.get("school"), "snapshot": _snap(v), "booking_reference": None, "status_line": None,
                            "handover_id": None, "check": None}
            ids.append(i)
        return ids

    async def get(self, account: str, item_id: str) -> Optional[dict]:
        r = self.rows.get(item_id)
        return dict(r) if r and r["account_id"] == account else None

    async def of_account(self, account: str, trip_id: Optional[str] = None) -> List[dict]:
        rows = [dict(r) for r in self.rows.values() if r["account_id"] == account and (trip_id is None or r["trip_id"] == trip_id)]
        return sorted(rows, key=lambda r: (r["day"] or "9999-12-31", r["starts_at"] or ""))

    async def _move(self, account: str, item_id: str, to: str, allowed: tuple, **set_) -> dict:
        r = self.rows.get(item_id)
        if not r or r["account_id"] != account:
            raise VisitError("visit_not_found", "there's no such visit on this account")
        if r["state"] not in allowed:
            raise VisitError(f"visit_{r['state']}", f"that visit is already {r['state'].replace('_', ' ')}")
        r.update(state=to, **set_)
        return dict(r)


class PostgresVisits:
    """public.trip_basket_items, kind 'visit' (needs 035_basket_visits.sql applied)."""

    async def suggest(self, account: str, trip_id: str, visits: List[dict], party: Optional[int]) -> List[str]:
        async def fn(conn):
            async with conn.transaction():
                await conn.execute("delete from trip_basket_items where account_id = $1 and trip_id = $2 and kind = 'visit' "
                                   "and state = 'suggested'", uuid.UUID(account), uuid.UUID(trip_id))
                out = []
                for v in visits:
                    out.append(await conn.fetchval(
                        "insert into trip_basket_items (trip_id, account_id, kind, state, day, starts_at, ends_at, party, provider, "
                        "provider_ref, snapshot, is_test) values ($1, $2, 'visit', 'suggested', $3, $4, $5, $6, $7, $8, $9::jsonb, false) "
                        "returning id", uuid.UUID(trip_id), uuid.UUID(account), date.fromisoformat(v["date"]) if v.get("date") else None,
                        _starts(v), _ends(v), party, PROVIDER, v.get("school"), json.dumps(_snap(v), default=str)))
                return [str(i) for i in out]
        return await BK._go(fn)

    async def get(self, account: str, item_id: str) -> Optional[dict]:
        try:
            iid = uuid.UUID(item_id)
        except (ValueError, TypeError):
            return None
        r = await BK._go(lambda c: c.fetchrow("select * from trip_basket_items where account_id = $1 and id = $2 and kind = 'visit'",
                                              uuid.UUID(account), iid))
        return _out(r) if r else None

    async def of_account(self, account: str, trip_id: Optional[str] = None) -> List[dict]:
        rows = await BK._go(lambda c: c.fetch(
            "select * from trip_basket_items where account_id = $1 and kind = 'visit' and ($2::uuid is null or trip_id = $2) "
            "order by coalesce(day, '9999-12-31'), starts_at nulls last, created_at", uuid.UUID(account),
            uuid.UUID(trip_id) if trip_id else None))
        return [_out(r) for r in rows]

    async def _move(self, account: str, item_id: str, to: str, allowed: tuple, **set_) -> dict:
        snap_extra = {k: v for k, v in set_.items() if k in ("handover_id", "check")}

        async def fn(conn):
            r = await conn.fetchrow("select state from trip_basket_items where account_id = $1 and id = $2 and kind = 'visit' for update",
                                    uuid.UUID(account), uuid.UUID(item_id))
            if not r:
                raise VisitError("visit_not_found", "there's no such visit on this account")
            if r["state"] not in allowed:
                raise VisitError(f"visit_{r['state']}", f"that visit is already {r['state'].replace('_', ' ')}")
            return await conn.fetchrow(
                "update trip_basket_items set state = $3, booking_reference = coalesce($4, booking_reference), "
                "status_line = coalesce($5, status_line), snapshot = snapshot || $6::jsonb, updated_at = now() "
                "where account_id = $1 and id = $2 returning *", uuid.UUID(account), uuid.UUID(item_id), to,
                set_.get("booking_reference"), set_.get("status_line"), json.dumps(snap_extra, default=str))
        return _out(await BK._go(fn))


def _out(r) -> dict:
    d = BK._row(r)
    s = d.get("snapshot") or {}
    d["handover_id"], d["check"] = s.get("handover_id"), s.get("check")
    return d


STORE: Any = None   # tests set a MemoryVisits(); otherwise Postgres when the basket has a database


def store():
    if STORE is not None:
        return STORE
    return PostgresVisits() if BK._run() is not None else _MEM


_MEM = MemoryVisits()


# ── the writes, each under its role ─────────────────────────────────────────────────────────────────────────────────

async def suggest(account: str, trip_id: str, visits: List[dict], party: Optional[int] = None) -> List[str]:
    """MAGELLAN · the tour's visits as `suggested` (a new tour of the same trip replaces the suggested ones; never a prepared one)."""
    ids = await store().suggest(account, trip_id, visits, party)
    BK._log(BK.MAGELLAN, "%d visits suggested on trip %s", len(ids), trip_id[:8])
    return ids


async def prepared(account: str, item_id: str, handover_id: Optional[str]) -> dict:
    """AUSTEN · the school's own form filled and handed over to the phone. Never `registered`: only the school says that."""
    r = await store()._move(account, item_id, "prepared", PREPARABLE, handover_id=handover_id)
    BK._log(BK.AUSTEN, "visit %s prepared", item_id[:8])
    return r


async def registered(account: str, item_id: str, number: Optional[str], line: str, check: dict) -> dict:
    """PACIOLI · the school's own confirmation matched what was prepared — the ONLY way a visit becomes `registered`."""
    if not check.get("confirmed"):
        raise VisitError("not_confirmed", "the school's reply doesn't confirm this visit")
    r = await store()._move(account, item_id, "registered", CHECKABLE, booking_reference=number, status_line=line, check=check)
    BK._log(BK.PACIOLI, "visit %s registered (%s)", item_id[:8], "with number" if number else "no number")
    return r


async def not_confirmed(account: str, item_id: str, line: str, check: dict) -> dict:
    """PACIOLI · a reply was checked and doesn't confirm it (said, never assumed)."""
    r = await store()._move(account, item_id, "not_confirmed", CHECKABLE, status_line=line, check=check)
    BK._log(BK.PACIOLI, "visit %s not confirmed", item_id[:8])
    return r


async def items(account: str, trip_id: Optional[str] = None) -> List[dict]:
    try:
        return await store().of_account(account, trip_id)
    except BK.BasketError as e:
        log.info("[basket_visits] no visits read: %s", e)
        return []


async def get(account: str, item_id: str) -> Optional[dict]:
    return await store().get(account, item_id)

