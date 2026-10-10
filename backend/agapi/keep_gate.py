"""Sasha 224 · WHERE the Keep is on. /s2: always (its own block). S1 (/next): only with SASHA_KEEP_S1=1, and then only for the
founder's account — off by default, so S1 is exactly as before. Flip back = unset SASHA_KEEP_S1 (or anything but "1").

    keep_on(account, surface) → bool
"""
from __future__ import annotations

import os
from typing import Optional


def s1_on(account: Optional[str]) -> bool:
    if os.getenv("SASHA_KEEP_S1", "").strip() != "1" or not account:
        return False
    from booking_signer.guest_accounts import founder
    return founder(account)


def keep_on(account: Optional[str], surface: Optional[str]) -> bool:
    return surface == "s2" or s1_on(account)


__all__ = ["keep_on", "s1_on"]
