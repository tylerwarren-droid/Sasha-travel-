"""Sasha 265 · item 4 (CR 99 §4c): a booking call is placed only from its AgAPI act (booking_signer.call_routes.ACT_REQUIRED, on in
production — pinned by test_s265). The older tests below drive the PLACING MACHINERY itself (claim, Bland, the sweeper, receipts,
confirmation calls) — the machinery an act's call goes through too — with Sasha's own read-backs; they open the act check for their own
run only (put back by addCleanup)."""
from booking_signer import call_routes as CR


def open_act_check(tc) -> None:
    tc.addCleanup(setattr, CR, "ACT_REQUIRED", True)
    CR.ACT_REQUIRED = False
