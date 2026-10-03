# Sasha 132: one-yes escalation, the travel demo

*3 Oct 2026.*
- **Commits:** b50300d, 5936ca2, dafec1f, bfbb15b.
- **Tests:** 932 OK.
- **Rehearsal:** WhatsApp simulated on the founder's account (his choice for this ticket); two runs. Transcripts are in
  `docs/business/demo-v4-travel/` (redacted).

## 0. Settings (done)

- Migration 031 verified live.
- On Railway:
  - `SASHA_TAP_ESCALATION=1`
  - `SASHA_COST_EMAIL_EUR=0.001`
  - `SASHA_COST_WHATSAPP_EUR=0.05`
  - `SASHA_COST_FORM_EUR=0`
- `SASHA_USD_EUR` is **not set**: calls (Bland's USD price) stay unknown in EUR, so the cost per confirmed booking stays
  unstated while there are calls. Set it or say leave it.
- **Still missing:** `STRIPE_TEST_SECRET_KEY` (the founder sets it) and the demo logins saved as
  demo-market.kanoe.ai / demo-spa.kanoe.ai.

## 1. One yes covers the escalation (founder's decision d)

**The first read-back says the plan:** "If you haven't booked on their page within 30 minutes, I'll email them; if they
don't reply within 24 hours, I'll call them. Your yes covers these steps — I'll ask you again only if something changes
(a new time, a deposit, a cost)."

**How the one-tap works now**
- It asks once ("Send me their page?").
- The page is made only after the yes, with the plan in its stored read-back. An email's read-back can carry it too.

**Later steps go out under `{how: "escalation_plan", from: link|email}`.**
- **The server verifies, from its own records,** that the cited yes:
  - belongs to this account;
  - was approved;
  - contains the plan line;
  - is for the same venue;
  - is under 7 days old.
- Anything else is refused, so a client can't send an email or place a call by merely claiming a plan.
- **What the engine then does:** emails or calls by itself, then tells the guest ("so — as you agreed — I've emailed
  them"). Without a plan, it still asks.
- **Tests:** 6.

## 2. The travel demo

| Beat | Works? | Evidence (rehearsal 2) |
|---|---|---|
| **Flights Madrid → Hanoi** (WhatsApp) | ✅ Duffel **TEST** | 3 cheapest as cards (BA / IB / Duffel Airways, about €370–385), 9.6 s |
| Pick → read-back | ✅ | Says TEST twice, plus the placeholders Duffel's test mode needs (birth date, title, gender), 5.7 s |
| Yes → **one-touch test payment** | ⛔ **blocked** | No `STRIPE_TEST_SECRET_KEY`: "I can't take the test payment yet … Nothing was booked." |
| Duffel TEST order → itinerary → calendar | ✅ (payment stood in) | Order C2ATO3 (rehearsal 1). In the desktop's bookings list after **0.9–2.2 s** (the page polls every 8 s). Calendar event after **17–20 s**. |
| **Web "Book it (TEST)"** on a Duffel card | ✅ up to payment | Read-back of 5 lines, bound to its hash. The pay step refuses honestly without the key. Vercel deploy not verified from here. |
| **Hoi An hotel** | ⚠ request only | Duffel Stays **403 "not enabled for your account"**; RateHawk **has no credentials**. So: photo cards (Tohe Riverside Lodge …), then the room is requested from the hotel (new room email, en/es). The first pick publishes only a phone (calls off), so "Nothing was sent". Pick one with an email. |
| **Restaurants in Hoi An** | ✅ | Cards. The test venue stands in, booked by its form in 24 s. Your test-club loyalty number goes in too. |
| **Madrid next week: restaurant + spa** | ✅ | Two bookings on one yes, 66 s end to end |
| **"Where am I on 13 November?"** | ✅ WhatsApp **and** web | "Your last flight before then goes to Hanoi …" (WhatsApp 3.9 s, web 0.9 s) |
| **"Do I have time to drive from Madrid to Toledo 13–18?"** | ✅ after a fix | "Yes: 1h 02m each way by car (Routes API) … 176 min there." |
| **"Do I have time to fly Madrid → Lisbon 9–14?"** | ✅ after a fix | "Yes — Air Europa UX 1153 10:25 → 10:45 … 9 flights fit" (Duffel TEST) |

**Hard rules**
- A **live** Duffel or Stripe key is refused.
- The Duffel test order is made **only after Stripe records the test payment**. The offer and price are re-checked
  first; a moved price books nothing.
- "Reset the demo" now also cancels TEST flights.

## 3. Defects the rehearsals found (all fixed with tests)

1. Our test **restaurant** was offered among the hotel cards.
2. A route-level import was missing. **No test reached that route**; one does now.
3. "Fly from Madrid **to Lisbon**" lost Lisbon; "drive **from** X" was ignored.
4. **Routes refused every driving request that had a departure time** (400: it must be traffic-aware). This latent
   defect also hit "time to leave" by car.
5. "Toledo" alone resolved to Ohio. Bare names now get their country.
6. "Do I have time to fly …" was taken as a flight search.
7. Time questions only looked at the 3 cheapest flights; now the whole schedule.

## 4. Not done, and why

- **The rehearsal on his iPhone and laptop.** As agreed, it ran with WhatsApp simulated; the desktop was proven through
  the same endpoint its page polls. The **one-touch payment** on the iPhone needs `STRIPE_TEST_SECRET_KEY`.
- **Instant hotel booking.** It needs Duffel Stays access (sales) or RateHawk sandbox credentials. Until then, a room
  is requested from the hotel, and said so.
- **Arrival times** for "do I have time to fly" are compared in the destination's local time (e.g. Lisbon is an hour
  behind Madrid).

## 5. For the founder

1. Set `STRIPE_TEST_SECRET_KEY` (sk_test_…), then tell me. I'll run the one-touch payment on your iPhone, with one live
   message.
2. Save the demo logins (demo-market.kanoe.ai, demo-spa.kanoe.ai) and a WhatsApp starting point.
3. Hotels: ask Duffel for Stays access or get RateHawk sandbox credentials, or keep "request from the hotel".
4. `SASHA_USD_EUR`: set it, or leave call costs in USD.
