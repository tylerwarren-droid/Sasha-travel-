"""Sasha 211 Part B · VENUE BOOKINGS ON THE AGENT, every route — part of the deploy gate (scripts/gate.py).

  REAL, in-process, on a scratch guest: our own Sasha Test Venue (its form) — read → hold_venue (the read-back) → book_venue
  refused in the same turn → the yes in the next turn → their confirmation page → CONFIRMED in Pacioli's rows (get_status),
  then cancel_venue's two steps. No real venue is contacted.
  EVERY OTHER ROUTE, against a stand-in for the booking API (it records what was asked of it; nothing leaves the process):
  the ladder's question (> 48 h: email them / book now; within 48 h: their page / a call), the platform page to the phone,
  the email, the call, the form filled in the cloud browser with "Tap to finish" on the phone (the founder's override), the
  WhatsApp-only draft — and never a send without the person's explicit yes in a LATER turn.
"""
from __future__ import annotations

import asyncio
import os
import sys
import time
import uuid
from datetime import date, datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.flight_suite import RESULTS, ok  # noqa: E402


def _ctx(a: str, said: str = ""):
    from agapi import v0 as API
    return API.Ctx(account=a, mode="test", user_said=said)


async def real_test_venue(a: str) -> None:
    from agapi import v0 as API
    from booking_signer import guest_whatsapp as GW
    from booking_signer.form_rung import test_venue_url
    s, cj = await GW.api(a, "GET", "/api/booking/contact")
    c = (cj or {}).get("consent") or {}
    s, j = await GW.api(a, "PUT", "/api/booking/contact", {"name": "Alex Gate", "mobile": "+447700900211",
                                                            "consent_version": c.get("version"), "consent_sha256": c.get("sha256")})
    ok("VENUE 0: a scratch guest with a contact (fictional, Ofcom's drama range)", s == 200, str(j)[:160])
    day = (date.today() + timedelta(days=4)).isoformat()
    v = {"name": "Sasha Test Venue", "city": "Madrid", "country": "ES", "website": test_venue_url("plain"), "what": "dinner"}
    r = await API.call(_ctx(a), "read_booking_route", v)
    ok("VENUE 1 (Sherlock): read_booking_route reads the venue's routes through the booking API",
       r.get("ok") and "form" in r["result"]["routes"], str(r.get("error") or r.get("result"))[:200])
    turn1 = _ctx(a, "Book it, the form please")
    h = await API.call(turn1, "hold_venue", {**v, "day": day, "time": "21:00", "party": 2, "route": "form", "idempotency_key": "venue-suite-h1"})
    ok("VENUE 2 (Austen): hold_venue → the read-back, nothing sent", h.get("ok") and h["result"]["status"] == "awaiting_yes" and h["result"]["route"] == "form",
       str(h.get("error") or h.get("result"))[:200])
    same = await API.call(turn1, "book_venue", {"approval": {"said": "Yes"}, "idempotency_key": "venue-suite-b0"})
    ok("VENUE 3: a yes in the SAME turn as the read-back books nothing", (same.get("error") or {}).get("code") == "read_back_first", str(same)[:160])
    no = await API.call(_ctx(a, "hmm, maybe"), "book_venue", {"approval": {"said": "hmm, maybe"}, "idempotency_key": "venue-suite-b1"})
    ok("VENUE 4: without an explicit yes, nothing is sent", (no.get("error") or {}).get("code") == "no_explicit_yes", str(no)[:160])
    b = await API.call(_ctx(a, "Yes, book it"), "book_venue", {"approval": {"said": "Yes, book it"}, "idempotency_key": "venue-suite-b2"})
    res = b.get("result") or {}
    ok("VENUE 5 (the form route, REAL — our test venue): the yes in the next turn → sent → their page confirms → CONFIRMED",
       b.get("ok") and res.get("status") == "confirmed", str(b.get("error") or res)[:220])
    st = await API.call(_ctx(a), "get_status", {})
    vb = (st.get("result") or {}).get("venues") or []
    ok("VENUE 6 (Pacioli): get_status lists it on its day, Confirmed — and only then does anything count as booked",
       st.get("ok") and any(x["date"] == day and x["status"] == "confirmed" for x in vb) and st["result"]["anything_booked"],
       str(vb)[:220])
    tid = next((x["trip_item_id"] for x in vb if x["date"] == day), None)
    c1 = await API.call(_ctx(a, "Cancel it"), "cancel_venue", {"trip_item_id": tid, "idempotency_key": "venue-suite-c1"})
    ok("VENUE 7: cancel_venue → its read-back first, back the way it was made; nothing sent yet",
       c1.get("ok") and c1["result"]["status"] == "awaiting_yes", str(c1.get("error") or c1.get("result"))[:200])


class FakeApi:
    """The booking API as the routes answer it — records every call; nothing leaves the process."""
    def __init__(self):
        self.calls = []

    async def __call__(self, account, method, path, body=None, timeout=90.0):
        self.calls.append((method, path, body))
        if path == "/api/booking/draft":
            return 200, {"parts": {"what": {"category": "restaurant", "activity": "table"}}}
        if path == "/api/booking/contact":
            return 200, {"contact": {"name": "Alex Gate", "mobile_e164": "+447700900211"}}
        if path == "/api/booking/forms":
            if body.get("handover"):
                return 200, {"form_id": "f-1", "trip_item_id": "t-1", "read_back": {"lines": ["I'll fill their booking page"], "sha256": "a" * 64}}
            return 403, {"rule": "forms_off", "message": "forms are off"}
        if path == "/api/booking/forms/f-1/handover":
            return 200, {"ok": True, "phone": {"sent": True}, "handover_id": "h-1"}
        if path == "/api/booking/links":
            return 200, {"link_id": "l-1", "trip_item_id": "t-2", "platform": "TheFork", "slot_filled": True,
                         "url": "https://www.thefork.es/restaurante/x-r1", "read_back": {"lines": ["their TheFork page"], "sha256": "b" * 64}}
        if path == "/api/booking/links/l-1/opened":
            return 200, {"url": "https://www.thefork.es/restaurante/x-r1", "status": "link_sent"}
        if path == "/api/booking/emails":
            return 200, {"email_id": "e-1", "trip_item_id": "t-3", "read_back": {"lines": ["I'll email them"], "sha256": "c" * 64}}
        if path == "/api/booking/emails/e-1/send":
            return 200, {"status": "sent", "say": "sent"}
        if path == "/api/booking/calls":
            return 200, {"call_id": "k-1", "trip_item_id": "t-4", "read_back": {"lines": ["I'll call them"], "sha256": "d" * 64}}
        if path == "/api/booking/calls/k-1/place":
            return 200, {"status": "placed"}
        return 404, {"rule": "unknown", "message": path}


async def routes_offline(a: str) -> None:
    from agapi import v0 as API, venues as VN
    from booking_signer import guest_accounts as GA, guest_whatsapp as GW, wa_brain as WB
    real = (GW.api, GW.tap_platform, VN._read, GA.founder, WB.trip_day_words)
    taps = []
    fake = FakeApi()

    def read_with(rungs: dict, facts=None):
        async def rd(ctx, args):
            return {"read_id": "r-1", "country": "ES", "venue": "Casa Gate", "facts": facts or [], "rungs": rungs,
                    "open_now": True, "opens_at": None, "say": ""}
        return rd

    async def tap(account, text, url, link_id=None, venue=None, when=None):
        taps.append(url)
        return "sent (captured)"

    async def where(account, day, venue):
        return "It's in your bookings"
    GW.api, GW.tap_platform, WB.trip_day_words = fake, tap, where
    GA.founder = lambda acct: True
    soon = (datetime.now() + timedelta(hours=20)).strftime("%Y-%m-%d %H:%M").split()
    later = (date.today() + timedelta(days=6)).isoformat()
    v = {"name": "Casa Gate", "city": "Madrid", "country": "ES", "what": "dinner", "party": 2}

    async def two_turns(args: dict, key: str) -> tuple:
        h = await API.call(_ctx(a, "book it"), "hold_venue", {**v, **args, "idempotency_key": key + "h"})
        b = await API.call(_ctx(a, "Yes"), "book_venue", {"approval": {"said": "Yes"}, "idempotency_key": key + "b"})
        return h, b
    try:
        VN._HELD.pop(a, None)
        VN._read = read_with({"link": {"value": "TheFork"}, "email": {}, "phone": {"fact_index": 0}})   # a platform venue
        q = await API.call(_ctx(a, "book it"), "hold_venue", {**v, "day": later, "time": "21:00", "idempotency_key": "vo-q1"})
        opts = {o["route"] for o in (q.get("result") or {}).get("options") or []}
        ok("VENUE ROUTE · more than 48 h away → the ladder's question first (email them, or book now), nothing prepared",
           q.get("ok") and q["result"]["status"] == "choose_route" and "email" in opts and a not in VN._HELD,
           str(q.get("result"))[:200])
        q2 = await API.call(_ctx(a, "book it"), "hold_venue", {**v, "day": soon[0], "time": soon[1], "idempotency_key": "vo-q2"})
        opts2 = {o["route"] for o in (q2.get("result") or {}).get("options") or []}
        ok("VENUE ROUTE · within 48 h → book now (their page) or a call", q2.get("ok") and q2["result"]["status"] == "choose_route"
           and {"page", "call"} <= opts2, str(q2.get("result"))[:200])
        VN._read = read_with({"form": {}, "link": {"value": "TheFork"}, "email": {}, "phone": {"fact_index": 0}})
        d = await API.call(_ctx(a, "book it"), "hold_venue", {**v, "day": later, "time": "21:00", "idempotency_key": "vo-q3"})
        ok("VENUE ROUTE · their own form, no CAPTCHA, more than 48 h away → “I can book it directly — shall I?”",
           d.get("ok") and d["result"]["status"] == "choose_route" and "form" in {o["route"] for o in d["result"]["options"]},
           str(d.get("result"))[:160])
        h, b = await two_turns({"day": later, "time": "21:00", "route": "page"}, "vo-p")
        ok("VENUE ROUTE · page (a platform): the real page goes to the phone on the yes — never fetched by Sasha",
           h.get("ok") and b.get("ok") and b["result"]["status"] == "page_on_phone" and taps == ["https://www.thefork.es/restaurante/x-r1"],
           f"{b.get('error') or b.get('result')} taps={taps}")
        h, b = await two_turns({"day": later, "time": "21:00", "route": "email"}, "vo-e")
        ok("VENUE ROUTE · email: sent on the yes, Requested until they reply",
           b.get("ok") and b["result"]["status"] == "requested" and ("POST", "/api/booking/emails/e-1/send") in [(m, p) for m, p, _ in fake.calls],
           str(b.get("error") or b.get("result"))[:160])
        h, b = await two_turns({"day": soon[0], "time": soon[1], "route": "call"}, "vo-c")
        ok("VENUE ROUTE · call: placed on the yes (its reading decides)", b.get("ok") and b["result"]["status"] == "placed",
           str(b.get("error") or b.get("result"))[:160])
        h, b = await two_turns({"day": later, "time": "21:00", "route": "form"}, "vo-f")
        ok("VENUE ROUTE · form (the founder's override): filled in the cloud browser; the human step → Tap to finish on the phone",
           h.get("ok") and h["result"]["route"] == "handover" and b.get("ok") and b["result"]["status"] == "tap_to_finish" and b["result"]["on_phone"],
           f"{h.get('error') or h.get('result', {}).get('route')} · {b.get('error') or b.get('result')}")
        VN._read = read_with({"whatsapp": {"value": "+34 600 000 211"}})
        w = await API.call(_ctx(a, "book it"), "hold_venue", {**v, "day": later, "time": "21:00", "idempotency_key": "vo-w"})
        ok("VENUE ROUTE · WhatsApp-only: the drafted message (they send it), nothing sent by Sasha",
           w.get("ok") and w["result"]["status"] == "draft_message" and "wa.me/34600000211" in w["result"].get("open_in_whatsapp", ""),
           str(w.get("error") or w.get("result"))[:200])
        n0 = len(fake.calls)
        VN._read = read_with({"email": {}})
        await API.call(_ctx(a, "book it"), "hold_venue", {**v, "day": later, "time": "21:00", "route": "email", "idempotency_key": "vo-n"})
        nb = await API.call(_ctx(a, "no, wait"), "book_venue", {"approval": {"said": "no, wait"}, "idempotency_key": "vo-nb"})
        ok("VENUE ROUTE · “no, wait” never sends", (nb.get("error") or {}).get("code") == "no_explicit_yes"
           and not any(p.endswith("/send") for _, p, _ in fake.calls[n0:]), str(nb.get("error")))
    finally:
        GW.api, GW.tap_platform, VN._read, GA.founder, WB.trip_day_words = real
        VN._HELD.pop(a, None)


async def main() -> int:
    if os.getenv("SASHA_FLIGHT_SUITE", "") == "skip":
        print("venue suite SKIPPED (SASHA_FLIGHT_SUITE=skip) — this deploy is not covered")
        return 0
    from booking_signer import routes  # noqa: F401
    from booking_signer import guest_accounts as GA, ops, plan_store as PS
    t0, start = time.time(), len(RESULTS)
    g, why = await GA.create_guest("venue-suite")
    if not g:
        ok("venue suite: scratch guest", False, why)
        return 1
    a = g["account_id"]
    try:
        await real_test_venue(a)
        await routes_offline(a)
    except Exception as e:
        ok("the venue suite itself", False, f"{type(e).__name__}: {e}")
    finally:
        try:
            s, _ = await ops.ADMIN("DELETE", f"/admin/users/{a}", {})
            print(f"scratch guest {a[:8]} deleted (HTTP {s})")
        except Exception as e:
            print(f"scratch guest {a[:8]} NOT deleted: {type(e).__name__}")
    mine = RESULTS[start:]
    failed = [n for n, p, _ in mine if not p]
    print(f"\nvenue suite: {len(mine) - len(failed)}/{len(mine)} passed in {time.time() - t0:.0f}s" + (f" — FAILED: {failed}" if failed else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
