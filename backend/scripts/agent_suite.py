"""Sasha 203 · THE AGENT'S TOOLS, IN THE REAL DATABASE — part of the deploy gate (scripts/gate.py). AgAPI v0 called as any
client would, on a scratch guest (Duffel replayed in the gate), cleaned up after:

  · propose_trip: a plan, a flight chosen on EACH leg, and a total that equals the booking quote (and get_total)
  · choose_offer replaces only that leg's flight; the total changes with it and still equals the quote
  · hold_booking without travellers → travellers_missing (never placeholders)
  · book without an explicit yes → refused, nothing held; with a yes → ONE payment held in the rows; the same key → replayed
  · get_status says nothing is booked before payment — and the reply guard catches "it's booked"
"""
from __future__ import annotations

import asyncio
import os
import sys
import time
import uuid
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.flight_suite import RESULTS, ok  # noqa: E402


async def cases(a: str) -> None:
    from agapi import v0 as API
    from app.agent import sasha as AG
    from booking_signer import basket as BK, basket_book as BB
    ctx = API.Ctx(account=a, mode="test")
    start = (date.today() + timedelta(days=60)).isoformat()
    r = await API.call(ctx, "propose_trip", {"destination": "Vietnam", "start_date": start, "nights": 6, "party": 2,
                                             "interests": "food and beaches", "origin": "Madrid"})
    res = r.get("result") or {}
    t = await API.call(ctx, "get_total", {})
    q = await BB.quote(a, "Madrid")
    ok("AGENT 1 (Magellan): propose_trip → days with stays, a flight chosen on each leg, total = the quote = get_total",
       r.get("ok") and res.get("days") and res.get("flight_out") and res.get("flight_back")
       and abs(res["total_eur"] - q["eur"]) < 0.01 and abs(t["result"]["total_eur"] - q["eur"]) < 0.01,
       str({k: res.get(k) for k in ("total_eur",)}) + f" quote {q.get('eur')} · {r.get('error')}")
    out = await API.call(ctx, "search_flights", {"origin": "Madrid", "destination": "Hanoi",
                                                 "date": (date.fromisoformat(start) - timedelta(days=1)).isoformat(), "passengers": 2, "leg": "out"})
    other = next((f for f in (out.get("result") or {}).get("flights") or [] if f["airline"] != res["flight_out"]["airline"]), None)
    c = await API.call(ctx, "choose_offer", {"offer_id": other["offer_id"], "idempotency_key": "agent-suite-c1"}) if other else {}
    rows = await BK.items(a, res["trip_id"], ("chosen",))
    legs = sorted((x.get("slice_key") or "").split(":")[0] for x in rows if x["kind"] == "flight")
    q2 = await BB.quote(a, "Madrid")
    ok("AGENT 2 (Austen): choose_offer replaces only that leg — still ONE out and ONE back; the new total = the quote",
       c.get("ok") and legs == ["back", "out"] and abs(c["result"]["total_eur"] - q2["eur"]) < 0.01, f"legs {legs} · {c.get('error')}")
    h = await API.call(ctx, "hold_booking", {"idempotency_key": "agent-suite-h0"})
    ok("AGENT 3: hold_booking with no travellers on file → travellers_missing (never placeholders)",
       (h.get("error") or {}).get("code") == "travellers_missing", str(h.get("error")))
    await API.call(ctx, "save_travellers", {"idempotency_key": "agent-suite-s1", "travellers": [
        {"given_name": "Alex", "family_name": "Smith", "date_of_birth": "1985-03-12", "title": "mr"},
        {"given_name": "Sam", "family_name": "Smith", "date_of_birth": "1987-05-02", "title": "ms"}]})
    h = await API.call(ctx, "hold_booking", {"idempotency_key": "agent-suite-h1"})
    sha = (h.get("result") or {}).get("read_back_sha256")
    ok("AGENT 4 (Sherlock via hold_booking): the read-back and its total; nothing held yet",
       h.get("ok") and sha and not await BK.items(a, res["trip_id"], ("pending_payment",)), str(h.get("error")))
    no = await API.call(ctx, "book", {"read_back_sha256": sha, "idempotency_key": "agent-suite-b0",
                                      "approval": {"said": "No. What's the total with the flight and lodging?"}})
    ok("AGENT 5: book without an explicit yes → refused; nothing held",
       (no.get("error") or {}).get("code") == "no_explicit_yes" and not await BK.items(a, res["trip_id"], ("pending_payment",)))
    yes = await API.call(ctx, "book", {"read_back_sha256": sha, "idempotency_key": "agent-suite-b1", "approval": {"said": "Then book it."}})
    again = await API.call(ctx, "book", {"read_back_sha256": sha, "idempotency_key": "agent-suite-b1", "approval": {"said": "Then book it."}})
    held = await BK.items(a, res["trip_id"], ("pending_payment",))
    ok("AGENT 6 (Austen): “Then book it.” → ONE payment, the rows hold it; the same key → replayed, never a second",
       yes.get("ok") and again.get("replayed") and held and len({x["paid_session"] for x in held}) == 1
       and yes["result"]["booked"] is False, f"{len(held)} held · {yes.get('error')}")
    st = await API.call(ctx, "get_status", {})
    ok("AGENT 7 (Pacioli): before payment nothing is booked — and the reply guard catches “it's all booked”",
       st.get("ok") and not st["result"]["anything_booked"] and AG.guard_check("Great — it's all booked!", set(), st["result"]["anything_booked"]))


async def quiver_cases() -> None:
    """Sasha 204 · never silent — a scripted model, real timing: a quiver line before a slow tool's result, at ~0.9 s of silence,
    and none when the answer is quick."""
    from app.agent.fakes import quiver_checks
    for name, (good, detail) in (await quiver_checks()).items():
        ok(f"AGENT QUIVER: {name}", good, detail[:180])


async def main() -> int:
    if os.getenv("SASHA_FLIGHT_SUITE", "") == "skip":
        print("agent suite SKIPPED (SASHA_FLIGHT_SUITE=skip) — this deploy is not covered")
        return 0
    from booking_signer import routes  # noqa: F401
    from booking_signer import guest_accounts as GA, ops, plan_store as PS
    t0, start = time.time(), len(RESULTS)
    g, why = await GA.create_guest("agent-suite")
    if not g:
        ok("agent suite: scratch guest", False, why)
        return 1
    a = g["account_id"]
    try:
        await cases(a)
        await quiver_cases()
    except Exception as e:
        ok("the agent suite itself", False, f"{type(e).__name__}: {e}")
    finally:
        try:
            run = PS._run()

            import hashlib
            mine = [hashlib.sha256(f"{a}:{n}:{k}".encode()).hexdigest()[:40] for n, k in (
                ("choose_offer", "agent-suite-c1"), ("save_travellers", "agent-suite-s1"), ("hold_booking", "agent-suite-h1"),
                ("book", "agent-suite-b1"))]

            async def fn(conn):   # exactly its own events: its items' (payments) and its own idempotency keys
                await conn.execute("delete from basket_events where item_id in (select id from trip_basket_items where account_id = $1)", uuid.UUID(a))
                return await conn.execute("delete from basket_events where source = 'agapi' and event_id = any($1::text[])", mine)
            await run(fn)
        except Exception as e:
            print(f"agent suite events not cleaned: {type(e).__name__}")
        try:
            s, _ = await ops.ADMIN("DELETE", f"/admin/users/{a}", {})
            print(f"scratch guest {a[:8]} deleted (HTTP {s})")
        except Exception as e:
            print(f"scratch guest {a[:8]} NOT deleted: {type(e).__name__}")
    mine = RESULTS[start:]
    failed = [n for n, p, _ in mine if not p]
    print(f"\nagent suite: {len(mine) - len(failed)}/{len(mine)} passed in {time.time() - t0:.0f}s" + (f" — FAILED: {failed}" if failed else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
