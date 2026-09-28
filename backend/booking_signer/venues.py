"""The venues a booking task can be built for — today exactly one, Restaurante Psi (contract §3.6).

⚠ The SERVER builds the task. The page sends the booking's particulars (date, time, party, name, email,
phone); this module turns them into the venue's own formats, the fields, the spec, the standing, and the
five read-back lines the user hears. The page never builds, edits or re-signs a task (contract §5.5), so it
never gets to choose a selector, a pattern or a URL.

Everything below is copied from the contract, and tests/test_booking_routes.py holds it to the §12 vector
byte for byte: the same particulars must produce the vector's fields, spec, standing and read-back.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import date, time
from typing import Any, Mapping

from .issue import BOOKING_STEPS, filled_values_lines

_MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August",
           "September", "October", "November", "December")


class ParticularsRefused(Exception):
    """The particulars cannot become a task. `rule` names why; nothing was recorded."""

    def __init__(self, rule: str, message: str) -> None:
        super().__init__(f"{rule}: {message}")
        self.rule = rule


@dataclass(frozen=True)
class Particulars:
    """A booking as the user asked for it — before any venue's formats are applied."""

    on: date
    at: time
    party: int
    name: str
    email: str
    phone: str


def parse_particulars(body: Mapping[str, Any]) -> Particulars:
    """Strict: an ISO date, a 24-hour HH:MM, a whole party of 1–100, and non-empty name/email/phone.

    ⚠ Values are trimmed ONCE, here, and the trimmed value is used for both the field and the read-back —
    so what the user hears is exactly what would be sent."""
    raw_date, raw_time = body.get("date"), body.get("time")
    try:
        on = date.fromisoformat(raw_date) if isinstance(raw_date, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw_date) else None
    except ValueError:
        on = None
    if on is None:
        raise ParticularsRefused("date_invalid", "date is a calendar date, YYYY-MM-DD")
    m = re.fullmatch(r"(\d{2}):(\d{2})", raw_time) if isinstance(raw_time, str) else None
    if not m or int(m.group(1)) > 23 or int(m.group(2)) > 59:
        raise ParticularsRefused("time_invalid", "time is a 24-hour clock time, HH:MM")
    party = body.get("party")
    if not isinstance(party, int) or isinstance(party, bool) or not 1 <= party <= 100:
        raise ParticularsRefused("party_invalid", "party is a whole number from 1 to 100")
    text = {}
    for k in ("name", "email", "phone"):
        v = body.get(k)
        if not isinstance(v, str) or not v.strip():
            raise ParticularsRefused(f"{k}_missing", f"{k} is required and non-empty")
        text[k] = v.strip()
    return Particulars(on=on, at=time(int(m.group(1)), int(m.group(2))), party=party, **text)


# ── Restaurante Psi — contract §3.4 and §3.6, verbatim ──────────────────────────────────────────

PSI_SPEC = {
    "accepted": {
        "text_pattern": "your\\s+booking\\s+request\\s+is\\s+waiting\\s+to\\s+be\\s+confirmed",
        "example": "Thanks, your booking request is waiting to be confirmed. Updates will be sent to the email address you provided.",
        "reference_pattern": None,
        "selector": None,
    },
    "refused": [
        {"text_pattern": "Please\\s+enter\\s+the\\s+date\\s+you\\s+would\\s+like\\s+to\\s+book", "meaning": "no date was given (case date_missing)", "selector": ".rtb-error"},
        {"text_pattern": "The\\s+date\\s+you\\s+entered\\s+is\\s+not\\s+valid", "meaning": "the date was not one the calendar offers (case date_invalid)", "selector": ".rtb-error"},
        {"text_pattern": "bookings\\s+must\\s+be\\s+made\\s+more\\s+than\\s+\\d+\\s+days?\\s+in\\s+advance", "meaning": "inside the venue's booking notice, or in the past (cases inside_24h_notice, date_in_the_past)", "selector": ".rtb-error"},
        {"text_pattern": "no\\s+bookings\\s+are\\s+being\\s+accepted\\s+on\\s+that\\s+date", "meaning": "the venue takes no bookings that day (case closed_day_sunday)", "selector": ".rtb-error"},
        {"text_pattern": "no\\s+bookings\\s+are\\s+being\\s+accepted\\s+at\\s+that\\s+time", "meaning": "the venue takes no bookings at that time (case closed_time_5pm)", "selector": ".rtb-error"},
        {"text_pattern": "Please\\s+enter\\s+the\\s+time\\s+you\\s+would\\s+like\\s+to\\s+book", "meaning": "no time was given (case time_missing)", "selector": ".rtb-error"},
        {"text_pattern": "The\\s+time\\s+you\\s+entered\\s+is\\s+not\\s+valid", "meaning": "the time was not one the form offers (case time_invalid)", "selector": ".rtb-error"},
        {"text_pattern": "Please\\s+enter\\s+a\\s+name\\s+for\\s+this\\s+booking", "meaning": "no name was given (case name_missing)", "selector": ".rtb-error"},
        {"text_pattern": "Please\\s+let\\s+us\\s+know\\s+how\\s+many\\s+people\\s+will\\s+be\\s+in\\s+your\\s+party", "meaning": "no valid party size (cases party_missing, party_zero, party_not_a_number)", "selector": ".rtb-error"},
        {"text_pattern": "Please\\s+enter\\s+an\\s+email\\s+address\\s+so\\s+we\\s+can\\s+confirm\\s+your\\s+booking", "meaning": "no email was given (case email_missing)", "selector": ".rtb-error"},
        {"text_pattern": "\\S[\\s\\S]*", "meaning": "the plugin rendered a validation error in its error container (.rtb-error) — the wording may be translated, so this is matched by WHERE it renders, not by what it says", "selector": ".rtb-error"},
    ],
}

#: Opaque signed data (contract §3.4): copied exactly, never resolved.
PSI_STANDING = {
    "established": True,
    "basis": "reference_install",
    "source": "our own WordPress Playground install (WP 6.6, PHP 7.4) of Five Star Restaurant Reservations 1.4.6 and 1.5.3 — the releases whose form matches Psi's served form exactly — 25 September 2026, 14 refusal cases; docs/sasha/S-08-reference-install.json. NOT observed at Psi.",
}


@dataclass(frozen=True)
class Venue:
    key: str
    name: str                 #: as the read-back says it
    short_name: str           #: as the status lines say it (contract §8)
    origin: str
    url: str
    timezone: str             #: IANA; a reservation's local date and time are in this zone
    confirmation_email_field: str
    outcome_ceiling: str


PSI = Venue(
    key="restaurante-psi",
    name="Restaurante Psi, Lisbon",
    short_name="Restaurante Psi",
    origin="https://www.restaurante-psi.com",
    url="https://www.restaurante-psi.com/reservas/",
    timezone="Europe/Lisbon",
    confirmation_email_field="rtb-email",
    outcome_ceiling="requested",
)

VENUES = {PSI.key: PSI}


def psi_date(d: date) -> str:
    """The page's `mmmm d, yyyy` — `October 2, 2026`, never ISO."""
    return f"{_MONTHS[d.month - 1]} {d.day}, {d.year}"


def psi_time(t: time) -> str:
    """The page's `h:i A` — `8:00 PM`, never `20:00`."""
    h = t.hour % 12 or 12
    return f"{h}:{t.minute:02d} {'AM' if t.hour < 12 else 'PM'}"


def _sha256hex(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def build_for_venue(venue: Venue, p: Particulars) -> dict:
    """The unsigned task (without its instants), the read-back lines, and both hashes.

    ⚠ The approval is bound to `read_back_sha256` and `filled_values_sha256`; the issue path recomputes
    both, so nothing here can drift from what is signed without the signer refusing it."""
    if venue.key != PSI.key:  # one venue is specified; any other would be a guess
        raise ParticularsRefused("venue_not_specified", f"no booking task is specified for {venue.key!r}")
    d, t = psi_date(p.on), psi_time(p.at)
    fields = [
        {"name": "rtb-date", "value": d, "selector": '[name="rtb-date"]'},
        {"name": "rtb-time", "value": t, "selector": '[name="rtb-time"]'},
        {"name": "rtb-party", "value": str(p.party), "selector": '[name="rtb-party"]'},
        {"name": "rtb-name", "value": p.name, "selector": '[name="rtb-name"]'},
        {"name": "rtb-email", "value": p.email, "selector": '[name="rtb-email"]'},
        {"name": "rtb-phone", "value": p.phone, "selector": '[name="rtb-phone"]'},
    ]
    filled = _sha256hex(filled_values_lines(fields))
    task = {
        "origin": venue.origin,
        "url": venue.url,
        "steps": list(BOOKING_STEPS),
        "fields": fields,
        "required": ["rtb-date", "rtb-time", "rtb-party", "rtb-name", "rtb-email", "rtb-phone"],
        "envelope": [{"name": "action", "value": "booking_request"}],
        "spec": PSI_SPEC,
        "outcome_ceiling": venue.outcome_ceiling,
        "filled_values_sha256": filled,
    }
    lines = [
        f"{venue.name}.",
        f"{d} at {t}, for {p.party}.",
        f"Under the name {p.name}.",
        f"They will have your email, {p.email}, and your telephone, {p.phone}.",
        "I will open their booking page on this machine and send it from here. Shall I?",
    ]
    return {
        "task": task,
        "standing": dict(PSI_STANDING),
        "read_back_lines": lines,
        "read_back_sha256": _sha256hex("\n".join(lines)),
        "filled_values_sha256": filled,
    }
