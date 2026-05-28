"""
Kanoe booking reference generator.

Format: KNO-YYYYMMDD-XXXXXX  (6 uppercase alphanumeric chars)
Example: KNO-20260527-A3Z9QR

References are generated here and stored in the booking_references table.
They are used as partner_order_id when submitting orders to RateHawk so
the external provider never receives a caller-supplied identifier.
"""

import random
import string
from datetime import date


_ALPHABET = string.ascii_uppercase + string.digits


def generate() -> str:
    suffix = "".join(random.choices(_ALPHABET, k=6))
    return f"KNO-{date.today().strftime('%Y%m%d')}-{suffix}"
