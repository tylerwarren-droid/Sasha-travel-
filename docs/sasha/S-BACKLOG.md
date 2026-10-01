# Sasha tab — backlog (ordered; the founder's numbering wins)

*Kept by the Sasha tab. An item moves to a numbered S-ticket when it is started.*

## After S-66 step 9 (booking inside the chat)

### 1. Who presses the last step — recorded on the reservation, chosen by the price tier
*Founder, 1 Oct 2026 (Sasha 58): his model for venues that ban automated platforms.*

- **The reservation records WHO took the final, venue-facing action**, as a fixed value:
  - `guest` — the guest pressed it themselves (Mode A WhatsApp, the slot link, their own form submit);
  - `kanoe_operator` — a named Kanoe person pressed it on the guest's behalf;
  - `sasha_phone` / `sasha_email` — Sasha, by a call or an email she sent.
- **Which one is used is chosen by the product's price tier**, not by the venue alone: a tier decides whether the guest
  presses, an operator presses, or Sasha acts — within what the venue allows (a platform-banned venue never gets an
  automated press; there the tier picks between the guest and an operator).
- **Every surface says who pressed it**, in the read-back before and on the result after — never implied.
- To design before building: where the tier lives (account / plan), how an operator's press is recorded (who, when,
  the approval it carried out), and how it shows in `/reservations` and the itinerary.

## Waiting on something

- **After-hours email to the same reservation** (S-67 follow-up) — when the GoDaddy DNS lands (US tab) and the email
  rung is live: closed now → email the request now, on the SAME reservation, and a reply cancels the scheduled call.
- **`fixed_start` used in the call brief** (S-64) — "the tour departs at 09:30": not yet said to the venue.
