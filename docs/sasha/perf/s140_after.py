"""Sasha 140 · PERFORMANCE — p50/p95 per step, founder's account, in-process (the same code the server runs), real services.
WhatsApp path (simulated, nothing sent): intent → venue search (Places) → photos (venues' own sites) → cards shown →
read-back (venue read of the pick) → booking (our test venue's form) → payment (a Stripe TEST checkout page, unpaid).
Web path: conduct() → the find (the same /venues/find the web card calls).
Usage: s140_perf.py <label> [reps]   — writes s140_<label>.json"""
import asyncio, json, statistics, sys, time
from datetime import datetime, timezone, timedelta
sys.path.insert(0, "/Users/tylerwarren/Developer/Sasha-travel-/backend")
from booking_signer import routes  # noqa
from booking_signer import guest_whatsapp as GW, handoff as HO, test_deposit as TD
from booking_signer.form_rung import test_venue_url

A = "11111111-1111-4111-8111-111111111111"
LABEL = sys.argv[1] if len(sys.argv) > 1 else "run"
REPS = int(sys.argv[2]) if len(sys.argv) > 2 else 3
KINDS = {"restaurant": "dinner", "hotel": "hotel", "spa": "spa", "tattoo": "tattoo studio"}   # the pre-warm list's own queries
CITIES = {"Madrid": "ES", "Hoi An": "VN", "Hanoi": "VN"}
T = {}


def rec(step, secs):
    T.setdefault(step, []).append(secs)


def pct(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, max(0, round(p / 100 * (len(xs) - 1))))]


LIMIT = 45.0


async def timed(step, coro):
    t = time.perf_counter()
    try:
        r = await asyncio.wait_for(coro, LIMIT)
    except asyncio.TimeoutError:
        rec(step, LIMIT)
        rec(f"{step} TIMEOUTS", 1)
        print(f"  TIMEOUT {step} (> {LIMIT:.0f}s)", flush=True)
        return None
    rec(step, time.perf_counter() - t)
    print(f"  {step}: {time.perf_counter() - t:.1f}s", flush=True)
    return r


async def one(kind, what, city, country):
    t_all = time.perf_counter()
    msg = f"{what} for 2 in {city} tomorrow at 9pm" if kind == "restaurant" else f"{what} in {city}"
    t = time.perf_counter()
    h = HO.booking_handoff(msg, [], datetime.now(timezone.utc))
    rec(f"{kind}·intent", time.perf_counter() - t)
    f = await timed(f"{kind}·search", GW.api(A, "POST", "/api/booking/venues/find", {"what": what, "where": city, "country": country}))
    if f is None:
        return
    s, f = f
    cands = (f or {}).get("candidates") or []
    order = ((f or {}).get("ranking") or {}).get("orders", {}).get("rated") or [c["place_id"] for c in cands]
    by = {c["place_id"]: c for c in cands}
    shown = [by[i] for i in order if i in by and i != "sasha-test-venue"][:3]
    got = await timed(f"{kind}·photos (within the budget)", GW._photos_within(shown, GW.photo_wait())) or ({}, [])
    photos, late = got
    rec(f"{kind}·cards shown", time.perf_counter() - t_all)
    for x in late:
        x.cancel()
    rec(f"{kind}·photo hit rate", len(photos) / max(1, len(shown)))
    if shown:
        c = shown[0]
        await timed(f"{kind}·read-back (venue read)", GW.api(A, "POST", "/api/booking/venues/read",
                                                             {"name": c["name"], "city": city, "country": country, "place_id": c["place_id"], "asked_for": what}))


async def booking_and_payment():
    r0 = await timed("booking·venue read (test venue)", GW.api(A, "POST", "/api/booking/venues/read",
                                                                  {"name": "Sasha Test Venue", "city": "Madrid", "country": "ES", "website": test_venue_url()}))
    if not r0:
        return
    s, rd = r0
    day = (datetime.now(timezone.utc) + timedelta(days=9)).date().isoformat()
    res = {"schema": "reservation/1", "flow": "book", "who": {"name": "Tyler Warren", "contact": {"mobile_e164": "+34600000000", "email": "guest@example.com"}},
           "what": {"activity": "a table", "activity_venue_lang": "una mesa", "category": "restaurant"}, "where": {},
           "when": {"mode": "at", "at": f"{day}T21:00"}, "how_many": {"count": 2, "unit": "people"}}
    r1 = await timed("booking·form read-back", GW.api(A, "POST", "/api/booking/forms", {"read_id": rd["read_id"], "reservation": res}))
    if not r1:
        return
    s, fm = r1
    sent = await timed("booking·form sent + their page read", GW.api(A, "POST", f"/api/booking/forms/{fm['form_id']}/send",
                                                                         {"read_back_sha256": fm["read_back"]["sha256"], "approval": {"how": "button"}}, timeout=120))
    await timed("payment·Stripe TEST page made", TD.checkout("10.00", "EUR", "perf test — not paid", "s140"))


async def web(kind, what, city):
    from app.services import conductor as CD
    msg = f"{what} for 2 in {city} tomorrow at 9pm" if kind == "restaurant" else f"{what} in {city}"
    t = time.perf_counter()
    try:
        out = await asyncio.wait_for(CD.conduct(msg, [], user_id=A), 90)
    except asyncio.TimeoutError:
        out = {}
        print(f"  TIMEOUT web {kind} {city}", flush=True)
    print(f"  web·{kind}·{city}: {time.perf_counter() - t:.1f}s", flush=True)
    rec(f"web·{kind}·conduct", time.perf_counter() - t)
    rec(f"web·{kind}·path", 0 if out.get("booking_find") else 1)   # 0 = deterministic find; 1 = the model path


async def warm():
    from booking_signer import demo_ops as DO
    t = time.perf_counter()
    for i in range(0, len(DO.DEMO_QUERIES), 4):
        async def one(what, where, country):
            s, f = await GW.api(A, "POST", "/api/booking/venues/find", {"what": what, "where": where, "country": country})
            by = {c["place_id"]: c for c in (f or {}).get("candidates") or []}
            order = [p for p in ((f.get("ranking") or {}).get("orders") or {}).get("rated") or list(by) if p in by and p != "sasha-test-venue"]
            top = [by[p] for p in order[:3]]
            await GW._photos(A, what, top)
            await asyncio.gather(*(GW.api(A, "POST", "/api/booking/venues/read", {"name": c.get("name"), "city": where, "country": country,
                                                                                    "place_id": c["place_id"], "asked_for": what}) for c in top))
        await asyncio.gather(*(one(*q) for q in DO.DEMO_QUERIES[i:i + 4]))
    print(f"pre-warm took {time.perf_counter() - t:.0f}s", flush=True)


async def main():
    if "warm" in LABEL:
        await warm()
    for r in range(REPS):
        for kind, what in KINDS.items():
            for city, country in CITIES.items():
                print(f"[{r + 1}] {kind} · {city}", flush=True)
                try:
                    await one(kind, what, city, country)
                except Exception as e:
                    print("error", kind, city, type(e).__name__, e, flush=True)
        await booking_and_payment()
        print(f"rep {r + 1}/{REPS} done", flush=True)
    for kind, what in KINDS.items():
        for city in ("Madrid", "Hanoi"):
            await web(kind, what, city)
    s, j = await GW.api(A, "POST", "/api/booking/ops/demo/reset")
    out = {k: {"n": len(v), "p50": round(statistics.median(v), 2), "p95": round(pct(v, 95), 2)} for k, v in sorted(T.items())}
    json.dump(out, open(f"/private/tmp/claude-501/-Users-tylerwarren-Developer-Applied-Diligence/8d68a04a-6c8c-489d-b582-8929ecc935eb/scratchpad/s140_{LABEL}.json", "w"), indent=1)
    for k, v in out.items():
        print(f"{k:42} n={v['n']:3} p50={v['p50']:6.2f}  p95={v['p95']:6.2f}")

asyncio.run(main())
