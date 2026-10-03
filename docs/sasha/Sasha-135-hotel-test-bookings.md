# Sasha 135: hotel "Reserve" is back, as a TEST booking

*3 Oct 2026. Commits 7ea42d1, ea37ac3 and 75e4a84 (the last is held for the gate, see the end). 937 tests OK. The founder's rule: add, never
remove or downgrade a capability without his OK.*

## 1. What a guest sees now

**WhatsApp:** "a hotel in Hoi An, Vietnam from 14 to 16 November for 2"
1. **Photo cards from Google.**
   - Opener: "Hotels for 2 nights from Saturday 14 November, 2 people. For the one you pick: a TEST booking (no hotel
     contacted), or a real request to the hotel."
2. **Pick → two buttons: "Test booking" or "Request from hotel".**
3. **Test booking → the read-back:**
   - "⚠ Test booking: no hotel contacted — nothing is reserved at …, and nothing is charged."
   - The dates, nights and people.
   - "Test price €240.00 (2 × €120) — a placeholder, not the hotel's rate".
   - Payment by one touch on Stripe's TEST page.
   - "It goes in your itinerary and calendar marked as a TEST booking, with a TEST- reference."
4. **Yes → one touch on Stripe's TEST page** (Apple Pay or the phone's saved card; nothing charged).
5. **Only when Stripe records it paid:** "🧪 Test booking: no hotel contacted: …, Reference TEST-XXXXXX. It's in your
   itinerary and calendar marked TEST — nothing was reserved or charged."
6. **Request from hotel → the real path, as before:**
   - The hotel's own route, usually its email (see the fix in §3).
   - The yes now reads: "Email ARTIEM Madrid to ask for a room for 2, Tuesday 20 October for 2 nights? It's a
     request — nothing is booked until they reply."

**Web:**
- Every hotel card has **"Reserve (TEST)"**: check-in, nights and people → the same read-back → Yes → Stripe's TEST
  page → the same TEST booking.
- The old trip-plan button is **kept**, renamed "Save · $X" (it saves to the trip; nobody is contacted).
- **Nothing was removed.**

**Never "confirmed":** the TEST label appears in the bookings list ("Test booking: no hotel contacted"), the calendar
event ("TEST booking — no hotel or provider was contacted; nothing is reserved"), the morning brief ("(TEST booking)"),
and the booking's own name.

**Reset:** "Reset the demo" cancels TEST hotel bookings too.

**Switching to real:**
- When Duffel Stays (requested from help@duffel.com) or RateHawk credentials arrive, `hotel_test.provider()` is where
  the same flow becomes a real booking.
- That real step is not built yet; it needs the provider first.

## 2. Rehearsals: founder's account, WhatsApp simulated, then the web

| Beat | Rehearsal 2 |
|---|---|
| Hoi An: cards (Tohe Riverside Lodge, Phước Linh, THE SAGA HOTEL) | 7.4 s |
| Pick → the two choices → Test booking → read-back | 1.2 s + 1.2 s |
| Yes → a **real** Stripe TEST checkout page | 2.1 s |
| TEST booking → on the desktop bookings list | **0.8 s** (the page polls every 8 s) |
| … → calendar event | 17–23 s |
| Madrid (ARTIEM): the same | list 0.9 s, calendar 12–29 s |
| Madrid: "Request from hotel" | the email read-back to madrid.recepcion@artiemhotels.com (from their website) — **stopped before any yes** |
| Web "Reserve (TEST)": Tohe (Hoi An), Hotel Urban (Madrid) | read-back → yes → a real Stripe TEST page → "awaiting payment" |

**Stood in:** the payment itself. The founder pays only when he says "send the test payment again", so the TEST
booking was recorded directly after the real payment page was made. This is labelled in the transcript
(`docs/business/demo-v5-hotels/rehearsal-transcript.txt`, redacted).

## 3. Defects the rehearsal found, fixed with tests

1. **"Request from hotel" stopped dead at hotels that publish only an email.** A guard written before the email route
   (Sasha 130) required a form, a link or a phone. Email-only venues of every kind now get their email route.
2. The opener still said hotels can't be booked.
3. The room request's yes read like a table booking ("Book X for 2 … at 15:00").

## Held

- Commit 75e4a84 (fix 3) is committed locally, but the gated push was blocked. The gate tests the shared working tree,
  where CR has unfinished edits in backend/products that fail 4 of its tests.
- I asked CR to tell me when it's green, and I'll push then.
