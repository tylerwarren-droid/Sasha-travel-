# AgAPI as the engine: phase 2

*CR 69 · written 9 Oct 2026. This is the plan only; nothing in it has been started. Phase 1 is live on `cr/agapi-api`:*
- *Postgres;*
- *accounts per product;*
- *test and live keys;*
- *per-operation metrics;*
- *`magellan.read_site`;*
- *the provider adapters in `agapi_service/adapters.py`. Every live provider currently refuses with "live provider not connected yet".*

**Headline: in about 15 working days, Sasha's real providers sit behind AgAPI's adapters. S2 then calls AgAPI behind a
one-variable flip-back switch: shadow first, then reads, then acts. S1 is not touched.**

## The rules for phase 2

1. **S1 is untouched until Tyler's S1 talk.**
   - S1 and S2 share one engine. Today every S2 tool goes through `backend/agapi/v0.py` `call()` (~:1050), which S1 also uses.
   - So **the switch is never placed in `v0.call`.** It goes where the turn selects S2's tools: `backend/app/agent/sasha.py` `turn()`
     (:495, `S2.S2_TOOLS`), only when the surface is `s2`.
   - S1's fingerprint (commit 10471df, `docs/sasha/s2-front-door.md`) must stay green at every step.
2. **Test mode stays byte-for-byte.**
   - `CONNECTED_LIVE` gains a provider kind only when its live adapter passes its tests.
   - Test keys keep the simulated adapters.
3. **Live secrets never sit in the sandbox.**
   - Live mode runs as a **second Railway service, `agapi-live`**: the same image, its own variables, the same Postgres or a separate one
     (Tyler decides).
   - `agapi-sandbox` keeps test keys only and holds no provider secret.
4. **One switch, default off: `SASHA_S2_VIA_AGAPI`**, read where the turn selects S2's tools:
   - `0` (the default): S2 exactly as today.
   - `shadow`: S2 as today, and the read-only tools are also asked of AgAPI, with the differences logged. Nothing acts.
   - `reads`: searches come from AgAPI.
   - `1`: every S2 tool goes through AgAPI.
   - **Flip back = set it to `0`.** No deploy is needed beyond the variable change.
5. **No requests to booking platforms.** The ladder keeps every rung's own flag (`SASHA_FORMS_ENABLED`, `SASHA_CALLS_ENABLED`,
   `SASHA_EMAILS_ENABLED`) and allow-lists, unchanged.

## The steps

Each step follows the same pattern:
- **Adapter:** a live class in `agapi_service/adapters_live/<kind>.py` implements the phase-1 interface by calling Sasha's existing code.
  The code is imported, not copied: the AgAPI image already includes `backend/booking_signer`.
- **Tests:** Sasha's existing tests for that provider are re-run through the adapter, with their existing fakes.
- **Switch-on:** the kind is added to `CONNECTED_LIVE` on `agapi-live` only.

| # | Provider | Sasha's code the live adapter calls | Gaps found | Tests | Days |
|---|---|---|---|---|---|
| 1 | **Flights (Duffel)** | `booking_signer/travel.py`: `search` :123, `refreshed` :239 (re-check), `order` :158 (+ `_record` :185). Webhook: `duffel_webhook.py` `verify` :76, `handle` :93. AgAPI gets its own `/hooks/duffel`, which updates `acts`. | Sasha has **no Duffel order-cancel call**: cancellations only arrive by webhook. `trip.cancel` on a flight stays `not_cancellable` live until one is built and tested. `app/services/duffel.py` is an older adapter the agent doesn't use: leave it. | `test_duffel.py`, `test_travel_s132.py`, `test_trip_cr13.py`, `test_robustness_cr56.py` on `scripts/duffel_fake` | 2 |
| 2 | **Places (Google)** | `booking_signer/venue_read.py`: `find_venues` :697, `read_venue` :836, `locate` :618, `google_photo_uri` :820. | `travel.find_stays` has no real provider in Sasha besides `hotel_test`, so it stays not connected (named in the refusal). | `test_find_venues.py`, `test_places_terms.py`, `test_places_cost_s141.py` on `scripts/places_fake` | 1 |
| 3 | **Venue ladder** | The rung choice is `ladder.py` `choose` :65. The rungs:<br>- form: `form_rung.py` `prepare` :533, `send` :656<br>- page link: `ladder_routes.py` `/links` :881<br>- email: `prepare_email` :571, `send_email` :644<br>- phone (Bland): `call_routes.py` `prepare` :356, `place` :702<br>Cancel: `cancel_routes.py` `cancel_plan` :215, `cancel_go` :231. Today `backend/agapi/venues.py` `_book_inner` :359 reaches them through `GW.api`; the adapter calls the same in-process routes. | The ladder writes Sasha's own tables (`trip_items`, `guest_receipt.record` :127). The adapter must also write AgAPI's `acts` and evidence, the same act recorded twice. Decide which one is the record (recommended: AgAPI's, with Sasha's as a copy until S1 moves). | `test_booking_ladder.py`, `test_form_rung.py`, `test_ladder_s158.py`, `test_booking_calls.py`, `test_states_s157.py`, `test_stop.py` | 3 |
| 4 | **Payments (Stripe)** | The agent's stack is `booking_signer/test_deposit.py`: `checkout` :89, `link` :55, `session_paid` :143, `expire` :133. It settles by polling (`paid_watch.py` :177). AgAPI's `payment_link()` becomes the Stripe link, and `pay()` settles from `session_paid`. | There are two Stripe stacks. The legacy `app/api/payments.py` (`create_checkout` :186, webhook :384) has no tests and is **not** moved. The agent's stack uses `STRIPE_TEST_SECRET_KEY`; whether live AgAPI takes real money is Tyler's decision (a Stripe live key is a separate step). | `test_pay_here_220.py`, `test_deposit_s131.py`, `test_test_pay_page_s136.py`, `test_payments_s81.py` | 2 |
| 5 | **Email (Resend)** | `booking_signer/emailing.py`: `send` :271, `compose` :200, `act_address` :50. Inbound: `verify_svix` :300, `fetch_received` :321. | Resend's inbound webhook covers the whole account, so AgAPI must not take over Sasha's `/email/inbound` (`ladder_routes` :739). Replies keep landing in Sasha, which forwards each one it doesn't own to AgAPI. | `test_booking_ladder.py`, `test_ladder_s158.py`, `test_s2_221.py`, `test_followup.py` | 1 |
| 6 | **WhatsApp (Twilio)** | `guest_whatsapp.py` `Sender.send` (~:343, ContentSid :344), `deliver` :396, `TEMPLATES` :3018. S2 has its own raw call, `agapi/s2_whatsapp.py` `_twilio` :48. | One number, one webhook: Sasha's `/sms` (`inbound_phone.py` :229) stays the inbound, and replies reach AgAPI's `messages.replies` by a forward, never by moving the webhook. STOP is honoured on both sides. | `test_guest_whatsapp_s75.py`, `test_inbound_phone.py`, `test_whatsapp_r1_r2_s206.py`, `test_s2_cr62.py` | 1.5 |
| 7 | **Calendar** | `agapi/powers.py` `ics` :128, `calendar_links` :142 (already the same code as AgAPI's). Google sync: `booking_signer/calendar_sync.py` `sync_one` :295. | `.ics` and links connect straight away. Google Calendar sync (OAuth per person) is a separate, later step. | `test_s2_powers.py`, `test_calendar_s79.py` | 0.5 |

**Then S2 goes through AgAPI (S2 only):**

| # | Step | Files | Tests | Days |
|---|---|---|---|---|
| 8 | `agapi-live` service: the same image, Sasha's provider secrets, live keys for `sasha` only, `/metrics` watched | Railway (Tyler pastes the secrets); `agapi_service/config.py` (`CONNECTED_LIVE` from an env list) | Phase-1 suite + `test_cr69.py` + every adapter's tests | 1 |
| 8a | `backend/agapi/agapi_client.py` (new): POST `/v1/{op}` with the `sasha` live key, the envelope parsed into the same shape S2's tools return now | new file; no change to `v0.py` | `test_agapi_client.py` (new) on a fake AgAPI | 1 |
| 9 | **Shadow** (`SASHA_S2_VIA_AGAPI=shadow`): for S2 turns only, the read-only tools (`search_flights`, `search_venues`, `activity`) also ask AgAPI; differences are logged, nothing acts | `app/agent/sasha.py` around :495 (the S2 branch only); `app/agent/s2.py` | `test_s2_216.py`, `test_s2_221.py`, `test_s2_cr62.py`, `test_s2_powers.py` + a new test: with every value of the switch, an **S1** turn's tool path is byte-identical (the 10471df fingerprint) | 1 |
| 10 | **Reads** (`reads`), then **acts** (`1`): S2's tools through AgAPI | the same S2 branch | the S2 suites + flip-back: set to `0` mid-conversation and the next turn is S2 as today | 1.5 |
| 11 | **Rehearsal**: Tyler's phone S2 demo (`docs/sasha/s2-phone-demo.md`) on `1`, then on `0` | — | the demo twice, `/metrics` p95 per operation compared with today's | 0.5 |

**Total: about 15 working days** (7 providers ≈ 11, then the S2 switch ≈ 4). Steps 1–7 can run in any order. The ladder (3) and payments (4)
are the riskiest; do them early.

## For EU (1.3)

`magellan.read_site` is a Kanoe extension (`spec/ext/operations.ext.json`, `cost_class: site_read`, 10 units). EU to formalize it in 1.3:
- the three purposes;
- the untrusted quote object;
- the booking-platform rule;
- the error mapping, whose `details.rule` and `details.why` say why a site couldn't be read.

## What Tyler decides before step 8

1. Where the live secrets live: the separate `agapi-live` service (recommended), and whether it shares the Postgres.
2. Whether live payments take real money (a Stripe live key), or stay on Stripe test for the first S2 users.
3. Which record is the source of truth for a venue booking during the transition (recommended: AgAPI's, with Sasha's as a copy until S1 moves).
4. The day S2 goes to `reads`, and the day it goes to `1`.
