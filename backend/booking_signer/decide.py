"""Sasha 130 (2) · THE DECISION WORKFLOW — how Sasha books a venue, decided in ONE place, with the reason the guest is shown.

    own form                                  → fill it after the guest's yes
    platform only (no own form)               → ONE-TAP: the venue's booking page on WhatsApp (pre-filled where the platform
                                                allows); the guest presses; Sasha matches the confirmation email in Gmail
                                                and files it — or a direct call, if the guest prefers
    no form · open now · phone · scripted     → call
    closed / email only / unscripted language → email; then, if no reply, a call offered at their opening
    the guest can always override             → any route that exists ("call them", "email them", "send me the link")

Pure: no I/O. The caller (guest_whatsapp) supplies what the venue read found; this says what to do and why, in the
guest's words. Nothing here dials, sends or presses — each route keeps its own read-back and yes.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional

ROUTES = ("form", "one_tap", "call", "email")


@dataclass(frozen=True)
class Venue:
    form: bool = False                 #: their own website's form, mapped and allowed
    platform: Optional[str] = None     #: a booking platform's page ("CoverManager"), when that's how they take bookings
    phone: bool = False                #: a number read for them
    email: bool = False                #: an address read for them
    open_now: Optional[bool] = None    #: None = their hours aren't known
    opens_at: Optional[str] = None     #: "13:00", their next opening today, when known
    scripted: bool = True              #: Sasha has a reviewed call script in their language
    calls_on: bool = True              #: calls are on, for this account and the server
    language_label: str = ""           #: "Vietnamese", for the reason when unscripted


@dataclass(frozen=True)
class Decision:
    route: Optional[str]               #: one of ROUTES, or None when nothing can be done from here
    reason: str                        #: shown to the guest, before any read-back
    then: Optional[str] = None         #: the follow-up, said now ("if they haven't replied by 13:00, I'll offer to call")
    alternatives: List[str] = field(default_factory=list)   #: the routes the guest may choose instead


_PREFER = (("call", re.compile(r"\b(call|phone|ring|llama|llamar|llámales|telefonea)\b", re.I)),
           ("email", re.compile(r"\b(e-?mail|correo|write to them|escr[ií]beles)\b", re.I)),
           ("one_tap", re.compile(r"\b(link|their page|booking page|i'?ll book it myself|myself|enlace)\b", re.I)),
           ("form", re.compile(r"\b(form|formulario)\b", re.I)))


def preference(text: str) -> Optional[str]:
    """The route the guest asked for in words, or None. "Call them instead" → "call"."""
    for route, rx in _PREFER:
        if rx.search(text or ""):
            return route
    return None


def available(v: Venue) -> List[str]:
    """Every route that exists for this venue right now, in the default order."""
    out = []
    if v.form:
        out.append("form")
    if v.platform:
        out.append("one_tap")
    if v.phone and v.calls_on:
        out.append("call")
    if v.email:
        out.append("email")
    return out


def decide(v: Venue, prefer: Optional[str] = None) -> Decision:
    can = available(v)
    alts = lambda r: [x for x in can if x != r]   # noqa: E731
    if prefer in can:
        return Decision(prefer, _REASON_ASKED[prefer], _then(v, prefer), alts(prefer))
    asked_but = ""
    if prefer and prefer not in can:
        asked_but = f"{_CANT[prefer](v)} "
    if v.form:
        return Decision("form", asked_but + "They take bookings on their own website's form — I'll fill it in after your yes.",
                        None, alts("form"))
    if v.platform:
        call_too = " Or I can call them, if you prefer." if "call" in can else ""
        return Decision("one_tap", asked_but + f"They book only through {v.platform}. I'll send you their booking page, filled in where "
                        f"{v.platform} allows — you press confirm (I can't press it for you), and I'll file their confirmation "
                        f"email from your Gmail.{call_too}", None, alts("one_tap"))
    if v.phone and v.calls_on and v.open_now and v.scripted:
        return Decision("call", asked_but + "They have no booking form, and they're open now — I'll call them, after your yes.",
                        None, alts("call"))
    if v.email:
        why = ("they're closed right now" if v.open_now is False else
               f"I can't call in {v.language_label or 'their language'}" if v.phone and not v.scripted else
               "calls are off" if v.phone and not v.calls_on else
               "email is the only way they publish" if not v.phone else
               "I don't know their hours, so I won't ring them blind")
        return Decision("email", asked_but + f"I'll email them — {why}.", _then(v, "email"), alts("email"))
    if v.phone and v.calls_on and v.scripted and v.open_now is False:
        return Decision("call", asked_but + "They're closed now and publish no email — I'll call them when they open"
                        + (f" at {v.opens_at}" if v.opens_at else "") + ", after your yes.", None, alts("call"))
    if v.phone and v.calls_on and v.scripted:   # hours unknown, no email: a call is the only way
        return Decision("call", asked_but + "A call is the only way they publish — I'll call them, after your yes.", None, alts("call"))
    if v.phone and v.calls_on:   # unscripted, no email: English abroad (Sasha 128), said as such
        return Decision("call", asked_but + f"They publish only a phone. I can't speak {v.language_label or 'their language'}, so I'll "
                        "call in English — they may not speak it.", None, alts("call"))
    return Decision(None, asked_but + ("They publish only a phone, and calls are off." if v.phone else
                                       "I found no way to book them that I may use."), None, [])


def _then(v: Venue, route: str) -> Optional[str]:
    if route != "email" or not (v.phone and v.calls_on):
        return None
    at = f" ({v.opens_at})" if v.opens_at and v.open_now is False else ""
    lang = "" if v.scripted else ", in English"
    return f"If they haven't replied by their opening{at}, I'll ask you here whether to call them{lang}."


_REASON_ASKED = {
    "form": "As you asked: their own website's form, filled in after your yes.",
    "one_tap": "As you asked: their booking page — you press confirm, and I'll file their confirmation email from your Gmail.",
    "call": "As you asked: I'll call them, after your yes.",
    "email": "As you asked: I'll email them, after your yes.",
}

_CANT = {
    "form": lambda v: "They have no form I may fill in.",
    "one_tap": lambda v: "They have no booking page I found.",
    "call": lambda v: ("I can't call them: calls are off." if v.phone else "I can't call them: they publish no number."),
    "email": lambda v: "I can't email them: they publish no address.",
}

__all__ = ["Venue", "Decision", "decide", "preference", "available", "ROUTES"]
