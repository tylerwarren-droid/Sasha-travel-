# Sasha 359 — who goes is chosen BY DESCRIPTION, through the one group engine, from every door

Tyler, 7 Nov: "I want to choose people by description. I want the user to be able to converse naturally with Sasha to plan their trip for their people."

## How it works (backend/booking_signer/groups.py — 358's engine)

- **`resolve(filter)` — the ONE resolver.** The model only *proposes* a structured filter: roles, grades, `names_in` / `names_out`, `exclude_roles`, `last_trip`, `everyone`.
  - The engine applies it to the roster deterministically.
  - It names every miss: "no one called Javier Prieto — did you mean Javier Moreno?"
  - Two people with the same name are both offered; neither is picked.
- **`propose`** shows the list for a yes, and nothing changes. It asks only what's missing, one short question at a time: "Where to?" → "Which dates?" → "Who's going?".
- **`confirm`**, used once, is the only thing that then makes the trip (`create_trip`) or adds / takes off people (`set_on_trip`).

## Every door

- **The chat:** S2, /next and WhatsApp share one brain.
  - `group_select` and `group_confirm` (only on their own yes) **replace** `group_start` / `group_choose`, which picked people their own way.
  - An organiser (an account with a company roster) is offered the group tools on every turn. This was found by the proof: "…all the executives" named no group word, so no group tool was offered.
  - A list pasted in the chat goes onto the roster, then the list for a yes (its unclear rows are asked first).
- **The card:** a read-back with "Yes, these people" / "No". These are typed-word taps, so WhatsApp draws them as buttons in one message.
- **/group's search box:** `POST /group/select` → the model's filter through the gateway → the same resolver. A new trip ticks the matches; on the open trip it shows the list, answered through `/group/confirm-list`.
- **Group tab:** S2 and /next render the same `GroupView`.

## Demo data (fictional, through the engine)

- Lusa Obras Demo: 6 executives (all with a passport in their own vault), 8 engineers, 6 technicians, 3 sales, 3 interns.
- 358's Lisbon 24–27 proof trip was ended through the switch (nothing was booked).

## Deploy

- The new tools changed the model requests, so the gate had no recorded replies (ReplayMissing).
- `SASHA_GATE_RECORD=1` was set in **Doppler** sasha/prd; the synced deploy (e240be31) recorded only the missing replies.
- It was then deleted from Doppler; Railway no longer has it, and the next deploy (eadd20cd) passed on the recordings.

## Recording the gate's replies: ONE build, never two (Sasha 381k, 13 Nov)

**Why the procedure started TWO builds.** Two things each start a Railway build of the service:
- a `git push` to main — Railway builds the new commit from GitHub;
- a change to a Doppler secret — the Doppler → Railway sync changes the service's variables, and Railway redeploys its **latest
  deployment**.
Pushing and then setting `SASHA_GATE_RECORD` straight away therefore built the same commit twice, at the same time: one gate replaying
(no recordings yet, so it fails), one recording. Two gates at once shared the test identities the gate links (found 13 Nov: both voice
loops linked the same fixed WhatsApp numbers, each took the other's mobile → `mobile_needed`, row 1998). Setting the flag *before* the
push doesn't help: setting it redeploys the current latest (the old commit), and the push then builds again.

**The procedure — one build at a time:**
1. Push to main (no flag). **Wait until that build has ended** (it fails with ReplayMissing when replies are new; that's expected).
2. Set the flag, output discarded: `doppler secrets set SASHA_GATE_RECORD=1 --project sasha --config prd --silent --no-interactive
   >/dev/null 2>&1`. The sync redeploys the latest deployment — that commit — **alone**: the recording build.
3. The moment its gate ends, delete the flag, output discarded: `doppler secrets delete SASHA_GATE_RECORD --project sasha --config prd
   --yes --silent >/dev/null 2>&1`; check by name only (`doppler secrets --only-names | grep -c SASHA_GATE_RECORD` = 0). The sync
   redeploys once more — the **replay** build, alone. Its gate must pass on the recordings (a recording from a build whose gate failed is
   never replayed, Sasha 381f).
Never push while a recording or replay build is running.

**And the gate never shares an identity between runs anyway** (`backend/scripts/gate_identity.py`): the voice loop's WhatsApp numbers
come from the run's own deployment id, and a number already linked to anyone is never taken. Its docstring lists every identity the
gate suites use and why only that one was shared.

## Proven (8 Nov)

### S2, as the test organiser
1. "plan a Lisbon retreat 24–27 Nov for all the executives minus Javier Moreno" → "Five executives, with Javier left out: Ana García, Carmen Castro, Elena Ortega, Luis Pérez and Marta Ruiz. Should I make the Lisbon trip, 24 to 27 November, with these five?" The card listed each with their home airport, with Yes / No.
2. **Yes** → planned from each own airport → "book them all" → ONE card of AgAPI read-backs (fare and stay changes said, passports from each person's own vault, TEST) → **Yes, book them** → "Done — 5 booked."
3. The Group tab: 5 booked — €716, €696, €708, €667, €708.
4. "send me the invoice" → **€3,495.21** with its link. That matches the record: the five booked prices sum to €3,495 (each row shown rounded).

### WhatsApp
Production's code and settings, the real signed webhook, the sandbox number; a fictional number linked in memory to the test organiser; outbound recorded, not sent.
- "plan a team trip to Porto 1–3 Dec for all the engineers minus Rui Novo" → ONE message: the list (each with their airport), "Note: no one called Rui Novo — did you mean Rui Novo (fictional)?", "Make the Porto trip with these 8?", and buttons **Yes, these people / No**.
- Nothing was made before the yes: 9 trips before and after.

## Found by the proof, fixed at their source

- The group tools weren't offered for a description with no group word. Now an organiser always gets them.
- Removing `/choose` took 358's `/state`, `/create` and `/switch` routes with it: /group and the Group tab read nothing (404) between 231106d2 and 2fb24271. A test now holds that every route the view calls is mounted.

## Not fixed here (said)

- The S2 card's header reads "YOUR BOOKING · ONE TAP" (the generic read-back label) for a list of people.
- WhatsApp's reminders offer came as an extra message after the list. That is pre-existing.

## Tests

`tests/test_s359_by_description.py`:
- the resolver;
- nothing changes before the yes, and exactly the list after (add / drop too);
- one question at a time;
- the chat's card and its WhatsApp buttons;
- confirm only on their yes;
- the old doors are gone;
- an organiser is offered the tools;
- one source, the tabs, the routes, the search box.

Suite: 3404 tests; the only failures are the 2 baseline ones.
