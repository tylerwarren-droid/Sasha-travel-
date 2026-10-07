"""CR 52 · test helpers for the calm, one-step-at-a-time products: everything said (texts AND button messages), and a
step's buttons pressed the way a person would."""
from __future__ import annotations

from booking_signer import guest_whatsapp as GW


def everything(case) -> str:
    return "\n".join(case.bodies() + [c for c, _ in GW.SENDER.contents])


def press(case, *payloads: str) -> str:
    for p in payloads:
        case.say("", payload=p)
    return everything(case)


def walk_consulate(case) -> str:
    """RelocateMe after the consulate: every step and its details, as tapping through them shows them."""
    return press(case, "rx:more:consulate", "rx:go:fees", "rx:more:fees", "rx:go:book", "rx:more:book", "rx:go:forms",
                 "rx:more:forms", "rx:go:docs", "rx:more:checklist")
