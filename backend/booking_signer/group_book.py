"""Sasha 334 · GROUP MOVEMENT v1 COMPLETE — book / swap / cancel from the master list through AgAPI (CR 163, TEST), and ONE invoice.
docs/sasha/S-334-group-v1.md.

THE ONE RECORDS: each worker's ONE trip (Sasha: trips + trip_basket_items — 332), each worker trip's ONE booking record (AgAPI's
group_bookings — CR 163), each person's ONE vault (the Keep — 333). Sasha passes AgAPI only keep:<id> REFERENCES; AgAPI opens them through
Sasha's resolver (keep_resolver.py) inside its one supplier call, under a grant Sasha makes for THAT worker at THAT moment.

  prepare(account, action, who)   AgAPI's read-back for each worker in the action (group.book / group.swap / group.cancel, nothing done),
                                  held as ONE card → its lines + Yes / No (sasha.yes_buttons — 330's one place)
  confirm(account, card, choice)  once (claimed): No → nothing; Yes → each worker: the organiser's approval of THAT read-back (the app tap,
                                  the WhatsApp reply, or in TEST the sandbox's simulated yes on their words) → the act → the worker's trip
                                  rows settled (booked / cancelled), live on the master list
  invoice(account)                ONE invoice per movement, from AgAPI's records: one line per worker, swaps and cancellations with their
                                  refunds, the total, the REAV note — TEST in test mode
"""
from __future__ import annotations

import asyncio
import logging
import secrets
import time
from datetime import date
from typing import Any, Callable, Dict, List, Optional, Tuple

log = logging.getLogger("booking_signer.group_book")
FAMILY = "group"
CARD_S = 900
_CARDS: Dict[str, Dict[str, Any]] = {}   # card id → {account, action, items, lines, at} — what the organiser is shown, held for their yes
HOTEL_WORDS = ("marriott", "bonvoy", "hilton", "hyatt", "ihg", "accor", "all ", "meliá", "melia", "nh ", "iberostar", "radisson",
               "wyndham", "barceló", "barcelo", "best western", "choice", "leading hotels")


# ── the ONE transport (agapi_route.post), on the group family (the sandbox: CR 163 is TEST) ─────────────────────────────────

async def _call(account: str, op: str, body: dict, approval: Optional[str] = None) -> Dict[str, Any]:
    if CALL is not None:
        return await CALL(op, body, approval)
    from agapi import agapi_route as AR
    url, key = await AR.client_for(FAMILY, account)
    if not key:
        return {"ok": False, "error": {"code": "not_configured", "message": "AgAPI's sandbox key isn't set here"}}
    h = {"Authorization": f"Bearer {key}", "content-type": "application/json", "Idempotency-Key": "s334_" + secrets.token_hex(12),
         **({"AgAPI-Approval-Id": approval} if approval else {})}
    return await AR.post(url, key, op, body, h, 60.0)


CALL = None   # tests replace it: (op, body, approval) → envelope


async def _organiser(account: str) -> Optional[str]:
    r = await _call(account, "users.register", {"external_ref": f"sasha:{account}"})
    return ((r.get("result") or {}).get("end_user_id")) if r.get("ok") else None


# ── a worker as AgAPI takes them: names + Keep REFERENCES only ───────────────────────────────────────────────────────────────

def owner_of(m: Dict[str, Any]) -> str:
    """Sasha 351 · whose vault: the PERSON on the roster (a trip's member is a link to them) — their passport is saved once, for every trip."""
    return str(m.get("person_id") or m["id"])


async def worker_of(m: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    from . import traveller_vault as TV
    v = await TV.vault_view(m)
    if not v["refs"].get("passport"):
        return None
    airline, hotel = [], []
    for name, ref in zip(v["loyalty"], v["refs"]["loyalty"]):
        (hotel if any(w in f"{name.lower()} " for w in HOTEL_WORDS) else airline).append(ref)
    given, _, family = m["name"].partition(" ")
    return {"key": m["id"], "given_name": given, "family_name": family or given,
            "keep": {"passport": v["refs"]["passport"], "loyalty": airline[:4], "hotel_loyalty": hotel[:4]}}


def _refs(w: Dict[str, Any]) -> List[str]:
    k = w.get("keep") or {}
    return [k.get("passport")] + list(k.get("loyalty") or []) + list(k.get("hotel_loyalty") or [])


def _minor(row: Optional[dict]) -> Optional[Dict[str, Any]]:
    """A trip row's price as AgAPI's money ({amount_minor, currency}) — None when the row has none (nothing invented)."""
    if not row or row.get("price_amount") is None:
        return None
    return {"amount_minor": int(round(float(row["price_amount"]) * 100)), "currency": str(row.get("price_currency") or "EUR").upper()}


async def _planned(account: str, m: Dict[str, Any]) -> Dict[str, Any]:
    """Sasha 337 · what the master list showed for this worker, read NOW from their ONE trip (never a copy): the flight row of each day
    and the stay row → {"flight": {day: price}, "stay": price}. CR 164: AgAPI re-prices and says "was €x when Sasha planned it"."""
    from . import groups as G
    if not m.get("trip_id"):
        return {"flight": {}, "stay": None}
    rows = [r for r in await G._items(account, str(m["trip_id"])) if r.get("state") in ("suggested", "chosen")]
    day = lambda r: str(r.get("day") or r.get("starts_at") or "")[:10]
    return {"flight": {day(r): _minor(r) for r in rows if r.get("kind") == "flight" and _minor(r)},
            "stay": next((_minor(r) for r in rows if r.get("kind") == "stay" and _minor(r)), None)}


async def _items(account: str, m: Dict[str, Any], mv: Dict[str, Any]) -> Tuple[Optional[List[dict]], Optional[str]]:
    """The worker's flights out and back and the stay, as AgAPI's own offers (AgAPI books only what it found) — the planned flight when
    AgAPI has it, else its cheapest on that route and day. PATCH (said): Sasha planned with its own Duffel search (332); AgAPI finds again."""
    items = []
    planned = await _planned(account, m)   # Sasha 337 · from the worker's ONE trip, at this moment
    from . import groups as G
    home = G.origin(m)   # Sasha 351 · the ONE answer to where they fly from (the roster's airport, else their city)
    for frm, to, day in ((home, mv["destination"], m["out_date"]), (mv["destination"], home, m["back_date"])):
        q = {"origin": {"query": frm}, "destination": {"query": to}, "date": str(day)[:10], "passengers": 1}
        r = await _call(account, "travel.find_flights", q)
        if not r.get("ok") and (r.get("error") or {}).get("code") in ("upstream_failed", "upstream_rate_limited"):   # Sasha 339 · once more
            await SLEEP(5)
            r = await _call(account, "travel.find_flights", q)
        offers = (r.get("result") or {}).get("offers") or [] if r.get("ok") else []
        if not offers:
            return None, f"no flight {frm} → {to} on {str(day)[:10]} on AgAPI's sandbox" + (f" ({(r.get('error') or {}).get('code')})" if not r.get("ok") else "")
        was = planned["flight"].get(str(day)[:10])
        items.append({"kind": "flight", "ref": offers[0]["offer_ref"], **({"planned_price": was} if was else {}),
                      **({"_price": offers[0]["price"]} if isinstance(offers[0].get("price"), dict) else {})})   # Sasha 339 · AgAPI's own price
    nights = max(1, (date.fromisoformat(str(m["back_date"])[:10]) - date.fromisoformat(str(m["out_date"])[:10])).days)
    r = await _call(account, "travel.find_stays", {"city": {"query": mv.get("hotel_area") or mv["destination"], "country": "ES"},
                                                   "check_in": str(m["out_date"])[:10], "nights": nights, "party": 1})
    res = (r.get("result") or {}) if r.get("ok") else {}
    stays = res.get("stays") or res.get("offers") or []
    if not stays and mv.get("hotel_area"):   # the area as a place AgAPI doesn't know: the destination itself
        r = await _call(account, "travel.find_stays", {"city": {"query": mv["destination"], "country": "ES"}, "check_in": str(m["out_date"])[:10],
                                                       "nights": nights, "party": 1})
        res = (r.get("result") or {}) if r.get("ok") else {}
        stays = res.get("stays") or res.get("offers") or []
    if not stays:
        return None, "no stay found on AgAPI's sandbox"
    s = stays[0]
    items.append({"kind": "stay", "ref": s.get("stay_ref") or s.get("offer_ref") or s.get("ref"), "at": f"{str(m['out_date'])[:10]}T15:00:00", "nights": nights,
                  **({"planned_price": planned["stay"]} if planned["stay"] else {}),
                  **({"_per_night": s["price_per_night"]} if isinstance(s.get("price_per_night"), dict) else {}),   # Sasha 339 · AgAPI's own
                  "_name": ((s.get("name") or {}).get("text") if isinstance(s.get("name"), dict) else s.get("name")) or "the hotel"})
    return items, None


# ── Sasha 339 · the limit at booking, AgAPI's busy answer, a gone offer ─────────────────────────────────────────────────────────

BOOK_PARALLEL = 2          # read-backs prepared at once (AgAPI and Duffel TEST share ONE token: 4 at once drew its limits — the 339 proof)
ACT_PARALLEL = 1           # acts after the yes: one at a time (Duffel TEST refused orders 4 at once; the job makes the time free)
SLEEP = asyncio.sleep      # tests replace it


def _wire(items: List[dict]) -> List[dict]:
    """What AgAPI receives: the item without Sasha's private notes (its prices ride along as _price / _per_night, never sent)."""
    return [{k: v for k, v in i.items() if not k.startswith("_")} for i in items]


def _euros(money: Optional[dict]) -> Optional[float]:
    return money["amount_minor"] / 100 if isinstance(money, dict) and str(money.get("currency") or "").upper() == "EUR" else None


def over_at_booking(items: List[dict], lim: Dict[str, float], kinds=("flight", "stay")) -> Optional[str]:
    """The worker's limit (groups.limit_for — the ONE rules record) against AgAPI's OWN prices for exactly the offers the read-back
    prices: the flights (out + back) against flight_return_eur, the stay's price per night against hotel_night_eur. → the words, or None."""
    words = []
    fl = [_euros(i.get("_price")) for i in items if i.get("kind") == "flight"]
    if "flight" in kinds and lim.get("flight_return_eur") is not None and fl and None not in fl and sum(fl) > lim["flight_return_eur"]:
        words.append(f"flights €{sum(fl):,.0f} > €{lim['flight_return_eur']:,.0f} limit")
    stay = next((i for i in items if i.get("kind") == "stay"), None)
    pn = _euros((stay or {}).get("_per_night"))
    if "stay" in kinds and stay and pn is not None and lim.get("hotel_night_eur") is not None and pn > lim["hotel_night_eur"]:
        words.append(f"{stay.get('_name') or 'the hotel'}: hotel €{pn:,.0f}/night > €{lim['hotel_night_eur']:,.0f} limit")
    return " · ".join(words) or None


def over_priced(priced: List[dict], lim: Dict[str, float], items: Optional[List[dict]] = None, kinds=("flight", "stay")) -> Optional[str]:
    """Sasha 340 · the worker's limit against the READ-BACK's own prices (CR 166: approval_required details.priced — per item {kind,
    offer_id, amount_minor, currency, per_night_minor?}): the flights' amounts (out + back) against flight_return_eur, the stay's per
    night against hotel_night_eur. Never a sentence; a currency other than EUR is never guessed. → the words, or None."""
    eur = lambda x, k="amount_minor": x[k] / 100 if str(x.get("currency") or "").upper() == "EUR" and isinstance(x.get(k), int) else None
    words = []
    fl = [eur(x) for x in priced or [] if x.get("kind") == "flight"]
    if "flight" in kinds and lim.get("flight_return_eur") is not None and fl and None not in fl and sum(fl) > lim["flight_return_eur"]:
        words.append(f"flights €{sum(fl):,.0f} > €{lim['flight_return_eur']:,.0f} limit")
    stay = next((x for x in priced or [] if x.get("kind") == "stay"), None)
    pn = eur(stay, "per_night_minor") if stay else None
    if "stay" in kinds and pn is not None and lim.get("hotel_night_eur") is not None and pn > lim["hotel_night_eur"]:
        name = next((i.get("_name") for i in items or [] if i.get("kind") == "stay" and i.get("ref") == stay.get("offer_id")), None) or "the hotel"
        words.append(f"{name}: hotel €{pn:,.0f}/night > €{lim['hotel_night_eur']:,.0f} limit")
    return " · ".join(words) or None


def _gone(e: dict) -> bool:
    d = e.get("details") or {}
    return e.get("code") == "upstream_refused" and (d.get("reason") == "offer_gone" or
                                                    d.get("duffel_code") in ("offer_no_longer_available", "offer_expired", "not_found"))


async def _read_back(account: str, op: str, body: dict) -> Dict[str, Any]:
    """AgAPI's read-back for one act; its "busy" answer (upstream_rate_limited) waited out ONCE, for the time it gives."""
    r = await _call(account, op, body)
    e = r.get("error") or {}
    if e.get("code") == "upstream_rate_limited":
        await SLEEP(min(float(e.get("retry_after_s") or (e.get("details") or {}).get("retry_after_s") or 10), 20))
        r = await _call(account, op, body)
    return r


async def _records(account: str) -> List[dict]:
    org = await _organiser(account)
    r = await _call(account, "group.bookings", {"end_user": org}) if org else {}
    return ((r.get("result") or {}).get("bookings") or []) if r.get("ok") else []


def _live_record(records: List[dict], member_id: str) -> Optional[dict]:
    return next((b for b in reversed(records) if (b.get("worker") or {}).get("key") == member_id and b.get("state") == "booked"), None)


async def _prepare_worker(account: str, m: dict, st_: Optional[str], who: Optional[List[str]], over_ok: bool, org: str, mv: dict) -> Tuple[str, dict]:
    """Sasha 339 · ONE worker's read-back for group.book → ("item", …) or ("skip", …): the vault, the plan's limit, AgAPI's offers, the
    limit AT BOOKING (AgAPI's own prices), the read-back — a gone offer re-planned once (the planner, the same limits), then held."""
    from . import groups as G
    w = await worker_of(m)   # Sasha 336 · the vault first: without a passport nobody can be booked, over the limit or not
    if not w:
        return "skip", {"name": m["name"], "member_id": m["id"], "kind": "needs_vault", "why": "no passport in their vault yet (invite them)"}
    asked = bool(who and over_ok)   # never over the limit without the organiser's explicit yes to THAT worker
    if st_ == "over limit" and not asked:
        return "skip", {"name": m["name"], "member_id": m["id"], "kind": "over_limit",
                        "why": "over the limit — say \"book " + m["name"].split()[0] + " anyway\" to include them"}
    lim = G.limit_for(mv.get("rules") or {}, m)
    replanned = False
    for attempt in (1, 2):
        its, why = await _items(account, m, mv)
        if not its:
            return "skip", {"name": m["name"], "member_id": m["id"], "kind": "not_found", "why": why}
        body = {"end_user": org, "worker": w, "items": _wire(its)}
        r = await _read_back(account, "group.book", body)
        e = r.get("error") or {}
        if e.get("code") == "approval_required":
            d = e.get("details") or {}
            # Sasha 340 · the limit against the read-back's OWN prices (details.priced, CR 166); AgAPI without them: its offer prices
            over = over_priced(d["priced"], lim, its) if d.get("priced") else over_at_booking(its, lim)
            if over and not asked:
                return "skip", {"name": m["name"], "member_id": m["id"], "kind": "over_at_booking", "why": over}
            return "item", {"op": "group.book", "member": m["id"], "owner": owner_of(m), "name": m["name"], "worker": w, "body": body,
                            "over": st_ == "over limit" or bool(over), "over_words": over, "replanned": replanned,
                            "read_back_id": d["read_back_id"], "sha": d.get("read_back_sha256") or "",
                            "lines": list((d.get("read_back") or {}).get("lines") or [])}
        if _gone(e) and attempt == 1:   # the fare was taken: re-plan THIS worker once (the planner, the same limits), find again
            await G.plan(account, mv["id"], only=[m["id"]])
            m = next((x for x in await G.store().members(mv["id"]) if x["id"] == m["id"]), m)
            replanned = True
            continue
        if _gone(e):
            return "skip", {"name": m["name"], "member_id": m["id"], "kind": "no_fare", "why": "no fare left on their flight, even after a new search — nothing held"}
        return "skip", {"name": m["name"], "member_id": m["id"], "kind": "not_found", "why": e.get("message") or "AgAPI didn't give a read-back"}
    return "skip", {"name": m["name"], "member_id": m["id"], "kind": "no_fare", "why": "no fare left — nothing held"}


async def _agapi_reachable(account: str) -> bool:
    """A key for the group family's target exists (or a test's AgAPI) — else no record can be read, and nothing is settled from it."""
    if CALL is not None:
        return True
    import os
    from agapi import agapi_route as AR
    return bool(os.getenv(AR.key_name(await AR.target_for(FAMILY, account)), "").strip())


def _latest(records: List[dict], member_id: str) -> Optional[dict]:
    return next((b for b in reversed(records) if (b.get("worker") or {}).get("key") == member_id), None)


def record_booked(records: List[dict], members: List[dict]) -> Dict[str, Dict[str, Any]]:
    """Sasha 340 · what a booked worker's master-list row shows, FROM AgAPI's record: the price booked (its parts) and its references."""
    out = {}
    for m in members:
        b = _latest(records, m["id"])
        if b and b.get("state") == "booked":
            parts = b.get("parts") or []
            out[m["id"]] = {"price_eur": round(sum(((p.get("price") or {}).get("amount_minor") or 0) for p in parts) / 100, 2),
                            "references": [p.get("reference") for p in parts if p.get("reference")]}
    return out


def record_states(records: List[dict], members: List[dict]) -> Dict[str, str]:
    """Sasha 339 (Tyler) · each worker's state AS AgAPI'S ONE RECORD SAYS: booked / cancelled (cancelled or swapped out) — absent when AgAPI has
    no record of them. The master list's status reads THIS first; the trip rows only decide for a worker AgAPI never booked."""
    out = {}
    for m in members:
        b = _latest(records, m["id"])
        if b and b.get("state") in ("booked", "cancelled", "swapped_out"):
            out[m["id"]] = "booked" if b["state"] == "booked" else "cancelled"
    return out


async def reconcile(account: str, members: List[dict], records: Optional[List[dict]] = None, booked: Optional[dict] = None) -> Dict[str, str]:
    """Sasha 339 (Tyler) · THE ONE BOOKING RECORD DECIDES: each worker's trip follows AgAPI's group.bookings — their latest record booked →
    their current plan's rows booked (with its references); cancelled / swapped out → cancelled. Run on every master-list read and once
    after every yes, so a trip row and AgAPI's record can never disagree for longer than one read. → rows changed."""
    from . import groups as G, basket as BK
    if records is None:
        if not await _agapi_reachable(account):
            return {}
        records = await _records(account)
    for m in members:
        b = _latest(records, m["id"])
        if not b or not m.get("trip_id"):
            continue
        want = "booked" if b.get("state") == "booked" else "cancelled" if b.get("state") in ("cancelled", "swapped_out") else None
        if not want:
            continue
        rows = [r for r in await G._items(account, str(m["trip_id"])) if not BK.superseded(r) and r.get("state") in ("suggested", "chosen", "booked")]
        if rows and not any(r.get("state") == want for r in rows):   # the trip hasn't heard yet: it follows (once)
            try:
                await _settle(account, str(m["trip_id"]), want, b.get("parts") or [] if want == "booked" else [])
            except Exception as e:
                log.warning("[group_book] %s not reconciled: %s", m["name"], type(e).__name__)
    if booked is not None:
        booked.update(record_booked(records, members))
    return record_states(records, members)


# ── prepare: AgAPI's read-backs, ONE card ───────────────────────────────────────────────────────────────────────────────────

def summary_taps(skipped: List[dict]) -> List[Dict[str, Any]]:
    """Sasha 336 · "Book all" with nothing bookable: a SHORT list with taps — never a paragraph per worker.
    "18 over limit — book anyway?" (the same card and Yes, over_ok for exactly those) · "2 need their vault — invite" (their links)."""
    by: Dict[str, List[dict]] = {}
    for x in skipped:
        by.setdefault(x.get("kind") or "other", []).append(x)
    out: List[Dict[str, Any]] = []
    if by.get("over_limit"):   # Sasha 346 · each tap: `say` (why they're held, from the record) + `label` (the button)
        n = len(by["over_limit"])
        out.append({"label": "Book anyway", "say": f"{n} over the limit",
                    "act": {"action": "book", "who": [x["name"] for x in by["over_limit"]], "over_ok": True}})
    if by.get("over_at_booking"):   # Sasha 339 · over the limit at AgAPI's price now: held, flagged, never booked silently
        ob = by["over_at_booking"]
        label = (f"{ob[0]['name']} — {ob[0]['why']}" if len(ob) == 1 else f"{len(ob)} over the limit at booking ({ob[0]['why']}…)")
        out.append({"label": "Book anyway", "say": label, "act": {"action": "book", "who": [x["name"] for x in ob], "over_ok": True}, "held": [f"{x['name']}: {x['why']}" for x in ob]})
    if by.get("needs_vault"):
        n = len(by["needs_vault"])
        out.append({"label": "Invite", "say": f"{n} {'is' if n == 1 else 'are'} waiting for their passport",
                    "invite": [x["member_id"] for x in by["needs_vault"]]})
    rest = [x for k, v in by.items() if k not in ("over_limit", "needs_vault", "over_at_booking") for x in v]
    if rest:
        out.append({"say": f"{len(rest)} not bookable now — " + "; ".join(f"{x['name']}: {x['why']}" for x in rest[:3]) + ("…" if len(rest) > 3 else "")})
    return out


async def prepare(account: str, action: str, who: Optional[List[str]] = None, swap_to: Optional[str] = None,
                  over_ok: bool = False, newcomer: Optional[Dict[str, Any]] = None,
                  progress: Optional[Callable[[int, int], None]] = None, held: Optional[List[dict]] = None) -> Dict[str, Any]:
    """→ {status: awaiting_yes, read_back, read_back_id (the card), ask, skipped} or {status: nothing, say}."""
    from . import groups as G
    st = G.store()
    mv = await st.movement(account)
    if not mv:
        return {"status": "nothing", "say": "There's no group movement yet."}
    members = await st.members(mv["id"])
    by_name = {m["name"].lower(): m for m in members}
    org = await _organiser(account)
    if not org:
        return {"status": "nothing", "say": "AgAPI's sandbox didn't answer — nothing was prepared."}
    view = {r["member_id"]: r for r in (await G.view(account))["rows"]}
    items, skipped, lines = [], [], []
    records = await _records(account)   # Sasha 339 · AgAPI's ONE booking record, read for book too (never book a worker twice)
    if action == "book":   # Sasha 339 · each worker in parallel (bounded), progress counted — the card in member order
        pick = [by_name[w.lower()] for w in who or [] if w.lower() in by_name] if who else members
        todo = [(m, view.get(m["id"], {}).get("status")) for m in pick if view.get(m["id"], {}).get("status") != "booked"
                and not _live_record(records, m["id"])]   # PATCH (said, Tyler): a belt only — reconcile() makes the trip follow the record
        sem, done = asyncio.Semaphore(BOOK_PARALLEL), [0]
        if progress:
            progress(0, len(todo))

        async def one(m, st_):
            async with sem:
                try:
                    out = await _prepare_worker(account, m, st_, who, over_ok, org, mv)
                except Exception as ex:   # one worker's failure is that worker's, said — never the whole card's
                    log.warning("[group_book] %s not prepared: %s", m["name"], type(ex).__name__)
                    out = ("skip", {"name": m["name"], "member_id": m["id"], "kind": "not_found", "why": "couldn't be prepared just now — try again"})
            done[0] += 1
            if progress:
                progress(done[0], len(todo))
            return out
        for kind, x in await asyncio.gather(*(one(m, st_) for m, st_ in todo)):
            (items if kind == "item" else skipped).append(x)
    elif action == "swap":
        a, b = (by_name.get((who or [""])[0].lower()), by_name.get((swap_to or "").lower()))
        if not a:
            return {"status": "nothing", "say": f"{(who or [''])[0] or 'The one who leaves'} isn't on the list."}
        rec = _live_record(records, a["id"])
        if not rec:
            return {"status": "nothing", "say": f"{a['name']} has no booking to swap."}
        if not b:   # Sasha 336 · the newcomer isn't on the list: the swap adds them (the list's own upload) and invites them, in this flow
            nc = newcomer or {}
            if not (swap_to or "").strip() or not str(nc.get("city") or "").strip():
                return {"status": "needs_details", "need": ["city", "grade"],
                        "say": f"{swap_to or 'The newcomer'} isn't on the list yet — give their home city and grade, and I'll add them "
                               "and invite them to their vault."}
            line = ", ".join([swap_to.strip(), str(nc["city"]).strip(), str(mv.get("starts_on") or ""), str(mv.get("ends_on") or ""),
                              str(nc.get("grade") or "worker").strip()])
            await G.upload(account, G.read_text(line), mv["id"])
            b = next((m for m in await st.members(mv["id"]) if m["name"].lower() == swap_to.strip().lower()), None)
            if not b:
                return {"status": "nothing", "say": f"{swap_to} couldn't be added to the list — check the name and city."}
        w = await worker_of(b)
        if not w:
            from . import traveller_vault as TV
            inv = await TV.invite(account, [b["id"]])
            return {"status": "needs_vault", "added": b["name"] if newcomer else None, "say": (f"{b['name']} is on the list now. " if newcomer else "")
                    + f"{b['name']}'s passport isn't in their vault yet — I've "
                    + ("emailed them their secure link." if inv.get("emailed") else "made their secure link (on the master list to forward).")
                    + " I'll swap as soon as it's there.", "links": inv.get("forward") or []}
        if not (await _planned(account, b))["flight"]:   # Sasha 339 · the newcomer planned from THEIR home city first (the planner)
            await G.plan(account, mv["id"], only=[b["id"]])
            b = next((x for x in await st.members(mv["id"]) if x["id"] == b["id"]), b)
        its, why = await _items(account, b, mv)
        own = [i for i in (its or []) if i.get("kind") == "flight"]
        if not own:
            return {"status": "nothing", "say": f"No flight found for {b['name']} from {G.origin(b) or 'their home airport'} — nothing changed. ({why or 'no offer'})"}
        over = over_at_booking(own, G.limit_for(mv.get("rules") or {}, b), kinds=("flight",))
        if over and not over_ok:
            return {"status": "nothing", "say": f"{b['name']}'s own flights are over the limit: {over}.",
                    "taps": [{"label": "Swap anyway", "say": f"{b['name']} — {over}", "act": {"action": "swap", "who": [a["name"]], "to": b["name"], "over_ok": True}}]}
        items.append({"op": "group.swap", "member": b["id"], "owner": owner_of(b), "from_member": a["id"], "name": f"{a['name']} → {b['name']}", "worker": w,
                      "over": bool(over), "over_words": over,
                      "body": {"end_user": org, "booking_id": rec["booking_id"], "worker": w, "flights": _wire(own)}})   # CR 164 · HIS own flights
    elif action == "cancel":
        for nm in who or []:
            m = by_name.get(nm.lower())
            rec = _live_record(records, m["id"]) if m else None
            if not rec:
                skipped.append({"name": nm, "why": "no booking to cancel"})
                continue
            items.append({"op": "group.cancel", "member": m["id"], "name": m["name"], "body": {"end_user": org, "booking_id": rec["booking_id"]}})
    for it in items:   # AgAPI's read-back for each (nothing is done without the approval)
        if it.get("read_back_id"):   # Sasha 339 · a book item brings its own (prepared in parallel)
            lines += it["lines"] + ([f"⚠ {it['name']} is OVER the group's limit ({it.get('over_words') or 'by the plan'}) — included only because you asked."]
                                    if it.get("over") else []) + (["(Re-planned: the first fare was gone.)"] if it.get("replanned") else []) + [""]
            continue
        r = await _read_back(account, it["op"], it["body"])
        e = r.get("error") or {}
        if e.get("code") != "approval_required":
            skipped.append({"name": it["name"], "why": e.get("message") or "AgAPI didn't give a read-back"})
            it["skip"] = True
            continue
        d = e.get("details") or {}
        it.update(read_back_id=d["read_back_id"], sha=d.get("read_back_sha256") or "", lines=list((d.get("read_back") or {}).get("lines") or []))
        lines += it["lines"] + ([f"⚠ {it['name']} is OVER the group's limit — included only because you asked."] if it.get("over") else []) + [""]
    items = [i for i in items if not i.get("skip")]
    taps = list(held or []) + summary_taps(skipped)   # Sasha 346 · the record's reasons (group_outcome.held) + AgAPI's, on ONE card
    if not items:   # Sasha 346 · "0 can be booked: 5 are waiting for their passport" — the count and each reason, from the record
        zero = {"book": "0 can be booked", "cancel": "0 can be cancelled", "swap": "Nothing swapped"}.get(action, "Nothing done")
        return {"status": "nothing", "say": f"{zero}: " + ("; ".join(t["say"] for t in taps) if taps else "nobody on the list is waiting to be "
                + {"book": "booked", "cancel": "cancelled"}.get(action, "changed")) + ".", "taps": taps, "skipped": skipped}
    cid = "grp_" + secrets.token_hex(10)
    _CARDS[cid] = {"account": account, "action": action, "items": items, "at": time.time()}
    n = len(items)
    verb = {"book": "Book", "swap": "Swap", "cancel": "Cancel"}[action]
    ask = {"book": f"Book {'these ' + str(n) if n > 1 else items[0]['name']}? Everything is on the card (TEST — nothing is charged now).",
           "swap": f"Swap {items[0]['name']}? The difference is on the card (TEST).",
           "cancel": f"Cancel {', '.join(i['name'] for i in items)}? The refund is on the card (TEST)."}[action]
    return {"status": "awaiting_yes", "action": action, "read_back": [l for l in lines if l is not None][:400], "read_back_id": cid, "ask": ask,
            "verb": verb, "skipped": skipped, "taps": taps, "how": "Say `ask` word for word — nothing happens until they say yes."}


# ── Sasha 339 · BOOK ALL is ONE background job: the ONE prepare, its progress, its result — the page follows it ──────────────

JOB_S = 900
CHAT_WAIT_S = 60.0   # the chat waits this long for the card (a turn's deadline is 100 s); else /group shows it
_JOBS: Dict[str, Dict[str, Any]] = {}   # account → its one book job (this worker's memory, R3: one worker)


def job_view(account: str) -> Dict[str, Any]:
    j = _JOBS.get(account)
    if not j or time.time() - j["at"] > JOB_S:
        return {"state": "none"}
    out = {"job": j["id"], "state": j["state"], "total": j["total"], "ready": j["ready"]}
    if j["state"] == "preparing":
        out["say"] = ((f"Booking {j['total']}… {j['ready']} done." if j.get("kind") == "confirm" else f"Preparing {j['total']}… {j['ready']} ready.")
                      if j["total"] else "Preparing…")
    elif j["state"] == "ready":
        out["result"] = j["result"]
    else:
        out["say"] = j.get("why") or "The read-backs couldn't be prepared — nothing was booked. Try again."
    return out


async def start(account: str, who: Optional[List[str]] = None, over_ok: bool = False, held: Optional[List[dict]] = None) -> Dict[str, Any]:
    """Start (or rejoin) this organiser's book job → its view at once. Never waits for the read-backs."""
    j = _JOBS.get(account)
    if j and j["state"] == "preparing" and time.time() - j["at"] < JOB_S:
        return job_view(account)
    j = {"id": "job_" + secrets.token_hex(8), "state": "preparing", "total": 0, "ready": 0, "at": time.time(), "result": None}
    _JOBS[account] = j

    def prog(done: int, total: int) -> None:
        j.update(ready=done, total=total)

    async def run() -> None:
        try:
            j["result"] = await prepare(account, "book", who, over_ok=over_ok, progress=prog, held=held)
            j["state"] = "ready"
        except Exception as e:
            log.error("[group_book] the book job failed: %s", type(e).__name__)
            j.update(state="failed", why="The read-backs couldn't be prepared — nothing was booked. Try again.")
    j["task"] = asyncio.create_task(run())
    await asyncio.sleep(0)
    return job_view(account)


async def wait(account: str, timeout: float) -> Dict[str, Any]:
    """The chat's path: the job's result if it is ready within `timeout`, else its progress (the card then waits on /group)."""
    j = _JOBS.get(account)
    if j and j.get("task") and j["state"] == "preparing":
        try:
            await asyncio.wait_for(asyncio.shield(j["task"]), timeout)
        except asyncio.TimeoutError:
            pass
    return job_view(account)


# ── confirm: once, the organiser's yes → each act ───────────────────────────────────────────────────────────────────────────

async def _approval(account: str, it: dict, said: str) -> Optional[str]:
    from agapi import agapi_route as AR, venue_submit as VS
    with AR.using(await AR.target_for(FAMILY, account)):   # the read-back is the group family's target (pinned: the sandbox) — its approval goes there too
        if VS.TAP.get() is not None:
            r = await VS.in_app_tap(account, it["read_back_id"], it["sha"])
            return r.get("approval_id") if r.get("ok") else None
        if VS.WA.get() is not None:
            r = await VS.whatsapp_tap(account, it["read_back_id"], it["sha"])
            return r.get("approval_id") if r.get("ok") else None
    r = await _call(account, "sandbox.simulate_approval", {"read_back_id": it["read_back_id"], "said": (said or "Yes, go ahead.")[:200]})
    return ((r.get("result") or {}).get("approval_id")) if r.get("ok") else None


SETTLE = None   # tests replace it: (account, item_id, state, reference) → None


async def _settle(account: str, trip_id: Optional[str], state: str, parts: List[dict]) -> None:
    """The worker's ONE trip follows AgAPI's record: its rows booked (with their references) or cancelled — the master list reads them."""
    if not trip_id:
        return
    from . import groups as G
    from . import basket as BK
    every = await G._items(account, trip_id)
    rows = [r for r in every if r.get("state") in ("suggested", "chosen", "booked")
            and not BK.superseded(r)]   # Sasha 339 · the CURRENT plan's rows only: a re-plan's superseded rows are not the booking
    if state == "booked":   # a superseded row holding the slice's booking (an earlier settle's) gives it back first — one booked row per slice
        for r in every:
            if BK.superseded(r) and r.get("state") in ("chosen", "pending_payment", "booked"):
                if SETTLE is not None:
                    await SETTLE(account, r["id"], "suggested", None)
                else:
                    await BK._settle(account, r["id"], "suggested")
    refs = {"flight": [p.get("reference") for p in parts if p.get("kind") == "flight"], "stay": [p.get("reference") for p in parts if p.get("kind") == "stay"]}
    for r in rows:
        kind = "flight" if r.get("kind") == "flight" else "stay"
        ref = refs[kind].pop(0) if refs[kind] else None
        if SETTLE is not None:
            await SETTLE(account, r["id"], state, ref)
            continue
        from . import basket as BK
        await BK._settle(account, r["id"], state, booking_reference=ref)


async def confirm(account: str, card_id: str, choice: str, said: str = "",
                  progress: Optional[Callable[[int, int], None]] = None) -> Dict[str, Any]:
    from . import groups as G
    from . import keep_resolver as KR
    c = _CARDS.get(card_id)
    if not c or c["account"] != account or time.time() - c["at"] > CARD_S:
        return {"status": "nothing_waiting", "say": "That card's already answered."}
    _CARDS.pop(card_id, None)   # once: a second tap finds nothing (and card_tap's durable claim holds it across restarts)
    if choice not in ("group_yes", "yes"):
        return {"status": "kept", "say": "Kept — nothing changed."}
    st = G.store()
    mv = await st.movement(account)
    members = {m["id"]: m for m in await st.members(mv["id"])}
    done, failed, reasked, sem, n = [], [], [], asyncio.Semaphore(ACT_PARALLEL), [0]   # Sasha 339 · each act (bounded: one at a time), counted
    if progress:
        progress(0, len(c["items"]))

    async def act(it: dict) -> None:
        async with sem:
            try:
                await _act_one(account, it, said, mv, members, done, failed, reasked)
            except Exception as e:   # one worker's failure is that worker's, said
                log.warning("[group_book] %s not done: %s", it["name"], type(e).__name__)
                failed.append({"name": it["name"], "why": "couldn't be completed just now — nothing was changed for them"})
        n[0] += 1
        if progress:
            progress(n[0], len(c["items"]))
    await asyncio.gather(*(act(it) for it in c["items"]))
    try:   # Sasha 339 (Tyler) · the trips follow AgAPI's ONE record after every yes
        await reconcile(account, list(members.values()))
    except Exception as e:
        log.warning("[group_book] reconcile after the yes: %s", type(e).__name__)
    order = {it["name"]: i for i, it in enumerate(c["items"])}
    done.sort(key=lambda d: order.get(d["name"], 0))
    failed.sort(key=lambda d: order.get(d["name"], 0))
    verb = {"book": "booked", "swap": "swapped", "cancel": "cancelled"}[c["action"]]
    cards = [_card_for(account, c["action"], x) for x in reasked]   # Sasha 340 · each moved fare: its OWN card, its own Yes
    say = (f"Done — {len(done)} {verb} (TEST)." if done else "Nothing was done.") + \
        (" Not done: " + "; ".join(f"{f['name']} ({f['why']})" for f in failed) + "." if failed else "") + \
        (f" The fare moved for {', '.join(x['name'] for x in reasked)} — {'a new card' if len(reasked) == 1 else 'new cards'} below, "
         f"{'its' if len(reasked) == 1 else 'each with its'} own Yes; nothing was booked for {'them' if len(reasked) > 1 else 'them'} yet." if reasked else "") + \
        " The master list shows it now."
    return {"status": "done", "done": done, "failed": failed, "reasked": cards, "say": say}


def waiting_cards(account: str) -> List[Dict[str, Any]]:
    """Sasha 340 · the moved-fare cards still waiting for THIS organiser's yes (the ONE card store, in time) — a reload never loses one."""
    out = []
    for cid, c in list(_CARDS.items()):
        it = (c.get("items") or [{}])[0]
        if c["account"] == account and len(c.get("items") or []) == 1 and it.get("moved") and time.time() - c["at"] <= CARD_S:
            out.append({"status": "awaiting_yes", "action": c["action"], "read_back": list(it.get("lines") or []), "read_back_id": cid,
                        "name": it["name"], "ask": f"Book {it['name']} at the new fare? Everything is on the card (TEST — nothing is charged now).",
                        "verb": "Book"})
    return out


def _card_for(account: str, action: str, it: dict) -> Dict[str, Any]:
    """ONE worker's own card (a moved fare, re-asked alone): the SAME card store, the same Yes / No (yes_buttons in the route)."""
    cid = "grp_" + secrets.token_hex(10)
    _CARDS[cid] = {"account": account, "action": action, "items": [it], "at": time.time()}
    lines = list(it.get("lines") or []) + ([f"⚠ {it['name']} is OVER the group's limit ({it.get('over_words')}) — included only because you asked."]
                                           if it.get("over") and it.get("over_words") else [])
    return {"status": "awaiting_yes", "action": action, "read_back": lines, "read_back_id": cid, "name": it["name"],
            "ask": f"Book {it['name']} at the new fare? Everything is on the card (TEST — nothing is charged now).", "verb": "Book"}


async def _act_one(account: str, it: dict, said: str, mv: dict, members: dict, done: list, failed: list, reasked: Optional[list] = None) -> None:
    """ONE worker's act after the organiser's yes: the approval of THAT read-back, the references granted for this act only, the act,
    then the worker's ONE trip settled from AgAPI's answer."""
    from . import keep_resolver as KR
    apv = await _approval(account, it, said or "Yes, go ahead.")
    if not apv:
        failed.append({"name": it["name"], "why": "the yes wasn't accepted for this one"})
        return
    refs = [r for r in _refs(it.get("worker") or {}) if r]
    KR.grant(it.get("owner") or it.get("member"), refs)   # THIS worker's references (their vault: the PERSON's, Sasha 351), for THIS act only
    try:
        r = await _call(account, it["op"], it["body"], approval=apv)
    finally:
        KR.revoke(refs)
    e = r.get("error") or {}
    d = e.get("details") or {}
    if e.get("code") == "approval_void" and d.get("void_reason") == "payload_changed" and reasked is not None:
        # Sasha 340 · CR 166: nothing was booked for THIS worker; the rest stand. A fresh read-back → their own card, their own Yes;
        # an offer gone (no read-back) → this worker prepared again (re-planned once), then their own card — or held, said.
        if d.get("read_back_id"):
            reasked.append({**it, "read_back_id": d["read_back_id"], "sha": d.get("read_back_sha256") or "",
                            "lines": list((d.get("read_back") or {}).get("lines") or []), "moved": True})
            return
        if it["op"] == "group.book":
            m = members.get(it["member"])
            org = (it.get("body") or {}).get("end_user")
            kind, x = await _prepare_worker(account, m, None, [m["name"]], bool(it.get("over")), org, mv) if m and org else ("skip", {"why": "not on the list"})
            if kind == "item":
                reasked.append({**x, "moved": True})
            else:
                failed.append({"name": it["name"], "why": x.get("why") or "the fare is gone and none was found again"})
            return
    if not r.get("ok"):
        failed.append({"name": it["name"], "why": e.get("message") or "AgAPI refused"})
        return
    res = r.get("result") or {}
    parts = res.get("parts") or []
    note = None
    try:   # AgAPI has DONE it: the trip follows — and if the trip can't, the act still happened and is said as done
        if it["op"] == "group.book":
            await _settle(account, members[it["member"]].get("trip_id"), "booked", parts)
        elif it["op"] == "group.cancel":
            await _settle(account, members[it["member"]].get("trip_id"), "cancelled", [])
        else:   # a swap: the one who leaves — cancelled; the one who comes — their trip, booked with the new references
            await _settle(account, members[it["from_member"]].get("trip_id"), "cancelled", [])
            await _swap_in(account, mv, members[it["member"]], parts)
    except Exception as e:   # Sasha 339 · never "nothing was changed" for an act AgAPI made
        log.error("[group_book] %s: done at AgAPI, the trip not updated: %s", it["name"], type(e).__name__)
        note = "done at AgAPI — the master list couldn't be updated; the invoice has it"
    done.append({"name": it["name"], "state": res.get("state"), "parts": [p.get("reference") for p in parts], **({"note": note} if note else {}),
                 **({"refund": res["refund"]} if res.get("refund") else {}), **({"difference": res["difference"]} if res.get("difference") else {})})


async def answer(account: str, card_id: str, choice: str, said: str = "", wait_s: float = 0.0) -> Dict[str, Any]:
    """Sasha 339 · THE one entry for a tap on a group card (the /group page, S2, WhatsApp): a card of one act is answered at once; a card of
    several runs as the account's ONE background job ("Booking 16… 9 done"), followed by /group/job — never one 120 s request."""
    c = _CARDS.get(card_id)
    if not c or choice not in ("group_yes", "yes") or len(c.get("items") or []) <= 1:
        return await confirm(account, card_id, choice, said)
    j = {"id": "job_" + secrets.token_hex(8), "kind": "confirm", "state": "preparing", "total": len(c["items"]), "ready": 0, "at": time.time(), "result": None}
    _JOBS[account] = j

    def prog(k: int, total: int) -> None:
        j.update(ready=k, total=total)

    async def run() -> None:
        try:
            j["result"] = await confirm(account, card_id, choice, said, progress=prog)
            j["state"] = "ready"
        except Exception as e:
            log.error("[group_book] the booking job failed: %s", type(e).__name__)
            j.update(state="failed", why="The bookings couldn't be completed — the master list shows what was done.")
    j["task"] = asyncio.create_task(run())
    await asyncio.sleep(0)
    v = await wait(account, wait_s) if wait_s else job_view(account)
    return v["result"] if v.get("state") == "ready" else {"status": "booking", **v}


async def _swap_in(account: str, mv: dict, m: dict, parts: List[dict]) -> None:
    """The worker who comes in: their ONE trip gets the booked parts (references; prices from AgAPI's record), so the list shows them."""
    from . import groups as G, basket as BK
    tid = await G.store().trip_of(account, m, f"{mv['company']} — {m['name']} to {mv['destination']}")
    # Sasha 339 · a newcomer who was planned (their own flights, as the swap now sends them): their plan's rows ARE the booking — settled
    # with the references, never a second set of rows beside them (the proof's master list showed both)
    if any(r.get("kind") == "flight" and r.get("state") in ("suggested", "chosen") and not BK.superseded(r) for r in await G._items(account, tid)):
        await _settle(account, tid, "booked", parts)
        return
    for p in parts:
        price = (p.get("price") or {})
        row = {"provider": "agapi_group", "provider_ref": p.get("reference"), "day": str(m.get("out_date") or "")[:10] or None, "party": 1,
               "price_amount": (price.get("amount_minor") or 0) / 100 if price else None, "price_currency": price.get("currency") or "EUR",
               "price_source": "quoted", "snapshot": {"from_swap": True, "reference": p.get("reference")}}
        await BK.suggest(account, tid, "flight" if p.get("kind") == "flight" else "stay", [row], slice_key=f"swap {p.get('reference')}", replace=False)
    await _settle(account, tid, "booked", parts)


# ── ONE invoice per movement, from AgAPI's records ──────────────────────────────────────────────────────────────────────────

REAV = ("Travel services arranged by Kanoe. Spanish travel-agency register (REAV) number: to be added before invoices go live. "
        "Package-travel rights under Spain's Real Decreto Legislativo 1/2007 apply where the booking is a package.")


def _eur(minor: int) -> str:
    return f"€{minor / 100:,.2f}"


async def invoice(account: str) -> Dict[str, Any]:
    from . import groups as G
    st = G.store()
    mv = await st.movement(account)
    if not mv:
        return {"why": "there's no group movement yet"}
    members = {m["id"]: m for m in await st.members(mv["id"])}
    # Sasha 339 · THIS movement's records only: AgAPI keeps one list per organiser (every movement of theirs) — a record belongs to this
    # invoice when its worker is one of this movement's members (the proof's invoice carried the previous movement's bookings)
    recs = [b for b in await _records(account) if (b.get("worker") or {}).get("key") in members]
    lines, adj, total = [], [], 0
    for b in recs:
        m = members.get((b.get("worker") or {}).get("key")) or {}
        price = sum(((p.get("price") or {}).get("amount_minor") or 0) for p in b.get("parts") or [])
        nights = max(1, (date.fromisoformat(str(m["back_date"])[:10]) - date.fromisoformat(str(m["out_date"])[:10])).days) if m.get("out_date") and m.get("back_date") else None
        row = {"who": b["worker"]["name"], "route": f"{G.origin(m) or '?'} ⇄ {mv['destination']}", "dates": f"{m.get('out_date')} – {m.get('back_date')}",
               "hotel_nights": nights, "price": _eur(price), "references": [p.get("reference") for p in b.get("parts") or []], "state": b["state"]}
        if b["state"] == "booked":
            total += price
            lines.append(row)
        elif b["state"] == "cancelled":
            adj.append({**row, "what": "Cancelled", "refund": _eur(price)})
        elif b["state"] == "swapped_out":
            fl = sum(((p.get("price") or {}).get("amount_minor") or 0) for p in b.get("parts") or [] if p.get("kind") == "flight")
            nxt = next((x for x in recs if x["booking_id"] == b.get("replaced_by")), None)
            adj.append({**row, "what": f"Swapped for {nxt['worker']['name'] if nxt else 'another worker'} (flights cancelled and rebooked; the stay renamed)",
                        "refund": _eur(fl)})
    test = True
    return {"to": mv.get("company"), "movement": {k: mv.get(k) for k in ("destination", "starts_on", "ends_on", "hotel_area")},
            "number": f"KAN-{str(mv['id'])[:8].upper()}{'-TEST' if test else ''}", "date": date.today().isoformat(), "test": test,
            "lines": lines, "adjustments": adj, "total": _eur(total), "total_minor": total, "currency": "EUR", "reav": REAV}


__all__ = ["prepare", "confirm", "invoice", "worker_of", "REAV"]


# the invoice's own link (WhatsApp): signed, the organiser's movement only, 30 days — its own key (never a vault link's)
def _ikey() -> bytes:
    import hashlib
    import os
    k = os.getenv("SASHA_BOOKING_KEY", "").strip()
    if not k:
        raise RuntimeError("no signing secret (SASHA_BOOKING_KEY)")
    return hashlib.sha256(("sasha-group-invoice:" + k).encode()).digest()


def invoice_token(owner: str, movement_id: str, now: Optional[float] = None) -> str:
    import base64
    import hmac
    import hashlib
    import json
    body = json.dumps({"o": owner, "v": movement_id, "e": int((now or time.time()) + 30 * 86400)}, separators=(",", ":")).encode()
    b = lambda x: base64.urlsafe_b64encode(x).decode().rstrip("=")   # noqa: E731
    return b(body) + "." + b(hmac.new(_ikey(), body, hashlib.sha256).digest())


def read_invoice_token(token: str, now: Optional[float] = None) -> Optional[Dict[str, str]]:
    import base64
    import hmac
    import hashlib
    import json
    try:
        a, s = token.split(".")
        un = lambda x: base64.urlsafe_b64decode(x + "=" * (-len(x) % 4))   # noqa: E731
        body, sig = un(a), un(s)
    except Exception:
        return None
    if not hmac.compare_digest(sig, hmac.new(_ikey(), body, hashlib.sha256).digest()):
        return None
    d = json.loads(body)
    return {"owner": d["o"], "movement": d["v"]} if d.get("e", 0) >= (now or time.time()) else None


def invoice_link(owner: str, movement_id: str) -> str:
    import os
    return os.getenv("SASHA_WEB_URL", "https://project.kanoe.ai").rstrip("/") + "/invoice/" + invoice_token(owner, movement_id)
