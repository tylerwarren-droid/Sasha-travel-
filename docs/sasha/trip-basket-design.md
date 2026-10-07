# Sasha 197 C · Flights + stays as ONE trip — the trip basket

Report only. No code has been written for this. It needs the founder's approval before any of it is built.
Written 7 Oct 2026 from the code as it stands at `311fea2`.

## 1 · Every current path, and where they collide

| # | Path | Where it lives | Holds its state in |
|---|---|---|---|
| P1 | **Plan JSON.** The itinerary builder writes days, hotels, activities and the estimate. | `itinerary_agent.build_itinerary` → `plan_store.save` | `trips` row (the plan JSON); `chosen_flight` is a key inside it (196) |
| P2 | **Hotel cards.** Each hotel is a name in the plan. The price is the *plan's estimate*. | plan JSON `days[].hotel` | the plan JSON only |
| P3 | **Hotel "reserve" (TEST).** | `hotel_test.py` | a placeholder price `SASHA_TEST_HOTEL_EUR` (default 120/night); a `TEST-` ref in `trip_items` |
| P4 | **Duffel search, conversational.** | `app/services/duffel.py` (`search_flights_from_text`, `_normalise_offer`, `card_has_live_offer`) | the chat card (`bookings[]`), no store |
| P5 | **Duffel search and order, booking.** | `booking_signer/travel.py` (`search`, `card_of`, `order`, `refreshed`) | in memory: `OFFER_ROUTE`, `USED_LISTS` |
| P6 | **Pick readers.** | `flight_pick.pick` (single-flight read-back: `flight_pick`); the conductor's guided block (196: `trip_pick` → `PS.choose_flight`) | the chat history, plus `chosen_flight` in the plan |
| P7 | **Single-flight book.** | `travel.prepare` / `travel.pay` → `FlightBookTest.tsx` | in memory: offer id; `paid_watch` row |
| P8 | **Bundle "book it".** | `trip_book.bundle` / `prepare` / `pay` → `TripBookTest.tsx` | in memory: `_QUOTES[account]`, `_BOOKED[sid]` |
| P9 | **Stripe checkout (TEST).** | `test_deposit` (session); `paid_watch.remember` | a `paid_watch` row with the payload |
| P10 | **After payment.** | `paid_watch.settle` → `travel.order` or `trip_book.book_paid` | `trip_items` rows (`T.RECORD`, `HT.RECORD`) |
| P11 | **Venue bookings** (restaurant, spa), via the ladder. | `ladder_routes`, `guest_whatsapp` | `trip_items` with `trip_id` |
| P12 | **Itinerary panel.** | `plan_store.merge(plan, bookings)` → `TripPanel.tsx` | the plan JSON and `trip_items` combined at read time |

### Where they collide

1. **Two Duffel clients** (P4 and P5). They have two offer shapes (`_normalise_offer` and `card_of`) and two expiry checks (`card_has_live_offer` and `refreshed`). A pick made from P4's card has to be translated into P5's card before booking.
2. **Three "chosen flight" notions:**
   - `flight_pick` (single read-back, P6/P7);
   - `trip_pick` → `plan.chosen_flight` (P6);
   - `_QUOTES[account].flights` (P8).
   
   The bundle re-reads `chosen_flight`, and when it is missing it searches again. That re-search is how "the flight I picked" and "the flight booked" can differ. The 196 fix narrows the gap but does not close it.
3. **In-memory state that a deploy wipes:** `_QUOTES`, `_BOOKED`, `OFFER_ROUTE`, `USED_LISTS`. `paid_watch` persists the payload, but `book_paid` reads `_QUOTES` first. After a restart between "yes" and the payment, the answer is *"this server no longer holds what was paid for"*.
4. **Two hotel prices:** the plan's estimate (P2) and the TEST placeholder (P3). The total said in chat and the per-night TEST price come from different sources.
5. **Passengers are placeholders.** `PLACEHOLDERS = born_on 1980-01-01, title mr, gender m`. The name comes from `/api/booking/contact`, not from the intake. Nothing is ever asked.
6. **Two checkouts for one trip.** A single-flight read-back (P7) and the bundle (P8) can both be open for the same flight, and `LIST_USED` exists only to stop that.
7. **The itinerary is computed, not owned.** `merge` joins the plan with `trip_items` at read time, so an item's state (suggested, chosen or booked) is inferred from three places. The ✕ / remove path has to edit all three.
8. **No Duffel webhooks.** After the order, nothing updates a schedule change or a cancellation.

## 2 · ONE trip basket

**One table, `trip_basket_items`, keyed by `trip_id`.** The conversation and every surface act on it alone.

| Field | Meaning |
|---|---|
| `id`, `trip_id`, `account` | identity |
| `kind` | `flight` · `stay` · `venue` (restaurant, spa, activity) |
| `state` | `suggested` → `chosen` → `pending_payment` → `booked` (also `failed` and `cancelled`) |
| `day`, `start`, `end`, `party` | when, and for how many |
| `provider`, `provider_ref` | `duffel` + offer id (or order id once booked); `test_hotel`; `ladder` |
| `snapshot` | what was shown: airline, flight numbers, slices, times, price and currency, `expires_at` |
| `price_eur`, `price_source` | `quoted` (provider) · `estimate` (AI estimate, labelled) · `placeholder` (TEST) |
| `booking_reference`, `paid_session` | set at booking |

### Rules

- **The plan builder writes `suggested` items:** hotels as stays, and activities. The plan JSON keeps only the narrative (days, notes).
- **A pick** ("the Iberia one", the Choose button, "book Casa Alberto") moves exactly one item to `chosen`. A new flight pick replaces the previous chosen flight on the same slice. It is never a second one.
- **"Book it"** prices the `chosen` items (plus the `suggested` stays the guest kept), shows ONE total, and creates ONE Stripe session. It writes `pending_payment` with the session id **into the rows**, not into memory.
- **Payment settled** → each item is booked by its provider → `booked` + reference, or `failed` + reason, item by item.
- **The itinerary panel renders the basket.** Its state decides the badge: suggested, chosen, "TEST · booked (demo)", booked. Its ✕ deletes one row.
- **The conductor never searches to answer "book it".** It reads the basket. A search happens only when the guest asks for flights or the chosen offer has expired (see §3).

**What this removes:** `_QUOTES`, `_BOOKED`, `OFFER_ROUTE`, `USED_LISTS`/`LIST_USED`, `plan.chosen_flight`, the single-flight vs bundle split (a single flight is a basket of one), and `merge`.

## 3 · Duffel as the flight backbone

1. **The offer request comes from the intake.** Origin (asked), destination and dates (plan), and passenger count (asked) give `POST /air/offer_requests`. The offer request id is stored on the trip.
2. **Offers are stored as `suggested` flight items:** offer id, slices, segments, owner, price and `expires_at`. Only the ones shown are stored, at most 8.
3. **Pick** → `chosen`.
4. **At "book it":** `GET /air/offers/{id}`.
   - If the offer is live and the price is the same, it stays.
   - If it has expired or the price changed, re-search the same route and day, then **keep the choice**: the same owner and flight numbers, matched by marketing carrier and flight number per segment.
   - If the same flight is found, the item is updated in place. A price difference is said before payment.
   - If it has gone, say so and offer the nearest one. Never swap silently.
5. **Passengers:**
   - The name comes from the intake (197 B now asks it). Duffel needs given and family name, so the family name is asked once if missing.
   - Date of birth, title and gender (plus passport only where `passenger_identity_documents_required`) are asked **once**, at the first "book it".
   - They are saved to a `travellers` table per account (name, DOB, title, gender, document fields optional), with each companion as a row, and reused after that.
   - The placeholders are removed for live mode. They stay for TEST runs only, marked as such.
6. **One Stripe payment** for the whole basket (flights, stays and anything else priced).
7. **Duffel order** per flight item (`type: instant`, balance payment). The `booking_reference` and order id are written to the row.
8. **Duffel webhooks:**
   - `order.updated`, `order.airline_initiated_change_detected` and `order.cancelled` → `POST /travel/duffel/webhook`;
   - the signature is verified with `X-Duffel-Signature`;
   - the row is updated, and the guest is told on WhatsApp.

### Duffel Stays — assessment

- Duffel Stays (`/stays/search` → `/stays/quotes` → `/stays/bookings`) fits the basket exactly: the same auth, the same balance payment, the same webhook family. It would replace the TEST hotel (P3) and its placeholder price with a quoted rate.
- **Status:** access was requested of Duffel on 3 Oct (see `hotel_test.py`). It is not enabled on our account. Every hotel booking stays a labelled TEST until it is.
- **Gaps to check once enabled:**
  - coverage of the plan's named hotels in Vietnam: the plan names a hotel, and Stays may not carry it, so the basket must allow "closest available" with the guest's OK;
  - cancellation policies, which must be shown at read-back;
  - rate expiry, which is like offers.

### Access needed

| What | Who | Variable / where |
|---|---|---|
| Duffel Stays enabled on the account (test, then live) | founder ↔ Duffel | same `DUFFEL_*` token |
| Duffel webhook endpoint + secret | founder sets the secret | `DUFFEL_WEBHOOK_SECRET` (Railway) |
| Duffel **live** token (only at go-live) | founder | `DUFFEL_LIVE_TOKEN` (name to be confirmed) |
| Duffel balance top-up for live orders (balance payments) | founder | Duffel dashboard |
| Stripe live keys (only at go-live) | founder | existing Stripe variable names |
| Migration for `trip_basket_items` + `travellers` | drafted here, applied by the founder | SQL file under `docs/sasha/` |

## 4 · The gating suite, and the replacement steps

### BASKET suite (added to `scripts/gate.py`, scratch guest, Duffel TEST)

1. The intake (name → kind → how many → from) produces an offer request with the right origin, dates and passenger count.
2. The plan gives `suggested` stays; the flights shown give `suggested` flight items; nothing is `chosen`.
3. "The Iberia one" → exactly one `chosen` flight. Then "actually the BA one" → still exactly one, the BA one.
4. "Book it" → ONE total, equal to the sum of the basket rows, with the chosen flight named. No search happens if the offer is live.
5. **Expired offer:** force `expires_at` into the past. "Book it" re-searches, keeps the same flight numbers, and says the price change if there is one.
6. **Restart between "yes" and the payment:** clear in-process state, then settle. Everything is still booked, read from the rows.
7. **Passengers:** the first "book it" asks DOB etc. once, and a second trip does not ask again.
8. After payment, every item is `booked` with a reference. A refused flight is `failed` with its reason, and the rest are still booked.
9. **Webhook:** a signed TEST `order.cancelled` → the row is `cancelled` and the panel shows it.
10. **✕** on a basket item deletes that row only; the total updates.
11. The existing W1–W4, V1, GUIDED, ITIN and SPACES checks stay green throughout.

### Replacement steps (each one ships behind the suite; effort in working sessions)

| Step | What | Effort |
|---|---|---|
| R1 | Migration draft: `trip_basket_items`, `travellers` (SQL file for the founder) | 0.5 |
| R2 | Basket store module plus the BASKET suite skeleton (cases 1–4 red) | 1 |
| R3 | Plan builder writes stays as items; the panel renders from the basket (`merge` retired behind a switch) | 1 |
| R4 | One Duffel client: fold `app/services/duffel.py` into `travel.py`'s card shape; offers stored as items | 1 |
| R5 | Pick readers write `chosen` (`flight_pick`, `trip_pick`, ladder); `chosen_flight` retired | 1 |
| R6 | "Book it" from the basket: re-validate or keep the choice; one Stripe session; rows carry `pending_payment` (`_QUOTES` / `_BOOKED` retired) | 1.5 |
| R7 | Passengers asked once and saved; placeholders only in TEST | 1 |
| R8 | Duffel webhooks (needs `DUFFEL_WEBHOOK_SECRET`) | 0.5 |
| R9 | Duffel Stays behind `provider()`, once Duffel enables it | 1.5 |
| R10 | Remove the dead paths (P7's separate checkout, `USED_LISTS`); the suite stays the gate | 0.5 |

**Total:** about 9.5 working sessions. R9 waits on Duffel; everything else can start on approval. R1's SQL is drafted, never applied by this tab.

## 5 · Sasha 198: approved, with conditions. The AgAPI roles

The founder approved this on 7 Oct, with conditions. Every write to the basket is made by one of four roles, named in code (`basket.py`'s `ROLE`) and on each event:

| Role | Job | In the basket |
|---|---|---|
| **Magellan** | search: Duffel offer requests, hotel search (Duffel Stays once enabled), Places | writes `suggested` items: the offers shown and the plan's stays |
| **Sherlock** | details and validation: offer details, expiry, price re-check, the venue's route (the ladder's read) | refreshes `snapshot`, `expires_at`, price; keeps the choice on a re-search |
| **Austen** | booking after the guest's yes: Stripe checkout → Duffel order, hotel booking, the ladder | `chosen` → `pending_payment` (with `paid_session`), then calls the provider |
| **Pacioli** | proof and truth: order references, Duffel webhooks, platform emails | the only writer of `booked`, `failed`, `cancelled`, `booking_reference`, `status_line`; records every event in `basket_events` |

**The model never writes a booked or paid line.** Sasha reads Pacioli's `status_line` aloud.

### Conditions

1. **One Duffel client.** Quotes and choices are persisted; nothing is held in memory.
2. **Real passengers.** The name comes from the intake, the rest is asked once, and both are saved in `saved_passengers`.
3. **Webhooks wired.**
4. **The guided conversation acts only on the basket.** The old pick readers and bundle stitching are removed once their replacements pass.
5. **The same behaviour on web, avatar and WhatsApp.** BASKET suite cases run on all three.
6. **No other changes** while R1–R10 run.

### Webhook secret

| | |
|---|---|
| Variable | `DUFFEL_WEBHOOK_SECRET` |
| Where | Railway, the backend service (sasha-travel-production) |
| How it is obtained | Duffel returns the secret once, when the webhook is created (`POST /air/webhooks`, url `https://sasha-travel-production.up.railway.app/travel/duffel/webhook`). At R8 this tab creates the webhook with the existing TEST token and sets the secret via the Railway CLI without printing it. If the founder prefers to create it in the Duffel dashboard, he gives the value and the tab sets it. |

### Access request

The Duffel Stays email to send is drafted in `docs/sasha/duffel-stays-access-request.md`.

### Migration

`backend/booking_signer/sql/033_trip_basket.sql` creates `trip_basket_items`, `saved_passengers` and `basket_events`. It is a draft; the founder runs it.

The existing `public.travellers` table is left untouched. Its FK points to `public.users`, which has 0 rows.
