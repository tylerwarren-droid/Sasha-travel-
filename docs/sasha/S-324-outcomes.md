# Sasha 324 · outcome logging: the 20–30 real-booking count starts

Tyler: "sasha needs to learn"; the reliability target.

## Root test (written before the code)

1. **The one truth for a booking's outcome is the one booking record:** AgAPI's act, plus Sasha's trip item for what Sasha books
   itself (flights and hotels through Duffel).
   - AgAPI writes each act's outcome into its outcomes ledger itself. Every `venue.submit_booking` records `agapi:<act_id>`, and the
     act's later states update it.
   - The ledger is that record's outcome view, not a table of Sasha's.
2. **PATCH test.** A per-surface log is a patch. Sasha writes to the ledger only for an attempt that never became an act: "handed to
   Tyler", or refused before anything was sent. It writes from ONE choke point, the agent's tool runner (`v0.call`), for every
   surface.
3. **Whole class: can any booking, change or cancel end without a recorded outcome?**
   - **A booking AgAPI sent:** recorded by AgAPI.
   - **A trip paid through Duffel:** recorded by Sasha (`basket_booked`).
   - **A booking, change or cancel that ends before an act** (to Tyler, refused, not prepared): recorded at the choke point.
   - **A change or cancel AgAPI sent** (its own act): ⛔ AgAPI's ledger takes booking attempts only. The cancel or change act keeps its
     state on the act record, but it is not in `outcomes.report`, so the week's numbers can't count it. That is AgAPI's to add
     (proposed CR 153: the ledger records cancel and change acts as attempts of their own kind). No second table in Sasha.

## Found while building it: every AgAPI booking was counted twice

`s2_outcomes.booked` recorded Sasha's AgAPI bookings (`rung agapi`, ref `sasha:agapi:…`), and AgAPI recorded the same act itself
(`agapi:<act_id>`). Since 319 every AgAPI booking sat in the ledger twice. Sasha no longer records an act; AgAPI's own row is the one.

## The outcomes

Each one is on the ledger with its channel (`email · whatsapp · phone · web_form · page_handover · handover`), its sector (the kind:
restaurant, spa, hotel…), when it was asked and when it was decided:
- confirmed;
- declined;
- failed + why: handed to Tyler — why, not prepared, not allowed, the error;
- **no answer:** an attempt still open past its channel's expected wait.

"No answer" is read from the ledger's own times; nothing stores it. The expected waits are one table (`outcomes_week.WAIT_H`):

| Channel | Expected wait |
|---|---|
| email | 24 h |
| WhatsApp | 12 h |
| phone | 2 h |
| a web form (its confirmation email) | 24 h |
| a page handed over | his to finish: never "no answer" |

## The week's query (read-only)

`outcomes_week.week()` reads AgAPI LIVE, so real people only (a test person's bookings go to the sandbox). AgAPI's report also leaves
out attempts marked test. It returns:
- real bookings this week;
- the outcome rate per channel and per kind;
- "no answer" counts;
- AgAPI's couldn't-handle list (`venue.unhandled`) with its counts.

Where to read it:
- **In the chat:** the founder's tool `booking_outcomes`.
- **An endpoint:** `GET /api/booking/outcomes/week` (founder only).
- **The log:** a line once a day and at start-up, numbers only: `[outcomes] week: …`.

## "No answer yet", once

An AgAPI booking still requested after its channel's wait reads "No answer yet" on the trip and in get_status, never a silent
"requested". It is said once, on WhatsApp and /s2, and the act remembers that it was said.
