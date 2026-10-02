"""S-75 step 1 · THE ONE CONFIRMATION SENTENCE, owned by the server — the web chat and WhatsApp say the same words.

Until S-75 the sentence was built in the browser (ChatBookingCall.tsx, ChatCancel.tsx). WhatsApp has no browser, and two
copies drift, so the server builds it from the reservation/1 object and every prepare/plan response carries it. The yes
still binds to the full read-back's hash; this sentence is what is asked, never what is approved.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Mapping, Optional


def day_words(iso: Optional[str]) -> str:
    """'2026-10-03' → 'Saturday 3 October' (as the web's en-GB long date said it)."""
    try:
        d = date.fromisoformat(str(iso)[:10])
    except (TypeError, ValueError):
        return ""
    return f"{d:%A} {d.day} {d:%B}"


def _when(o: Mapping[str, Any]) -> tuple:
    w = o.get("when") or {}
    if w.get("mode") == "venue_proposes":
        return True, None, None
    at = str(w.get("at") or "")
    return False, at[:10] or None, at[11:16] or None


def confirm_sentence(o: Mapping[str, Any], venue: str) -> str:
    """'Book Botavara for 2, Saturday 3 October at 21:00, under Warren?'"""
    ask, on, at = _when(o)
    hm = o.get("how_many") or {}
    count, unit = hm.get("count"), hm.get("unit") or "people"
    surname = (str((o.get("who") or {}).get("name") or "").split() or [""])[-1]
    when = "whenever they have space" if ask else f"{day_words(on)} at {at}"
    return f"Book {venue} for {count}{'' if unit == 'people' else f' {unit}'}, {when}, under {surname}?"


def cancel_sentence(o: Mapping[str, Any], venue: str) -> str:
    """'Cancel Botavara, Saturday 3 October at 21:00, for 2, under Tyler Warren?'"""
    ask, on, at = _when(o)
    count = (o.get("how_many") or {}).get("count")
    name = str((o.get("who") or {}).get("name") or "").strip()
    day = day_words(on) or "no day set"
    return f"Cancel {venue}, {day}{f' at {at}' if at else ''}, for {count if count else '—'}, under {name or '—'}?"


__all__ = ["day_words", "confirm_sentence", "cancel_sentence"]
