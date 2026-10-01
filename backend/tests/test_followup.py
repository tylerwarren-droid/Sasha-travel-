"""Sasha 74 · the redundancy rules: Sasha's own email on every phone booking; the confirmation email after a yes; the
"could you confirm" email after an unclear call; the venue's reply read with the field checks. Memory and Postgres.

    cd backend && python -m unittest tests.test_followup -v
"""
from __future__ import annotations

import asyncio
import os
import unittest
from unittest import mock

from booking_signer import emailing as E, followup as FU
from booking_signer.call_store import MemoryCallStore
from booking_signer.ladder_store import MemoryLadderStore
from tests import test_booking_ladder as TBL
from tests.test_booking_ladder import PG_URL, LA_CONTRA_SITE, LadderRoutes, NOW, R, signed

READY = {"SASHA_EMAIL_FROM": "Sasha (Kanoe) <sasha@in.kanoe.test>", "SASHA_INBOUND_DOMAIN": "in.kanoe.test"}
GUEST = "anna@example.test"


def run(c):
    return asyncio.run(c)


class FollowUps:
    """Mixed into one TestCase per store, on the ladder routes' own fixture (a read of La Contra: a phone and an email)."""

    def setUp(self):
        LadderRoutes.setUp(self)
        self.ready = mock.patch.dict(os.environ, READY)
        self.ready.start()
        self.set_guest_email(GUEST)

    def tearDown(self):
        self.ready.stop()
        LadderRoutes.tearDown(self)

    def read(self):
        return LadderRoutes.read(self)

    def prepare(self):
        v = self.read()
        r = self.c.post("/api/booking/calls", json={"read_id": v["read_id"], **LadderRoutes.BOOKING})
        self.assertEqual(r.status_code, 200, r.text)
        return v, r.json()

    def call_row(self, call_id):
        return self.c.portal.call(self.calls.get_call, TBL.DEMO_ACCOUNT_ID, call_id)

    def sends(self):
        return [b for m, u, b in self.web.requests if u == E.RESEND_SEND_URL]

    # ── rule 1 and the read-back ──────────────────────────────────────────────────────────────────────────────────

    def test_the_read_back_says_her_email_and_the_follow_up_before_the_yes(self):
        _, p = self.prepare()
        lines = p["read_back"]["lines"]
        # Sasha 90 (a) · her address is now given as the written confirmation she asks for after the yes
        self.assertTrue(any(l.startswith("After their yes I'll ask them to confirm it in writing — ") and "sasha@in.kanoe.test" in l for l in lines), lines)
        follow = [l for l in lines if l.startswith("After the call I'll email La Contra at ")]
        self.assertEqual(len(follow), 1, lines)
        self.assertIn(f"you're copied privately at {GUEST}", follow[0])
        self.assertTrue(lines[-1].endswith("Shall I call them now?"))
        brief = self.call_row(p["call_id"])["brief"]
        self.assertIn("sasha arroba in punto kanoe punto test", brief["confirm_ask"])          # said in Spanish, spelled out
        self.assertIn(brief["confirm_ask"], brief["task"])
        self.assertLessEqual(len(brief["task"]), 2000)
        self.assertEqual((brief["sasha_email"], brief["followup"]["bcc"]), ("sasha@in.kanoe.test", GUEST))
        self.assertTrue(brief["followup"]["to"].endswith("@lacontra.test"))

    def test_nothing_is_promised_while_her_address_cannot_receive(self):
        with mock.patch.dict(os.environ, {"RESEND_WEBHOOK_SECRET": ""}):
            _, p = self.prepare()
        self.assertFalse([l for l in p["read_back"]["lines"] if "sasha@" in l or "After the call I'll email" in l])
        self.assertNotIn("followup", self.call_row(p["call_id"])["brief"])

    # ── rules 2–3 · the email after the call ──────────────────────────────────────────────────────────────────────

    def after(self, outcome):
        _, p = self.prepare()
        call = self.call_row(p["call_id"])
        return p, call, self.c.portal.call(FU.after_call, call, outcome, NOW)

    def test_a_yes_sends_the_confirmation_once_restating_everything(self):
        p, call, what = self.after("yes")
        self.assertEqual(what, "sent")
        mail = self.sends()[-1]
        ref = call["brief"]["own_reference"]   # Sasha 88 · her reference, as she said it on the call
        self.assertEqual((mail["to"], mail["bcc"], mail["subject"]), ([call["brief"]["followup"]["to"]], [GUEST], f"Confirmación de la reserva a nombre de Anna Johnson · Ref. {ref}"))
        self.assertIn(f"(Ref. {ref}).", mail["text"])
        self.assertIn("les escribo para dejar por escrito la reserva que nos confirmaron", mail["text"])
        self.assertIn("Una mesa: jueves 8 de octubre", mail["text"])
        self.assertIn("Johnson", mail["text"])
        self.assertIn("sasha@in.kanoe.test", mail["text"])
        self.assertEqual(mail["reply_to"], f"act-{FU.followup_id(p['call_id'], 'confirm')}@in.kanoe.test")
        self.assertEqual(self.c.portal.call(FU.after_call, call, "yes", NOW), "already sent")   # never twice
        self.assertEqual(len([m for m in self.sends() if m["subject"].startswith("Confirmación")]), 1)

    def test_an_unclear_call_asks_them_to_confirm(self):
        p, call, what = self.after("unclear")
        self.assertEqual(what, "sent")
        mail = self.sends()[-1]
        self.assertEqual(mail["subject"], f"¿Podrían confirmar la reserva a nombre de Anna Johnson? · Ref. {call['brief']['own_reference']}")
        self.assertIn("Acabo de hablar con ustedes por teléfono y no me quedó claro", mail["text"])

    def test_no_follow_up_for_a_no_or_when_email_is_off(self):
        _, _, what = self.after("no")
        self.assertIsNone(what)
        _, p = self.prepare()                                  # promised while email was on…
        call = self.call_row(p["call_id"])
        with mock.patch.dict(os.environ, {"SASHA_EMAILS_ENABLED": "0"}):   # …and off by the time the call ended: said, not sent
            what = self.c.portal.call(FU.after_call, call, "yes", NOW)
        self.assertTrue(what.startswith("not sent: emails are off"), what)

    # ── rule 3 · the reply, read with the field checks ────────────────────────────────────────────────────────────

    def reply_to(self, p, kind, text, pid):
        self.web.resend_received[pid] = {"text": text}
        body, h = signed({"type": "email.received", "data": {"email_id": pid, "from": "La Contra <reservas@lacontra.test>",
                                                            "to": [f"act-{FU.followup_id(p['call_id'], kind)}@in.kanoe.test"], "subject": "Re: ¿Podrían confirmar?"}})
        return self.c.post("/api/booking/email/inbound", content=body, headers=h)

    def test_a_reply_confirming_day_time_and_number_confirms(self):
        p, call, _ = self.after("unclear")
        r = self.reply_to(p, "ask", "Sí, confirmado: 4 personas el jueves 8 a las 20:00, a nombre de Johnson. Un saludo.", "rcv_ok")
        self.assertEqual(r.json(), {"ok": True, "matched": True})
        self.assertEqual(self.trip_status(call["trip_item_id"]), "confirmed")

    def test_a_reply_with_another_time_is_a_proposal_never_a_booking(self):
        p, call, _ = self.after("unclear")
        self.reply_to(p, "ask", "A las 20 imposible, os podemos dar a las 22:00 para 4.", "rcv_prop")
        self.assertEqual(self.trip_status(call["trip_item_id"]), "proposed")

    def test_a_reply_that_says_neither_leaves_it_as_it_is(self):
        p, call, _ = self.after("unclear")
        before = self.trip_status(call["trip_item_id"])
        self.reply_to(p, "ask", "Gracias, lo miramos y les decimos.", "rcv_none")
        self.assertEqual(self.trip_status(call["trip_item_id"]), before)

    def test_the_reading_rules(self):
        o = {"schema": "reservation/1", "flow": "book", "who": {"name": "Anna Johnson"}, "what": {"activity": "a table", "activity_venue_lang": "una mesa", "category": "restaurant"},
             "where": {}, "when": {"mode": "at", "at": "2026-10-08T20:00"}, "how_many": {"count": 4, "unit": "people"}}
        self.assertEqual(FU.reply_reading("Sí, confirmado para 4 el jueves 8 a las 20:00.", o)["result"], "confirmed")
        self.assertEqual(FU.reply_reading("Sí, perfecto.", o)["result"], "none")            # a bare yes restates nothing
        self.assertEqual(FU.reply_reading("No, lo siento, estamos completos.", o)["result"], "declined")
        self.assertEqual(FU.reply_reading("Podemos a las 21:00.", o)["result"], "proposed")

    # ── Sasha 75 · the email rung's own booking: the reply is read the same way ───────────────────────────────────

    def rung_email(self):
        v = self.read()
        p = self.c.post("/api/booking/emails", json={"read_id": v["read_id"], **LadderRoutes.BOOKING, "email": GUEST}).json()
        r = self.c.post(f"/api/booking/emails/{p['email_id']}/send", json={"read_back_sha256": p["read_back"]["sha256"], "approval": {"how": "button"}})
        self.assertEqual(r.json()["status"], "sent", r.text)
        return p

    def rung_reply(self, p, text, pid):
        self.web.resend_received[pid] = {"text": text}
        body, h = signed({"type": "email.received", "data": {"email_id": pid, "from": "Tyler <tyler@kanoe.test>",
                                                            "to": [f"act-{p['email_id']}@in.kanoe.test"], "subject": "Re: Solicitud de mesa"}})
        return self.c.post("/api/booking/email/inbound", content=body, headers=h).json()

    def test_an_email_rung_booking_confirmed_by_reply(self):
        p = self.rung_email()
        quoted = ("Confirmado: mesa para 4 personas el jueves 8 de octubre a las 20:00, a nombre de Johnson.\n\n"
                  "El jue, 1 oct 2026 a las 17:20, Sasha (Kanoe) <act-x@in.kanoe.test> escribió:\n> Solicitud de mesa…")
        self.assertEqual(self.rung_reply(p, quoted, "rcv_rung_ok"), {"ok": True, "matched": True})
        self.assertEqual(self.trip_status(p["trip_item_id"]), "confirmed")

    def test_an_email_rung_reply_with_another_time_is_proposed(self):
        p = self.rung_email()
        self.rung_reply(p, "A las 20:00 no podemos; os ofrecemos el jueves 8 a las 21:30 para 4.\n\nOn Thu wrote:\n> …", "rcv_rung_prop")
        self.assertEqual(self.trip_status(p["trip_item_id"]), "proposed")

    def test_a_bare_yes_above_our_quoted_email_confirms_nothing(self):
        p = self.rung_email()
        before = self.trip_status(p["trip_item_id"])
        self.rung_reply(p, "Sí.\n\nEl jue, 1 oct 2026 a las 17:20, Sasha (Kanoe) <act-x@in.kanoe.test> escribió:\n"
                           "> Solicitud de mesa para 4 personas el 2026-10-08 a las 20:00", "rcv_rung_bare")
        self.assertEqual(self.trip_status(p["trip_item_id"]), before)

    def test_a_reply_whose_words_could_not_be_fetched_is_read_on_the_next_sweep(self):
        """Sasha 76 · live, 1 Oct: the sending-only key could not read received mail; both replies landed unread."""
        from booking_signer import ladder_routes as LR
        p = self.rung_email()
        body, h = signed({"type": "email.received", "data": {"email_id": "rcv_late", "from": "Tyler <tyler@kanoe.test>",
                                                            "to": [f"act-{p['email_id']}@in.kanoe.test"], "subject": "Re: Solicitud"}})
        self.c.post("/api/booking/email/inbound", content=body, headers=h)                  # Resend has no body for it yet → unread
        self.assertNotEqual(self.trip_status(p["trip_item_id"]), "confirmed")
        self.web.resend_received["rcv_late"] = {"text": "Confirmado: mesa para 4 personas el jueves 8 de octubre a las 20:00, a nombre de Johnson."}
        self.assertEqual(self.c.portal.call(LR.reread_replies), 1)
        self.assertEqual(self.trip_status(p["trip_item_id"]), "confirmed")
        self.assertEqual(self.c.portal.call(LR.reread_replies), 0)                             # read once

    def test_own_words(self):
        self.assertEqual(FU.own_words("Vale\n\nOn Thu, Oct 1, 2026 at 5:20 PM Sasha (Kanoe) <a@b.c> wrote:\n> x"), "Vale")
        self.assertEqual(FU.own_words("Perfecto\n\nDe: Sasha (Kanoe) <sasha@booking.kanoe.ai>\nEnviado: jueves"), "Perfecto")
        self.assertEqual(FU.own_words("Ok\n-----Original Message-----\nFrom: x"), "Ok")

    # ── inbound: other products' mail is not Sasha's ──────────────────────────────────────────────────────────────

    def test_mail_for_another_domain_is_ignored_and_nothing_is_kept(self):
        body, h = signed({"type": "email.received", "data": {"email_id": "rcv_ad", "from": "someone@example.com",
                                                            "to": ["ops@applieddiligence.com"], "subject": "AD business"}})
        r = self.c.post("/api/booking/email/inbound", content=body, headers=h)
        self.assertEqual(r.json(), {"ok": True, "ignored": "not addressed to Sasha's domain"})
        self.assertEqual(self.quarantined(), [])

    def test_spoken_addresses(self):
        self.assertEqual(FU.spoken("sasha@booking.kanoe.ai", "es"), "sasha arroba booking punto kanoe punto ai")
        self.assertEqual(FU.spoken("sasha@booking.kanoe.ai", "de"), "sasha at booking Punkt kanoe Punkt ai")
        self.assertEqual(FU.spoken("sasha@booking.kanoe.ai", "fr"), "sasha arobase booking point kanoe point ai")


class OnMemory(FollowUps, unittest.TestCase):
    def make_stores(self):
        calls, ladder = MemoryCallStore(), MemoryLadderStore()
        ladder.trip_items = calls.trip_items   # one trip_items table, as in Postgres
        return calls, ladder

    def set_guest_email(self, e):
        self.ladder.account_emails = {TBL.DEMO_ACCOUNT_ID: e}

    def trip_status(self, item):
        return self.calls.trip_items[item]["status"]

    def quarantined(self):
        return self.ladder.quarantined


@unittest.skipUnless(PG_URL, "BOOKING_TEST_DATABASE_URL is not set — the Postgres half did NOT run")
class OnPostgres(FollowUps, unittest.TestCase):
    setUpClass = classmethod(TBL.OnPostgres.setUpClass.__func__)
    make_stores = TBL.OnPostgres.make_stores
    _q = TBL.OnPostgres._q

    def set_guest_email(self, e):
        self._q("update auth.users set email = $1 where id = $2::uuid", e, TBL.DEMO_ACCOUNT_ID)
        self.addCleanup(lambda: self._q("update auth.users set email = null where id = $1::uuid", TBL.DEMO_ACCOUNT_ID))

    def trip_status(self, item):
        return self._q("select status from trip_items where id = $1::uuid", item)[0]["status"]

    def quarantined(self):
        return self._q("select * from booking_email_quarantine")


if __name__ == "__main__":
    unittest.main()
