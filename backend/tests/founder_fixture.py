"""Sasha 249 · WHO THE FOUNDER IS IN THE TEST FIXTURES: the seeded auth user 11111111-… (booking_signer/sql/001), named.

Until Sasha 249 an unset FOUNDER_ACCOUNT_ID made the founder that account by FALLBACK (identity.founder_account), and these
tests leaned on it. The fallback is gone — unset, nobody is the founder and his session is refused (one-truth-spec §1.2,
T2) — so a test that means "the founder" names him here, the way production names him (FOUNDER_ACCOUNT_ID is set there).
Imported for its effect: FOUNDER_ACCOUNT_ID defaults to FOUNDER for the run; a test that means "unset" patches it to "".
"""
import os

FOUNDER = "11111111-1111-4111-8111-111111111111"
os.environ.setdefault("FOUNDER_ACCOUNT_ID", FOUNDER)
