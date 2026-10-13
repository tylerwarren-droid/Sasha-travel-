"""Sasha 249 · WHO THE FOUNDER IS IN THE TEST FIXTURES: the seeded auth user 11111111-… (booking_signer/sql/001), named.

Until Sasha 249 an unset FOUNDER_ACCOUNT_ID made the founder that account by FALLBACK (identity.founder_account), and these
tests leaned on it. The fallback is gone — unset, nobody is the founder and his session is refused (one-truth-spec §1.2,
T2) — so a test that means "the founder" names him here, the way production names him (FOUNDER_ACCOUNT_ID is set there).
Imported for its effect: FOUNDER_ACCOUNT_ID defaults to FOUNDER for the run; a test that means "unset" patches it to "".

Sasha 254 item 5 · ACCESS IS THE RECORD (agapi.person_access). The code no longer reads FOUNDER_ACCOUNT_ID for a power, nor any
SASHA_*_ACCOUNTS / SASHA_REHEARSAL / SASHA_DEMO_STANDIN / SASHA_FOUNDER_EMAIL list. The older tests still SAY their fixture that
way (a patched FOUNDER_ACCOUNT_ID, an env list); `fixture_record` turns what a test says into the RECORD that person would have,
through person_access's test hook (RESOLVER) — test-only, no network. New tests install records directly
(person_access.install / person_access.records) and never use env lists.
"""
import os

FOUNDER = "11111111-1111-4111-8111-111111111111"
os.environ.setdefault("FOUNDER_ACCOUNT_ID", FOUNDER)


def _env_list(name: str) -> set:
    return {a.strip().lower() for a in os.getenv(name, "").split(",") if a.strip()}


def _founder_now() -> str:
    """The founder as the test names him now (FOUNDER_ACCOUNT_ID, or a patched accounts/identity.founder_account)."""
    from booking_signer import identity as I   # identity.founder_account reads accounts.founder_account at call time: a patch of either shows
    return str(I.founder_account() or "").lower()


def fixture_record(account: str) -> dict:
    """The record a test's fixture describes for this account (the old lists' meaning, as of 253): everyone "live" (the old
    person_mode's default when the auth user is unread), the founder's powers, and each listed account's power."""
    a = (account or "").lower()
    founder = bool(a) and a == _founder_now()
    gmail = founder or a in _env_list("SASHA_GMAIL_ACCOUNTS")
    outlook = gmail or a in _env_list("SASHA_OUTLOOK_ACCOUNTS")
    demo = None
    if founder and ("1" in (os.getenv("SASHA_REHEARSAL", ""), os.getenv("SASHA_DEMO_STANDIN", ""))):
        demo = "founder_rehearsal"
    elif a in _env_list("SASHA_S2_DEMO_ACCOUNTS"):
        demo = "s2_demo"
    return {"mode": "live", "founder": founder,
            "calls": "on" if founder or a in _env_list("SASHA_CALLS_ACCOUNTS") else "off",
            "real_venue_sends": "on" if founder or a in _env_list("SASHA_REAL_CONTACT_ACCOUNTS") else "off",
            "mailboxes": [m for m, on in (("gmail", gmail), ("outlook", outlook)) if on], "demo": demo,
            "email": (os.getenv("SASHA_FOUNDER_EMAIL", "").strip().lower() or None) if founder else None,
            "real_money": "off", "source": "fixture"}


def install() -> None:
    from agapi import person_access as PA
    PA.RESOLVER = fixture_record


install()
