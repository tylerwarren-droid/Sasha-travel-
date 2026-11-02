"""Sasha 327 · THE PAY PROOF on Stripe TEST, run by the gate after its verdict (never part of it — a Stripe outage never blocks a
deploy). Real Stripe calls through the ONE place money is taken (booking_signer/test_deposit.py), with Stripe's own test cards; a
scratch customer, nothing else touched. What the hosted page does when he ticks "save" (Stripe attaches the card to his customer) is
done here by attaching Stripe's test card directly — the page's own human step can't run on a server."""
from __future__ import annotations

import time

from booking_signer import test_deposit as TD


def _p(ok: bool, what: str, got) -> bool:
    print(f"PAY PROOF · {'PASS' if ok else 'FAIL'} · {what} — {str(got)[:240]}")
    return ok


async def run() -> bool:
    if not TD.key():
        print("PAY PROOF · skipped: no Stripe TEST key")
        return False
    t0, ok = int(time.time()) - 5, True
    s, cus = await TD.HTTP("POST", "/customers", {"description": "Sasha 327 pay proof (TEST)", "metadata[sasha_proof]": "327"})
    cid = cus["id"]
    real = TD.customer_of

    async def mine(account, create=True):
        return cid
    TD.customer_of = mine
    try:
        page = await TD.checkout("12.00", "EUR", "pay proof", "proof327", account="proof")   # the Pay-now page: wallets first, save ON
        s2, cs = await TD.HTTP("GET", f"/checkout/sessions/{page.get('id')}", {})
        ok &= _p(s2 == 200 and cs.get("customer") == cid and (cs.get("custom_text") or {}).get("submit") is not None
                 and "card" in (cs.get("payment_method_types") or []),
                 "the Pay-now page: his customer, the save wording, its payment methods", {"methods": cs.get("payment_method_types"),
                                                                                         "save": (cs.get("custom_text") or {}).get("submit")})
        await TD.HTTP("POST", f"/checkout/sessions/{page['id']}/expire", {})

        s3, pm = await TD.HTTP("POST", "/payment_methods/pm_card_visa/attach", {"customer": cid})   # what "save" leaves at Stripe
        card = await TD.saved_card("proof")
        ok &= _p(bool(card) and card["last4"] == "4242", "saved: Stripe holds it; Sasha says brand + last 4", card and card["words"])
        pi = await TD.intent_saved(card, "23.40", "EUR", "pay proof — second booking", "proof327b")
        r = await TD.confirm_saved(pi["id"])
        st = await TD.session_paid(pi["id"])
        ok &= _p(bool(r.get("paid") and st), "second booking: \"Yes\" alone charges the saved card", {"pi": pi["id"], **r, "paid": st})

        await TD.remove_saved("proof")
        await TD.HTTP("POST", "/payment_methods/pm_card_authenticationRequired/attach", {"customer": cid})
        card = await TD.saved_card("proof")
        pi = await TD.intent_saved(card, "31.00", "EUR", "pay proof — SCA", "proof327c")
        r = await TD.confirm_saved(pi["id"])
        ok &= _p(str(r.get("confirm_url") or "").startswith("https://"), "SCA test card: ONE Confirm-with-your-bank link",
                 {"pi": pi["id"], "link": (r.get("confirm_url") or "")[:60]})
        await TD.expire(pi["id"])

        await TD.remove_saved("proof")
        await TD.HTTP("POST", "/payment_methods/pm_card_chargeCustomerFail/attach", {"customer": cid})
        card = await TD.saved_card("proof")   # Stripe's card that attaches but fails when charged (4000 0000 0000 0341)
        if not card:
            raise RuntimeError("the decline test card wasn't saved at Stripe")
        pi = await TD.intent_saved(card, "9.00", "EUR", "pay proof — declined", "proof327d")
        r = await TD.confirm_saved(pi["id"])
        ok &= _p(bool(r.get("declined")), "declined: said plainly (the page is offered)", r.get("why"))
        await TD.expire(pi["id"])

        n = await TD.remove_saved("proof")
        ok &= _p(n >= 1 and await TD.saved_card("proof") is None, "remove my saved card: gone — the next booking shows the page", {"removed": n})

        s4, ev = await TD.HTTP("GET", "/events", {"created[gte]": t0, "limit": 40})
        types = [e.get("type") for e in (ev.get("data") or []) if (e.get("data") or {}).get("object", {}).get("customer") in (cid, None)
                 or (e.get("data") or {}).get("object", {}).get("id") == cid]
        print("PAY PROOF · Stripe TEST events: " + ", ".join(reversed(types[:40])))
    finally:
        TD.customer_of = real
        await TD.HTTP("DELETE", f"/customers/{cid}", {})
    print(f"PAY PROOF: {'PASS' if ok else 'FAIL'} (Stripe TEST, after the verdict — never part of it)")
    return ok
