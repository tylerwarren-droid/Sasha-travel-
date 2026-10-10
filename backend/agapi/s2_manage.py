"""Sasha 226 · /s2 MANAGES what's booked: MY PLANS, CHANGE / CANCEL, and "I'M RUNNING LATE" — each act read back, done only on
the person's yes in a LATER turn, recorded with its proof. /s2 only (never in S1's tool list).

    my_plans         every trip and booking on the account (bookings made on /next too), upcoming first; `on` = one day
                     ("Where am I on the 5th?": that day's bookings and the night's hotel)
    running_late     read-back "I'll call {venue} and say the {name} table for {n} at {time} will arrive about {new}. OK?" → yes →
                     a short call in the venue's language (booking_signer.venue_notice; nobody answers → the email instead)
    change_booking   venue: new time / party (email or call, their answer decides) · flight: Duffel TEST change with Duffel's quote,
                     "not possible through the airline's system" said plainly · hotel: dates can't be changed yet — said, with the cancel
    cancel_booking   hotel: our TEST stay, cancelled free (no money moves) · flight: Duffel TEST cancel with Duffel's own refund quote
                     (a restaurant or spa: cancel_venue, already S2's)
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Dict, List, Optional

log = logging.getLogger("agapi.s2_manage")
_HELD: Dict[str, dict] = {}   # account → the read-back the next yes would bind to {tool, sha, at, …}
_OK = re.compile(r"^\s*(ok|okay|vale|sí|si|yes please|please do)[.!]?\s*$", re.I)


def _err(code: str, message: str):
    from agapi.v0 import ToolError
    return ToolError(code, message)


def _yes(said: str, *, cancel: bool = False, ok: bool = False) -> bool:
    from agapi import v0 as API
    from agapi.s2_tools import strict_yes
    return (API.yes_to_cancel(said) if cancel else strict_yes(said)) or bool(ok and _OK.match(said or ""))


def _hold(ctx, tool: str, lines: List[str], **extra) -> None:
    import hashlib
    _HELD[ctx.account] = {"tool": tool, "sha": hashlib.sha256("\n".join(lines).encode()).hexdigest(), "lines": lines,
                          "at": datetime.now(timezone.utc), **extra}


def _held(ctx, tool: str) -> Optional[dict]:
    from agapi.v0 import stale
    h = _HELD.get(ctx.account)
    if not h or h["tool"] != tool:
        return None
    if stale(h["at"]):
        _HELD.pop(ctx.account, None)
        return None
    return h if h["at"] < ctx.started else None   # the yes comes in a LATER turn than the read-back it answers


async def _record(account: str, kind: str, state: str, proof: dict, about: str) -> None:
    try:
        from agapi import s2_records as REC
        await REC.record(account, kind, state, {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), **proof}, about)
    except Exception as e:   # 039 not applied yet: the act stands; its Activity row waits
        log.info("[s2-manage] activity not recorded (%s): %s", kind, type(e).__name__)


# ── MY PLANS ─────────────────────────────────────────────────────────────────────────────────────────────────────────────────

def _venue_kind(t: Optional[str]) -> str:
    t = (t or "").lower()
    return "spa" if re.search(r"spa|massage|beauty|salon|nail|hair|wellness", t) else "dinner"


async def plans_of(account: str) -> List[dict]:
    """Everything booked (or awaiting payment) on the account, from Pacioli's records only — /next's and /s2's alike."""
    from agapi import venues as VN
    from booking_signer import basket as BK, plan_store as PS
    out: List[dict] = []
    for v in await VN.venue_bookings(account):
        when = f"{v['date']}T{v['time']}" if v.get("date") and v.get("time") else (v.get("date") or "")
        out.append({"kind": _venue_kind(v.get("type")), "title": v["venue"], "when": when, "status": v.get("status") or "",
                    "party": v.get("party"), **({"reference": v["reference"]} if v.get("reference") else {}), "id": v["trip_item_id"],
                    "source": "venue"})
    seen = set()
    for p in await PS.plans(account):
        for r in await BK.items(account, p["trip_id"], ("booked", "pending_payment")):
            if r["id"] in seen:
                continue
            seen.add(r["id"])
            s = r.get("snapshot") or {}
            status = "booked" if r["state"] == "booked" else "awaiting payment"
            if r["kind"] == "flight":
                title = " ".join(x for x in (s.get("owner"), s.get("flights")) if x) or "Flight"
                where = f"{s.get('from') or ''} → {s.get('to') or ''}".strip(" →")
                out.append({"kind": "flight", "title": title, "when": str(s.get("departs") or r.get("day") or ""), "where": where,
                            "status": status, **({"reference": r["booking_reference"]} if r.get("booking_reference") else {}),
                            "id": str(r["id"]), "order_id": r.get("order_id"), "trip": p.get("title"), "source": "flight"})
            elif r["kind"] == "stay":
                nights = int(s.get("nights") or 1)
                out.append({"kind": "hotel", "title": s.get("name") or s.get("hotel") or "Your stay", "when": str(r.get("day") or ""),
                            "where": s.get("city") or "", "nights": nights, "status": status,
                            **({"reference": r["booking_reference"]} if r.get("booking_reference") else {}),
                            "id": str(r["id"]), "trip_item_id": str(r["trip_item_id"]) if r.get("trip_item_id") else None,
                            "trip": p.get("title"), "source": "hotel"})
    today = date.today().isoformat()
    keep = [i for i in out if (i["when"] or today)[:10] >= today or
            (i["kind"] == "hotel" and i["when"] and (date.fromisoformat(i["when"][:10]) + timedelta(days=i.get("nights") or 1)).isoformat() > today)]
    return sorted(keep, key=lambda i: (i["when"] + ("T15:00" if i["kind"] == "hotel" and len(i["when"]) == 10 else "")) or "9999")   # a stay from check-in


def _on(items: List[dict], day: str) -> List[dict]:
    d = date.fromisoformat(day)
    hit = []
    for i in items:
        if not i["when"]:
            continue
        start = date.fromisoformat(i["when"][:10])
        if start == d or (i["kind"] == "hotel" and start <= d < start + timedelta(days=i.get("nights") or 1)):
            hit.append(i)
    return hit


async def my_plans(ctx, a: dict) -> dict:
    items = await plans_of(ctx.account)
    day = str(a.get("on") or "").strip()[:10] or None
    if day:
        try:
            items = _on(items, day)
        except ValueError:
            raise _err("date_invalid", "on is YYYY-MM-DD")
    shown = [{k: i.get(k) for k in ("kind", "title", "when", "where", "status", "reference", "id", "party", "nights") if i.get(k) is not None}
             for i in items[:20]]
    return {"items": shown, **({"on": day} if day else {}), "count": len(items),
            "say": ("Nothing booked that day." if day else "Nothing coming up.") if not items else
                   "Say the first one or two in a sentence; the card lists them all. Use each item's id to change or cancel it."}


# ── RUNNING LATE (a venue) ───────────────────────────────────────────────────────────────────────────────────────────────────

async def _venue_target(ctx, a: dict) -> dict:
    from agapi import venues as VN
    bookings = await VN.venue_bookings(ctx.account)
    tid, name = a.get("trip_item_id") or a.get("id"), (a.get("venue") or "").lower().strip()
    hit = [b for b in bookings if (tid and b["trip_item_id"] == tid) or (name and name in (b["venue"] or "").lower())]
    if not hit and not tid and not name:
        today = date.today().isoformat()
        hit = [b for b in bookings if b.get("date") == today] or bookings[:1]
    if not hit:
        raise _err("booking_unknown", "which booking? my_plans lists them")
    return hit[0]


def _arrive(b: dict, a: dict) -> Optional[str]:
    if re.fullmatch(r"\d{1,2}:\d{2}", str(a.get("arrive") or "")):
        return str(a["arrive"]).zfill(5)
    mins = a.get("minutes")
    if isinstance(mins, (int, float)) or str(mins or "").isdigit():
        t = datetime.combine(date.today(), time.fromisoformat(str(b["time"])[:5])) + timedelta(minutes=int(mins))
        return t.strftime("%H:%M")
    return None


async def _notice(ctx, a: dict, kind: str, tool: str) -> dict:
    from agapi import venues as VN
    from agapi.v0 import claim
    GW = VN._API()
    said = ((a.get("approval") or {}).get("said")) or ""
    held = _held(ctx, tool)
    if held and said and _yes(said, ok=True):   # anything but their yes is a NEW read-back below (nothing is sent)
        await claim(ctx)
        _HELD.pop(ctx.account, None)
        s, j = await GW.api(ctx.account, "POST", f"/api/booking/reservations/{held['tid']}/notice",
                            {"kind": kind, **held["args"], "read_back_sha256": held["notice_sha"], "approval": {"how": "voice", "said": said}}, timeout=60)
        if s != 200:
            raise _err((j or {}).get("rule") or "not_sent", GW.refusal_words(j or {}, s))
        what = "venue_late" if kind == "late" else "booking_change"
        if j.get("status") == "call_prepared":
            s2, j2 = await GW.api(ctx.account, "POST", f"/api/booking/calls/{j['call_id']}/place",
                                  {"read_back_sha256": j["call_read_back_sha256"], "approval": {"how": "voice", "said": said}}, timeout=60)
            ok = s2 == 200 and (j2 or {}).get("status") in ("placed", "uncertain", "scheduled")
            await _record(ctx.account, what, "requested" if ok else "failed", {"reference": j["call_id"], "said": said,
                                                                               "read_back_sha256": "sha256:" + held["sha"]}, held["venue"])
            return {"status": "calling" if ok else "not_placed", "venue": held["venue"],
                    "say": (f"Calling {held['venue']} now — I'll tell you here exactly what they say." if ok else
                            f"I couldn't place the call: {(j2 or {}).get('why') or GW.refusal_words(j2 or {}, s2)}")}
        await _record(ctx.account, what, "requested" if j.get("status") == "requested" else "failed",
                      {"reference": j.get("email_id") or held["tid"], "said": said, "read_back_sha256": "sha256:" + held["sha"]}, held["venue"])
        return {"status": j.get("status"), "venue": held["venue"], "say": j.get("say")}
    b = await _venue_target(ctx, a)
    args = {"arrive": _arrive(b, a)} if kind == "late" else {k: v for k, v in (("time", a.get("new_time")), ("party", a.get("new_party"))) if v}
    if kind == "late" and not args["arrive"]:
        raise _err("arrive_missing", "how late? ask what time they'll get there (or how many minutes)")
    q = "&".join(f"{k}={v}" for k, v in args.items() if v)
    s, j = await GW.api(ctx.account, "GET", f"/api/booking/reservations/{b['trip_item_id']}/notice?kind={kind}&{q}")
    if s != 200:
        raise _err((j or {}).get("rule") or "booking_unknown", GW.refusal_words(j or {}, s))
    lines = j["read_back"]["lines"]
    if not j.get("route"):
        return {"status": "not_possible", "venue": b["venue"], "say": " ".join(lines)}
    _hold(ctx, tool, lines, tid=b["trip_item_id"], args={k: str(v) for k, v in args.items() if v}, notice_sha=j["read_back"]["sha256"],
          venue=b["venue"])
    return {"status": "awaiting_yes", "venue": b["venue"], "route": j["route"], "read_back": lines,
            "say": "Read this back in a sentence or two (its first line as it is) and ask: OK? Act only on their yes in their next turn."}


async def running_late(ctx, a: dict) -> dict:
    return await _notice(ctx, a, "late", "running_late")


# ── CHANGE / CANCEL (venue · hotel · flight) ─────────────────────────────────────────────────────────────────────────────────

async def _item(ctx, a: dict, kind: str) -> dict:
    items = [i for i in await plans_of(ctx.account) if i["source"] == kind]
    iid, name = a.get("id"), (a.get("name") or a.get("venue") or "").lower()
    hit = [i for i in items if (iid and i["id"] == iid) or (name and name in i["title"].lower())] or (items if len(items) == 1 else [])
    if not hit:
        raise _err("booking_unknown", f"which {kind}? my_plans lists them (with their ids)")
    return hit[0]


async def change_booking(ctx, a: dict) -> dict:
    what = (a.get("what") or "").lower()
    if what in ("venue", "restaurant", "dinner", "spa", "table"):
        return await _notice(ctx, a, "change", "change_booking")
    if what == "hotel":
        it = await _item(ctx, a, "hotel")
        return {"status": "not_possible", "say": f"I can't change the dates of your stay at {it['title']} yet. I can cancel it — free, "
                                                 "it's a test booking — and book the new dates. Shall I read that back?"}
    if what == "flight":
        from booking_signer import flight_manage as FM
        said = ((a.get("approval") or {}).get("said")) or ""
        held = _held(ctx, "change_booking")
        if held and held.get("flight") and said and _yes(said):
            from agapi.v0 import claim
            await claim(ctx)
            _HELD.pop(ctx.account, None)
            got = await FM.change_confirm(held["change_offer_id"])
            done = got.get("status") == "changed"
            await _record(ctx.account, "booking_change", "done" if done else "failed",
                          {"reference": got.get("order_change_id") or held["order_id"], "said": said, "read_back_sha256": "sha256:" + held["sha"]},
                          held["title"])
            return {"status": got.get("status"), "say": ("Changed — Duffel confirmed it." + (f" Booking reference {got['booking_reference']}." if got.get("booking_reference") else ""))
                    if done else f"It wasn't changed: {got.get('why') or got.get('provider_words') or 'the airline system said no'}"}
        it = await _item(ctx, a, "flight")
        if not it.get("order_id"):
            raise _err("not_changeable", "that flight isn't ticketed yet (awaiting payment) — nothing to change")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(a.get("new_date") or "")):
            raise _err("date_missing", "which day should it move to? (YYYY-MM-DD)")
        q = await FM.change_quote(it["order_id"], a["new_date"], a.get("leg"))
        if q.get("why"):
            raise _err("change_unavailable", q["why"])
        if not q.get("possible"):
            return {"status": "not_possible", "say": q.get("say")}
        _hold(ctx, "change_booking", q["lines"], flight=True, change_offer_id=q["change_offer_id"], order_id=it["order_id"], title=it["title"])
        return {"status": "awaiting_yes", "read_back": q["lines"], "say": "Read it back, with Duffel's price, and ask: shall I?"}
    raise _err("what_invalid", "what is venue, hotel or flight")


async def cancel_booking(ctx, a: dict) -> dict:
    from agapi.v0 import claim
    what = (a.get("what") or "").lower()
    if what in ("venue", "restaurant", "dinner", "spa", "table"):
        raise _err("use_cancel_venue", "a restaurant or spa is cancelled with cancel_venue")
    said = ((a.get("approval") or {}).get("said")) or ""
    held = _held(ctx, "cancel_booking")
    if held and said and _yes(said, cancel=True):
        await claim(ctx)
        _HELD.pop(ctx.account, None)
        from booking_signer import basket as BK
        if held["kind"] == "flight":
            from booking_signer import flight_manage as FM
            got = await FM.cancel_confirm(held["quote_id"])
            if got.get("status") != "cancelled":
                return {"status": "not_cancelled", "say": f"It wasn't cancelled: {got.get('why') or got.get('provider_words')}"}
            await BK.cancelled(ctx.account, held["id"])   # Activity shows it (the basket row), with Duffel's cancellation as proof
            await BK.event("duffel_cancel", got.get("cancellation_id") or held["quote_id"], "order.cancelled", got, verified=True, item_id=held["id"])
            refund = f" Refund: {got['refund_currency']} {got['refund_amount']} to your original payment." if got.get("refund_amount") not in (None, "0", "0.00") else ""
            return {"status": "cancelled", "say": f"Cancelled — Duffel confirmed it.{refund}"}
        await BK.cancelled(ctx.account, held["id"])
        if held.get("trip_item_id"):
            from booking_signer import plan_store as PS
            run = PS._run()
            if run is not None:
                import uuid as _u
                await run(lambda c: c.execute("update trip_items set status = 'cancelled', updated_at = now() where id = $1", _u.UUID(held["trip_item_id"])))
        return {"status": "cancelled", "say": f"Cancelled your stay at {held['title']} — free, it was a test booking."}
    if what == "flight":
        from booking_signer import flight_manage as FM
        it = await _item(ctx, a, "flight")
        if not it.get("order_id"):
            raise _err("not_cancellable", "that flight isn't ticketed yet (awaiting payment) — nothing to cancel")
        q = await FM.cancel_quote(it["order_id"])
        if q.get("why"):
            raise _err("cancel_unavailable", q["why"])
        if not q.get("possible"):
            return {"status": "not_possible", "say": q.get("say")}
        _hold(ctx, "cancel_booking", q["lines"], kind="flight", quote_id=q["quote_id"], id=it["id"], title=it["title"])
        return {"status": "awaiting_yes", "read_back": q["lines"], "say": "Read it back, with Duffel's refund, and ask: shall I cancel it?"}
    if what == "hotel":
        it = await _item(ctx, a, "hotel")
        lines = [f"I'll cancel your stay at {it['title']}, from {it['when'][:10]} for {it.get('nights') or 1} night{'s' if (it.get('nights') or 1) != 1 else ''}"
                 + (f" (ref {it['reference']})." if it.get("reference") else "."),
                 "It's a test hotel booking: cancelling is free and no money moves.", "Shall I cancel it?"]
        _hold(ctx, "cancel_booking", lines, kind="hotel", id=it["id"], trip_item_id=it.get("trip_item_id"), title=it["title"])
        return {"status": "awaiting_yes", "read_back": lines, "say": "Read it back and ask: shall I cancel it?"}
    raise _err("what_invalid", "what is hotel or flight (a restaurant or spa: cancel_venue)")


def tools() -> List[dict]:
    from agapi.v0 import _t
    appr = {"approval": {"type": "object", "properties": {"said": {"type": "string"}}, "description": "the person's own words (filled by the caller)"}}
    return [
        _t("my_plans", "Pacioli", my_plans, "Everything booked on their account — restaurants, spas, flights, hotels, from any screen — "
           "upcoming first, on a card. 'What's coming up?' → no args; 'Where am I on the 5th?' → on=YYYY-MM-DD (that day's bookings and "
           "the night's hotel). Each item has an id for change_booking / cancel_booking / cancel_venue / running_late.",
           {"on": {"type": "string", "description": "YYYY-MM-DD, one day"}}, [], {"type": "object", "properties": {"items": {"type": "array"}}}, []),
        _t("running_late", "Austen", running_late, "They're running late for a restaurant or spa booking. FIRST call: the read-back — say its "
           "first line as it is and ask 'OK?'. After their yes in a LATER turn, call again (same booking): a short call to the venue in "
           "its language (no answer → an email). Give arrive (HH:MM) or minutes late; venue or id.",
           {"venue": {"type": "string"}, "id": {"type": "string"}, "arrive": {"type": "string", "description": "HH:MM"},
            "minutes": {"type": "integer", "minimum": 1, "maximum": 180}, **appr}, [],
           {"type": "object", "properties": {"status": {"type": "string"}}}, ["booking_unknown", "arrive_missing", "no_explicit_yes", "not_sent"], austen=True),
        _t("change_booking", "Austen", change_booking, "Change a booking. what=venue (new_time HH:MM and/or new_party), flight (new_date "
           "YYYY-MM-DD, leg out/back: Duffel's own quote; some fares can't be changed — say so plainly), hotel (dates can't be changed yet "
           "— say so). FIRST call: the read-back; after their yes in a LATER turn, call again to do it.",
           {"what": {"enum": ["venue", "flight", "hotel"]}, "id": {"type": "string"}, "venue": {"type": "string"}, "name": {"type": "string"},
            "new_time": {"type": "string"}, "new_party": {"type": "integer", "minimum": 1, "maximum": 20},
            "new_date": {"type": "string"}, "leg": {"enum": ["out", "back"]}, **appr}, ["what"],
           {"type": "object", "properties": {"status": {"type": "string"}}},
           ["booking_unknown", "no_explicit_yes", "change_unavailable", "not_changeable", "date_missing", "what_invalid"], austen=True),
        _t("cancel_booking", "Austen", cancel_booking, "Cancel a hotel stay or a flight (a restaurant or spa: cancel_venue). FIRST call: the "
           "read-back (a flight's refund is Duffel's own quote); after their explicit yes in a LATER turn, call again to cancel.",
           {"what": {"enum": ["hotel", "flight"]}, "id": {"type": "string"}, "name": {"type": "string"}, **appr}, ["what"],
           {"type": "object", "properties": {"status": {"type": "string"}}},
           ["booking_unknown", "no_explicit_yes", "cancel_unavailable", "not_cancellable", "what_invalid"], austen=True),
    ]


__all__ = ["my_plans", "running_late", "change_booking", "cancel_booking", "plans_of", "tools"]
