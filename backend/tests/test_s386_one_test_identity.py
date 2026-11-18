"""Sasha 386 · B) TEST DATA NEVER REACHES A REAL PERSON — every test recipient comes from ONE source, booking_signer.test_identity.

Found (Sasha 385's proof, 17 Nov): the TEST organiser's roster held a real person's gmail address — a test trip's itinerary would have
emailed a real colleague. Not one fixture to edit (that is a PATCH): every place a test recipient was made — the roster, the gate's
numbers, the rehearsal forms' fictional guest, the i18n test list, ~90 test fixtures — now comes from the one source, and a recipient
outside it is refused where it would be HELD (the roster) and where it would be SENT (the one sender to another person).

Scope (Tyler, 18 Nov — "Persons only"): every PERSON identity (guest, traveller, roster member, organiser, WhatsApp sender, an email
recipient) is the source's or Kanoe's own (KANOE_DECISIONS 12 Nov: "Tyler's org and phone"); personal mailboxes are refused outright.
A venue's or business's own number is not a person (no fictional range exists in Spain, Kenya, Portugal…): a venue is reached only
through AgAPI under real_venue_sends.

    cd backend && python -m unittest tests.test_s386_one_test_identity -v
"""
from __future__ import annotations

import ast
import asyncio
import inspect
import json
import pathlib
import re
import unittest
from unittest import mock

import phonenumbers

from agapi import person_access as PA
from booking_signer import group_report as GR, groups as G, live_events as LE, test_identity as TI, traveller_vault as TV
from booking_signer.i18n import emails as I18N

run = asyncio.run
BACKEND = pathlib.Path(__file__).resolve().parents[1]
OWNER = "00000000-0000-4000-8000-000000000386"
LIVE = "00000000-0000-4000-8000-000000000387"
TEST_PERSON = {"mode": "test", "source": "installed"}   # the TEST organiser's record (every guest reads the same)


# ── the scan: every person identity a test or a gate script builds ─────────────────────────────────────────────────────────────────

EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
PERSONAL = re.compile(r"(?i)[A-Za-z0-9._%+-]+@(?:gmail|googlemail|hotmail|outlook|live|msn|yahoo|ymail|icloud|me|mac|proton|protonmail|aol"
                      r"|gmx|yandex)\.(?:com|es|co\.uk|me|net|fr|de|it)\b")
#: keys whose value is a person's address or number
EMAIL_KEYS = re.compile(r"(?i)^(to|cc|bcc|email|emails|reply_to|recipient|recipients)$|_email$|^email_")
NUMBER_KEYS = re.compile(r"(?i)^(mobile|mobile_e164|wa_id|waid|number_e164|guest_phone|guest_mobile|phone_e164)$")
WEBHOOK_KEYS = re.compile(r"(?i)^(from|to)$")   # Twilio's From / To — a person's when it is a whatsapp: address
#: a module-level name that holds a person
PERSON_NAME = re.compile(r"(?i)(guest|mobile|traveller|organi[sz]er|founder|person|member|email|user)")
#: a dict that is a person (any of these keys) unless it is a venue's (any of VENUE)
PERSON = {"email", "mobile", "mobile_e164", "home_city", "home_airport", "grade", "role", "guest", "traveller", "first_name", "last_name",
          "date_of_birth", "booking_email", "born_on", "given_name", "family_name"}
VENUE = {"form", "platform", "booking_form", "facts", "fact_index", "venue", "place_id", "website", "address", "source_kind", "source_label",
         "listing", "rating", "url", "kind", "value", "route", "card", "brand", "exp", "cvc", "iban"}
#: a person's contact as they type it: "Tyler Warren, +34 600 …"
CONTACT = re.compile(r"^\s*[A-Z][a-zà-ÿ]+(?: [A-Z][a-zà-ÿ]+)+,? (\+\d[\d ]{7,17}\d)\s*$")   # the whole message


def email_ok(e: str) -> bool:
    dom = e.lower().rpartition("@")[2]
    return TI.is_test_email(e) or TI.is_kanoe(e) or dom.endswith(".kanoe")   # .kanoe: internal ids (act_…@sasha.kanoe), no such TLD


def number_ok(s: str) -> bool:
    """A string that is a number at all → from the source or Kanoe's own. Anything that isn't a number (a uuid, a date) passes."""
    if not re.fullmatch(r"(whatsapp:)?\+?[\d ]+", s.strip()):
        return True
    d = re.sub(r"[^\d+]", "", s.replace("whatsapp:", ""))
    digits = d.lstrip("+")
    if not (8 <= len(digits) <= 15) or re.fullmatch(r"(19|20)\d{6}", digits):
        return True
    if not d.startswith("+") and not re.fullmatch(r"(1|2\d{2}|3\d|4\d|6\d|8\d|9\d)\d{8,12}", digits):
        return True   # a national form: no country, so no one in particular
    return TI.is_test_number("+" + digits) or TI.is_kanoe_number("+" + digits)


def _strings(v):
    return [x.value for x in ast.walk(v) if isinstance(x, ast.Constant) and isinstance(x.value, str)]


def person_findings(path: pathlib.Path):
    """(line, where, value) for every person address or number outside the source in one Python file."""
    text = path.read_text(errors="ignore")
    out = [(text[:m.start()].count("\n") + 1, "a personal mailbox", m.group(0)) for m in PERSONAL.finditer(text)
           if not TI.is_test_email(m.group(0))]
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return out
    for n in ast.walk(tree):
        if isinstance(n, ast.Constant) and isinstance(n.value, str):
            out += [(n.lineno, "a typed contact", m.group(0).strip()) for m in CONTACT.finditer(n.value) if not number_ok(m.group(1))]
        pairs, venue = [], False
        if isinstance(n, ast.Dict):
            ks = {k.value for k in n.keys if isinstance(k, ast.Constant) and isinstance(k.value, str)}
            venue = bool(VENUE & ks) or not (PERSON & ks)
            pairs = [(k.value, v) for k, v in zip(n.keys, n.values) if isinstance(k, ast.Constant) and isinstance(k.value, str)]
        elif isinstance(n, ast.Call):
            pairs = [(kw.arg, kw.value) for kw in n.keywords if kw.arg]
        elif isinstance(n, ast.Assign):
            pairs = [("NAME:" + t.id, n.value) for t in n.targets if isinstance(t, ast.Name) and PERSON_NAME.search(t.id)]
        for k, v in pairs:
            k = str(k)
            named = k.startswith("NAME:")
            for s in _strings(v):
                if named or (EMAIL_KEYS.search(k) and not (venue and k in ("to", "email"))):
                    out += [(n.lineno, k, e) for e in EMAIL.findall(s) if not email_ok(e)]
                if "@" not in s and (named or NUMBER_KEYS.match(k) or (k == "phone" and not venue)
                                     or (WEBHOOK_KEYS.match(k) and s.startswith("whatsapp:"))) and not number_ok(s):
                    out.append((n.lineno, k, s))
    return out


def json_findings(path: pathlib.Path):
    """The same for a JSON fixture: an address under a recipient key, a number under a person's number key."""
    def walk(o, key=None, at=""):
        if isinstance(o, dict):
            for k, v in o.items():
                yield from walk(v, k, f"{at}/{k}")
        elif isinstance(o, list):
            for i, v in enumerate(o):
                yield from walk(v, key, f"{at}/{i}")
        elif isinstance(o, str):
            yield str(key or ""), o, at
    try:
        data = json.loads(path.read_text())
    except (ValueError, UnicodeDecodeError):
        return []
    out = []
    for k, v, at in walk(data):
        recipient = "/to/" in at + "/" or EMAIL_KEYS.search(k) or k == "address" and "/to" in at
        if recipient:
            out += [(at, e) for e in EMAIL.findall(v) if not email_ok(e)]
        if (NUMBER_KEYS.match(k) or (k == "number" and "/to" in at)) and not number_ok(v):
            out.append((at, v))
        out += [(at, m.group(0)) for m in PERSONAL.finditer(v) if not TI.is_test_email(m.group(0))]
    return out


#: AgAPI's own spec vectors (vendored, ~/Developer/agapi spec/ext/vectors/powers.json): their recipient is AgAPI's to fix — reported
#: to AgAPI (mailbox, Sasha 386). This file's check is an EXPECTED failure until AgAPI ships the fix; then it passes and says so.
AGAPI_VECTORS = "tests/fixtures/agapi_powers_vectors.json"
#: bytes signed by the booking helper's own JavaScript (cross-implementation vectors: changing a byte breaks them) — held to a stricter
#: rule instead: their person's number is one NO-ONE can hold (not a valid number anywhere) and every address is reserved or Kanoe's.
SIGNED = ("tests/booking_signer_vectors.json", "tests/booking_signer_issue_cases.json")


def _files(*suffixes):
    for base in ("tests", "scripts"):
        for p in sorted((BACKEND / base).rglob("*")):
            if p.suffix in suffixes and "__pycache__" not in p.parts:
                yield p


class NoTestBuildsARealPerson(unittest.TestCase):
    """THE CLASS TEST: fails if any test or gate script holds a person's address or number outside the source."""

    def test_every_python_test_and_gate_script(self):
        bad = [f"{p.relative_to(BACKEND)}:{ln} {k} {v}" for p in _files(".py") for ln, k, v in person_findings(p)]
        self.assertEqual(bad, [], "a person outside booking_signer.test_identity:\n" + "\n".join(bad))

    def test_every_json_fixture(self):
        bad = [f"{p.relative_to(BACKEND)} {at} {v}" for p in _files(".json")
               if str(p.relative_to(BACKEND)) not in SIGNED + (AGAPI_VECTORS,) for at, v in json_findings(p)]
        self.assertEqual(bad, [], "\n".join(bad))

    @unittest.expectedFailure
    def test_agapis_vendored_vectors(self):
        """jurgen@example.de (a registered domain) and +34 600 000 001 — AgAPI's spec, reported to AgAPI (Sasha 386)."""
        self.assertEqual(json_findings(BACKEND / AGAPI_VECTORS), [])

    def test_the_signed_vectors_hold_no_one(self):
        for f in SIGNED:
            text = (BACKEND / f).read_text()
            for e in EMAIL.findall(text):
                self.assertTrue(email_ok(e), (f, e))
            for m in re.finditer(r"\+\d[\d ]{7,17}\d", text):
                n = phonenumbers.parse(m.group(0))
                self.assertFalse(phonenumbers.is_valid_number(n) and not TI.recipient_ok(m.group(0)), (f, m.group(0)))

    def test_the_scan_sees_what_it_must(self):
        """The scanner itself: a real gmail, a real Spanish mobile on a guest, a typed contact and a WhatsApp From are each caught."""
        real = REAL_MOBILE.replace(" ", "")
        src = (f'GUEST = "{real}"\n'
               f'r = {{"name": "A", "email": "{REAL_MAILBOX}", "home_city": "Madrid"}}\n'
               f'f = {{"From": "whatsapp:{real}", "Body": "hi"}}\n'
               f's = "Ana Ruiz, {REAL_MOBILE}"\n'
               'v = {"venue": "Casa", "phone": "+34910000000"}\n'           # a venue's: not a person
               f'ok = {{"email": "{TI.email("ana")}", "mobile": "{TI.number(1)}", "home_city": "Madrid"}}\n')
        p = pathlib.Path(self.id().replace(".", "_") + ".py")
        tmp = BACKEND / "tests" / "__pycache__" / p.name
        tmp.parent.mkdir(exist_ok=True)
        tmp.write_text(src)
        try:
            got = {(k, v) for _, k, v in person_findings(tmp)}
        finally:
            tmp.unlink()
        self.assertIn(("NAME:GUEST", real), got)
        self.assertIn(("a personal mailbox", REAL_MAILBOX), got)
        self.assertIn(("email", REAL_MAILBOX), got)
        self.assertIn(("From", "whatsapp:" + real), got)
        self.assertIn(("a typed contact", "Ana Ruiz, " + REAL_MOBILE), got)
        self.assertFalse(any("+34910000000" in v for _, v in got))
        self.assertEqual(len(got), 5, got)   # the five above (the gmail is caught twice: mailbox + key) — and nothing from `ok`


REAL_MAILBOX = "@".join(("someone", "gmail.com"))   # a real-looking personal mailbox, assembled so no literal holds one
REAL_MOBILE = "+34 611" + " 222 333"                 # a real-shaped Spanish mobile, likewise


# ── the source itself ──────────────────────────────────────────────────────────────────────────────────────────────────────────

class TheSource(unittest.TestCase):
    def test_numbers_are_fiction_by_rule_and_a_supplier_takes_them(self):
        nums = [TI.number(n) for n in range(0, 100 * len(TI.AREAS), 7)]
        for n in nums:
            self.assertTrue(TI.is_test_number(n), n)
            self.assertTrue(phonenumbers.is_valid_number(phonenumbers.parse(n)), n)     # Duffel's own check (contacts.supplier_mobile)
        self.assertEqual(len(set(TI.number(n) for n in range(100 * len(TI.AREAS)))), 100 * len(TI.AREAS))
        self.assertTrue(TI.is_test_number(TI.sandbox_guest(93)) and TI.sandbox_guest(93).startswith("+1500555"))
        self.assertTrue(TI.is_test_number(TI.uk_drama(123)) and TI.is_test_number(TI.au_drama(2)))
        self.assertTrue(TI.is_test_number("whatsapp:+12025550123") and TI.is_test_number("12025550123"))   # a wa_id
        for real in ("+34600111222", "+447911123456", "+12025550200", "+12025551234", "+254725909800"):
            self.assertFalse(TI.is_test_number(real), real)

    def test_emails_are_reserved_names(self):
        self.assertEqual(TI.email("Ana García"), "ana-garc-a@example.invalid")
        for ok in (TI.email("x"), "a@b.test", "a@sasha.test", "Name <a@x.example>", "a@example.com", TI.form_email("p")):
            self.assertTrue(TI.is_test_email(ok), ok)
        for real in (REAL_MAILBOX, "a@example.de", "a@example-domain.com", "a@test.com", "a@invalid.es", "nope"):
            self.assertFalse(TI.is_test_email(real), real)
        self.assertFalse(TI.recipient_ok(TI.stand_in("venue")))            # Kanoe's, but NOT a test address
        self.assertTrue(TI.is_kanoe(TI.stand_in("venue")))

    def test_resends_delivered_sink_is_a_test_address_and_nothing_else_there_is(self):
        """Tyler, 18 Nov: a proof shows emails ARRIVING at Resend's sink — delivered(+tag)@resend.dev, which reaches no person."""
        self.assertEqual(TI.sink("Ana García"), "delivered+ana-garc-a@resend.dev")
        for ok in (TI.sink("x"), "delivered@resend.dev", "Ana <delivered+ana@resend.dev>"):
            self.assertTrue(TI.recipient_ok(ok), ok)
        for no in ("bounced@resend.dev", "complained+x@resend.dev", "someone@resend.dev", "delivered@resend.dev.evil.com"):
            self.assertFalse(TI.recipient_ok(no), no)

    def test_the_fictional_person_is_wholly_fictional(self):
        f = TI.fictional_person()
        self.assertTrue(TI.recipient_ok(f["email"]) and TI.recipient_ok(f["mobile"]))
        self.assertFalse(TI.is_kanoe_number(f["mobile"]))                  # never Tyler's (CR 23: nothing real before a DPA)


# ── where a test recipient would be HELD: the roster ───────────────────────────────────────────────────────────────────────────

class TheRosterCantHoldARealPerson(unittest.TestCase):
    def setUp(self):
        self.store = G.MemStore()
        self.p = mock.patch.object(G, "STORE", self.store)
        self.p.start()
        PA.install({LIVE: PA.LIVE_PERSON, OWNER: TEST_PERSON})   # each account's record, whatever another test left

    def tearDown(self):
        self.p.stop()
        PA.uninstall(LIVE, OWNER)

    def add(self, account, **f):
        return run(G.add_people(account, [{"name": "Jain Example", "home_city": "Madrid", **f}], "Acme Components (fictional)"))

    def people(self, account):
        return run(G.roster(account))["people"]

    def test_a_test_account_refuses_a_real_address_and_number_and_says_so(self):
        for f in ({"email": REAL_MAILBOX}, {"email": TI.stand_in("jain")}, {"phone": REAL_MOBILE}):
            got = self.add(OWNER, **f)
            self.assertEqual(got["added"], 0, f)
            self.assertIn("TEST account", " ".join(got["unclear"][0]["why"]), f)
        self.assertEqual(self.people(OWNER), [])                           # never stored, not even half

    def test_a_test_account_keeps_test_people(self):
        got = self.add(OWNER, email=TI.email("jain"), phone=TI.number(5))
        self.assertEqual(got["added"], 1, got)
        self.assertEqual(self.people(OWNER)[0]["email"], TI.email("jain"))

    def test_a_live_account_keeps_its_real_people(self):
        self.assertEqual(self.add(LIVE, email=TI.stand_in("jain"))["added"], 1)

    def test_every_roster_write_goes_through_the_one_guard(self):
        """The list (upload), the People page / chat (add_people) and an edit (edit_person): each calls _held first."""
        run(G.add_people(OWNER, [{"name": "Jain Example", "home_city": "Madrid"}], "Acme Components (fictional)"))
        pid = self.people(OWNER)[0]["id"]
        got = run(G.edit_person(OWNER, pid, {"email": REAL_MAILBOX}))
        self.assertIn("TEST account", got.get("why", ""))
        self.assertIsNone(self.people(OWNER)[0].get("email"))
        self.assertIn("_held(r, test)", inspect.getsource(G._on_roster))
        self.assertIn("_held(f,", inspect.getsource(G.edit_person))
        for caller in (G.upload, G.add_people):
            self.assertIn("TI.is_test_account(account)", inspect.getsource(caller))
        writers = [n for n, f in inspect.getmembers(G, inspect.isfunction) if f.__module__ == G.__name__
                   and re.search(r"\.(add_person|update_person)\(", inspect.getsource(f))]
        self.assertEqual(sorted(writers), ["_on_roster", "edit_person"])     # no third way onto the roster


# ── where a test recipient would be SENT: the one sender to another person ─────────────────────────────────────────────────────

class TheOneSender(unittest.TestCase):
    def setUp(self):
        PA.install({LIVE: PA.LIVE_PERSON, OWNER: TEST_PERSON})   # each account's record, whatever another test left
        self.sent = []

        async def send(msg):
            self.sent.append(msg["to"])
            return {"sent": True}
        self.p = mock.patch.object(LE, "SEND", send)
        self.p.start()

    def tearDown(self):
        self.p.stop()
        PA.uninstall(LIVE, OWNER)

    def test_a_test_account_reaches_only_the_source(self):
        got = run(LE.send_to_person(OWNER, {"to": TI.stand_in("jain"), "subject": "x", "text": "x"}))
        self.assertEqual((got["sent"], got["why"]), (False, "test_recipient"))
        self.assertTrue(run(LE.send_to_person(OWNER, {"to": TI.email("jain"), "subject": "x", "text": "x"}))["sent"])
        self.assertTrue(run(LE.send_to_person(LIVE, {"to": TI.stand_in("jain"), "subject": "x", "text": "x"}))["sent"])
        self.assertEqual(self.sent, [TI.email("jain"), TI.stand_in("jain")])

    def test_old_data_holding_a_real_address_is_never_emailed(self):
        """A roster written before 386 (Jain's real gmail on the TEST organiser's roster): the itinerary is not sent, and said so."""
        store = G.MemStore()
        with mock.patch.object(G, "STORE", store):
            grp = run(store.company(OWNER, "Acme Components (fictional)", create=True))
            run(store.add_person(grp["id"], {"name": "Jain Example", "home_city": "Madrid", "email": TI.stand_in("jain")}))
            with mock.patch.object(GR, "sent_record", mock.AsyncMock(return_value={})):
                out = run(GR.send_itineraries(OWNER, {"id": "mv1", "destination": "Yerevan", "company": "Acme"},
                                              [{"name": "Jain Example", "member_id": "m1", "status": "booked", "references": ["X1"]}]))
        self.assertEqual(out["not_sent"], ["Jain Example"])
        self.assertEqual(self.sent, [])

    def test_every_send_to_another_person_is_the_one_sender(self):
        self.assertIn("LE.send_to_person(account, msg)", inspect.getsource(GR.send_itineraries))
        self.assertIn("LE.send_to_person(owner, msg)", inspect.getsource(TV))
        self.assertNotIn("SEND", [n for n in vars(TV) if n == "SEND"])              # the vault's own second sender is gone
        self.assertIn("TI.may_reach(account", inspect.getsource(LE.send_to_person))


# ── the 0b inventory: every place a test recipient was built before, each now from the one source ─────────────────────────────

class The0bInventory(unittest.TestCase):
    def src(self, rel):
        return (BACKEND / rel).read_text()

    def test_each_place(self):
        from scripts import gate_identity as GI
        inventory = {
            # (1) the gate's WhatsApp numbers (were +346…: real Spanish mobiles)
            "scripts/gate_identity.py": "TI.number(",
            # (2) the gate suites' scratch traveller mobile (was f"+346120000{n}")
            "scripts/flight_suite.py": "booking_signer.test_identity",
            "scripts/basket_suite.py": "booking_signer.test_identity",
            # (3) the voice proof's sandbox guest (was +1 500 555 0200…0999: outside the fiction range)
            "scripts/voice_proof.py": "TI.sandbox_guest(",
            # (4) the rehearsal forms' fictional guest typed into venue / hotel / university forms (was +34600000000 / 600000000)
            "booking_signer/handover.py": "_TI.fictional_person()",
            "booking_signer/handover_guestcentric.py": "_TI.fictional_person()",
            "products/campus/live.py": "_TI.fictional_person()",
            # (5) the i18n "our test addresses" list (SASHA_I18N_TEST_TO: any address the env named)
            "booking_signer/i18n/emails/__init__.py": "TI.ours(to)",
            # (6) the non-delivering names an email check trusts
            "booking_signer/issue.py": "from .test_identity import RESERVED_TLDS",
            # (7) the demo user's address
            "app/services/chat_store.py": "booking_signer.test_identity",
            # (8) the roster (the TEST organiser's people) and (9) the sends to them
            "booking_signer/groups.py": "TI.recipient_ok(",
            "booking_signer/live_events.py": "TI.may_reach(",
        }
        for rel, mark in inventory.items():
            self.assertIn(mark, self.src(rel), rel)
        for n in range(1, 16):
            self.assertTrue(TI.is_test_number(GI.mobile_for("dep_386", n)))
        self.assertTrue(I18N.is_test_address("book@venue.sasha.test"))
        with mock.patch.dict("os.environ", {"SASHA_I18N_TEST_TO": "qa@kanoe.ai, " + REAL_MAILBOX}):
            self.assertTrue(I18N.is_test_address("qa@kanoe.ai"))
            self.assertFalse(I18N.is_test_address(REAL_MAILBOX))   # the env can't make an outside address a test one

    def test_no_second_source_in_production(self):
        """What COUNTS as a test recipient — the reserved names, the i18n list — is defined ONLY in booking_signer/test_identity.py; and
        every fictional person a form is filled with (a FICTIONAL… table) is the source's. (A filled document that is never sent —
        relocation's demo applicant on the EX-15 / health card — is not a recipient.)"""
        marks = re.compile(r"example\.invalid|SASHA_I18N_TEST_TO|_NON_DELIVERING_\w+ = \(")
        hits = []
        for p in sorted(BACKEND.rglob("*.py")):
            rel = p.relative_to(BACKEND).as_posix()
            if rel.startswith(("tests/", "scripts/", "venv/", ".venv/")) or rel == "booking_signer/test_identity.py":
                continue
            text = p.read_text(errors="ignore")
            hits += [f"{rel}:{i}: {line.strip()[:120]}" for i, line in enumerate(text.splitlines(), 1) if marks.search(line)]
            for n in ast.walk(ast.parse(text)):   # a FICTIONAL… person with a literal email / phone of its own
                if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id.startswith("FICTIONAL") for t in n.targets) \
                        and isinstance(n.value, ast.Dict):
                    for k, v in zip(n.value.keys, n.value.values):
                        if isinstance(k, ast.Constant) and re.search(r"email|phone|mobile", str(k.value)) and isinstance(v, ast.Constant):
                            hits.append(f"{rel}:{n.lineno}: FICTIONAL {k.value} = {v.value!r} (not from the source)")
        self.assertEqual(hits, [], "\n".join(hits))


if __name__ == "__main__":
    unittest.main()
