"""S-36 · THE CHOOSER — from what Magellan read, which rungs exist, which Sasha can use, and what she says.

  "They have no booking form. I'll call them — or I can email and we wait. Which?"

Every rung is listed with whether it is AVAILABLE and, when not, WHY in plain words — a rung is never silently
missing, and never offered when it cannot run (a button that cannot act is standing rule 4).
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import List, Optional

from . import calls as C
from . import slot_link as SL
from .venue_read import COUNTRIES

#: Forms Sasha can fill today — the one mapped venue (S-17). An unmapped form is a fact, not a rung.
MAPPED_FORM_HOSTS = {"www.restaurante-psi.com", "restaurante-psi.com"}


_BOOKING_MAILBOX = re.compile(r"reserv|booking|bookings|reservas|reservations|prenot|buchung", re.I)


def best_email(facts: list) -> Optional[tuple]:
    """(index, fact) of the address to write to: one whose mailbox says reservations beats a general one; otherwise the
    first published. The read-back names it, so the choice is heard before the yes."""
    emails = [(i, f) for i, f in enumerate(facts) if f["kind"] == "email"]
    return next(((i, f) for i, f in emails if _BOOKING_MAILBOX.search(f["value"].split("@")[0])), emails[0] if emails else None)


def emails_ready() -> Optional[str]:
    """None when the email rung can send, else the reason it cannot — named by the variable that is missing."""
    missing = [v for v in ("SASHA_RESEND_API_KEY", "SASHA_EMAIL_FROM", "SASHA_INBOUND_DOMAIN") if not os.getenv(v, "").strip()]
    if os.getenv("SASHA_EMAILS_ENABLED", "").strip() != "1":
        return "emails are off on this server (SASHA_EMAILS_ENABLED is not 1)"
    if missing:
        return f"email is not set up yet ({', '.join(missing)})"
    return None


def calls_ready(account: Optional[str] = None) -> Optional[str]:
    from .limits import calls_on, CALLS_OFF_FOR_ACCOUNT
    if not calls_on(account):   # Sasha 120 · guests: off until the founder switches calls on for them
        return CALLS_OFF_FOR_ACCOUNT
    if not C.calls_enabled():
        return "phone calls are off on this server (SASHA_CALLS_ENABLED is not 1)"
    if not C.bland_key():
        return "the calling service is not configured (BLAND_API_KEY)"
    return None


@dataclass
class Rung:
    rung: str                     #: form | phone | email | whatsapp | platform
    available: bool
    fact_index: Optional[int]     #: which fact it would use
    value: Optional[str]
    source: Optional[str]
    why_not: Optional[str] = None
    slot_filled: Optional[bool] = None   #: link rung only: True when a verified recipe fills the slot in the URL


_BOOKING_PATH = re.compile(r"reserv|book|cita|prenot|buch|agendar", re.I)


def own_page(read: dict) -> Optional[tuple]:
    """Sasha 246 · RUNG 2 — the venue's OWN booking page: (fact index, https URL, source label), or None. In order: the page
    carrying their booking form; a booking link on their own site (their own engine); a page of theirs whose path says it
    books and that asks the guest to prove they're human (Sasha 242's CAPTCHA site). None when they use a platform: a
    platform they use but don't link stays refused — never their own page in its place (Sasha 195)."""
    facts = read.get("facts") or []
    if any(f.get("kind") == "platform" for f in facts):
        return None
    for i, f in enumerate(facts):
        if f.get("kind") == "booking_form" and f.get("value") and str(f.get("source_url") or "").startswith("https://"):
            return i, f["source_url"], f"{f.get('source_label')} (their own booking page)"
    for i, f in enumerate(facts):
        if f.get("kind") == "booking_page" and str(f.get("value") or "").startswith("https://"):
            return i, f["value"], f"{f.get('source_label')} (their own booking page)"
    for i, f in enumerate(facts):
        u = str(f.get("source_url") or "")
        if f.get("kind") == "challenge" and f.get("source_kind", "site") == "site" and u.startswith("https://") \
                and _BOOKING_PATH.search(u.split("://", 1)[1].partition("/")[2]):
            return i, u, f"{f.get('source_label') or 'their website'} (their own booking page)"
    return None


def choose(read: dict, host_of=lambda u: None, account: Optional[str] = None) -> dict:
    """`read` is VenueRead.to_json(). Returns the rungs in ladder order and the sentence she says."""
    facts = read.get("facts") or []
    # Sasha 64 · a listing fact that could not be re-read has no value: it is not a way to reach them
    first = lambda kind: next(((i, f) for i, f in enumerate(facts) if f["kind"] == kind and f.get("value") is not None), (None, None))
    rungs: List[Rung] = []

    i, form = first("booking_form")
    ip, plat = first("platform")
    if form:
        # Sasha 89 · a form Sasha may SEND: our test venue, or a venue the founder approved and mapped (form_rung)
        from .form_rung import form_map
        mapped = form_map(form.get("source_url") or form["value"]) is not None
        rungs.append(Rung("form", mapped, i, form["value"], form["source_label"],
                          None if mapped else "they have a booking form on their site, but I can't send a form that hasn't been mapped and approved yet"))
    if plat:
        page = SL.platform_page(read)
        if page:
            # S-37 · the guest books on the platform, with their own press — Sasha hands them the venue's page
            rec = SL.RECIPES.get(page[0])
            rungs.append(Rung("link", True, ip, page[0], page[2], None, bool(rec and rec.verified)))
        else:
            rungs.append(Rung("platform", False, ip, plat["value"], plat["source_label"],
                              f"they book through {plat['value']}, but their site doesn't link their page there, and I never guess one"))
    if not (form and rungs[0].available):
        # Sasha 246 · RUNG 2 — their own site books (a form Sasha may not send, or their own engine): she prepares THEIR page
        # with the day, time and number — the guest finishes it there — BEFORE email, phone or a message (EU 241: Hammam Al
        # Ándalus got email/Instagram, La Mi Venta phone/email)
        op = own_page(read)
        if op:
            rungs.append(Rung("own_page", True, op[0], op[1], op[2]))

    i, phone = first("phone")
    if phone:
        # Sasha 130 · a language with no call script is called in English (English abroad, Sasha 128 — said in the
        # read-back), so the language no longer closes the rung; only calls being off does
        why = calls_ready(account)
        rungs.append(Rung("phone", why is None, i, phone["value"], phone["source_label"], why))

    i, email = best_email(facts) or (None, None)
    if email:
        why = emails_ready()
        rungs.append(Rung("email", why is None, i, email["value"], email["source_label"], why))

    i, wa = first("whatsapp")
    if wa:
        # ⚠ sent from the USER's own WhatsApp: Sasha writes it, they press send; the reply comes to them
        rungs.append(Rung("whatsapp", True, i, wa["value"], wa["source_label"], None))

    i, ig = first("instagram")
    if ig:
        # Sasha 212 · a DM on Instagram, from the USER's own account: Sasha writes it, they send it; never "booked"
        rungs.append(Rung("instagram", True, i, ig["value"], ig["source_label"], None))

    return {"rungs": [r.__dict__ for r in rungs], "say": say(rungs, read.get("name") or "They")}


def say(rungs: List[Rung], name: str) -> str:
    by = {r.rung: r for r in rungs}
    if "form" in by and by["form"].available:
        lead = "They have a booking form I can fill."
    elif "form" in by:
        lead = "They have a booking form, but I can't fill it yet."
    elif "link" in by:
        # Sasha 95 · their only booking route is a platform widget: the slot link is the way, and the guest presses
        lead = f"They book only through {by['link'].value}, so you make the final press there — I can't press it for you."
    elif "platform" in by:
        lead = f"They book through {by['platform'].value}, which I can't use yet."
    elif "own_page" in by:   # Sasha 246
        lead = "They take bookings on their own website."
    else:
        lead = "They have no booking form."
    offers = []
    if by.get("link"):
        offers.append(f"I'll send you their {by['link'].value} page with your table filled in — one press, yours"
                      if by["link"].slot_filled else
                      f"I'll send you their {by['link'].value} page and the exact day, time and number to pick")
    if by.get("form") and by["form"].available:
        offers.append("I'll fill in their form")
    if by.get("own_page"):   # Sasha 246 · rung 2, before email, phone and messages
        offers.append("I'll send you their own booking page with your day, time and number — you finish it there")
    if by.get("phone") and by["phone"].available:
        offers.append("I'll call them")
    if by.get("email") and by["email"].available:
        offers.append("I can email and we wait" if offers else "I'll email them and we wait")
    if by.get("whatsapp"):
        offers.append("you can WhatsApp them — I'll write the message" if offers else "I'll write a WhatsApp message for you to send")
    if by.get("instagram"):
        offers.append("you can message them on Instagram — I'll write it" if offers else "I'll write an Instagram message for you to send")
    if not offers:
        reasons = [r.why_not for r in rungs if r.why_not]
        found = ", ".join(sorted({r.rung for r in rungs})) or "nothing I can use"
        return f"{lead} I found {found}, but I can't reach them myself: " + ("; ".join(reasons) if reasons else "they publish no phone, email or WhatsApp") + "."
    if len(offers) == 1:
        return f"{lead} {offers[0][0].upper()}{offers[0][1:]}. Shall I?"
    return f"{lead} {offers[0][0].upper()}{offers[0][1:]} — or " + " — or ".join(offers[1:]) + ". Which?"
