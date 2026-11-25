"""Sasha 406b · the ONE detector of COMPONENT STATE written onto T (tests/test_s406b_t_holds_references): T (booking_signer/trip_record)
holds references only — which components belong to the journey and in what order. A component's state (its status, reference, time,
party, price, order, provider) lives in its OWN record (AgAPI's acts / bookings / group_bookings / flight_orders …). Every module that
writes such state onto T's tables (trips, trip_items, trip_basket_items) or into the person's record as a copy (s2_memory venue_acts,
prepared_pages, offers) is found here — by SQL and by call."""
from __future__ import annotations

import pathlib
import re
from typing import Dict, List

BACKEND = pathlib.Path(__file__).resolve().parents[1]
DIRS = ("agapi", "app", "booking_signer", "products")
STATE = r"(status|state|booking_reference|order_id|status_line|snapshot|price_amount|price_currency|price_source|provider_name|provider_ref|" \
        r"date_time|duration_minutes|location_name|party_size|depart_date|return_date|escalation_notes|paid_session|failed_why|type)"
#: T's own rows are `trips` (the journey: its title, plan, span, lifecycle — T's, not a component's); a component's state on T is a copy in
#: trip_items / trip_basket_items. (trips' span widened FROM a booking is a copy too: named in the test, plan_store.)
WRITE = re.compile(r"\b(insert\s+into|update)\s+(trip_items|trip_basket_items)\b", re.I)
COPY_KINDS = re.compile(r"put_kind\([^,]+,\s*(\"venue_acts\"|PREPARED_KIND|OFFERS_KIND)")


def _sql(src: str) -> List[str]:
    out = []
    for m in re.finditer(r'"(?:[^"\\\n]|\\.)*"(?:\s*(?:\n\s*)?(?:\+\s*)?"(?:[^"\\\n]|\\.)*")*', src):
        out.append(re.sub(r'"\s*(?:\n\s*)?(?:\+\s*)?"', "", m.group(0)))
    return out


def findings(rel: str, src: str) -> List[str]:
    found = []
    for s in _sql(src):
        m = WRITE.search(s)
        if not m:
            continue
        tail = s[m.end():]
        cols = re.search(r"\bset\s+(.*?)(?:\bwhere\b|\bfrom\b|$)", tail, re.I | re.S) if m.group(1).lower().startswith("update") \
            else re.search(r"\(([^)]*)\)", tail)
        if cols and re.search(rf"\b{STATE}\b", cols.group(1), re.I):
            what = " ".join(cols.group(1).split())[:80]
            found.append(f"{m.group(2).lower()}: {what}")
    for m in COPY_KINDS.finditer(src):
        found.append(f"s2_memory copy: {m.group(1)}")
    return found


def writers() -> Dict[str, List[str]]:
    hits = {}
    for d in DIRS:
        for p in sorted((BACKEND / d).rglob("*.py")):
            rel = p.relative_to(BACKEND).as_posix()
            f = findings(rel, p.read_text())
            if f:
                hits[rel] = f
    return hits
