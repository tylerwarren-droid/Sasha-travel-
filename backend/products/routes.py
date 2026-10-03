"""CR 1 · /api/booking/products/* — mounted under the booking router (so its key gate applies; the frontend's narrow
/api/products/* route adds the key and forwards nothing else). A case id is the capability for its page; an expired or
unknown id is a plain 404 that says so.

  GET /api/booking/products/health                       which store, which schools are proven, the watch loop
  GET /api/booking/products/campus/{id}                  the hand-over: the school's form, question by question
  GET /api/booking/products/campus/{id}/visit.ics        the visit, for any calendar
  GET /api/booking/products/relocation/{id}              the reviewer's screen: every EX-01 widget, its state, its checks
  GET /api/booking/products/relocation/{id}/EX-01-prepared.pdf   the official PDF, prepared — not signed, not filed
"""
from __future__ import annotations

import asyncio
import os
from typing import Any

from fastapi import APIRouter, HTTPException
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
            "route": st.get("route"), "fictional": st.get("fictional", False), "prepared_at": st.get("prepared_at"),
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
