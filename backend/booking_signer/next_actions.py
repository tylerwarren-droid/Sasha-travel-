"""Sasha 352 · THE NEXT ACTION — every card's buttons, from ONE place, derived from its item's state.

Found live (Tyler, S2, 6 Nov 10:45): "YOUR TRIP · MAD → LHR · Iberia · €72.57 all in" offered only "See the whole trip" — to book he had to
know to type "book it". And the gate's VOICE LOOP 5: "Book it." went to the model, which tried, failed (no trip) and planned in the
booking turn — the words and the action were not the same path.

  for_trip(state)        a trip's buttons:  offers → Choose · prepared → See the trip · chosen → Book it · held → Yes, book it ·
                         pending_payment → Pay · booked → Change / Cancel  (and See the whole trip, a view, wherever there is a trip)
  for_group(view)        the master list's: anyone planned → Book all · anyone booked → The invoice
  for_group_row(row)     a person's: planned → Book · needs vault → Invite · booked → Cancel
  heard(text)            the words → the action they ARE ("book it", "pay here", "book all", "invite Luis Pérez")

A button IS its words: tapping says `say` (S2, S1, WhatsApp's say: taps), and the conversation routes those words — typed, spoken or
tapped — to the action by code (app/agent/sasha.turn), never to a model that may plan instead. /group's buttons call the same outcome
path (group_outcome.run) the chat's tools call. Nothing here reads a store: pure, so every surface and every test reads the same table.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

#: action id → (its button's label, the words it says, the tool the words reach). The ONE table.
ACTIONS: Dict[str, Dict[str, Any]] = {
    "see": {"label": "See the trip", "say": "Show me the trip", "tool": "propose_trip"},
    "book": {"label": "Book it", "say": "Book it", "tool": "hold_booking"},
    "yes": {"label": "Yes, book it", "say": "Yes, book it", "tool": "book"},
    "pay": {"label": "Pay", "say": "Pay here", "tool": "book"},
    "change": {"label": "Change", "say": "Change my booking", "tool": "change_booking"},
    "cancel": {"label": "Cancel", "say": "Cancel my booking", "tool": "cancel_booking"},
    "book_all": {"label": "Book all", "say": "Book all", "tool": "group_book"},
    "invoice": {"label": "The invoice", "say": "The invoice", "tool": "group_invoice"},
    "invite_all": {"label": "Invite everyone to the vault", "say": "Invite everyone", "tool": "group_invite_vault"},
}
#: a view, not an action: the Trip tab (it says nothing; it opens what is already there)
OPEN_TRIP = {"id": "open_trip", "label": "See the whole trip", "open": "trip"}

TRIP_STATES = ("offers", "prepared", "chosen", "held", "pending_payment", "booked")
_TRIP = {"offers": [], "prepared": ["see"], "chosen": ["book"], "held": ["yes"], "pending_payment": ["pay"], "booked": ["change", "cancel"]}


def action(aid: str, **more: Any) -> Dict[str, Any]:
    a = ACTIONS[aid]
    return {"id": aid, "label": a["label"], "say": a["say"], **more}


def for_trip(state: Optional[str]) -> List[Dict[str, Any]]:
    """A trip card's buttons, in order: its next action(s), then the view of the whole trip (when there is one on the record)."""
    if state not in _TRIP:
        return []
    out = [action(a) for a in _TRIP[state]]
    return out + ([dict(OPEN_TRIP)] if state not in ("offers", "prepared") else [])


def trip_state(*, held: bool = False, pending: bool = False, rows: Optional[List[dict]] = None, prepared: bool = False,
               offers: bool = False) -> Optional[str]:
    """The trip's state as its record has it (the caller reads the record; this only decides). rows: the trip's live basket rows."""
    rows = [r for r in rows or [] if r.get("state") in ("suggested", "chosen", "pending_payment", "booked")]
    if pending or any(r["state"] == "pending_payment" for r in rows):
        return "pending_payment"
    if rows and all(r["state"] == "booked" for r in rows):
        return "booked"
    if held and rows:   # a read-back they heard, waiting for their yes (never over a payment or a booking)
        return "held"
    if any(r["state"] in ("suggested", "chosen") for r in rows):
        return "chosen"
    if prepared:
        return "prepared"
    if offers:
        return "offers"
    return None


# ── the group's master list (groups.view) ─────────────────────────────────────────────────────────────────────────────────

def for_group_row(row: Dict[str, Any]) -> List[Dict[str, Any]]:
    """A person's next action on the master list — from their row's status (groups.status_of: the one classification)."""
    s, name = row.get("status"), row.get("name") or ""
    if s == "planned":
        return [{"id": "book_one", "label": "Book", "say": f"Book {name}", "tool": "group_book", "args": {"who": [name]}}]
    if s == "needs vault":
        return [{"id": "invite", "label": "Invite", "say": f"Invite {name}", "tool": "group_invite_vault", "args": {"who": [name]}}]
    if s == "over limit":
        return [{"id": "book_anyway", "label": "Book anyway", "say": f"Book {name} anyway", "tool": "group_book",
                 "args": {"who": [name], "over_limit_ok": True}}]
    if s == "booked":
        return [{"id": "cancel_one", "label": "Cancel", "say": f"Cancel {name}", "tool": "group_cancel", "args": {"who": [name]}}]
    return []


def for_group(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """The master list's own buttons: Book all while anyone is planned; Invite everyone while anyone waits for their passport; the
    invoice once anyone is booked."""
    out = []
    if any(r.get("status") == "planned" for r in rows):
        out.append(action("book_all"))
    if any(r.get("status") == "needs vault" for r in rows):
        out.append(action("invite_all"))
    if any(r.get("status") in ("booked", "cancelled") for r in rows):
        out.append(action("invoice"))
    return out


# ── the words → the action (typed, spoken or tapped: ONE path) ───────────────────────────────────────────────────────────

_YES = re.compile(r"(?i)^\s*(?:yes|yeah|yep|sure|ok(?:ay)?|go ahead|do it|please do|confirm)\b(?:[,!. ]+(?:please|book it|go ahead|do it))*[.! ]*$")
_BOOK = re.compile(r"(?i)^\s*(?:(?:ok(?:ay)?|right|great|perfect|lovely|then|so)[,!. ]+)*(?:please\s+)?(?:book|reserve)\s+(?:it|this|that|"
                   r"them|the (?:whole )?trip|the flights?|everything)(?:\s+(?:please|now|then|for me))*[.! ]*$")
_PAY = re.compile(r"(?i)^\s*(?:pay(?: it)?(?: now)?(?: here)?|pay on (?:my|this) phone|i(?:'ll| will) pay(?: now)?)[.! ]*$")
_BOOK_ALL = re.compile(r"(?i)^\s*book (?:them )?all(?: planned)?(?: of them)?[.! ]*$")
_INVOICE = re.compile(r"(?i)^\s*(?:the |send me the |show me the )?invoice[.! ?]*$")
_INVITE_ALL = re.compile(r"(?i)^\s*invite (?:them all|everyone|everybody|all of them)(?: to the vault)?[.! ]*$")
_SEE = re.compile(r"(?i)^\s*(?:show me|see) the trip[.! ]*$")


def heard(text: Optional[str]) -> Optional[str]:
    """The action these words ARE — only when they say nothing else ("Book it." · "Yes, book it" · "Pay here" · "Book all"), else None
    (and the conversation runs as before). Change and cancel are app/agent/voice.manage_tool's (Sasha 306), unchanged."""
    t = (text or "").strip()
    if not t or len(t) > 60:
        return None
    if _BOOK_ALL.match(t):
        return "book_all"
    if _BOOK.match(t):   # before the yes: "Ok, book it" asks to book (and, after a read-back, IS the yes — v0.next_uses)
        return "book"
    if _YES.match(t):
        return "yes"
    if _PAY.match(t):
        return "pay"
    if _INVOICE.match(t):
        return "invoice"
    if _INVITE_ALL.match(t):
        return "invite_all"
    if _SEE.match(t):
        return "see"
    return None


__all__ = ["ACTIONS", "OPEN_TRIP", "TRIP_STATES", "action", "for_trip", "trip_state", "for_group", "for_group_row", "heard"]
