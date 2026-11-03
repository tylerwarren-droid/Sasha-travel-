"""Sasha 328 · THE PLATFORM BOOKING LOOP (CR 160), then cancel (Tyler, 3 Nov: "finish the platform booking loop — do all of that, then cancel").

ROOT TEST (written first: docs/sasha/S-328-platform-loop.md)
  ONE trip record — AgAPI's act (kept in s2_memory venue_acts, pointers beside it) is the ONE booking record: My bookings reads it, the
  Gmail reader attaches the platform's cancel link TO it, cancel reads it. ONE AgAPI booking path — venue.prepare_booking (VS.prepare with
  booking_person, the ONE person) → venue.submit_booking's read-back → the person's yes → VS.submit. The walk's question is asked once and
  answered on that same path — Sasha 329 · CR 161: AgAPI's ask {choice, label, options}, answered as venue.submit_booking `choices` on the
  SAME prepared_id (328's prepare_booking `answers` and its sentence reader are gone: tests/test_s329.py). The whole class, held below: no
  venue person built anywhere but booking_person; the cancel link kept only on the act.
Offline: AgAPI, Gmail, the stores and the model are stood in; nothing leaves the process.

    cd backend && python3 -m unittest tests.test_s328 -v
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import inspect
import json
import pathlib
import re
import unittest
from datetime import datetime, timezone
from unittest import mock

from agapi import v0 as V0, venue_submit as VS, venues as VN
from booking_signer import contacts as CT, mailbox as MB

run = asyncio.run
ACCT = "00000000-0000-4000-8000-000000000328"
CM_PAGE = "https://www.covermanager.com/reserve/module_restaurant/la-taberna/spanish"
CANCEL = "https://www.covermanager.com/reservation/cancel/la-taberna/CM48213?token=8f3e2a91"
ASK = {"choice": "zona", "label": "Zona", "options": ["Terraza", "Salón", "Barra"]}   # Sasha 329 · CR 161's structured ask
ZONA = "Their page asks which Zona you'd like. Here's their page with your details ready: " + CM_PAGE
RD = {"venue": "La Taberna", "rungs": {}, "place_id": "ChIJ328", "read_id": "r328", "country": "ES"}
RES = {"who": {"name": "Tyler Warren", "contact": {"mobile_e164": "+34608445715"}}, "how_many": {"count": 2},
       "when": {"at": "2026-11-13T21:00"}, "what": {"category": "restaurant"}}
CARD = {"name": "La Taberna", "website": "https://lataberna.example", "place_id": "ChIJ328", "phone": "+34910000328"}
DEC = {"route": "platform", "channel": "CoverManager booking", "how_far": "hand_over",
       "say_text": "La Taberna books on CoverManager.", "button": {"label": "Book on CoverManager", "link": CM_PAGE, "sends": False}}
LINES = ["Sasha fills in your booking on CoverManager for La Taberna and presses Book: date: 2026-11-13; time: 21:00; party: 2.",
         "If their page asks for a card, a deposit or a sign-in, or shows a security check, it stops and hands the booking back to you."]
# CoverManager's confirmation, as it lands in Spanish (text part; the HTML part carries the same links)
CM_MAIL = ("Reserva confirmada - La Taberna", "CoverManager <noreply@covermanager.com>",
           "Hola Tyler,\n\nTu reserva en La Taberna está confirmada.\n\nFecha: viernes, 13 de noviembre de 2026\nHora: 21:00\n"
           "Personas: 2\nZona: Terraza\nLocalizador: CM48213\n\n¿No puedes venir? Puedes cancelar tu reserva aquí:\n" + CANCEL +
           "\n\nConsulta nuestra política de privacidad: https://www.covermanager.com/privacy\n"
           "Descarga la app: https://evil.example/reservation/cancel/la-taberna\n")


class Ctx:
    def __init__(self, said="", surface="s2", via="page"):
        self.account, self.surface, self.user_said, self.via, self.session = ACCT, surface, said, via, "sess-328"
        self.started = datetime.now(timezone.utc)
        self.idem = self.act_name = self.claimed = None


class Memory:
    def __init__(self):
        self.kinds = {}

    async def kind(self, _a, name):
        return self.kinds.get(name)

    async def put_kind(self, _a, name, value):
        self.kinds[name] = json.loads(json.dumps(value, default=str))
        return True


class AgAPI:
    """venue.* as AgAPI 1.x answers them for a person in the platform beta (CR 160): prepare → platform_book; submit without approval →
    the read-back; the in-app tap → the walk's outcome, scripted (first: the Zona stop; then: Booked with CoverManager's reference)."""

    def __init__(self, outcomes):
        self.calls, self.outcomes, self.n, self.extra_line, self.choices = [], list(outcomes), 0, [], {}

    async def call(self, op, body, approval=None, account=None):
        self.calls.append((op, json.loads(json.dumps(body))))
        if op == "users.register":
            return {"ok": True, "result": {"end_user_id": "eu_328"}}
        if op == "venue.prepare_booking":
            self.n += 1
            return {"ok": True, "result": {"prepared_id": f"vpr_{self.n:032d}", "link": f"https://agapi.example/prepared/t{self.n}",
                                           "submitted": False, "say": "Ready for you to confirm.",
                                           "decision": {"route": "platform_book", "how_far": "zero_touch",
                                                        "say_text": "They book on CoverManager — I'll fill in their booking and press Book for you.",
                                                        "button": {"label": "Yes, book it", "link": None, "sends": True}},
                                           "hand_over": {"link": CM_PAGE, "platform": "CoverManager", "carried": [], "copy": []}}}
        if op == "venue.submit_booking" and not approval:   # CR 161 · choices kept on the prepared booking and read back
            self.choices.update(body.get("choices") or {})
            picked = "; ".join(f"{k}: {v}" for k, v in self.choices.items())
            lines = [LINES[0][:-1] + (f"; {picked}." if picked else "."), *LINES[1:]] + (self.extra_line if self.choices else [])
            return {"ok": False, "error": {"code": "approval_required", "details": {
                "read_back_id": f"rb_{body['prepared_id'][-4:]}", "read_back": {"lines": lines},
                "read_back_sha256": hashlib.sha256("\n".join(lines).encode()).hexdigest()}}}
        if op == "approvals.in_app_tap":
            return {"ok": True, "result": {"approval_id": "apv", "result": self.outcomes.pop(0)}}
        if op in ("venue.bookings", "venue.booking_status", "venue.manage_options"):
            return {"ok": False, "error": {"code": "unknown_operation"}}
        if op == "venue.cancel_booking":   # Sasha 329 · CR 161 · a person outside the platform-cancel beta: their link, nothing pressed
            return {"ok": True, "result": {"act_id": body["act_id"], "status": "not_allowed", "why": ["not in the beta"],
                                           "say": "I can't cancel it on their page for you."}}
        return {"ok": False, "error": {"code": "unexpected", "message": op}}

    def ops(self):
        return [op for op, _ in self.calls]

    def bodies(self, op):
        return [b for o, b in self.calls if o == op]


STOPPED = {"status": "failed", "act_id": "act_zona", "how": "platform_form", "rung": "zero_touch", "venue": "La Taberna", "say": ZONA,
           "venue_words": {"untrusted_text": ZONA[:ZONA.index(" Here's")]}, "hand_over": {"link": CM_PAGE, "copy": [], "why": "choice"},
           "ask": ASK}
BOOKED = {"status": "confirmed", "act_id": "act_booked", "how": "platform_form", "rung": "zero_touch", "venue": "La Taberna",
          "reference": "CM48213", "say": "Booked: La Taberna, 2026-11-13 21:00, 2 people, ref CM48213."}


class Base(unittest.TestCase):
    OUTCOMES = (STOPPED, BOOKED)

    def setUp(self):
        from agapi import s2_memory as M, s2_outcomes as OC
        from booking_signer import guest_receipt as GR, live_events as LE, wa_brain as WB
        VN._HELD.pop(ACCT, None)
        VN._PREV.pop(ACCT, None)
        VN._CANCEL.pop(ACCT, None)
        VS._ACTS.pop(ACCT, None)
        VS._USERS.clear()
        VS._RECORD.pop(ACCT, None)
        V0._CLAIMED.clear()
        self.mem, self.ag = Memory(), AgAPI(self.OUTCOMES)
        self.contacts = CT.MemoryContactStore()
        self.contacts.rows[ACCT] = {"account_id": ACCT, "name": "Tyler Warren", "mobile_e164": "+34608445715",
                                    "consent_at": datetime(2026, 11, 1, tzinfo=timezone.utc), "consent_wording_version": "v1",
                                    "consent_text_sha256": "0" * 64}
        self.mb = MB.MemoryMailboxStore()
        GW = VN._API()
        self.p = [mock.patch.object(M, "kind", self.mem.kind), mock.patch.object(M, "put_kind", self.mem.put_kind),
                  mock.patch.object(VS, "CALL", self.ag.call), mock.patch.object(VS, "target", mock.AsyncMock(return_value="sandbox")),
                  mock.patch.object(CT, "STORE", self.contacts), mock.patch.object(MB, "STORE", self.mb),
                  mock.patch.object(GR, "address_of", mock.AsyncMock(return_value="tyler@kanoe.ai")),
                  mock.patch.object(WB, "trip_day_words", mock.AsyncMock(return_value="")),
                  mock.patch.object(OC, "booked_later", lambda *a, **k: None),
                  mock.patch.object(LE, "completed", mock.AsyncMock(return_value={})),
                  mock.patch.object(GW, "api", mock.AsyncMock(return_value=(200, {"reservations": []}))),
                  mock.patch.object(VN, "card_of", lambda acct, pid=None, name=None: CARD),
                  mock.patch("booking_signer.basket._run", lambda: None)]   # claims in-process (no database in a unit test)
        for p in self.p:
            p.start()
        self.tok = VS.TAP.set({"kind": "supabase", "token": "test-session"})   # the in-app session: their tap IS the approval

    def tearDown(self):
        VS.TAP.reset(self.tok)
        for p in self.p:
            p.stop()
        VN._HELD.pop(ACCT, None)
        VS._ACTS.pop(ACCT, None)

    def hold(self):
        return run(VN.follow(Ctx("book La Taberna friday 21:00 for 2"), {"name": "La Taberna", "city": "Madrid"}, RD, RES,
                             "2026-11-13T21:00", datetime.now(timezone.utc), CARD, DEC))

    def yes(self):
        return run(VN.book_venue(Ctx("Yes, book it"), {"approval": {"said": "Yes, book it"}}))

    def tap(self, qid, option):
        return run(VN.answer_card(Ctx(option), qid, "pick:" + option))


class TheZonaQuestion(Base):
    def test_asked_once_with_agapis_options_as_taps_and_the_answer_goes_back_to_agapi(self):
        held = self.hold()
        self.assertEqual((held["status"], held["route"]), ("awaiting_yes", "platform_book"))
        q = self.yes()
        print("\n── the walk stopped; Sasha asks ONCE ──\n" + json.dumps({k: q[k] for k in ("ask", "choices", "read_back_id")}, ensure_ascii=False))
        self.assertEqual(q["ask"], "La Taberna's booking asks for your Zona: Terraza, Salón, Barra. Which one?")   # AgAPI's ask, said
        self.assertEqual([c["title"] for c in q["choices"]], ["Terraza", "Salón", "Barra"])        # exactly AgAPI's options
        self.assertTrue(all(c["route"] == "pick:" + c["title"] for c in q["choices"]))
        from app.agent import sasha as S
        card = S.render("book_venue", q, {})
        self.assertEqual((card["kind"], card["read_back_id"]), ("read_back", q["read_back_id"]))     # S2's one-tap card
        done = self.tap(q["read_back_id"], "Terraza")
        sub = self.ag.bodies("venue.submit_booking")
        print("── the submit_booking body after the tap (Sasha 329 · CR 161) ──\n" + json.dumps(sub[-1], ensure_ascii=False))
        self.assertEqual(sub[-1]["choices"], {"zona": "Terraza"})                                   # the PERSON's choice, to AgAPI
        self.assertEqual(sub[-1]["prepared_id"], sub[0]["prepared_id"])                             # the SAME prepared booking
        self.assertNotIn("choices", sub[0])                                                         # never guessed before
        self.assertEqual(len(self.ag.bodies("venue.prepare_booking")), 1)                           # prepared once — no `answers`
        self.assertEqual(self.ag.ops().count("approvals.in_app_tap"), 2)   # their yes, then their tap — no third ask
        print("── said ──\n" + done["line"])
        self.assertEqual(done["status"], "confirmed")
        for part in ("La Taberna", "Friday 13 November", "21:00", "2 people", "Terraza", "CM48213"):
            self.assertIn(part, done["line"])
        self.assertNotIn("CoverManager", done["line"])   # 249: the platform is never said

    def test_her_words_answer_it_too_and_never_a_guess(self):
        self.hold()
        q = self.yes()
        with self.assertRaises(V0.ToolError) as e:   # "the one by the window" names no option: asked, never chosen for them
            run(VN.book_venue(Ctx("the one by the window"), {"approval": {"said": "the one by the window"}}))
        self.assertEqual(e.exception.code, "which_option")
        self.assertEqual(self.ag.choices, {})
        done = run(VN.book_venue(Ctx("salon please"), {"approval": {"said": "salon please"}}))
        self.assertEqual(self.ag.bodies("venue.submit_booking")[-1]["choices"], {"zona": "Salón"})
        self.assertEqual(done["status"], "confirmed")
        self.assertTrue(q["read_back_id"].startswith("q_"))

    def test_in_my_bookings_with_its_reference_and_the_stop_is_not_a_booking(self):
        self.hold()
        q = self.yes()
        self.tap(q["read_back_id"], "Terraza")
        rows = run(VS.bookings(ACCT))
        print("── My bookings ──\n" + json.dumps(rows, ensure_ascii=False))
        self.assertEqual([r["act_id"] for r in rows], ["act_booked"])
        self.assertEqual((rows[0]["status"], rows[0]["reference"], rows[0]["route"], rows[0]["chosen"]),
                         ("confirmed", "CM48213", "platform", {"zona": "Terraza"}))

    def test_on_whatsapp_the_options_are_taps_never_yes_no(self):
        from booking_signer import guest_whatsapp as GWM, wa_agent as WA
        self.hold()
        q = self.yes()
        out = GWM.Out()
        WA._read_back({"kind": "read_back", **q}, out)
        kind, text, buttons = out.items[0]
        self.assertEqual(kind, "ask")
        self.assertEqual(buttons, [("Terraza", "say:Terraza"), ("Salón", "say:Salón"), ("Barra", "say:Barra")])
        self.assertEqual(WA.message_of(ACCT, "", "say:Terraza"), "Terraza")


class TheTapIsTheYesOnlyForTheSameWords(Base):
    def test_a_changed_read_back_is_shown_and_waits_for_their_yes(self):
        self.ag.extra_line = ["Their deposit: €10 per person, charged by CoverManager."]   # AgAPI's read-back changed after the answer
        self.hold()
        q = self.yes()
        got = self.tap(q["read_back_id"], "Terraza")
        self.assertEqual(got["status"], "awaiting_yes")
        self.assertIn("zona: Terraza", got["read_back"][0])   # Sasha 329 · CR 161 · AgAPI's own read-back carries the choice
        self.assertIn("Their deposit: €10 per person, charged by CoverManager.", got["read_back"])
        self.assertEqual(self.ag.ops().count("approvals.in_app_tap"), 1)   # nothing sent on the tap
        done = run(VN.book_venue(Ctx("Yes, book it"), {"approval": {"said": "Yes, book it"}}))   # their yes to THESE words sends it
        self.assertEqual((done["status"], self.ag.ops().count("approvals.in_app_tap")), ("confirmed", 2))

    def test_voice_or_old_s1_without_an_in_app_session_never_takes_the_tap_as_the_yes(self):
        VS.TAP.reset(self.tok)
        self.tok = VS.TAP.set(None)
        self.hold()
        VN._HELD[ACCT].update(rung="platform_choice", id="q_x", read_back_id="q_x", choice="zona", field="Zona", options=["Terraza", "Salón"],
                              base=VN._HELD[ACCT]["same"], asked_at=datetime.now(timezone.utc), out={})
        got = run(VN.book_venue(Ctx("Terraza", surface="voice"), {"approval": {"said": "Terraza"}}))
        self.assertEqual(got["status"], "awaiting_yes")
        self.assertNotIn("approvals.in_app_tap", self.ag.ops())


class AskedOnceNeverALoop(Base):
    """If the walk stops again on the SAME question after their answer, it is said plainly, with their page — never asked twice."""
    OUTCOMES = (STOPPED, {**STOPPED, "act_id": "act_zona2"})

    def test_the_same_question_after_the_answer_is_said_not_asked(self):
        self.hold()
        q = self.yes()
        again = self.tap(q["read_back_id"], "Terraza")
        print("\n── the walk stopped again on the same question ──\n" + again["say"])
        self.assertEqual(self.ag.bodies("venue.submit_booking")[-1]["choices"], {"zona": "Terraza"})   # sent all the same
        self.assertEqual(again["status"], "not_booked")
        self.assertNotIn("choices", again)
        self.assertNotIn("Which one", again["say"])
        self.assertEqual(again["page_url"], CM_PAGE)
        self.assertIsNone(VN._HELD.get(ACCT))
        self.assertEqual(run(VS.bookings(ACCT)), [])   # two stops, no booking


class TheConfirmationEmailAndCancel(Base):
    def _booked(self):
        self.hold()
        self.tap(self.yes()["read_back_id"], "Terraza")

    def _sync(self, mails):
        from booking_signer import guest_whatsapp as GWM
        from booking_signer.vault import crypto as VC
        self.mb.links[ACCT] = {"account_id": ACCT, "vault_item_id": "v328"}

        async def gmail(method, url, token, params=None):
            if url.endswith("/messages"):
                return 200, {"messages": [{"id": k} for k in mails]}
            if url.endswith("/profile"):
                return 200, {"emailAddress": "Tyler.Reads@gmail.com"}
            s, frm, body = mails[url.rsplit("/", 1)[1]]
            return 200, {"payload": {"headers": [{"name": "Subject", "value": s}, {"name": "From", "value": frm}], "mimeType": "text/plain",
                                     "body": {"data": base64.urlsafe_b64encode(body.encode()).decode()}}}
        with mock.patch.object(MB, "GMAIL_HTTP", gmail), mock.patch.object(VC, "use_connection", mock.AsyncMock(return_value="ya29")), \
                mock.patch.object(GWM, "_upcoming", mock.AsyncMock(return_value=[])), mock.patch.object(MB, "_offer_on_whatsapp", mock.AsyncMock()):
            return run(MB.sync(ACCT))

    def test_coverManagers_email_puts_its_cancel_link_on_that_booking(self):
        self._booked()
        found = self._sync({"m1": CM_MAIL})
        act = next(a for a in run(VS.acts_of(ACCT)) if a["act_id"] == "act_booked")
        print("\n── the act after CoverManager's email ──\n" + json.dumps({k: act.get(k) for k in ("act_id", "reference", "cancel_link")}))
        self.assertEqual(act["cancel_link"], CANCEL)                       # https, CoverManager's own host, named a cancel
        self.assertEqual((found[0]["match_basis"], found[0]["offered_action"]), ("agapi_act", None))   # never "Add it to your itinerary?"
        self.assertNotIn("cancel_link", found[0]["facts"])                 # one place: the act
        self.assertEqual(self.mb.applied, [])                              # no second trip item
        self.assertEqual(run(VS.bookings(ACCT))[0]["cancel_link"], CANCEL)

    def test_only_https_on_the_platforms_own_host(self):
        frm = "CoverManager <noreply@covermanager.com>"
        self.assertIsNone(MB.cancel_link(frm, "Cancela aquí: https://evil.example/reservation/cancel/x"))
        self.assertIsNone(MB.cancel_link(frm, "Cancela aquí: http://www.covermanager.com/reservation/cancel/x"))
        self.assertIsNone(MB.cancel_link(frm, "Privacidad: https://www.covermanager.com/privacy"))
        self.assertIsNone(MB.cancel_link("La Taberna <hola@lataberna.example>", "cancel: https://lataberna.example/cancel"))
        self.assertEqual(MB.cancel_link(frm, CM_MAIL[2]), CANCEL)

    def test_outside_the_cancel_beta_the_emails_link_and_the_phone_nothing_pressed(self):
        """Sasha 329 · CR 161: "Cancel La Taberna" goes to AgAPI's venue.cancel_booking (the ONE cancel path). Outside the beta AgAPI says
        not_allowed with no link of its own here: the link their confirmation email gave (on the act) and the phone — nothing pressed."""
        self._booked()
        self._sync({"m1": CM_MAIL})
        n = len(self.ag.calls)
        out = run(VN.cancel_venue(Ctx("Cancel La Taberna"), {"venue": "La Taberna"}))
        print("\n── \"Cancel La Taberna\" (outside the beta) ──\n" + out["line"] + "\n" + json.dumps(out.get("button")))
        self.assertEqual((out["status"], out["sent"], out["page_url"]), ("yours_there", False, CANCEL))
        self.assertEqual(out["button"], {"label": "Cancel on CoverManager", "link": CANCEL})
        self.assertIn("+34910000328", out["line"])
        sent = [(op, b) for op, b in self.ag.calls[n:]]
        self.assertEqual([op for op, _ in sent if op == "venue.cancel_booking"], ["venue.cancel_booking"])   # asked of AgAPI, once
        self.assertFalse({"approvals.in_app_tap", "venue.submit_booking"} & {op for op, _ in sent}, sent)
        from app.agent import sasha as S
        self.assertEqual(S.render("cancel_venue", out, {})["url"], CANCEL)

    def test_before_the_email_arrives_the_phone(self):
        self._booked()
        out = run(VN.cancel_venue(Ctx("Cancel La Taberna"), {"venue": "La Taberna"}))
        self.assertNotIn("page_url", out)
        self.assertIn("+34910000328", out["line"])


class TheBookingEmail(Base):
    def test_use_this_email_is_stored_on_the_one_contact_record_and_given_to_agapi(self):
        got = run(VN.save_contact(Ctx("use tylerwarren@gmail.com for my bookings"), {"email": "tylerwarren@gmail.com"}))
        self.assertEqual(got["booking_email"], "tylerwarren@gmail.com")
        self.assertEqual(self.contacts.rows[ACCT]["booking_email"], "tylerwarren@gmail.com")    # THE record (no second store)
        self.assertEqual(self.contacts.rows[ACCT]["mobile_e164"], "+34608445715")              # name and mobile untouched
        self.hold()
        person = self.ag.bodies("venue.prepare_booking")[0]["person"]
        print("\n── prepare_booking's person ──\n" + json.dumps(person))
        self.assertEqual(person, {"name": "Tyler Warren", "phone": "+34608445715", "email": "tylerwarren@gmail.com"})
        run(self.contacts.put({**self.contacts.rows[ACCT], "name": "Tyler W"}))                # a name change keeps it
        self.assertEqual(self.contacts.rows[ACCT]["booking_email"], "tylerwarren@gmail.com")

    def test_never_an_address_they_didnt_write(self):
        with self.assertRaises(V0.ToolError) as e:
            run(VN.save_contact(Ctx("use my gmail for bookings"), {"email": "tylerwarren@gmail.com"}))
        self.assertEqual(e.exception.code, "not_their_words")
        self.assertNotIn("booking_email", self.contacts.rows[ACCT])
        del self.contacts.rows[ACCT]
        with self.assertRaises(V0.ToolError) as e:   # no contact yet: kept with their name and mobile, asked once
            run(VN.save_contact(Ctx("use tylerwarren@gmail.com"), {"email": "tylerwarren@gmail.com"}))
        self.assertEqual(e.exception.code, "contact_first")

    def test_the_default_is_the_linked_mailbox_then_the_sign_in(self):
        self.assertEqual(run(CT.booking_email(ACCT)), "tyler@kanoe.ai")              # no mailbox: their sign-in address
        self.mb.links[ACCT] = {"account_id": ACCT, "vault_item_id": "v328"}
        run(MB.STORE.set_link(ACCT, address="tyler.reads@gmail.com"))
        self.assertEqual(run(CT.booking_email(ACCT)), "tyler.reads@gmail.com")       # where Sasha reads
        self.hold()
        self.assertEqual(self.ag.bodies("venue.prepare_booking")[0]["person"]["email"], "tyler.reads@gmail.com")

    def test_the_mailbox_learns_its_own_address_once(self):
        TheConfirmationEmailAndCancel._sync(self, {})
        self.assertEqual(self.mb.links[ACCT]["address"], "tyler.reads@gmail.com")


ROOT = pathlib.Path(__file__).resolve().parents[1]


class TheWholeClass(unittest.TestCase):
    def _py(self):
        for d in ("agapi", "booking_signer", "app"):
            for f in (ROOT / d).rglob("*.py"):
                yield f, f.read_text()

    def test_one_person_for_every_venue(self):
        """Every venue.prepare_booking person comes from booking_person (its one email) — no person dict built anywhere else."""
        src = (ROOT / "agapi" / "venues.py").read_text()
        self.assertNotIn("GR.address_of", src)
        built = re.findall(r'"email":\s*await[^}]*', src)
        self.assertEqual(built, ['"email": await CT.booking_email(account)'])   # booking_person's own line, and no other
        for m in re.finditer(r"\n(\s*)p = await VS\.prepare\(ctx\.account, place, person", src):
            before = src[max(0, m.start() - 900):m.start()]
            self.assertIn("person = await booking_person(ctx.account, res)", before)
        self.assertIn("CT.booking_email(account)", inspect.getsource(VN.booking_person))

    def test_prepare_booking_has_one_sender_and_one_named_patch(self):
        hits = sorted(str(f.relative_to(ROOT)) for f, s in self._py() if re.search(r'(?:CALL|_call)\((?:account, )?"venue\.prepare_booking"', s))
        self.assertEqual(hits, ["agapi/venue_submit.py", "agapi/venue_truth.py"])   # venue_truth: the PATCH named in the doc

    # Sasha 329 · MOVED: "the walk's sentence read in one place" → read NOWHERE (CR 161's ask; test_s329.TheWholeClass), and "the platform
    # cancel sends nothing" → the platform cancel goes through AgAPI's venue.cancel_booking after the read-back yes (test_s329)

    def test_the_cancel_link_is_kept_only_on_the_act(self):
        writers = sorted(str(f.relative_to(ROOT)) for f, s in self._py() if re.search(r'\["cancel_link"\]\s*=|"cancel_link":\s*cancel', s))
        self.assertEqual(writers, ["agapi/venue_submit.py"])


if __name__ == "__main__":
    unittest.main()
