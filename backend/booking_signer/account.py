"""Whose booking is this? S-62 step 1: the account the gate VERIFIED (identity.py) — a signed-in guest's token, the
founder's session, or the demo when his session asks for it. With none, every booking route refuses.

The demo id is the chat store's DEMO_USER_ID (backend/app/services/chat_store.py), restated here rather than imported
because backend/app/ is replaced wholesale by every CTO drop; a test holds the two equal.
"""
from __future__ import annotations

from fastapi import HTTPException
from starlette.requests import Request

#: = app.services.chat_store.DEMO_USER_ID ("Jon Peters"). Held equal by tests/test_booking_routes.py.
DEMO_ACCOUNT_ID = "11111111-1111-4111-8111-111111111111"


def account_for(request: Request) -> str:
    """The VERIFIED account a request acts for (gate.py → identity.resolve). ⛔ Never a default: no account, 401."""
    account = getattr(request.state, "account", None)
    if not account:
        raise HTTPException(401, {"ok": False, "rule": "account_required",
                                  "message": "sign in to book — this route acts for a signed-in account only"})
    return account
