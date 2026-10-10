"""CR 74b step 4 · RENTAL COVER (EU 216 §3): country + rental company + the person's cards → the COUNTER CARD: decline / keep / optional,
each line quoted from the card's terms and the rental company's own terms for that country. Pure; vectors pin it.

  decline   only when the card's terms say it covers damage AND theft, say the rental company's CDW must be declined, AND list the excluded
            countries without this one — otherwise a CHECK line (ask the claims line first), never a guess
  keep      the third-party liability the rental includes (the rental terms' quote) — and the card's own "liability isn't covered" quote
  optional  the rental company's excess cover, with its price and the excess it removes (quoted)
Never "you don't need insurance": the guard refuses any such line (and the tests assert it)."""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

COUNTRY_NAMES = {
    "PT": ("portugal",), "ES": ("spain", "españa", "espana"), "FR": ("france", "francia"), "IT": ("italy", "italia"), "IE": ("ireland", "irlanda", "republic of ireland"),
    "GB": ("united kingdom", "uk", "great britain", "reino unido", "northern ireland"), "IL": ("israel",), "JM": ("jamaica",), "AU": ("australia",),
    "NZ": ("new zealand",), "US": ("united states", "usa", "estados unidos"), "DE": ("germany", "alemania"), "GR": ("greece", "grecia"),
    "MX": ("mexico", "méxico"), "CR": ("costa rica",), "NL": ("netherlands", "países bajos"), "AT": ("austria",), "CH": ("switzerland", "suiza"),
}
NEVER = re.compile(r"(don'?t|do not|no) need (any )?(insurance|cover)|you('re| are) (fully )?covered\b(?! for)", re.I)
FRAMING = "From your card's terms and the rental company's own terms for this country, each line quoted. You decide what to buy at the counter."
UNSAID = "the terms I've read don't say"


def _q(c: dict) -> dict:
    return {"claim_id": c["id"], "quote": c["quote"], "source_url": c["source_url"], "read_at": c["read_at"][:10], **({"warning": c["warning"]} if c.get("warning") else {})}


def _get(claims: List[dict], benefit: str, field: str) -> Optional[dict]:
    return next((c for c in claims if c["benefit"] == benefit and c["field"].split("@")[0] == field), None)


def _claims_for(claims: List[dict], field: str, benefit: str) -> Optional[dict]:
    """A claims fact for this benefit first (field@benefit), then a general one."""
    return (next((c for c in claims if c["benefit"] == "claims" and c["field"] == f"{field}@{benefit}"), None)
            or next((c for c in claims if c["benefit"] == "claims" and c["field"] == field), None))


def _money(v: dict) -> str:
    return f"{v['currency']} {v['amount_minor'] / 100:,.0f}" + (f" {v['per']}" if v.get("per") else "")


def card_status(card: dict, country: str, days: Optional[int], vehicle: Optional[str]) -> Dict[str, Any]:
    cl = card["claims"]
    rent = [c for c in cl if c["benefit"] == "car_rental"]
    names = COUNTRY_NAMES.get(country, (country.lower(),))
    out: Dict[str, Any] = {"card": card["name"], "quotes": []}
    if not rent:
        return {**out, "status": "not_stated", "say": f"{card['name']}: rental car cover — {UNSAID}."}
    exc = _get(cl, "car_rental", "excluded_countries")
    if exc and any(any(n == x.lower().strip() or n in x.lower() for n in names) for x in exc["value"]):
        return {**out, "status": "excluded", "say": f"{card['name']}: its terms exclude rentals in this country.", "quotes": [_q(exc)]}
    mx = _get(cl, "car_rental", "max_rental_days")
    if days and mx and days > mx["value"]:
        return {**out, "status": "too_long", "say": f"{card['name']}: its terms cover rentals of up to {mx['value']} days.", "quotes": [_q(mx)]}
    veh = _get(cl, "car_rental", "excluded_vehicles")
    if vehicle and veh and any(vehicle.lower() in x.lower() for x in veh["value"]):
        return {**out, "status": "vehicle_excluded", "say": f"{card['name']}: its terms exclude this kind of vehicle.", "quotes": [_q(veh)]}
    dt = _get(cl, "car_rental", "damage_theft_covered")
    if not dt or dt["value"] is not True:
        return {**out, "status": "unclear", "say": f"{card['name']}: whether it covers damage and theft — {UNSAID}.", "quotes": [_q(c) for c in rent[:2]]}
    ct = _get(cl, "car_rental", "cover_type")
    return {**out, "status": "covers", "cover_type": ct["value"] if ct else None, "country_listed": bool(exc),
            "say": f"{card['name']}: covers damage and theft" + (f" as {ct['value']} cover" if ct else "") + ".",
            "quotes": [_q(dt)] + ([_q(ct)] if ct else []) + ([_q(exc)] if exc else [])}


def compose(country: str, company: str, rental: Optional[List[dict]], rental_note: Optional[str], cards: List[dict],
            days: Optional[int] = None, vehicle: Optional[str] = None) -> Dict[str, Any]:
    """rental: the rental company's claims for this country (None → not read). cards: [{name, claims}]."""
    statuses = [card_status(c, country, days, vehicle) for c in cards]
    order = {"covers": 0, "unclear": 1, "not_stated": 2, "too_long": 3, "vehicle_excluded": 3, "excluded": 4}
    ranked = sorted(zip(statuses, cards), key=lambda t: (order[t[0]["status"]], 0 if t[0].get("cover_type") == "primary" else 1,
                                                         0 if t[0].get("country_listed") else 1, t[0]["card"]))
    best_s, best_c = ranked[0] if ranked else (None, None)
    rc = rental or []
    decline, keep, optional, check, conditions, bring, report = [], [], [], [], [], [], []
    cdw = _get(rc, "rental_terms", "cdw_name")
    cdw_words = cdw["value"] if cdw else "the rental company's collision damage waiver (CDW/LDW)"
    if best_s and best_s["status"] == "covers":
        cl = best_c["claims"]
        must = _get(cl, "car_rental", "must_decline_rental_cdw")
        if must and must["value"] is True and best_s["country_listed"]:
            decline.append({"say": f"Decline {cdw_words}: your {best_c['name']}'s terms say it covers damage and theft"
                                   + (f" as {best_s['cover_type']} cover" if best_s.get("cover_type") else "")
                                   + " when you decline it, and this country isn't among the excluded countries they list.",
                            "quotes": best_s["quotes"] + [_q(must)]})
        elif not best_s["country_listed"]:
            check.append({"say": f"Your {best_c['name']}'s terms I've read cover damage and theft but don't list which countries are excluded: "
                                 "ask the card's claims line before you decline the rental company's cover.", "quotes": best_s["quotes"]})
        else:
            check.append({"say": f"Your {best_c['name']}'s terms I've read cover damage and theft but don't say whether you must decline the "
                                 "rental company's cover: ask the card's claims line before you decide.", "quotes": best_s["quotes"]})
        for f in ("paid_with_card_condition", "must_decline_rental_cdw", "max_rental_days", "excluded_vehicles"):
            c = _get(cl, "car_rental", f)
            if c:
                conditions.append({"say": {"paid_with_card_condition": "Pay for the whole rental with this card.",
                                           "must_decline_rental_cdw": "Declining the rental company's CDW/LDW is a condition of the card's cover.",
                                           "max_rental_days": f"Rentals of up to {c['value']} days.", "excluded_vehicles": "Some vehicles are excluded."}[f],
                                   "quotes": [_q(c)]})
        lim = _get(cl, "car_rental", "limit")
        if lim:
            optional.append({"say": f"Your card's own limit for rental damage: {_money(lim['value'])}.", "quotes": [_q(lim)]})
        bring.append({"say": f"The card you pay with: {best_c['name']}.", "quotes": []})
    elif cards:
        check.append({"say": "None of your cards' terms I've read say they cover damage to a rental car here: the rental company's own cover is "
                             "below, quoted. You decide.", "quotes": [q for s in statuses for q in s["quotes"]][:4]})
    card_liab = best_c and _get(best_c["claims"], "car_rental", "liability_included")
    r_liab = _get(rc, "rental_terms", "liability_included")
    r_lim = _get(rc, "rental_terms", "liability_limit") or _get(rc, "rental_terms", "liability_note")
    if r_liab and r_liab["value"] is True:
        keep.append({"say": "Keep the third-party liability the rental includes." + (f" Limit: {_money(r_lim['value'])}." if r_lim and isinstance(r_lim["value"], dict) else ""),
                     "quotes": [_q(r_liab)] + ([_q(r_lim)] if r_lim else [])})
    else:
        why = UNSAID if rental is not None else (rental_note or "the rental company's terms aren't read").rstrip(".")
        keep.append({"say": f"Third-party liability included in the rental: {why} — ask at the counter.", "quotes": []})
    if card_liab and card_liab["value"] is False:
        keep.append({"say": "Your card doesn't cover liability.", "quotes": [_q(card_liab)]})
    exc_amt, sc_name, sc_price, sc_rm = (_get(rc, "rental_terms", f) for f in ("excess_amount", "super_cover_name", "super_cover_price", "super_cover_removes_excess"))
    if sc_name or sc_price:
        optional.insert(0, {"say": f"Optional: {sc_name['value'] if sc_name else 'the excess cover'}"
                                   + (f" ({_money(sc_price['value'])})" if sc_price else "")
                                   + (" removes the excess" if sc_rm and sc_rm["value"] else "")
                                   + (f" of {_money(exc_amt['value'])}" if exc_amt else "") + ".",
                            "quotes": [_q(c) for c in (sc_name, sc_price, sc_rm, exc_amt) if c]})
    elif exc_amt:
        optional.insert(0, {"say": f"The rental's excess: {_money(exc_amt['value'])}.", "quotes": [_q(exc_amt)]})
    for f, say in (("idp_required", "International Driving Permit"), ("licence_rule", "Driving licence"), ("deposit", "Deposit")):
        c = _get(rc, "rental_terms", f)
        if c:
            v = c["value"]
            bring.append({"say": f"{say}: " + (("required" if v else "not required") if isinstance(v, bool) else _money(v) if isinstance(v, dict) else str(v)) + ".",
                          "quotes": [_q(c)]})
    r_rep = _get(rc, "rental_terms", "accident_report_deadline_hours")
    if r_rep:
        report.append({"say": f"Report an accident to {company} within {r_rep['value']} hours.", "quotes": [_q(r_rep)]})
    if best_s and best_s["status"] == "covers":
        for f, say in (("notice_deadline_days", "Notify the card's claims administrator within {v} days."), ("phone", "Card claims line: {v}.")):
            c = _claims_for(best_c["claims"], f, "car_rental")
            if c:
                report.append({"say": say.format(v=c["value"]), "quotes": [_q(c)]})
    out = {"framing": FRAMING, "country": country, "company": company, "card": best_c["name"] if best_s and best_s["status"] == "covers" else None,
           "cards": [{k: s[k] for k in ("card", "status", "say", "quotes")} for s in statuses],
           "counter": {"decline": decline, "keep": keep, "optional": optional, "check": check},
           "conditions": conditions, "bring": bring, "report": report, **({"rental_note": rental_note} if rental_note else {})}
    for part in [out["counter"][k] for k in out["counter"]] + [conditions, bring, report]:
        for line in part:
            if NEVER.search(line["say"]):
                raise AssertionError("a counter-card line may never say you don't need insurance")
    return out
