"""CR 70 · THE VENUE BOOKING LADDER, live — OVER HTTPS (Tyler's choice, 10 Oct): Sasha's own deployed booking routes are the provider's API.
AgAPI never touches Sasha's database; Sasha does the work, AgAPI keeps the act and its evidence. The booking key (SASHA_BOOKING_KEY) and the
session 'demo' (Sasha's demo account; each guest's own token arrives with the S2 switch). Sasha's server adds its own guards (the demo account
reaches no real venue's form; forms only where Sasha approved them).
  prepare (hold)  the venue read → Sasha's own route decision → the first route AgAPI may use: a FORM only on an allow-listed host (Sasha's
                  own test venue), an EMAIL only to AGAPI_EMAIL_ALLOW, a CALL only to AGAPI_WHATSAPP_ALLOW — then Sasha prepares it and its
                  read-back lines become part of AgAPI's read-back (the person approves exactly what Sasha will send). Never a booking platform.
  book (act)      the prepared route sent with the person's yes (tap → button; their words → chat) → CONFIRMED (a form's confirmation) or
                  REQUESTED (an email or a call: booked only when the venue answers).
  cancel          Sasha's cancellation for that reservation (its own read-back), under the cancellation's yes."""
from __future__ import annotations

import hashlib
import json
import os
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlsplit

from .. import config
from ..adapters import VenueLadder
from ..registry import AgapiError
from ..store import dumps, loads, ts

PLATFORM = ("opentable", "thefork", "resy", "sevenrooms", "tock", "quandoo", "booking.com", "covermanager", "tablein", "bookatable")


def base() -> str:
    return os.getenv("AGAPI_SASHA_API_URL", "https://sasha-travel-production.up.railway.app").rstrip("/")


def form_hosts() -> set:
    v = os.getenv("AGAPI_FORM_ALLOW", "").strip()
    return {h.strip().lower() for h in v.split(",") if h.strip()} if v else {urlsplit(base()).hostname}


async def sasha(method: str, path: str, body: Any = None, timeout: float = 60.0) -> Tuple[int, dict]:
    """One call to Sasha's booking routes: the booking key + Sasha's demo session. → (status, json)."""
    from . import http
    key = os.getenv("SASHA_BOOKING_KEY", "").strip()
    if not key:
        raise AgapiError("upstream_unreachable", "agapi-live has no Sasha booking key; nothing was prepared.", {"service": "sasha_ladder"})
    try:
        from . import GUEST_TOKEN
        tok = GUEST_TOKEN.get()
        who = {"authorization": f"Bearer {tok}"} if tok else {"x-sasha-session": "demo"}   # CR 71 · the guest themself, else the demo account
        r = await http(method, base() + path, headers={"x-sasha-booking-key": key, **who, "content-type": "application/json"},
                       json=body, timeout=timeout)
    except Exception as e:
        raise AgapiError("upstream_unreachable", f"Sasha's booking service didn't answer ({type(e).__name__}); nothing was sent.",
                         {"service": "sasha_ladder"}, retry_after_s=30)
    try:
        j = r.json()
    except ValueError:
        j = {}
    return r.status_code, (j if isinstance(j, dict) else {"value": j})


def _why(j: dict, st: int) -> str:
    d = j.get("detail") if isinstance(j.get("detail"), dict) else j
    return str((d or {}).get("message") or (d or {}).get("say") or f"HTTP {st}")[:200]


def _num(v: str) -> str:
    return "".join(c for c in (v or "") if c.isdigit() or c == "+")


def _allowed(rung: str, value: str) -> bool:
    v = str(value or "")
    if any(p in v.lower() for p in PLATFORM):
        return False                                                         # never a booking platform
    if rung == "form":
        return (urlsplit(v).hostname or "").lower() in form_hosts()
    if rung == "email":
        return v.strip().lower() in config.EMAIL_ALLOW
    if rung == "phone":
        return _num(v) in config.WHATSAPP_ALLOW
    return False


class LiveLadder(VenueLadder):
    async def prepare(self, offer: dict, item: dict) -> Dict[str, Any]:
        fx = offer.get("_fixture") or {}
        st, rd = await sasha("POST", "/api/booking/venues/read", {k: v for k, v in {"place_id": fx.get("place_id"), "name": fx.get("name"),
                                                                                     "asked_for": "a table"}.items() if v})
        if st != 200 or not rd.get("read_id"):
            raise AgapiError("upstream_failed", f"Sasha couldn't read that venue ({_why(rd, st)}); nothing was prepared.", {"service": "sasha_ladder"})
        rungs = {r["rung"]: r for r in rd.get("rungs") or [] if isinstance(r, dict) and r.get("available")}
        plan = ((rd.get("plan") or {}).get("route") or "")
        first = {"form": "form", "email": "email", "call": "phone", "call_email": "phone"}.get(plan)
        order = ([first] if first else []) + [r for r in ("form", "email", "phone") if r != first]
        pick = next((r for r in order if r in rungs and _allowed(r, rungs[r].get("value"))), None)
        if not pick:
            raise AgapiError("upstream_refused", f"AgAPI live books only through allow-listed routes for now; {rd.get('venue') or 'this venue'} "
                             "has none of them. Nothing was prepared.", {"service": "sasha_ladder", "reason": "not_allow_listed"})
        at, party = item["at"], int(item["party"])
        _s, d = await sasha("POST", "/api/booking/draft", {"text": "a table", "country": rd.get("country")})
        what = (d.get("parts") or {}).get("what") or {"category": "restaurant", "activity": "table"}
        cs, cj = await sasha("GET", "/api/booking/contact")
        contact = (cj or {}).get("contact") if cs == 200 else None
        if not contact:
            raise AgapiError("upstream_refused", "Sasha's demo account has no contact name and mobile set; nothing was prepared.",
                             {"service": "sasha_ladder", "reason": "contact_missing"})
        res = {"schema": "reservation/1", "flow": "book", "who": {"name": contact["name"], "contact": {"mobile_e164": contact["mobile_e164"]}},
               "what": what, "where": {}, "when": {"mode": "at", "at": at[:16]}, "how_many": {"count": party, "unit": "people"}}
        if pick == "form":
            st, j = await sasha("POST", "/api/booking/forms", {"read_id": rd["read_id"], "reservation": res})
            rid = j.get("form_id")
        elif pick == "email":
            st, j = await sasha("POST", "/api/booking/emails", {"read_id": rd["read_id"], "date": at[:10], "time": at[11:16], "party": party,
                                                                "name": contact["name"], "email": ""})
            rid = j.get("email_id")
        else:
            fi = rungs["phone"].get("fact_index")
            st, j = await sasha("POST", "/api/booking/calls", {"reservation": res, "read_id": rd["read_id"], **({"fact_index": fi} if fi is not None else {})})
            rid = j.get("call_id")
        rb = j.get("read_back") or {}
        if st != 200 or not rid or not rb.get("sha256"):
            raise AgapiError("upstream_failed", f"Sasha didn't prepare the {pick} ({_why(j, st)}); nothing was sent.", {"service": "sasha_ladder"})
        return {"rung": pick, "id": rid, "sha256": rb["sha256"], "lines": [str(x)[:300] for x in rb.get("lines") or []][:12],
                "trip_item_id": j.get("trip_item_id"), "venue": rd.get("venue")}

    async def book(self, kind, item, up, approval: Optional[dict] = None):
        import time
        prep = item.get("_ladder") or {}
        if not prep.get("id"):
            raise AgapiError("hold_expired", "The prepared booking is gone; hold again.")
        said = (approval or {}).get("said")
        how = {"how": "chat", "said": said} if said else {"how": "button"}
        t0 = time.perf_counter()
        path = {"form": f"/api/booking/forms/{prep['id']}/send", "email": f"/api/booking/emails/{prep['id']}/send",
                "phone": f"/api/booking/calls/{prep['id']}/place"}[prep["rung"]]
        st, j = await sasha("POST", path, {"read_back_sha256": prep["sha256"], "approval": how}, timeout=120)
        if st != 200:
            up.add("sasha_ladder_" + prep["rung"], t0, False, "upstream_refused")
            raise AgapiError("upstream_refused", f"Sasha didn't send it: {_why(j, st)}. Nothing was booked.", {"service": "sasha_ladder"})
        up.add("sasha_ladder_" + prep["rung"], t0, True)
        confirmed = prep["rung"] == "form" and j.get("status") == "sent" and (j.get("reading") or {}).get("result") == "confirmed"
        ref = j.get("booking_reference") if confirmed else None
        words = (f"{prep.get('venue')}: their form confirmed" + (f", reference {ref}" if ref else "") + "." if confirmed else
                 {"form": "Their form was sent; it's requested until their confirmation comes back.",
                  "email": "Sasha emailed the venue; it's requested until they reply.",
                  "phone": f"Sasha's call is {j.get('status') or 'placed'}; booked only if they say yes."}[prep["rung"]])
        return {"reference": ref or prep.get("trip_item_id") or prep["id"], "service": "sasha_ladder_" + prep["rung"], "words": words,
                "sha256": hashlib.sha256(json.dumps(j, sort_keys=True, default=str).encode()).hexdigest(),
                "outcome_kind": "CONFIRMED" if confirmed else "REQUESTED"}

    async def cancel(self, service, act_id, up, prep: Optional[dict] = None, approval: Optional[dict] = None):
        tid = (prep or {}).get("trip_item_id")
        if not tid:
            raise AgapiError("not_cancellable", "This booking has no reservation in Sasha to cancel.", {"service": "sasha_ladder"})
        st, j = await sasha("GET", f"/api/booking/reservations/{tid}/cancel")
        if st != 200 or not (j.get("read_back") or {}).get("sha256"):
            raise AgapiError("not_cancellable", f"Sasha can't cancel it: {_why(j, st)}.", {"service": "sasha_ladder"})
        said = (approval or {}).get("said")
        st, k = await sasha("POST", f"/api/booking/reservations/{tid}/cancel", {"read_back_sha256": j["read_back"]["sha256"],
                                                                                "approval": {"how": "chat", "said": said} if said else {"how": "button"}}, timeout=120)
        if st != 200:
            raise AgapiError("upstream_refused", f"Sasha didn't send the cancellation: {_why(k, st)}.", {"service": "sasha_ladder"})
        return {"reference": tid, "service": "sasha_ladder_cancel", "words": k.get("say") or "Sasha sent the cancellation.",
                "sha256": hashlib.sha256(json.dumps(k, sort_keys=True, default=str).encode()).hexdigest(),
                "outcome_kind": "CONFIRMED" if k.get("status") == "cancelled" else "REQUESTED"}

    async def smoke(self) -> dict:
        """Contacts nobody, prepares nothing: Sasha's booking health (config only) and the demo account's contact (a read)."""
        from . import http
        h = await http("GET", base() + "/api/booking/health")
        st, cj = await sasha("GET", "/api/booking/contact")
        return {"ok": h.status_code == 200 and st == 200, "health": h.status_code, "booking_key": "accepted" if st == 200 else f"HTTP {st}",
                "demo_contact": bool((cj or {}).get("contact")), "form_hosts": sorted(form_hosts()), "sent": False}
