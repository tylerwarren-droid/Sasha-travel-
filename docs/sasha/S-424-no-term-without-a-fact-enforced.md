# Sasha 424 · NO TERM WITHOUT A FACT, ENFORCED

KANOE 27 Nov 16:18: "go, drop it, switch off and fix CI".

**CLASS:** no door ever states a booking term that AgAPI's facts don't hold, and no rule in Sasha's tests can be silently undone.

## (1) The one truth
- **A booking's terms:** AgAPI's `facts.answer`. Sasha composes none.
- **"Is the rule still true":** Sasha's full test suite, run by CI (`.github/workflows/sasha-ci.yml`) on every PR and on main. Red blocks the merge (the `project-main` ruleset requires both jobs).

## (2) A · the unsourced terms: deleted, not flagged
| What | Was | Now |
|---|---|---|
| `agapi/booking_terms.py` (Sasha 301) | composed deposit / cancellation / no-show / time-limit terms and a "by <date>" deadline from the venue's reply | **deleted**. Perks moved to `agapi/booking_perks.py` (his own Keep, "as you told me": not a term) |
| `itinerary.row_terms`, `with_terms`, `start_of`, `terms_text`, `as_reservation.terms` | every itinerary row, the Trip tab's rows and the reminders' rows carried `terms` | **deleted**: no row carries terms |
| `booking_fine_print` (/s2, voice, WhatsApp, /next) | said the venue's terms and deadline | says "**I have no confirmed terms on record for this booking.**" plus his perks; the tool description and the S2 prompt say never to state or guess one |
| `proactive` `cancel_by` reminder | "Cancellation deadline for X …" sent before the deadline the venue stated | **deleted at source**: no kind, no `_due` branch, no template, no text. No scheduled job can compute or send it |
| Trip tab (`TripPanel.tsx`), plans card (`S2Cards.tsx`) | `termHead` labels, "cancel by …" on the day line | **deleted** |
| `plan_store` day lines, `s2_manage.my_plans` | carried `terms` | **deleted** |
| `group_report.keep` + report row | "it can't be refunded" / "only the airline can cancel it" / "it can't be changed", kept on the trip as `cond:<member>` and drawn in the report | **deleted**: nothing written, and the report reads no `cond:` (rows kept from before are never read) |
| `group_book` | carried each part's `conditions`; the `incomplete` reason said "(only the airline can cancel it)" | **deleted** |

**These return ONLY as AgAPI facts:**
- venue words → FP-4 `venue_words` facts;
- DMC terms → FP-3;
- the group fine print → AgAPI's facts for the group's bookings;

each read through `facts.answer`.

## (3) The ratchet: two halves, both run by CI
**Backend:** `backend/tests/test_s423_no_term_without_a_fact.py` (also deploy-gate T103).
- **No term field:** none in Python, and no SQL column still standing. `KNOWN_DEBT` is empty.
- **No composer:** `COMPOSERS` lists every deleted reader and sentence. None may appear in the backend, and `agapi/booking_terms.py` must not exist.

**Frontend:** `frontend/scripts/no-term-424.test.mjs`, in `npm test`. The deploy gate runs with backend/ only, and test_s283 forbids a gate test reading frontend/, so this half lives here.
- No TypeScript type holds a term field (the same name rule).
- No component holds a deleted composer.
- No screen says "Refundable" / "Non-refundable" / "Free cancellation".

## B · CI runs everything, and red blocks
**`.github/workflows/sasha-ci.yml`** runs on every PR and every push to main. Both jobs are **required status checks** on main (ruleset `project-main`, set through the API 27 Nov).
- **backend · full suite:**
  - Python 3.11 (production's version);
  - Postgres as a service, so the 79 Postgres tests run;
  - node and the frontend installed, so the backend tests that run the page's own code run too;
  - the import check, then every test (`discover -s tests -t .`);
  - **the job fails if any test is skipped.**
- **frontend · tests + build:** `npm ci`, `npm test`, then `npm run build` (prebuild checks included).

### Each red found, fixed at its cause (never skipped, isolated or retried)
Each was found by bisecting the modules that run before the failing test.

**`test_s2_226.MyPlans`**
- **Cause:** `flight_manage._SEEN`, the 20-second Duffel order cache, handed back a read made through one Duffel client when a *different* client asked. `test_flight_manage_226` and `test_s246_item4` swap the client, so their fake `ord_1` (dated 2037) leaked into later readers.
- **Fix (the class):** a read keeps the client that answered it and is reused only for that same client. Production has one client. Pinned by `test_flight_manage_226.OneReadOneClient`, which is red without the fix.

**`test_stage_b_hooks.TheResponseCarriesIt`**
- **Cause:** `test_s311` called `self.setUp()` and `self.tearDown()` by hand. A `GW.STORE` patch was overwritten and never stopped, then leaked into every later test.
- **Fix:** each wording gets a fresh store in a `subTest`, and every patch ends through `addCleanup`.

**7 group-mandate test files (s365, s366, s367, s369, s371b, s372, s376)**
- **Cause:** they passed only when an *earlier* module happened to import `tests/founder_fixture` (which installs person_access's test resolver). Alone, they fell through to person_access's network read and failed.
- **Fix (the class):** `backend/tests/__init__.py` imports the fixture, and CI discovers with `-t .`. Every module is then `tests.<name>`, so the package init runs before any test, whatever the order. This also ends the double import, where discovery loaded `test_x` while other tests imported `tests.test_x`.

**4 unconditional `@unittest.skip` tests**
- `test_demo_s169` ×2: `trip_book.stays()` and the in-memory bundle were deleted (Sasha 198).
- `test_invitations_s80.test_6`, `test_escalation_s132.test_one_yes_then_the_page`: the pinned conversation was replaced by the ladder (Sasha 195).
- **Deleted:** their subject no longer exists. The rules are held by the BASKET suite and `scripts/core_suites` LADDER/REST, both in the deploy gate.

**15 frontend tests nothing ran**
- 12 drifted with refactors, and each was restored to its rule against the moved code.
- 3 rules were deliberately retired by a later Sasha ticket, and each test now asserts the new rule (one-total-249 is the least certain).
- 1 was a real regression: two "sourced" EspañaMe rows on the AgAPI hub page carried no source. Each now cites the official page its figures were read from.

**6 Postgres tests that never ran** (the database URL was unset everywhere, so they had been skipping). Each was fixed in the test, at the commit that caused the drift:
- `test_booking_calls` and `test_form_rung`: Sasha 319 (2daf1f47) retired Sasha's own send/place routes. The tests now hold the new rule: Sasha never sends a form, and a call is placed through AgAPI's call act.
- `test_inbound_phone` ×3, which had three causes:
  - the setup lacked sql/018 (Sasha 118);
  - the SMS came from a number Sasha never called (Sasha 386);
  - two clocks, so after 4 Nov the call fell outside the 30-day match window.
  The WhatsApp harness is now one helper that both halves use.
- `test_guest_whatsapp_s75` store: Sasha 392 (a4c7fbed) keeps no history in `guest_wa_state`, and the test now asserts that.
- `test_s2_cr62`: it reads `trips` / `trip_items`, so it now builds them itself as temp tables.

**EU's contract is vendored, never read from a sibling repo on disk.**
- `backend/agapi/spec/v1` is `git archive` of applied-diligence **d63b7b7** `docs/agapi/v1` (AgAPI 1.3): 32 files, `diff -r` empty, EU's own SHA256SUMS. The sha is recorded in `backend/agapi/spec/VENDORED.md`, the same sha as agapi's CR 235 `spec/VENDORED.md`.
- CI runs `shasum -c`, and `test_agapi_v1_sasha` also refuses any unlisted file. Conformance passes 93/93.
- Sasha's code ratchets (the kanoe_contract ratchet, s369's no-default scan) skip exactly the files a vendored set's own SHA256SUMS lists (`tests/vendored.py`, derived, never a hand-kept list).

**CI on cd0e8c3:** backend 3704 tests, 0 skipped, 0 failures, 32/32 sums OK. Frontend 161/161 and the build pass.

**One named debt (not a skip):** `test_robustness_cr56.Injection.test_the_tool_list_is_scoped` is `@expectedFailure`. It is CR 56's ranked gap (the model gets every tool on every turn) and turns red the day it is fixed.

## The seam: every reader, and what it says now
| Door | Now |
|---|---|
| S2 chat, voice, WhatsApp (`booking_fine_print`, one brain) | "no confirmed terms on record" + perks |
| /next (S1, `v0.MANAGE_TOOLS`) | the same tool, the same words |
| Trip tab (`/api/booking/reservations` via `ladder_routes`) | rows without `terms`; no deadline on a day line |
| Reminders (`proactive`, the scheduled tick) | no `cancel_by` kind exists |
| Group report (page + email, `group_report.report`) | the flight column is the transport only |
| agapi repo | `adapters_live/ladder.py` calls `/reservations/{tid}/cancel` (read-back only; never `terms`). Nothing else |
| luxuryoffseason | no caller |

**Named, not changed here:**
- `group_book.MANDATE_FACTS["fare_not_refundable"]` is AgAPI's mandate reason for **refusing an offered fare**, not a booking's term.
- The "They said: …" line quotes the venue's reply as their message, not as a term.
- `payments_t0` (S-81) builds a deposit payment request from the venue's words on a call. **That is a third unsourced term**, outside this ticket's two. It is Tyler's question.

## Open question (found fixing the Postgres tests): ⛔
`MemoryGuestStore.put_state` (`booking_signer/guest_whatsapp.py:227`) still keeps a `history` that the Postgres store dropped in Sasha 392.
- Removing it breaks `test_one_sasha_cr10.py` (lines 57 and 97). Those assertions read that key, which nothing real writes, so today they always pass.
- Pointed at the one record (`s2_memory`) instead, they fail, because the one record holds relocation's turns word for word, the passport number included.
- **Tyler's question:** under 392, is it by design that a product's answers (passport details included) go into Sasha's one conversation record, or is that a leak? Untouched until answered.

## Found on the real path (Step 1's golf proof): ⛔
Asked on the live conductor, "What is the cancellation policy at Montgomerie Links golf course?" returns **HTTP 500** `run_general() missing 1 required positional argument: 'general_prompt'`.
- **Cause:** S-32 (bd0b94a5) took golf out of `AGENT_REGISTRY`. The conductor still classifies golf, and `AGENT_REGISTRY.get(intent, run_general)` runs any unregistered intent through the generic call, which omits `general_prompt`. Every golf turn crashes, and it has done so since S-32. Sasha 423 did not cause it.
- **One source:** the conductor's dispatch, where the classifier's intents meet the registry.
- **Root fix needs:** the classifier to emit only intents the registry holds, or an unregistered intent to dispatch as `general` with its prompt. conductor.py is the CTO's file, so it also needs a Stage B re-apply. That is not this ticket's.
