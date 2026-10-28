"""Sasha 301 · T79 — BOOKING MANAGEMENT SLICE 2: THE FINE PRINT ON EVERY BOOKING.

The root test (written before code, docs/sasha/s301-fine-print.md): every fine-print line hangs on THE ONE ITINERARY's row
(agapi/itinerary.py). The venue's terms are read from the venue's OWN words already on that row (no store of their own), each the
sentence they wrote, with "by <date/time>" only from the hours / days they stated and the booking's start. His cards and loyalty
numbers live in ONE place, his Keep: a loyalty item (programme + number) and a my_card (name, the LAST FOUR only, a perk in his
words). PATCH if a term nobody stated can be shown, or a full card number kept or shown.

    cd backend && python -m unittest tests.test_s301 -v
"""
from __future__ import annotations

import asyncio
import inspect
import os
import re
import unittest
from datetime import date, datetime, timedelta, timezone
from unittest import mock
from zoneinfo import ZoneInfo

from agapi import booking_fine_print as FP, booking_terms as BT, itinerary as IT, keep as K, s2_keep as KEEP
from booking_signer import loyalty as LY
from tests.test_s300 import ACCT, DAY, Base as S300Base, Ctx, run

MAD = ZoneInfo("Europe/Madrid")
#: a venue's reply, as their email says it — with Sasha's own request quoted under it (never their terms)
REPLY = ("Hola Tyler, confirmamos vuestra mesa para 2 personas. Pedimos una señal de 20€ por persona para confirmar la reserva. "
         "Las cancelaciones con menos de 24 horas de antelación no se reembolsan. La mesa es para 2 horas.\n"
         "El lun, 27 oct 2026, Sasha escribió:\n> No podemos dar tarjeta ni depósito. Si hay que cancelar, avisaremos 48 horas antes.")


def start(day=DAY, hhmm="21:00"):
    return datetime.fromisoformat(f"{day}T{hhmm}").replace(tzinfo=MAD)


# ── (1) THE TERMS: the venue's own sentences, never Sasha's, never a deadline nobody stated ───────────────────────────────────────

class Terms(unittest.TestCase):
    def test_deposit_cancellation_deadline_and_time_limit_in_their_words(self):
        t = BT.terms_of(REPLY, start())
        self.assertEqual([x["kinds"] for x in t], [["deposit"], ["cancellation"], ["time_limit"]])
        self.assertEqual(t[0]["quote"], "Pedimos una señal de 20€ por persona para confirmar la reserva.")
        self.assertEqual(t[1]["by"], (start() - timedelta(hours=24)).isoformat())
        self.assertEqual(t[1]["by_words"], BT.by_words(start() - timedelta(hours=24)))
        self.assertTrue(all(x["quote"] in REPLY for x in t))   # each one a sentence THEY wrote

    def test_sashas_own_request_quoted_under_their_reply_is_never_a_term(self):
        quotes = " ".join(x["quote"] for x in BT.terms_of(REPLY, start()))
        self.assertNotIn("48 horas", quotes)
        self.assertNotIn("depósito", quotes)

    def test_no_number_no_deadline_and_nothing_stated_nothing_shown(self):
        t = BT.terms_of("You can cancel the day before, no problem.", start())
        self.assertEqual(t[0]["kinds"], ["cancellation"])
        self.assertNotIn("by", t[0])   # "the day before" is not a time they gave: no deadline worked out
        self.assertEqual(BT.terms_of("Sí, os esperamos a las 21:00. ¡Gracias!", start()), [])
        self.assertEqual(BT.terms_of(None, start()), [])

    def test_a_no_show_charge_and_free_cancellation_in_english(self):
        t = BT.terms_of("Free cancellation up to 48 hours before. No-shows are charged £30 per guest.", start())
        self.assertEqual([x["kinds"] for x in t], [["cancellation"], ["no_show"]])
        self.assertTrue(t[0]["free"])
        self.assertEqual(t[0]["by"], (start() - timedelta(hours=48)).isoformat())

    def test_a_sentence_cut_off_by_the_record_is_never_shown(self):
        text = ("Confirmed for Friday. " + "x" * 160 + ". Cancellations within 24 hours are charged at 50 euros per pers")[:240]
        self.assertEqual(len(text), 240)
        self.assertEqual(BT.terms_of(text, start(), cut_at=IT.ACT_WORDS_CUT), [])

    def test_the_reminder_reads_the_earliest_deadline_they_stated(self):
        t = BT.terms_of("Cancel up to 72 hours before for free. Within 24 hours, 50% is charged.", start())
        self.assertEqual(BT.cancel_by(t)["by"], (start() - timedelta(hours=72)).isoformat())


# ── (2) HIS CARDS AND LOYALTY: one place (the Keep), the last four only, nothing invented ──────────────────────────────────────────

class KeepCards(unittest.TestCase):
    def setUp(self):
        self.store, self.kms = KEEP.MemoryKeepStore(), K.LocalKms(os.urandom(32))
        from agapi import s2_records as REC
        for p in (mock.patch.object(KEEP, "STORE", self.store), mock.patch("booking_signer.vault.kms.kek", lambda: self.kms),
                  mock.patch.object(REC, "RUN", None), mock.patch("booking_signer.plan_store._run", lambda: None)):
            p.start()
            self.addCleanup(p.stop)

    def note(self, **a):
        return run(FP.keep_note(Ctx(), a))

    def test_a_card_is_its_name_and_last_four_never_more(self):
        out = self.note(kind="card", name="Amex Gold", last4="1234", perk="free breakfast", perk_for="hotel", perk_where="Marriott")
        self.assertEqual(out["saved"], "Amex Gold ••••1234")
        from agapi.v0 import ToolError
        for bad in ({"last4": "4111111111111111"}, {"last4": "12345"}, {"name": "Visa 4111 1111 1111 1111"},
                    {"name": "Visa 41111111"}, {"perk": "card 4242424242424242"}):
            with self.assertRaises(ToolError, msg=bad) as e:
                self.note(kind="card", **{"name": "Visa", "last4": "9999", **bad})
            self.assertEqual(e.exception.code, "never_card")
        self.assertEqual(len(run(KEEP.wallet(ACCT))), 1)   # nothing refused was kept

    def test_the_same_card_told_again_is_one_item_with_its_perk(self):
        self.note(kind="card", name="Amex Gold", last4="1234")
        self.note(kind="card", name="Amex Gold", last4="1234", perk="free breakfast", perk_for="hotel")
        w = run(KEEP.wallet(ACCT))
        self.assertEqual([(x["masked"], x.get("perk")) for x in w], [("Amex Gold ••••1234", "free breakfast")])

    def test_a_loyalty_number_is_kept_and_only_its_mask_and_programme_leave(self):
        out = self.note(kind="loyalty", program="Marriott Bonvoy", number="123456789")
        self.assertEqual(out["saved"], "Marriott Bonvoy ••••789")
        self.assertEqual(out["say"], "Saved your Marriott Bonvoy number in your Keep. I'll show it on the bookings it applies to.")
        w = run(KEEP.wallet(ACCT))
        self.assertEqual(w[0]["program"], "Marriott Bonvoy")
        self.assertNotIn("123456789", repr(w))   # the wallet never carries the number

    def test_a_perk_with_no_place_it_applies_is_asked_not_guessed(self):
        from agapi.v0 import ToolError
        with self.assertRaises(ToolError) as e:
            self.note(kind="card", name="Amex Gold", last4="1234", perk="lounge access")
        self.assertEqual(e.exception.code, "perk_for_missing")

    def test_before_044_a_card_isnt_saved_and_she_says_so(self):
        class StorageError(Exception):   # found live: the database's refusal came back wrapped, its check named in the words
            pass

        async def refuse(row):
            raise StorageError('new row for relation "keep_items" violates check constraint "keep_items_type_check"')
        from agapi.v0 import ToolError
        with mock.patch.object(self.store, "add_item", refuse), self.assertRaises(ToolError) as e:
            self.note(kind="card", name="Amex Gold", last4="1234")
        self.assertEqual(e.exception.code, "type_not_open")
        self.assertEqual(e.exception.message, "Your Keep can't hold your cards yet — nothing was saved.")


class Perks(unittest.TestCase):
    WALLET = [{"item_id": "k1", "type": "loyalty", "masked": "Marriott Bonvoy ••••789", "program": "Marriott Bonvoy"},
              {"item_id": "k2", "type": "my_card", "masked": "Amex Gold ••••1234", "name": "Amex Gold", "last4": "1234",
               "perk": "free breakfast", "perk_for": "hotel", "perk_where": "Marriott"},
              {"item_id": "k3", "type": "my_card", "masked": "Visa ••••9999", "name": "Visa", "last4": "9999"}]

    def test_a_loyalty_number_and_a_card_perk_on_the_matching_hotel(self):
        p = BT.perks_for("hotel", "The Westin Palace Madrid", self.WALLET)
        self.assertEqual([x["line"] for x in p], ["Use your Marriott Bonvoy number (••••789).",
                                                   "Your Amex Gold (••••1234) includes free breakfast — as you told me."])

    def test_nothing_on_a_booking_it_doesnt_apply_to(self):
        self.assertEqual(BT.perks_for("hotel", "Hotel Urban Madrid", self.WALLET), [])
        self.assertEqual(BT.perks_for("dinner", "DiverXO", self.WALLET), [])   # a hotel programme never on a restaurant
        self.assertTrue(LY.matches("Hilton Honors", "Conrad Algarve", "hotel"))


# ── (3) ON THE ONE ITINERARY: the act's row, the Trip tab, the reminders, "what's the fine print on Friday?" ──────────────────────

class OnTheItinerary(S300Base):
    def setUp(self):
        super().setUp()
        self.api.states["act_mail"] = "confirmed"
        words = REPLY[:REPLY.index("\nEl lun")]   # what reaches the act's record: their reply (cut at 240 on the record)
        self.words = words[:240]
        orig = self.api.__call__

        async def call(op, body, approval=None, account=None):
            r = await orig(op, body, approval, account)
            if op == "venue.booking_status" and body["act_id"] == "act_mail":
                r["result"]["venue_words"] = {"untrusted_text": words}
            return r
        p = mock.patch.object(IT, "_wallet", mock.AsyncMock(return_value=Perks.WALLET))
        p.start()
        self.addCleanup(p.stop)
        from agapi import venue_submit as VS
        q = mock.patch.object(VS, "CALL", call)
        q.start()
        self.addCleanup(q.stop)

    def test_the_acts_row_carries_its_terms_in_their_words(self):
        r = self.rows()["DiverXO"]
        self.assertEqual(r["source"], "act")
        self.assertEqual([t["kinds"] for t in r["terms"]], [["deposit"], ["cancellation"], ["time_limit"]])
        self.assertTrue(all(t["quote"] in self.words for t in r["terms"]))
        self.assertEqual(r["terms"][1]["by"], (start() - timedelta(hours=24)).isoformat())
        self.assertEqual(self.rows()["Bar Tomate"]["terms"], [])   # a hand-over with no words of theirs: nothing

    def test_the_trip_tab_and_the_reminders_read_the_same_terms(self):
        extra = {r["venue"]: r for r in run(IT.extra_reservations(ACCT))}
        self.assertEqual(extra["DiverXO"]["terms"], self.rows()["DiverXO"]["terms"])
        from booking_signer import guest_whatsapp as GW
        ladder = [{"id": "11111111-1111-4111-8111-111111111111", "venue": "Casa Botín", "date": DAY, "time": "20:00", "timezone": "Europe/Madrid",
                   "status": "confirmed", "venue_words": "Reservado. Cancellations up to 12 hours before are free."}]
        with mock.patch.object(GW, "_upcoming", mock.AsyncMock(return_value=ladder)):
            from booking_signer import proactive as PR
            rows = {r["venue"]: r for r in run(PR._rows(ACCT))}
        self.assertEqual(rows["Casa Botín"]["terms"][0]["by"], (start(hhmm="20:00") - timedelta(hours=12)).isoformat())
        self.assertTrue(rows["DiverXO"]["terms"])

    def test_whats_the_fine_print_on_the_day(self):
        out = run(FP.booking_fine_print(Ctx("what's the fine print on that day?"), {"on": DAY, "venue": "DiverXO"}))
        self.assertIn("DiverXO", out["say"])
        self.assertIn("“Pedimos una señal de 20€ por persona para confirmar la reserva.”", out["say"])
        self.assertIn("that's by " + BT.by_words(start() - timedelta(hours=24)), out["say"])
        none = run(FP.booking_fine_print(Ctx(), {"on": DAY, "venue": "Bar Tomate"}))
        self.assertIn(FP.NO_TERMS, none["say"])
        self.assertNotRegex(out["say"] + none["say"], r"(?:\d[ -]?){5}")   # no number but the ones they and he gave (no card digits)

    def test_a_hotel_on_the_itinerary_shows_his_loyalty_and_card_perk(self):
        from booking_signer import basket as BK
        stay = {"id": "s1", "kind": "stay", "state": "booked", "day": DAY, "snapshot": {"name": "The Westin Palace Madrid", "nights": 2},
                "booking_reference": "W1", "trip_item_id": None}
        with mock.patch.object(BK, "items", mock.AsyncMock(return_value=[stay])):
            items = {i["title"]: i for i in run(IT.of(ACCT))}
        self.assertEqual([p["kind"] for p in items["The Westin Palace Madrid"]["perks"]], ["loyalty", "card"])
        self.assertNotIn("perks", items["DiverXO"])


class Reminder(unittest.TestCase):
    def setUp(self):
        from booking_signer import routes   # noqa: F401 · its import sets the Postgres ledger: imported first, so the test's stands
        from tests import test_proactive_s83 as T83
        self.t = T83.Rules("test_1_honest_status")
        self.t.setUp()
        self.addCleanup(self.t.tearDown)
        self.T83 = T83

    def test_a_reminder_before_their_cancellation_deadline_once(self):
        T83, t = self.T83, self.t
        t.rows = [{**T83.booking(date="2026-10-03", time="21:00"),
                   "venue_words": "Confirmado. Las cancelaciones con menos de 24 horas de antelación se cobran a 30€."}]
        t.inbound(T83.at(2026, 10, 2, 15, 30))
        self.assertEqual([d for d in t.tick(T83.at(2026, 10, 2, 14, 59)) if d["kind"] == "cancel_by"], [])   # before the 6 h lead
        done = [d for d in t.tick(T83.at(2026, 10, 2, 15, 1)) if d["kind"] == "cancel_by"]
        self.assertEqual(done[0]["outcome"], "sent")
        self.assertEqual(done[0]["text"], "Cancellation deadline for Casa Lucio (tomorrow, 21:00): Fri 2 Oct, 21:00. They said: "
                                          "“Las cancelaciones con menos de 24 horas de antelación se cobran a 30€.” Want to cancel? Tell me.")
        self.assertEqual([d["outcome"] for d in t.tick(T83.at(2026, 10, 2, 16, 0)) if d["kind"] == "cancel_by"], ["already sent"])   # once
        self.assertEqual(sum("Cancellation deadline" in b for b in t.bodies()), 1)
        self.assertEqual([d for d in t.tick(T83.at(2026, 10, 2, 21, 1)) if d["kind"] == "cancel_by"], [])   # never after it

    def test_no_deadline_they_stated_no_reminder_and_never_for_a_request(self):
        T83, t = self.T83, self.t
        t.rows = [{**T83.booking(status="requested"), "venue_words": "Cancel up to 24 hours before."},
                  {**T83.booking(i="t-2", venue="Botín"), "venue_words": "You can cancel any time."}]
        t.inbound(T83.at(2026, 10, 2, 15, 30))
        self.assertEqual([d for d in t.tick(T83.at(2026, 10, 2, 15, 1)) if d["kind"] == "cancel_by"], [])

    def test_before_044_a_cancel_by_is_never_sent(self):
        from booking_signer import proactive as PR

        class Base_:
            async def _run(self, fn):
                raise RuntimeError('new row violates check constraint "proactive_sent_kind_check"')
        pg = PR.PostgresProactiveStore(Base_())
        self.assertEqual(run(pg.claim({"account_id": ACCT, "trip_item_id": "11111111-1111-4111-8111-111111111111", "kind": "cancel_by",
                                       "local_day": date.today(), "status_at_send": "confirmed"})), -1)

    def test_the_044_migration_is_drafted_not_applied(self):
        import pathlib
        sql = (pathlib.Path(__file__).resolve().parents[1] / "booking_signer" / "sql" / "044_fine_print.sql").read_text()
        self.assertIn("APPLY AFTER DEPLOY", sql)
        self.assertIn("'cancel_by'", sql)
        self.assertIn("'my_card'", sql)
        self.assertIn("'two_hours'", sql)   # 043's kind kept


class OnePlace(unittest.TestCase):
    def test_terms_are_read_from_the_row_never_kept(self):
        src = inspect.getsource(BT) + inspect.getsource(FP)
        self.assertNotRegex(src, r"put_kind|put_kinds|STORE\.add|insert into")   # no store of their own
        self.assertIn("IT.of(ctx.account)", inspect.getsource(FP.booking_fine_print))
        self.assertIn("KEEP.put(", inspect.getsource(FP.keep_note))

    def test_the_tools_are_in_the_one_brain(self):
        from app.agent import s2 as S2
        from agapi import v0
        self.assertIn("booking_fine_print", S2.S2_TOOLS)
        self.assertIn("keep_note", S2.S2_TOOLS)
        self.assertIn("booking_fine_print", {t["name"] for t in v0.MANAGE_TOOLS})


if __name__ == "__main__":
    unittest.main()
