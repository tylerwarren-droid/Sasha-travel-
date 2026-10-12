"""Whose booking is this? S-62 step 1: the account the gate VERIFIED (identity.py) — a signed-in guest's token, the
founder's session, or the demo when his session asks for it. With none, every booking route refuses.

Sasha 249 · the demo id is app.services.accounts.DEMO_ACCOUNT_ID — the ONE constant — imported, never restated (until 249
this was a second copy of chat_store's 11111111, held equal only by a test).
"""
from __future__ import annotations

from fastapi import HTTPException
from starlette.requests import Request

from app.services.accounts import DEMO_ACCOUNT_ID  # noqa: F401  (Sasha 249 · the one demo id, re-exported)


def account_for(request: Request) -> str:
    """The VERIFIED account a request acts for (gate.py → identity.resolve). ⛔ Never a default: no account, 401."""
    account = getattr(request.state, "account", None)
    if not account:
        raise HTTPException(401, {"ok": False, "rule": "account_required",
                                  "message": "sign in to book — this route acts for a signed-in account only"})
    return account
