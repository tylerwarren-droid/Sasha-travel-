"""From a VERIFIED report to an outcome, and what the user is told (contract §7 and §8).

⚠ Only a report that has passed verify.verify_device_report reaches here, and the reading it carries is the
USER'S DEVICE'S observation — never ours. It is recorded as "read on the user's device".

The mapping is the contract's, and nothing else:
  sent false                                   → NO outcome. Nothing was asked of the venue.
  sent true, submitted_and_read, accepted      → requested   (⛔ never confirmed: this surface cannot reach it)
  sent true, submitted_and_read, refused       → declined    (with the venue's own words)
  sent true, submitted_and_read, neither       → unreachable (and the venue's words do NOT go on the record)
  sent true, anything else                     → failed
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional


@dataclass(frozen=True)
class Outcome:
    #: None when nothing was sent — then no outcome is recorded and no reservation exists.
    status: Optional[str]
    #: What to say to the user, in the contract's words.
    say: Optional[str]
    #: A one-line status for the trip view, or None.
    status_line: Optional[str]
    #: What the venue's page said, when the contract puts it on the record (requested, declined); else None.
    venue_words: Optional[str]
    #: The venue's own reservation number, when its page gave one. Psi's gives none.
    venue_reference: Optional[str]
    #: When the device read the page (reading.read_at), else None.
    observed_at: Optional[str]


def outcome_of(report: Mapping[str, Any], venue_short_name: str) -> Outcome:
    sent = report.get("sent") is True
    if not sent:
        # §7: "Recording 'unreachable' here would claim you tried and failed; you did not try."
        return Outcome(None, report.get("user_words"), None, None, None, None)

    reading = report.get("reading") if isinstance(report.get("reading"), Mapping) else {}
    observed_at = reading.get("read_at")
    if report.get("phase") == "submitted_and_read":
        matched = reading.get("matched")
        if matched == "accepted":
            return Outcome(
                "requested",
                "The request is in, sent from your machine. The ceiling on this form is REQUESTED: confirmation "
                "comes later, from the venue. Watch for their reply.",
                f"Asked {venue_short_name} via web_form; no confirmation yet. This is not a booking.",
                reading.get("quoted"), reading.get("reference"), observed_at,
            )
        if matched == "refused":
            quoted = reading.get("quoted")
            return Outcome(
                "declined",
                "The form would not take it. Their page said so on your machine — choose an alternative rather "
                "than repeating the ask.",
                f'{venue_short_name} declined: "{quoted}". That is the venue\'s answer.',
                quoted, None, observed_at,
            )
        return Outcome(
            "unreachable",
            "Your machine read the page after and it matched neither what acceptance looks like nor what refusal "
            "looks like. Nothing is established. Read it yourself before any retry — and a retry is a NEW intent.",
            f"Sent to {venue_short_name} from your machine; their answer could not be read. Nothing is established.",
            None, None, observed_at,
        )
    return Outcome(
        "failed",
        report.get("user_words") or (
            "It was sent from the user's machine and the page after could not be read. Check for the venue's email "
            "before any retry — a retry is a NEW intent, and a repeat could book twice."
        ),
        f"Sent to {venue_short_name} from your machine; the page after could not be read. Check your email before any retry.",
        None, None, observed_at,
    )
