"""CR 1 · /api/booking/products/* — mounted under the booking router (so its key gate applies; the frontend's narrow
/api/products/* route adds the key and forwards nothing else). A case id is the capability for its page; an expired or
unknown id is a plain 404 that says so.

  GET /api/booking/products/health                       which store, which schools are proven, the watch loop
  GET /api/booking/products/campus/{id}                  the hand-over: the school's form, question by question
  GET /api/booking/products/campus/{id}/visit.ics        the visit, for any calendar
  GET /api/booking/products/relocation/{id}              the reviewer's screen: every EX-01 widget, its state, its checks
  GET /api/booking/products/relocation/{id}/EX-01-prepared.pdf   the official PDF, prepared — not signed, not filed
  GET /api/booking/products/health/{id}/1449F1-prepared.pdf      CR 30 · the health-card form, filled — not signed, not submitted
  GET /api/booking/products/reminders                    CR 10 · the account's dated reminders (not bookings), for "You"
"""
from __future__ import annotations

import asyncio
import os
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

from . import store as ST
from .campus import handover as HV
from .campus import schools as SC

router = APIRouter(prefix="/products", tags=["products"])
STORE_KIND = {"kind": "memory (not started)"}


@router.on_event("startup")
async def _choose_store() -> None:
    from booking_signer import routes as BR
    STORE_KIND["kind"] = await ST.choose(BR.STORE)
    from .campus import watch
    watch.start()
    if getattr(ST.STORE, "durable", False):
        asyncio.ensure_future(_expire_daily())


async def _expire_daily() -> None:
    """Personal data expires: every case is deleted 30 days after it was made (logged in retention_log)."""
    import logging
    while True:
        try:
            from .relocation import after
            from .health import turn as health
            await after.due()                       # relocation reminders whose day has come
            await health.due()                      # health reminders; hand-over identifiers dropped after 24 h
            n = await ST.expire_once()
            if n:
                logging.getLogger("products").info("[products] %d expired case(s) deleted", n)
        except Exception as e:
            logging.getLogger("products").error("[products] expiry failed: %s: %s", type(e).__name__, e)
        await asyncio.sleep(24 * 3600)


@router.get("/health")
async def health() -> dict:
    from .campus import watch
    from .relocation import ex01
    return {"ok": True, "store": STORE_KIND["kind"], "durable": bool(getattr(ST.STORE, "durable", False)),
            "campus": {"proven": [s["name"] for s in SC.SCHOOLS.values() if s.get("proven")],
                       "configured_unproven": [s["name"] for s in SC.SCHOOLS.values() if not s.get("proven")],
                       "submits": False, "watch_loop": watch.running()},
            "relocation": {"ex01_pdf": ex01.pdf_status(), "submits": False}}


@router.get("/espana/areas")
async def espana_areas() -> dict:
    """CR 17 · EspañaMe's six areas — the same cards the chat shows (health/espana.py): public, no personal data."""
    from .health import espana as ES
    return {"ok": True, "areas": ES.areas(), "read_on": ES._READ.get("read_on")}


@router.get("/reminders")
async def reminders(request: Request) -> dict:
    """CR 10 · dated reminders the products keep — relocation's apply-from/certificates/TIE, health's padrón follow-ups.
    NOT trip items (the Sasha tab's rule): "You" lists them in their own block. Only the gate's own account; only
    reminders still to come; the source of each date said with it."""
    from booking_signer.account import account_for
    from datetime import date
    account = account_for(request)
    today = date.today().isoformat()
    out = []
    for product, label, get in (("relocation", "Relocation · EX-01", lambda st: (st.get("after") or {}).get("reminders")),
                                ("health", "Health · new in Madrid", lambda st: st.get("reminders"))):
        for c in await ST.STORE.of_account(account, product):
            st = c["state"]
            if st.get("kind") == "conversation" or st.get("showcase"):
                continue
            for r in get(st) or []:
                if r.get("on") and r["on"] >= today:
                    out.append({"on": r["on"], "text": r["text"], "product": product, "label": label, "sent": bool(r.get("sent"))})
    out.sort(key=lambda r: r["on"])
    return {"reminders": out}


async def _case(cid: str, product: str) -> dict:
    c = await ST.STORE.get(cid)
    if not c or c["product"] != product:
        raise HTTPException(404, {"ok": False, "rule": "case_not_found",
                                  "message": "This page has expired or never existed. Ask again on WhatsApp for a new one."})
    return c


@router.get("/campus/{cid}")
async def campus_case(cid: str) -> dict:
    c = await _case(cid, "campus")
    st = c["state"]
    if "session" not in st:
        raise HTTPException(404, {"ok": False, "rule": "case_not_found", "message": "Nothing was prepared on this page."})
    s = SC.SCHOOLS[st["school"]]
    return {"ok": True, "school": {k: s[k] for k in ("name", "full_name", "city", "host", "rules")},
            "session": st["session"], "form_url": st["form_url"], "form_read": st.get("form_read"),
            "form_pages": st.get("form_pages", 1), "challenge_seen": st.get("challenge_seen", False),
            "rows": st["rows"], "counts": HV.counts(st["rows"]), "status": st.get("status"),
            "confirmation_quote": st.get("confirmation_quote"), "prepared_at": str(c["created_at"]),
            "fictional": bool(st.get("fictional")), "showcase": bool(st.get("showcase")),
            "form_rows": st.get("rows"), "left_for_you": st.get("left_for_you"), "form_source": st.get("source"),
            "form_pdf": f"/api/booking/products/health/{cid}/1449F1-prepared.pdf" if st.get("rows") else None,
            "expires_at": str(c["expires_at"]), "submits": False}


@router.get("/campus/{cid}/visit.ics")
async def campus_ics(cid: str) -> Response:
    from .campus import visits as VS
    c = await _case(cid, "campus")
    st = c["state"]
    if "session" not in st:
        raise HTTPException(404, {"ok": False, "rule": "case_not_found", "message": "Nothing was prepared on this page."})
    body = VS.ics(SC.SCHOOLS[st["school"]], st["session"], cid, st.get("status") == "confirmed_in_writing")
    return Response(body, media_type="text/calendar", headers={"content-disposition": 'attachment; filename="campus-visit.ics"'})


@router.get("/relocation/{cid}")
async def relocation_case(cid: str) -> dict:
    from .relocation import ex01 as E
    c = await _case(cid, "relocation")
    st = c["state"]
    return {"ok": True, "rows": st["rows"], "counts": st["counts"], "checks": st["checks"], "status": st.get("status"),
            "route": st.get("route"), "fictional": st.get("fictional", False), "showcase": bool(st.get("showcase")),
            "prepared_at": st.get("prepared_at"),
            "signed_at": st.get("signed_at"), "after": st.get("after"), "expires_at": str(c["expires_at"]),
            "form": {"name": "EX-01", "title": "Autorización de residencia temporal no lucrativa", "pages": 3,
                     "widgets": len(st["rows"]), "pdf_sha256": E.PDF_SHA256}, "submits": False}


@router.get("/relocation/{cid}/EX-01-prepared.pdf")
async def relocation_pdf(cid: str) -> Response:
    from .relocation import ex01 as E
    c = await _case(cid, "relocation")
    pdf = E.fill(c["state"]["rows"])   # rebuilt from the rows every time: the guard runs on every download
    return Response(pdf, media_type="application/pdf",
                    headers={"content-disposition": 'inline; filename="EX-01-prepared-not-signed.pdf"'})


@router.get("/health/{cid}/1449F1-prepared.pdf")
async def health_card_pdf(cid: str) -> Response:
    """CR 30 · the Comunidad de Madrid's own health-card form, filled — not signed, not submitted. Rebuilt from the rows on
    every download (the guard runs each time); after 24 hours the rows are dropped and the link says so."""
    from datetime import datetime, timezone
    from .health import tarjeta as TS
    c = await _case(cid, "health")
    st = c["state"]
    if st.get("kind") != "tarjeta":
        raise HTTPException(404, {"ok": False, "rule": "case_not_found", "message": "This page has expired or never existed."})
    if not st.get("rows") or TS.expired(st, datetime.now(timezone.utc)):
        if st.get("rows"):
            st["rows"] = None
            await ST.STORE.update(cid, st)
        raise HTTPException(410, {"ok": False, "rule": "values_expired",
                                  "message": "This form's details were dropped after 24 hours. Ask Sasha again for a new one."})
    return Response(TS.fill(st["rows"]), media_type="application/pdf",
                    headers={"content-disposition": 'inline; filename="Tarjeta-Sanitaria-1449F1-not-signed.pdf"'})


@router.get("/health/{cid}")
async def health_case(cid: str) -> dict:
    """The health hand-over or the new-in-Madrid checklist. The identifiers are served only inside their 24 hours, and
    dropped from the case the first time they're found expired (the daily job drops them too)."""
    from datetime import datetime, timezone
    from .health import sources as HS
    c = await _case(cid, "health")
    st = c["state"]
    if st.get("values") and (st.get("values_expire_at") or "") <= datetime.now(timezone.utc).isoformat():
        st["values"] = None
        await ST.STORE.update(cid, st)
    if st.get("kind") == "tarjeta" and st.get("rows"):
        from .health import tarjeta as TS
        if TS.expired(st, datetime.now(timezone.utc)):
            st["rows"] = None
            await ST.STORE.update(cid, st)
    return {"ok": True, "kind": st.get("kind"), "appointment_type": st.get("appointment_type"), "values": st.get("values"),
            "values_source": st.get("values_source"), "values_expire_at": st.get("values_expire_at"),
            "fictional": bool(st.get("fictional")), "checklist": st.get("checklist"), "reminders": st.get("reminders"),
            "padron_date": st.get("padron_date"), "sermas": HS.SERMAS, "read_on": HS.READ_ON,
            "expires_at": str(c["expires_at"]), "submits": False}


# ── CR 8 · the case officer's queue (fictional applications; the real checks) ─────────────────────────────────────

async def _officer_case(cid: str) -> dict:
    c = await _case(cid, "relocation")
    if (c["state"] or {}).get("kind") != "officer_queue":
        raise HTTPException(404, {"ok": False, "rule": "case_not_found", "message": "This page has expired or never existed."})
    return c


@router.get("/relocation/officer/{cid}")
async def officer_queue(cid: str) -> dict:
    from .relocation import officer as OF
    c = await _officer_case(cid)
    returned = c["state"].get("returned") or {}
    apps = [{**a, "returned": returned.get(a["id"]), "message": OF.return_message(a)} for a in OF.queue()]
    return {"ok": True, "applications": apps, "fictional": True, "kind": "click-through", "sends": False,
            "expires_at": str(c["expires_at"])}


@router.post("/relocation/officer/{cid}/return/{app_id}")
async def officer_return(cid: str, app_id: str) -> dict:
    """RECORDS that the case officer returned the application, with the exact message. Nothing is sent to anyone."""
    from datetime import datetime, timezone
    from .relocation import officer as OF
    c = await _officer_case(cid)
    app = next((a for a in OF.queue() if a["id"] == app_id), None)
    if app is None:
        raise HTTPException(404, {"ok": False, "rule": "application_unknown", "message": "No such application in this queue."})
    if app["status"] == "complete":
        raise HTTPException(409, {"ok": False, "rule": "nothing_to_return", "message": "This application is complete — nothing to return."})
    st = c["state"]
    st.setdefault("returned", {})
    if app_id not in st["returned"]:
        st["returned"][app_id] = {"at": datetime.now(timezone.utc).isoformat(), "items": app["open_items"],
                                  "message": OF.return_message(app)}
        await ST.STORE.update(cid, st)
    return {"ok": True, "returned": st["returned"][app_id], "sent": False}
