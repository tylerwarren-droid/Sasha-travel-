# Sasha 385 — the SME group finish: ONE "so what", ONE final report, traveller by traveller

KANOE_DECISIONS 13 Nov 15:12 — "The group finish is a clear final report … never a wall of text. In chat: ONE short "so what" … Then a final
report document, traveller by traveller … Each traveller is emailed their own itinerary. The report is drawn from the one trip record /
master list, never a second copy."

## Found (Tyler's Yerevan demo, 13 Nov 15:07)
One paragraph: "1 of 7 booked. Their references are on the master list. Confirmations have been sent to each traveller's registered email.
The invoice … Ana García and Carmen Castro: the airline hasn't confirmed yet … Elena Ortega / Luis Pérez / Marta Ruiz: part of the trip is
booked and the rest isn't" — 6 of 7 named, "sent to each traveller" while 1 was booked, no fix offered; then "Hey Sam, what can I help you
with?" mid-flow (S2's rule 4: her last line was a statement, and a group job running isn't a question on screen).

## The one source: `backend/booking_signer/group_report.py`
- `buckets` — every traveller in exactly ONE: fully booked · waiting on the airline · need a new flight / hotel (an incomplete record: the
  part it didn't book, from its parts) · not booked. A traveller on the trip but absent from the list → "missing from the list (<name>)".
- `line` — "Yerevan, 15–20 Dec: 1 of 7 fully booked · 2 waiting on the airline · 3 need a new flight · 1 not booked." by code.
- `question` — the ONE grouped question with its taps: "Rebook the 3 on the next flights?" [Rebook them] [Release the hotels]; a hotel to
  replace; else the named reasons (group_book.one_question) [Book anyway] [Another option] [Leave off]; nothing to decide → none. The
  mandate's own card (anyone outside the instruction: its explicit tap) stays THE question when there is one.
- `report` / `page` — a row per traveller: flight (+ its fare's conditions) · hotel · status · reference · itinerary emailed (yes/no, from
  the send record) · what's missing · the fix; the invoice. Served at `/api/agent/group-report/<signed, dated token>` from the list as
  it is now (no second copy).
- The trip record keeps what the list can't: `itinerary:<member>` (each itinerary that WENT), `why:<member>` (the reason a run met),
  `cond:<member>` (a booked fare's conditions), `invite:<member>` (each passport link that WENT) — one key per traveller (atomic).
- `send_itineraries` — each FULLY booked traveller's own itinerary, once, through the one sender (`live_events.send_email`), recorded;
  "sent" is said only from that record (the report's "emailed"). The old `_confirmations` (a second sender, and the "each traveller"
  claim) is deleted.

## Where it shows
- `group_book.finish` returns the line + the question + the card + the report link + the list card; `mandate.py` tells it to the door
  that started it (`channel.tell`: S2's `group_done` event with the list card ("Full report →") and the question card; WhatsApp: the line,
  the question's buttons, "Full report → <link>"); a tap on the group card (`sasha.card_tap`) yields the same two cards.
- S2: the live "Working on it" card ends with the record's own line (no more "Done — the master list has every reference."); rule 4
  counts a turn in flight or a group trip being booked as mid-flow — no "Hey <name>" inside it (held by the prebuild).
- /next: a `say:` tap is the message itself (never an answer to a card).

## What reads the master list (groups.view) today
agapi/v0.py (group_list), booking_signer/group_book.py (prepare, swap, finish, invoice …), group_outcome.py, group_report.py,
group_routes.py (/group/list), mandate.py (planning and the finish).

## Tests
`backend/tests/test_s385_one_group_finish.py` — 7 travellers in mixed states: each counted once within the template; the half-booked
offered the fix; a traveller missing from the list said; a row per traveller from the record; each itinerary once; a failed send is never
"emailed: yes"; the report link signed and dated; one source. ONE TRUTH T101.
