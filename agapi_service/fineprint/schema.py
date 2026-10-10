"""The benefit schema (EU 216 §1): each benefit's fields and their value types. A value outside its type is DROPPED, never guessed;
a numeric value must appear in its own quote (so "$500" can't come from a sentence that says "$5,000")."""
from __future__ import annotations

import re
from typing import Any, Dict, Optional

# type: money · hours · days · months · count · percent · bool · enum:<a|b> · text · list · earn
BENEFITS: Dict[str, Dict[str, str]] = {
    "travel_insurance": {"trip_cancellation_limit": "money", "trip_interruption_limit": "money", "trip_delay_threshold_hours": "hours",
                         "trip_delay_limit": "money", "baggage_delay_threshold_hours": "hours", "baggage_delay_limit": "money",
                         "baggage_loss_limit": "money", "paid_with_card_condition": "text", "exclusions": "list"},
    "car_rental": {"cover_type": "enum:primary|secondary", "damage_theft_covered": "bool", "liability_included": "bool",
                   "max_rental_days": "days", "excluded_countries": "list", "excluded_vehicles": "list",
                   "must_decline_rental_cdw": "bool", "paid_with_card_condition": "text", "limit": "money"},
    "purchase_protection": {"days": "days", "per_claim_limit": "money", "annual_limit": "money", "exclusions": "list"},
    "extended_warranty": {"months_added": "months", "limit": "money"},
    "lounges": {"programme": "text", "guest_rules": "text", "visit_limit": "text"},
    "fx_fee": {"percent": "percent"},
    "points": {"earn_rate": "earn", "transfer_partners": "list", "caps": "text"},
    "claims": {"administrator": "text", "url": "text", "phone": "text", "email": "text", "notice_deadline_days": "days",
               "documents_deadline_days": "days"},
    # CR 74b · a RENTAL COMPANY's own terms for one country (step 4: the counter card)
    "rental_terms": {"excess_amount": "money", "cdw_name": "text", "cdw_price": "money", "super_cover_name": "text", "super_cover_price": "money",
                     "super_cover_removes_excess": "bool", "liability_included": "bool", "liability_limit": "money", "liability_note": "text",
                     "deposit": "money", "idp_required": "bool", "licence_rule": "text", "min_driver_age": "count",
                     "accident_report_deadline_hours": "hours", "accident_report_rule": "text", "cross_border": "text", "fuel_policy": "text"},
}
BENEFITS["rental_terms"]["contact_email"] = "text"     # CR 75 · where the rental company takes accident reports / disputes, as its terms say
# CR 75 · a COUNTRY's official accident rules (step 7, the playbook): the authority's own page or the law's own text
BENEFITS["accident_rules"] = {"emergency_number": "text", "safety_steps": "list", "scene_duties": "list", "police_when": "text",
                              "statement_name": "text", "statement_advice": "text", "notice_deadline_days": "days", "notice_deadline_hours": "hours",
                              "notice_rule": "text"}
CARD_BENEFITS = tuple(b for b in BENEFITS if b not in ("rental_terms", "accident_rules"))
CATEGORIES = ("travel", "flights", "hotels", "car_rental", "dining", "groceries", "gas", "transit", "everything_else")
NUM_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "twelve": 12,
             "fifteen": 15, "twenty": 20, "thirty": 30, "forty-five": 45, "sixty": 60, "ninety": 90,
             # CR 75 · the official sources' own languages (a deadline written in words is still in its quote)
             "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "siete": 7, "diez": 10, "quince": 15, "treinta": 30, "sesenta": 60,
             "deux": 2, "trois": 3, "cinq": 5, "dix": 10, "quinze": 15, "trente": 30,
             "tre": 3, "cinque": 5, "sette": 7, "dieci": 10, "quindici": 15, "trenta": 30, "sessanta": 60,
             "zwei": 2, "drei": 3, "fünf": 5, "sieben": 7, "zehn": 10, "vierzehn": 14, "dreißig": 30,
             "dois": 2, "três": 3, "oito": 8, "trinta": 30,
             "einer woche": 7, "una semana": 7, "une semaine": 7, "una settimana": 7, "uma semana": 7}


def _num(s: str) -> Optional[float]:
    s = s.strip().lower().replace(",", "")
    if s in NUM_WORDS:
        return float(NUM_WORDS[s])
    try:
        return float(s)
    except ValueError:
        return None


def _in_quote(n: float, quote: str) -> bool:
    """The number, as the quote writes it (10,000 · 10.000 · 10000 · 3% · three)."""
    q = (quote or "").lower()
    for m in re.finditer(r"\d[\d,.\s]*\d|\d", q):
        raw = m.group(0).replace(" ", "")
        for cand in (raw.replace(",", ""), raw.replace(".", "").replace(",", "."), raw.replace(",", ".")):
            try:
                if abs(float(cand) - n) < 1e-9:
                    return True
            except ValueError:
                pass
    return any(v == n and re.search(rf"\b{re.escape(w)}\b", q) for w, v in NUM_WORDS.items())


def normal(benefit: str, field: str, value: str, quote: str) -> Optional[Any]:
    """The claim's value in its type — or None (dropped)."""
    t = BENEFITS.get(benefit, {}).get(field)
    v = (value or "").strip()
    if not t or not v:
        return None
    if t == "money":
        m = re.fullmatch(r"([\d.,]+)\s+([A-Z]{3})(?:\s+(per [a-z ]{3,30}))?", v)
        n = m and _num(m.group(1))
        if not m or n is None or not _in_quote(n, quote):
            return None
        return {"amount_minor": int(round(n * 100)), "currency": m.group(2), **({"per": m.group(3)} if m.group(3) else {})}
    if t in ("hours", "days", "months", "count"):
        n = _num(v.split()[0])
        if n is None or n != int(n) or not _in_quote(n, quote):
            return None
        return int(n)
    if t == "percent":
        n = _num(v.rstrip("%"))
        if n is None or not 0 <= n <= 20 or not _in_quote(n, quote):
            return None
        return {"basis_points": int(round(n * 100))}
    if t == "bool":
        return {"true": True, "false": False}.get(v.lower())
    if t.startswith("enum:"):
        return v.lower() if v.lower() in t[5:].split("|") else None
    if t == "list":
        items = [x.strip() for x in v.split(";") if x.strip()]
        return items[:20] or None
    if t == "earn":
        m = re.fullmatch(r"([\d.]+)\s+(points?|miles?|percent)\s+per\s+([A-Z]{3})\s+on\s+([a-z_]+)", v)
        n = m and _num(m.group(1))
        if not m or n is None or m.group(4) not in CATEGORIES or not _in_quote(n, quote):
            return None
        return {"rate_x100": int(round(n * 100)), "unit": m.group(2).rstrip("s"), "per": m.group(3), "category": m.group(4)}   # no floats in claims
    return v[:300]
