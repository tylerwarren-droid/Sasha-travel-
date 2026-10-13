"""Sasha 249 · ONE IDENTITY (EU 245 step 2; one-truth-spec §1.2–1.3) — the account ids and the founder decision, each
decided HERE and nowhere else.

  · DEMO_ACCOUNT_ID — the one demo account: what an anonymous visitor's chat is, and what `x-sasha-session: demo` names.
    Nobody's, and empty. Until Sasha 249 there were two: chat_store's 11111111 ("Jon Peters" — and the founder's own
    account while FOUNDER_ACCOUNT_ID was unset) and chat_account.PUBLIC_DEMO_ID (this id, Sasha 142). Nothing in the code
    resolves to 11111111 any more; its old rows stay where they are and belong to nobody.
  · founder_account() — FOUNDER_ACCOUNT_ID when set and well-formed, else None. ⛔ Never a fallback to the demo: unset,
    nobody is the founder, and a founder session is refused (chat_account) rather than quietly made the demo — the
    EU 238 passport landed in 11111111 exactly that way.
  · is_founder_test(acting, power=…) / is_founder(acting) / has(acting, power) — Sasha 254 item 5: every founder / test power
    reads the ONE record (agapi.person_access — AgAPI's person_access, through access.get): founder → record.founder; calls →
    record.calls; gmail / outlook → record.mailboxes; s2_demo / rehearsal → record.demo; real_venue_sends → record.mode live AND
    record.real_venue_sends. Until 254 each rule read its own env list (SASHA_CALLS_ACCOUNTS, SASHA_GMAIL_ACCOUNTS,
    SASHA_S2_DEMO_ACCOUNTS, SASHA_REHEARSAL / SASHA_DEMO_STANDIN with FOUNDER_ACCOUNT_ID …); none is read for a decision now.
    founder_account() stays for IDENTITY only — which account the founder's sign-in session names (the record has no "find
    the founder" operation); it grants nothing: the founder's powers are his record's.
"""
from __future__ import annotations

import os
import re
from typing import Optional

#: Sasha 249 · THE demo account (was chat_account.PUBLIC_DEMO_ID, Sasha 142): its own, empty, shared by anonymous visitors.
DEMO_ACCOUNT_ID = "00000000-0000-4000-8000-0000000d3e00"

_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


def founder_account() -> Optional[str]:
    """FOUNDER_ACCOUNT_ID (his own auth user), read at call time; None when unset or malformed — never the demo."""
    v = os.getenv("FOUNDER_ACCOUNT_ID", "").strip().lower()
    return v if _UUID.fullmatch(v) else None


def access(acting: Optional[str]) -> dict:
    """Sasha 254 · the acting person's record, as last read (≤ 60 s; warmed where the account is resolved) — CLOSED for nobody,
    a guest with no row, or a failed read: test, everything off."""
    from agapi import person_access as PA
    return PA.cached(acting)


#: Sasha 254 · each power → its field in the record (CR row 823). Nothing else grants one.
POWERS = {
    "founder": lambda r: bool(r.get("founder")),
    "calls": lambda r: r.get("calls") == "on",
    "gmail": lambda r: "gmail" in (r.get("mailboxes") or []),
    "outlook": lambda r: "outlook" in (r.get("mailboxes") or []),
    "s2_demo": lambda r: r.get("demo") == "s2_demo",
    "rehearsal": lambda r: r.get("demo") == "founder_rehearsal",
    "real_venue_sends": lambda r: r.get("mode") == "live" and r.get("real_venue_sends") == "on",
}


def has(acting: Optional[str], power: str) -> bool:
    if not acting:
        return False
    return POWERS[power](access(acting))


def is_founder_test(acting: Optional[str], *, power: str = "founder") -> bool:
    """Is `acting` granted this power by their record? (founder by default). Nobody (no account) never is."""
    return has(acting, power)


def is_founder(acting: Optional[str]) -> bool:
    """The founder himself: his record says founder = true."""
    return has(acting, "founder")


def founder_email() -> Optional[str]:
    """Sasha 254 · the founder's own address from HIS record (was SASHA_FOUNDER_EMAIL) — None when the record carries none."""
    f = founder_account()
    return access(f).get("email") if f and is_founder(f) else None


def signed_in(account: Optional[str]) -> bool:
    """A real account (a verified guest, or the founder): the products and anything personal may act on it."""
    return bool(account) and account != DEMO_ACCOUNT_ID


__all__ = ["DEMO_ACCOUNT_ID", "founder_account", "access", "has", "POWERS", "is_founder_test", "is_founder", "founder_email", "signed_in"]
