"""Sasha 130 (2) · Sasha 131 — once THE DECISION WORKFLOW. Sasha 254 · RETIRED as a decider: every venue booking is decided by the
vendored booking rules (agapi/booking_rules: decide(ctx)), through ONE adapter (agapi/booking_decide). What stays here is only the
words parser the old WhatsApp flow (and the old voice avatar through it) uses to hear "call them instead" / "email them" — the
person's preference, which the rules then weigh (they decide; it never routes by itself).

Retired (Sasha 254), each replaced by the rules:
  decide()          → booking_rules.decide (via booking_decide.legacy_decision for the old flow's shape)
  ladder()          → booking_rules' ONE question, R2 (booking_decide.legacy_ladder)
  line()            → booking_rules.PHRASES (booking_decide.say)
  urgent_hours()    → booking_rules.URGENT_HOURS (48) / HOTEL_ARRIVAL_CALL_HOURS (24) — SASHA_URGENT_HOURS is read nowhere
  reply_hours()     → booking_rules.HOTEL_NO_REPLY_HOURS (24, hotels) — SASHA_EMAIL_REPLY_HOURS is read nowhere
  tap_window_min()  → none: the rules have no "page not pressed" escalation (proactive.tap_offers retired)
  available(), urgent(), _then(), Venue, Decision → the rules' ctx and Decision
"""
from __future__ import annotations

import re
from typing import Optional

ROUTES = ("form", "one_tap", "call", "email", "call_email")

_PREFER = (("call_email", re.compile(r"\b(call and email|email and call|both)\b", re.I)),
           ("call", re.compile(r"\b(call|phone|ring|llama|llamar|llámales|telefonea)\b", re.I)),
           ("email", re.compile(r"\b(e-?mail|correo|write to them|escr[ií]beles)\b", re.I)),
           ("one_tap", re.compile(r"\b(link|their page|booking page|i'?ll book it myself|myself|enlace)\b", re.I)),
           ("form", re.compile(r"\b(form|formulario)\b", re.I)))


def preference(text: str) -> Optional[str]:
    """The route the guest asked for in words, or None. "Call them instead" → "call". (A preference — the rules decide.)"""
    for route, rx in _PREFER:
        if rx.search(text or ""):
            return route
    return None


__all__ = ["preference", "ROUTES"]
