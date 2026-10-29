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
    """Everything booked (or awaiting payment) on the account — Sasha 300: THE ONE ITINERARY (agapi/itinerary.py), every route."""
    from agapi import itinerary as IT
    return await IT.of(account)


def _IT_stay_end(i: dict) -> str:
    from agapi import itinerary as IT
    return IT.stay_end(i)


def _on(items: List[dict], day: str) -> List[dict]:
    d = date.fromisoformat(day)
    hit = []
    for i in items:
        if not i["when"]:
            continue
        start = date.fromisoformat(i["when"][:10])
        if start == d or (i["kind"] == "hotel" and start <= d and d.isoformat() < _IT_stay_end(i)):   # Sasha 306 · AgAPI's check-out
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
    shown = [{k: i.get(k) for k in ("kind", "title", "when", "where", "status", "status_words", "route_words", "venue_said", "reference",
                                    "id", "party", "nights", "check_in", "check_out", "change_answer", "trip", "map_url", "terms", "perks", "live") if i.get(k) is not None}   # Sasha 300 · its route, their words · 302: the fine print
             for i in items[:20]]
    return {"items": shown, **({"on": day} if day else {}), "count": len(items),
            "say": ("Nothing booked that day." if day else "Nothing coming up.") if not items else
                   "Say the first one or two in a sentence; the card lists them all. Use each item's id to change or cancel it."}


# ── RUNNING LATE (a venue) ───────────────────────────────────────────────────────────────────────────────────────────────────

async def _venue_target(ctx, a: dict) -> dict:
    """Sasha 300 · the booking meant — the ONE itinerary's row (every route: AgAPI's acts, the hand-overs, the old ladder's)."""
    from agapi import itinerary as IT
    return await IT.find(ctx.account, a)


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
    if held and held.get("act_id") and said and _yes(said, ok=True):   # Sasha 300 · an AgAPI act: by ITS route, on this yes
        return await _act_notice_go(ctx, held, said, kind)
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
    from agapi import itinerary as IT
    if b["source"] == "handover":   # Sasha 300 · handed over (their page / his own WhatsApp): his, there, by that route — nothing sent
        return IT.page_answer(b, kind)
    if b["source"] == "act":   # Sasha 300 · AgAPI's act: the change goes by the route it went (venue.change_booking, CR 131 (c))
        return await _act_notice(ctx, a, b, kind, tool)
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


async def _act_notice(ctx, a: dict, b: dict, kind: str, tool: str) -> dict:
    """Sasha 300 · a change or "running late" for a booking AgAPI sent: venue.change_booking's read-back (its own route — an email
    act's an email, a WhatsApp act's a WhatsApp, a call act's a call). Not offered by AgAPI yet → said plainly; nothing is sent."""
    from agapi import venue_submit as VS
    from app.agent import voice as V
    if kind == "late":
        arrive = _arrive(b, a)
        if not arrive:
            raise _err("arrive_missing", "how late? ask what time they'll get there (or how many minutes)")
        args = {"arrive": arrive}
    else:
        hm = _HHMM.search(str(a.get("new_time") or ""))
        day = str(a.get("new_date") or b.get("date") or "")[:10]
        nights = a.get("nights") if a.get("nights") is not None else a.get("new_nights")
        # Sasha 306 · the tool's words → AgAPI's field names (one translation, never a list of what a kind may change): AgAPI's
        # booking_kinds takes what this booking's kind can change and refuses anything else by name — said as it says it
        args = {**({"at": f"{day}T{int(hm.group(1)):02d}:{hm.group(2)}"} if hm and day else {}),
                **({"party": int(a["new_party"])} if str(a.get("new_party") or "").isdigit() else {}),
                **({"nights": int(nights)} if str(nights or "").isdigit() else {}),
                **({"check_in": str(a["check_in"])[:10]} if a.get("check_in") else {})}
        if not args:
            raise _err("change_missing", "what should it change to — a new time, a different number of people, or (a stay) its nights "
                                         "or check-in day?")
    rb = await VS.change_read_back(ctx.account, b["act_id"], kind, **args)
    if not rb.get("ok"):
        e = rb["error"]
        if e["code"] == "not_yet":
            return {"status": "not_possible", "venue": b["venue"], "route": b["route"], "sent": False,
                    "say": V.change_not_yet(b["venue"], b["route_words"], kind)}
        if e["code"] == "not_allowed":
            link = (e.get("details") or {}).get("link")
            return {"status": "not_possible", "venue": b["venue"], "say": e["message"], **({"open": link, "page_url": link} if link else {})}
        raise _err(e["code"], e["message"])
    st = b.get("stay") if isinstance(b.get("stay"), dict) else None
    _hold(ctx, tool, rb["lines"], act_id=b["act_id"], read_back_id=rb["read_back_id"], read_back_sha256=rb.get("read_back_sha256"),
          end_user=rb.get("end_user"), venue=b["venue"], kind=kind, route=b["route"], ask=args, stay=bool(st))   # Sasha 302: his yes sends it
    return {"status": "awaiting_yes", "venue": b["venue"], "route": b["route"], "read_back": rb["lines"],
            # Sasha 306 · a stay's read-back is said by code (voice.flight_line): the stay as AgAPI's record has it, then AgAPI's own
            # read-back (the new nights and check-out are its words) — old vs new, nothing computed here
            **({"stay": True, "was": stay_words(b["venue"], st)} if st else {}),
            "say": "Read this back in a sentence or two (its first line as it is) and ask: OK? Act only on their yes in their next turn."}


def stay_words(venue: str, st: dict) -> str:
    """Sasha 306 · a stay as AgAPI's record has it (venue.bookings' stay: check_in, check_out, nights) — its own dates, never computed."""
    def d(x):
        try:
            return date.fromisoformat(str(x)[:10]).strftime("%a %d %b")
        except ValueError:
            return str(x or "")
    n = st.get("nights")
    return (f"Your stay at {venue} now reads {d(st.get('check_in'))} to {d(st.get('check_out'))}"
            + (f" ({n} night{'s' if n != 1 else ''})" if n else "") + ".")


async def _act_notice_go(ctx, held: dict, said: str, kind: str) -> dict:
    """On his yes (a later turn): venue.change_booking with the approval → sent by the act's route, or (his own WhatsApp) the message
    for HIM to send. The venue's answer comes back on the act (venue.booking_status) and the itinerary shows it."""
    from agapi.v0 import claim
    from agapi import venue_submit as VS
    await claim(ctx)
    _HELD.pop(ctx.account, None)
    r = await VS.change_submit(ctx.account, held, said)
    if not r.get("ok"):
        raise _err(r["error"]["code"], r["error"]["message"])
    what = "venue_late" if kind == "late" else "booking_change"
    if r.get("status") == "waiting_for_their_tap":
        return {"status": "waiting_for_their_tap", "venue": held["venue"], "say": "I've sent you the link — it goes once you tap yes there."}
    if r.get("status") == "person_sends":   # his own WhatsApp: the message AgAPI wrote, for him to send (nothing sent by Kanoe)
        m = r.get("message") or {}
        return {"status": "yours_to_send", "venue": held["venue"], "sent": False, "say": r.get("say") or "",
                **({"open": m["link"], "button": {"label": "Send on WhatsApp", "link": m["link"]}} if m.get("link") else {})}
    await _record(ctx.account, what, "requested" if r.get("status") == "sent" else "failed",
                  {"reference": r.get("change_act_id") or held["act_id"], "said": said, "read_back_sha256": "sha256:" + held["sha"]},
                  held["venue"])
    return {"status": "requested" if r.get("status") == "sent" else r.get("status"), "venue": held["venue"],
            **({"stay": True} if held.get("stay") else {}),   # Sasha 306 · AgAPI's own words after his yes, said by code
            "say": r.get("say") or ("I've told them. It's held once they reply." if kind == "late" else
                                    "I've asked them. It's changed only once they reply to say so; until then it stays as it was.")}


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


_KINDS = {"flight": ("flight",), "hotel": ("hotel",), "venue": ("dinner", "spa"), "restaurant": ("dinner",), "dinner": ("dinner",),
          "spa": ("spa",), "table": ("dinner",)}
_WHAT = {"flight": "flight", "hotel": "hotel", "dinner": "venue", "spa": "venue"}


async def booking_meant(ctx, a: dict, what: str) -> Optional[dict]:
    """Sasha 305 · THE ONE RESOLVER for a change or a cancel: the itinerary row the person means (agapi/itinerary.of — every kind, every
    route). By its id first (any kind: the row's own kind then decides, never the model's `what`); else among `what`'s kind by name (the
    booking's, its trip's or its place's), a flight by leg (out = the trip's first, back = its last); one of the kind → that one.
    None when nothing on the itinerary matches (the caller's older paths answer)."""
    items = [i for i in await plans_of(ctx.account) if i.get("status") != "cancelled"]
    iid = str(a.get("id") or "").strip()
    if iid:
        hit = next((i for i in items if iid in (i.get("id"), i.get("order_id"), i.get("reference"))), None)
        if hit:
            return hit
    pool = [i for i in items if i.get("kind") in _KINDS.get(what, ())]
    name = re.sub(r"\s+", " ", str(a.get("name") or a.get("venue") or "").lower()).strip()
    if name:
        pool = [i for i in pool if any(name in str(i.get(k) or "").lower() for k in ("title", "trip", "where"))] or \
            ([] if what != "flight" else pool)   # "my Rio flight": a flight is named by its trip or its airports, never only its number
    if what == "flight" and len(pool) > 1 and a.get("leg") in ("out", "back"):
        pool = sorted(pool, key=lambda i: str(i.get("when") or ""))
        return pool[0] if a["leg"] == "out" else pool[-1]
    if len(pool) == 1:
        return pool[0]
    if what == "flight" and len(pool) > 1:
        raise _err("which_flight", "more than one flight is booked — which one: out or back (leg), or its id from my_plans?")
    if what == "hotel" and len(pool) > 1:   # two stays of the same name: never the first one found — ask, by their dates
        raise _err("which_booking", "more than one stay matches — which one? " + "; ".join(
            f"{i['title']} from {str(i.get('when') or '')[:10]} (id {i['id']})" for i in pool[:4]))
    return pool[0] if pool else None


def _act_ref(row: dict) -> dict:
    """An itinerary venue row → how cancel_venue names it (its act, its hand-over, or the old ladder's trip item)."""
    rid = str(row.get("id") or "")
    return {"act_id": rid} if rid.startswith("act_") else {"id": rid} if rid.startswith("hand:") else {"trip_item_id": rid}


_CHANGE: Dict[str, dict] = {}   # Sasha 246 · account → the flight-change options she offered {order_id, new_date, leg, options, default, at}
_HHMM = re.compile(r"\b([01]?\d|2[0-3])[:.h]([0-5]\d)\b")


def _offered(ctx, order_id: str, new_date: Optional[str], leg: Optional[str]) -> Optional[dict]:
    """Sasha 246 · the change options offered for THIS order (the same day and leg, when given), still inside the read-back window."""
    from agapi.v0 import stale
    o = _CHANGE.get(ctx.account)
    if not o or o.get("order_id") != order_id or stale(o["at"]):
        return None
    if (new_date and new_date != o["new_date"]) or (leg and o.get("leg") and leg != o["leg"]):
        return None
    return o


def _option_named(options: List[dict], a: dict, said: str):
    """Sasha 246 · (the offered option they named, named?) — by change_offer_id, by new_time (HH:MM), or by a time in their own
    words that IS one of the options (a time in their words that isn't — "my 09:00 flight" — is no pick)."""
    oid = str(a.get("change_offer_id") or "").strip()
    if oid:
        return next((o for o in options if o.get("change_offer_id") == oid), None), True
    m = _HHMM.search(str(a.get("new_time") or ""))
    if m:
        hhmm = f"{int(m.group(1)):02d}:{m.group(2)}"
        return next((o for o in options if str(o.get("departs") or "")[11:16] == hhmm), None), True
    for m in _HHMM.finditer(said or ""):
        hhmm = f"{int(m.group(1)):02d}:{m.group(2)}"
        hit = next((o for o in options if str(o.get("departs") or "")[11:16] == hhmm), None)
        if hit:
            return hit, True
    return None, False


def _options_view(options: List[dict]) -> List[dict]:
    from booking_signer import flight_manage as FM
    out = []
    for o in options:
        amt = FM._amount(o.get("change_total_amount"))
        cost = "no cost" if not amt else FM.money(amt, o.get("change_total_currency")) + (" back" if amt < 0 else "")
        out.append({"time": str(o.get("departs") or "")[11:16], "flights": o.get("new_flights") or "flight", "cost": cost,
                    "change_offer_id": o.get("change_offer_id")})
    return out


NO_REAL_MONEY = "No real money moves."   # Sasha 305 · S2's screen drops a TEST label (Sasha 218): "This is a TEST booking — no money
#                                          moves" showed as "This is a booking — no money moves". This says the truth with no label to drop


def _s2_lines(lines: List[str]) -> List[str]:
    from booking_signer import flight_manage as FM
    return [NO_REAL_MONEY if x == FM.TEST_LINE else x for x in lines]


def changed_words(got: dict) -> str:
    """Sasha 305 · after his yes: what Duffel's order says NOW (re-read after the change) — the new flight and times, its reference,
    and what was charged or refunded (Duffel's own change total). The order unread → said so, never the offer's words as the result."""
    from booking_signer import flight_manage as FM
    o = got.get("order") or {}
    amt = FM._amount(got.get("change_total_amount"))
    money = (f"{FM.money(amt, got.get('change_total_currency'))} was charged to the Duffel test balance." if amt and amt > 0 else
             f"{FM.money(amt, got.get('change_total_currency'))} comes back." if amt and amt < 0 else "Nothing was charged.")
    if not o:
        return (f"Changed — Duffel confirmed it. {money} I couldn't re-read the booking from Duffel just now "
                f"({got.get('order_why') or 'no answer'}), so check My trips in a moment. {NO_REAL_MONEY}")
    legs = "; ".join(f"{l['flights']}, {l['times']}" for l in o.get("legs") or [] if l.get("times")) or o.get("flights") or "your flight"
    return (f"Changed — Duffel confirmed it. Your {o.get('owner') or 'airline'} booking now reads: {legs}. "
            f"Booking reference {o.get('reference') or '—'}. {money} {NO_REAL_MONEY}")


async def change_booking(ctx, a: dict) -> dict:
    what = (a.get("what") or "").lower()
    row = None
    if a.get("id") or what == "hotel":   # Sasha 305 · the booking he means decides who answers: its own source, never the model's `what`
        row = await booking_meant(ctx, a, what)
        if row:
            what = _WHAT.get(row["kind"], what)
    if what in ("venue", "restaurant", "dinner", "spa", "table"):
        return await _notice(ctx, {**a, **({"id": row["id"], "venue": row["title"]} if row else {})}, "change", "change_booking")
    if what == "hotel":
        if row and row.get("source") == "venue":   # Sasha 305 · a stay booked through AgAPI (CR 102): by the hotel's own route
            # Sasha 306 · its nights / check-in too (CR 137): AgAPI's read-back, then his yes — Sasha 305's "not yet" is retired
            return await _notice(ctx, {**a, "id": row["id"], "venue": row["title"]}, "change", "change_booking")
        it = row or await _item(ctx, a, "hotel")
        return {"status": "not_possible", "say": f"I can't change the dates of your stay at {it['title']} yet. I can cancel it — free, "
                                                 "it's a test booking — and book the new dates. Shall I read that back?"}
    if what == "flight":
        from booking_signer import flight_manage as FM
        said = ((a.get("approval") or {}).get("said")) or ""
        held = _held(ctx, "change_booking")
        pick = None
        if held and held.get("flight") and said and _yes(said):
            # Sasha 246 · a yes that names ANOTHER of the offered times ("yes, the 17:48") is not a yes to this read-back: that
            # option is read back instead, from the options she offered — never confirmed, never searched again
            off = _CHANGE.get(ctx.account)
            if off and off.get("order_id") == held.get("order_id"):
                pick, _named = _option_named(off["options"], {}, said)
                a = {**a, "id": a.get("id") or held.get("item_id")}
        if held and held.get("flight") and said and _yes(said) and (not pick or pick["change_offer_id"] == held["change_offer_id"]):
            from agapi.v0 import claim
            await claim(ctx)
            _HELD.pop(ctx.account, None)
            _CHANGE.pop(ctx.account, None)
            got = await FM.change_confirm(held["change_offer_id"])
            done = got.get("status") == "changed"
            await _record(ctx.account, "booking_change", "done" if done else "failed",
                          {"reference": got.get("order_change_id") or held["order_id"], "said": said, "read_back_sha256": "sha256:" + held["sha"]},
                          held["title"])
            if not done:
                return {"flight": True, "status": got.get("status"), "say": f"It wasn't changed: {got.get('why') or got.get('provider_words') or 'the airline system said no'}"}
            return {"flight": True, "status": "changed", "order_id": got.get("order_id"), "booking_reference": got.get("booking_reference"),
                    "say": changed_words(got), "how": "Say this as it is: it is the order as Duffel has it now."}
        it = row if row and row.get("kind") == "flight" else (await booking_meant(ctx, a, "flight") or await _item(ctx, a, "flight"))
        if (it.get("legs") or 1) < 2:   # Sasha 305 · one flight per order (the Rio trip's out and back): the order IS the leg
            a = {k: v for k, v in a.items() if k != "leg"}
        if not it.get("order_id"):
            raise _err("not_changeable", "that flight isn't ticketed yet (awaiting payment) — nothing to change")
        # Sasha 246 · THE OPTIONS SHE OFFERED are the options the change accepts: the same order, day and leg within the
        # read-back window → picked from them (by new_time / change_offer_id / a time in their words), never a fresh quote
        off = _offered(ctx, it["order_id"], a.get("new_date"), a.get("leg"))
        new_date = str(a.get("new_date") or (off or {}).get("new_date") or "")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", new_date):
            raise _err("date_missing", "which day should it move to? (YYYY-MM-DD)")
        if off is None:
            q = await FM.change_quote(it["order_id"], new_date, a.get("leg"))
            if q.get("why"):
                raise _err("change_unavailable", q["why"])
            if not q.get("possible"):
                return {"flight": True, "status": "not_possible", "say": q.get("say")}
            off = {"order_id": it["order_id"], "new_date": new_date, "leg": a.get("leg"), "options": q.get("options") or [q],
                   "default": q["change_offer_id"], "at": datetime.now(timezone.utc)}
            _CHANGE[ctx.account] = off
        if pick is None:
            pick, named = _option_named(off["options"], a, said)
            if named and pick is None:
                times = ", ".join(v["time"] for v in _options_view(off["options"]) if v["time"])
                return {"status": "not_offered", "options": _options_view(off["options"]),
                        "say": f"That isn't one of the times Duffel offered for {FM._day(new_date)} — the times are {times}. "
                               "Say them and ask which one; never say a time is unavailable that is on this list."}
        q = pick or next((o for o in off["options"] if o["change_offer_id"] == off["default"]), off["options"][0])
        lines = _s2_lines(list(q["lines"]))
        mine = next((v for v in _options_view([q])), {})
        others, said_ = [], {(mine.get("time"), mine.get("flights"), mine.get("cost"))}
        for v in _options_view(off["options"]):   # Sasha 305 · found live: each time listed 2–3 times (fare brands), the offered one too
            k = (v["time"], v["flights"], v["cost"])
            if v["time"] and k not in said_:
                said_.add(k)
                others.append(v)
        if others:
            lines.insert(len(lines) - 1, "Other times that day, from the same Duffel quote: "
                         + ", ".join(f"{v['time']} ({v['flights']}, {v['cost']})" for v in others) + ".")
        _hold(ctx, "change_booking", lines, flight=True, change_offer_id=q["change_offer_id"], order_id=it["order_id"], title=it["title"],
              item_id=it["id"])
        return {"flight": True, "status": "awaiting_yes", "read_back": lines, "options": _options_view(off["options"]),
                "say": "Read it back, with Duffel's price, and ask: shall I? If they pick another of these times, call change_booking "
                       "again with that new_time (HH:MM) — it is one of these options, never a new search."}
    raise _err("what_invalid", "what is venue, hotel or flight")


def _held_lines(pend: dict, title: Optional[str]) -> List[str]:
    """Sasha 246 · the read-back for dropping a HELD trip (its items waiting for payment, nothing booked)."""
    names = []
    for r in pend.get("rows") or []:
        s = r.get("snapshot") or {}
        if r.get("kind") == "flight":
            names.append(" ".join(x for x in (s.get("owner"), s.get("flights"), f"{s.get('from') or ''}→{s.get('to') or ''}".strip("→")) if x) or "a flight")
        elif r.get("kind") == "stay":
            names.append(f"{s.get('name') or s.get('hotel') or 'a hotel'}" + (f", {s['city']}" if s.get("city") else ""))
    head = f"I'll drop your held trip{f' “{title}”' if title else ''}" + (f": {'; '.join(names)}." if names else ".")
    return [head, "It isn't booked or paid: the payment page is closed, nothing is charged and there's nothing to refund.", "Shall I drop it?"]


async def _drop_held(ctx) -> dict:
    """Sasha 246 · CANCEL CAN DROP A HELD PLAN: the trip's items held for a payment that was never made (pending_payment, no
    order) — the read-back first; nothing is touched until their yes in a later turn."""
    from booking_signer import basket_book as BB
    pend = await BB.in_progress(ctx.account)
    if not pend:   # found live (246): a trip read back but not yet paid has no payment held — the planned trip itself is dropped
        cur = await BB.current(ctx.account)
        if cur and cur.get("rows") and not await _any_booked(ctx.account, cur["trip_id"]):
            title = cur.get("title") or "your trip"
            lines = [_held_lines({"rows": cur["rows"]}, title)[0].replace("your held trip", "your planned trip"),
                     "Nothing on it is booked or paid, so nothing is charged and there's nothing to refund.", "Shall I drop it?"]
            _hold(ctx, "cancel_booking", lines, kind="planned", trip_id=cur["trip_id"], title=title)
            return {"status": "awaiting_yes", "read_back": lines, "say": "Read it back and ask: shall I drop it?"}
        raise _err("nothing_held", "nothing is held for payment — my_plans lists what's booked")
    title = next((p.get("title") for p in await _plans(ctx.account) if p.get("trip_id") == pend["trip_id"]), None)
    lines = _held_lines(pend, title)
    _hold(ctx, "cancel_booking", lines, kind="held", sid=pend["sid"], trip_id=pend["trip_id"], title=title or "your trip")
    return {"status": "awaiting_yes", "read_back": lines, "say": "Read it back and ask: shall I drop it?"}


async def _any_booked(account: str, trip_id: str) -> bool:
    from booking_signer import basket as BK
    return bool(await BK.items(account, trip_id, ("booked", "pending_payment")))


async def _dropped_planned(ctx, held: dict) -> dict:
    """Sasha 246 · their yes to dropping the planned trip: its suggested / chosen items cancelled and the plan marked cancelled
    (never deleted) — only while nothing on it is booked or held for payment."""
    from booking_signer import basket as BK
    if await _any_booked(ctx.account, held["trip_id"]):
        return {"status": "not_cancelled", "say": "Something on that trip is now booked or being paid for, so I haven't dropped it — "
                                                  "nothing was changed. Ask me again."}
    await BK.drop_planned(ctx.account, held["trip_id"])
    from booking_signer import plan_store as PS
    run = PS._run()
    if run is not None:
        import uuid as _u
        try:
            await run(lambda c: c.execute("update trips set status = 'cancelled', updated_at = now() where id = $1 and owner_id = $2 "
                                          "and status in ('draft','active')", _u.UUID(held["trip_id"]), _u.UUID(ctx.account)))
        except Exception as e:
            log.warning("[s2-manage] planned trip not marked cancelled: %s", type(e).__name__)
    log.info("[s2-manage] planned trip %s dropped on their yes", held["trip_id"][:8])
    return {"status": "cancelled", "say": f"Dropped {held.get('title') or 'your planned trip'} — nothing was booked or charged."}


async def _plans(account: str) -> List[dict]:
    from booking_signer import plan_store as PS
    try:
        return await PS.plans(account)
    except Exception as e:
        log.info("[s2-manage] plans not read: %s", type(e).__name__)
        return []


async def _dropped(ctx, held: dict, said: str) -> dict:
    """Sasha 246 · their yes to dropping the held trip: the payment closed at Stripe first (so it can never be paid), its items
    cancelled (basket_book's own supersede path); paid already → refused, never dropped."""
    from booking_signer import basket as BK, basket_book as BB
    pend = await BB.in_progress(ctx.account)
    if not pend or pend["sid"] != held["sid"]:
        return {"status": "not_cancelled", "say": "That held trip has changed since I read it back — nothing was dropped. Ask me again."}
    refused = await BB._supersede(ctx.account, pend)
    if refused:
        return {"status": "not_cancelled", "say": f"It wasn't dropped: {refused['why']}."}
    if not await BK.items(ctx.account, held["trip_id"], ("booked",)):   # nothing booked on it: the plan itself goes (cancelled, not deleted)
        from booking_signer import plan_store as PS
        run = PS._run()
        if run is not None:
            import uuid as _u
            try:
                await run(lambda c: c.execute("update trips set status = 'cancelled', updated_at = now() where id = $1 and owner_id = $2 "
                                              "and status in ('draft','active')", _u.UUID(held["trip_id"]), _u.UUID(ctx.account)))
            except Exception as e:
                log.warning("[s2-manage] held trip's plan not cancelled: %s", type(e).__name__)
    log.info("[s2-manage] held trip %s dropped on their yes (payment %s)", held["trip_id"][:8], held["sid"][:14])   # the rows' cancelled state is its record
    return {"status": "cancelled", "say": f"Dropped {held.get('title') or 'your held trip'} — nothing was booked or charged."}


async def cancelled_words(got: dict) -> str:
    """Sasha 305 · after his yes to cancelling a flight: Duffel's confirmed refund, and the order re-read — said cancelled only as it reads."""
    from booking_signer import flight_manage as FM
    amt = FM._amount(got.get("refund_amount"))
    refund = (f"Refund: {FM.money(amt, got.get('refund_currency'))} {FM.REFUND_TO.get(str(got.get('refund_to') or ''), '')}".rstrip() + "."
              if amt and amt > 0 else "There is no refund.")
    o = await FM.order_now(got.get("order_id")) if got.get("order_id") else {"why": "no order on the cancellation"}
    now = (f"Duffel's booking {o.get('reference') or '—'} now reads cancelled." if o.get("cancelled") else
           "I couldn't re-read the booking from Duffel just now — My trips shows it once Duffel does." if o.get("why") else
           f"Duffel's booking {o.get('reference') or '—'} doesn't read cancelled yet — I'll check again.")
    return f"Cancelled — Duffel confirmed it. {refund} {now} {NO_REAL_MONEY}"


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
        if held["kind"] == "held":   # Sasha 246 · a held (unpaid, unbooked) trip dropped
            return await _dropped(ctx, held, said)
        if held["kind"] == "planned":   # Sasha 246 · a planned trip (read back, never paid) dropped
            return await _dropped_planned(ctx, held)
        if held["kind"] == "flight":
            from booking_signer import flight_manage as FM
            got = await FM.cancel_confirm(held["quote_id"])
            if got.get("status") != "cancelled":
                return {"flight": True, "status": "not_cancelled", "say": f"It wasn't cancelled: {got.get('why') or got.get('provider_words')}"}
            await BK.cancelled(ctx.account, held["id"])   # Activity shows it (the basket row), with Duffel's cancellation as proof
            await BK.event("duffel_cancel", got.get("cancellation_id") or held["quote_id"], "order.cancelled", got, verified=True, item_id=held["id"])
            return {"flight": True, "status": "cancelled", "order_id": got.get("order_id"), "say": await cancelled_words(got),
                    "how": "Say this as it is: it is Duffel's own answer and the order as it reads now."}
        await BK.cancelled(ctx.account, held["id"])
        if held.get("trip_item_id"):
            from booking_signer import plan_store as PS
            run = PS._run()
            if run is not None:
                import uuid as _u
                await run(lambda c: c.execute("update trip_items set status = 'cancelled', updated_at = now() where id = $1", _u.UUID(held["trip_item_id"])))
        return {"status": "cancelled", "say": f"Cancelled your stay at {held['title']} — free, it was a test booking."}
    if what in ("plan", "trip", "held"):   # Sasha 246 · the held trip, as a whole
        return await _drop_held(ctx)
    row = None
    if a.get("id") or what in ("hotel", "flight"):   # Sasha 305 · the booking he means decides who answers (its own source)
        row = await booking_meant(ctx, a, what)
        if row:
            what = _WHAT.get(row["kind"], what)
    if row and row.get("source") == "venue":   # Sasha 305 · booked through AgAPI (a hotel stay, CR 102; a table): its own route
        from agapi import venues as VN
        return await VN.cancel_venue(ctx, {**{k: v for k, v in a.items() if k not in ("id", "what")}, **_act_ref(row)})
    if what == "flight":
        from booking_signer import flight_manage as FM
        it = row if row and row.get("kind") == "flight" else await _item(ctx, a, "flight")
        if not it.get("order_id") and it.get("status") == "awaiting payment":   # Sasha 246 · held, never ticketed: drop the held trip
            return await _drop_held(ctx)
        if not it.get("order_id"):
            raise _err("not_cancellable", "that flight isn't ticketed yet (awaiting payment) — nothing to cancel")
        q = await FM.cancel_quote(it["order_id"])
        if q.get("why"):
            raise _err("cancel_unavailable", q["why"])
        if not q.get("possible"):
            return {"flight": True, "status": "not_possible", "say": q.get("say")}
        rb = _s2_lines(q["lines"])
        _hold(ctx, "cancel_booking", rb, kind="flight", quote_id=q["quote_id"], id=it["id"], title=it["title"])
        return {"flight": True, "status": "awaiting_yes", "read_back": rb, "say": "Read it back, with Duffel's refund, and ask: shall I cancel it?"}
    if what == "hotel":
        it = row or await _item(ctx, a, "hotel")
        if it.get("status") == "awaiting payment":   # Sasha 246 · held with the trip's payment: the held trip is dropped as one
            return await _drop_held(ctx)
        lines =[f"I'll cancel your stay at {it['title']}, from {it['when'][:10]} for {it.get('nights') or 1} night{'s' if (it.get('nights') or 1) != 1 else ''}"
                 + (f" (ref {it['reference']})." if it.get("reference") else "."),
                 "It's a test hotel booking: cancelling is free and no money moves.", "Shall I cancel it?"]
        _hold(ctx, "cancel_booking", lines, kind="hotel", id=it["id"], trip_item_id=it.get("trip_item_id"), title=it["title"])
        return {"status": "awaiting_yes", "read_back": lines, "say": "Read it back and ask: shall I cancel it?"}
    raise _err("what_invalid", "what is hotel, flight or plan (a held trip); a restaurant or spa: cancel_venue")


async def note_rental(ctx, a: dict) -> dict:
    """Sasha 227 · a car rental they tell her about (Sasha books none): kept so My plans shows it and, for the founder behind
    SASHA_PROACTIVE_RENTALS, the evening before pickup she can say what to decline at the counter (CR 75's moment)."""
    from booking_signer import rental_moments as RM
    try:
        r = await RM.note(ctx.account, a)
    except ValueError as e:
        raise _err("rental_invalid", str(e))
    return {"saved": True, "rental": {k: r[k] for k in ("rental_company", "country", "place", "pickup_date", "pickup_time") if r.get(k)},
            "say": "Say it's noted in a sentence. If they haven't seen the counter card yet, offer it (rental_cover)."}


# ── Sasha 253 · the WhatsApp old flow's capabilities, in the one brain (docs/sasha/S252-whatsapp-capabilities.md G1 · G9 · G10 ·
# G13). Each tool CALLS the old flow's own helper — the one place its logic lives — so /s2, WhatsApp and /next (parity) do what
# WhatsApp's old flow did, with the same words.

def _on_whatsapp(ctx) -> bool:
    return str(getattr(ctx, "session", "") or "").startswith("wa:")


def _their_words(ctx, a: dict, key: str, must: Optional[str] = None) -> str:
    """Their own words this turn (never the model's copy of them) — unless they don't carry what's needed (`must`, a regex)."""
    said = str(getattr(ctx, "user_said", "") or "").strip()
    given = str(a.get(key) or "").strip()
    if said and (not must or re.search(must, said, re.I)):
        return said
    return given or said


async def file_confirmation(ctx, a: dict) -> dict:
    """G1 · a venue's confirmation they forwarded or pasted → filed on the ONE booking it names (booking_signer/written.py),
    read with the field checks — guest_whatsapp.forwarded_confirmation, the old flow's own path (Sasha 118)."""
    from booking_signer import guest_whatsapp as GW
    text = _their_words(ctx, a, "text")
    number = None
    try:
        ch = await GW.STORE.channel_of_account(ctx.account) if GW.STORE is not None else None
        number = (ch or {}).get("number_e164")
    except Exception as e:
        log.info("[s2-manage] no channel for the forward: %s", type(e).__name__)
    line = await GW.forwarded_confirmation(ctx.account, number, text, GW.NOW(), prefix="wa-fwd-" if _on_whatsapp(ctx) else "web-fwd-")
    if line is None:
        return {"filed": False, "say": "That doesn't read like a venue's confirmation — it needs the venue's own words with the day "
                                       "(and their reference if they gave one). Nothing was filed."}
    return {"filed": not line.startswith("That reads like"), "say": line, "how": "Say this line as it is; nothing else changed."}


async def time_between(ctx, a: dict) -> dict:
    """G9 · "do I have time to drive / fly to X between A and B?" — booking_signer/itinerary_q.answer, the old flow's own answer:
    their bookings, Google's Routes API (driving) and Duffel's TEST schedules (flying). Nothing guessed."""
    from booking_signer import guest_whatsapp as GW, itinerary_q as IQ
    text = _their_words(ctx, a, "question", must=r"\bdo i have time\b")
    if not re.search(r"\bdo i have time\b", text, re.I):
        text = "do I have time " + re.sub(r"^\s*(?:do\s+i\s+have\s+time\s+)?", "", text, flags=re.I)
    lines = await IQ.answer(ctx.account, text, GW.NOW())
    return {"answer": lines, "say": "\n".join(lines), "how": "Say the answer as it is — its figures and sources are the tool's."}


def _kind_of(what: str) -> str:
    return "restaurant" if re.search(r"restaurant|dinner|lunch|table|bar|tapas|cena|comida", what or "", re.I) else "other"


_ASKS_TO_BOOK = re.compile(r"(?i)\b(book|reserv|reserve|table for)\w*")
_PARK_WORDS = re.compile(r"(?i)\b(later|not (?:book|ready)|don'?t book|do not book|without booking|just (?:add|save|keep)|save it|park|add it to)\b")


def _asked_to_book(ctx) -> bool:
    """Sasha 253 · found by EU's scoreboard: "book it, but don't send anything to them" was PARKED (save_for_later) — "book it" is
    always hold_venue (it sends nothing without their yes). Parking is only for their own words to park."""
    said = str(getattr(ctx, "user_said", "") or "")
    return bool(_ASKS_TO_BOOK.search(said)) and not _PARK_WORDS.search(said)


_BOOK_NOT_PARK = ("they asked to BOOK it: call hold_venue (it prepares the booking and sends nothing without their yes — "
                  "the prefilled form is theirs to confirm). Park only when they say so.")


async def add_to_trip(ctx, a: dict) -> dict:
    """G10 · a place they found, added to a day of their trip — NOT booked (wa_brain.add_to_trip, the old flow's own: a plan
    item on that day, "picked; not booked yet"). Booking it later is the venue's own route: hold_venue → their yes → book_venue."""
    if _asked_to_book(ctx):
        raise _err("book_not_park", _BOOK_NOT_PARK)
    from booking_signer import guest_whatsapp as GW, wa_brain as WB
    name, what = str(a.get("name") or "").strip(), str(a.get("what") or "restaurant").strip()
    day, city = str(a.get("day") or "").strip()[:10], str(a.get("city") or "").strip()
    if day and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day):
        raise _err("date_invalid", "day is YYYY-MM-DD")
    now = GW.NOW()
    c = await WB.context(ctx.account, " ".join(x for x in (day, city) if x), _kind_of(what), now)
    if c.get("ask"):
        raise _err("which_day", "which day or city of their trip? its cities: " + ", ".join(c["ask"]))
    if not c.get("trip") or c.get("home"):
        raise _err("no_trip", "they have no trip on now — book it (hold_venue) or save it for later (save_for_later)")
    if day and c["trip"].get("date") != day:
        raise _err("day_not_on_trip", f"{day} isn't a day of their trip “{c['trip'].get('title') or 'the trip'}” — ask which day")
    out = GW.Out()
    await WB.add_to_trip({"account": ctx.account, "out": out, "st": {}, "now": now},
                         {"find": {"what": what, "where": c.get("where"), "trip": c["trip"]}, "draft": {}},
                         {"name": name, "place_id": a.get("place_id")})
    said = out.said()
    added = said.startswith("Added ")
    return {"added": added, "say": said, **({"trip_day": c["trip"].get("date"), "place_id": a.get("place_id")} if added else {}),
            "how": ("Say it's on that day of their trip and NOT booked. To book it later, read it back with hold_venue (this place, "
                    "that day, the time they say) and book only on their yes." if added else "Say it wasn't added; nothing was booked.")}


async def save_for_later(ctx, a: dict) -> dict:
    """G13 · "save it for later": parked UNBOOKED on their trip tab / Requests (wa_brain.saved_words → save_item, the old flow's
    park). Nothing is booked, nothing is contacted."""
    if _asked_to_book(ctx):
        raise _err("book_not_park", _BOOK_NOT_PARK)
    from booking_signer import wa_brain as WB
    name = str(a.get("name") or "").strip()
    if not name:
        raise _err("name_missing", "what should be saved? (the place, or what they asked for)")
    at, city = str(a.get("when") or "").strip() or None, str(a.get("city") or "").strip() or None
    if at and not re.fullmatch(r"\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2})?", at):
        raise _err("date_invalid", "when is YYYY-MM-DD or YYYY-MM-DDTHH:MM")
    said = await WB.saved_words(ctx.account, name, at, city)
    return {"saved": said.startswith("Saved"), "say": said, "how": "Say this line as it is."}


async def call_again(ctx, a: dict) -> dict:
    """Sasha 269 · "try once more" / "call them again" in WORDS (the card's tap goes straight to venue_calls.again, no model between): the
    booking's act → venue.call_again reason person_asked, under its ONE approval (no new card, nothing asked again) → Sasha dials only
    that call_plan. Asked twice: the same call. Said: the act's own `say`."""
    from agapi import venue_calls as VC, venue_submit as VS
    from app.agent import voice as V
    acts = [x for x in await VS.acts_of(ctx.account) if x.get("route") == "call" and not x.get("cancels")]
    want = str(a.get("act_id") or "").strip()
    name = re.sub(r"\W+", " ", str(a.get("venue") or "").lower()).strip()
    act = next((x for x in acts if want and x.get("act_id") == want), None) \
        or next((x for x in reversed(acts) if name and name in re.sub(r"\W+", " ", str(x.get("venue") or "").lower())), None) \
        or next((x for x in reversed(acts) if x.get("state") == "no_answer"), None)
    if not act:
        return {"status": "no_act", "say": V.NO_CALL_OPEN, "how": "Say `say` as it is."}
    got = await VC.again(ctx.account, act["act_id"], "person_asked")
    return {**got, "venue": act.get("venue"), "booked": False, "how": "Say `say` word for word — nothing else."}


def tools() -> List[dict]:
    from agapi.v0 import _t
    appr = {"approval": {"type": "object", "properties": {"said": {"type": "string"}}, "description": "the person's own words (filled by the caller)"}}
    return [
        _t("note_rental", "Pacioli", note_rental, "Note a car rental they've booked elsewhere (company, country, where, pickup day and "
           "time) so it's in My plans. Nothing is sent anywhere; you don't book rentals.",
           {"rental_company": {"type": "string"}, "country": {"type": "string", "description": "ISO-2, e.g. PT"}, "place": {"type": "string"},
            "pickup_date": {"type": "string", "description": "YYYY-MM-DD"}, "pickup_time": {"type": "string", "description": "HH:MM"},
            "days": {"type": "integer", "minimum": 1, "maximum": 90}}, ["rental_company", "country", "pickup_date"],
           {"type": "object", "properties": {"saved": {"type": "boolean"}}}, ["rental_invalid"]),
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
           "YYYY-MM-DD, leg out/back: Duffel's own quote; some fares can't be changed — say so plainly), hotel (nights and/or check_in: by the hotel's own "
           "route; its answer comes back on the booking). Name the booking by its id from my_plans. FIRST call: the read-back; after their yes in a LATER turn, call again to do it. A flight's result lists the "
           "times Duffel offered that day (options): if they pick another, call again with its new_time (HH:MM) or change_offer_id "
           "— only those times exist; never say one of them can't be found.",
           {"what": {"enum": ["venue", "flight", "hotel"]}, "id": {"type": "string"}, "venue": {"type": "string"}, "name": {"type": "string"},
            "new_time": {"type": "string", "description": "HH:MM — a venue's new time, or the flight time they picked from the options"},
            "change_offer_id": {"type": "string", "description": "a flight option's id, from the options"},
            "new_party": {"type": "integer", "minimum": 1, "maximum": 20},
            "new_date": {"type": "string"}, "leg": {"enum": ["out", "back"]},
            "nights": {"type": "integer", "minimum": 1, "maximum": 60, "description": "a hotel stay's new number of nights"},
            "check_in": {"type": "string", "description": "YYYY-MM-DD — a hotel stay's new first night (\"arrive a day later\")"}, **appr}, ["what"],
           {"type": "object", "properties": {"status": {"type": "string"}}},
           ["booking_unknown", "no_explicit_yes", "change_unavailable", "not_changeable", "date_missing", "what_invalid", "which_flight", "which_booking"], austen=True),
        _t("cancel_booking", "Austen", cancel_booking, "Cancel a hotel stay or a flight (a restaurant or spa: cancel_venue). FIRST call: the "
           "read-back (a flight's refund is Duffel's own quote); after their explicit yes in a LATER turn, call again to cancel. "
           "what=plan drops a HELD trip (waiting for payment, nothing booked): its payment closed, nothing charged.",   # Sasha 246
           {"what": {"enum": ["hotel", "flight", "plan"]}, "id": {"type": "string"}, "name": {"type": "string"},
            "leg": {"enum": ["out", "back"], "description": "a flight: the trip's outbound or its return"}, **appr}, ["what"],
           {"type": "object", "properties": {"status": {"type": "string"}}},
           ["booking_unknown", "no_explicit_yes", "cancel_unavailable", "not_cancellable", "what_invalid", "nothing_held", "which_flight", "which_booking"], austen=True),
        # Sasha 253 · the WhatsApp capabilities in the one brain (S252 audit G1 · G9 · G10 · G13)
        _t("file_confirmation", "Pacioli", file_confirmation, "They forwarded or pasted a venue's booking confirmation (its email or "
           "message): file it on the ONE booking it names (their reference, or the venue's name and the day), read with the field "
           "checks — 'confirmed in writing' only when it restates the day, time and number. Pass the text as they sent it.",
           {"text": {"type": "string", "maxLength": 8000, "description": "the venue's message, as they sent it"}}, [],
           {"type": "object", "properties": {"filed": {"type": "boolean"}}}, []),
        _t("time_between", "Magellan", time_between, "'Do I have time to drive / fly to X between A and B (on a day)?' — answered from "
           "their bookings with Google's Routes API (driving) or Duffel's TEST schedules (flying). Pass the question as they asked it.",
           {"question": {"type": "string", "maxLength": 300}}, ["question"], {"type": "object", "properties": {"answer": {"type": "array"}}}, []),
        _t("add_to_trip", "Magellan", add_to_trip, "ONLY when they ask to add it without booking. Add a place they found to a day of their current trip WITHOUT booking it (it shows "
           "on that day as 'not booked yet'). To book it later: hold_venue for that place and day, then their yes.",
           {"name": {"type": "string"}, "place_id": {"type": "string"}, "what": {"type": "string", "description": "e.g. restaurant, spa"},
            "day": {"type": "string", "description": "YYYY-MM-DD, a day of the trip"}, "city": {"type": "string"}}, ["name"],
           {"type": "object", "properties": {"added": {"type": "boolean"}}}, ["no_trip", "which_day", "day_not_on_trip", "date_invalid"]),
        _t("save_for_later", "Pacioli", save_for_later, "'Save it for later' / 'not ready to book yet' — only their own words to park; 'book it' (even 'don't send anything yet') is hold_venue: park it UNBOOKED in their trip "
           "tab and Requests (nothing booked, nothing contacted).",
           {"name": {"type": "string", "maxLength": 200}, "when": {"type": "string", "description": "YYYY-MM-DD or YYYY-MM-DDTHH:MM, if said"},
            "city": {"type": "string"}}, ["name"], {"type": "object", "properties": {"saved": {"type": "boolean"}}}, ["name_missing", "date_invalid"]),
        _t("call_again", "Austen", call_again, "ONLY after a call that wasn't picked up, when they say 'try once more' / 'call them again': "
           "the SAME booking's call, under the yes they already gave (never a new read-back, never ask again). The engine decides when "
           "(never sooner than 30 minutes) and how many; say its `say` word for word.",
           {"venue": {"type": "string"}, "act_id": {"type": "string"}}, [],
           {"type": "object", "properties": {"status": {"type": "string"}, "say": {"type": "string"}}}, ["no_act"]),
    ]


__all__ = ["my_plans", "running_late", "change_booking", "cancel_booking", "plans_of", "tools", "file_confirmation", "time_between",
           "add_to_trip", "save_for_later", "call_again"]
