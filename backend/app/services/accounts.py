"""Sasha 249 · ONE IDENTITY (EU 245 step 2; one-truth-spec §1.2–1.3) — the account ids and the founder decision, each
decided HERE and nowhere else.

  · DEMO_ACCOUNT_ID — the one demo account: what an anonymous visitor's chat is, and what `x-sasha-session: demo` names.
    Nobody's, and empty. Until Sasha 249 there were two: chat_store's 11111111 ("Jon Peters" — and the founder's own
    account while FOUNDER_ACCOUNT_ID was unset) and chat_account.PUBLIC_DEMO_ID (this id, Sasha 142). Nothing in the code
    resolves to 11111111 any more; its old rows stay where they are and belong to nobody.
  · founder_account() — FOUNDER_ACCOUNT_ID when set and well-formed, else None. ⛔ Never a fallback to the demo: unset,
    nobody is the founder, and a founder session is refused (chat_account) rather than quietly made the demo — the
    EU 238 passport landed in 11111111 exactly that way.
  · is_founder_test(acting, …) — "is this the founder's own test session": the ONE founder decision that the five rules
    (guest_accounts.founder, ladder_routes._s2_demo_account / standin, guest_whatsapp.rehearsal, switching.on) and the
    founder-only routes call. Each rule keeps its own switch (a flag, an account list); only the founder test is here.
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


def _listed(env: str) -> set:
    return {a.strip().lower() for a in os.getenv(env, "").split(",") if a.strip()}


def is_founder_test(acting: Optional[str], *, flag: Optional[str] = None, listed: Optional[str] = None,
                    founder: bool = True) -> bool:
    """Is `acting` the founder's own test session for this rule?
      · flag   — an env switch the rule needs ON ("1"); off → False for everyone;
      · founder — the founder's account counts (False: only the accounts the rule lists, e.g. the S2 demo);
      · listed — an env var of extra accounts (comma-separated) the rule also admits.
    Nobody (no account) is never the founder, and with FOUNDER_ACCOUNT_ID unset nobody is."""
    if not acting:
        return False
    if flag is not None and os.getenv(flag, "") != "1":
        return False
    who = str(acting).lower()
    if founder:
        f = founder_account()
        if f is not None and who == f:
            return True
    return listed is not None and who in _listed(listed)


def is_founder(acting: Optional[str]) -> bool:
    """The founder himself (FOUNDER_ACCOUNT_ID) — is_founder_test with no switch and no list."""
    return is_founder_test(acting)


def signed_in(account: Optional[str]) -> bool:
    """A real account (a verified guest, or the founder): the products and anything personal may act on it."""
    return bool(account) and account != DEMO_ACCOUNT_ID


__all__ = ["DEMO_ACCOUNT_ID", "founder_account", "is_founder_test", "is_founder", "signed_in"]
