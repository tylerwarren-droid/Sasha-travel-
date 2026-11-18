"""Sasha 386 · THE ONE TEST-IDENTITY SOURCE — every test recipient (a test's fixture, a gate run's scratch person, a TEST account's
roster or invitee) comes from HERE, and nothing else can be one.

Found (Sasha 385's proof, 17 Nov): the TEST organiser's roster held a real person's gmail address, so a test group's itinerary
would have emailed a real colleague. The roster, the gate's numbers (+346…: real Spanish mobiles), the rehearsal forms' fictional
guest (+34600000000), the i18n test list and the test fixtures each made up their own recipients. One edited address would have
been a PATCH; this is the root: ONE source, and a recipient outside it is refused where it would be held and where it would be sent.

  email(slug)        "<slug>@example.invalid": .invalid is reserved by RFC 2606 / RFC 6761, so it can never be delivered to anyone.
  number(n)          a NANP number in 555-0100…0199, reserved for fiction in every area code (valid to libphonenumber, so a supplier
                     takes it; nobody can own it). AREAS: the area codes checked valid.
  uk_drama(n)        Ofcom's drama range, +44 7700 900nnn (fictional; INVALID to libphonenumber: what a supplier refuses).
  au_drama(n)        ACMA's fictional mobiles, +61 491 570 156…159 (valid, fictional).
  sandbox_guest(n)   AgAPI sandbox's own guest range that is also NANP fiction: +1 500 555 01nn.
  form_email(slug)   "<slug>@example.com": reserved, and accepted by web forms (which refuse .invalid).
  fictional_person() THE fictional guest ("Prueba Sasha") every rehearsal / demo form is filled with.
  is_test_email / is_test_number / recipient_ok      the one rule: is this address or number from this source? (Recognised: every
                     reserved domain — RFC 2606/6761 —, and 555-0100…0199 in ANY area code, as NANPA reserves it.)
  KANOE_NUMBERS / is_kanoe_number / is_kanoe   Kanoe's OWN numbers and domains (reach only Kanoe — "Tyler's org and phone").
  stand_in / kanoe_inboxes / ours   a stand-in for "a real address" in a test (Kanoe's domain, outside the reserved names), and the
                     review inboxes (SASHA_I18N_TEST_TO, Kanoe's domains only) an unreviewed language may be sent to.
  is_test_account(account)   async: the person's record (agapi.person_access) is not mode live — every guest, the TEST organiser.
  may_reach(account, to)     the one check before anything about a trip goes to ANOTHER person: a live account may reach anyone;
                             a TEST account only this source's recipients (test data never reaches a real person).

KANOE_DECISIONS: "Tests and proofs: … never a real person contacted" (12 Nov 2026); group bookings run in Duffel TEST (12 Nov).
"""
from __future__ import annotations

import re
from typing import Any, Optional

DOMAIN = "example.invalid"
AREAS = (202, 212, 312, 415, 617, 206, 303, 305, 404, 512, 702, 713, 801, 919, 201, 203, 205, 213, 214, 215, 503, 602)
_NANP = re.compile(r"\+1(\d{3})55501(\d{2})")
_UK = re.compile(r"\+447700900\d{3}")
_AU = re.compile(r"\+6149157015[6-9]")


def _slug(s: Any) -> str:
    out = re.sub(r"[^a-z0-9._-]+", "-", str(s or "").strip().lower()).strip("-.")
    return out or "someone"


def email(slug: Any) -> str:
    """A person's test email: "<slug>@example.invalid" — undeliverable by rule."""
    return f"{_slug(slug)}@{DOMAIN}"


def number(n: int) -> str:
    """The n-th test number: +1 <area> 555 01nn — fictional by rule, valid to libphonenumber (a supplier accepts it)."""
    n = int(n) % (100 * len(AREAS))
    return f"+1{AREAS[n // 100]}55501{n % 100:02d}"


def sandbox_guest(n: int) -> str:
    """A guest number in AgAPI sandbox's own range (+1 500 555 0xxx) that is ALSO NANP fiction: +1 500 555 01nn."""
    return f"+150055501{int(n) % 100:02d}"


def form_email(slug: Any) -> str:
    """A reserved address a WEB FORM accepts (forms refuse .invalid): "<slug>@example.com" — IANA's, never a person's."""
    return f"{_slug(slug)}@example.com"


def fictional_person() -> dict:
    """THE fictional person every rehearsal and demo form is filled with ("Prueba Sasha") — from this source, never invented elsewhere.
    Wholly fictional (CR 23: nothing real through the cloud browser before a DPA): a reserved address and NANP fiction, +1 202 555 0123."""
    return {"first": "Prueba", "last": "Sasha", "name": "Prueba Sasha", "email": form_email("prueba"), "mobile": number(23)}


def uk_drama(n: int = 0) -> str:
    """Ofcom's drama range (+44 7700 900000…999) — fictional, and refused by a supplier (invalid to libphonenumber)."""
    return f"+447700900{int(n) % 1000:03d}"


def au_drama(n: int = 0) -> str:
    """ACMA's fictional mobiles (+61 491 570 156…159) — valid to libphonenumber, nobody's."""
    return f"+6149157015{6 + int(n) % 4}"


def _digits(x: Any) -> str:
    s = re.sub(r"[\s().-]", "", str(x or "").strip())
    if s.lower().startswith("whatsapp:"):
        s = s[9:]
    if s.startswith("00"):
        s = "+" + s[2:]
    if re.fullmatch(r"\d{8,15}", s):   # a wa_id: the number without its +
        s = "+" + s
    return s


#: names no mail can ever be delivered to a person at (RFC 2606 / RFC 6761): reserved top-level names, and IANA's example domains
RESERVED_TLDS = ("invalid", "test", "example", "localhost", "local")   # .local: RFC 6762
RESERVED_DOMAINS = ("example.com", "example.net", "example.org")


def is_test_email(addr: Any) -> bool:
    """A reserved-domain address (.invalid — what email() makes —, .test, .example, .localhost, example.com/.net/.org)."""
    a = str(addr or "").strip().lower()
    m = re.search(r"<([^>]+)>\s*$", a)   # "Name <x@y>"
    a = m.group(1) if m else a
    if a.count("@") != 1 or not a.partition("@")[0]:
        return False
    dom = a.rpartition("@")[2]
    return dom.rpartition(".")[2] in RESERVED_TLDS or any(dom == d or dom.endswith("." + d) for d in RESERVED_DOMAINS)


def is_test_number(x: Any) -> bool:
    """555-0100…0199 in ANY NANP area code (NANPA: fictional), Ofcom's drama range, ACMA's fictional mobiles."""
    s = _digits(x)
    return bool(_NANP.fullmatch(s) or _UK.fullmatch(s) or _AU.fullmatch(s))


def recipient_ok(to: Any) -> bool:
    """Is this recipient (an email, a number, a wa_id, "whatsapp:+…") from the one source? Anything else: no."""
    return is_test_email(to) if "@" in str(to or "") else is_test_number(to)


#: Kanoe's OWN numbers (they reach only Kanoe): the Twilio WhatsApp sandbox sender, Sasha's own number, and Tyler's own mobile —
#: KANOE_DECISIONS 12 Nov 2026, "Tests and proofs: Tyler's org and phone" (docs/sasha/S-70: the authorised representative's number).
KANOE_NUMBERS = {"+14155238886": "the Twilio WhatsApp sandbox (our sender)", "+447915914215": "Sasha's own number",
                 "+34608445715": "Tyler's own mobile"}


def is_kanoe_number(x: Any) -> bool:
    return _digits(x) in KANOE_NUMBERS


KANOE_DOMAIN = "kanoe.ai"   # Kanoe's own mail: reaches only Kanoe (KANOE_DECISIONS 12 Nov: tests and proofs use Tyler's org)
KANOE_DOMAINS = (KANOE_DOMAIN, "applieddiligence.com")   # + Applied Diligence, Kanoe's own product (issue.OUR_ORIGINS)


def is_kanoe(addr: Any) -> bool:
    a = str(addr or "").strip().lower()
    m = re.search(r"<([^>]+)>\s*$", a)
    dom = (m.group(1) if m else a).rpartition("@")[2]
    return "@" in a and any(dom == d or dom.endswith("." + d) for d in KANOE_DOMAINS)


def stand_in(slug: Any) -> str:
    """An address that is NOT a test address (outside the reserved names), yet reaches only Kanoe — for a test that proves a real
    recipient is refused or treated as real: "<slug>@stand-in.kanoe.ai". Never a real person's."""
    return f"{_slug(slug)}@stand-in.{KANOE_DOMAIN}"


def kanoe_inboxes() -> set:
    """Kanoe's own review inboxes (SASHA_I18N_TEST_TO, comma-separated): only addresses on Kanoe's own domain count — the env can't
    make an outside address a test one."""
    import os
    return {a.strip().lower() for a in os.getenv("SASHA_I18N_TEST_TO", "").split(",") if a.strip() and is_kanoe(a.strip())}


def ours(to: Any) -> bool:
    """A recipient that is ours to test on: the one source's (reserved names), or one of Kanoe's own review inboxes."""
    return is_test_email(to) or str(to or "").strip().lower() in kanoe_inboxes()


async def is_test_account(account: Optional[str]) -> bool:
    """A TEST person: their person_access record isn't mode live (every guest reads CLOSED = test). Read once per session there."""
    from agapi import person_access as PA
    return (await PA.get(account)).get("mode") != "live"


async def may_reach(account: Optional[str], to: Any) -> bool:
    """THE one check before a trip's message goes to another person: live → anyone; TEST → only this source's recipients."""
    return recipient_ok(to) or not await is_test_account(account)


REFUSED = "a test trip only reaches test addresses ({}): never a real person"


def refused_why() -> str:
    return REFUSED.format("…@" + DOMAIN)
