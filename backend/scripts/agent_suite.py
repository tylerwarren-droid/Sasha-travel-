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
    t0 = time.perf_counter()
    pr = await API.call(ctx, "prepare_trip", {"destination": "Vietnam", "start_date": start, "nights": 6, "party": 2, "origin": "Madrid"})
    t_prep = time.perf_counter() - t0
    await asyncio.sleep(0)
    await asyncio.sleep(float(os.getenv("AGENT_SUITE_PREP_WAIT", "6")))   # the intake goes on while it prepares
    t1 = time.perf_counter()
    r = await API.call(ctx, "propose_trip", {"destination": "Vietnam", "start_date": start, "nights": 6, "party": 2,
                                             "interests": "food and beaches", "origin": "Madrid"})
    t_prop = time.perf_counter() - t1
    print(f"   timing · propose_trip after prepare: {t_prop:.2f}s (this host)", flush=True)
    ok("AGENT 0 (Sasha 205): prepare_trip returns at once, and propose_trip USES the prepared itinerary and flights",
       pr.get("ok") and t_prep < 0.5 and (r.get("result") or {}).get("prefetched") == {"itinerary": True, "flights": True},
       f"prepare {t_prep:.2f}s · propose {t_prop:.2f}s · {(r.get('result') or {}).get('prefetched')} · {r.get('error')}")
    res = r.get("result") or {}
    t = await API.call(ctx, "get_total", {})
    q = await BB.quote(a, "Madrid")
    ok("AGENT 1 (Magellan): propose_trip → days with stays, a flight chosen on each leg, total = the quote = get_total",
       r.get("ok") and res.get("days") and res.get("flight_out") and res.get("flight_back")
       and abs(res["total_eur"] - q["eur"]) < 0.01 and abs(t["result"]["total_eur"] - q["eur"]) < 0.01,
       str({k: res.get(k) for k in ("total_eur",)}) + f" quote {q.get('eur')} · {r.get('error')}")
    fo = res.get("flight_options") or {}
    ev = AG.render("propose_trip", res, {})
    ok("AGENT 1b (Sasha 210): the proposal arrives WITH a range of flights per leg (3–5, tagged), the chosen one marked — as cards",
       all(3 <= len(fo.get(leg) or []) <= 5 and sum(1 for f in fo[leg] if f["chosen"]) == 1
           and fo[leg][[f["chosen"] for f in fo[leg]].index(True)]["offer_id"] == res[f"flight_{leg}"]["offer_id"] for leg in ("out", "back"))
       and len((ev or {}).get("cards") or []) == 2 and all(any(o["chosen"] for o in c["options"]) for c in ev["cards"]),
       f"{ {k: len(v) for k, v in fo.items()} }")
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
    same = await API.call(ctx, "book", {"idempotency_key": "agent-suite-b-same", "approval": {"said": "Book it."}})
    ok("AGENT 4b (Sasha 210): “book it” and the read-back in ONE turn → no payment yet: the yes answers a read-back they heard",
       (same.get("error") or {}).get("code") == "read_back_first" and not await BK.items(a, res["trip_id"], ("pending_payment",)),
       str(same.get("error")))
    ctx = API.Ctx(account=a, mode="test")   # Sasha 210 · the yes comes in the NEXT turn, after the read-back was said
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
    await paid_cases(a, yes)


async def paid_cases(a: str, yes: dict) -> None:
    """Sasha 212 · PAY → EVENT → UTTERANCE → EMAIL: the payment is simulated (Stripe says paid); everything after it is real —
    paid_watch.settle books it (Duffel replayed), Pacioli records it, the open page hears ONE event with what she says (no
    figures in the spoken words) and the itinerary card, and the confirmation email is queued (captured, not sent)."""
    import re as _re
    from booking_signer import guest_receipt as GR, live_events as LE, paid_watch as PW, test_deposit as TD
    sid = ((yes or {}).get("result") or {}).get("session_id")
    real = (TD.session_paid, LE.SEND, GR.address_of)
    mails = []

    async def paid(_sid):
        return True

    async def capture(msg):
        mails.append(msg)
        return {"sent": True}

    async def addr(_acct):
        return "gate@example.com"
    q = LE.subscribe(a)
    TD.session_paid, LE.SEND, GR.address_of = paid, capture, addr
    try:
        r = await PW.settle(sid) if sid else None
    finally:
        TD.session_paid, LE.SEND, GR.address_of = real
        LE.unsubscribe(a, q)
    evs = []
    while not q.empty():
        evs.append(q.get_nowait())
    ev = evs[0] if evs else {}
    ok("AGENT 8 (Sasha 212): paid → booked by Pacioli → ONE event to the open page → she says it (no figures spoken) → the email queued",
       (r or {}).get("status") == "booked" and len(evs) == 1 and ev.get("type") == "booked" and "you're booked" in ev.get("text", "")
       and "gate@example.com" in ev.get("text", "") and not _re.search(r"\d", ev.get("spoken", "").replace("gate at example dot com", ""))
       and (ev.get("card") or {}).get("url", "").endswith("/next?tab=trip") and len(mails) == 1 and mails[0]["to"] == "gate@example.com"
       and "TEST" in mails[0]["subject"] and ev["card"]["url"] in mails[0]["text"],
       f"settle {(r or {}).get('status')} · events {[e.get('type') for e in evs]} · mails {len(mails)} · {ev.get('text', '')[:120]}")


async def render_cases() -> None:
    """Sasha 205 · every tool's result type has a renderer in the /next UI."""
    from agapi import v0 as API
    from app.agent import sasha as AG
    missing = sorted(set(API.BY_NAME) - set(AG.RENDER))
    ok("AGENT RENDER: every tool's result has a renderer (venues → photo cards, flights/stays → cards, trip → the Trip view…)",
       not missing and set(AG.RENDER.values()) <= AG.KINDS | AG.KINDS_S2_ONLY, f"missing {missing}")   # Sasha 224 · /s2's own kinds (S2App)
    card = {"place_id": "ChIJ-gate-1", "name": "Casa Gate", "address": "Calle Mayor 1, 28013 Madrid, Spain", "rating": 4.6}
    res = {"venues": [{"name": "Casa Gate"}], "ribbon": "1 dinner in Madrid", "find": {"what": "dinner", "where": "Madrid"},
           "preset": {"all": [card], "cards": [card], "show": 1}}
    ev = AG.render("search_venues", res, {"what": "dinner", "where": "Madrid"})
    ok("AGENT RENDER (Sasha 213): search_venues' cards ARE its result (no second search) — the same cards, the same ribbon",
       (ev or {}).get("kind") == "venues" and ev["preset"]["cards"] == [card] and ev["ribbon"] == "1 dinner in Madrid", str(ev)[:200])


async def quiver_cases() -> None:
    """Sasha 204/205 · never silent — a scripted model, real timing: an acknowledgement before a slow tool's result and at ~0.9 s
    of silence, none when the answer is quick; and acknowledgements never repeat and never carry a fact."""
    from app.agent.fakes import quiver_checks
    for name, (good, detail) in (await quiver_checks()).items():
        ok(f"AGENT FILLER: {name}", good, detail[:180])


async def main() -> int:
    from scripts import places_fake   # Sasha 213 · NO live Google Places from a suite (it costs money) — the founder's say-so only
    places_fake.install()
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
        await render_cases()
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
