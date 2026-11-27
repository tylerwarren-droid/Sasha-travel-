# Sasha 423 · FP-4 · NO REFUNDABILITY WITHOUT A FACT

KANOE 26 Nov 11:08 · "anything shown about a booking the person is making or has made reads only from facts.answer" · HAZARD TO CLEAR FIRST:
"FP-4 deletes it or proves no live door reaches it."

**CLASS:** any term shown about a booking (refundable, deadlines, fees) comes from AgAPI's facts.answer, or it is not shown.

## (1) The one truth
AgAPI `fine_print_facts`, read through `facts.answer {question: "of_item"}` (CR 222, agapi_service/facts.py).

The published contract already carries it: `facts.answer` (`of_item`) is in @kanoe/contract **1.110.0**. Sasha's vendored copy
(`backend/kanoe_contract`) is 1.104.0, and re-vendoring is a routine step (see Sasha 386). That is not what blocks the reader. These do:
- **No Sasha row carries an `item_ref` the record keys.** Per EU 319, `item_ref` is Kanoe's `lst_` id. TAAP bookings reach Sasha with CR 230 / Sasha 420; today's Sasha itinerary is venue acts, which are on ice.
- **No fact stands on live for any booking.** FP-2's writer (CR 223, PR #189) is unmerged, and FP-1's scratch writer writes, reads back and forgets.
So "a trip with a fact shows the fact's words" has nothing to show yet. That reader belongs with Sasha 420's trips door, and lands there.

## (2) The second copies: deleted
| Where | What | Who read it |
|---|---|---|
| `backend/app/models/itinerary.py:43-44` | `is_refundable: bool = True`, `cancellation_policy = {}` | nobody: the model is imported nowhere |
| `frontend/types/index.ts:39` | `is_refundable: boolean` | ItineraryPanel only |
| `frontend/app/components/ItineraryPanel.tsx:55` | the "Refundable" / "Non-refundable" badge | nobody: the panel is mounted nowhere (no importer) |
| `backend/app/services/vietnam_golf_database.py` | 22 hardcoded `"cancellation_policy": "NN hours notice required"` | `get_course_details` returned the whole dict to the golf agent's model, so it could have said it. **Corrected 27 Nov (Sasha 424):** no live door reaches it. S-32 took golf out of the conductor registry, `run_golf_intent` has no caller, and /api/agents/golf is unmounted (404). A golf turn on the live conductor returns 500 (`run_general() missing … 'general_prompt'`): the registry's fallback calls `run_general` without its prompt. That is a separate defect, reported to Tyler. The tool description no longer promises it either. |
| `booking_signer/sql/024_payments.sql` | `payment_requests.refundable_until` | nothing writes or reads it; `062_no_refundable_until.sql` drops it (NOT APPLIED: founder approves, chat applies) |

## (3) The ratchet
`backend/tests/test_s423_no_term_without_a_fact.py` covers the whole repo, not a file list. It fails on any of these, when the name matches `TERM_FIELD`:
- a Python class attribute or dict-literal key;
- a TypeScript interface member;
- a SQL column still standing after every file has run.

`TERM_FIELD` matches `refundab*` and term-shaped `cancel*` names: `cancellation`, `cancel_policy`, `_until`, `_deadline`, `_fee`, `free_cancel*`, `refund_policy`. A status (`cancelled`), an action (`booking_cancel`) and an id (`cancellation_id`) are not fields about terms.

A second test checks the frontend: no screen draws "Refundable" or `is_refundable`. Red on origin/main (both tests), green on this branch.

CTO drops overwrite `backend/app` and `frontend/app`. **Sasha 424:** CI (`sasha-ci.yml`) now runs the full backend suite and `npm test` on every PR and on main, and both are required checks. The TypeScript and screen half moved to `frontend/scripts/no-term-424.test.mjs`, and the `booking_terms.py` debt below is deleted.

**One named debt (shrink-only):** `agapi/booking_terms.py` (Sasha 301) composes venue terms and a "by <date>" deadline from the venue's own reply at view time. Readers:
- the Trip tab (`itinerary.with_terms`);
- `booking_fine_print` (/s2, voice, WhatsApp);
- the `cancel_by` reminder (proactive).

These terms are not read through facts.answer. Their writer is AgAPI `venue_words` facts (FP-4 venue words), on ice with venue booking (KANOE 26 Nov 12:07). Whether to switch them off meanwhile is Tyler's question.

## The seam: every reader
| Door | Reads a refundability / terms field of Sasha's? |
|---|---|
| S2 (/s2 chat, voice, WhatsApp: app/agent/s2 → booking_fine_print) | no stored field; Sasha 301 view-time venue terms (the debt) |
| /next (S1) | no (bundle has no "Refundable" or `is_refundable`) |
| WhatsApp (products/whatsapp, conductor) | golf strings, deleted here; Sasha 301 terms via the S2 brain (the debt) |
| Luxury site (luxuryoffseason) | no trips door yet (Sasha 420 builds trips.open_guest). `lib/words.ts:39`'s "free cancellation" describes a measured **offer** (AgAPI observations' `refundable`), not a booking, and is AgAPI's field, not Sasha's |
| Guestcentric hand-over | its `cancel` is the hotel engine's own words for an **offered** rate, with no frontend caller. Parser retired (KANOE B-Q4) |
| group_report / group_book | **open, Tyler's question**: tells the guest "it can't be refunded" / "only the airline can cancel it" from `group.book`'s `conditions`, an AgAPI answer but not facts.answer. Not a Sasha field (the ratchet doesn't match it); by the class's plain words, the same kind as Sasha 301 |

**Live, 27 Nov:** project.kanoe.ai `/`, `/next`, `/s2`, `/vietnam2` and `/vietnam` were fetched with every JS chunk (4.4 MB). They contain 0 "Refundable" and 0 `is_refundable`.
