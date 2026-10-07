"""Sasha 169 (2) → Sasha 198 R10 · BOOK THE WHOLE TRIP — from the TRIP BASKET (basket.py / basket_book.py): the stays and the
chosen flights, in ONE read-back, ONE yes, ONE Stripe TEST payment, ONE tap on the guest's phone.

  prepare → basket_book.quote(): Sherlock re-checks each chosen flight (an expired offer re-found, the choice kept); stays at
            their provider's price (the TEST hotel's placeholder, said so) → the read-back lines and their hash.
  pay     → the yes, bound to that hash (recomputed from the rows) → one Stripe TEST checkout → the rows hold the session.
  status  → paid_watch.settle(): every held item booked by its provider; Pacioli writes each line.
R10 deleted the in-memory stitching this file used to hold (_QUOTES, _BOOKED, the bundle re-search, book_paid, stays()).
Nothing is reserved, nothing is charged; every line says TEST.
"""
from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

log = logging.getLogger("booking_signer.trip_book")
router = APIRouter(prefix="/travel", tags=["travel"])
SEARCH = None                    # tests replace it (travel.search)


async def bundle(account: str, origin: str) -> dict:
    """The whole trip's quote, from the basket: {lines, sha256, eur, flights, chosen, summary, …} or {why}."""
    from . import basket_book as BB
    return await BB.quote(account, origin)


import re  # noqa: E402

ASK = re.compile(r"^\s*(?:(?:ok(?:ay)?|yes|great|perfect|lovely|now|and)[,!. ]+)*(?:please\s+|let'?s\s+|can you\s+)?"
                 r"book\s+(?:it(?:\s+all)?|everything|(?:the|my|this)\s+(?:whole\s+|entire\s+)?trip|the\s+(?:hotels?|stays?)\s+and\s+(?:the\s+)?flights?|"
                 r"(?:the\s+)?hotels?\s+and\s+(?:the\s+)?flights?)"
                 r"(?:[,]?\s+(?:with\s+)?(?:the\s+)?(?:hotels?\s+and\s+(?:the\s+)?flights?))?"
                 r"(?:[,]?\s+(?:flying\s+)?from\s+(?P<origin>[A-ZÁÉÍÓÚa-záéíóúñ][\w .'-]{1,40}?))?\s*(?:please)?\s*[.!]?\s*$", re.I)


def asked(message: str) -> Optional[str]:
    """"book it" / "book the whole trip from Madrid" → the origin said ("" when none), else None."""
    m = ASK.match(message or "")
    return None if not m else (m["origin"] or "").strip()


def _refuse(status: int, rule: str, message: str) -> JSONResponse:
    return JSONResponse({"ok": False, "rule": rule, "message": message}, status_code=status)


@router.post("/trip/prepare")
async def prepare(request: Request):
    from .account import account_for
    from . import travel as T
    if not T.token():
        return _refuse(422, "travel_off", "flights need a Duffel TEST token, and none is set")
    try:
        body = await request.json()
    except Exception:
        body = {}
    origin = str((body or {}).get("from") or "Madrid").strip()[:60] or "Madrid"
    b = await bundle(account_for(request), origin)
    if "why" in b:
        return _refuse(422, "trip_not_bookable", b["why"])
    return {"ok": True, "read_back": {"lines": b["lines"], "sha256": b["sha256"]}, "eur": b["eur"], "title": b["title"], "summary": b.get("summary")}


@router.post("/trip/pay")
async def pay(request: Request):
    from . import yes as YS, basket_book as BB
    from .account import account_for
    account = account_for(request)
    body = await request.json()
    if not YS.approval_ok(body.get("approval")):
        return _refuse(422, "approval_void", YS.APPROVAL_VOID)
    got = await BB.pay(account, str(body.get("read_back_sha256") or ""))
    if "why" in got:
        return _refuse(422, "approval_void" if "different words" in got["why"] else "trip_not_bookable", got["why"])
    return {"ok": True, "url": got["url"], "session_id": got["session_id"], "phone": got["phone"]}


ORDERABLE = None   # tests replace it


async def _orderable(cards: List[dict]) -> Optional[dict]:
    """Sasha 171 · the cheapest fare Duffel TEST still holds when asked for it again — live, its China Eastern fares came back
    from the search but were 'gone' when booked (the founder paid, and the flight home wasn't booked)."""
    from . import travel as T
    check = ORDERABLE or (lambda c: T.HTTP("GET", f"/air/offers/{c['id']}"))
    for c in cards:
        try:
            st, _j = await check(c)
        except Exception:
            continue
        if st == 200:
            return c
    return None


async def _same_or_cheaper(c: dict, party: int) -> Optional[dict]:
    from . import travel as T
    search = SEARCH or T.search
    try:
        r = await search(c.get("from_city") or c["from"], c.get("to_city") or c["to"], str(c["departs"])[:10], adults=party, limit=8)
    except Exception as e:
        log.warning("[trip_book] re-price failed: %s: %s", type(e).__name__, e)
        return None
    same = [x for x in r.get("cards") or [] if x.get("currency") == c.get("currency")]
    ok = [x for x in same if float(x["amount"]) <= float(c["amount"])] or \
         [x for x in same if float(x["amount"]) <= float(c["amount"]) * 1.5]   # TEST mode: a dearer test fare, said, not dropped
    return ok[0] if ok else None


@router.get("/trip/status")
async def trip_status(request: Request):
    from . import paid_watch as PWT
    sid = request.query_params.get("session_id") or ""
    r = await PWT.settle(sid)   # the one booking path after a payment (survives a restart)
    if r is None:
        return {"ok": True, "status": "awaiting_payment"}
    return {"ok": True, "status": "awaiting_payment"} if r.get("status") == "booking" else {"ok": True, **r}


__all__ = ["router", "bundle", "asked", "ASK", "prepare", "pay"]
