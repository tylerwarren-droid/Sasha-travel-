"""CR 70 · PAYMENTS (Stripe), live in TEST MODE (decision 2: no real money). Sasha's own Stripe code (booking_signer.test_deposit: key() —
which refuses any key that isn't sk_test_ —, HTTP, session_paid) makes a Stripe TEST Checkout page for the act's total; Stripe sends the payer
back to AgAPI's own /pay/return/{token}; the act settles only when Stripe's own record says paid (the return page, or the poller), through
the same single-claim path as the sandbox's pay page (E.pay)."""
from __future__ import annotations

import asyncio
import hashlib
import logging
from typing import Optional

from .. import config
from ..adapters import Payments
from ..registry import AgapiError
from ..store import Store, ts

log = logging.getLogger("agapi.payments")


def _td():
    from booking_signer import test_deposit as TD
    return TD


def _table(store: Store) -> None:
    store.x("create table if not exists pay_sessions (token_hash text primary key, account text not null, act_id text not null, "
            "session_id text not null, created_at text not null, settled_at text)")


class LivePayments(Payments):
    def payment_link(self, token):            # (sync form unused live: link_for makes the Stripe page)
        raise AgapiError("internal", "use link_for")

    async def link_for(self, store: Store, account: str, act_id: str, token: str, total: dict, label: str) -> str:
        TD = _td()
        if not TD.key():
            raise AgapiError("upstream_unreachable", "No Stripe TEST key on agapi-live; nothing was charged.", {"service": "stripe_test"})
        back = f"{config.PUBLIC_URL}/pay/return/{token}"
        s, j = await TD.HTTP("POST", "/checkout/sessions", {
            "mode": "payment", "success_url": back + "?s={CHECKOUT_SESSION_ID}", "cancel_url": back + "?s={CHECKOUT_SESSION_ID}&cancelled=1",
            "line_items[0][quantity]": 1, "line_items[0][price_data][currency]": total["currency"].lower(),
            "line_items[0][price_data][unit_amount]": int(total["amount_minor"]),
            "line_items[0][price_data][product_data][name]": f"TEST payment — {label}"[:250],
            "metadata[test_payment]": "true", "metadata[agapi_act]": act_id, "metadata[agapi_account]": account})
        if s != 200 or j.get("livemode"):
            raise AgapiError("upstream_failed", "Stripe (test) refused the payment page; nothing was charged.", {"service": "stripe_test"})
        _table(store)
        store.x("insert into pay_sessions (token_hash, account, act_id, session_id, created_at) values (?, ?, ?, ?, ?)",
                hashlib.sha256(token.encode()).hexdigest(), account, act_id, j["id"], ts())
        return j["url"]

    async def smoke(self) -> dict:
        """Spends nothing, contacts nobody: the TEST account's balance (no charge, no page)."""
        TD = _td()
        if not TD.key():
            return {"ok": False, "why": "no sk_test_ key on agapi-live"}
        s, j = await TD.HTTP("GET", "/balance", {})
        return {"ok": s == 200 and j.get("livemode") is False, "status": s, "livemode": j.get("livemode")}


async def settle(store: Store, token_hash: str) -> Optional[dict]:
    """Stripe's own record says paid → the act (once: the pay token is claimed in a transaction) → E.pay. → the outcome, or None."""
    from .. import engine as E
    _table(store)
    row = store.one("select * from pay_sessions where token_hash = ?", token_hash)
    if not row or row["settled_at"]:
        return None
    paid = await _td().session_paid(row["session_id"])
    if not paid:
        return None
    with store.tx():
        act = store.one("select * from acts where account = ? and id = ? and pay_token_hash = ?", row["account"], row["act_id"], token_hash)
        if act:
            store.x("update acts set pay_token_hash = null where account = ? and id = ?", act["account"], act["id"])
            store.x("update pay_sessions set settled_at = ? where token_hash = ?", ts(), token_hash)
    if not act:
        return None
    return await E.pay(store, act)


async def poll(get_store) -> None:
    """agapi-live only: every 20 s, the open TEST sessions of the last 24 h (Stripe's record, never a guess)."""
    while True:
        try:
            st = get_store()
            _table(st)
            from ..store import later
            for r in st.q("select token_hash from pay_sessions where settled_at is null and created_at >= ?", later(minutes=-24 * 60)):
                await settle(st, r["token_hash"])
        except Exception as e:
            log.warning("pay poll: %s", type(e).__name__)
        await asyncio.sleep(20)
