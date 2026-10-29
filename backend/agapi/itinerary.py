"""Sasha 300 · THE ONE ITINERARY — every booking on the account, from request to after the visit, built HERE and nowhere else.

  THE RECORD   a venue booking lives on AgAPI's booking record: its act (act_id — venue_sent / venue_requests). CR 132: ONE read of
               it — venue.bookings (agapi.venue_submit.agapi_bookings) — gives every act's state, route, place and map link, how it is
               managed and an open change; a hand-over with a prepared booking is an act there too (venue.handed_over, written by
               agapi.venues.note_prepared). Sasha keeps a POINTER (s2_memory "venue_acts"), never a second truth about its state.
               An AgAPI without venue.bookings: the acts through venue.booking_status, as before. A hand-over with no prepared
               booking (THE FLOOR, a page with no slot) stays the hand-over's row (agapi.venues.prepared_pages).
               A booking made on the old ladder (/next: the signer's trip_items) is read from its own record, as before.
  THE VIEW     of(account) → each booking's status (asked · confirmed · offered another time · declined · cancelled · handed over),
               venue, day, time, people, the ROUTE it went by, the venue's own words (untrusted data), its map link, its trip.
               my_plans (chat, voice, WhatsApp), the Trip tab (extra_reservations) and the reminders (upcoming) read it.
  FINE PRINT   Sasha 301 · each venue row's `terms` (the venue's own sentences: a deposit, a cancellation term with "by <date/time>",
               a no-show charge, a time limit — agapi/booking_terms.py, read from the row's words, no store of its own) and each
               booking's `perks` (his Keep's loyalty numbers and card perks that apply, masked). booking_fine_print reads them here.
  MANAGE       manage_of(row) — how a change, a cancellation or "running late" goes for THIS booking: by the route it was made on,
               never chosen again. The one place that says so; s2_manage and venues.cancel_venue ask it.
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime, time as dtime, timedelta
from typing import Any, Dict, List, Optional
from urllib.parse import quote, urlsplit

log = logging.getLogger("agapi.itinerary")

# ── the route a booking went by, and its words (one owner) ─────────────────────────────────────────────────────────────────
#: never a channel's name (her voice, Sasha 249: the model reads these too) — the platform's name is only its button's label, never said
ROUTE_WORDS = {"email": "by email", "kanoe_whatsapp": "by message, from Kanoe", "your_whatsapp": "from your own phone",
               "platform": "on their booking platform", "their_page": "on their own page", "call": "by phone", "form": "on their booking form"}
#: how a change / cancellation / running late goes, per route — the booking's OWN route, never another
#:   message      AgAPI writes and sends it on the act's own channel (venue.change_booking / venue.cancel_booking), on his yes
#:   call         AgAPI's call act (the same op, route call), on his yes
#:   your_whatsapp  he sends it from his own WhatsApp, in his chat with them (CR 131 (d): AgAPI writes the words)
#:   their_page   their own page (the platform's, their form's): he changes or cancels it there — she opens it
#:   ladder       a booking on the old ladder: its own record's path (booking_signer's notice / cancel routes), as before
MANAGE = {"email": "message", "kanoe_whatsapp": "message", "call": "call", "your_whatsapp": "your_whatsapp", "platform": "their_page",
          "their_page": "their_page", "form": "their_page"}

# ── the status, in the ticket's words (the WORDS are s2_status's — one place) ──────────────────────────────────────────────────
#: a status from any record → the itinerary's
_ACT = {"requested": "asked", "confirmed": "confirmed", "proposed": "offered", "declined": "declined", "stopped": "declined",
        "cancelled": "cancelled", "failed": "failed", "calling": "calling", "no_answer": "no_answer"}
_LADDER = {"confirmed": "confirmed", "guest_booked": "booked_by_you", "proposed": "offered", "quoted": "offered", "declined": "declined",
           "escalated": "declined", "cancelled": "cancelled", "failed": "failed"}
_WORDS_KEY = {"asked": "requested", "confirmed": "confirmed", "offered": "proposed", "declined": "declined", "cancelled": "cancelled",
              "failed": "failed", "calling": "calling", "no_answer": "no_answer", "booked_by_you": "by_you"}
_PLATFORM_HOSTS = ("covermanager", "thefork", "eltenedor", "opentable", "resy", "sevenrooms", "quandoo", "tock", "bookatable",
                   "dish.co", "restoo", "fresha", "treatwell", "booksy")


def words(status: str, route: Optional[str] = None) -> str:
    from agapi import s2_status as ST
    if status == "handed_over":
        return ST.WORDS["your_whatsapp"] if route == "your_whatsapp" else ST.WORDS["prepared"]
    return ST.WORDS.get(_WORDS_KEY.get(status, "requested"), ST.WORDS["requested"])


def route_words(route: str, platform: Optional[str] = None) -> str:
    return ROUTE_WORDS.get(route, "")


def map_url(name: Optional[str], place_id: Optional[str]) -> Optional[str]:
    """The venue on Google Maps: a search link by its place ID (allowed to keep; no API call, nothing of Google's stored)."""
    if not place_id:
        return None
    return f"https://www.google.com/maps/search/?api=1&query={quote(str(name or 'venue'))}&query_place_id={quote(str(place_id))}"


def _platform(url: str) -> Optional[str]:
    host = (urlsplit(url or "").hostname or "").lower()
    if not host:
        return None
    try:
        from booking_signer import venue_read as VR
        hit = VR.platform_of(url)
        if hit:
            return hit
    except Exception:
        pass
    return next((h.split(".")[0].capitalize() for h in _PLATFORM_HOSTS if h in host), None)


def handover_route(r: dict) -> str:
    """A hand-over's route: his own WhatsApp (a wa.me link), a platform (its link's record, or its page), else their own page."""
    if r.get("route") in ROUTE_WORDS:
        return str(r["route"])
    url = str(r.get("url") or "")
    if re.match(r"https?://(?:wa\.me|api\.whatsapp\.com|(?:www\.)?whatsapp\.com)/", url):
        return "your_whatsapp"
    if r.get("link_id") or is_platform(r.get("platform")) or _platform(url):
        return "platform"
    return "their_page"


#: the platforms as the person reads them (a decision's channel or its button may say "CoverManager booking widget", "Book on TheFork")
_PLATFORM_NAMES = {"covermanager": "CoverManager", "thefork": "TheFork", "eltenedor": "ElTenedor", "opentable": "OpenTable", "resy": "Resy",
                   "sevenrooms": "SevenRooms", "quandoo": "Quandoo", "bookatable": "Bookatable", "restoo": "Restoo", "fresha": "Fresha",
                   "treatwell": "Treatwell", "booksy": "Booksy"}


def platform_name(*said: Any) -> Optional[str]:
    """The first of these words that names a booking platform, as the person reads it — else None."""
    for x in said:
        n = re.sub(r"[^a-z]", "", str(x or "").lower())
        hit = next((v for k, v in _PLATFORM_NAMES.items() if n and k in n), None)
        if hit:
            return hit
    return None


def is_platform(name: Any) -> bool:
    return platform_name(name) is not None


def act_route(a: dict) -> str:
    """An act's route — the channel AgAPI sent it on (venue_submit keeps it), a call act's call, else their form (zero-touch)."""
    if a.get("route") == "call":
        return "call"
    if a.get("channel") == "email":
        return "email"
    if a.get("channel") == "whatsapp":
        return "kanoe_whatsapp"
    return "form"


#: Sasha 302 · the states in which an act carries the VENUE's words (an answer) — before one, what the record holds is AgAPI's own note
ANSWERED = ("confirmed", "offered", "declined", "cancelled")

_LADDER_ROUTE = {"form": "form", "phone": "call", "email": "email", "link": "platform"}


def _trip_of(plans: List[dict], day: Optional[str]) -> Optional[dict]:
    """The trip a booking without its own trip id sits in: the one whose dates hold its day (the newest first)."""
    if not day:
        return None
    for p in plans:
        s, e = str(p.get("start") or "")[:10], str(p.get("end") or p.get("start") or "")[:10]
        if s and s <= day[:10] <= (e or s):
            return p
    return None


# ── THE ROWS ──────────────────────────────────────────────────────────────────────────────────────────────────────────────

#: CR 132 · AgAPI's record (venue.bookings) in the itinerary's words: its route, and its state
_AG_ROUTE = {"email": "email", "whatsapp": "kanoe_whatsapp", "whatsapp_person": "your_whatsapp", "platform": "platform",
             "their_page": "their_page", "call": "call", "form": "form"}
_AG_STATE = {"sent": "asked", "confirmed": "confirmed", "proposed": "offered", "declined": "declined", "cancelled": "cancelled",
             "failed": "failed", "calling": "calling", "no_answer": "no_answer", "handed_over": "handed_over", "sent_by_person": "asked",
             "booked_by_person": "booked_by_you", "opted_out": "declined"}


def _from_record(g: dict, a: Optional[dict] = None) -> dict:
    """CR 132 · one booking on AgAPI's record (venue.bookings) as an itinerary row — AgAPI's state, route, slot, place and change, as given."""
    v, at = g.get("venue") or {}, str(g.get("at") or "")
    ref = str(g.get("external_ref") or "")
    trip = ref[5:] if ref.startswith("trip:") else (a or {}).get("trip_id")
    return {"id": g["act_id"], "source": "act", "act_id": g["act_id"], "route": _AG_ROUTE.get(str(g.get("route") or ""), "their_page"),
            "status": _AG_STATE.get(str(g.get("state") or ""), "asked"), "venue": v.get("name") or (a or {}).get("venue"),
            "date": at[:10] or None, "time": at[11:16] or None, "party": g.get("party"), "type": "restaurant",
            **({"place_id": v["place_id"]} if v.get("place_id") else {}), **({"map_url": v["maps_url"]} if v.get("maps_url") else {}),
            **({"address": v["address"]} if v.get("address") else {}), **({"trip_id": trip} if trip else {}),
            **({"platform": g["platform"]} if g.get("platform") else {}), **({"url": g["manage_url"]} if g.get("manage_url") else {}),
            **({"reference": g["reference"]} if g.get("reference") else {}),
            **({"venue_said": {"untrusted_text": str((g.get("venue_words") or {}).get("untrusted_text") or "")[:160]}}
               if (g.get("venue_words") or {}).get("untrusted_text") else {}),
            # Sasha 302 · the terms read the record's words IN FULL (the 160 above is the line shown): a cut sentence is never a term
            **({"terms_text": str((g.get("venue_words") or {}).get("untrusted_text") or "")[:4000]}
               if (g.get("venue_words") or {}).get("untrusted_text") else {}),
            **({"type": "hotel"} if (a or {}).get("stay") or isinstance(g.get("stay"), dict) else {}),   # Sasha 302 · a stay act (CR 102) is a hotel
            # Sasha 306 · CR 137: the stay AS IT STANDS on AgAPI's record (check_in, check_out, nights — never computed here) and the
            # hotel's answer to a change, in its own words (answers.change)
            **({"stay": g["stay"]} if isinstance(g.get("stay"), dict) else {}),
            **({"change_answer": _answer(g["answers"]["change"])} if isinstance((g.get("answers") or {}).get("change"), dict) else {}),
            **({"change": g["change"]} if g.get("change") else {})}


def _answer(c: dict) -> dict:
    """Sasha 306 · answers.change as the itinerary shows it: its state, what was asked, and the venue's words (quoted, untrusted)."""
    w = (c.get("venue_words") or {}).get("untrusted_text") if isinstance(c.get("venue_words"), dict) else None
    return {"state": c.get("state"), **({"asked": c["asked"]} if c.get("asked") else {}),
            **({"venue_said": {"untrusted_text": str(w)[:400]}} if w else {})}


async def venue_rows(account: str, include_cancelled: bool = True) -> List[dict]:
    """Every venue booking on the account — AgAPI's record (venue.bookings: CR 132), the old ladder's, then the hand-overs on neither."""
    from agapi import venues as VN, venue_submit as VS
    acts = {a.get("act_id"): a for a in await VS.acts_of(account)}
    record = await VS.agapi_bookings(account)   # None: an AgAPI without venue.bookings — the acts as before
    on_agapi = {g["act_id"]: g for g in record or [] if g.get("act_id")}
    records = await VN.venue_bookings(account, include_cancelled=True)
    out: List[dict] = []
    today = date.today().isoformat()
    for g in on_agapi.values():   # CR 132 · AgAPI's record is the truth for every booking on it (the hand-overs too); from today on
        if (str(g.get("at") or "")[:10] or today) >= today:
            out.append(_from_record(g, acts.get(g["act_id"])))
    for b in records:
        if b.get("act_id") and b["act_id"] in on_agapi:
            continue   # on AgAPI's record: its row is above
        if b.get("act_id"):
            a = acts.get(b["act_id"]) or {}
            route = act_route({**a, **b})
            status = _ACT.get(str(b.get("status") or ""), "asked")
            row = {"id": b["act_id"], "source": "act", "act_id": b["act_id"], "route": route, "status": status,
                   **({"place_id": a["place_id"]} if a.get("place_id") else {}), **({"trip_id": a["trip_id"]} if a.get("trip_id") else {}),
                   **({"stay": True} if a.get("stay") or b.get("stay") else {})}   # Sasha 302 · a hotel stay's act (CR 102)
        else:
            route = _LADDER_ROUTE.get(str(b.get("channel") or "form"), "form")
            status = _LADDER.get(str(b.get("status") or ""), "asked")
            row = {"id": b["trip_item_id"], "source": "ladder", "trip_item_id": b["trip_item_id"], "route": route, "status": status,
                   **({"trip_id": b["trip_id"]} if b.get("trip_id") else {}), **({"address": b["address"]} if b.get("address") else {})}
        kind = "hotel" if row.pop("stay", None) else b.get("type")
        if row["source"] == "act" and status not in ANSWERED:   # Sasha 302 · found live: "They said: Emailed … — sandbox: captured" was AgAPI's
            b = {k: v for k, v in b.items() if k != "venue_said"}  # note on a sent request, not the venue's words (CR 132's venue.bookings rule)
        out.append({**row, "venue": b.get("venue"), "date": b.get("date"), "time": b.get("time"), "party": b.get("party"),
                    "type": kind, **({"reference": b["reference"]} if b.get("reference") else {}),
                    **({"venue_said": b["venue_said"]} if b.get("venue_said") else {}),
                    **({"venue_words": b["venue_words"]} if b.get("venue_words") and not b.get("act_id") else {}),   # 301 · the ladder's own
                    **{k: b[k] for k in ("cancel", "change", "country") if b.get(k)}})
    on_record = {(VN._base(r.get("venue") or ""), str(r.get("date") or "")) for r in out}
    for h in await VN.prepared_pages(account):
        if (VN._base(h.get("venue") or ""), str(h.get("date") or "")) in on_record:
            continue   # the booking is on a record: that row is it
        route = handover_route(h)
        booked = h.get("outcome") in VN.WORD_BOOKED
        out.append({"id": "hand:" + VN._word_key(h), "source": "handover", "key": VN._word_key(h), "route": route,
                    "status": "booked_by_you" if booked else "handed_over", "venue": h.get("venue"), "date": h.get("date") or None,
                    "time": h.get("time") or None, "party": h.get("party") or None, "type": "restaurant",
                    **({"url": h["url"]} if h.get("url") else {}), **({"link_id": h["link_id"]} if h.get("link_id") else {}),
                    **({"platform": platform_name(h.get("platform")) or _platform(str(h.get("url") or ""))} if route == "platform" else {}),
                    **({"place_id": h["place_id"]} if h.get("place_id") else {})})
    for r in out:
        r["terms"] = row_terms(r)   # Sasha 301 · the venue's own terms, from its own words on this row
        r["status_words"] = words(r["status"], r["route"])
        r["route_words"] = route_words(r["route"], r.get("platform"))
        r["manage"] = "ladder" if r["source"] == "ladder" else MANAGE.get(r["route"], "their_page")
        m = map_url(r.get("venue"), r.get("place_id"))
        if m:
            r["map_url"] = m
    return [r for r in out if include_cancelled or r["status"] != "cancelled"]


async def of(account: str) -> List[dict]:
    """THE itinerary: every booking (venues, flights, stays, the rentals they told her about), upcoming first, each in its trip."""
    from booking_signer import basket as BK, plan_store as PS
    plans = await PS.plans(account)
    out: List[dict] = []
    for v in await venue_rows(account):
        when = f"{v['date']}T{v['time']}" if v.get("date") and v.get("time") else (v.get("date") or "")
        trip = next((p for p in plans if p.get("trip_id") == v.get("trip_id")), None) or _trip_of(plans, v.get("date"))
        out.append({"kind": _venue_kind(v.get("type")), "title": v["venue"], "when": when, "status": v["status"],
                    "status_words": v["status_words"], "route": v["route"], "route_words": v["route_words"], "manage": v["manage"],
                    "party": v.get("party"), "id": v["id"], "source": "venue",
                    **{k: v[k] for k in ("reference", "venue_said", "map_url", "address", "platform", "url", "cancel", "change", "terms",
                                         "change_answer") if v.get(k)},
                    **({k: v["stay"][k] for k in ("check_in", "check_out", "nights") if v["stay"].get(k) is not None}   # Sasha 306 · AgAPI's
                       if isinstance(v.get("stay"), dict) else {}),
                    **({"trip_id": trip["trip_id"], "trip": trip.get("title")} if trip else {})})
    seen, tied = set(), set()
    for p in plans:
        # Sasha 305 · a ticketed flight is its Duffel order read now (basket.live), never the snapshot copied at booking; one cancelled
        # after ticketing stays on, said cancelled
        rows = await BK.items(account, p["trip_id"], ("booked", "pending_payment", "cancelled"))
        rows = await BK.live([r for r in rows if r["state"] != "cancelled" or (r["kind"] == "flight" and r.get("order_id"))])
        for r in rows:
            if r["id"] in seen:
                continue
            seen.add(r["id"])
            if r.get("trip_item_id"):
                tied.add(str(r["trip_item_id"]))
            s = r.get("snapshot") or {}
            status = {"booked": "booked", "cancelled": "cancelled"}.get(r["state"], "awaiting payment")
            if r["kind"] == "flight":
                title = " ".join(x for x in (s.get("owner"), s.get("flights")) if x) or "Flight"
                where = f"{s.get('from') or ''} → {s.get('to') or ''}".strip(" →")
                out.append({"kind": "flight", "title": title, "when": str(s.get("departs") or r.get("day") or ""), "where": where,
                            "status": status, **({"reference": r["booking_reference"]} if r.get("booking_reference") else {}),
                            "id": str(r["id"]), "order_id": r.get("order_id"), "trip": p.get("title"), "trip_id": p["trip_id"],
                            "source": "flight", **({"live": r["live"]} if "live" in r else {}),
                            **({"legs": len(s["legs"])} if s.get("legs") else {}),
                            **({"status_words": f"booked — not re-read from the airline just now ({r['live_why']})"}
                               if r.get("live") is False else {})})
            elif r["kind"] == "stay":
                nights = int(s.get("nights") or 1)
                out.append({"kind": "hotel", "title": s.get("name") or s.get("hotel") or "Your stay", "when": str(r.get("day") or ""),
                            "where": s.get("city") or "", "nights": nights, "status": status,
                            **({"reference": r["booking_reference"]} if r.get("booking_reference") else {}),
                            "id": str(r["id"]), "trip_item_id": str(r["trip_item_id"]) if r.get("trip_item_id") else None,
                            "trip": p.get("title"), "trip_id": p["trip_id"], "source": "hotel"})
    # Sasha 305 · found live: a flight booked from the basket ALSO left the old ladder's trip item, listed again as a "dinner" — one booking,
    # one row: the basket's (its Duffel order, read now) is it
    out = [i for i in out if not (i["source"] == "venue" and str(i["id"]) in tied)]
    from booking_signer import rental_moments as RM   # Sasha 227 · the rentals they told her about
    for r in await RM.rentals(account):
        out.append({"kind": "car", "title": f"{r['rental_company']} car rental", "when": r["pickup_date"] + (f"T{r['pickup_time']}" if r.get("pickup_time") else ""),
                    "where": r.get("place") or r.get("country") or "", "status": "noted (booked elsewhere)", "id": r["id"], "source": "rental"})
    wallet = await _wallet(account)   # Sasha 301 · his loyalty numbers and card perks that apply to each booking (masked)
    if wallet:
        from agapi import booking_terms as BT
        for i in out:
            p = BT.perks_for(i["kind"], i.get("title") or "", wallet)
            if p:
                i["perks"] = p
    today = date.today().isoformat()
    keep = [i for i in out if (i["when"] or today)[:10] >= today or
            (i["kind"] == "hotel" and i["when"] and stay_end(i) > today)]
    return sorted(keep, key=lambda i: (i["when"] + ("T15:00" if i["kind"] == "hotel" and len(i["when"]) == 10 else "")) or "9999")   # a stay from check-in


def stay_end(i: dict) -> str:
    """Sasha 306 · a stay's check-out: AgAPI's record's own (check_out) when it has one; Sasha's own TEST stays (no record but their
    basket row) from their check-in and nights, as before."""
    if i.get("check_out"):
        return str(i["check_out"])[:10]
    return (date.fromisoformat(str(i["when"])[:10]) + timedelta(days=i.get("nights") or 1)).isoformat()


def start_of(r: dict) -> Optional[datetime]:
    """A booking's start in its own time zone (its country's), or None without a day and a time."""
    from zoneinfo import ZoneInfo
    try:
        return datetime.combine(date.fromisoformat(str(r["date"])[:10]), dtime.fromisoformat(str(r["time"])[:5]),
                                tzinfo=ZoneInfo(r.get("timezone") or _zone_of(r.get("country"))))
    except Exception:
        return None


#: an act's words are cut at this many characters on its record (venue_submit._words): a sentence that reaches it unfinished is dropped
ACT_WORDS_CUT = 240


def row_terms(r: dict) -> List[dict]:
    """Sasha 301 · the venue's own terms on this booking: from the VENUE's words only — an act's reply (venue_said), the old ladder's
    venue_words (its venue_said is Sasha's status sentence, never read for terms), a reservation row's venue_words."""
    from agapi import booking_terms as BT
    if r.get("source") == "ladder" or (r.get("source") is None and r.get("venue_words")):
        text = r.get("venue_words")
        cut = None
    elif r.get("terms_text"):   # Sasha 302 · AgAPI's record (venue.bookings): its words in full
        text, cut = r["terms_text"], None
    else:
        said = r.get("venue_said")
        text = said.get("untrusted_text") if isinstance(said, dict) else None
        cut = ACT_WORDS_CUT if r.get("source") == "act" else None
    return BT.terms_of(text, start_of(r), cut_at=cut) if text else []


async def _wallet(account: str) -> List[dict]:
    from agapi import s2_keep as KEEP
    return await KEEP.wallet(account)


def _venue_kind(t: Optional[str]) -> str:
    t = (t or "").lower()
    if t in ("hotel", "stay"):   # Sasha 302 · a hotel stay booked as an act (CR 102)
        return "hotel"
    return "spa" if re.search(r"spa|massage|beauty|salon|nail|hair|wellness", t) else "dinner"


# ── THE TRIP TAB and THE REMINDERS: the same rows, in the shape their views already draw ─────────────────────────────────────

_RESERVATION_STATUS = {"asked": "requested", "confirmed": "confirmed", "offered": "proposed", "declined": "declined",
                       "cancelled": "cancelled", "failed": "failed", "calling": "requested", "no_answer": "requested",
                       "booked_by_you": "guest_booked", "handed_over": "link_sent"}


def as_reservation(r: dict, trip_id: Optional[str] = None) -> dict:
    """An itinerary row (not the old ladder's own) as a /api/booking/reservations row — the Trip tab and the reminders draw it."""
    said = (r.get("venue_said") or {}).get("untrusted_text") if isinstance(r.get("venue_said"), dict) else None
    return {"id": r["id"], "trip_id": trip_id or r.get("trip_id"), "intent_id": None, "channel": r["route"], "venue": r.get("venue"),
            "date": r.get("date"), "time": r.get("time"), "timezone": _zone_of(r.get("country")), "party": r.get("party"),
            "status": _RESERVATION_STATUS.get(r["status"], "requested"), "status_words": r["status_words"],
            "route_words": r["route_words"], "booking_reference": r.get("reference"), "sasha_reference": None, "receipt": None,
            "venue_words": said, "type": r.get("type") or "restaurant", "address": r.get("address"), "map_url": r.get("map_url"),
            "itinerary": r["source"], "manage": r["manage"], **({"url": r["url"]} if r.get("url") else {}),
            "terms": r.get("terms") or []}   # Sasha 301 · the venue's own terms (the Trip tab draws them; cancel_by reads them)


def _zone_of(country: Optional[str]) -> str:
    try:
        from booking_signer import venue_read as VR
        return (VR.COUNTRIES.get(str(country or "").upper()) or (None, None, None, "Europe/Madrid"))[3]
    except Exception:
        return "Europe/Madrid"


async def extra_reservations(account: str) -> List[dict]:
    """The bookings the old ladder's /reservations doesn't hold (AgAPI's acts, the hand-overs), as its rows, each in its trip —
    added to the Trip tab's rows so no booking is missing from its trip's itinerary."""
    from booking_signer import plan_store as PS
    try:
        plans = await PS.plans(account)
        rows = [r for r in await venue_rows(account) if r["source"] != "ladder"]
    except Exception as e:   # the extra rows unreadable: the view still shows the ladder's (logged, never silent)
        log.warning("[itinerary] extra rows not read: %s", type(e).__name__)
        return []
    out = []
    for r in rows:
        trip = next((p for p in plans if p.get("trip_id") == r.get("trip_id")), None) or _trip_of(plans, r.get("date"))
        out.append(as_reservation(r, trip["trip_id"] if trip else None))
    return out


def with_terms(rows: List[dict]) -> List[dict]:
    """Sasha 301 · reservation rows (the old ladder's /reservations, as the Trip tab and the reminders read them), each with the venue's
    own terms from its own words — the same reader as every itinerary row (row_terms)."""
    return [r if "terms" in r else {**r, "terms": row_terms(r)} for r in rows]


async def upcoming(account: str, ladder_rows: List[dict]) -> List[dict]:
    """The reminders' bookings: the old ladder's upcoming rows (as they were read) and the itinerary's other rows still to come."""
    today = date.today().isoformat()
    extra = [r for r in await extra_reservations(account) if r.get("date") and r["date"] >= today
             and r["status"] not in ("cancelled", "declined", "failed")]
    return with_terms(ladder_rows) + extra   # Sasha 301 · the ladder's rows: their terms from their venue_words


# ── MANAGE: by the booking's own route ───────────────────────────────────────────────────────────────────────────────────────

async def find(account: str, a: dict, kinds: tuple = ("act", "ladder", "handover")) -> dict:
    """The booking a change / cancellation / running late means: its id (act_id, trip_item_id or the hand-over's), else the venue
    named, else today's (or the only one). Several match → which one (raised, never a guess)."""
    from agapi.v0 import ToolError
    rows = [r for r in await venue_rows(account, include_cancelled=False) if r["source"] in kinds]
    rid = a.get("act_id") or a.get("trip_item_id") or a.get("id")
    name = (a.get("venue") or "").lower().strip()
    hit = [r for r in rows if rid and rid in (r["id"], r.get("act_id"), r.get("trip_item_id"))]
    if not hit and name:
        hit = [r for r in rows if name in (r.get("venue") or "").lower()]
    if not hit and not rid and not name:
        today = date.today().isoformat()
        hit = [r for r in rows if r.get("date") == today] or (rows if len(rows) == 1 else [])
    if not hit:
        raise ToolError("booking_unknown", "which booking? my_plans lists them (with their ids)")
    if len(hit) > 1 and not rid:
        day = str(a.get("date") or "")[:10]
        hit = [r for r in hit if r.get("date") == day] or hit
        if len(hit) > 1:
            raise ToolError("which_booking", "more than one booking matches — ask which one (" + "; ".join(
                f"{r['venue']} {r.get('date')} {r.get('time') or ''} · id {r['id']}" for r in hit) + ") and call again with its id")
    return hit[0]


def page_answer(row: dict, kind: str) -> dict:
    """A booking made on their own page (a platform's, their form's) or from his own WhatsApp: the change or cancellation is HIS,
    there — she opens it; nothing is sent from here. The words are voice.manage_line's (one place)."""
    from app.agent import voice as V
    link = row.get("url")
    if row["route"] == "your_whatsapp" and link:
        link = re.sub(r"\?.*$", "", link)   # his chat with them — the number only, never a message written here (CR 131 (d))
    out = {"status": "yours_there", "venue": row.get("venue"), "route": row["route"], "booked": row["status"] in ("confirmed", "booked_by_you"),
           "say": V.manage_line(kind, row["route"], row.get("venue") or "the venue", row.get("platform"), link=bool(link))}
    if link:
        out.update(open=link, page_url=link, button={"label": V.manage_button(row["route"], row.get("platform")), "link": link})
    return out


__all__ = ["of", "venue_rows", "extra_reservations", "upcoming", "find", "page_answer", "as_reservation", "words", "route_words",
           "map_url", "handover_route", "act_route", "MANAGE", "ROUTE_WORDS", "row_terms", "start_of", "with_terms"]
