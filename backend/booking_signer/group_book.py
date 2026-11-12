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
from kanoe_contract import ERR, OP  # Sasha 374 · THE ONE generated contract (CR 186)

import asyncio
import hashlib
import json
import os
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

#: Sasha 371b · CR 184: AgAPI's group acts are idempotent — ONE key per traveller + movement + plan, re-sent unchanged on every retry
GROUP_ACTS = (OP.GROUP_BOOK, OP.GROUP_SWAP, OP.GROUP_CANCEL)
#: the answers that mean "AgAPI didn't (yet) answer this request" — the SAME request is sent again with the SAME key, never a new one
RESEND = ("timeout", "unreachable", ERR.IDEMPOTENCY_IN_FLIGHT, ERR.UPSTREAM_RATE_LIMITED, ERR.RATE_LIMITED)   # timeout / unreachable: the transport's own (agapi_route.post)
RESEND_WAIT_S = (2.0, 5.0, 10.0, 20.0)


def plan_version(body: dict) -> str:
    """The plan this request carries (its offers, nights, worker, mandate — everything but the organiser): a new plan is a new version,
    the same plan the same one. Lowercase hex."""
    b = {k: v for k, v in (body or {}).items() if k != "end_user"}
    return hashlib.sha256(json.dumps(b, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()[:16]


def idem_key(op: str, movement_id: str, member_id: str, version: str) -> str:
    """CR 184 (row 1885) · sha256("<op>:" + movement_id + ":" + member_id + ":" + plan_version), lowercase hex (spec/ext/vectors/group.json)."""
    return hashlib.sha256(f"{op}:{movement_id}:{member_id}:{version}".encode()).hexdigest()


def act_key(op: str, movement_id: str, member_id: str, body: dict) -> str:
    return idem_key(op, str(movement_id), str(member_id), plan_version(body))


async def _call(account: str, op: str, body: dict, approval: Optional[str] = None, idem: Optional[str] = None) -> Dict[str, Any]:
    if op in GROUP_ACTS and not idem:   # ⛔ Sasha 371b · a group act without its ONE key is a bug — never a random one
        raise ValueError(f"{op} needs its idempotency key (act_key)")
    if CALL is not None:
        KEYS.append((op, idem))
        import inspect
        if "idem" in inspect.signature(CALL).parameters:   # a test's AgAPI that keeps CR 184's keys
            return await CALL(op, body, approval, idem=idem)
        return await CALL(op, body, approval)
    from agapi import agapi_route as AR
    url, key = await AR.client_for(FAMILY, account)
    if not key:
        return {"ok": False, "error": {"code": "not_configured", "message": "AgAPI's sandbox key isn't set here"}}
    h = {"Authorization": f"Bearer {key}", "content-type": "application/json", "Idempotency-Key": idem or "s334_" + secrets.token_hex(12),
         **({"AgAPI-Approval-Id": approval} if approval else {})}
    return await AR.post(url, key, op, body, h, act_timeout() if is_act(op, body, approval) else TIMEOUT_S)


async def _send(account: str, op: str, body: dict, idem: str, approval: Optional[str] = None) -> Dict[str, Any]:
    """Sasha 371b · THE ONE WAY a group act is sent: no answer (a dropped connection, a timeout, AgAPI still working on it, busy) → the SAME
    request with the SAME key, after the time AgAPI gives (or a short wait), a few times — AgAPI then answers with its ONE record. Still no
    answer → returned as it is; the record (group.bookings by movement) says what happened."""
    r: Dict[str, Any] = {}
    for wait in (0.0,) + RESEND_WAIT_S:
        if wait:
            await SLEEP(wait)
        r = await _call(account, op, body, approval=approval, idem=idem)
        e = r.get("error") or {}
        if r.get("ok") or e.get("code") not in RESEND:
            return r
        given = e.get("retry_after_s") or (e.get("details") or {}).get("retry_after_s")
        if given:
            await SLEEP(min(float(given), 20.0))
    return r


#: Sasha 371b · CR 184's answers that NAME the traveller's record on this movement (details {booking_id, state, movement_id}): states, never "failed"
ON_RECORD = (ERR.ALREADY_COMPLETED, ERR.OUTCOME_UNKNOWN)
NO_ANSWER = ("timeout", "unreachable", ERR.IDEMPOTENCY_IN_FLIGHT)   # still no answer after _send's re-sends: AgAPI may have ordered — its record decides, read by movement


def recorded(e: Dict[str, Any]) -> Dict[str, Any]:
    """An answer that names (or may name) the record → {state, status, booking_id?, why} in plain words — never "not booked"."""
    d = (e or {}).get("details") or {}
    state = d.get("state") or ("unknown" if (e or {}).get("code") in (ERR.OUTCOME_UNKNOWN,) + NO_ANSWER else "booked")
    status = RECORD_STATUS.get(state, "confirming")
    why = {"booked": "already booked on this trip — nothing new was ordered",
           "confirming": "the airline hasn't confirmed yet — I'm checking; nothing will be ordered twice",
           "incomplete": "part of their trip is booked and the rest isn't — it's on the master list",
           "cancelled": "their booking on this trip was cancelled"}.get(status, "on the master list")
    return {"state": state, "status": status, "code": (e or {}).get("code"), "why": why, **({"booking_id": d["booking_id"]} if d.get("booking_id") else {})}


CALL = None   # tests replace it: (op, body, approval) → envelope
KEYS: List[Tuple[str, Optional[str]]] = []   # tests read it: every (op, Idempotency-Key) sent through CALL
TIMEOUT_S = 60.0


def is_act(op: str, body: dict, approval: Optional[str]) -> bool:
    """The call that ORDERS: an approved group act, or a group.book under the manager's mandate (that call IS the act — CR 182)."""
    return op in GROUP_ACTS and bool(approval or (body or {}).get("mandate_id"))


def act_timeout() -> float:
    """How long Sasha waits for AgAPI's answer to an approved act before the connection is dropped and the SAME request re-sent (_send).
    The transport's own setting (SASHA_GROUP_ACT_TIMEOUT_S, default 60 s) — a drill sets it short to drop mid-order on the real path."""
    try:
        return max(1.0, float(os.getenv("SASHA_GROUP_ACT_TIMEOUT_S", "") or TIMEOUT_S))
    except ValueError:
        return TIMEOUT_S


async def _organiser(account: str) -> Optional[str]:
    r = await _call(account, OP.USERS_REGISTER, {"external_ref": f"sasha:{account}"})
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
        r = await _call(account, OP.TRAVEL_FIND_FLIGHTS, q)
        if not r.get("ok") and (r.get("error") or {}).get("code") in (ERR.UPSTREAM_FAILED, ERR.UPSTREAM_RATE_LIMITED):   # Sasha 339 · once more
            await SLEEP(5)
            r = await _call(account, OP.TRAVEL_FIND_FLIGHTS, q)
        offers = (r.get("result") or {}).get("offers") or [] if r.get("ok") else []
        if not offers:
            return None, f"no flight {frm} → {to} on {str(day)[:10]} on AgAPI's sandbox" + (f" ({(r.get('error') or {}).get('code')})" if not r.get("ok") else "")
        was = planned["flight"].get(str(day)[:10])
        items.append({"kind": "flight", "ref": offers[0]["offer_ref"], **({"planned_price": was} if was else {}),
                      **({"_price": offers[0]["price"]} if isinstance(offers[0].get("price"), dict) else {})})   # Sasha 339 · AgAPI's own price
    nights = max(1, (date.fromisoformat(str(m["back_date"])[:10]) - date.fromisoformat(str(m["out_date"])[:10])).days)
    # Sasha 365 · their room at the GROUP's hotel — the plan's ONE search (groups.group_hotel), never a search per person
    h = (mv.get("rules") or {}).get("hotel") or await G.group_hotel(account, mv, await G.store().members(mv["id"]))
    if not h or not h.get("ref"):
        return None, "no hotel found for the group on AgAPI's sandbox"
    items.append({"kind": "stay", "ref": h["ref"], "at": f"{str(m['out_date'])[:10]}T15:00:00", "nights": nights,
                  **({"planned_price": planned["stay"]} if planned["stay"] else {}),
                  **({"_per_night": {"amount_minor": round(float(h["eur_per_night"]) * 100), "currency": "EUR"}} if h.get("eur_per_night") is not None else {}),
                  "_name": h.get("name") or "the hotel"})
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
    return e.get("code") == ERR.UPSTREAM_REFUSED and (d.get("reason") == "offer_gone" or
                                                    d.get("duffel_code") in ("offer_no_longer_available", "offer_expired", "not_found"))


async def _read_back(account: str, op: str, body: dict, idem: str) -> Dict[str, Any]:
    """AgAPI's read-back for one act (Sasha 371b: the same key as the act it reads back — and the act, under a mandate), through _send."""
    return await _send(account, op, body, idem)


class Unread(Exception):
    """Sasha 376 · AgAPI's record couldn't be read: said as that — never as nothing booked, never as €0.00."""


async def _records(account: str, movement_id: str) -> List[dict]:
    """Sasha 371b · AgAPI's ONE record for THIS movement (CR 184: group.bookings {end_user, movement_id}) — never the organiser's every trip.
    Sasha 376 · no answer → the SAME read again (as an act's, _send); still unread → Unread, never an empty list."""
    if not movement_id:
        raise ValueError("group.bookings is read by movement")
    org = await _organiser(account)
    if not org:
        raise Unread("the organiser isn't known to AgAPI just now")
    r = await _send(account, OP.GROUP_BOOKINGS, {"end_user": org, "movement_id": str(movement_id)}, "s376_read_" + secrets.token_hex(12))
    if not r.get("ok"):
        raise Unread((r.get("error") or {}).get("code") or "unread")
    return (r.get("result") or {}).get("bookings") or []


LIVE = ("booked", "unknown", "incomplete")   # CR 184 · a record that holds (or may hold) an order — at most ONE per traveller per movement


def record_of(records: List[dict], member_id: str) -> Optional[dict]:
    """The traveller's record on THIS movement: the live one (CR 184 holds at most one), else the last settled one (cancelled / swapped out)."""
    mine = [b for b in records if (b.get("worker") or {}).get("key") == member_id]
    return next((b for b in mine if b.get("state") in LIVE and (b.get("state") != "incomplete" or b.get("parts"))), None) or (mine[-1] if mine else None)


def _live_record(records: List[dict], member_id: str) -> Optional[dict]:
    b = record_of(records, member_id)
    return b if b and b.get("state") == "booked" else None


def contact_of(m: Dict[str, Any]) -> Dict[str, str]:
    """Sasha 367 · the traveller's OWN contact, from the roster (CR 181): a mobile a supplier accepts (E.164) and their email — never one
    made up; missing → AgAPI's mobile_needed / email_needed, asked as the missing fact."""
    from .contacts import supplier_mobile
    out = {}
    ph = supplier_mobile(str(m.get("phone") or "")) if m.get("phone") else None
    if ph:
        out["phone"] = ph
    if m.get("email"):
        out["email"] = str(m["email"]).strip()
    return out


async def _prepare_worker(account: str, m: dict, st_: Optional[str], who: Optional[List[str]], over_ok: bool, org: str, mv: dict,
                          mandate_id: Optional[str] = None) -> Tuple[str, dict]:
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
        body = {"end_user": org, "movement_id": str(mv["id"]), "worker": {**w, **contact_of(m)}, "items": _wire(its),
                **({"mandate_id": mandate_id} if mandate_id else {})}   # Sasha 371b · CR 184: the movement on the record; worker.key = member id
        idem = act_key(OP.GROUP_BOOK, mv["id"], m["id"], body)   # the read-back, the act and every retry of it: ONE key
        # Sasha 378 · CR 189: the references open ONLY through AgAPI's signed call, bound to THIS movement and member and checked against
        # Sasha's own records (keep_resolver.resolve) — no allow-list of Sasha's own
        r = await _read_back(account, OP.GROUP_BOOK, body, idem)
        e = r.get("error") or {}
        if mandate_id and r.get("ok"):   # Sasha 367 · INSIDE the mandate: booked on the manager's instruction (no read-back to answer)
            return "booked", {"name": m["name"], "member_id": m["id"], "result": r.get("result") or {}}
        if e.get("code") in ON_RECORD or (mandate_id and e.get("code") in NO_ANSWER):   # Sasha 371b · AgAPI's record holds it: a STATE, never "failed"
            return "recorded", {"name": m["name"], "member_id": m["id"], **recorded(e)}
        if mandate_id and e.get("code") in (ERR.MOBILE_NEEDED, ERR.EMAIL_NEEDED, ERR.APPROVAL_EXPIRED, ERR.NOT_FOUND, "incomplete", "passport_detail_needed"):
            d = e.get("details") or {}
            return "skip", {"name": m["name"], "member_id": m["id"], "kind": e["code"], "code": e["code"],
                            **({"left_booked": d.get("left_booked")} if d.get("left_booked") else {})}
        if e.get("code") == ERR.APPROVAL_REQUIRED:
            d = e.get("details") or {}
            # Sasha 340 · the limit against the read-back's OWN prices (details.priced, CR 166); AgAPI without them: its offer prices
            over = over_priced(d["priced"], lim, its) if d.get("priced") else over_at_booking(its, lim)
            outside = [x.get("why") for x in ((d.get("mandate") or {}).get("outside") or []) if x.get("why")]
            if mandate_id and outside and not asked:   # Sasha 367 · OUTSIDE the mandate: asked with AgAPI's reasons (the explicit tap)
                return "outside", {"op": OP.GROUP_BOOK, "member": m["id"], "owner": owner_of(m), "name": m["name"], "worker": w, "body": body, "idem": idem,
                                   "outside": outside, "read_back_id": d["read_back_id"], "sha": d.get("read_back_sha256") or "",
                                   "lines": list((d.get("read_back") or {}).get("lines") or [])}
            if over and not asked:
                return "skip", {"name": m["name"], "member_id": m["id"], "kind": "over_at_booking", "why": over}
            return "item", {"op": OP.GROUP_BOOK, "member": m["id"], "owner": owner_of(m), "name": m["name"], "worker": w, "body": body, "idem": idem,
                            **({"outside": outside} if outside else {}),   # Sasha 376 · AgAPI's reasons ride on the card's item
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
        return "skip", {"name": m["name"], "member_id": m["id"], "kind": "not_found", **decision(e)}   # Sasha 364 · plain words
    return "skip", {"name": m["name"], "member_id": m["id"], "kind": "no_fare", "why": "no fare left — nothing held"}


async def _agapi_reachable(account: str) -> bool:
    """A key for the group family's target exists (or a test's AgAPI) — else no record can be read, and nothing is settled from it."""
    if CALL is not None:
        return True
    import os
    from agapi import agapi_route as AR
    return bool(os.getenv(AR.key_name(await AR.target_for(FAMILY, account)), "").strip())


def record_booked(records: List[dict], members: List[dict]) -> Dict[str, Dict[str, Any]]:
    """Sasha 340 · what a booked worker's master-list row shows, FROM AgAPI's record: the price booked (its parts) and its references."""
    out = {}
    for m in members:
        b = record_of(records, m["id"])
        if b and b.get("state") == "booked":
            parts = b.get("parts") or []
            out[m["id"]] = {"price_eur": round(sum(((p.get("price") or {}).get("amount_minor") or 0) for p in parts) / 100, 2),
                            "references": [p.get("reference") for p in parts if p.get("reference")]}
    return out


#: Sasha 371b · AgAPI's record state → the master list's status (CR 184: booked | incomplete | unknown | cancelled | swapped_out)
RECORD_STATUS = {"booked": "booked", "cancelled": "cancelled", "swapped_out": "cancelled", "unknown": "confirming", "incomplete": "incomplete"}


def record_states(records: List[dict], members: List[dict]) -> Dict[str, str]:
    """Sasha 339 (Tyler) · each worker's state AS AgAPI'S ONE RECORD SAYS — absent when AgAPI has no record of them on this movement.
    Sasha 371b · "unknown" (an order may exist) is "confirming" and "incomplete" is "incomplete": NEITHER is ever "not booked"."""
    out = {}
    for m in members:
        b = record_of(records, m["id"])
        if b and b.get("state") in RECORD_STATUS:
            out[m["id"]] = RECORD_STATUS[b["state"]]
    return out


HELD = ("booked", "confirming", "incomplete")   # the master list's statuses AgAPI's record holds an order (or a maybe) for


async def booked_line(account: str, movement_id: Optional[str]) -> str:
    """Sasha 371b · what is booked, said ONLY from AgAPI's record for THIS movement (the master list's status) — never assumed."""
    from . import groups as G
    if not movement_id:
        return "Nothing is booked yet."
    rows = (await G.view(account, movement_id)).get("rows") or []
    n = sum(1 for r in rows if r.get("status") == "booked")
    return "Nothing is booked yet." if not n else f"{n} of {len(rows)} {'is' if n == 1 else 'are'} already booked."


async def unbooked(account: str, movement_id: str) -> List[str]:
    """The members AgAPI's record holds NO order for on this movement — the only ones a plan may change."""
    from . import groups as G
    return [r["member_id"] for r in (await G.view(account, movement_id)).get("rows") or [] if r.get("status") not in HELD]


def record_whys(records: List[dict], members: List[dict]) -> Dict[str, str]:
    """Sasha 371b · AgAPI's own "why" on a record that isn't booked (CR 184) — said, never a guess."""
    out = {}
    for m in members:
        b = record_of(records, m["id"])
        if b and b.get("why") and b.get("state") in ("unknown", "incomplete"):
            out[m["id"]] = str(b["why"])
    return out


async def reconcile(account: str, movement_id: str, members: List[dict], records: Optional[List[dict]] = None, booked: Optional[dict] = None,
                    whys: Optional[dict] = None) -> Dict[str, str]:
    """Sasha 339 (Tyler) · THE ONE BOOKING RECORD DECIDES: each worker's trip follows AgAPI's group.bookings — their latest record booked →
    their current plan's rows booked (with its references); cancelled / swapped out → cancelled. Run on every master-list read and once
    after every yes, so a trip row and AgAPI's record can never disagree for longer than one read. → rows changed."""
    from . import groups as G, basket as BK
    if records is None:
        if not await _agapi_reachable(account):
            return {}
        records = await _records(account, movement_id)
    for m in members:
        b = record_of(records, m["id"])
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
    if whys is not None:
        whys.update(record_whys(records, members))
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
                  progress: Optional[Callable[[int, int], None]] = None, held: Optional[List[dict]] = None,
                  movement_id: Optional[str] = None) -> Dict[str, Any]:
    """→ {status: awaiting_yes, read_back, read_back_id (the card), ask, skipped} or {status: nothing, say}. The organiser's trip (the one
    they have open, or `movement_id`) is chosen HERE, once; the card carries its id to the act (Sasha 371b)."""
    from . import groups as G
    st = G.store()
    mv = await st.movement(account, movement_id)
    if not mv:
        return {"status": "nothing", "say": "There's no group movement yet."}
    members = await st.members(mv["id"])
    org = await _organiser(account)
    if not org:
        return {"status": "nothing", "say": "AgAPI's sandbox didn't answer — nothing was prepared."}
    view = {r["member_id"]: r for r in (await G.view(account, mv["id"]))["rows"]}
    items, skipped, lines = [], [], []
    records = await _records(account, mv["id"])   # Sasha 371b · AgAPI's ONE booking record for THIS movement
    if action == "book" and not (mv.get("rules") or {}).get("hotel"):   # Sasha 365 · the group's ONE hotel search, before the workers
        await G.group_hotel(account, mv, members)
    if action == "book":   # Sasha 339 · each worker in parallel (bounded), progress counted — the card in member order
        pick = G.pick(members, who)[0]   # Sasha 376 · the one person resolver
        todo = [(m, view.get(m["id"], {}).get("status")) for m in pick
                if (record_of(records, m["id"]) or {}).get("state") not in LIVE]   # Sasha 371b · AgAPI's record: anyone it holds an order for is not asked again
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
        a, b = ((G.pick(members, [(who or [""])[0]])[0] or [None])[0], (G.pick(members, [swap_to])[0] or [None])[0] if swap_to else None)
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
        sb = {"end_user": org, "booking_id": rec["booking_id"], "worker": w, "flights": _wire(own)}   # CR 164 · HIS own flights
        items.append({"op": OP.GROUP_SWAP, "member": b["id"], "owner": owner_of(b), "from_member": a["id"], "name": f"{a['name']} → {b['name']}", "worker": w,
                      "over": bool(over), "over_words": over, "body": sb, "idem": act_key(OP.GROUP_SWAP, mv["id"], b["id"], sb)})
    elif action == "cancel":
        for nm in who or []:
            m = (G.pick(members, [nm])[0] or [None])[0]   # Sasha 376 · the one person resolver
            rec = _live_record(records, m["id"]) if m else None
            if not rec:
                skipped.append({"name": nm, "why": "no booking to cancel"})
                continue
            cb = {"end_user": org, "booking_id": rec["booking_id"]}
            items.append({"op": OP.GROUP_CANCEL, "member": m["id"], "name": m["name"], "body": cb, "idem": act_key(OP.GROUP_CANCEL, mv["id"], m["id"], cb)})
    for it in items:   # AgAPI's read-back for each (nothing is done without the approval)
        if it.get("read_back_id"):   # Sasha 339 · a book item brings its own (prepared in parallel)
            lines += it["lines"] + ([f"⚠ {it['name']} is OVER the group's limit ({it.get('over_words') or 'by the plan'}) — included only because you asked."]
                                    if it.get("over") else []) + (["(Re-planned: the first fare was gone.)"] if it.get("replanned") else []) + [""]
            continue
        r = await _read_back(account, it["op"], it["body"], it["idem"])
        e = r.get("error") or {}
        if e.get("code") != ERR.APPROVAL_REQUIRED:
            skipped.append({"name": it["name"], **decision(e)})   # Sasha 364 · a named decision, never the raw message
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
    _CARDS[cid] = {"account": account, "action": action, "items": items, "at": time.time(), "movement_id": str(mv["id"])}
    n = len(items)
    verb = {"book": "Book", "swap": "Swap", "cancel": "Cancel"}[action]
    ask = {"book": f"Book {'these ' + str(n) if n > 1 else items[0]['name']}? Everything is on the card (TEST — nothing is charged now).",
           "swap": f"Swap {items[0]['name']}? The difference is on the card (TEST).",
           "cancel": f"Cancel {', '.join(i['name'] for i in items)}? The refund is on the card (TEST)."}[action]
    return {"status": "awaiting_yes", "action": action, "read_back": [l for l in lines if l is not None][:400], "read_back_id": cid, "ask": ask,
            "verb": verb, "skipped": skipped, "taps": taps, "how": "Say `ask` word for word — nothing happens until they say yes."}


async def book_under_mandate(account: str, mandate_id: str, names: List[str], movement_id: str, over_ok: bool = False,
                             progress: Optional[Callable[[int, int], None]] = None) -> Dict[str, Any]:
    """Sasha 367 · every worker booked under the manager's ONE mandate (CR 182): inside → booked (the trip settled from AgAPI's answer);
    outside → ONE card of AgAPI's read-backs with their reasons (the explicit tap: Yes, book them); the rest named (missing contact,
    expired). → {done, outside, asks, card}."""
    from . import groups as G
    st = G.store()
    mv = await st.movement(account, movement_id)   # Sasha 371b · the mandate's OWN movement, never "the open trip"
    members = G.pick(await st.members(mv["id"]), names)[0]   # Sasha 376 · the one person resolver
    org = await _organiser(account)
    if not org:
        return {"done": [], "outside": [], "asks": [{"name": m["name"], "code": "upstream_unreachable"} for m in members], "card": None}
    if not (mv.get("rules") or {}).get("hotel"):
        await G.group_hotel(account, mv, await st.members(mv["id"]))
        mv = await st.movement(account, movement_id)
    view = {r["member_id"]: r for r in (await G.view(account, movement_id))["rows"]}
    sem, n = asyncio.Semaphore(BOOK_PARALLEL), [0]
    done, outside, asks = [], [], []
    if progress:
        progress(0, len(members))

    async def one(m: dict) -> None:
        async with sem:
            for attempt in (1, 2):   # Sasha 365 · an airline's refusal: once more with a fresh fare, inside the same mandate, then named
                try:
                    kind, x = await _prepare_worker(account, m, view.get(m["id"], {}).get("status"), [m["name"]] if over_ok else None, over_ok,
                                                    org, mv, mandate_id=mandate_id)
                except Exception as ex:
                    log.warning("[group_book] %s not booked: %s", m["name"], type(ex).__name__)
                    kind, x = "skip", {"name": m["name"], "code": "upstream_failed"}
                if not (kind == "skip" and x.get("code") in RETRY_ONCE):
                    break
                if attempt == 2:
                    x = {**x, "code": "refused_twice"}   # x keeps the airline's own reason (airline_code / _field / _title)
            if kind == "booked":
                res = x["result"]
                try:
                    await _settle(account, m.get("trip_id"), "booked", res.get("parts") or [])
                except Exception as ex:
                    log.error("[group_book] %s: booked at AgAPI, the trip not updated: %s", m["name"], type(ex).__name__)
                done.append({"name": m["name"], "state": res.get("state"), "parts": [p.get("reference") for p in res.get("parts") or []],
                             "conditions": [{"kind": p.get("kind"), **(p.get("conditions") or {}), **({"cancel_by": p["cancel_by"]} if p.get("cancel_by") else {})}
                                            for p in res.get("parts") or [] if p.get("conditions") or p.get("cancel_by")]})
            elif kind in ("outside", "item"):   # Sasha 376 · a read-back waiting for the explicit tap — ON the card, never dropped
                outside.append(x)
            elif kind == "recorded":   # Sasha 371b · AgAPI's record holds them (booked / confirming / incomplete): a state, said from the record
                done.append({"name": m["name"], "state": x["state"], "parts": []})
            else:
                asks.append(x)
        n[0] += 1
        if progress:
            progress(n[0], len(members))
    await asyncio.gather(*(one(m) for m in members))
    try:
        await reconcile(account, mv["id"], await st.members(mv["id"]))
    except Exception as e:
        log.warning("[group_book] reconcile after the mandate: %s", type(e).__name__)
    card = None
    if outside:   # ONE card, the explicit tap (card_tap → confirm → each read-back's own approval)
        cid = "grp_" + secrets.token_hex(10)
        _CARDS[cid] = {"account": account, "action": "book", "items": outside, "at": time.time(), "movement_id": str(mv["id"])}
        lines = [l for it in outside for l in it["lines"] + [""]]
        card = {"read_back_id": cid, "read_back": lines[:400], "ask": f"Book {'these ' + str(len(outside)) if len(outside) > 1 else outside[0]['name']} anyway?",
                "choices": [dict(c) for c in __import__("app.agent.voice", fromlist=["x"]).GROUP_CHOICES["book"]]}
    return {"done": done, "outside": outside, "asks": asks, "card": card}


# ── Sasha 339 · BOOK ALL is ONE background job: the ONE prepare, its progress, its result — the page follows it ──────────────

JOB_S = 900
CHAT_WAIT_S = 60.0   # the chat waits this long for the card (a turn's deadline is 100 s); else /group shows it
_JOBS: Dict[str, Dict[str, Any]] = {}   # account → its one book job (this worker's memory, R3: one worker)


def job_view(account: str) -> Dict[str, Any]:
    j = _JOBS.get(account)
    if not j or time.time() - j["at"] > JOB_S:
        return {"state": "none"}
    out = {"job": j["id"], "state": j["state"], "total": j["total"], "ready": j["ready"]}
    if j["state"] == "preparing" and j.get("kind") == "mandate":   # Sasha 365 · the instruction's job: its live line, from the record
        out["say"] = j.get("line") or "Starting…"
    elif j["state"] == "preparing":
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
    r = await _call(account, OP.SANDBOX_SIMULATE_APPROVAL, {"read_back_id": it["read_back_id"], "said": (said or "Yes, go ahead.")[:200]})
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
                  progress: Optional[Callable[[int, int], None]] = None, ask_once: bool = False,
                  also: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    from . import groups as G
    from . import keep_resolver as KR
    c = _CARDS.get(card_id)
    if not c or c["account"] != account or time.time() - c["at"] > CARD_S:
        return {"status": "nothing_waiting", "say": "That card's already answered."}
    _CARDS.pop(card_id, None)   # once: a second tap finds nothing (and card_tap's durable claim holds it across restarts)
    if choice not in ("group_yes", "yes"):
        return {"status": "kept", "say": "Kept — nothing changed."}
    st = G.store()
    mv = await st.movement(account, c["movement_id"])   # Sasha 371b · the card's OWN movement (set when it was prepared)
    if not mv:
        return {"status": "nothing", "say": "That trip isn't on the list any more — nothing was done."}
    members = {m["id"]: m for m in await st.members(mv["id"])}
    done, failed, reasked, sem, n = [], [], [], asyncio.Semaphore(ACT_PARALLEL), [0]   # Sasha 339 · each act (bounded: one at a time), counted
    if progress:
        progress(0, len(c["items"]))

    card_apv = await _card_approvals(account, c["items"], done, failed)   # Sasha 378 · CR 190: ONE WhatsApp yes approves the card

    async def act(it: dict) -> None:
        if card_apv is not None and it["read_back_id"] not in card_apv:   # refused by AgAPI on the card: said (or a state), never acted
            n[0] += 1
            return
        async with sem:
            try:
                await _act_one(account, it, said, mv, members, done, failed, reasked,
                               apv=card_apv.get(it["read_back_id"]) if card_apv is not None else None)
            except Exception as e:   # one worker's failure is that worker's, said
                log.warning("[group_book] %s not done: %s", it["name"], type(e).__name__)
                failed.append({"name": it["name"], "why": "couldn't be completed just now — nothing was changed for them"})
        n[0] += 1
        if progress:
            progress(n[0], len(c["items"]))
    await asyncio.gather(*(act(it) for it in c["items"]))
    try:   # Sasha 339 (Tyler) · the trips follow AgAPI's ONE record after every yes
        await reconcile(account, mv["id"], list(members.values()))
    except Exception as e:
        log.warning("[group_book] reconcile after the yes: %s", type(e).__name__)
    order = {it["name"]: i for i, it in enumerate(c["items"])}
    done.sort(key=lambda d: order.get(d["name"], 0))
    failed.sort(key=lambda d: order.get(d["name"], 0))
    verb = {"book": "booked", "swap": "swapped", "cancel": "cancelled"}[c["action"]]
    cards = [_card_for(account, c["action"], x, mv["id"]) for x in reasked]   # Sasha 340 · each moved fare: its OWN card, its own Yes
    if c["action"] == "book":   # Sasha 364 · THE FINISH, composed from the trip record: booked, references, confirmations, the invoice
        fin = await finish(account, mv["id"], done, failed + list(also or []), ask_once=ask_once)   # Sasha 365 · `also`: the mandate's held ones
        moved = (f" The fare moved for {', '.join(x['name'] for x in reasked)} — {'a new card' if len(reasked) == 1 else 'new cards'} below, "
                 f"{'its' if len(reasked) == 1 else 'each with its'} own Yes; nothing was booked for them yet.") if reasked else ""
        return {"status": "done", "done": done, "failed": failed, "reasked": cards, "say": fin["say"] + moved, "finish": fin}
    say = (f"Done — {len(done)} {verb} (TEST)." if done else "Nothing was done.") + \
        (" Not done: " + "; ".join(f"{f['name']}: {f['why']}" for f in failed) + "." if failed else "") + \
        (f" The fare moved for {', '.join(x['name'] for x in reasked)} — {'a new card' if len(reasked) == 1 else 'new cards'} below, "
         f"{'its' if len(reasked) == 1 else 'each with its'} own Yes; nothing was booked for {'them' if len(reasked) > 1 else 'them'} yet." if reasked else "") + \
        " The master list shows it now."
    return {"status": "done", "done": done, "failed": failed, "reasked": cards, "say": say}


# ── Sasha 364 · a group trip ENDS in one clear finished state, from the ONE trip record ─────────────────────────────────────────

#: AgAPI's refusal codes → the decision put to the manager, in plain words (never the supplier's nested error text)
DECISIONS = {
    "not_cancellable": "their fare can only be cancelled by the airline, not online — that's a condition of the fare, not a failure. "
                       "Shall I find a fare that can be cancelled online, or take them off this trip?",
    "price_changed": "their fare's price moved before it was booked — nothing was taken. Shall I read it back again at the new price?",
    "offer_expired": "their fare expired before it was booked — nothing was taken. Shall I find the same flight again?",
    "upstream_unreachable": "the airline didn't answer just now — nothing was taken. Shall I try them again?",
    # Sasha 371b · CR 184
    "idempotency_conflict": "their booking request changed while it was being sent — nothing new was ordered. Shall I read it back again?",
    "limits_missing": "no limit is set for them yet — what's their flight and hotel limit?",
    "another_movement": "that booking belongs to another trip — nothing was ordered on this one.",
    "over_flight_limit": "their flights are over their own flight limit. Book anyway, another option, or leave them off?",
    "over_stay_limit": "their hotel is over their own nightly limit. Book anyway, another option, or leave them off?",
}


RETRY_ONCE = (ERR.UPSTREAM_REFUSED, ERR.UPSTREAM_FAILED, ERR.UPSTREAM_UNREACHABLE)

#: Sasha 367 · AgAPI's mandate answers as facts (details.mandate.outside[].why, and the missing contact)
MANDATE_FACTS = {"worker_not_named": "not named in your instruction", "another_destination": "their flight goes somewhere else",
                 "outside_dates": "their flight is outside the trip's dates", "over_flight_limit": "their flights are over their own flight limit",
                 "over_stay_limit": "their hotel is over their own nightly limit", "over_trip_limit": "their trip is over the company's limit",
                 "currency": "the fare is in another currency", "fare_not_refundable": "their fare can't be refunded",
                 "mobile_needed": "no mobile on their profile — add it on the Group page",
                 "passport_detail_needed": "a detail an airline needs is missing from their passport (sex, date of birth or name) — their link is emailed", "email_needed": "no email on their profile — add it on the Group page",
                 "approval_expired": "your instruction had expired", "not_found": "the booking system didn't know your instruction",
                 "incomplete": "part is booked (only the airline can cancel it) and the rest was refused",
                 # Sasha 371b · CR 184's reasons, asked — never "failed"
                 "limits_missing": "no limit is set for them yet — what's their flight and hotel limit?",
                 "another_movement": "their booking would be on another trip than this instruction's",
                 "already_completed": "already booked on this trip — nothing new was ordered",
                 "outcome_unknown": "the airline hasn't confirmed yet — I'm checking; nothing will be ordered twice"}   # Sasha 365 · tried once more before anyone is asked

#: Sasha 365 · the same reasons as FACTS (no question each): the mandate puts them to the manager as ONE grouped question
FACTS = {"approval_refused": "the booking system didn't take your instruction as the yes for it (nothing was booked or charged)",
         "upstream_refused": "the airline refused the booking", "refused_twice": "the airline refused the booking, twice",
         "upstream_failed": "the airline's system failed on the booking","not_cancellable": "their fare can only be cancelled by the airline", "price_changed": "their fare's price moved",
         "offer_expired": "their fare expired", "upstream_unreachable": "the airline didn't answer", "over_limit": "over the company's limit",
         "over_at_booking": "over the company's limit at today's price", "needs_vault": "no passport in their vault yet",
         "passport": "no passport in their vault yet", "not planned": "not planned yet", "not_found": "no flight found for them"}


def one_question(asks: List[Dict[str, Any]]) -> str:
    """Sasha 365 · everything outside the limits, as ONE grouped question (after the rest is done): who, and why, in plain words."""
    if not asks:
        return ""
    def fact(a: Dict[str, Any]) -> str:
        if a.get("outside"):   # Sasha 367 · AgAPI's own reasons, each named
            return " and ".join(dict.fromkeys(MANDATE_FACTS.get(w, w.replace("_", " ")) for w in a["outside"]))   # each reason once (both legs say it)
        k = a.get("code") or a.get("kind") or ""
        said = FACTS.get(k) or MANDATE_FACTS.get(k) or a.get("fact") or "not booked just now"
        return said + (f" — the airline says: “{a['airline_title']}”" if a.get("airline_title") else "")   # Sasha 369 · its own reason
    who = "; ".join(f"{a['name']}: {fact(a)}" for a in asks)
    them = asks[0]["name"].split()[0] if len(asks) == 1 else "them"
    return f"Not booked — {who}. What would you like for {them}: book anyway, another option, or leave off this trip?"


def airline_reason(e: Dict[str, Any]) -> Dict[str, str]:
    """Sasha 369 · the AIRLINE's own reason, as CR 183 keeps it on error.details (its code, the field it names, its title) — never the
    free-text message (it can echo a passenger's value back). {} when the supplier said nothing."""
    d = (e or {}).get("details") or {}
    out = {k: str(d[k])[:120] for k in ("code", "field", "title") if d.get(k)}
    if out:
        log.warning("[group_book] the airline refused: %s [%s] %s", out.get("code"), out.get("field"), out.get("title"))
    return {"airline_" + k: v for k, v in out.items()}


def decision(e: Dict[str, Any]) -> Dict[str, Any]:
    """A refusal → {why: the decision in plain words, code} + the airline's own reason (CR 183). Unknown codes: a plain line and what can be
    done — never the raw message."""
    code = str((e or {}).get("code") or "")
    return {"why": DECISIONS.get(code) or "their booking couldn't be completed just now — nothing was taken. Shall I try again, or take "
                                          "them off this trip?", "code": code or "unknown", **airline_reason(e)}


async def _confirmations(account: str, mv: Dict[str, Any], booked_names: List[str]) -> Dict[str, List[str]]:
    """Each booked traveller's confirmation, to THEIR registered email (the roster's), through the ONE sender (live_events.send_email),
    TEST-tagged. → {sent: [names], no_email: [names], not_sent: [names]}."""
    from . import groups as G, live_events as LE
    view = await G.view(account, mv["id"])
    rows = {r["name"]: r for r in view.get("rows") or []}
    people = {p["name"]: p for p in (await G.roster(account)).get("people") or []}
    out: Dict[str, List[str]] = {"sent": [], "no_email": [], "not_sent": []}
    for name in booked_names:
        email = (people.get(name) or {}).get("email")
        if not email:
            out["no_email"].append(name)
            continue
        r = rows.get(name) or {}
        msg = {"from": os.getenv("SASHA_EMAIL_FROM", "").strip(), "to": email,
               "subject": f"Booked (TEST): {mv.get('destination')} {str(mv.get('starts_on') or '')[:10]} – {str(mv.get('ends_on') or '')[:10]}",
               "text": "\n".join([f"Hello {name.split()[0]},", "", f"You're booked for {mv.get('company')}'s trip to {mv.get('destination')} (TEST).", "",
                                  f"Travel: {r.get('transport') or '—'}", f"Hotel: {r.get('hotel') or '—'}",
                                  "References: " + (", ".join(r.get("references") or []) or "on the trip's master list"), "",
                                  "TEST: a demo booking — no airline or hotel charge.", "", "— Sasha (AI concierge, Kanoe Technologies SL)"])}
        try:
            sent = await LE.send_email(msg)
        except Exception as ex:
            sent = {"sent": False, "why": type(ex).__name__}
        out["sent" if sent.get("sent") else "not_sent"].append(name)
    return out


def _names(xs: List[str]) -> str:
    return xs[0] if len(xs) == 1 else ", ".join(xs[:-1]) + " and " + xs[-1] if xs else ""


UNREAD_SAY = ("AgAPI's booking record didn't answer just now, so I can't say yet who is booked — nothing is booked twice, and the master "
              "list will show it as soon as the record answers. Ask me again in a minute.")
INVOICE_UNREAD_SAY = "The invoice couldn't be read just now — ask me for it again in a minute."


async def finish(account: str, movement_id: str, done: List[Dict[str, Any]], failed: List[Dict[str, Any]], ask_once: bool = False) -> Dict[str, Any]:
    """THE ONE FINISH of a group booking, composed from the trip record (the master list as it is now — AgAPI's record for the booked):
    how many are booked, where the references are, the confirmations sent (to each traveller's registered email; anyone without one
    named), the invoice — and anything not done as a named decision, never an error."""
    from . import groups as G
    mv = await G.store().movement(account, movement_id)
    view = await G.view(account, movement_id)
    if view.get("record_unread"):   # Sasha 376 · nothing said as booked or not, no money said: the record, as unread
        return {"say": UNREAD_SAY, "booked": [], "total": len(view.get("rows") or []), "confirmations": {"sent": [], "no_email": [], "not_sent": []},
                "invoice": {}, "decisions": [], "unread": True}
    rows = view.get("rows") or []
    booked = [r["name"] for r in rows if r.get("status") == "booked"]
    confirming = [r["name"] for r in rows if r.get("status") == "confirming"]   # Sasha 371b · AgAPI's record: an order may exist
    incomplete = [r for r in rows if r.get("status") == "incomplete"]
    failed = [f for f in failed if f.get("name") not in set(confirming) | {r["name"] for r in incomplete}]   # a state, never asked as "not booked"
    total = len(rows)
    conf = await _confirmations(account, mv, booked) if booked else {"sent": [], "no_email": [], "not_sent": []}
    try:
        inv = await invoice(account, movement_id)
    except Exception as e:
        log.warning("[group_book] the invoice wasn't read for the finish: %s", type(e).__name__)
        inv = {}
    head = (f"All {total} booked" if booked and len(booked) == total else f"{len(booked)} of {total} booked" if booked else "Nobody was booked")
    parts = [head + (" (TEST)." if booked else ".")]
    if booked:
        parts.append("Their references are on the master list.")
        if conf["sent"]:
            parts.append(("Confirmations have been sent to each traveller's registered email" if not conf["no_email"] and not conf["not_sent"]
                          else f"Confirmations sent to {_names(conf['sent'])}") + ".")
        if conf["no_email"]:
            parts.append(f"No email on file for {_names(conf['no_email'])} — add it on the Group page and I'll send theirs.")
        if conf["not_sent"]:
            parts.append(f"{_names(conf['not_sent'])}'s confirmation didn't go out just now — I'll send it again.")
        if inv.get("unread"):   # Sasha 376 · never "€0.00" for a record that didn't answer
            parts.append(INVOICE_UNREAD_SAY)
        elif inv.get("number") and inv.get("total"):
            parts.append(f"The invoice {inv['number']}: {inv['total']}.")
    for d in done:   # Sasha 367 · each booked fare's own conditions (CR 181: parts[].conditions / cancel_by), said plainly
        said_for: set = set()
        for c in d.get("conditions") or []:
            words = [w for w in (("only the airline can cancel it" if c.get("cancel_by") == "airline" else ""),
                                 ("it can't be refunded" if c.get("refund") in (False, "none", "no") else ""),
                                 ("it can't be changed" if c.get("change") in (False, "none", "no") else "")) if w]
            line = f"{d['name']}'s {c.get('kind') or 'booking'}: " + ", ".join(words) + "."
            if words and line not in said_for:   # Sasha 371b · found live: both legs said the same line twice — once per fact
                said_for.add(line)
                parts.append(line)
    if confirming:
        parts.append(f"{_names(confirming)}: the airline hasn't confirmed yet — I'm checking, and nothing will be ordered twice.")
    # Sasha 371b · found by the live drill: no answer after every re-send, and AgAPI's record has NOTHING for them (no order was made) —
    # said from the record, never left out of the finish and never "booked"
    on_record = set(booked) | set(confirming) | {r["name"] for r in incomplete}
    unanswered = [d["name"] for d in done if d.get("state") == "unknown" and d["name"] not in on_record]
    if unanswered:
        parts.append(f"{_names(unanswered)}: the booking system didn't answer, and it has no order for "
                     f"{'them' if len(unanswered) > 1 else unanswered[0].split()[0]} — nothing was booked or charged, and nothing will be ordered "
                     f"twice. Say \"book {unanswered[0].split()[0]}\" to try again.")
    for r in incomplete:
        parts.append(f"{r['name']}: part of the trip is booked and the rest isn't"
                     + (f" ({FACTS.get(r.get('record_why') or '', str(r.get('record_why')).replace('_', ' '))})" if r.get("record_why") else "") + ".")
    if ask_once:   # Sasha 365 · the mandate: ONE grouped question for everything outside the limits
        q = one_question(failed)
        if q:
            parts.append(q)
    else:
        for f in failed:
            parts.append(f"{f['name']}: {f['why']}")
    return {"say": " ".join(parts), "booked": booked, "total": total, "confirmations": conf, "invoice": {k: inv.get(k) for k in ("number", "total")},
            "decisions": [{"name": f["name"], "code": f.get("code") or f.get("kind"),
                           "why": f.get("why") or FACTS.get(f.get("code") or f.get("kind") or "", "not booked just now")} for f in failed]}


def open_card(account: str) -> Optional[str]:
    """Sasha 376 · THE OPEN CARD on this organiser's conversation: the newest group card still waiting for their yes (the ONE card store,
    in time) → its id, else None. sasha.turn reads it BEFORE anything can start a new instruction: a yes in any form answers THIS card."""
    live = [(c["at"], cid) for cid, c in _CARDS.items() if c.get("account") == account and time.time() - c["at"] <= CARD_S]
    return max(live)[1] if live else None


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


def _card_for(account: str, action: str, it: dict, movement_id: str) -> Dict[str, Any]:
    """ONE worker's own card (a moved fare, re-asked alone): the SAME card store, the same Yes / No (yes_buttons in the route)."""
    cid = "grp_" + secrets.token_hex(10)
    _CARDS[cid] = {"account": account, "action": action, "items": [it], "at": time.time(), "movement_id": str(movement_id)}
    lines = list(it.get("lines") or []) + ([f"⚠ {it['name']} is OVER the group's limit ({it.get('over_words')}) — included only because you asked."]
                                           if it.get("over") and it.get("over_words") else [])
    return {"status": "awaiting_yes", "action": action, "read_back": lines, "read_back_id": cid, "name": it["name"],
            "ask": f"Book {it['name']} at the new fare? Everything is on the card (TEST — nothing is charged now).", "verb": "Book"}


async def _card_approvals(account: str, items: List[dict], done: list, failed: list) -> Optional[Dict[str, str]]:
    """Sasha 378 · CR 190 · on WhatsApp, a card of SEVERAL read-backs: their ONE reply approves the card — ONE approvals.in_app_tap
    {read_backs, session} (VS.whatsapp_card_tap), never one tap per item (AgAPI keeps the message id once). → {read_back_id: approval_id};
    each read-back AgAPI refused is said with ITS why — one already done is a STATE (ON_RECORD), never "failed". None: not that case
    (S2's in-app tap, a one-person card, the sandbox's simulated yes) — _approval, per read-back, as before."""
    from agapi import agapi_route as AR, venue_submit as VS
    if VS.WA.get() is None or VS.TAP.get() is not None or len(items) < 2:
        return None
    with AR.using(await AR.target_for(FAMILY, account)):   # the read-backs are the group family's target — their approval goes there too
        r = await VS.whatsapp_card_tap(account, [{"read_back_id": it["read_back_id"], "read_back_sha256": it["sha"]} for it in items])
    names = {it["read_back_id"]: it["name"] for it in items}
    if not r.get("ok"):
        for it in items:
            failed.append({"name": it["name"], "code": "approval_refused", "why": FACTS["approval_refused"]})
        return {}
    for x in r["refused"]:
        name = names.get(x.get("read_back_id"), "")
        if x.get("code") in ON_RECORD + (ERR.APPROVAL_CONSUMED,):   # already done on AgAPI's record: its state, never "failed"
            y = recorded({"code": x.get("code"), "details": {"state": "booked" if x.get("code") == ERR.ALREADY_COMPLETED else "unknown"}})
            done.append({"name": name, "state": y["state"], "parts": []})
        else:
            failed.append({"name": name, "code": x.get("code"), "why": x.get("why") or FACTS["approval_refused"]})   # AgAPI's own why
    return {k: v for k, v in r["approvals"].items() if v}


async def _act_one(account: str, it: dict, said: str, mv: dict, members: dict, done: list, failed: list, reasked: Optional[list] = None,
                   apv: Optional[str] = None) -> None:
    """ONE worker's act after the organiser's yes: the approval of THAT read-back (the card's, when ONE WhatsApp yes approved the card —
    CR 190), the act (its references open only through AgAPI's signed, bound call — CR 189), then the worker's ONE trip settled."""
    apv = apv or await _approval(account, it, said or "Yes, go ahead.")
    if not apv:
        failed.append({"name": it["name"], "code": "approval_refused", "why": FACTS["approval_refused"]})   # Sasha 366 · named, never "just now"
        return
    r = await _send(account, it["op"], it["body"], it["idem"], approval=apv)   # Sasha 371b · its ONE key, re-sent unchanged
    e = r.get("error") or {}
    d = e.get("details") or {}
    if e.get("code") in ON_RECORD + NO_ANSWER:   # Sasha 371b · AgAPI's record holds (or may hold) it: a state from the record, never "failed"
        x = recorded(e)
        done.append({"name": it["name"], "state": x["state"], "parts": []})
        return
    if e.get("code") == ERR.APPROVAL_VOID and d.get("void_reason") == "payload_changed" and reasked is not None:
        # Sasha 340 · CR 166: nothing was booked for THIS worker; the rest stand. A fresh read-back → their own card, their own Yes;
        # an offer gone (no read-back) → this worker prepared again (re-planned once), then their own card — or held, said.
        if d.get("read_back_id"):
            reasked.append({**it, "read_back_id": d["read_back_id"], "sha": d.get("read_back_sha256") or "",
                            "lines": list((d.get("read_back") or {}).get("lines") or []), "moved": True})
            return
        if it["op"] == OP.GROUP_BOOK:
            m = members.get(it["member"])
            org = (it.get("body") or {}).get("end_user")
            kind, x = await _prepare_worker(account, m, None, [m["name"]], bool(it.get("over")), org, mv) if m and org else ("skip", {"why": "not on the list"})
            if kind == "item":
                reasked.append({**x, "moved": True})
            else:
                failed.append({"name": it["name"], "why": x.get("why") or "the fare is gone and none was found again"})
            return
    if not r.get("ok") and e.get("code") in RETRY_ONCE and it["op"] == OP.GROUP_BOOK and not it.get("_retried"):
        # Sasha 365 · the airline refused the ORDER (found live, 10 Nov: two Vueling orders): once more, inside the same instruction — a
        # fresh fare for that worker (its own read-back, approved by the same words), never a question first
        m = members.get(it["member"])
        org = (it.get("body") or {}).get("end_user")
        kind, x = await _prepare_worker(account, m, None, [m["name"]], bool(it.get("over")), org, mv) if m and org else ("skip", {})
        if kind == "item":
            return await _act_one(account, {**x, "_retried": True}, said, mv, members, done, failed, reasked)   # its OWN read-back: its own approval
    if not r.get("ok"):
        why = decision(e)
        if it.get("_retried") and e.get("code") in RETRY_ONCE:
            why = {"code": "refused_twice", "why": FACTS["refused_twice"] + " — nothing was taken. Shall I look for another flight, or take them off?"}
        failed.append({"name": it["name"], **why})   # Sasha 364 · a named decision in plain words, never the supplier's raw text
        return
    res = r.get("result") or {}
    parts = res.get("parts") or []
    note = None
    try:   # AgAPI has DONE it: the trip follows — and if the trip can't, the act still happened and is said as done
        if it["op"] == OP.GROUP_BOOK:
            await _settle(account, members[it["member"]].get("trip_id"), "booked", parts)
        elif it["op"] == OP.GROUP_CANCEL:
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


async def invoice(account: str, movement_id: str) -> Dict[str, Any]:
    """ONE invoice for THIS movement (Sasha 371b: by its id — the link's own, never "the open trip"), from AgAPI's records for it."""
    from . import groups as G
    st = G.store()
    mv = await st.movement(account, movement_id) if movement_id else None
    if not mv:
        return {"why": "there's no group movement yet"}
    members = {m["id"]: m for m in await st.members(mv["id"])}
    try:
        recs = await _records(account, mv["id"])   # CR 184 · AgAPI's records for this movement only
    except Unread as e:   # Sasha 376 · an unread record is said as unread — never a €0.00 invoice
        return {"why": "unread", "unread": True, "cause": str(e), "number": f"KAN-{str(mv['id'])[:8].upper()}-TEST"}
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


# Sasha 374 · CR 186 · a test double on CALL may never answer a field AgAPI doesn't publish (agapi/contract_shape.py)
from agapi import contract_shape as _CONTRACT_SHAPE  # noqa: E402
_CONTRACT_SHAPE.guard(__name__, 'CALL')
