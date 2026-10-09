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
import re
import time
from typing import Any, Dict, Optional

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

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


async def checkout(amount: str, currency: str, label: str, ref: str, embedded: bool = False, where: str = "phone",
                   name: Optional[str] = None) -> Dict[str, str]:
    """Sasha 132 · one touch for ANY test amount (a flight's fare): a Stripe TEST Checkout session. {id, url} or {why}."""
    if not key():
        return {"why": "no Stripe TEST key is set (STRIPE_TEST_SECRET_KEY, sk_test_…) — the founder sets it on Railway"}
    try:
        cents = int(round(float(amount) * 100))
    except ValueError:
        return {"why": f"not an amount: {amount!r}"}
    # Sasha 136 · after paying, the phone's browser lands on a PUBLIC page (no sign-in): "Paid (TEST) — check WhatsApp", with the
    # booking's status once known. Stripe fills {CHECKOUT_SESSION_ID} itself.
    from .form_rung import public_base
    back = f"{public_base()}/api/booking/test-pay"
    # Sasha 220 · "pay HERE": Stripe Embedded Checkout (the card inside the conversation; Apple Pay / Google Pay where the device
    # has them) — no redirect; the page hears the outcome from Pacioli, never from the browser
    # (Stripe renamed the mode: "embedded" is refused now — "embedded_page", checked live in TEST on 9 Oct)
    shape = ({"ui_mode": "embedded_page", "redirect_on_completion": "never"} if embedded else
             {"success_url": f"{back}/done?s={{CHECKOUT_SESSION_ID}}" + ("&w=here" if where == "here" else ""),
              "cancel_url": f"{back}/back?s={{CHECKOUT_SESSION_ID}}"})
    s, j = await HTTP("POST", "/checkout/sessions", {
        "mode": "payment", **shape, "metadata[sasha_where]": where,
        "line_items[0][quantity]": 1, "line_items[0][price_data][currency]": currency.lower(),
        "line_items[0][price_data][unit_amount]": cents, "line_items[0][price_data][product_data][name]": (name or f"TEST payment — {label}")[:250],   # Sasha 222 · the pay card: its own name (Stripe's TEST MODE badge stays)
        "metadata[test_payment]": "true", "metadata[sasha_ref]": ref[:100]})
    if s != 200:
        return {"why": f"Stripe refused the test page: {j.get('error', {}).get('message', s)}"}
    if j.get("livemode"):
        return {"why": "Stripe answered in LIVE mode — refused"}
    return {"id": j["id"], "url": j.get("url"), **({"client_secret": j["client_secret"]} if j.get("client_secret") else {}),
            "embedded": bool(embedded)}


async def session_state(session_id: str) -> Optional[dict]:
    """Sasha 220 · a checkout as Stripe holds it now: open / complete / expired, paid or not, and how it's paid (embedded's secret)."""
    if not key():
        return None
    s, cs = await HTTP("GET", f"/checkout/sessions/{session_id}", {})
    if s != 200 or cs.get("livemode"):
        return None
    return {"status": cs.get("status"), "paid": cs.get("payment_status") == "paid", "url": cs.get("url"),
            "client_secret": cs.get("client_secret"), "embedded": str(cs.get("ui_mode") or "").startswith("embedded"),
            "where": (cs.get("metadata") or {}).get("sasha_where") or ("here" if str(cs.get("ui_mode") or "").startswith("embedded") else "phone"),
            "amount": (cs.get("amount_total") or 0) / 100}


async def expire(session_id: str) -> bool:
    """Sasha 215 · a checkout that must never be paid (its booking record wasn't written): expired at Stripe, so the page refuses."""
    if not key():
        return False
    s, j = await HTTP("POST", f"/checkout/sessions/{session_id}/expire", {})
    if s != 200:
        log.error("[test_deposit] session %s not expired: HTTP %s", session_id[:16], s)
    return s == 200


async def session_paid(session_id: str) -> Optional[dict]:
    s, cs = await HTTP("GET", f"/checkout/sessions/{session_id}", {})
    if s != 200 or cs.get("livemode") or cs.get("status") != "complete" or cs.get("payment_status") != "paid":
        return None
    return {"amount": (cs.get("amount_total") or 0) / 100, "currency": (cs.get("currency") or "eur").upper(), "payment": cs.get("payment_intent"),
            "created": cs.get("created") or 0}


# ── Sasha 136 · the public page Stripe returns to — no sign-in, nothing personal: the payment's state and the booking's ──

public = APIRouter(prefix="/test-pay", tags=["test-pay"])
OUTCOMES: Dict[str, dict] = {}   # Stripe session → what Sasha did with it (this server's memory; the watchers write it)
_SID = re.compile(r"cs_test_[A-Za-z0-9]{10,200}")


def note(session_id: str, ok: bool, line: str) -> None:
    """The booking's outcome for this payment, for the return page. `line` names the booking — never the guest."""
    if session_id:
        OUTCOMES[session_id] = {"ok": ok, "line": line[:300]}
        if len(OUTCOMES) > 500:
            OUTCOMES.pop(next(iter(OUTCOMES)))


_PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
{refresh}<title>Sasha — test payment</title><style>body{{font:17px/1.5 -apple-system,system-ui,sans-serif;max-width:32rem;margin:3rem auto;
padding:0 1.25rem;color:#111;background:#fff}}h1{{font-size:1.4rem}}.t{{display:inline-block;background:#fff3cd;border:1px solid #e0c36b;
border-radius:6px;padding:.1rem .5rem;font-size:.85rem}}.s{{color:#555}}@media (prefers-color-scheme:dark){{body{{color:#eee;background:#111}}
.s{{color:#aaa}}.t{{background:#3a3110;border-color:#7a6620;color:#f3e2a8}}}}</style></head><body>
<span class="t">TEST — nothing is charged</span><h1>{title}</h1><p>{body}</p><p class="s">{status}</p></body></html>"""


def _page(title: str, body: str, status: str, refresh: bool) -> HTMLResponse:
    from html import escape
    return HTMLResponse(_PAGE.format(title=escape(title), body=escape(body), status=escape(status),
                                     refresh='<meta http-equiv="refresh" content="5">' if refresh else ""),
                        headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})


@public.get("/done")
async def done(request: Request):
    sid = request.query_params.get("s") or ""
    if not _SID.fullmatch(sid):
        return _page("Test payment", "This link isn't a test payment Sasha made.", "", False)
    out = OUTCOMES.get(sid)
    here = request.query_params.get("w") == "here"   # Sasha 220 · paid HERE: the conversation hears it, not WhatsApp
    where_words = "back in your conversation with Sasha" if here else "on WhatsApp"
    if out:
        return _page("Paid (TEST) — " + ("booked (TEST)" if out["ok"] else "not booked"), out["line"],
                     f"The same message is {where_words}. You can close this page.", False)
    paid = await session_paid(sid) if key() else None
    if paid and time.time() - (paid.get("created") or 0) > 600:   # this page can't see it (another process, a redeploy): say so, stop waiting
        return _page("Paid (TEST)", f"Stripe recorded the TEST payment ({paid['currency']} {paid['amount']:.2f}); nothing was charged.",
                     "The booking's result is in your WhatsApp messages from Sasha — this page can't show it. You can close it.", False)
    if paid:
        return _page("Paid (TEST). Sasha is booking it — " + ("go back to your conversation." if here else "check WhatsApp."),
                     f"Stripe recorded the TEST payment ({paid['currency']} {paid['amount']:.2f}); nothing was charged.",
                     "Waiting for the booking… this page updates by itself.", True)
    return _page("Payment not recorded yet", "Stripe hasn't recorded this TEST payment yet. If you just paid, give it a moment.",
                 "This page updates by itself.", True)


@public.get("/back")
async def back(request: Request):
    return _page("Not paid", "You left the test payment page, so nothing was paid and nothing was booked.",
                 "Ask Sasha on WhatsApp to send the page again whenever you like.", False)


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


__all__ = ["ops", "link", "paid_since", "message", "key", "LABEL", "checkout", "session_paid"]
