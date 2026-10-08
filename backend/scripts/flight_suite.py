"""Sasha 193 · THE FLIGHT REGRESSION SUITE — real Duffel TEST calls on a scratch guest, cleaned up after.

Runs as Railway's preDeployCommand (railway.json): a failure BLOCKS the deploy (the old one keeps serving). Locally:
    railway run python -m scripts.flight_suite        (from backend/)
SASHA_FLIGHT_SUITE=skip skips it (an emergency deploy, said in its log); never the default.

Each case ends where a script can honestly end: the Stripe TEST checkout is CREATED for real; the payment itself is a person's
tap on a phone, so it is marked paid here (the one simulated step, said in the output); then the booking after payment runs
for real (Duffel TEST order) and the row is checked in the guest's own list.
"""
from __future__ import annotations

import asyncio
import json
import random
import os
import re
import sys
import time
import types
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

RESULTS: list = []


def ok(name: str, cond: bool, detail: str = "") -> bool:
    RESULTS.append((name, bool(cond), detail))
    print(f"{'PASS' if cond else 'FAIL'} · {name}{(' — ' + detail) if detail else ''}", flush=True)
    return bool(cond)


class Req:
    def __init__(self, a, body=None, q=None):
        self._b, self.query_params, self.headers, self.state, self._a = body or {}, q or {}, {}, types.SimpleNamespace(), a

    async def json(self):
        return self._b


def _airline(card: dict, prefer=("Iberia", "British Airways", "Duffel Airways")) -> str:
    names = [o.get("name") for o in (card or {}).get("options") or [] if o.get("provider") == "duffel"]
    return next((p for p in prefer if p in names), names[0] if names else "")


def _resp(r) -> dict:
    return r if isinstance(r, dict) else json.loads(r.body)


async def _pay_and_settle(a: str, prepare, pay, body: dict, label: str) -> bool:
    """read-back → pay (a real Stripe TEST checkout) → [paid, simulated] → settled → booked."""
    from booking_signer import paid_watch as PW, test_deposit as TD
    p = _resp(await prepare(Req(a, body)))
    if not ok(f"{label}: read-back", p.get("ok") and (p.get("read_back") or {}).get("sha256"), str(p.get("message") or "")[:120]):
        return False
    q = _resp(await pay(Req(a, {**body, **({"offer_id": p["offer_id"]} if p.get("offer_id") else {}),
                                 "read_back_sha256": p["read_back"]["sha256"], "approval": {"how": "chat", "said": "yes"}})))
    if not ok(f"{label}: Stripe TEST checkout", q.get("ok") and "checkout.stripe.com" in str(q.get("url")), str(q.get("message") or "")[:120]):
        return False
    real = TD.session_paid

    async def paid(_s):
        return {"amount": 1, "currency": "EUR", "payment": "pi_suite", "created": int(time.time())}
    TD.session_paid = paid   # the ONE simulated step: the person's Apple Pay tap
    try:
        r = await PW.settle(q["session_id"])
    finally:
        TD.session_paid = real
    return ok(f"{label}: booked after payment (Duffel TEST order)", (r or {}).get("status") == "booked", str((r or {}).get("say") or r)[:160])


async def main() -> int:
    from scripts import places_fake   # Sasha 213 · NO live Google Places from a suite (it costs money) — the founder's say-so only
    places_fake.install()
    if os.getenv("SASHA_FLIGHT_SUITE", "") == "skip":
        print("flight suite SKIPPED (SASHA_FLIGHT_SUITE=skip) — this deploy is not covered")
        return 0
    from booking_signer import routes  # noqa: F401 — the Postgres stores
    from booking_signer import guest_accounts as GA, travel as T, trip_book as TB, voice_turn as VT, itinerary_q as IQ, ops
    import booking_signer.account as ACC
    from app.services.conductor import conduct
    t0 = time.time()
    g, why = await GA.create_guest("flight-suite")
    if not g:
        print(f"FAIL · could not create the scratch guest: {why}")
        return 1
    a = g["account_id"]
    print(f"scratch guest {a[:8]}", flush=True)
    real_acc = ACC.account_for
    ACC.account_for = lambda r: getattr(r, "_a", None) or real_acc(r)
    try:
        # W1 · web, typed: a single flight from home, picked by airline, booked
        sid = "suite-w1-" + uuid.uuid4().hex[:6]
        r = await conduct(f"find me flights to Hanoi on {random.randint(10, 28)} November for 2", [], user_id=a, signed_in=True, session_id=sid)
        card = next((b for b in r.get("bookings") or [] if b.get("_provider") == "duffel"), None)
        ok("W1 web: flights to Hanoi listed from Madrid", bool(card and card.get("options")) and "Madrid" in (r.get("response") or ""),
           (r.get("response") or "")[:90])
        al = _airline(card)
        r2 = await conduct(f"the {al} one", r["messages"], user_id=a, signed_in=True, session_id=sid)
        fp = r2.get("flight_pick")
        if ok(f"W1 web: typed pick “the {al} one” → its read-back", bool(fp), (r2.get("response") or "")[:90]):
            await _pay_and_settle(a, T.prepare, T.pay, {"offer_id": fp["offer_id"]}, "W1")

        # W2 · web, transcribed voice: the mic's words in the meeting
        sid = "suite-w2-" + uuid.uuid4().hex[:6]
        r = await conduct(f"find me flights to Hanoi on {random.randint(1, 20)} December for 2", [], user_id=a, signed_in=True, session_id=sid)
        card = next((b for b in r.get("bookings") or [] if b.get("_provider") == "duffel"), None)
        al = _airline(card)
        r2 = await conduct(f"Okay. Give me the {al} fight, please, Sasha.", r["messages"], user_id=a, signed_in=True, session_id=sid)
        ok(f"W2 voice: “Give me the {al} fight, please, Sasha.” → its read-back", bool(r2.get("flight_pick")), (r2.get("response") or "")[:90])
        r3 = await conduct("Okay. Go ahead. I'm ready to pay.", [], user_id=a, signed_in=True, session_id="suite-w2b-" + uuid.uuid4().hex[:6])
        ok("W2 honesty: “I'm ready to pay” with nothing open never claims a booking",
           not re.search(r"\b(?:is|are|been|all|now|it's|you're|i've|i have|has been|successfully)\s+booked\b|✅ booked|payment('s)? (has )?gone through"
                         r"|secure payment form", r3.get("response") or "", re.I), (r3.get("response") or "")[:90])   # a claim, not "haven't booked"

        # W3 · web, the guided trip (Sasha 196): plan → flights asked about → a pick ADDED (not booked) → "book it, flying from Madrid"
        #      → ONE total with THAT flight → paid → booked
        sid = "suite-w3-" + uuid.uuid4().hex[:6]
        h = []
        for m in ("plan me 8 days in Vietnam from 12 November for 2 of us", "Sounds good", "Alex", "culture and beaches", "from Madrid", "yes please"):
            rr = await conduct(m, h, user_id=a, signed_in=True, session_id=sid)
            if rr.get("continue_turn"):   # Sasha 202 · the pacing line, then the proposal (as the client asks for it)
                rr = await conduct("…", rr.get("messages") or h, user_id=a, signed_in=True, session_id=sid)
            if m.startswith("plan me"):
                ok("W3 plan: the opening first, and a clean start (no plan, flights, offers or prices)", "pulling together an itinerary" in (rr.get("response") or "")
                   and not rr.get("bookings") and not rr.get("itinerary") and "€" not in (rr.get("response") or ""), (rr.get("response") or "")[:90])
            h = rr.get("messages") or h
        card = next((b for b in rr.get("bookings") or [] if b.get("trip_pick")), None)
        ok("W3 plan: the proposal built, and on “yes please” the other flights shown to choose", bool(card), (rr.get("response") or "")[:120])
        al = _airline(card)
        rp = await conduct(f"Can I book the {al} flight, please? I like that one.", h, user_id=a, signed_in=True, session_id=sid)
        h = rp.get("messages") or h
        ok(f"W3 plan: “Can I book the {al} flight, please?” → swapped into the itinerary (not booked yet)",
           "I've swapped it in" in (rp.get("response") or ""), (rp.get("response") or "")[:110])
        rb = await conduct("book it, flying from Madrid", h, user_id=a, signed_in=True, session_id=sid)
        from booking_signer import passengers as PX   # Sasha 198 R7 · the travellers, asked once before the first total
        ok("W3 plan: the first “book it” asks the travellers' details once", PX.MARK in (rb.get("response") or ""), (rb.get("response") or "")[:90])
        rb = await conduct("Alex Smith, Mr, 12 March 1985; Sam Smith, Ms, 2 May 1987", rb.get("messages") or h, user_id=a, signed_in=True,
                           session_id=sid)
        ok("W3 plan: “book it, flying from Madrid” → ONE total for the stays and flights",
           bool(rb.get("trip_book")) and "for the stays and flights" in (rb.get("response") or ""), (rb.get("response") or "")[:120])
        if rb.get("trip_book"):
            await _pay_and_settle(a, TB.prepare, TB.pay, {"from": "Madrid"}, "W3 whole trip")
            rows = await IQ._rows(a)
            ok("W3: the trip's flight and hotels are in the guest's list", sum(1 for x in rows if "TEST" in str(x.get("venue") or "")
                                                                                   or str(x.get("booking_reference") or "").startswith("TEST-")) >= 3,
               f"{len(rows)} rows")

        # W4 · a named destination is Sasha's, never the relocation's
        r4 = await conduct("plan a twelve day trip to Singapore", [], user_id=a, signed_in=True, session_id="suite-w4-" + uuid.uuid4().hex[:6])
        ok("W4: “plan a twelve day trip to Singapore” is never RelocateMe's", "Spain" not in (r4.get("response") or ""), (r4.get("response") or "")[:90])

        # V1 · the avatar's voice page and WhatsApp share this flow: a flight by voice → read-back → yes → checkout → booked
        h = []
        v = await VT.turn(a, f"book a flight from Madrid to London on {random.randint(1, 28)} January", h)
        ok("V1 voice/WhatsApp: flights Madrid → London listed", bool(v) and "London" in (v or {}).get("response", ""), ((v or {}).get("response") or "")[:90])
        v2 = await VT.turn(a, "the first one", (v or {}).get("messages") or [])
        ok("V1: “the first one” → the read-back, asked once", bool(v2) and re.search(r"Book it\?|book it", (v2 or {}).get("response", "")) is not None,
           ((v2 or {}).get("response") or "")[:90])
        v3 = await VT.turn(a, "yes", (v2 or {}).get("messages") or [])
        ok("V1: “yes” → a Stripe TEST checkout", "checkout.stripe.com" in ((v3 or {}).get("response") or ""), ((v3 or {}).get("response") or "")[:90])
        m = re.search(r"cs_test_[A-Za-z0-9]+", (v3 or {}).get("response") or "")
        if m:
            from booking_signer import paid_watch as PW, test_deposit as TD
            real = TD.session_paid

            async def paid(_s):
                return {"amount": 1, "currency": "EUR", "payment": "pi_suite", "created": int(time.time())}
            TD.session_paid = paid
            try:
                s = await PW.settle(m[0])
            finally:
                TD.session_paid = real
            ok("V1: booked after payment (Duffel TEST order)", (s or {}).get("status") == "booked", str((s or {}).get("say") or s)[:140])

        print("NOT COVERED (no scratch relocation/campus file is made by this suite): RelocateMe's “book my flights”, CampusMe's travel offer")
    except Exception as e:
        ok("the suite itself", False, f"{type(e).__name__}: {e}")
    finally:
        ACC.account_for = real_acc
        try:
            s, _ = await ops.ADMIN("DELETE", f"/admin/users/{a}", {})
            print(f"scratch guest {a[:8]} deleted (HTTP {s})")
        except Exception as e:
            print(f"scratch guest {a[:8]} NOT deleted: {type(e).__name__}")
    failed = [n for n, p, _ in RESULTS if not p]
    print(f"\nflight suite: {len(RESULTS) - len(failed)}/{len(RESULTS)} passed in {time.time() - t0:.0f}s" + (f" — FAILED: {failed}" if failed else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
