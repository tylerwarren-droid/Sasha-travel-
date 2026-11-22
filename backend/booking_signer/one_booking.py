"""Sasha 399 · A CONFIRMATION LANDS ON THE ACT IT BELONGS TO — the ONE rule every confirmation matcher decides by.

Found on Tyler's real 19 Nov booking (La Taberna de Peñalver, BARRIO SALAMANCA, 2 people, 21:45): three acts on that day at that
time carry "La Taberna de Peñalver" — two at Barrio Salamanca (a retry) and one at Cava Baja. Two of Sasha's three matchers took the
FIRST act whose name overlapped within 90 minutes (venue_submit.attach_from_mail, mailbox.match), so a confirmation for one could
be written onto another. Only written.pick asked "does exactly ONE booking fit?".

THE RULE (one place): the tiers are read in order; the first tier anything fits DECIDES —
  · exactly ONE booking fits → that booking (and the tier's name, the basis);
  · two or more fit → NO MATCH: held and said as unmatched ("not guessed"), never the nearest-looking one, never the next tier;
  · nothing fits any tier → no match (held and said).
"""
from __future__ import annotations

from typing import Any, Callable, Iterable, List, Mapping, Optional, Tuple

AMBIGUOUS = "two or more bookings fit by {rule} — not guessed"


def decide(tiers: Iterable[Tuple[str, List[Mapping[str, Any]]]], key: Callable[[Mapping[str, Any]], Any]
           ) -> Tuple[Optional[dict], str, bool]:
    """(the ONE booking, the rule that named it, True) — or (None, why not, False). Never a guess."""
    for rule, hits in tiers:
        ids = {key(h) for h in hits}
        if len(ids) == 1:
            return dict(hits[0]), rule, True
        if ids:
            return None, AMBIGUOUS.format(rule=rule), False
    return None, "nothing in it names exactly one of the bookings", False


__all__ = ["decide", "AMBIGUOUS"]
