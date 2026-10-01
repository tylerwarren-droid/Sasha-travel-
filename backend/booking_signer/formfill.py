"""S-64 step 10 · A BOOKING FORM FILLED FROM reservation/1 — by S-46's field roles, never by guess.

docs/sasha/S-64-agnostic-reservation.md §2 "Form fill", S-46 §1 (the role vocabulary). Given the fields a form has
(each with its S-46 role, and for a select its option texts), `fill` returns what goes in each — or STOPS, saying why,
before anything is typed. ⛔ The golden test: Psi's dry-run task fields, built from the object, are exactly today's
(`venues.build_for_venue`), so its `filled_values_sha256` and the guest's approval mean the same thing.

The rules:
  · date / time / date_time ← `when.at`, in the FORM's own format (the caller passes it: Psi wants "October 2, 2026"
    and "8:00 PM"). No set time (a window, venue-proposes) → stop: a form books a slot, it cannot ask.
  · party_size ← `how_many.count` ONLY when the unit is people; a form that counts people for a request counted in
    sessions or pieces → stop and ask.
  · person_name ← the name; given_name + family_name ← the first words and the last word, only when BOTH fields exist.
  · email / phone ← `who.contact`; asked for but not given → stop and ask (never invented, never Sasha's own).
  · free_text ← `extras.notes` and `what.spec`, each only if present.
  · service (a select of the venue's own options) ← `what.service`, by EXACT option text only. Otherwise stop and ask —
    never the nearest option.
  · consent is never ticked for the guest; challenge (a CAPTCHA) stops the fill; a trap (honeypot) is never touched.
  · anything else the form REQUIRES that the object does not hold → stop and ask. Optional unknowns are left empty.
"""
from __future__ import annotations

from datetime import date, time
from typing import Any, Callable, Dict, List, Mapping, Optional

from . import reservation as RS

BOOKING_ROLES = ("date", "time", "date_time", "party_size", "person_name", "given_name", "family_name", "email", "phone",
                 "free_text", "service", "consent", "challenge", "trap", "birth_date", "other")


class Stop(Exception):
    """The fill stops before anything is typed: `rule`, and the plain sentence the guest is asked."""
    def __init__(self, rule: str, ask: str) -> None:
        super().__init__(f"{rule}: {ask}")
        self.rule, self.ask = rule, ask


def fill(o: Mapping[str, Any], fields: List[Mapping[str, Any]], *,
         date_fmt: Callable[[date], str] = lambda d: d.isoformat(),
         time_fmt: Callable[[time], str] = lambda t: t.strftime("%H:%M"),
         date_time_fmt: Optional[Callable[[date, time], str]] = None) -> List[Dict[str, str]]:
    """[{name, value, selector}] for every field Sasha fills, in the form's order. Raises Stop instead of guessing."""
    o = RS.validate(o)
    roles = [f.get("role") for f in fields]
    unknown = sorted({r for r in roles if r not in BOOKING_ROLES})
    if unknown:
        raise Stop("role_unknown", f"the form has fields whose role isn't known ({', '.join(map(str, unknown))}) — a person should look first")
    if "challenge" in roles:
        raise Stop("challenge", "the form has a CAPTCHA or a question meant to stop machines; Sasha never solves one — you can send it yourself")
    contact = o["who"].get("contact") or {}
    on = at = None
    if o["when"]["mode"] == "at":
        d, hm = o["when"]["at"].split("T")
        on, at = date.fromisoformat(d), time.fromisoformat(hm)
    name = o["who"]["name"]
    words = name.split()
    out: List[Dict[str, str]] = []
    for f in fields:
        role, nm = f["role"], f["name"]
        required = bool(f.get("required"))
        value: Optional[str] = None
        if role in ("date", "time", "date_time"):
            if on is None:
                raise Stop("no_time", "a booking form books a set day and time; this request asks the venue when — it can't be sent by form")
            value = date_fmt(on) if role == "date" else time_fmt(at) if role == "time" else \
                (date_time_fmt(on, at) if date_time_fmt else f"{on.isoformat()} {at.strftime('%H:%M')}")
        elif role == "party_size":
            if o["how_many"]["unit"] != "people":
                raise Stop("unit_mismatch", f"the form asks how many people; your request is {o['how_many']['count']} "
                                            f"{o['how_many']['unit']} — how many people will come?")
            value = str(o["how_many"]["count"])
        elif role == "person_name":
            value = name
        elif role in ("given_name", "family_name"):
            if not ({"given_name", "family_name"} <= set(roles)) or len(words) < 2:
                raise Stop("name_split", "the form splits the name in a way that isn't clear — which part goes where?")
            value = " ".join(words[:-1]) if role == "given_name" else words[-1]
        elif role == "email":
            value = contact.get("email")
            if not value:
                raise Stop("email_missing", "the form needs your email address — which one should they have?")
        elif role == "phone":
            value = contact.get("mobile_e164")
            if not value:
                raise Stop("phone_missing", "the form needs a phone number — which one should they have?")
        elif role == "free_text":
            parts = [p for p in ((o.get("extras") or {}).get("notes"), o["what"].get("spec")) if p]
            value = " · ".join(parts) or None
        elif role == "service":
            want = o["what"].get("service")
            options = list(f.get("options") or [])
            if not want or want not in options:
                raise Stop("service_not_exact", "the form's service list doesn't have exactly what you asked for "
                                                f"({want or 'nothing named'}); its options are: {', '.join(options) or 'none read'} — which one?")
            value = want
        elif role in ("consent", "trap"):
            if role == "consent" and required:
                raise Stop("consent", "the form asks you to accept its terms; that is yours to tick, not Sasha's")
            continue   # never ticked for the guest; a honeypot is never touched
        if value is None:
            if required:
                raise Stop("required_unknown", f"the form requires '{f.get('label') or nm}', which your request doesn't say — what should go there?")
            continue
        out.append({"name": nm, "value": value, "selector": f.get("selector") or f'[name="{nm}"]'})
    return out


#: Psi's six fields by S-46 role — the one form specified today (venues.PSI)
PSI_FIELDS = [
    {"name": "rtb-date", "role": "date", "required": True},
    {"name": "rtb-time", "role": "time", "required": True},
    {"name": "rtb-party", "role": "party_size", "required": True},
    {"name": "rtb-name", "role": "person_name", "required": True},
    {"name": "rtb-email", "role": "email", "required": True},
    {"name": "rtb-phone", "role": "phone", "required": True},
]
