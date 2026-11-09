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
                   name: Optional[str] = None, account: Optional[str] = None) -> Dict[str, str]:
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
    save = await _save_fields(account)   # Sasha 327 · his Stripe customer; "save this card for next time" (default ON in beta)
    s, j = await HTTP("POST", "/checkout/sessions", {
        "mode": "payment", **shape, **save, "metadata[sasha_where]": where,
        "payment_intent_data[capture_method]": "manual",   # Sasha 363 · AUTHORISE only: money moves on the supplier's confirmation (finish)
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
    """Sasha 220 · a checkout as Stripe holds it now: open / complete / expired, paid or not, and how it's paid (embedded's secret).
    Sasha 327 · a saved-card payment (pi_…): the same shape, where "saved"."""
    if not key():
        return None
    if session_id.startswith("pi_"):
        return await _intent_state(session_id)
    s, cs = await HTTP("GET", f"/checkout/sessions/{session_id}", {})
    if s != 200 or cs.get("livemode"):
        return None
    pi = await _intent_state(cs["payment_intent"]) if cs.get("status") == "complete" and cs.get("payment_status") != "paid" \
        and cs.get("payment_intent") else None   # Sasha 363 · a HOLD (manual capture) is paid-for: the booking decides capture / release
    return {"status": cs.get("status"), "paid": cs.get("payment_status") == "paid" or bool(pi and pi["held"]), "held": bool(pi and pi["held"]),
            "url": cs.get("url"),
            "client_secret": cs.get("client_secret"), "embedded": str(cs.get("ui_mode") or "").startswith("embedded"),
            "where": (cs.get("metadata") or {}).get("sasha_where") or ("here" if str(cs.get("ui_mode") or "").startswith("embedded") else "phone"),
            "amount": (cs.get("amount_total") or 0) / 100}


async def read_session(session_id: str):
    """Read-only: a checkout session as Stripe returns it (the pay proof checks its fields). → (status, body)."""
    return await HTTP("GET", f"/checkout/sessions/{session_id}", {})


async def expire(session_id: str) -> bool:
    """Sasha 215 · a checkout that must never be paid (its booking record wasn't written): expired at Stripe, so the page refuses."""
    if not key():
        return False
    s, j = await (HTTP("POST", f"/payment_intents/{session_id}/cancel", {}) if session_id.startswith("pi_") else
                  HTTP("POST", f"/checkout/sessions/{session_id}/expire", {}))   # Sasha 327 · a saved-card payment: cancelled
    if s != 200:
        log.error("[test_deposit] session %s not expired: HTTP %s", session_id[:16], s)
    return s == 200


async def session_paid(session_id: str) -> Optional[dict]:
    if session_id.startswith("pi_"):   # Sasha 327 · a saved-card payment: Stripe's PaymentIntent, succeeded
        st = await _intent_state(session_id)
        return {"amount": st["amount"], "currency": st["currency"], "payment": session_id, "created": st["created"]} if st and st["paid"] else None
    s, cs = await HTTP("GET", f"/checkout/sessions/{session_id}", {})
    if s != 200 or cs.get("livemode") or cs.get("status") != "complete":
        return None
    pi = await _intent_state(cs["payment_intent"]) if cs.get("payment_intent") and cs.get("payment_status") != "paid" else None
    if cs.get("payment_status") != "paid" and not (pi and pi["held"]):   # Sasha 363 · held (authorised, manual capture) counts
        return None
    return {"amount": (cs.get("amount_total") or 0) / 100, "currency": (cs.get("currency") or "eur").upper(), "payment": cs.get("payment_intent"),
            "created": cs.get("created") or 0, "held": bool(pi and pi["held"])}


# ── Sasha 363 · MONEY MOVES ONLY ON A CONFIRMED BOOKING: every payment is a HOLD (authorised, capture_method manual); the booking
# decides — finish() captures exactly what the supplier CONFIRMED, or releases the hold. Never a refund after a capture. ───────────
HELD_OR_TAKEN = ("requires_capture", "succeeded")


async def _pi_of(sid: str) -> Optional[str]:
    if sid.startswith("pi_"):
        return sid
    s, cs = await HTTP("GET", f"/checkout/sessions/{sid}", {})
    return cs.get("payment_intent") if s == 200 and not cs.get("livemode") else None


async def finish(sid: str, booked_cents: int) -> Dict[str, Any]:
    """THE ONE place money moves after a booking: booked_cents > 0 → capture that (≤ the hold; the rest is released by Stripe);
    0 → release the hold. A payment taken before this rule (automatic capture) is left as it is, said. → {captured} · {released} · {why}."""
    if not key():
        return {"why": "no Stripe TEST key"}
    pi_id = await _pi_of(sid)
    if not pi_id:
        return {"why": "no payment for this session"}
    s, pi = await HTTP("GET", f"/payment_intents/{pi_id}", {})
    if s != 200 or pi.get("livemode"):
        return {"why": f"the payment couldn't be read ({s})"}
    st = pi.get("status")
    if st == "succeeded":
        return {"captured": pi.get("amount_received") or pi.get("amount"), "already": True}   # taken before 363's rule: nothing more moves
    if st == "canceled":
        return {"released": True, "already": True}
    if st != "requires_capture":
        return {"why": f"the payment isn't held ({st})"}
    if booked_cents > 0:
        s2, j = await HTTP("POST", f"/payment_intents/{pi_id}/capture", {"amount_to_capture": min(int(booked_cents), int(pi.get("amount") or 0))})
        if s2 != 200:
            log.error("[test_deposit] capture of %s refused: %s", pi_id[:14], (j.get("error") or {}).get("message", s2))
            return {"why": f"Stripe didn't take the payment ({(j.get('error') or {}).get('message', s2)})"}
        return {"captured": j.get("amount_received")}
    s3, j = await HTTP("POST", f"/payment_intents/{pi_id}/cancel", {})
    if s3 != 200:
        log.error("[test_deposit] the hold on %s wasn't released: %s", pi_id[:14], (j.get("error") or {}).get("message", s3))
        return {"why": "the hold couldn't be released just now"}
    return {"released": True}


# ── Sasha 327 · PAY IN ONE TAP: his Stripe customer and the card Stripe saved for him ────────────────────────────────────────
# Sasha never sees, logs or stores a card number: Stripe holds it (the customer + its saved payment method). Sasha keeps only the
# customer's id (a pointer, s2_memory "stripe_customer") and says a card as its brand and last four digits, as Stripe gives them.
SAVE_WORDS = "Your card is saved securely with Stripe for your next booking. Say \"remove my saved card\" any time to delete it."
CUSTOMER_KIND = "stripe_customer"


def save_default() -> bool:
    """Default ON while Sasha is in beta (every person; Stripe TEST). SASHA_SAVE_CARD=off turns it off; live stays OFF regardless."""
    return os.getenv("SASHA_SAVE_CARD", "on").strip().lower() != "off"


async def customer_of(account: Optional[str], create: bool = True) -> Optional[str]:
    if not account or not key():
        return None
    from agapi import s2_memory as M
    try:
        cus = await M.kind(account, CUSTOMER_KIND)
    except Exception as e:
        log.warning("[test_deposit] customer not read: %s", type(e).__name__)
        cus = None
    if isinstance(cus, str) and cus.startswith("cus_"):
        return cus
    if not create:
        return None
    s, c = await HTTP("POST", "/customers", {"metadata[sasha_account]": account, "description": "Sasha guest (TEST)"})
    if s != 200 or c.get("livemode"):
        log.warning("[test_deposit] customer not made: HTTP %s", s)
        return None
    await M.put_kind(account, CUSTOMER_KIND, c["id"])
    return c["id"]


async def _save_fields(account: Optional[str]) -> Dict[str, Any]:
    cus = await customer_of(account) if account else None
    if not cus:
        return {}
    out: Dict[str, Any] = {"customer": cus, "saved_payment_method_options[payment_method_remove]": "enabled"}   # removable on the page
    if save_default():   # saved for next time, said where he pays
        out.update({"payment_intent_data[setup_future_usage]": "off_session", "custom_text[submit][message]": SAVE_WORDS})
    else:
        out["saved_payment_method_options[payment_method_save]"] = "enabled"   # Stripe's own checkbox
    return out


async def saved_card(account: Optional[str]) -> Optional[Dict[str, str]]:
    """The card Stripe saved for him → {id, brand, last4, words}, or None. Never the number."""
    cus = await customer_of(account, create=False)
    if not cus:
        return None
    s, j = await HTTP("GET", f"/customers/{cus}/payment_methods", {"limit": 1})
    if s != 200:
        return None
    pm = next(iter(j.get("data") or []), None)
    if not pm:
        return None
    c = pm.get("card") or {}
    wallet = ((c.get("wallet") or {}).get("type") or "").replace("_", " ").title()
    brand = str(c.get("brand") or pm.get("type") or "card").title()
    return {"id": pm["id"], "customer": cus, "brand": brand, "last4": str(c.get("last4") or ""),
            "words": f"your saved {brand}" + (f" ({wallet})" if wallet else "") + (f" ending {c['last4']}" if c.get("last4") else "")}


async def remove_saved(account: Optional[str]) -> int:
    """Detach every payment method Stripe saved for him → how many were removed."""
    cus = await customer_of(account, create=False)
    if not cus:
        return 0
    s, j = await HTTP("GET", f"/customers/{cus}/payment_methods", {"limit": 20})
    n = 0
    for pm in (j.get("data") or []) if s == 200 else []:
        s2, _ = await HTTP("POST", f"/payment_methods/{pm['id']}/detach", {})
        n += s2 == 200
    return n


async def intent_saved(card: Dict[str, str], amount: str, currency: str, label: str, ref: str) -> Dict[str, Any]:
    """A PaymentIntent for the saved card, NOT yet confirmed (its id is recorded before any money moves). {id} or {why}."""
    try:
        cents = int(round(float(amount) * 100))
    except ValueError:
        return {"why": f"not an amount: {amount!r}"}
    s, pi = await HTTP("POST", "/payment_intents", {"amount": cents, "currency": currency.lower(), "customer": card["customer"],
                                                   "payment_method": card["id"], "description": f"TEST payment — {label}"[:250],
                                                   "metadata[test_payment]": "true", "metadata[sasha_ref]": ref[:100],
                                                   "metadata[sasha_where]": "saved",
                                                   "capture_method": "manual"})   # Sasha 363 · a hold; captured only on a confirmed booking
    if s != 200:
        return {"why": f"Stripe refused the payment: {pi.get('error', {}).get('message', s)}"}
    if pi.get("livemode"):
        return {"why": "Stripe answered in LIVE mode — refused"}
    return {"id": pi["id"]}


async def confirm_saved(pi_id: str) -> Dict[str, Any]:
    """Charge it, off-session. → {paid} · {confirm_url} (his bank asks him to confirm: SCA / 3-D Secure) · {declined, why}."""
    s, pi = await HTTP("POST", f"/payment_intents/{pi_id}/confirm", {"off_session": "true"})
    if s == 200 and pi.get("status") in HELD_OR_TAKEN:   # Sasha 363 · held (authorised): the booking decides capture or release
        return {"paid": True, "held": pi.get("status") == "requires_capture"}
    err = (pi.get("error") or {}) if s != 200 else {}
    if err.get("code") == "authentication_required" or pi.get("status") == "requires_action":
        from .form_rung import public_base   # on-session now: Stripe's own page for his bank, then back to ours
        s2, pi2 = await HTTP("POST", f"/payment_intents/{pi_id}/confirm", {"payment_method": (err.get("payment_method") or {}).get("id") or pi.get("payment_method") or "",
                                                                        "return_url": f"{public_base()}/api/booking/test-pay/done?s={pi_id}",
                                                                        "use_stripe_sdk": "false"})
        url = ((pi2.get("next_action") or {}).get("redirect_to_url") or {}).get("url") if s2 == 200 else None
        if url:
            return {"confirm_url": url}
        if s2 == 200 and pi2.get("status") in HELD_OR_TAKEN:
            return {"paid": True, "held": pi2.get("status") == "requires_capture"}
    return {"declined": True, "why": err.get("message") or f"the bank didn't accept the saved card ({pi.get('status') or s})"}


async def _intent_state(pi_id: str) -> Optional[dict]:
    s, pi = await HTTP("GET", f"/payment_intents/{pi_id}", {})
    if s != 200 or pi.get("livemode"):
        return None
    st = pi.get("status")
    url = ((pi.get("next_action") or {}).get("redirect_to_url") or {}).get("url")
    return {"status": "complete" if st in HELD_OR_TAKEN else "expired" if st == "canceled" else "open", "paid": st in HELD_OR_TAKEN,
            "held": st == "requires_capture", "url": url,
            "client_secret": None, "embedded": False, "where": "saved", "amount": (pi.get("amount") or 0) / 100,
            "currency": (pi.get("currency") or "eur").upper(), "created": pi.get("created") or 0}


async def legacy_session(stripe_sdk, **kw):
    """Sasha 327 · the legacy S1 itinerary checkout (app/api/payments.py, its own key mode SASHA_LEGACY_STRIPE_MODE — TEST in the beta):
    created HERE, so every place money is taken is this one module (its shape and keys unchanged)."""
    import asyncio as _aio
    return await _aio.to_thread(stripe_sdk.checkout.Session.create, **kw)


# ── Sasha 327 · Apple Pay on Kanoe's own pages (Embedded Checkout): the payment method domains, registered with Stripe ─────
PAY_DOMAINS = ("project.kanoe.ai", "demo.kanoe.ai", "investor.kanoe.ai")


async def register_domains() -> Dict[str, str]:
    """Idempotent: each of Kanoe's pay domains as a Stripe payment method domain (Apple Pay needs it for an embedded page; Google Pay and
    Link read the same list). TEST key only. → {domain: state}."""
    if not key():
        return {"why": "no Stripe TEST key"}
    s, j = await HTTP("GET", "/payment_method_domains", {"limit": 50})
    have = {d.get("domain_name"): d for d in (j.get("data") or [])} if s == 200 else {}
    out = {}
    for dom in PAY_DOMAINS:
        d = have.get(dom)
        if not d:
            s2, d = await HTTP("POST", "/payment_method_domains", {"domain_name": dom, "enabled": "true"})
            if s2 != 200:
                out[dom] = f"refused: {(d.get('error') or {}).get('message', s2)}"
                continue
        out[dom] = "apple_pay " + str(((d.get("apple_pay") or {}).get("status")) or "?") + " · google_pay " + \
            str(((d.get("google_pay") or {}).get("status")) or "?") + " · link " + str(((d.get("link") or {}).get("status")) or "?")
    return out


# ── Sasha 136 · the public page Stripe returns to — no sign-in, nothing personal: the payment's state and the booking's ──

public = APIRouter(prefix="/test-pay", tags=["test-pay"])
OUTCOMES: Dict[str, dict] = {}   # Stripe session → what Sasha did with it (this server's memory; the watchers write it)
_SID = re.compile(r"(?:cs_test_|pi_)[A-Za-z0-9]{10,200}")   # Sasha 327 · + a saved card's payment, back from his bank


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


__all__ = ["ops", "link", "paid_since", "message", "key", "LABEL", "checkout", "session_paid", "finish", "HELD_OR_TAKEN", "saved_card", "remove_saved",
           "intent_saved", "confirm_saved", "customer_of", "register_domains", "SAVE_WORDS"]
