"""Sasha 206 (EU 186, docs/sasha/whatsapp-architecture.md §4) · WhatsApp correctness — offline, the real WhatsApp turn and the
real state store (get_state is NOT faked: test_s159 faked it, which is how R1 went unseen).

  R1 · after a guest writes, the payment result reaches them on WhatsApp, from the number they wrote to — the number is
       saved with their state (last_to), and survives a save and a reload
  R2 · the same Twilio MessageSid twice runs ONE turn

    cd backend && python -m unittest tests.test_whatsapp_r1_r2_s206 -v
"""
from __future__ import annotations

import unittest

from booking_signer import guest_whatsapp as GW, paid_watch as PW
from tests import test_guest_whatsapp_s75 as TG

run = TG.run


class R1PaymentResultReachesThePhone(TG.Base):
    def test_last_to_is_kept_and_the_payment_result_is_sent_from_it(self):
        self.link()
        self.say("hi")                                                          # the guest writes (to the sandbox number)
        st = run(GW.STORE.get_state(GW.wa_key(TG.GUEST)))                       # the REAL store, saved and read back
        self.assertEqual(st.get("last_to"), TG.SANDBOX)
        n = len(GW.SENDER.sent)
        run(PW._tell(TG.ACCOUNT, {"say": "✅ Booked — everything's in your itinerary."}))
        sent = GW.SENDER.sent[n:]
        self.assertEqual([(s["from"], s["to"], s["body"]) for s in sent],
                         [(TG.SANDBOX, TG.GUEST, "✅ Booked — everything's in your itinerary.")])

    def test_without_last_to_it_still_goes_from_the_guest_sender(self):
        self.link()
        self.say("hi")
        st = run(GW.STORE.get_state(GW.wa_key(TG.GUEST)))
        run(GW.STORE.put_state(GW.wa_key(TG.GUEST), {**st, "last_to": None}))  # as before 034: nothing kept
        n = len(GW.SENDER.sent)
        run(PW._tell(TG.ACCOUNT, {"say": "✅ Booked"}))
        self.assertEqual([s["from"] for s in GW.SENDER.sent[n:]], [GW.sender_for({})])


class R2NoTurnTwice(TG.Base):
    def test_a_repeated_message_sid_runs_one_turn(self):
        self.link()
        turns = []
        real_spawn = GW._spawn

        def spawn(coro):
            turns.append(1)
            coro.close()
        GW._spawn = spawn
        try:
            p = {"MessageSid": "SM" + "a" * 32, "From": f"whatsapp:{TG.GUEST}", "To": f"whatsapp:{TG.SANDBOX}", "Body": "hi"}

            async def not_a_venue(_):
                return None
            self.assertEqual(run(GW.dispatch(p, not_a_venue)), "")
            self.assertEqual(run(GW.dispatch(dict(p), not_a_venue)), "")        # Twilio's retry
            self.assertEqual(len(turns), 1)
            run(GW.dispatch({**p, "MessageSid": "SM" + "b" * 32}, not_a_venue))  # a new message: its own turn
            self.assertEqual(len(turns), 2)
        finally:
            GW._spawn = real_spawn


if __name__ == "__main__":
    unittest.main()
