"""
Stripe payments — the 'pay' half of talk → recommend → book → pay.

Uses Stripe **Checkout** (Stripe-hosted payment page): the backend creates a Checkout
Session and the browser redirects to `session.url`. Card data never touches our servers
(PCI SAQ-A) and we add zero client-side Stripe dependencies, so the frontend build stays
self-contained.

All Stripe calls run in a thread (`asyncio.to_thread`) because stripe-python is synchronous
— calling it directly in an async handler would block the event loop and stall other turns.

Configuration (test-mode-ready; absent keys → 501 so the demo degrades gracefully):
  STRIPE_SECRET_KEY        sk_test_... / sk_live_...
  STRIPE_WEBHOOK_SECRET    whsec_...   (for /webhook signature verification)
  STRIPE_SUCCESS_URL       where Checkout returns on success
  STRIPE_CANCEL_URL        where Checkout returns on cancel
"""

import asyncio
import os
import uuid
from typing import Optional

import httpx
import stripe
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.services import chat_store
from app.services.booking_ref import generate as generate_booking_ref

stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
SUCCESS_URL = os.getenv("STRIPE_SUCCESS_URL", "http://localhost:3000/vietnam?paid=1")
CANCEL_URL = os.getenv("STRIPE_CANCEL_URL", "http://localhost:3000/vietnam?canceled=1")
RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
RESEND_FROM = os.getenv("RESEND_FROM", "Sasha <onboarding@resend.dev>")

router = APIRouter(prefix="/api/payments", tags=["payments"])


class LineItem(BaseModel):
    name: str
    amount: float                       # major units, per item


class CheckoutRequest(BaseModel):
    # Two trustworthy inputs, both server-priced: `itinerary_id` (the whole trip) and
    # `offer_id` (a single stored hotel/flight/cab card). For either, the price is read from
    # the stored record and any client-sent `amount` is ignored — a browser must never be able
    # to name its own price. `amount`/`items` remain only for the legacy no-id path.
    amount: Optional[float] = None
    currency: str = "usd"
    description: str = "Sasha Travel booking"
    items: Optional[list[LineItem]] = None   # optional itemized breakdown (hotels/activities)
    itinerary_id: Optional[str] = None
    offer_id: Optional[str] = None           # a single bookable card (hotel / flight / cab)
    customer_email: Optional[str] = None


async def _send_confirmation_email(to: str, amount_cents: int, currency: str,
                                   booking_ref: Optional[str] = None) -> bool:
    """Best-effort booking confirmation via Resend. Returns whether it was actually sent.

    Returns False (rather than raising) when RESEND_API_KEY is unset or the send fails — the
    booking is already paid for and must never be undone by an email problem. The caller
    surfaces this so the UI doesn't promise an email that was never sent.
    """
    if not RESEND_API_KEY or not to:
        print(f"[payments] confirmation email skipped (key set: {bool(RESEND_API_KEY)}, to: {bool(to)})")
        return False
    total = f"{amount_cents / 100:,.0f} {currency.upper()}"
    ref_line = f"<p>Your booking reference: <b>{booking_ref}</b></p>" if booking_ref else ""
    try:
        async with httpx.AsyncClient(timeout=6) as http:
            res = await http.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {RESEND_API_KEY}", "Content-Type": "application/json"},
                json={
                    "from": RESEND_FROM,
                    "to": [to],
                    "subject": "Your Vietnam trip is booked ✈️",
                    "html": (
                        "<h2>You're all set!</h2><p>Thanks for booking your Vietnam adventure with "
                        f"Sasha. Total charged: <b>{total}</b>.</p>{ref_line}<p>We'll be in touch with your "
                        "detailed itinerary and confirmations shortly. Chúc bạn đi du lịch vui vẻ!</p>"
                    ),
                },
            )
        # The response was previously discarded, so a rejected send (bad key, unverified
        # sender domain — Resend's most common 4xx) looked exactly like a delivered one.
        if res.status_code >= 300:
            print(f"[payments] confirmation email rejected {res.status_code}: {res.text[:200]}")
            return False
        print(f"[payments] confirmation email sent to {to}")
        return True
    except Exception as e:
        print(f"[payments] confirmation email failed: {e}")
        return False


class ReserveRequest(BaseModel):
    # Exactly one of the two: a single stored hotel/flight/cab/restaurant card, or the whole
    # stored trip. Server-priced from the stored record, same trust model as checkout.
    offer_id: Optional[str] = None
    itinerary_id: Optional[str] = None


@router.post("/reserve")
async def reserve(body: ReserveRequest):
    """Reservation-only booking — no payment (client feedback 2026-08-11).

    Sasha simply takes the reservation: the booking row is created and its reference minted
    immediately, with a `resv-` pseudo session id in place of a Stripe session. Works with no
    Stripe keys configured, which is the demo's normal state. The paid flow (create-checkout /
    verify / webhook) remains intact for when payments are re-enabled.
    """
    offer = await chat_store.get_offer(body.offer_id) if body.offer_id else None
    if body.offer_id and not offer:
        raise HTTPException(status_code=404, detail="offer not found")

    itinerary = await chat_store.get_itinerary(body.itinerary_id) if (body.itinerary_id and not offer) else None
    if body.itinerary_id and not offer and not itinerary:
        raise HTTPException(status_code=404, detail="itinerary not found")
    if not offer and not itinerary:
        raise HTTPException(status_code=400, detail="offer_id or itinerary_id required")

    if offer:
        amount = float(offer.get("amount_usd") or 0)
        label = offer.get("label") or offer.get("name") or "Your reservation"
    else:
        amount = float(itinerary.get("total_usd") or 0)
        label = itinerary.get("title") or "Your trip"

    sid = f"resv-{uuid.uuid4()}"
    await chat_store.create_booking(
        booking_id=str(uuid.uuid4()),
        stripe_session_id=sid,
        itinerary_id=("" if offer else (body.itinerary_id or "")),
        user_id=chat_store.DEMO_USER_ID,
        amount_usd=amount,
        offer_id=(body.offer_id if offer else None),
        kind=(offer.get("kind") if offer else None),
        label=(label if offer else None),
    )
    ref = generate_booking_ref()
    booking = await chat_store.mark_booking_paid(sid, ref)
    if not booking:
        raise HTTPException(status_code=500, detail="could not record reservation")

    # Same freshness rule as the paid path: the just-reserved place shouldn't keep
    # re-surfacing as the stable top option on the next search.
    if offer and offer.get("session_id"):
        try:
            await chat_store.clear_session_cards(offer["session_id"], offer.get("kind"))
        except Exception as e:
            print(f"[payments] cache clear after reservation failed (non-fatal): {e}")

    return {
        "reserved": True,
        "booking_ref": ref,
        "amount_usd": amount,
        "item": ({"kind": offer.get("kind"), "label": label, "amount_usd": amount} if offer else None),
        "itinerary": (itinerary or {}).get("payload"),
    }


@router.post("/create-checkout")
async def create_checkout(body: CheckoutRequest):
    """Create a Stripe Checkout Session and return its hosted URL for redirect.

    The price comes from the STORED itinerary, not from the request. Previously the caller
    supplied `amount` and it was charged as given, so an $8,420 trip could be checked out for
    a cent. When `itinerary_id` is present its `total_usd` wins and any client-sent amount is
    ignored.
    """
    if not stripe.api_key:
        raise HTTPException(status_code=501, detail="payments not configured")

    # A single bookable card (hotel / flight / cab). Priced from the STORED offer, exactly like
    # a whole trip is priced from its stored itinerary — the browser's amount is never trusted.
    offer = await chat_store.get_offer(body.offer_id) if body.offer_id else None
    if body.offer_id and not offer:
        raise HTTPException(status_code=404, detail="offer not found")

    itinerary = await chat_store.get_itinerary(body.itinerary_id) if (body.itinerary_id and not offer) else None
    if body.itinerary_id and not offer and not itinerary:
        raise HTTPException(status_code=404, detail="itinerary not found")

    if offer:
        amount = float(offer.get("amount_usd") or 0)
        description = offer.get("label") or offer.get("name") or body.description
        line_items = [{
            "price_data": {
                "currency": body.currency.lower(),
                "product_data": {"name": description[:120]},
                "unit_amount": int(round(amount * 100)),
            },
            "quantity": 1,
        }]
        if body.amount is not None and abs(float(body.amount) - amount) > 0.01:
            print(f"[payments] client amount {body.amount} != stored offer {amount}; charging stored")
    elif itinerary:
        amount = float(itinerary.get("total_usd") or 0)
        description = itinerary.get("title") or body.description
        line_items = [{
            "price_data": {
                "currency": body.currency.lower(),
                "product_data": {"name": description[:120]},
                "unit_amount": int(round(amount * 100)),
            },
            "quantity": 1,
        }]
        if body.amount is not None and abs(float(body.amount) - amount) > 0.01:
            # Not fatal — the server price simply wins — but a mismatch means the client is
            # out of date or someone is probing, and it should be visible in the logs.
            print(f"[payments] client amount {body.amount} != stored {amount}; charging stored")
    else:
        # Legacy path: no stored trip (e.g. a one-off hotel). Nothing to validate against.
        amount = float(body.amount or 0)
        description = body.description
        if body.items:
            line_items = [{
                "price_data": {
                    "currency": body.currency.lower(),
                    "product_data": {"name": it.name[:120]},
                    "unit_amount": int(round(it.amount * 100)),
                },
                "quantity": 1,
            } for it in body.items if it.amount > 0]
        else:
            line_items = [{
                "price_data": {
                    "currency": body.currency.lower(),
                    "product_data": {"name": description},
                    "unit_amount": int(round(amount * 100)),
                },
                "quantity": 1,
            }]

    if amount <= 0:
        raise HTTPException(status_code=400, detail="amount must be greater than zero")

    try:
        session = await asyncio.to_thread(
            stripe.checkout.Session.create,
            mode="payment",
            line_items=line_items,
            # Stripe fills in the real session id. The return leg presents it and we ask
            # Stripe whether it was actually paid — the old success_url was a bare "?paid=1",
            # which meant typing that URL was indistinguishable from paying.
            success_url=SUCCESS_URL + ("&" if "?" in SUCCESS_URL else "?") + "session_id={CHECKOUT_SESSION_ID}",
            cancel_url=CANCEL_URL,
            customer_email=body.customer_email or None,
            metadata={"itinerary_id": body.itinerary_id or ""},
        )
    except stripe.error.StripeError as e:  # type: ignore[attr-defined]
        raise HTTPException(status_code=502, detail=f"stripe error: {getattr(e, 'user_message', None) or str(e)}")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"checkout error: {e}")

    # Pin the attempt server-side BEFORE the guest leaves for Stripe, so the return leg has an
    # authoritative row to reconcile against rather than trusting whatever comes back.
    try:
        await chat_store.create_booking(
            booking_id=str(uuid.uuid4()),
            stripe_session_id=session.id,
            itinerary_id=("" if offer else (body.itinerary_id or "")),
            user_id=chat_store.DEMO_USER_ID,
            amount_usd=amount,
            offer_id=(body.offer_id if offer else None),
            kind=(offer.get("kind") if offer else None),
            label=(description if offer else None),
        )
    except Exception as e:
        print(f"[payments] could not record booking attempt (non-fatal): {e}")

    return {"url": session.url, "id": session.id}


@router.get("/verify")
async def verify_payment(session_id: str):
    """Confirm a booking — the ONLY path that may do so.

    The browser comes back from Stripe with a session id. We ask STRIPE whether that session
    was actually paid; we never take the browser's word for it. Only on a genuine `paid`
    status is a reference minted (server-side) and the booking recorded.

    Idempotent: refreshing the return page, or the webhook racing the redirect, returns the
    same reference rather than minting a second one.
    """
    if not stripe.api_key:
        raise HTTPException(status_code=501, detail="payments not configured")
    try:
        session = await asyncio.to_thread(stripe.checkout.Session.retrieve, session_id)
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"unknown checkout session: {e}")

    if session.get("payment_status") != "paid":
        # Includes 'unpaid' (abandoned, or a delayed-notification method still pending).
        return {"paid": False, "status": session.get("payment_status")}

    booking, email_sent = await _confirm_paid_session(session)
    itinerary = await chat_store.get_itinerary(booking["itinerary_id"]) if booking and booking.get("itinerary_id") else None
    # A single-item booking (hotel/flight/cab) carries an offer instead of an itinerary, so the
    # return page can show an item confirmation rather than the whole-trip one.
    item = None
    if booking and booking.get("offer_id"):
        item = {
            "kind": booking.get("kind"),
            "label": booking.get("label"),
            "amount_usd": booking.get("amount_usd"),
        }
    return {
        "paid": True,
        "booking_ref": (booking or {}).get("booking_ref"),
        "amount_usd": (booking or {}).get("amount_usd"),
        "itinerary": (itinerary or {}).get("payload"),
        "item": item,
        # So the UI can say "a confirmation is on its way" only when one actually is.
        "email_sent": email_sent,
    }


async def _confirm_paid_session(session: dict):
    """Mark a genuinely-paid Stripe session as booked and mint its reference (once).

    Shared by the redirect (/verify) and the webhook so that whichever arrives first wins and
    the second is a no-op — the guest must never end up with two references for one trip.

    Returns (booking, email_sent). The email is best-effort and never blocks the booking: the
    money has already moved, so a mail failure must not undo a confirmed trip. It's reported
    back only so the UI can avoid promising an email that wasn't sent.
    """
    sid = session.get("id")
    if not sid:
        return None, False
    ref = generate_booking_ref()
    booking = await chat_store.mark_booking_paid(sid, ref)
    if not booking:
        print(f"[payments] paid session {sid} has no recorded booking row")
        return None, False

    # Booking done → drop this session's cached cards for the booked kind so the next search is
    # fresh (the just-booked place shouldn't keep re-surfacing as the stable top option). The
    # session lives on the OFFER, not the booking row, so resolve it there.
    if booking.get("offer_id"):
        try:
            offer = await chat_store.get_offer(booking["offer_id"])
            if offer and offer.get("session_id"):
                await chat_store.clear_session_cards(offer["session_id"], offer.get("kind"))
                print(f"[payments] cleared {offer.get('kind')} card cache for session {offer['session_id']}")
        except Exception as e:
            print(f"[payments] cache clear after booking failed (non-fatal): {e}")
    email = (session.get("customer_details") or {}).get("email") or session.get("customer_email")
    email_sent = False
    if email:
        email_sent = await _send_confirmation_email(
            email, session.get("amount_total") or 0, session.get("currency") or "usd",
            booking.get("booking_ref"),
        )
    return booking, email_sent


@router.post("/webhook")
async def stripe_webhook(request: Request):
    """Verify and handle Stripe events (payment confirmation).

    Stripe authenticates itself via the signature header — this endpoint is intentionally
    open (no client key) but refuses any event it cannot verify against the webhook secret.
    """
    if not STRIPE_WEBHOOK_SECRET:
        raise HTTPException(status_code=501, detail="webhook secret not configured")
    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")
    try:
        event = stripe.Webhook.construct_event(payload, sig, STRIPE_WEBHOOK_SECRET)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"invalid signature: {e}")

    if event["type"] == "checkout.session.completed":
        obj = event["data"]["object"]
        # `checkout.session.completed` does NOT mean paid: for delayed-notification methods
        # Stripe fires it with payment_status "unpaid" while the debit is still pending. It
        # used to email "You're all set!" on the event type alone.
        if obj.get("payment_status") != "paid":
            print(f"[payments] session {obj.get('id')} completed but unpaid — not confirming")
            return {"received": True}
        print(f"[payments] PAID id={obj.get('id')} itinerary={(obj.get('metadata') or {}).get('itinerary_id','')}")
        await _confirm_paid_session(obj)   # (booking, email_sent) — nothing to return to Stripe

    return {"received": True}
