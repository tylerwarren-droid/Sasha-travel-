"""Sasha 194 · THE CORE-FLOW SUITES — itinerary, restaurant, spa, spaces — beside the flight suite in the deploy gate.

Deterministic where it matters: the restaurant and the spa book OUR test venue (never a real place is contacted); the routing
rules (forms first, the platform page, the 48-hour rule) are checked on the decision itself. Typed AND transcribed-voice
phrasings. A scratch guest, deleted after (its product files too). Exit 1 on any failure: Railway then keeps the old deploy.
    railway run python -m scripts.core_suites        (from backend/)
"""
from __future__ import annotations

import asyncio
import os
import types
import re
import sys
import time
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.flight_suite import RESULTS, ok  # noqa: E402  — one pass list for the gate


def _said(r) -> str:
    return (r or {}).get("response") or ""


async def itinerary(a: str, conduct) -> None:
    """The intake from the meeting's own words (all said at once) and a hotel swap; the step-by-step intake is GUIDED's."""
    sid = "core-i2-" + uuid.uuid4().hex[:6]
    v = await conduct("I'd like you to plan a trip for me to Vietnam, please, for twelve days. From November 15 to November 27.", [],
                      user_id=a, signed_in=True, session_id=sid)
    ok("ITIN voice: the meeting's words → ONE question first (my name)", "what's your name" in _said(v) and _said(v).count("?") == 1, _said(v)[:110])
    v = await conduct("It's Alex.", v["messages"], user_id=a, signed_in=True, session_id=sid)
    ok("ITIN voice: the name → greeted by it, then what kind of trip", "Alex" in _said(v) and "What kind of trip" in _said(v), _said(v)[:110])
    v2 = await conduct("Be two of us, flying from London, and we'd like a mixture between culture and beaches, please.", v["messages"],
                       user_id=a, signed_in=True, session_id=sid)
    ok("ITIN voice: everything said → built for the 15th–27th, flights asked about from London", bool(v2.get("itinerary"))
       and "Shall we look at flights?" in _said(v2) and "London" in _said(v2) and "14 November" in _said(v2), _said(v2)[:150])
    v3 = await conduct("change the hotel in Hoi An to something on the beach", v2["messages"], user_id=a, signed_in=True, session_id=sid)
    ok("ITIN: the Hoi An hotel swapped to a beach hotel, said with the new estimate",
       "Hoi An is now" in _said(v3) and "Beach" in _said(v3) and "€" in _said(v3), _said(v3)[:110])


async def restaurant(a: str) -> None:
    from booking_signer import decide as D, slot_link as SL, voice_turn as VT, guest_whatsapp as GW
    V = D.Venue
    d = D.decide(V(form=True, platform="CoverManager", phone=True, email=True, open_now=True, opens_at=None, scripted=True, calls_on=True, hours_until=200))
    ok("REST ladder: their own form first", d.route == "form", d.route)
    d = D.decide(V(form=False, platform="CoverManager", phone=True, email=True, open_now=True, opens_at=None, scripted=True, calls_on=True, hours_until=200))
    ok("REST ladder: a platform → its page on the phone (one tap)", d.route == "one_tap", d.route)
    d = D.decide(V(form=False, platform=None, phone=True, email=True, open_now=True, opens_at=None, scripted=True, calls_on=True, hours_until=72))
    ok("REST 48 h rule: more than 48 h away, no page → email first", d.route == "email", d.route)
    d = D.decide(V(form=False, platform=None, phone=True, email=True, open_now=True, opens_at=None, scripted=True, calls_on=True, hours_until=30))
    ok("REST 48 h rule: within 48 h → call and email at once", d.route == "call_email", d.route)
    read = {"facts": [{"kind": "platform", "value": "CoverManager", "source_label": "their website", "source_url": "https://example.test/",
                       "detail": {"link": "https://www.covermanager.com/reservation/module_restaurant/restaurante-ejemplo/spanish"}}]}
    page = SL.platform_page(read)
    ok("REST platform: the venue's own CoverManager page is the one sent (never fetched)", bool(page) and "covermanager.com" in page[1], str(page)[:100])
    W = "Saturday 10 October at 21:00, 2 people"
    L = lambda **k: (D.ladder(V(**k), "Casa Ejemplo", W) or {}).get("line", "")
    ok("LADDER >48 h, books directly: “I can book Casa Ejemplo for you directly — … Shall I?”",
       L(form=True, phone=True, email=True, hours_until=72) == f"I can book Casa Ejemplo for you directly — {W}. Shall I?")
    ok("LADDER >48 h, a page: “We have time. Would you like me to email … or … book with them now?”",
       L(platform="CoverManager", phone=True, email=True, hours_until=72).startswith("We have time. Would you like me to email Casa Ejemplo"))
    ok("LADDER within 48 h, a page: “It's soon, so I recommend we book it now together … Or I can call them for you.”",
       L(platform="CoverManager", phone=True, email=True, hours_until=20) == "It's soon, so I recommend we book it now together — I'll send their booking page to your phone. Or I can call them for you.")
    ok("LADDER a CAPTCHA page counts as a page (never 'directly')", L(form=True, challenge=True, email=True, hours_until=72).startswith("We have time"))
    ok("LADDER no online booking, >48 h: “They don't take online bookings — I'll email them …”",
       L(phone=True, email=True, hours_until=72) == "They don't take online bookings — I'll email them and update you as soon as they reply. OK?")
    ok("LADDER no online booking, within 48 h: “They only take bookings by phone — shall I call them?”",
       L(phone=True, hours_until=20) == "They only take bookings by phone — shall I call them?")
    real = GW.rehearsal
    GW.rehearsal = lambda acct: True   # this process only: the guest's cards end with OUR test venue (contacts no one)
    try:
        h = []
        for said in ("dinner for 2 in Chamberí, Madrid on Saturday at 9pm", "Sasha Test Venue", "Suite Guest +34 600 000 000", "yes"):
            v = await VT.turn(a, said, h)
            h = (v or {}).get("messages") or h
            if said.startswith("Suite Guest"):
                ok("REST typed: the ladder's words — “I can book Sasha Test Venue for you directly — … Shall I?”",
                   "I can book Sasha Test Venue for you directly" in _said(v), _said(v)[:120])
        ok("REST typed → booked at the test venue, with its reference", re.search(r"✅|[Bb]ooked|confirmed", _said(v)) is not None, _said(v)[:120])
        h = []
        for said in ("Uh, a table for two in Chamberí, Madrid, Saturday at nine at night, please.", "the third one", "yes"):
            v = await VT.turn(a, said, h)
            print(f"   REST voice · {said!r} → {_said(v)[:140]!r}", flush=True)
            h = (v or {}).get("messages") or h
        ok("REST voice phrasing → booked at the test venue", re.search(r"✅|[Bb]ooked|confirmed", _said(v)) is not None, _said(v)[:120])
    finally:
        GW.rehearsal = real


async def spa(a: str) -> None:
    from booking_signer import ladder_routes as LR, captcha_test as CT, decide as D
    real_s = LR.standin
    LR.standin = lambda acct: bool(acct)   # this process only: the founder's demo setting (real spas, online only)
    try:
        req = types.SimpleNamespace(state=types.SimpleNamespace(), headers={})
        body = {"what": "spa", "where": "Madrid", "country": "ES"}
        out = await LR._online_only(a, await __import__("booking_signer.venue_read", fromlist=["find_venues"]).find_venues(
            LR.HTTP, what="spa", where="Madrid", country="ES", now=LR.NOW()), body)
        c = out.get("candidates") or []
        ok("SPA live: real spas, each bookable online (platform or own page)", bool(c) and all(x.get("online") for x in c),
           " | ".join(f"{x.get('name')} ({x.get('online')})" for x in c[:3]))
        ok("SPA live: never our test venue among real spas", not any(x.get("place_id") == LR.REHEARSAL_ID for x in c), "")
    finally:
        LR.standin = real_s
    W = "Saturday 10 October at 16:00, 2 people"
    line = (D.ladder(D.Venue(form=True, challenge=True, hours_until=20), "Spa Ejemplo", W) or {}).get("line", "")
    ok("SPA a CAPTCHA page within 48 h → their page on the phone, now", line.startswith("It's soon, so I recommend we book it now together"), line[:100])
    ok("SPA “send me the captcha test” still answered", CT.asked("send me the captcha test"), "")


async def guided(a: str, conduct) -> None:
    """Sasha 196 · THE GUIDED TRIP, end to end (typed and voice-style): intake one question at a time → plan → flights asked
    about → picked and ADDED (not booked) → a restaurant via the ladder on the trip's day → no → changes → hotel swap → no, book it
    → ONE total (hotels + the picked flight) → paid (simulated tap) → booked, venue bookings listed apart."""
    from booking_signer import voice_turn as VT, guest_whatsapp as GW, plan_store as PS, trip_book as TB, travel as T, itinerary_q as IQ
    from scripts.flight_suite import _pay_and_settle
    import booking_signer.account as ACC
    sid = "core-g-" + uuid.uuid4().hex[:6]
    h = []

    async def say(m):
        nonlocal h
        r = await conduct(m, h, user_id=a, signed_in=True, session_id=sid)
        h = r.get("messages") or h
        return r
    r = await say("plan me a trip to Vietnam from 12 November for 8 days")
    ok("GUIDED 1: introduces herself, asks my NAME first (one question)", "I'm Sasha" in _said(r) and "what's your name" in _said(r)
       and _said(r).count("?") == 1, _said(r)[:90])
    r = await say("Uh, my name is Alex.")
    ok("GUIDED 1b: then what kind of trip, by name", "Alex" in _said(r) and "What kind of trip" in _said(r) and _said(r).count("?") == 1, _said(r)[:90])
    r = await say("Uh, we're into food and culture, please.")
    ok("GUIDED 2: then how many", "How many of you" in _said(r), _said(r)[:90])
    r = await say("Be two of us.")
    ok("GUIDED 3: then where from (Madrid suggested)", "flying from" in _said(r) and "Madrid" in _said(r), _said(r)[:90])
    r = await say("Madrid please.")
    ok("GUIDED 4: the plan, then flights ASKED about (never assumed)", bool(r.get("itinerary")) and "Shall we look at flights?" in _said(r)
       and not r.get("bookings"), _said(r)[:140])
    r = await say("Yeah, direct ones please.")
    card = next((b for b in r.get("bookings") or [] if b.get("trip_pick")), None)
    ok("GUIDED 5: direct flights shown, each to CHOOSE (not book)", bool(card) and all("nonstop" in (o.get("detail") or "") for o in card["options"]),
       _said(r)[:90])
    name = (card or {}).get("options", [{}])[0].get("name", "")
    r = await say(f"the {name} one")
    ok("GUIDED 6: “Done — I've added the … flight to your itinerary.” + anything else?",
       f"Done — I've added the {name} flight to your itinerary." in _said(r) and "anything else you'd like me to add" in _said(r), _said(r)[:140])
    p = await PS.latest(a)
    from booking_signer import basket as BK   # Sasha 198 R10 · the pick is the basket's chosen flight
    _ch = [x for x in await BK.items(a, p["trip_id"], ("chosen",)) if x["kind"] == "flight"] if p else []
    ok("GUIDED 6: the flight is ON the itinerary (the basket's one chosen flight), not booked",
       len(_ch) == 1 and (_ch[0]["snapshot"].get("owner") == name or _ch[0]["snapshot"].get("name") == name)
       and not any("Flight" in str(x.get("venue")) for x in await IQ._rows(a)), str([x["snapshot"].get("owner") for x in _ch]))
    real = GW.rehearsal
    GW.rehearsal = lambda acct: True
    try:
        vh = []
        v = await VT.turn(a, "dinner for 2 in Hanoi on the 13th at 8pm", vh)
        vh = (v or {}).get("messages") or vh
        v = await VT.turn(a, "Sasha Test Venue", vh)
        for _ in range(3):   # the contact if it's asked, then the ladder's question — answered as a guest would
            vh = (v or {}).get("messages") or vh
            if "Whose name" in _said(v):
                v = await VT.turn(a, "Suite Guest +34 600 000 000", vh)
            elif "Shall I?" in _said(v):
                ok("GUIDED 7: the ladder's words, on the trip's day — “I can book … directly — Friday 13 November at 20:00”",
                   "directly — Friday 13 November at 20:00" in _said(v), _said(v)[:120])
                v = await VT.turn(a, "yes", vh)
                break
    finally:
        GW.rehearsal = real
    from booking_signer import journeys as JN
    await JN.file(a)   # as every itinerary view does before showing it
    rows = await IQ._rows(a)
    din = next((x for x in rows if "Sasha Test Venue" in str(x.get("venue")) and x.get("date") == "2026-11-13"), None)
    ok("GUIDED 7: a restaurant added via the ladder, on the trip's 13th, in the trip", bool(din) and din.get("date") == "2026-11-13"
       and str(din.get("trip_id")) == str((p or {}).get("trip_id")), str({k: (din or {}).get(k) for k in ("date", "status")}))
    r = await say("no")
    ok("GUIDED 8: “Would you like to make any changes?”", "Would you like to make any changes?" in _said(r), _said(r)[:90])
    r = await say("change the hotel in Hoi An to something on the beach")
    ok("GUIDED 9: the hotel swapped, then “Anything else?”", "Hoi An is now" in _said(r) and _said(r).rstrip().endswith("Anything else?"), _said(r)[:120])
    r = await say("no, book it")
    from booking_signer import passengers as PX   # Sasha 198 R7 · the travellers, asked once before the first total
    ok("GUIDED 9b: the first “book it” asks the travellers' details once", PX.MARK in _said(r), _said(r)[:100])
    r = await say("Alex Smith, Mr, 12 March 1985; Sam Smith, Ms, 2 May 1987")
    ok(f"GUIDED 10: ONE total for the hotels and the {name} flight — “Shall I book it?” (no flights offered again)",
       bool(r.get("trip_book")) and f"the {name} flight" in _said(r) and "Shall I book it?" in _said(r) and not r.get("bookings"), _said(r)[:140])
    real_acc = ACC.account_for
    ACC.account_for = lambda rq: getattr(rq, "_a", None) or real_acc(rq)
    try:
        await _pay_and_settle(a, TB.prepare, TB.pay, {"from": "Madrid"}, "GUIDED 11 whole trip")
    finally:
        ACC.account_for = real_acc
    rows = await IQ._rows(a)
    fl = [x for x in rows if str(x.get("venue") or "").startswith("Flight ")]
    ok("GUIDED 12: booked — the flight HE picked (only it), the hotels, the dinner kept apart",
       len(fl) == 1 and sum(1 for x in rows if "TEST booking" in str(x.get("venue")) and not str(x.get("venue")).startswith("Flight")) >= 4
       and any("Sasha Test Venue" in str(x.get("venue")) for x in rows), f"{len(fl)} flight(s), {len(rows)} rows")


async def tabs(a: str) -> None:
    from booking_signer import journeys as JN, itinerary_q as IQ
    j = await JN.journeys(a, await IQ._rows(a))
    sp = {t["key"]: t.get("space") for t in j["journeys"]}
    ok("TABS: CampusMe, RelocateMe and EspañaMe always there, each opening its space",
       sp.get("campus") == "campus" and sp.get("relocation") == "relocate" and sp.get("espana") == "españa", str(sp))


async def spaces(a: str, conduct) -> None:
    from products.web import current_space
    sid = "core-s-" + uuid.uuid4().hex[:6]
    h = []

    async def say(m):
        nonlocal h
        r = await conduct(m, h, user_id=a, signed_in=True, session_id=sid)
        h = r.get("messages") or h
        return r
    await say("campus")
    ok("SPACES: “campus” enters CampusMe", await current_space(a) in ("campus",), str(await current_space(a)))
    r = await say("plan a trip to visit Yale")
    ok("SPACES: inside CampusMe, “plan a trip to visit Yale” stays CampusMe", await current_space(a) in ("campus", "trip")
       and "products" in (r.get("intents") or []), _said(r)[:100])
    await say("sasha")
    ok("SPACES: “sasha” leaves it", await current_space(a) is None, str(await current_space(a)))
    r = await say("plan a trip to Singapore")
    ok("SPACES: in Sasha, “plan a trip to Singapore” is travel (no space entered)", await current_space(a) is None
       and "products" not in (r.get("intents") or []) and "Spain" not in _said(r), _said(r)[:100])
    await say("relocate")
    ok("SPACES: “relocate” enters RelocateMe", await current_space(a) == "relocation", str(await current_space(a)))
    r = await say("book my flights")
    ok("SPACES: inside RelocateMe, “book my flights” stays RelocateMe", await current_space(a) in ("relocation", "trip")
       and "products" in (r.get("intents") or []), _said(r)[:100])
    await say("sasha")
    r = await say("book my flights")
    ok("SPACES: in Sasha, “book my flights” never enters a space", await current_space(a) is None and "products" not in (r.get("intents") or []),
       _said(r)[:100])


async def main() -> int:
    if os.getenv("SASHA_FLIGHT_SUITE", "") == "skip":
        print("core suites SKIPPED (SASHA_FLIGHT_SUITE=skip) — this deploy is not covered")
        return 0
    from booking_signer import routes  # noqa: F401
    from booking_signer import guest_accounts as GA, ops
    from products.store import choose
    from app.services.conductor import conduct
    await choose(routes.STORE)
    t0 = time.time()
    g, why = await GA.create_guest("core-suites")
    if not g:
        print(f"FAIL · no scratch guest: {why}")
        return 1
    a = g["account_id"]
    print(f"scratch guest {a[:8]}", flush=True)
    try:
        for name, fn in (("itinerary", lambda: itinerary(a, conduct)), ("restaurant", lambda: restaurant(a)),
                         ("spa", lambda: spa(a)), ("guided", lambda: guided(a, conduct)), ("tabs", lambda: tabs(a)), ("spaces", lambda: spaces(a, conduct))):
            try:
                await fn()
            except Exception as e:
                ok(f"{name} suite ran", False, f"{type(e).__name__}: {e}")
    finally:
        try:
            from products import store as PST
            for key in (f"acct:{a}", f"web:{a}"):
                for r in await PST.STORE.conversations(key):
                    await PST.STORE.drop_conversation(key, r["product"])
        except Exception as e:
            print(f"product conversations not dropped: {type(e).__name__}")
        s, _ = await ops.ADMIN("DELETE", f"/admin/users/{a}", {})
        print(f"scratch guest {a[:8]} deleted (HTTP {s})")
    failed = [n for n, p, _ in RESULTS if not p]
    print(f"\ncore suites: {len(RESULTS) - len(failed)}/{len(RESULTS)} passed in {time.time() - t0:.0f}s" + (f" — FAILED: {failed}" if failed else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
