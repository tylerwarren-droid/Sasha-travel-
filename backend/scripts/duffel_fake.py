"""Sasha 198 · THE DEPLOY GATE'S DUFFEL — recorded Duffel TEST answers, replayed in-process: no network, no rate limit, no
withdrawn fare, no "a booking with the same details was already made". The deploy gate is then a test of OUR code only.

Recorded 7 Oct 2026 from Duffel TEST (scripts/fixtures/duffel/, re-record with the scratch recorder named in its README line
below) — place suggestions, three offer requests (MAD→HAN ×2 adults, MAD→LON ×1, MAD⇄HAN return), one offer read and one order.
Replay rewrites a recorded answer to the question asked: the route's codes, the dates (every segment shifted by the same number
of days), the number of passengers (price scaled), fresh offer ids and a 30-minute expiry. An offer read answers from what this
replay issued; an order on an issued offer returns a fresh booking reference (never live_mode).

The LIVE Duffel suite is not lost: it runs on a schedule (scripts/live_suite.py) and alerts, but never blocks a deploy.
`install()` replaces both clients' transports — booking_signer.travel.HTTP and app.services.duffel._request.
"""
from __future__ import annotations

import copy
import json
import os
import random
import string
import uuid
from datetime import date, datetime, timedelta, timezone

DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "duffel")
_ISSUED: dict = {}      # offer id → the offer as this replay issued it
_ORDERS: dict = {}
CALLS: list = []        # (method, path) — the gate can say what was replayed


def _load(name: str) -> dict:
    with open(os.path.join(DIR, name)) as f:
        return json.load(f)


_PLACES = _load("places.json")
_OFFERS = _load("offer_requests.json")
_ORDER = _load("offer_and_order.json")


def _place(q: str):
    q = (q or "").strip()
    hit = next((v for k, v in _PLACES.items() if k.lower() == q.lower()), None)
    if hit:
        return hit["status"], copy.deepcopy(hit["body"])
    if len(q) == 3 and q.isalpha():   # an IATA code we never recorded: an airport of that code
        return 200, {"data": [{"type": "airport", "iata_code": q.upper(), "iata_city_code": q.upper(), "name": q.upper(),
                               "city_name": q.upper(), "time_zone": "Europe/Madrid"}]}
    return 200, {"data": []}


def _shift(ts: str, days: int) -> str:
    if not ts:
        return ts
    d = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    return (d + timedelta(days=days)).isoformat().replace("+00:00", "Z") if ts.endswith("Z") else (d + timedelta(days=days)).isoformat()


def _code_obj(code: str, like: dict) -> dict:
    o = copy.deepcopy(like or {})
    o.update({"iata_code": code, "iata_city_code": code})
    return o


def _offer_request(body: dict):
    want = (body or {}).get("data") or {}
    slices = want.get("slices") or []
    n = max(1, len(want.get("passengers") or []))
    key = "MAD-HAN-RT" if len(slices) > 1 else ("MAD-LON" if slices and slices[0].get("destination") in ("LON", "LHR", "LGW") else "MAD-HAN")
    rec = copy.deepcopy(_OFFERS[key]["body"]["data"])
    rec_req = _OFFERS[key]["request"]["data"]
    rec_n = max(1, len(rec_req["passengers"]))
    rec_slices = rec_req["slices"]
    now = datetime.now(timezone.utc)
    offers = []
    for o in rec["offers"]:
        o["id"] = "off_fx_" + uuid.uuid4().hex[:20]
        o["expires_at"] = (now + timedelta(minutes=30)).isoformat().replace("+00:00", "Z")
        o["live_mode"] = False
        o["passengers"] = [{"id": "pas_fx_" + uuid.uuid4().hex[:16], "type": "adult"} for _ in range(n)]
        for k in ("total_amount", "base_amount", "tax_amount"):
            if o.get(k) is not None:
                o[k] = f"{float(o[k]) * n / rec_n:.2f}"
        for i, s in enumerate(o.get("slices") or []):
            if i >= len(slices):
                break
            ask, was = slices[i], rec_slices[i]
            dd = (date.fromisoformat(ask["departure_date"]) - date.fromisoformat(was["departure_date"])).days
            segs = s.get("segments") or []
            if ask.get("origin") != was["origin"] and segs:
                segs[0]["origin"] = _code_obj(ask["origin"], segs[0].get("origin"))
                s["origin"] = _code_obj(ask["origin"], s.get("origin"))
            if ask.get("destination") != was["destination"] and segs:
                segs[-1]["destination"] = _code_obj(ask["destination"], segs[-1].get("destination"))
                s["destination"] = _code_obj(ask["destination"], s.get("destination"))
            for g in segs:
                g["departing_at"], g["arriving_at"] = _shift(g.get("departing_at"), dd), _shift(g.get("arriving_at"), dd)
        _ISSUED[o["id"]] = o
        offers.append(o)
    rec.update({"id": "orq_fx_" + uuid.uuid4().hex[:16], "offers": offers, "live_mode": False,
                "slices": [{"origin": {"iata_code": s.get("origin")}, "destination": {"iata_code": s.get("destination")},
                            "departure_date": s.get("departure_date")} for s in slices]})
    return 201, {"data": rec}


def _order(body: dict):
    d = (body or {}).get("data") or {}
    oid = ((d.get("selected_offers") or [None])[0])
    o = _ISSUED.get(oid)
    if not o:
        return 422, {"errors": [{"message": "The offer has expired or does not exist (replay)"}]}
    rec = copy.deepcopy(_ORDER["order"]["body"]["data"])
    ref = "".join(random.choice(string.ascii_uppercase + string.digits) for _ in range(6))
    rec.update({"id": "ord_fx_" + uuid.uuid4().hex[:16], "booking_reference": ref, "live_mode": False,
                "slices": o.get("slices"), "owner": o.get("owner"), "total_amount": o.get("total_amount"),
                "total_currency": o.get("total_currency"), "passengers": d.get("passengers") or []})
    _ORDERS[rec["id"]] = rec
    return 201, {"data": rec}


async def replay(method: str, path: str, body=None, params=None):
    """booking_signer.travel's transport, replayed: (status, json)."""
    CALLS.append((method, path.split("?")[0]))
    p = path.split("?")[0]
    if method == "GET" and p == "/places/suggestions":
        return _place((params or {}).get("query", ""))
    if method == "POST" and p == "/air/offer_requests":
        return _offer_request(body)
    if method == "GET" and p.startswith("/air/offers/"):
        o = _ISSUED.get(p.rsplit("/", 1)[1])
        return (200, {"data": copy.deepcopy(o)}) if o else (404, {"errors": [{"message": "Offer not found (replay)"}]})
    if method == "POST" and p == "/air/orders":
        return _order(body)
    return 404, {"errors": [{"message": f"not recorded: {method} {p}"}]}


def install() -> None:
    from booking_signer import travel as T
    from app.services import duffel as D
    T.HTTP = replay
    T.token = lambda: "duffel_test_replay"

    async def _request(method, path, *, params=None, body=None):
        s, j = await replay(method, path, body, params)
        if s >= 400:
            raise D.DuffelError(f"Duffel {s}: {((j.get('errors') or [{}])[0]).get('message')}")
        return j.get("data")
    D._request = _request
    D.DUFFEL_ACCESS_TOKEN = D.DUFFEL_ACCESS_TOKEN or "duffel_test_replay"
    print("DUFFEL: recorded fixtures (scripts/fixtures/duffel, recorded 7 Oct 2026) — no network", flush=True)
