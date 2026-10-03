"""CR 10 · ONE SASHA, NOT ROOMS: CampusMe, relocation and health are skills inside one conversation. A message that isn't
the product's goes to Sasha's own flow, in the same chat, with the product's context; the product resumes where it was.
No "Say EXIT" anywhere. Offline; the real WhatsApp turn; the model is never called.

    cd backend && python -m unittest tests.test_one_sasha_cr10 -v
"""
from __future__ import annotations

import json

from booking_signer import guest_whatsapp as GW
from products import store as ST, whatsapp as PW
from tests import test_guest_whatsapp_s75 as TG

run = TG.run


class OneSasha(TG.Base):
    def setUp(self):
        super().setUp()
        self.saved = ST.STORE
        ST.STORE = ST.MemoryCaseStore()
        self.link()

    def tearDown(self):
        ST.STORE = self.saved
        super().tearDown()

    def said(self):
        return "\n".join(self.bodies() + [b for b, _ in GW.SENDER.contents])

    def st(self):
        return run(GW.STORE.get_state(GW.wa_key(TG.GUEST)))

    def to_passport(self):
        for t in ("relocation", "first", "me", "myself"):
            self.say(t)
        self.assertEqual(self.bodies()[-1], "Your passport number?")

    def test_relocation_then_flights_then_back_to_relocation(self):
        self.to_passport()
        n = len(GW.SENDER.sent)
        self.say("book me flights to Madrid on 1 March")
        sasha = "\n".join(s["body"] for s in GW.SENDER.sent[n:])
        self.assertEqual(sasha, GW.ASK_ONE)                                   # Sasha's own flow answered, in the same chat
        self.assertIsNone(self.st()["pending"])                               # her pending is hers again
        self.assertNotIn("Relocation", json.dumps(self.st()["history"], ensure_ascii=False))   # never in her history
        self.assertEqual(run(PW.context(GW.wa_key(TG.GUEST)))["city"], "Madrid")              # read-only, for her parsers
        self.say("EXAMPLE000")                                                # an answer to relocation's own question
        self.assertEqual(self.bodies()[-1], "Your first surname, exactly as on your passport?")
        self.assertEqual(self.st()["pending"]["facts"]["applicant"]["passport_number"]["value"], "EXAMPLE000")

    def test_the_keyword_alone_says_where_we_were(self):
        self.to_passport()
        self.say("I need a flight from London to Madrid on 1 March")
        self.say("relocation")
        self.assertEqual(self.bodies()[-1], "Back to your EX-01. Your passport number?")

    def test_sashas_own_question_keeps_its_answers(self):
        self.to_passport()
        self.say("dinner for 2 in Chamberí on Saturday at 21:00")            # Sasha: cards, her own pending
        self.assertEqual(self.st()["pending"]["kind"], "cards")
        self.say("1")                                                         # her card, not a passport number
        self.assertNotIn("first surname", self.bodies()[-1])
        self.assertIn("/api/booking/venues/read", self.api_paths())
        self.say("relocation")                                                # and relocation is exactly where it was
        self.assertEqual(self.bodies()[-1], "Back to your EX-01. Your passport number?")

    def test_a_product_answer_is_never_taken_by_sasha(self):
        self.to_passport()
        self.say("not a passport!")                                           # not a passport number: relocation re-asks
        self.assertIn("letters and digits", self.bodies()[-1])
        self.assertNotIn("/api/booking/venues/find", self.api_paths())

    def test_context_is_minimum_necessary(self):
        self.to_passport()
        for a in ("EXAMPLE000", "Ejemplo", "NONE", "Ana"):
            self.say(a)
        self.say("book me flights")
        c = run(PW.context(GW.wa_key(TG.GUEST)))
        self.assertEqual((c["product"], c["city"], c["country"], c["name"]), ("relocation", "Madrid", "Spain", "Ana Ejemplo"))
        self.assertNotIn("EXAMPLE000", json.dumps(c))                         # never a passport fact
        self.assertNotIn("Ana", json.dumps(self.st()["history"], ensure_ascii=False))

    def test_no_wall_anywhere(self):
        self.to_passport()
        self.say("what's the weather like")                                   # neither relocation's nor a booking: re-asked
        self.say("campus")
        self.say("salud")
        self.assertNotRegex(self.said(), r"(?i)say exit|go back to sasha")

    def test_health_hands_sasha_only_the_city(self):
        self.say("health I need a doctor this week")
        self.say("", payload="hx:consent:yes")
        self.say("", payload="hx:priv")
        self.say("cancel my dinner at Botavara")                              # Sasha's: a cancellation
        c = run(PW.context(GW.wa_key(TG.GUEST)))
        self.assertEqual((c["product"], c["city"]), ("health", "Madrid"))
        self.assertNotRegex(json.dumps(c, ensure_ascii=False), r"(?i)doctor|médico|gp|appointment")


class OneItinerary(TG.Base):
    """What the person booked THEMSELVES joins their itinerary as guest_booked (the Sasha tab's rules)."""

    def setUp(self):
        super().setUp()
        from products import itinerary as IT
        self.IT, self.saved = IT, (ST.STORE, IT.guest_booked)
        ST.STORE = ST.MemoryCaseStore()
        self.added = []

        async def fake(account, **kw):
            self.added.append(kw)
            return "item-1"
        IT.guest_booked = fake
        self.link()

    def tearDown(self):
        ST.STORE, self.IT.guest_booked = self.saved
        super().tearDown()

    def test_the_consulate_and_tie_appointments(self):
        for t in ("relocation", "DEMO", "SIGNED", "UK", "SKIP", "1 March 2027"):
            self.say(t)
        self.say("show my receipts")                                           # Sasha in between… (CR 13: "book me flights" is a plan now)
        self.say("consulate booked 12 November 10:00")                         # …and relocation picks it up
        self.say("TIE appointment booked 20 March 2027 at 9:30")
        a, b = self.added
        self.assertEqual((a["type_"], a["provider_name"], a["at"], a["tz"]), ("visa", self.IT.CONSULATE, "10:00", "Europe/London"))
        self.assertEqual((b["provider_name"], str(b["on"]), b["tz"]), (self.IT.TIE, "2027-03-20", "Europe/Madrid"))
        self.assertIn("booked by you. I'll remind you the day before", self.bodies()[-1])

    def test_a_sermas_appointment_only_on_an_explicit_yes(self):
        self.say("salud")
        self.say("", payload="hx:consent:yes")
        self.say("", payload="hx:pub")
        self.say("I booked it for Tuesday 6 October 10:00")
        self.assertEqual(self.added, [])                                        # nothing before the yes
        self.assertIn("kept with your bookings like any other — not just 30 days", GW.SENDER.contents[-1][0])
        self.say("", payload="hx:sermas:yes")
        (a,) = self.added
        self.assertEqual((a["type_"], a["provider_name"], a["at"]), ("doctor", self.IT.SERMAS, "10:00"))

    def test_no_means_nothing_kept(self):
        self.say("salud")
        self.say("", payload="hx:consent:yes")
        self.say("", payload="hx:pub")
        self.say("booked 6 October 10:00")
        self.say("", payload="hx:sermas:no")
        self.assertEqual(self.added, [])


class Reminders(TG.Base):
    """GET /api/booking/products/reminders: the account's own dated reminders, to come, never another account's."""

    def setUp(self):
        super().setUp()
        self.saved = ST.STORE
        ST.STORE = ST.MemoryCaseStore()

    def tearDown(self):
        ST.STORE = self.saved
        super().tearDown()

    def get(self, account):
        from fastapi import FastAPI, Request
        from fastapi.testclient import TestClient
        from products import routes as PR
        app = FastAPI()

        @app.middleware("http")
        async def who(request: Request, call_next):
            request.state.account = account
            return await call_next(request)
        app.include_router(PR.router)
        return TestClient(app).get("/products/reminders").json()["reminders"]

    def test_own_upcoming_reminders_only(self):
        other = "33333333-3333-4333-8333-333333333333"
        run(ST.STORE.put("relocation", TG.ACCOUNT, "w", {"after": {"reminders": [
            {"on": "2000-01-01", "text": "past", "sent": True}, {"on": "2099-01-01", "text": "apply from today", "sent": False}]}}))
        run(ST.STORE.put("health", TG.ACCOUNT, "w", {"reminders": [{"on": "2098-01-01", "text": "volante", "sent": False}]}))
        run(ST.STORE.put("health", other, "w", {"reminders": [{"on": "2098-01-01", "text": "not yours", "sent": False}]}))
        rs = self.get(TG.ACCOUNT)
        self.assertEqual([(r["on"], r["text"], r["product"]) for r in rs],
                         [("2098-01-01", "volante", "health"), ("2099-01-01", "apply from today", "relocation")])
