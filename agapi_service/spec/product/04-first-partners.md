# AgAPI for partners · 4: the first three partner types to pitch

*EU 211 · 9 Oct 2026. Each partner type gets:*
- *the job AgAPI does for them;*
- *the **three operations they'd use first** (plus what those imply);*
- *the pitch line;*
- *the demo to show.*

## 1. A consumer travel app (trip planner, AI travel assistant)

**Their problem:** their assistant can *suggest* a flight but can't safely *buy* it. When a model books, they can't
prove the user agreed, and a retry might buy two tickets.

**The first three operations:**

| # | Operation | Why first |
|---|---|---|
| 1 | `travel.find_flights` | real Duffel inventory (test today), with honest coverage when a source is down |
| 2 | `trip.hold` | the price re-checked + **the read-back**: the exact lines their user approves |
| 3 | `trip.complete` | the one act: needs the user's own yes, happens once, returns proof |

**Implied:** `approvals.request` (the SMS link) or the SDK, and `acts.status` for "booked".

**Pitch:** *"Let your assistant book, not just suggest, with proof your user said yes, and never twice."*

**Demo:** `/demo`, as built (find → hold → the phone → yes → confirmed + proof).

## 2. A relocation agency (moving employees or students to a new city)

**Their problem:** each move is dozens of small acts done by hand:
- emailing a landlord, writing to a school, booking a first-week stay;
- reminding the person of each appointment.

Agents spend hours on messages that need the mover's say-so.

**The first three operations:**

| # | Operation | Why first |
|---|---|---|
| 1 | `messages.send_email` | writes to landlords, schools and offices **from AgAPI's address on the mover's behalf**, sent only after the mover's yes to the exact text; proof of what was sent |
| 2 | `calendar.add_event` | every confirmed appointment or booking straight into the mover's calendar, free, no sign-in |
| 3 | `activity.list` | one timeline per mover of everything done, from the proof records: the agency's case file |

**Next:** `messages.send_whatsapp` + `messages.replies` (landlords answer on WhatsApp), and `travel.find_stays` +
`trip.hold` for the first-week stay.

**Pitch:** *"Every message to a landlord or school approved by the mover in one tap, sent once, logged with
proof."*

**Demo:** the `/demo` buttons "Email the plan to Marta" + "Add to calendar", then `activity.list`.

## 3. A corporate-travel / expense tool

**Their problem:** policy and audit. Who approved this trip? Was this the price shown? Can finance prove it?

**The first three operations:**

| # | Operation | Why first |
|---|---|---|
| 1 | `trip.hold` | the read-back is the **policy moment**: price, fare rules and cancellation terms, as lines an approver sees |
| 2 | `approvals.status` | their workflow polls it, with no webhook needed, to know when the traveller (or their manager, once approver roles exist) said yes |
| 3 | `evidence.get` | the proof for expenses and audit: what was booked, at what price, approved by whom and when, verifiable by hash (`evidence.verify`) |

**Implied:** `trip.complete`, plus webhooks (`act.confirmed`) into their expense system.

**Pitch:** *"Every booking with a verifiable record of what was approved, at what price, by whom: audit-ready
by default."*

**Demo:** `/demo` up to "Confirmed + proof", then `evidence.verify` recomputing the hash live.

⚠ **Gap for this partner:** the approver today is the end user only (`presented_to`). A **manager approves** flow is
not in v1. It would be an additive v1.x feature: an approver role on the read-back. Don't promise it in the pitch.

## Order to pitch

1. **The travel app.** It's the demo as built, and the clearest "agent acts" story.
2. **The relocation agency.** It uses the v1.1 message operations, and those are where AgAPI differs most from a
   booking API.
3. **The corporate-travel tool.** It needs the approver-role gap closed to be fully convincing.
