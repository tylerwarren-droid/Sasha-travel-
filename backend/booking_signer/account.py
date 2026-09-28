"""Whose booking is this? Today: always the one demo account (S-18 found Sasha has no signed-in user).

⚠⚠ THIS IS THE ONE PLACE TO CHANGE WHEN REAL ACCOUNTS ARRIVE. Every route asks `account_for(request)`
and nothing else; every stored row carries the account it belongs to. Until then, EVERY caller of these
routes is the demo account — see docs/sasha/S-17-signer-mounted.md §4 for exactly what that means and
what breaks when it changes.

The id is the chat store's DEMO_USER_ID (backend/app/services/chat_store.py). It is restated here rather
than imported, because backend/app/ is replaced wholesale by every CTO drop; a test holds the two equal.
"""
from __future__ import annotations

from starlette.requests import Request

#: = app.services.chat_store.DEMO_USER_ID ("Jon Peters"). Held equal by tests/test_booking_routes.py.
DEMO_ACCOUNT_ID = "11111111-1111-4111-8111-111111111111"


def account_for(request: Request) -> str:
    """The account a request acts for. ⚠ No authentication exists, so this cannot fail — and that is the
    problem it names, not a guarantee it gives."""
    return DEMO_ACCOUNT_ID
