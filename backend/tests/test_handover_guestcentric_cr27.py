"""CR 27 · the Guestcentric hand-over, offline: the engine faked screen by screen (rates → rate terms → Select → /guest), the
founder's rules each tested — pay-at-hotel rates only, the guest's exact (rate, room) checked in the hotel's own summary,
every information field filled, the terms box left for the guest (2 taps), a card page after Book Now ends the session.

    cd backend && python -m unittest tests.test_handover_guestcentric_cr27 -v
"""
from __future__ import annotations

import asyncio
import os
import unittest
from datetime import date
from unittest import mock

from booking_signer import handover as HO
from booking_signer import handover_guestcentric as GC
from tests.test_handover_cr23 import FakeBB

ENGINE = ("https://book.smallportuguesehotels.com/api/bg/book.php?apikey=718b5ce5fcf26a16e6b8d80d90941bef&s=default"
          "&channelKey=39ed7b7b7dae559eb40276305db50f97&l=en")
STAY = {"checkin": date(2026, 11, 16), "checkout": date(2026, 11, 18), "adults": 2, "children": 0, "rooms": 1}
# the hotels' own words (read 5 Oct 2026, CR 27)
STANDARD = ("Standard Rate Experience comfort and charm with our standard rate! Free cancellation 24h! Room Only Book directly with "
            "us and take advantage of our free cancellation policy until 24hours prior to arrival with the standard rate. Pay at the hotel.")
NONREF = ("Non-Refundable Rate Our Best Rate — Non-Refundable Room Only Pay now and secure our lowest available price — the smartest "
          "choice when your plans are set. Please note that this rate is non-refundable.")
PROMO = "Newsletter Special Promotion! Register, book directly and get more. Enjoy free cancellation up to 5 days before arrival"


def guest_fields(values=None, terms=False, offers=False, extra=()):
    v = values or {}
    names = ["first-name", "last-name", "email", "country-code", "phone", "address", "city", "zip-code"]
    out = [{"name": n, "type": "text", "value": v.get(n, ""), "checked": False, "autocomplete": "", "label": n} for n in names]
    out.append({"name": "special-requests", "type": "textarea", "value": v.get("special-requests", ""), "checked": False,
                "autocomplete": "", "label": "Notes"})
    out += [{"name": "notify-offers", "type": "checkbox", "value": "", "checked": offers, "autocomplete": "", "label": "offers"},
            {"name": "accept-terms", "type": "checkbox", "value": "", "checked": terms, "autocomplete": "", "label": "terms"}]
    return out + list(extra)


class FakeEngine:
    """Emporium Lisbon Suites' engine, as seen on 5 Oct: two rates, one room each; Select → /guest."""
    rates_list = [{"i": 0, "rate": "Non-Refundable Rate", "room": "Family Suite City View", "price": "€280 /total stay", "cancel": "Non refundable"},
                  {"i": 1, "rate": "Standard Rate", "room": "Family Suite City View", "price": "€400 /total stay",
                   "cancel": "Free cancellation until 14 Nov 2026 at 18:00 local time."}]
    terms = {0: NONREF, 1: STANDARD}
    summary_for = None            # a test can make the summary name another rate
    after_select = "/guest"
    pay_frames: list = []
    custom: list = []
    stubborn: set = set()
    answer_page = {"url": "https://book.smallportuguesehotels.com/confirmation", "text": "Thank you! Your reservation is confirmed. "
                   "Reservation number: GC-4411-PT", "fields": [], "frames": []}

    def __init__(self):
        self.values, self.selected, self.country, self.motive, self.closed = {}, None, "", None, False
        self.watching, self.guarded = None, None

    async def connect(self, url): pass
    async def guard(self, read_only): self.guarded = read_only
    async def goto(self, url): self.url = url
    async def settle(self, ms=0): pass
    async def rates(self): return [dict(r) for r in self.rates_list]
    async def rate_terms(self, i, url): return self.terms[i]

    async def select(self, i):
        self.selected = i
        return "https://book.smallportuguesehotels.com" + self.after_select + "?gc=x"

    async def read_guest(self):
        r = self.rates_list[self.selected] if self.selected is not None else {}
        summ = self.summary_for or f"{r.get('room')} {r.get('rate')} Total stay"
        return {"url": "https://book.smallportuguesehotels.com/guest", "fields": guest_fields(self.values), "custom": self.custom,
                "country": self.country, "summary": summ, "motive": [], "frames": list(self.pay_frames), "text": ""}

    async def set_country(self, c):
        self.country = c
        return c

    async def set_motive(self, m): self.motive = m

    async def fill_named(self, vals):
        for k, v in vals.items():
            if k not in self.stubborn:
                self.values[k] = v
        return {k: ("" if k in self.stubborn else v) for k, v in vals.items()}

    async def point_two(self): return {"terms": "I accept the Terms and Conditions", "book": "Book Now"}
    async def watch(self, on_tap, on_press, read_only, on_nav): self.watching = (on_tap, on_press, read_only, on_nav)
    async def answer(self): return dict(self.answer_page)
    async def close(self): self.closed = True


class Base(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.bb, self.pages = FakeBB(), []
        self.saved = (HO.BB, GC.PAGE_FACTORY, dict(HO.HANDOVERS))

        def factory():
            p = FakeEngine()
            self.pages.append(p)
            return p
        HO.BB, GC.PAGE_FACTORY = self.bb, factory
        FakeEngine.summary_for, FakeEngine.after_select, FakeEngine.pay_frames = None, "/guest", []
        FakeEngine.custom, FakeEngine.stubborn = [], set()
        GC.RATE_TERMS.clear()
        self.env = mock.patch.dict(os.environ, {"BROWSERBASE_API_KEY": "k"})
        self.env.start()

    def tearDown(self):
        for r in HO.HANDOVERS.values():
            if r.get("_watch"):
                r["_watch"].cancel()
        HO.BB, GC.PAGE_FACTORY = self.saved[0], self.saved[1]
        HO.HANDOVERS.clear(), HO.HANDOVERS.update(self.saved[2])
        self.env.stop()

    async def open(self, rate="Standard Rate", room="Family Suite City View", guest=None, read_only=True):
        return await GC.open_gc_handover(engine_url=ENGINE, stay=STAY, rate=rate, room=room, guest=guest or dict(GC.FICTIONAL),
                                         hotel="Emporium Lisbon Suites", account=None, read_only=read_only, fictional=True)


class Rates(unittest.TestCase):
    def test_only_pay_at_hotel_without_card_words(self):
        self.assertTrue(GC.rate_ok(STANDARD)[0])
        self.assertFalse(GC.rate_ok(NONREF)[0])                  # "Pay now", "non-refundable"
        self.assertFalse(GC.rate_ok(PROMO)[0])                   # silent on payment → not handed over
        self.assertFalse(GC.rate_ok("Pay at the hotel. A valid credit card is required as guarantee.")[0])
        self.assertTrue(GC.rate_ok("Pago en el hotel.")[0])

    def test_a_reference_is_a_reference(self):
        m = GC.CONFIRMED.search("Your reservation is confirmed. Reservation number: GC-4411-PT")
        self.assertEqual(m.group(1) or m.group(2), "GC-4411-PT")
        self.assertIsNone(GC.CONFIRMED.search("Your reservation is being processed"))
        m = GC.CONFIRMED.search("Reserva confirmada. Localizador: 88231")
        self.assertEqual(m.group(1) or m.group(2), "88231")


class Ready(Base):
    async def test_two_taps_every_field_filled_terms_left(self):
        rec = await self.open()
        self.assertEqual((rec["state"], rec["taps_left"], rec["rate"]), ("ready", 2, "Standard Rate"))
        p = self.pages[0]
        self.assertEqual(p.selected, 1)                          # the guest's rate, not the first card
        self.assertTrue(p.guarded)                               # read-only: no write leaves the browser
        self.assertEqual((p.country, p.motive), ("Spain", "Leisure"))
        self.assertEqual(p.values["first-name"], "Prueba")
        self.assertNotIn("accept-terms", p.values)               # never ticked
        self.assertEqual(rec["summary"]["day"], "Mon 16 Nov – Wed 18 Nov · 2 nights")
        self.assertIn('book.php?apikey=', rec["fallback_link"])


class Refusals(Base):
    async def refused(self, rule, **kw):
        with self.assertRaises(HO.Refused) as c:
            await self.open(**kw)
        self.assertEqual(c.exception.rule, rule)
        if self.pages:
            self.assertTrue(self.pages[0].closed)
            self.assertEqual(self.bb.released, ["s1"])
        return c.exception

    async def test_a_card_rate_is_never_handed_over(self):
        e = await self.refused("card_rate", rate="Non-Refundable Rate")
        self.assertIn("book.php?apikey=", e.say)                 # the hotel's own page offered instead

    async def test_terms_read_when_the_rate_was_offered_are_used_while_fresh(self):
        GC.RATE_TERMS[(GC._engine_key(ENGINE), "Standard Rate")] = (HO.CLOCK(), NONREF)   # what the offer said, minutes ago
        await self.refused("card_rate")
        GC.RATE_TERMS[(GC._engine_key(ENGINE), "Standard Rate")] = (HO.CLOCK() - GC.TERMS_FRESH - 1, NONREF)   # stale: read again
        self.pages.clear(); self.bb.released.clear(); self.bb.created.clear()
        rec = await self.open()
        self.assertEqual(rec["state"], "ready")

    async def test_the_summary_must_name_the_guests_rate(self):
        FakeEngine.summary_for = "Family Suite City View Non-Refundable Rate To be paid €296.00"
        await self.refused("wrong_rate")

    async def test_an_unknown_rate(self):
        await self.refused("rate_not_found", rate="Breakfast Rate")

    async def test_payment_on_the_details_page(self):
        FakeEngine.pay_frames = ["https://js.stripe.com/v3/elements-inner-card.html"]
        await self.refused("payment_step")

    async def test_a_field_that_did_not_take(self):
        FakeEngine.stubborn = {"zip-code"}
        await self.refused("not_all_prefilled")

    async def test_missing_information_is_asked_before_any_session(self):
        g = dict(GC.FICTIONAL, address="")
        e = await self.refused("missing_info", guest=g)
        self.assertIn("address", e.say)
        self.assertEqual(self.bb.created, [])

    async def test_a_custom_question_without_an_answer(self):
        FakeEngine.custom = [{"name": "6650712BB2249", "label": "Check-in Time", "value": ""}]
        g = dict(GC.FICTIONAL)
        g.pop("arrival_time")

        original = FakeEngine.read_guest

        async def read_guest(self_):
            out = await original(self_)
            out["fields"].append({"name": "6650712BB2249", "type": "text", "value": self_.values.get("6650712BB2249", ""),
                                  "checked": False, "autocomplete": "off", "label": "Check-in Time"})
            return out
        with mock.patch.object(FakeEngine, "read_guest", read_guest):
            await self.refused("not_all_prefilled", guest=g)

    async def test_real_guests_wait_for_the_dpa(self):
        with self.assertRaises(HO.Refused) as c:
            await GC.open_gc_handover(engine_url=ENGINE, stay=STAY, rate="Standard Rate", room=None, guest=dict(GC.FICTIONAL),
                                      hotel="x", account="a", read_only=False, fictional=False)
        self.assertEqual(c.exception.rule, "no_dpa")

    async def test_a_marketing_page_is_not_the_engine(self):
        with self.assertRaises(HO.Refused) as c:
            await GC.open_gc_handover(engine_url="https://www.smallportuguesehotels.com/en/property-details/emporium-lisbon-suites",
                                      stay=STAY, rate="Standard Rate", room=None, guest=dict(GC.FICTIONAL), hotel="x",
                                      account=None, read_only=True, fictional=True)
        self.assertEqual(c.exception.rule, "not_the_engine")


class Pressed(Base):
    async def test_read_only_stops_book_now(self):
        rec = await self.open()
        _, on_press, ro, _ = self.pages[0].watching
        self.assertTrue(ro)
        on_press("Book Now")
        await asyncio.wait_for(rec["_watch"], 2)
        self.assertEqual(rec["state"], "read_only_stopped")

    async def test_live_confirmation_is_booked(self):
        rec = await self.open(read_only=False)
        on_tap, on_press, _, on_nav = self.pages[0].watching
        on_tap("accept-terms"), on_tap("Book Now"), on_press("Book Now")
        await asyncio.wait_for(rec["_watch"], 2)
        self.assertEqual((rec["state"], rec["reference"], rec["taps"]), ("booked", "GC-4411-PT", 2))
        self.assertTrue(rec["say"].startswith("✅ Booked — Emporium Lisbon Suites, ref GC-4411-PT"))

    async def test_a_card_page_after_book_now_ends_the_session(self):
        rec = await self.open(read_only=False)
        self.pages[0].answer_page = {"url": "x", "text": "Payment", "frames": ["https://js.stripe.com/v3/x"], "fields": []}
        _, on_press, _, _ = self.pages[0].watching
        on_press("Book Now")
        await asyncio.wait_for(rec["_watch"], 2)
        self.assertEqual(rec["state"], "card_page")
        self.assertEqual(self.bb.released, ["s1"])
        body = (await HO.view(rec["id"], rec["token"])).body.decode()
        self.assertIn('let state = "card"', body)
        self.assertIn("Open the hotel&#8217;s page", body)

    async def test_the_page_asks_for_two_taps(self):
        rec = await self.open()
        rec["rehearsal_view"] = True
        body = (await HO.view(rec["id"], rec["token"])).body.decode()
        self.assertIn("Tick <b>&#8220;I accept the Terms&#8221;</b>, then press <b>&#8220;Book Now&#8221;</b>", body)
        self.assertIn("Rehearsal: the last press is blocked", body)
        self.assertIn('<span class="chip">Standard Rate</span>', body)


if __name__ == "__main__":
    unittest.main()
