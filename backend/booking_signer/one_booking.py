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


# ── Sasha 401 · EU 292 claim 2 · A REPLY LANDS ON THE BOOKING IT ANSWERS ────────────────────────────────────────────────────────────
# Measured: a venue's SMS / WhatsApp / voicemail landed on the LATEST call to that number (inbound_phone.call_for_number, "desc limit 1"),
# an email to Sasha's own address on the LAST email ever sent to that sender (ladder_store.email_for_sender) — "the most recent one",
# never which booking the words answer. Now every channel GATHERS the bookings it contacted at that number / address (a list), and this
# is the ONE reader of the reply's words into the rule's tiers — for any channel, the ones that don't exist yet too.

def day_time(c: Mapping[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    """A contacted booking's local day and time: its own local_date / local_time, else its date_time in its own zone."""
    if c.get("local_date"):
        t = c.get("local_time")
        return str(c["local_date"])[:10], (str(t)[:5] if t else None)
    dt = c.get("date_time")
    if dt is None:
        return None, None
    from datetime import datetime
    from zoneinfo import ZoneInfo
    if isinstance(dt, str):
        dt = datetime.fromisoformat(dt)
    try:
        dt = dt.astimezone(ZoneInfo(c.get("local_timezone") or "Europe/Madrid"))
    except Exception:
        pass
    return dt.date().isoformat(), dt.strftime("%H:%M")


def reply_for(cands: List[Mapping[str, Any]], words: Optional[str], now, key: Callable[[Mapping[str, Any]], Any]
              ) -> Tuple[Optional[dict], str, bool]:
    """The booking a reply answers, from the bookings its channel contacted at that sender: Sasha's reference → the venue's reference →
    the day AND time it names → the day it names → the only booking it can be answering. Several fit → none (held, said)."""
    from .mailbox import _when
    from .written import _compact
    hay = str(words or "")
    ch = _compact(hay)
    said = (_when(hay, now) or "") if hay.strip() else ""
    day, tm = (said[:10] or None), (said[11:16] if "T" in said else None)

    def ref(field: str):
        return [c for c in cands if c.get(field) and len(_compact(str(c[field]))) >= 4 and _compact(str(c[field])) in ch]
    tiers = [("Sasha's reference", ref("own_reference")),
             ("the venue's reference", ref("booking_reference")),
             ("the day and time it names", [c for c in cands if day and tm and day_time(c) == (day, tm)]),
             ("the day it names", [c for c in cands if day and day_time(c)[0] == day]),
             ("the only booking it can be answering", list(cands))]
    return decide(tiers, key)


HELD_LINE = ("{venue} sent a message I can't tie to one of your bookings with them, so I've kept it aside and changed nothing. "
             "Tell me which booking it's about.")


async def say_held(cands: List[Mapping[str, Any]], why: str) -> List[str]:
    """Held, and SAID to each person whose booking it might be — the venue's name only, never the words across accounts. → accounts told."""
    import logging
    log = logging.getLogger("booking_signer.one_booking")
    told: List[str] = []
    for account in dict.fromkeys(str(c["account_id"]) for c in cands if c.get("account_id")):
        venue = next((c.get("venue") for c in cands if str(c.get("account_id")) == account and c.get("venue")), None) or "A venue"
        try:
            from . import channel as CH
            await CH.tell(account, HELD_LINE.format(venue=venue))
            told.append(account)
        except Exception as e:   # still held (the inbound row, unattached); logged
            log.warning("[one_booking] a held reply wasn't said: %s", type(e).__name__)
    log.info("[one_booking] a reply held (%s): %d person(s) told", why, len(told))
    return told


__all__ = ["decide", "AMBIGUOUS", "reply_for", "day_time", "say_held", "HELD_LINE"]
