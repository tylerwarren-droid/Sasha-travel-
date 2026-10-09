"""Sasha 211 Part B · REAL VENUE BOOKINGS ON THE AGENT — the EXISTING ladder (booking_signer: /venues/read, /forms, /links,
/emails, /calls, cancel), called in-process (guest_whatsapp.api) exactly as the WhatsApp guest flow calls it. No new booking
machinery: these tools only sequence it for the agent, with the same two steps as the trip's checkout.

  read_booking_route   the venue read (its routes), remembered for this account
  hold_venue           the route — the ladder's own question when it has one (> 48 h: "email them, or book it with you now?";
                       within 48 h: their page now, or a call) — then the read-back the yes binds to. Nothing is sent.
  book_venue           only after the person's explicit yes in a LATER turn (as book): by route
                         form      → filled by Sasha (the founder's override: the cloud browser) — any human step (a CAPTCHA,
                                     terms, the final button) goes to the phone as "Tap to finish"
                         page      → the platform's real page to the phone (TheFork, CoverManager, OpenTable…); the person books
                         email     → sent (Requested until the venue replies)
                         call      → placed (the call's reading decides)
                         whatsapp  → the drafted message, for the person to send
  cancel_venue         the same two steps, back the same route (cancel_routes)
Pacioli: every booking is a trip_items row the routes write; it is in the itinerary on its day; Requested → Confirmed only
from proof (the form's confirmation page, the platform's email via Gmail, the venue's reply) — get_status reads them.
"""
from __future__ import annotations

import hashlib
import logging
import re
import uuid
from datetime import date, datetime, time, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import quote

log = logging.getLogger("agapi.venues")

_READS: Dict[str, Dict[str, dict]] = {}   # account → venue key → the read (read_id, rungs, facts…)
_HELD: Dict[str, dict] = {}               # account → the prepared booking (route, id, sha, when it was said)
_CANCEL: Dict[str, dict] = {}             # account → the prepared cancellation
ROUTE_TO_PREFER = {"form": "form", "email": "email", "page": "one_tap", "call": "call"}


def _API():
    from booking_signer import guest_whatsapp as GW
    return GW


def _err(code: str, message: str):
    from agapi.v0 import ToolError
    return ToolError(code, message)


def _key(a: dict) -> str:
    return (a.get("place_id") or f"{a.get('name', '')}|{a.get('city', '')}").strip().lower()


def _what(a: dict) -> str:
    return (a.get("what") or "a table").strip()[:120]


async def _read(ctx, a: dict) -> dict:
    """The venue read through the booking API (it keeps a read_id the routes need), remembered per account."""
    GW = _API()
    k = _key(a)
    got = _READS.get(ctx.account, {}).get(k)
    if got:
        return got
    asked = " ".join(x for x in (_what(a), a.get("type") or "") if x)[:200]
    body = {"name": a.get("name"), "city": a.get("city"), "country": a.get("country"), "place_id": a.get("place_id"),
            "website": a.get("website"), "asked_for": asked}
    status, rd = await GW.api(ctx.account, "POST", "/api/booking/venues/read", {k2: v for k2, v in body.items() if v})
    if status != 200:
        raise _err((rd or {}).get("rule") or "read_failed", GW.refusal_words(rd or {}, status))
    venue = (rd.get("listing") or {}).get("name") or a.get("name") or rd.get("venue")
    if "(TEST stand-in)" in str(rd.get("venue") or ""):
        venue = rd["venue"]
    rungs = {r["rung"]: r for r in rd.get("rungs") or [] if r.get("available")}
    out = {"read_id": rd["read_id"], "country": rd.get("country"), "venue": venue, "facts": rd.get("facts") or [], "place_id": a.get("place_id"),
           "rungs": {k2: {"fact_index": r.get("fact_index"), "value": r.get("value")} for k2, r in rungs.items()},
           **GW._hours_of(rd, datetime.now(timezone.utc)), "say": rd.get("say")}
    _READS.setdefault(ctx.account, {})[k] = out
    return out


# ── Sasha 213 · ONE TURN, ONE STATE: the cards on screen are the cards she was given ─────────────────────────────────────
_SHOWN: Dict[str, Dict[str, dict]] = {}   # account → place_id → the card as shown (the pick and the booking show THAT card)


def shown_cards(r: dict) -> List[dict]:
    """The cards the person sees: the server's ranking's default order, its `show` count — what ChatBooking shows."""
    all_ = [c for c in (r.get("candidates") or []) if c.get("place_id")]
    rk = r.get("ranking") or {}
    order = (rk.get("orders") or {}).get(rk.get("default") or "rated")
    by = {c["place_id"]: c for c in all_}
    cards = [by[i] for i in order if i in by] if order else all_
    return cards[: int(r.get("show") or 5)]


def area_of(c: dict) -> str:
    parts = [p.strip() for p in str(c.get("address") or "").split(",") if p.strip()]
    return re.sub(r"^\d{4,5}\s*", "", parts[-2]) if len(parts) >= 3 else (parts[0] if parts else "")


def card_for_model(c: dict) -> dict:
    return {"name": c.get("name"), "place_id": c.get("place_id"), "area": area_of(c), "type": c.get("type"),
            "rating": c.get("rating"), "reviews": c.get("rating_count"),
            # Sasha 217 · OPENING HOURS only — never "a table is free": availability is known only when the venue answers
            **({"opening_hours_then": c["open_at"], "table_availability": "unknown until the venue answers"} if c.get("open_at") else {})}


def remember_cards(account: str, cards: List[dict]) -> None:
    m = _SHOWN.setdefault(account, {})
    for c in cards:
        m[c["place_id"]] = c
    while len(m) > 60:
        m.pop(next(iter(m)))


def card_of(account: str, place_id: Optional[str], name: Optional[str] = None) -> Optional[dict]:
    m = _SHOWN.get(account) or {}
    if place_id and place_id in m:
        return m[place_id]
    n = (name or "").strip().lower()
    return next((c for c in reversed(list(m.values())) if n and (c.get("name") or "").strip().lower() == n), None)


def ribbon_line(a: dict, shown: List[dict], r: dict) -> str:
    """The one line over the cards — from the SAME result as the cards and her words."""
    what, where = (a.get("what") or "places").strip(), (a.get("where") or "").strip()
    when = ""
    if a.get("open_at"):
        try:
            from booking_signer import sentences as SN
            when = f" · {SN.day_words(a['open_at'][:10])} {a['open_at'][11:16]}"
        except Exception:
            when = ""
    if not shown:
        return f"No {what} found in {where}{when}" if not r.get("no_match") else f"No {r['no_match']} places found in {where}{when}"
    return f"{len(shown)} {what} in {where}{when}"


async def photos_for(cards: List[dict], budget: float = 1.2) -> None:
    """The top results' photos, fetched now (each venue's own picture, else Google's), cached by the photo layer; a card
    whose photo misses the budget shows without it and gets it lazily."""
    GW = _API()
    try:
        got, _late = await GW._photos_within(cards, budget)
    except Exception as e:
        log.info("[venues] photos: %s", type(e).__name__)
        got = {}
    for c in cards:
        if got.get(c["place_id"]):
            c["photo"] = got[c["place_id"]]


def _routes_of(rd: dict) -> List[str]:
    r = rd.get("rungs") or {}
    return [x for x, k in (("form", "form"), ("page", "link"), ("email", "email"), ("call", "phone"), ("whatsapp", "whatsapp"),
                           ("instagram", "instagram")) if k in r]


async def read_booking_route(ctx, a: dict) -> dict:
    rd = await _read(ctx, a)
    card = card_of(ctx.account, a.get("place_id"), a.get("name"))   # Sasha 213 · the picked card is what's on screen
    return {**({"card": card} if card else {}), "venue": rd["venue"], "routes": _routes_of(rd), "how": rd.get("say"),
            "open_now": rd.get("open_now"), "opens_at": rd.get("opens_at")}


async def _reservation(ctx, a: dict, rd: dict) -> dict:
    GW = _API()
    try:
        day = date.fromisoformat(str(a["day"]))
        hhmm = time.fromisoformat(str(a["time"])[:5]).strftime("%H:%M")
    except (KeyError, ValueError):
        raise _err("when_invalid", "day is YYYY-MM-DD and time HH:MM") from None
    party = max(1, min(20, int(a.get("party") or 2)))
    _s, d = await GW.api(ctx.account, "POST", "/api/booking/draft", {"text": _what(a), "country": rd.get("country")})
    what = (d.get("parts") or {}).get("what")
    if not what:
        _s, d = await GW.api(ctx.account, "POST", "/api/booking/draft", {"text": f"{_what(a)} restaurant", "country": rd.get("country")})
        what = (d.get("parts") or {}).get("what") or {"category": "restaurant", "activity": "table"}
    status, cj = await GW.api(ctx.account, "GET", "/api/booking/contact")
    contact = (cj or {}).get("contact") if status == 200 else None
    if not contact:
        raise _err("contact_missing", "the venue needs the person's name and mobile — ask them, once")
    return {"schema": "reservation/1", "flow": "book", "who": {"name": contact["name"], "contact": {"mobile_e164": contact["mobile_e164"]}},
            "what": what, "where": {}, "when": {"mode": "at", "at": f"{day.isoformat()}T{hhmm}"},
            "how_many": {"count": party, "unit": "people"}}


async def hold_venue(ctx, a: dict) -> dict:
    """Prepare the booking by its route → the read-back (or the ladder's question first). Nothing is sent."""
    from booking_signer import guest_accounts as GA, guest_receipt as GR
    GW = _API()
    rd = await _read(ctx, a)
    res = await _reservation(ctx, a, rd)
    at = res["when"]["at"]
    now = datetime.now(timezone.utc)
    route = a.get("route")
    card = card_of(ctx.account, a.get("place_id"), a.get("name"))   # Sasha 213 · this venue's card, highlighted on screen
    return _with_card(card, await _hold_inner(ctx, a, rd, res, at, now, route))


def _with_card(card: Optional[dict], out: dict) -> dict:
    if card and isinstance(out, dict):
        out["card"] = card
    return out


async def _hold_inner(ctx, a: dict, rd: dict, res: dict, at: str, now, route: Optional[str]) -> dict:
    from booking_signer import guest_accounts as GA, guest_receipt as GR
    GW = _API()
    msg_routes = [x for x in _routes_of(rd) if x in ("whatsapp", "instagram")]
    if route in ("whatsapp", "instagram") or (not route and msg_routes and set(_routes_of(rd)) <= {"whatsapp", "instagram"}):
        # Sasha 212 · a place that books only by a message (a tattoo studio on Instagram, a bar on WhatsApp): Sasha DRAFTS it
        # for their phone — they send it; nothing is booked until the place answers them
        ch = route if route in ("whatsapp", "instagram") else msg_routes[0]
        val = str((rd["rungs"].get(ch) or {}).get("value") or "")
        n = res['how_many']['count']
        when_words = f"{n} {'person' if n == 1 else 'people'}"
        msg = (f"Hola, quería pedir cita para {n} {'persona' if n == 1 else 'personas'} el {at[:10]} a las {at[11:16]}, a nombre de {res['who']['name']}. "
               f"¿Tienen disponibilidad? Gracias." if rd.get("country") == "ES" else
               f"Hello, I'd like to book for {when_words} on {at[:10]} at {at[11:16]}, under {res['who']['name']}. "
               f"Do you have availability? Thank you.")
        link = (f"https://wa.me/{re.sub(r'[^0-9]', '', val)}?text={quote(msg)}" if ch == "whatsapp" and re.sub(r"\D", "", val)
                else f"https://ig.me/m/{val}" if ch == "instagram" and val else None)
        prev = _HELD.get(ctx.account)
        sha = hashlib.sha256(f"draft|{ch}|{rd['venue']}|{msg}".encode()).hexdigest()
        _HELD[ctx.account] = {"rung": "draft", "id": ch, "sha": sha, "at": prev["at"] if prev and prev.get("sha") == sha else now,
                              "venue": rd["venue"], "summary": GW.summary(res), "when": at, "party": res["how_many"]["count"],
                              "message": msg, "link": link, "channel": ch}
        return {"status": "draft_message", "venue": GW.plain_venue(rd["venue"]), "route": ch, "message": msg,
                **({"open_in_" + ch: link} if link else {}),
                "what_happens": f"they book only by a {('WhatsApp' if ch == 'whatsapp' else 'Instagram')} message: on their yes, "
                                "Sasha sends the drafted message to their phone and they send it; it is NOT booked until the place replies"}
    if not route:
        lad = GW.ladder_of(rd, res, now)
        if lad and lad.get("options"):
            return {"status": "choose_route", "venue": rd["venue"], "ask": lad["line"],
                    "options": [{"title": t, "route": r} for t, r in lad["options"]]}
    if route == "no":
        return {"status": "not_booking", "venue": rd["venue"]}
    dv = GW.decision_of(rd, ROUTE_TO_PREFER.get(route or ""), at, now, ctx.account)
    order = [r for r in [dv.route] + list(dv.alternatives) if r]
    if route in ROUTE_TO_PREFER:   # the person's choice first
        order = [ROUTE_TO_PREFER[route]] + [r for r in order if r != ROUTE_TO_PREFER[route]]
    rungs, why = rd["rungs"], None
    contact_name = res["who"]["name"]
    for r in order:
        if r == "form" and "form" in rungs:
            email = await GR.address_of(ctx.account)
            rf = {**res, "who": {**res["who"], "contact": {**res["who"]["contact"], **({"email": email} if email else {})}}}
            status, j = await GW.api(ctx.account, "POST", "/api/booking/forms", {"read_id": rd["read_id"], "reservation": rf})
            rung = "form"
            if status != 200 and GA.founder(ctx.account):   # the founder's override: the cloud browser fills it; a human step → the phone
                status, j = await GW.api(ctx.account, "POST", "/api/booking/forms", {"read_id": rd["read_id"], "reservation": rf, "handover": True})
                rung = "handover"
            if status == 200:
                return _hold(ctx, rung, j["form_id"], j["read_back"], rd, res, extra={"trip_item_id": j.get("trip_item_id")})
            why = GW.refusal_words(j, status)
        elif r == "one_tap" and ("link" in rungs or "form" in rungs):
            status, j = await GW.api(ctx.account, "POST", "/api/booking/links", {
                "read_id": rd["read_id"], "date": at[:10], "time": at[11:16], "party": res["how_many"]["count"], "name": contact_name,
                "venue": GW.plain_venue(rd["venue"])[:120]})
            if status == 200:
                return _hold(ctx, "page", j["link_id"], j["read_back"], rd, res,
                             extra={"url": j["url"], "platform": j.get("platform"), "slot_filled": bool(j.get("slot_filled")),
                                    "trip_item_id": j.get("trip_item_id")})
            why = GW.refusal_words(j, status)
        elif r in ("call", "call_email") and "phone" in rungs:
            fi = rungs["phone"].get("fact_index")
            status, j = await GW.api(ctx.account, "POST", "/api/booking/calls",
                                     {"reservation": res, "read_id": rd["read_id"], **({"fact_index": fi} if fi is not None else {})})
            if status == 200:
                return _hold(ctx, "call", j["call_id"], j["read_back"], rd, res, extra={"trip_item_id": j.get("trip_item_id")})
            why = GW.refusal_words(j, status)
        elif r == "email" and "email" in rungs:
            mine = await GR.address_of(ctx.account)
            status, j = await GW.api(ctx.account, "POST", "/api/booking/emails", {
                "read_id": rd["read_id"], "date": at[:10], "time": at[11:16], "party": res["how_many"]["count"], "name": contact_name,
                "email": mine or ""})
            if status == 200:
                return _hold(ctx, "email", j["email_id"], j["read_back"], rd, res, extra={"trip_item_id": j.get("trip_item_id")})
            why = GW.refusal_words(j, status)
    raise _err("no_route", f"{GW.plain_venue(rd['venue'])} can't be booked from here right now" + (f" — {why}" if why else ""))


def _hold(ctx, rung: str, rid: str, read_back: dict, rd: dict, res: dict, extra: Optional[dict] = None) -> dict:
    GW = _API()
    prev = _HELD.get(ctx.account)
    at = prev["at"] if prev and prev.get("sha") == read_back["sha256"] else datetime.now(timezone.utc)
    _HELD[ctx.account] = {"rung": rung, "id": rid, "sha": read_back["sha256"], "at": at, "venue": rd["venue"], "summary": GW.summary(res),
                          "place_id": rd.get("place_id"),
                          "when": res["when"]["at"], "party": res["how_many"]["count"], **(extra or {})}
    lines = GW.guest_lines(rung, read_back.get("lines") or [])
    return {"status": "awaiting_yes", "venue": GW.plain_venue(rd["venue"]), "route": rung, "when": GW.summary(res),
            "read_back": lines, "what_happens": {
                "form": "Sasha sends their own booking form",
                "handover": "Sasha fills their booking page; if it needs a human step (a CAPTCHA, terms, the final button) "
                            "it goes to their phone as Tap to finish",
                "page": f"their {extra.get('platform') or 'booking'} page goes to their phone; they press book there" if extra else "",
                "email": "Sasha emails them; it's a request until they reply",
                "call": "Sasha calls them; it's booked only if they say yes on the call"}.get(rung, "")}


async def book_venue(ctx, a: dict) -> dict:
    """After the person's explicit yes in a LATER turn: the prepared booking, by its route."""
    from agapi.v0 import claim, stale, yes_to_book
    GW = _API()
    said = ((a.get("approval") or {}).get("said")) or ""
    if not yes_to_book(said):
        raise _err("no_explicit_yes", "booking needs the person's explicit yes in this turn — ask them, then call book_venue")
    held = _HELD.get(ctx.account)
    if not held:
        raise _err("nothing_held", "call hold_venue first — the yes is bound to its read-back")
    if held["at"] >= ctx.started:
        raise _err("read_back_first", "say what you'll do and ask them to go ahead; book once they say yes")
    if stale(held["at"]):   # Sasha 215 · a read-back over 15 minutes old is never acted on: prepared again, said again
        _HELD.pop(ctx.account, None)
        raise _err("read_back_stale", "that was prepared over 15 minutes ago — call hold_venue again and read it back before booking")
    how = {"how": "voice", "said": said}
    venue, rung = GW.plain_venue(held["venue"]), held["rung"]
    await claim(ctx)   # Sasha 215 · durable: sent once, across restarts and workers
    _HELD.pop(ctx.account, None)
    out = await _book_inner(ctx, held, how, venue, rung)
    card = card_of(ctx.account, held.get("place_id"), venue)
    return _with_card(card, out)


async def _book_inner(ctx, held: dict, how: dict, venue: str, rung: str) -> dict:
    from booking_signer import slot_link as SL, wa_brain as WB
    GW = _API()
    where = await WB.trip_day_words(ctx.account, held["when"][:10], venue)
    if rung == "form":
        status, j = await GW.api(ctx.account, "POST", f"/api/booking/forms/{held['id']}/send", {"read_back_sha256": held["sha"], "approval": how}, timeout=120)
        if status != 200:
            raise _err("not_sent", GW.refusal_words(j, status))
        result = (j.get("reading") or {}).get("result") if j.get("status") == "sent" else None
        ref = j.get("booking_reference") if result == "confirmed" else None
        return {"status": "confirmed" if result == "confirmed" else ("requested" if j.get("status") == "sent" else "not_sent"),
                "venue": venue, "when": held["summary"], "itinerary": where, **({"reference": ref} if ref else {}),
                "line": (f"✅ Booked: {venue}, {held['summary']}." + (f" Their reference: {ref}." if ref else "")) if result == "confirmed"
                else "Sent — it's Requested until their confirmation comes back."}
    if rung == "draft":   # Sasha 212 · the drafted message goes to THEIR phone; they send it — never "booked"
        sent = False
        try:
            ch = await GW.STORE.channel_of_account(ctx.account) if GW.STORE else None
            if ch:
                where_ = "WhatsApp" if held["channel"] == "whatsapp" else "Instagram"
                out = await GW._tell(ch, f"✍️ For {venue} — send this on {where_}{': ' + held['link'] if held.get('link') else ''}\n\n{held['message']}")
                sent = "sent" in out and "not" not in out
        except Exception as e:
            log.warning("[venues] the draft was not sent to the phone: %s", type(e).__name__)
        return {"status": "draft_on_phone" if sent else "draft_message", "venue": venue, "when": held["summary"], "booked": False,
                "message": held["message"], **({"open": held["link"]} if held.get("link") and not sent else {}),
                "line": "It's not booked until they reply to you."}
    if rung == "handover":
        status, j = await GW.api(ctx.account, "POST", f"/api/booking/forms/{held['id']}/handover", {}, timeout=120)
        if status != 200:
            raise _err("not_opened", (j or {}).get("say") or GW.refusal_words(j, status))
        sent = bool((j.get("phone") or {}).get("sent"))
        return {"status": "tap_to_finish", "venue": venue, "when": held["summary"], "itinerary": where, "on_phone": sent,
                **({} if sent else {"open": j.get("view_url")}), **({"view_url": j["view_url"]} if j.get("view_url") else {})}
    if rung == "page":
        status, j = await GW.api(ctx.account, "POST", f"/api/booking/links/{held['id']}/opened", {"read_back_sha256": held["sha"]})
        if status != 200:
            raise _err("not_sent", GW.refusal_words(j, status))
        dt = datetime.fromisoformat(held["when"])
        url = j.get("url") or held.get("url")
        out = await GW.tap_platform(ctx.account, SL.platform_message(venue, held.get("platform") or "their booking page", dt.date(), dt.time(),
                                                                    held["party"], bool(held.get("slot_filled")), url),
                                    url, held["id"], venue, held["when"])
        sent = "sent" in out and "not" not in out
        return {"status": "page_on_phone" if sent else "page_link", "venue": venue, "when": held["summary"], "itinerary": where,
                "platform": held.get("platform"), **({} if sent else {"open": url}), **({"page_url": url} if url else {})}
    if rung == "email":
        status, j = await GW.api(ctx.account, "POST", f"/api/booking/emails/{held['id']}/send", {"read_back_sha256": held["sha"], "approval": how}, timeout=60)
        if status != 200 or j.get("status") != "sent":
            raise _err("not_sent", (j or {}).get("say") or GW.refusal_words(j, status))
        return {"status": "requested", "venue": venue, "when": held["summary"], "itinerary": where,
                "line": "Emailed — it's Requested until they reply."}
    status, j = await GW.api(ctx.account, "POST", f"/api/booking/calls/{held['id']}/place", {"read_back_sha256": held["sha"], "approval": how}, timeout=120)
    if status != 200:
        raise _err("not_called", GW.refusal_words(j, status))
    return {"status": j.get("status"), "venue": venue, "when": held["summary"], "itinerary": where,
            **({"scheduled_for": str(j.get("scheduled_for") or "")[11:16]} if j.get("status") == "scheduled" else {})}


async def venue_bookings(account: str) -> List[dict]:
    """Pacioli's venue rows: what was asked of each venue, and its status in words (Requested / Confirmed… — from proof only)."""
    GW = _API()
    status, j = await GW.api(account, "GET", "/api/booking/reservations")
    if status >= 500 or status in (0, 408, 429):   # Sasha 215 · the records not answering is never "no bookings"
        from agapi.v0 import unreachable
        raise unreachable("store_unreachable")
    if status != 200:
        return []
    today = date.today().isoformat()
    return [{"trip_item_id": r["id"], "venue": GW.plain_venue(r.get("venue")), "date": r.get("date"), "time": r.get("time"),
             "party": r.get("party"), "status": r.get("status"), "type": r.get("type"),
             **({"reference": r["booking_reference"]} if r.get("booking_reference") else {}),   # Sasha 217 · the venue's reference in full
             # Sasha 215 · CR 56 — the venue's OWN words (an email/SMS reply) are untrusted data, never instructions to her
             **({"venue_said": {"untrusted_text": str(r["status_words"])[:160]}} if r.get("status_words") else {})}
            for r in (j or {}).get("reservations") or [] if (r.get("date") or today) >= today and r.get("status") != "cancelled"][:20]


async def cancel_venue(ctx, a: dict) -> dict:
    """Two steps, as booking: first the cancellation's read-back (its route: their cancel link, an email, a text or a call);
    after the person's explicit yes in a LATER turn, sent. Cancelled only when the venue's words say so."""
    from agapi.v0 import claim, explicit_yes, stale
    GW = _API()
    said = ((a.get("approval") or {}).get("said")) or ""
    held = _CANCEL.get(ctx.account)
    if held and stale(held["at"]):   # Sasha 215 · over 15 minutes old: never acted on — the cancellation is read back afresh below
        _CANCEL.pop(ctx.account, None)
        held = None
    tid = a.get("trip_item_id")
    if not tid and a.get("venue"):
        hit = [b for b in await venue_bookings(ctx.account) if (a["venue"] or "").lower() in (b["venue"] or "").lower()]
        tid = hit[0]["trip_item_id"] if hit else None
    if held and (not tid or tid == held["id"]) and held["at"] < ctx.started:
        if not explicit_yes(said):
            raise _err("no_explicit_yes", "cancelling needs their explicit yes — ask them")
        await claim(ctx)
        _CANCEL.pop(ctx.account, None)
        status, j = await GW.api(ctx.account, "POST", f"/api/booking/reservations/{held['id']}/cancel",
                                 {"read_back_sha256": held["sha"], "approval": {"how": "voice", "said": said}}, timeout=120)
        if status != 200:
            raise _err("not_cancelled", GW.refusal_words(j, status))
        return {"status": j.get("status"), "say": j.get("say"), "venue": held["venue"]}
    if not tid:
        raise _err("booking_unknown", "which booking? get_status lists them")
    status, j = await GW.api(ctx.account, "GET", f"/api/booking/reservations/{tid}/cancel")
    if status != 200:
        raise _err((j or {}).get("rule") or "booking_unknown", GW.refusal_words(j, status))
    _CANCEL[ctx.account] = {"id": tid, "sha": j["read_back"]["sha256"], "at": datetime.now(timezone.utc), "venue": j.get("venue")}
    return {"status": "awaiting_yes", "venue": GW.plain_venue(j.get("venue")), "route": j.get("route"), "read_back": j["read_back"]["lines"]}


__all__ = ["read_booking_route", "hold_venue", "book_venue", "cancel_venue", "venue_bookings"]
