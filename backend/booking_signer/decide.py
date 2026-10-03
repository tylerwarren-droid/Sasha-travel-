"""Sasha 130 (2) · Sasha 131 · THE DECISION WORKFLOW — the founder's ESCALATION POLICY, decided in ONE place, with the reason
the guest is shown.

    own form                                → fill it after the guest's yes
    otherwise                               → ONE-TAP on the guest's phone (the default): the venue's booking page; the
                                              guest presses; Sasha files the confirmation email from Gmail
    one-tap not completed within the window → EMAIL the venue (offered on WhatsApp, its own read-back and yes)
    no venue reply to the email in 24 h     → CALL (offered the same way)
    URGENT (the booking is within 24 h)     → CALL + EMAIL at once, on ONE yes
    no page, no form                        → email (then the call after 24 h); a phone only → call
    the guest can always override           → any route that exists ("call them", "email them", "send me the link")

Calls are no longer the default for an open venue (Sasha 131). Every threshold is a setting (below). Pure: no I/O;
nothing here dials, sends or presses — each route keeps its own read-back and yes.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import List, Optional


def _num(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, "") or default)
    except ValueError:
        return default


def tap_window_min() -> float:
    """How long the guest has to press on the platform before the email is offered."""
    return _num("SASHA_TAP_WINDOW_MIN", 30)


def reply_hours() -> float:
    """How long an email waits for the venue's reply before the call is offered."""
    return _num("SASHA_EMAIL_REPLY_HOURS", 24)


def urgent_hours() -> float:
    """A booking this soon is URGENT: call and email at once."""
    return _num("SASHA_URGENT_HOURS", 24)


ROUTES = ("form", "one_tap", "call", "email", "call_email")


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
    hours_until: Optional[float] = None  #: hours from now to the booking; None = not a fixed time


@dataclass(frozen=True)
class Decision:
    route: Optional[str]               #: one of ROUTES, or None when nothing can be done from here
    reason: str                        #: shown to the guest, before any read-back
    then: Optional[str] = None         #: the follow-up, said now ("if they haven't replied by 13:00, I'll offer to call")
    alternatives: List[str] = field(default_factory=list)   #: the routes the guest may choose instead


_PREFER = (("call_email", re.compile(r"\b(call and email|email and call|both)\b", re.I)),
           ("call", re.compile(r"\b(call|phone|ring|llama|llamar|llámales|telefonea)\b", re.I)),
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
    if v.phone and v.calls_on and v.email:
        out.append("call_email")
    if v.phone and v.calls_on:
        out.append("call")
    if v.email:
        out.append("email")
    return out


def urgent(v: Venue) -> bool:
    return v.hours_until is not None and v.hours_until < urgent_hours()


def decide(v: Venue, prefer: Optional[str] = None) -> Decision:
    can = available(v)
    alts = lambda r: [x for x in can if x != r]   # noqa: E731
    if prefer in can:
        return Decision(prefer, _REASON_ASKED[prefer], _then(v, prefer), alts(prefer))
    asked_but = f"{_CANT[prefer](v)} " if prefer in _CANT else ""
    english = "" if v.scripted else f" I can't speak {v.language_label or 'their language'}, so the call is in English."
    if v.form:
        return Decision("form", asked_but + "They take bookings on their own website's form — I'll fill it in after your yes.",
                        None, alts("form"))
    if urgent(v) and "call_email" in can:
        return Decision("call_email", asked_but + f"It's within {_h(urgent_hours())}, so I'll call them and email them at once — "
                        f"one yes covers both.{english}", None, alts("call_email"))
    if urgent(v) and "call" in can:
        return Decision("call", asked_but + f"It's within {_h(urgent_hours())}, so I'll call them, after your yes.{english}",
                        None, alts("call"))
    if v.platform:
        return Decision("one_tap", asked_but + f"They book through {v.platform}. I'll send you their booking page, filled in where "
                        f"{v.platform} allows — you press confirm (I can't press it for you), and I'll file their confirmation "
                        f"email from your Gmail.", _then(v, "one_tap"), alts("one_tap"))
    if v.email:
        why = ("they're closed right now" if v.open_now is False else
               "they have no booking page or form" if v.phone else "email is the only way they publish")
        return Decision("email", asked_but + f"I'll email them — {why}.", _then(v, "email"), alts("email"))
    if v.phone and v.calls_on:
        when = (" when they open" + (f" at {v.opens_at}" if v.opens_at else "")) if v.open_now is False else ""
        return Decision("call", asked_but + f"A phone is the only way they publish — I'll call them{when}, after your yes.{english}",
                        None, alts("call"))
    return Decision(None, asked_but + ("They publish only a phone, and calls are off." if v.phone else
                                       "I found no way to book them that I may use."), None, [])


def _h(hours: float) -> str:
    return f"{int(hours)} hours" if hours != 1 else "an hour"


def _then(v: Venue, route: str) -> Optional[str]:
    """The next step, said now — only promised by the caller when that escalation is switched on."""
    lang = "" if v.scripted else ", in English"
    if route == "one_tap" and (v.email or (v.phone and v.calls_on)):
        nxt = "email them" if v.email else f"call them{lang}"
        return f"If it isn't booked there within {int(tap_window_min())} minutes, I'll ask you here whether to {nxt}."
    if route == "email" and v.phone and v.calls_on:
        return f"If they haven't replied within {_h(reply_hours())}, I'll ask you here whether to call them{lang}."
    return None


_REASON_ASKED = {
    "form": "As you asked: their own website's form, filled in after your yes.",
    "one_tap": "As you asked: their booking page — you press confirm, and I'll file their confirmation email from your Gmail.",
    "call": "As you asked: I'll call them, after your yes.",
    "email": "As you asked: I'll email them, after your yes.",
    "call_email": "As you asked: I'll call them and email them at once — one yes covers both.",
}

_CANT = {
    "form": lambda v: "They have no form I may fill in.",
    "one_tap": lambda v: "They have no booking page I found.",
    "call": lambda v: ("I can't call them: calls are off." if v.phone else "I can't call them: they publish no number."),
    "email": lambda v: "I can't email them: they publish no address.",
    "call_email": lambda v: "I can't do both: they publish " + ("no address." if v.phone else "no number." if v.email else "neither."),
}

__all__ = ["Venue", "Decision", "decide", "preference", "available", "urgent", "ROUTES", "tap_window_min", "reply_hours", "urgent_hours"]
