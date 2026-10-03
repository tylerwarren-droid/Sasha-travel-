"""Sasha 131 (4) · DEPOSITS IN ONE TOUCH — and our TEST venue's deposit, as a Stripe TEST-mode Payment Link.

How a deposit works with Sasha (any venue): the venue's OWN payment page is sent to the guest's phone and the guest pays
there in one touch — Apple Pay or the card saved on the phone. Sasha never sees, holds or types a card (S-78 §8); she
checks the page's outcome where she can, and says so where she can't.

Our TEST venue stands in for a venue that asks a deposit: its page is a Stripe Payment Link in TEST mode, labelled
"test payment" everywhere — nothing is charged (Stripe's test mode; with Apple Pay in test mode the wallet's card is
shown but never charged). The key is TEST only: a live key (sk_live_…) is refused here, always.

  STRIPE_TEST_SECRET_KEY        sk_test_… — the founder sets it on Railway himself; never in chat
  SASHA_TEST_DEPOSIT_EUR        the test deposit (default 10)
"""
from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

log = logging.getLogger("booking_signer.test_deposit")
ops = APIRouter(prefix="/ops", tags=["booking-ops"])
STRIPE = "https://api.stripe.com/v1"
LABEL = "Sasha Test Venue — deposit (TEST payment, nothing is charged)"
_LINK: Dict[str, str] = {}   # this server's memory: the one link it made (id, url)


def key() -> Optional[str]:
    k = os.getenv("STRIPE_TEST_SECRET_KEY", "").strip()
    return k if k.startswith("sk_test_") else None   # ⛔ a live key is never used here


def amount_cents() -> int:
    try:
        return max(50, int(round(float(os.getenv("SASHA_TEST_DEPOSIT_EUR", "") or 10) * 100)))
    except ValueError:
        return 1000


async def _stripe(method: str, path: str, data: Optional[Dict[str, Any]] = None):
    import httpx
    async with httpx.AsyncClient(timeout=httpx.Timeout(20.0)) as c:
        r = await c.request(method, f"{STRIPE}{path}", auth=(key() or "", ""), data=data if method == "POST" else None,
                            params=data if method == "GET" else None)
    return r.status_code, r.json()


HTTP = _stripe   # tests replace it


async def link() -> Dict[str, str]:
    """The test venue's deposit page — made once per server, in TEST mode. {id, url} or {why}."""
    if not key():
        return {"why": "no Stripe TEST key is set (STRIPE_TEST_SECRET_KEY, sk_test_…) — the founder sets it on Railway"}
    if _LINK.get("url"):
        return dict(_LINK)
    s, prod = await HTTP("POST", "/products", {"name": LABEL})
    if s != 200:
        return {"why": f"Stripe refused the product: {prod.get('error', {}).get('message', s)}"}
    s, price = await HTTP("POST", "/prices", {"product": prod["id"], "currency": "eur", "unit_amount": amount_cents()})
    if s != 200:
        return {"why": f"Stripe refused the price: {price.get('error', {}).get('message', s)}"}
    s, pl = await HTTP("POST", "/payment_links", {"line_items[0][price]": price["id"], "line_items[0][quantity]": 1,
                                                  "metadata[purpose]": "sasha_test_venue_deposit", "metadata[test_payment]": "true"})
    if s != 200:
        return {"why": f"Stripe refused the payment link: {pl.get('error', {}).get('message', s)}"}
    if pl.get("livemode"):
        return {"why": "Stripe answered in LIVE mode — refused"}
    _LINK.update(id=pl["id"], url=pl["url"])
    return dict(_LINK)


async def paid_since(link_id: str, since: float) -> Optional[dict]:
    """The first COMPLETED test checkout on this link since `since` (epoch seconds) — Stripe's own record, or None."""
    s, j = await HTTP("GET", "/checkout/sessions", {"payment_link": link_id, "limit": 10})
    if s != 200:
        return None
    for cs in j.get("data") or []:
        if cs.get("status") == "complete" and cs.get("payment_status") == "paid" and (cs.get("created") or 0) >= since and not cs.get("livemode"):
            return {"amount": (cs.get("amount_total") or 0) / 100, "currency": (cs.get("currency") or "eur").upper(),
                    "payment": cs.get("payment_intent"), "session": cs.get("id")}
    return None


def message(url: str) -> str:
    eur = amount_cents() / 100
    return (f"Sasha Test Venue asks a €{eur:.2f} deposit to hold the table. ⚠ TEST payment — nothing is charged. "
            f"One touch: pay on their page with Apple Pay or your phone's saved card — I never see your card.\n{url}\n"
            f"I'll tell you here when their page shows it paid.")


@ops.post("/test-deposit/link")
async def make_link(request: Request):
    from .ops import founder_only
    no = founder_only(request)
    if no:
        return no
    got = await link()
    if "why" in got:
        return JSONResponse({"ok": False, "rule": "test_deposit_unavailable", "message": got["why"]}, status_code=422)
    return {"ok": True, **got, "say": message(got["url"])}


@ops.get("/test-deposit/status")
async def status(request: Request):
    from .ops import founder_only
    no = founder_only(request)
    if no:
        return no
    if not _LINK.get("id"):
        return {"ok": True, "paid": None, "say": "no test deposit link made on this server yet"}
    since = float(request.query_params.get("since") or (time.time() - 3600))
    got = await paid_since(_LINK["id"], since)
    return {"ok": True, "paid": got, "say": (f"Paid (TEST): €{got['amount']:.2f} — Stripe test payment {got['payment']}" if got else "not paid yet")}


__all__ = ["ops", "link", "paid_since", "message", "key", "LABEL"]
