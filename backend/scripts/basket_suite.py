"""Sasha 198 · THE BASKET SUITE — part of the deploy gate (scripts/gate.py). Grows with each step R2–R10.

R2 holds the store itself (booking_signer/basket.py) on a scratch guest's scratch trip, in the real database, cleaned up after:
suggested → chosen (one per slice) → the total → held with the payment → Pacioli's booked line and event ledger; another account
can neither read nor choose; the ✕ removes one row. Conversation cases (web, avatar, WhatsApp) join at R5/R6.
"""
from __future__ import annotations

import asyncio
import os
import sys
import time
import uuid
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.flight_suite import RESULTS, ok  # noqa: E402 — one result list for the whole gate


def _flight(owner: str, n: str, amount: float, slice_key: str) -> dict:
    return {"provider": "duffel", "provider_ref": "off_suite_" + uuid.uuid4().hex[:10], "slice_key": slice_key, "day": "2026-11-12",
            "party": 2, "price_amount": amount, "price_currency": "EUR", "price_source": "quoted",
            "snapshot": {"owner": owner, "flights": n, "from": "MAD", "to": "HAN"}}


async def store_cases(a: str, other: str, trip: str) -> None:
    from booking_signer import basket as BK
    sk = "MAD-HAN 2026-11-12"
    fl = await BK.suggest(a, trip, "flight", [_flight("Iberia", "IB123", 900, sk), _flight("British Airways", "BA45", 950, sk),
                                              _flight("Duffel Airways", "ZZ1", 700, sk)], slice_key=sk)
    st = await BK.suggest(a, trip, "stay", [{"provider": "test_hotel", "day": "2026-11-12", "party": 2, "price_amount": 360,
                                             "price_currency": "EUR", "price_source": "placeholder", "snapshot": {"name": "Metropole Hanoi"}},
                                            {"provider": "test_hotel", "day": "2026-11-15", "party": 2, "price_amount": 240,
                                             "price_currency": "EUR", "price_source": "placeholder", "snapshot": {"name": "Hoi An Riverside"}}])
    rows = await BK.items(a, trip)
    ok("BASKET 1 (Magellan): 3 flights + 2 stays suggested, nothing chosen", len(rows) == 5 and not [r for r in rows if r["state"] != "suggested"],
       f"{len(rows)} rows")
    await BK.choose(a, fl[0])
    await BK.choose(a, fl[1])
    ch = [r for r in await BK.items(a, trip) if r["state"] == "chosen"]
    ok("BASKET 2 (Austen): the Iberia pick, then “actually the BA one” → exactly one chosen, BA",
       len(ch) == 1 and ch[0]["snapshot"]["owner"] == "British Airways", str([c["snapshot"]["owner"] for c in ch]))
    t = BK.total(await BK.items(a, trip))
    ok("BASKET 3: ONE total = the chosen flight + the kept stays, sources said", t["amount"] == 950 + 360 + 240 and t["currency"] == "EUR"
       and t["sources"] == ["placeholder", "quoted"], str(t))
    try:
        await BK.choose(other, fl[2])
        stolen = True
    except BK.BasketError:
        stolen = False
    ok("BASKET 4: another account can neither read nor choose this trip's items", not stolen and await BK.items(other, trip) == [])
    # a "restart": nothing in memory — a fresh read from the rows is the whole truth
    import importlib
    importlib.reload(BK)
    again = await BK.items(a, trip)
    ok("BASKET 5: after a restart the basket is the same (persisted, never in memory)",
       sorted((r["id"], r["state"]) for r in again) == sorted((r["id"], r["state"]) for r in await BK.items(a, trip)) and len(again) == 5)
    removed = await BK.remove(a, st[1])
    ok("BASKET 6: the ✕ removes exactly one row", removed and len(await BK.items(a, trip)) == 4)
    sid = "cs_suite_" + uuid.uuid4().hex[:12]
    held = await BK.hold(a, trip, sid)
    ok("BASKET 7 (Austen): the yes holds the chosen flight + the kept stay, with the payment session in the rows",
       len(held) == 2 and {r["kind"] for r in held} == {"flight", "stay"} and len(await BK.by_session(sid)) == 2)
    f = next(r for r in held if r["kind"] == "flight")
    b = await BK.booked(a, f["id"], booking_reference="SUITE1", order_id="ord_suite")
    ok("BASKET 8 (Pacioli): booked → its status line written from the record",
       b["state"] == "booked" and b["status_line"].startswith("✈️ British Airways BA45 MAD→HAN") and "ref SUITE1 (TEST)" in b["status_line"],
       b["status_line"])
    eid = "evt_suite_" + uuid.uuid4().hex[:10]
    first = await BK.event("suite", eid, "order.created", {"id": eid}, verified=True, item_id=f["id"])
    second = await BK.event("suite", eid, "order.created", {"id": eid}, verified=True, item_id=f["id"])
    ok("BASKET 9 (Pacioli): a provider event is recorded once (a redelivery is not a second)", first and not second)
    s2 = next(r for r in held if r["kind"] == "stay")
    x = await BK.failed(a, s2["id"], "the hotel refused (suite)")
    ok("BASKET 10 (Pacioli): a refused item says NOT booked, with why", x["state"] == "failed" and "NOT booked: the hotel refused" in x["status_line"],
       x["status_line"])


async def view_cases(a: str) -> None:
    """R3 · the plan's hotels become suggested stays; every surface's view shows each stay in its state; a revision keeps a chosen
    stay and never suggests it twice."""
    from booking_signer import basket as BK, plan_store as PS
    days = [{"day": 1, "city": "Hanoi", "hotel": {"name": "Sofitel Legend Metropole Hanoi", "price_from": 300}, "activities": []},
            {"day": 2, "city": "Hanoi", "hotel": None, "activities": []},
            {"day": 3, "city": "Hoi An", "hotel": {"name": "Anantara Hoi An", "price_from": 200}, "activities": []},
            {"day": 4, "city": "Hoi An", "hotel": None, "activities": []}]
    BK.ON = True
    try:
        trip = await PS.save(a, {"title": "Basket view suite", "days": days, "party": 2}, "from 12 November 2026 for 2", datetime.now(timezone.utc))
        st = [r for r in await BK.items(a, trip) if r["kind"] == "stay"]
        ok("BASKET R3-1 (Magellan): the plan's hotels → 2 suggested stays (2 nights Hanoi, 1 night Hoi An), priced as an ESTIMATE",
           [(r["snapshot"]["name"], r["snapshot"]["nights"], r["price_source"]) for r in st]
           == [("Sofitel Legend Metropole Hanoi", 2, "estimate"), ("Anantara Hoi An", 1, "estimate")], str([(r["snapshot"], r["price_amount"]) for r in st]))
        p = await PS.by_id(a, trip)
        v = await PS.view(a, p, [])
        ok("BASKET R3-2: the view (web, WhatsApp, voice) carries each night's stay in its state",
           [((d.get("stay") or {}).get("name"), (d.get("stay") or {}).get("words")) for d in v["days"]][:3]
           == [("Sofitel Legend Metropole Hanoi", "in your plan — not booked")] * 2 + [("Anantara Hoi An", "in your plan — not booked")],
           str([(d.get("date"), d.get("stay")) for d in v["days"]]))
        await BK.choose(a, st[0]["id"])
        t = "\n".join(PS.text(await PS.view(a, await PS.by_id(a, trip), [])))
        ok("BASKET R3-3: WhatsApp/voice text says the chosen stay as chosen, not booked", "🏨 Sofitel Legend Metropole Hanoi: chosen — not booked yet" in t, t[:200])
        await PS.save(a, {"title": "Basket view suite", "days": days, "party": 2}, "from 12 November 2026 for 2", datetime.now(timezone.utc))
        st2 = [(r["snapshot"]["name"], r["state"]) for r in await BK.items(a, trip) if r["kind"] == "stay"]
        ok("BASKET R3-4: a revision keeps the chosen stay and never suggests it twice",
           sorted(st2) == [("Anantara Hoi An", "suggested"), ("Sofitel Legend Metropole Hanoi", "chosen")], str(st2))
    finally:
        BK.ON = None


async def flight_cases(a: str) -> None:
    """R4 · ONE Duffel client: the guided flow's flights come through the one transport, each option carries the one card shape,
    and the flights shown are the basket's suggestions for the trip (Magellan)."""
    import types as _ty
    from booking_signer import basket as BK, travel as T
    import booking_signer.account as ACC
    from app.services.conductor import conduct
    from app.services import duffel as D
    seen = []
    real_http = T.HTTP

    async def spy(method, path, body=None, params=None):
        seen.append(path.split("?")[0])
        return await real_http(method, path, body, params)
    T.HTTP = spy
    BK.ON = True
    sid = "basket-r4-" + uuid.uuid4().hex[:6]
    h = []
    try:
        for m in ("plan me 6 days in Vietnam from 12 November for 2 of us", "Alex", "food and culture", "from Madrid", "yes please"):
            r = await conduct(m, h, user_id=a, signed_in=True, session_id=sid)
            h = r.get("messages") or h
        card = next((b for b in r.get("bookings") or [] if b.get("trip_pick")), None)
        opts = (card or {}).get("options") or []
        ok("BASKET R4-1: one Duffel client — the conversation's search went through the one transport",
           "/air/offer_requests" in seen and D._request.__doc__ and "ONE DUFFEL CLIENT" in D._request.__doc__, str(seen[:6]))
        ok("BASKET R4-2: every option carries the ONE card shape (id, owner, flights, from/to, departs, amount)",
           bool(opts) and all((o.get("card") or {}).get("id") == o.get("provider_offer_id") and (o.get("card") or {}).get("flights") for o in opts),
           str([(o.get("name"), (o.get("card") or {}).get("flights")) for o in opts][:4]))
        from booking_signer import plan_store as PS
        p = await PS.latest(a)
        sk = {r["slice_key"] for r in await BK.items(a, p["trip_id"]) if r["id"] in {o.get("basket_item_id") for o in opts}} if p else set()
        fl = [r for r in await BK.items(a, p["trip_id"]) if r["kind"] == "flight" and r["slice_key"] in sk] if p else []   # this search's slice
        ok("BASKET R4-3 (Magellan): the flights shown are the trip's suggested flights, one row each, linked by id",
           len(fl) == len(opts) and all(r["state"] == "suggested" and r["price_source"] == "quoted" for r in fl)
           and {o.get("basket_item_id") for o in opts} == {r["id"] for r in fl}, f"{len(fl)} rows, {len(opts)} options")
    finally:
        T.HTTP = real_http
        BK.ON = None


async def main() -> int:
    if os.getenv("SASHA_FLIGHT_SUITE", "") == "skip":
        print("basket suite SKIPPED (SASHA_FLIGHT_SUITE=skip) — this deploy is not covered")
        return 0
    from booking_signer import routes  # noqa: F401 — the Postgres stores
    from booking_signer import guest_accounts as GA, ops, plan_store as PS
    t0, start = time.time(), len(RESULTS)
    guests = []
    try:
        for n in ("basket-suite", "basket-suite-other"):
            g, why = await GA.create_guest(n)
            if not g:
                ok("basket suite: scratch guests", False, why)
                return 1
            guests.append(g["account_id"])
        a, other = guests
        trip = await PS.save(a, {"title": "Basket suite", "days": [{"day": 1, "city": "Hanoi", "activities": []}]},
                             "12 November for 2", datetime.now(timezone.utc))
        if not ok("basket suite: scratch trip", bool(trip)):
            return 1
        await store_cases(a, other, trip)
        await view_cases(a)
        await flight_cases(a)
    except Exception as e:
        ok("the basket suite itself", False, f"{type(e).__name__}: {e}")
    finally:
        try:
            run = PS._run()

            async def fn(conn):
                return await conn.execute("delete from basket_events where source = 'suite'")
            print(f"suite events cleaned: {await run(fn)}")
        except Exception as e:
            print(f"suite events NOT cleaned: {type(e).__name__}: {e}")
        for g in guests:   # the trip, its basket rows and its passengers go with the guest (on delete cascade)
            try:
                s, _ = await ops.ADMIN("DELETE", f"/admin/users/{g}", {})
                print(f"scratch guest {g[:8]} deleted (HTTP {s})")
            except Exception as e:
                print(f"scratch guest {g[:8]} NOT deleted: {type(e).__name__}")
    mine = RESULTS[start:]
    failed = [n for n, p, _ in mine if not p]
    print(f"\nbasket suite: {len(mine) - len(failed)}/{len(mine)} passed in {time.time() - t0:.0f}s" + (f" — FAILED: {failed}" if failed else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
