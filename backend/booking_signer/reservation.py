"""S-64 · THE AGNOSTIC RESERVATION — one object for any activity, at any venue, at a time (`reservation/1`).

docs/sasha/S-64-agnostic-reservation.md §1. Step 1 of §7: the object, its validation, its canonical JSON and sha256,
and `from_particulars()` — today's call, email and link particulars turned into the object. Nothing here touches the
database or changes what any channel says; the renderers (step 4 on) are built from this object, and the restaurant
read-back must come out byte for byte as it does today.

The rules (§1.1):
  · NOTHING IS GUESSED. A field that isn't stated stays absent; validation refuses what is missing, never fills it.
  · `when.mode` is "at" (a date and an HH:MM, exact to the minute), "window" (both ends), or "venue_proposes" (no
    time at all — and so never `flow: book`, which needs one).
  · `extras.constraints` is ALWAYS {no_deposit: true, no_card: true}. It is not settable: Sasha holds no payment.
  · The object is canonical JSON (canonical.py, the task signer's own serialiser) with a sha256. Any change is a new
    request, a new read-back and a new yes.
"""
from __future__ import annotations

import hashlib
import re
from datetime import date, datetime, time
from typing import Any, Dict, Mapping, Optional, Sequence
from zoneinfo import ZoneInfo

from .canonical import canonical_json

SCHEMA = "reservation/1"
CATEGORIES = ("restaurant", "experience", "beauty", "appointment", "other")
UNITS = ("people", "sessions", "pieces", "places")
#: S-64 step 9 · "availability" — "when do you have space for …?" — is the §3 venue-proposes row as a flow of its own:
#: it asks, it never books, and whatever is offered comes back to the guest for a new yes
FLOWS = ("book", "quote_first", "availability", "cancel")
ASKING = ("quote_first", "availability")
MODES = ("at", "window", "venue_proposes")
CONSTRAINTS = {"no_deposit": True, "no_card": True}

#: the same rule calls.py applies to a name that is SPOKEN to a stranger
_NAME = re.compile(r"[^\W\d_]+(?:[ '’.-][^\W\d_]+)*", re.UNICODE)
_E164 = re.compile(r"\+[1-9]\d{7,14}")
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_HM = re.compile(r"([01]\d|2[0-3]):([0-5]\d)")


class ReservationRefused(ValueError):
    def __init__(self, rule: str, message: str) -> None:
        super().__init__(f"{rule}: {message}")
        self.rule = rule


def _text(v: Any, lo: int, hi: int, rule: str, what: str) -> str:
    if not isinstance(v, str) or not lo <= len(v.strip()) <= hi:
        raise ReservationRefused(rule, f"{what} is {lo}–{hi} characters")
    return " ".join(v.split())


def _opt_text(v: Any, hi: int, rule: str, what: str) -> Optional[str]:
    if v is None or v == "":
        return None
    return _text(v, 1, hi, rule, what)


def _int(v: Any, lo: int, hi: int, rule: str, what: str) -> int:
    if not isinstance(v, int) or isinstance(v, bool) or not lo <= v <= hi:
        raise ReservationRefused(rule, f"{what} is a whole number from {lo} to {hi}")
    return v


def _local_dt(v: Any, rule: str) -> str:
    """A LOCAL datetime at the venue: YYYY-MM-DDTHH:MM, no offset (the venue's timezone is `where.timezone`)."""
    if not isinstance(v, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T([01]\d|2[0-3]):[0-5]\d", v):
        raise ReservationRefused(rule, "a local date and time is YYYY-MM-DDTHH:MM, in the venue's own time")
    try:
        datetime.fromisoformat(v)
    except ValueError:
        raise ReservationRefused(rule, f"{v} is not a real date") from None
    return v


def validate(obj: Mapping[str, Any]) -> Dict[str, Any]:
    """The object, checked and normalised — or ReservationRefused naming the first thing wrong. Never fills a gap."""
    if not isinstance(obj, Mapping):
        raise ReservationRefused("reservation_malformed", "a reservation is a JSON object")
    if obj.get("schema") != SCHEMA:
        raise ReservationRefused("schema_unknown", f"schema must be {SCHEMA!r}")
    unknown = set(obj) - {"schema", "who", "what", "where", "when", "how_many", "extras", "flow", "backfilled"}
    if unknown:
        raise ReservationRefused("field_unknown", f"not part of {SCHEMA}: {sorted(unknown)}")

    who = obj.get("who") if isinstance(obj.get("who"), Mapping) else {}
    name = _text(who.get("name"), 2, 60, "name_invalid", "who.name")
    if not _NAME.fullmatch(name):
        raise ReservationRefused("name_invalid", "who.name is letters, spaces, apostrophes, dots and hyphens")
    contact_in = who.get("contact") if isinstance(who.get("contact"), Mapping) else {}
    contact: Dict[str, str] = {}
    if contact_in.get("email"):
        if not isinstance(contact_in["email"], str) or len(contact_in["email"]) > 254 or not _EMAIL.fullmatch(contact_in["email"].strip()):
            raise ReservationRefused("contact_invalid", "who.contact.email is not an email address")
        contact["email"] = contact_in["email"].strip()
    if contact_in.get("mobile_e164"):
        m = re.sub(r"[\s().-]", "", str(contact_in["mobile_e164"]))
        if not _E164.fullmatch(m):
            raise ReservationRefused("contact_invalid", "who.contact.mobile_e164 is + and 8–15 digits")
        contact["mobile_e164"] = m
    account_id = _text(who.get("account_id"), 1, 64, "account_invalid", "who.account_id")

    what = obj.get("what") if isinstance(obj.get("what"), Mapping) else {}
    category = what.get("category")
    if category not in CATEGORIES:
        raise ReservationRefused("category_invalid", f"what.category is one of {', '.join(CATEGORIES)}")
    what_out: Dict[str, Any] = {
        "activity": _text(what.get("activity"), 2, 120, "activity_invalid", "what.activity"),
        "activity_venue_lang": _text(what.get("activity_venue_lang"), 2, 160, "activity_invalid", "what.activity_venue_lang"),
        "category": category,
    }
    for k, hi in (("service", 120), ("spec", 1000)):
        v = _opt_text(what.get(k), hi, f"{k}_invalid", f"what.{k}")
        if v:
            what_out[k] = v
    photos = what.get("photos")
    if photos:
        if not isinstance(photos, Sequence) or isinstance(photos, str) or len(photos) > 5 or \
                not all(isinstance(p, str) and 1 <= len(p) <= 200 for p in photos):
            raise ReservationRefused("photos_invalid", "what.photos is up to five asset references")
        what_out["photos"] = list(photos)

    where = obj.get("where") if isinstance(obj.get("where"), Mapping) else {}
    tz = where.get("timezone")
    try:
        ZoneInfo(str(tz))
    except Exception:
        raise ReservationRefused("timezone_invalid", "where.timezone is an IANA zone (e.g. Europe/Madrid)") from None
    ids = where.get("venue_ids") or []
    if not isinstance(ids, Sequence) or isinstance(ids, str) or not all(isinstance(i, str) and i for i in ids):
        raise ReservationRefused("venue_ids_invalid", "where.venue_ids is a list of ids")
    where_out: Dict[str, Any] = {"venue_name": _text(where.get("venue_name"), 1, 120, "venue_invalid", "where.venue_name"),
                                 "timezone": str(tz), "venue_ids": list(ids)}
    if where.get("read_id"):
        where_out["read_id"] = _text(where["read_id"], 1, 64, "read_id_invalid", "where.read_id")
    addr = _opt_text(where.get("address"), 240, "address_invalid", "where.address")
    if addr:
        where_out["address"] = addr

    flow = obj.get("flow")
    if flow not in FLOWS:
        raise ReservationRefused("flow_invalid", f"flow is one of {', '.join(FLOWS)}")

    when = obj.get("when") if isinstance(obj.get("when"), Mapping) else {}
    mode = when.get("mode")
    if mode not in MODES:
        raise ReservationRefused("when_invalid", f"when.mode is one of {', '.join(MODES)}")
    when_out: Dict[str, Any] = {"mode": mode}
    if mode == "at":
        when_out["at"] = _local_dt(when.get("at"), "when_invalid")
    elif mode == "window":
        win = when.get("window") if isinstance(when.get("window"), Mapping) else {}
        a, b = _local_dt(win.get("earliest"), "when_invalid"), _local_dt(win.get("latest"), "when_invalid")
        if a >= b:
            raise ReservationRefused("when_invalid", "a window's earliest is before its latest")
        when_out["window"] = {"earliest": a, "latest": b}
        days = win.get("days")
        if days:
            if not isinstance(days, Sequence) or isinstance(days, str) or not all(isinstance(d, int) and not isinstance(d, bool) and 0 <= d <= 6 for d in days):
                raise ReservationRefused("when_invalid", "a window's days are weekday numbers, Monday 0 to Sunday 6")
            when_out["window"]["days"] = sorted(set(days))
    elif mode == "venue_proposes":
        if when.get("at") or when.get("window"):
            raise ReservationRefused("when_invalid", "venue_proposes carries no time of its own")
        if flow not in ASKING:
            raise ReservationRefused("when_invalid", "a booking needs a time: venue_proposes is for asking (quote_first or availability)")
    if when.get("duration_min") is not None:
        when_out["duration_min"] = _int(when["duration_min"], 5, 1440, "duration_invalid", "when.duration_min")
    if when.get("fixed_start") is not None:
        if not isinstance(when["fixed_start"], bool):
            raise ReservationRefused("when_invalid", "when.fixed_start is true or false")
        when_out["fixed_start"] = when["fixed_start"]

    hm = obj.get("how_many") if isinstance(obj.get("how_many"), Mapping) else {}
    unit = hm.get("unit")
    if unit not in UNITS:
        raise ReservationRefused("unit_invalid", f"how_many.unit is one of {', '.join(UNITS)}")
    how_many = {"count": _int(hm.get("count"), 1, 100, "count_invalid", "how_many.count"), "unit": unit}

    ex = obj.get("extras") if isinstance(obj.get("extras"), Mapping) else {}
    if "constraints" in ex and ex["constraints"] != CONSTRAINTS:
        raise ReservationRefused("constraints_fixed", "extras.constraints is always no deposit, no card — it cannot be changed")
    extras: Dict[str, Any] = {"constraints": dict(CONSTRAINTS)}
    for k, hi in (("notes", 500), ("accessibility", 200), ("dietary", 200)):
        v = _opt_text(ex.get(k), hi, f"{k}_invalid", f"extras.{k}")
        if v:
            extras[k] = v
    if ex.get("budget") is not None:
        b = ex["budget"] if isinstance(ex["budget"], Mapping) else {}
        cur = b.get("currency")
        if not isinstance(cur, str) or not re.fullmatch(r"[A-Z]{3}", cur):
            raise ReservationRefused("budget_invalid", "extras.budget.currency is a three-letter code")
        extras["budget"] = {"max": _int(b.get("max"), 1, 10_000_000, "budget_invalid", "extras.budget.max"), "currency": cur}

    out = {"schema": SCHEMA, "who": {"name": name, "contact": contact, "account_id": account_id}, "what": what_out,
           "where": where_out, "when": when_out, "how_many": how_many, "extras": extras, "flow": flow}
    if obj.get("backfilled") is True:
        out["backfilled"] = True
    return out


def sha256(obj: Mapping[str, Any]) -> str:
    """Over the VALIDATED object's canonical JSON — the same serialiser the booking-task signature uses."""
    return hashlib.sha256(canonical_json(validate(obj)).encode("utf-8")).hexdigest()


#: what a restaurant booking is called, per language, when the particulars say only "a table"
TABLE = {"en": "a table", "es": "una mesa", "pt": "uma mesa", "fr": "une table", "de": "einen Tisch", "it": "un tavolo"}


def from_particulars(p: Any, *, account_id: str, venue_name: str, timezone: str, lang: str,
                     venue_ids: Sequence[str] = (), read_id: Optional[str] = None, address: Optional[str] = None,
                     email: Optional[str] = None, flow: str = "book") -> Dict[str, Any]:
    """Today's particulars (calls.CallParticulars / emailing.EmailParticulars: on, at, party, name, phone?, guest_email?)
    → a validated `reservation/1`. A table, at a time, for people — which is all today's rungs can express."""
    on: date = p.on
    at: time = p.at
    obj = {
        "schema": SCHEMA,
        "who": {"name": p.name, "account_id": account_id,
                "contact": {k: v for k, v in (("email", email or getattr(p, "guest_email", None)),
                                              ("mobile_e164", getattr(p, "phone", None))) if v}},
        "what": {"activity": "a table", "activity_venue_lang": TABLE.get(lang.split("-")[0], TABLE["en"]), "category": "restaurant"},
        "where": {"venue_name": venue_name, "timezone": timezone, "venue_ids": list(venue_ids),
                  **({"read_id": read_id} if read_id else {}), **({"address": address} if address else {})},
        "when": {"mode": "at", "at": f"{on.isoformat()}T{at.strftime('%H:%M')}"},
        "how_many": {"count": p.party, "unit": "people"},
        "extras": {"constraints": dict(CONSTRAINTS)},
        "flow": flow,
    }
    return validate(obj)


def try_from_particulars(p: Any, **kw) -> Optional[Dict[str, Any]]:
    """S-64 step 3 · the write-through is ADDITIVE: a booking is never refused because its object could not be built
    (a form's free-text name, say). It is logged, and the row simply carries no request."""
    try:
        return from_particulars(p, **kw)
    except (ReservationRefused, AttributeError, TypeError) as e:
        import logging
        logging.getLogger("sasha.reservation").warning("[reservation] no reservation/1 object for this row: %s", e)
        return None


def columns(obj: Mapping[str, Any]) -> Dict[str, Any]:
    """What the object writes into trip_items' existing columns (§1.2), so readers that know only the columns work."""
    o = validate(obj)
    out: Dict[str, Any] = {"local_timezone": o["where"]["timezone"], "provider_name": o["where"]["venue_name"]}
    if o["when"]["mode"] == "at":
        d, hm = o["when"]["at"].split("T")
        out["local_date"], out["local_time"] = date.fromisoformat(d), time.fromisoformat(hm)
    if o["when"].get("duration_min"):
        out["duration_minutes"] = o["when"]["duration_min"]
    if o["how_many"]["unit"] == "people":
        out["party_size"] = o["how_many"]["count"]
    return out
