"""Sasha 408 · SASHA'S WORDS COME FROM THE RECORD — the ONE writer of what Sasha says about a prepared booking's state.

The live case (Tyler, /s2, 26 Nov 06:54 UTC, "Wellness Boutique Experience", Fri 27 Nov 12:00, 1 person): she said "their form asks you to prove
you're human, so I've filled it in for you" over six Copy buttons. AgAPI's prepare result for it recorded `form: None` ("no form schema on the
venue's own site") and carried nothing into their page — nothing was filled. Sasha decided "filled" from `bool(prep)` (venues), said a fixed
"Done — it's on your screen", the status "their page is filled in" for EVERY hand-over (s2_status), and AgAPI's phrasebook's
"prepared_link_captcha" ("filled in for you … prove you're human") whenever its decision chose it.

  facts(prep)          AgAPI's OWN record of the prepare → {filled: [labels it put INTO their page], copy: [labels to copy], their_form: bool,
                       human_check: bool, human_step: AgAPI's words for the person's step}. Nothing else decides these.
  handover_line(...)   THE sentence over a prepared hand-over: what the record says was filled (or that the details are to copy), and the
                       human step only when AgAPI's record names one.
  status_words(row)    a prepared hand-over's status, from the same facts kept on its row — never "filled in" unless the record said so.
  UNREAD               the one line for a record that couldn't be read: never a state.
"""
from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional

UNREAD = "I can't see that yet — I couldn't read the booking record just now."
#: AgAPI's phrasebook keys (booking_rules, vendored) whose fixed text CLAIMS a fill — said only as the record holds it (handover_line);
#: their text is AgAPI's to fix (FOR CR, Sasha 408). Every other key is AgAPI's own words for what it did, said as given.
FILL_CLAIMS = frozenset({"done_form", "prepared_link", "prepared_link_captcha", "platform_step"})


def _labels(xs: Any) -> List[str]:
    out = []
    for x in xs or []:
        if isinstance(x, Mapping):
            v = x.get("label") or x.get("field") or x.get("role")
        else:
            v = x
        if v:
            out.append(str(v))
    return out


def facts(prep: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    """What AgAPI's prepare RECORDED — never inferred from there being a result."""
    p = prep or {}
    ho = p.get("hand_over") if isinstance(p.get("hand_over"), Mapping) else {}
    dec = p.get("decision") if isinstance(p.get("decision"), Mapping) else {}
    ch = dec.get("channel") if isinstance(dec.get("channel"), Mapping) else {}
    their_form = isinstance(p.get("form"), Mapping) and bool(p.get("form"))   # AgAPI filled THEIR form (a schema it read), to the last press
    filled = _labels(ho.get("carried")) + (_labels(p.get("fills")) if their_form else [])
    copy = _labels(ho.get("copy")) or ([] if their_form else _labels(p.get("fills")))
    return {"read": bool(prep), "their_form": their_form, "filled": list(dict.fromkeys(filled)), "copy": list(dict.fromkeys(copy)),
            "human_check": bool(ch.get("captcha")) or bool(isinstance(p.get("form"), Mapping) and p["form"].get("captcha")),
            "human_step": str(p.get("human_step") or "") or None}


def handover_line(venue: str, f: Mapping[str, Any], surface: str = "s2") -> str:
    """THE line over a prepared hand-over, from the record's facts. Each clause only when the record holds it."""
    where = "below" if surface == "wa" else "on your screen"
    if f.get("read") and f.get("filled"):
        head = f"{venue}'s booking page has your details filled in"
    else:
        head = f"Here's {venue}'s booking page with your details {where} to copy in"
    tail = " — their page asks you to prove you're human, which only you can do" if f.get("human_check") else ""
    return f"{head}{tail}. It's booked only when their page confirms it."


#: Sasha 270 · CR 101 · a link the person handed over, by AgAPI's OWN classification of it (venue.profile link: its `kind`) — each line is
#: said only when the record names that kind (voice.link_line)
LINK_THEIRS = {"captcha": "Their form asks you to prove you're human, so that last step is yours — here it is.",
               "needs_sign_in": "Their form needs you to sign in, so it's yours to fill — here it is.",
               "platform": "Here's their page — you finish it there.",
               "not_a_booking_form": "That page isn't a booking form I can fill in — here it is to look at.",
               "cant_read": "I couldn't read that page from here — here it is to open yourself."}


def slot_words(filled: bool, who: str, when: str) -> str:
    """A platform's page: "filled in" only when its link's OWN record says it carries the slot (booking_links.slot_filled)."""
    return f"it's filled in for {who}, {when}" if filled else f"pick {when} for {who} there"


def details_state(filled: bool) -> str:
    """A live hand-over's own record (handover.py: the fields its fill put in) → the words for it."""
    return "Your details are filled in" if filled else "Your details are ready to copy there"


def status_words(row: Mapping[str, Any]) -> str:
    """A prepared hand-over's status, from the facts kept on its row (older rows hold none: no fill is claimed)."""
    if row.get("filled") is True:
        return "Prepared, not booked — their page has your details filled in, waiting for you to book it there"
    if row.get("filled") is False:
        return "Prepared, not booked — your details are ready to copy into their page; you book it there"
    return "Prepared, not booked — waiting for you to book it on their page"


__all__ = ["slot_words", "LINK_THEIRS", "FILL_CLAIMS", "facts", "handover_line", "status_words", "details_state", "UNREAD"]
