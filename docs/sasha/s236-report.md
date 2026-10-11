# Sasha 236 — report (11 Oct 2026) · S2 parity (EU 232 §2.1) + delete everything

## Live
- main **512b582** (code). Railway **9d6586ca** SUCCESS, gate PASS. Vercel **dpl_CvHYnrhqnXTYWH6uGJzuUdinmnS5** READY (sasha-travel-hdyp).
- Units 1966 OK (146 skipped, 1 expected failure). `npx next build` OK. eslint is clean on S2App.tsx and tripBoardCss.ts.
- **S1 fingerprint: byte-identical to 228's baseline** after every commit.
  - The spec's `book` description fix sits in S1's tool list. The prompt says "S1 untouched", so /s2 carries its own `S2_BOOK` and S1's description is unchanged.
  - SashaChat and /next were not changed. The trip board's styles are a scoped copy (`app/s2/tripBoardCss.ts`), so no before/after screenshot was needed.
- **Migration `backend/booking_signer/sql/042_account_purge.sql`: DRAFT, not applied.** Apply it in Supabase whenever you like; nothing depends on the order. It does three things:
  - deletes orphaned rows (s2_acts: 1 today);
  - makes the six tables cascade from auth.users;
  - adds `guest_erasure` to retention_log's allowed rules.

## Gate (service key `sk-ant-… bc1e05b8d099`, gate key unset)
| deploy | commit | result | $ |
|---|---|---|---|
| 2be117ab | dab207a | 149/149 | $1.07 |
| d0f81cd9 | bc0f7cc | 149/149 | $1.07 |
| d7f0a774 | 82ede6d | 149/149 | $1.03 |
| da744794 | aa4fddc | 149/149 | $1.05 |
| 7876ebc9 | 05c0c35 | 149/149 | $1.05 |
| 91e1c7f8 | 4f6399e | 149/149 | $1.06 |
| **057eed4a** | 97539a0 | **FAIL**: voice loop 9/15 ("payment links on the phone: 0") | $1.02 |
| 1d0a7084 | 9c9399a | 149/149 | $0.94 |
| 9d6586ca | 512b582 | 149/149, DEPLOY GATE: PASS | $1.05 |

**The FAIL was my fault.** I pushed 9c9399a while 97539a0's deploy was still running its gate. Two gates collided, which is the known "0 payment links" symptom, so it was not a code fault. 97539a0 had also pushed a test without its code: my edit had failed and the chained commit went ahead anyway. 9c9399a added that code and passed.

## 1 · CR 80 merged (cr/80-s2 @ ff73d18): DONE
Proof on production /s2 → agapi-sandbox, scratch guest:
> "My checked bag on Example Air EX123 … came 2 days late — I got it on 11 October. PIR LHREX12345, receipts 85.50 euros"
> → "Example Air has to receive the claim by **1 November 2026**, which is 21 days after you got your bag back … The Montreal Convention caps what an airline pays … it doesn't set what you're owed."
> → "Yes, claim it. Booking EXA1B2, just me, Alex Gate." → read-back (baggage@example-air.example, EX123, PIR, €85.50)
> → "Yes, file it." → "It's filed with Example Air."
> → "Where's my bag claim?" → "filed with Example Air on 11 October 2026 (ref sbx_claim_wqdhft11) … **Their reply is due by 10 November 2026** … 'We reply to every claim within 30 days.'"

Found live and fixed (bc0f7cc):
- The read-back said "EXEX123": the airline code was doubled.
- In one run she described the claim from memory and never called `file_bag_claim`, so "yes" never filed.

## 2 · S2 says what she can do: DONE
- **S2_WHO:** "cancelling a subscription" is out of her can't-do examples. They are now a taxi, a doctor's appointment and a food delivery.
- **`s2_home.CAPABILITIES`:** gains groups for Your bookings, Trips, Cards & cover, If something goes wrong, Money back and Subscriptions. `SAY` is updated to match.
- **`test_s2_225`:** every line must be backed by a tool /s2 has, and every listed tool must be on the card.
- **Stale copy fixed:** the S2App header and /s2's own `book` description.
- **Proofs:**
  - "Can you cancel my Netflix?" → "I can't see a Netflix subscription on your account yet. If you upload a bank or card statement here, I'll find it and work out how to cancel it." Not "can't".
  - "What can you do for me?" → `what_i_can_do` and the card: "book tables, spas and whole trips … keep track of your bookings … get money back if a flight or bag goes wrong".

## 3 · Handover card: DONE
- S2App renders `kind: "handover"` as a "Tap to finish" card.
  - Our own hand-over opens in a sheet over her with "Back to Sasha", as /next does.
  - A platform's page opens in their browser.
- **Proof** (production /s2): Método Javier Panizo (Treatwell), "Yes, book it." → `book_venue(page_link)` → `render: handover` → "Their Treatwell page is on this screen. Tap to finish opens it."
- **Found live and fixed:** a page-route venue could never be booked on /s2.
  - Each re-hold's read-back carried a new one-time forwarding address (`act-<uuid>@…`), so her yes never answered a read-back the person had heard. She held again, turn after turn.
  - Fixes:
    - 82ede6d, 05c0c35: the same words keep the time they were said.
    - aa4fddc: `yes_heard` tells her to call `book_venue` now.
    - 4f6399e: the one-yes gate binds a venue by its words.
    - 9c9399a: "on this screen", not "on your phone", when nothing went to the phone.

## 4 · Trip board: DONE
- /s2 has a **Trip** tab that renders **S1's own TripPanel**, so it uses the same records (`/api/booking/plan` + `/api/booking/journeys`).
- flights, stays, flight_chosen, total, trip and trip_changed events refresh it, and a card in the chat says "See the whole trip".
- **Proof:** a Lisbon weekend planned and booked on /s2. Stripe was not paid; the after-payment step was run as the server runs it. The tab's own data calls returned:
  > plan: 3 days in Lisbon · day 1 stay Olympia Lis Baixa (booked, TEST-52CD5B) + Flight U2 7652 MAD→LIS (ref KFBFBLX) · day 3 Flight ZZ 9060 LIS→MAD (ref MHH5HB)
  > journeys: "✈️ Lisbon, Oct · 3" · everything: the 3 bookings with their references · receipts: 3 · forms: 0 (this trip has none)
- **Not done:** a phone screenshot. Signing in to production as the guest would mean typing its password.

## 5 · Delete everything: DONE
- `booking_signer/purge.py` deletes the account's keep_fills, keep_items, keep_keys, s2_acts, s2_wa_replies, s2_wa_contacts and s2_memory rows, plus this process's copies.
- It's called by the account's own `DELETE /api/booking/account/data`. Migration 042 adds the cascades as a floor under it.
- **Proof** (scratch guest 933e30d7): Keep + activity + memory, then a fresh sign-in, then DELETE through the site → HTTP 200.
  - deleted: keep_items 3, keep_keys 1, s2_acts 3, s2_memory 1;
  - then **0 rows in all seven tables**, plus 19 retention_log lines for the erasure.
- **Found live and fixed (512b582):** the route answered **500** after erasing. retention_log's check doesn't allow the rule `guest_erasure`, so this route had never completed on production.
  - Until 042 is applied, the line is logged under `all` with the reason in its note.

## Cleanup
- Scratch guests 2c225197 and 933e30d7 deleted (200), with 0 rows left in any public/auth table for either.
- Duffel TEST orders and the sandbox's claim and end user are test data.
