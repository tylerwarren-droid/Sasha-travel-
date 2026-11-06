# Sasha 351 · a company's people are ONE standing roster; every trip is a SELECTION from it

This ticket follows the NO PATCHES rule.

## What was there, and its cause

- **Before:** `group_members` belonged to a movement. Each row carried its own name, grade, home city, email and phone, and each row was its own vault owner (`keep_owners.member_id`).
- **The problem:** the same worker on two trips was two records with two passports. sasha-prod, 6 Nov: "Obras Ejemplo SL" had 82 rows for 21 people, with 56 vaults.
- **The cause:** the person had no record of their own. The trip's row *was* the person.

## The one source

**`group_people` is the roster:** one row per worker, under the company (`groups`).
- It holds their name, grade, **home airport**, home city, email and phone.
- It owns **their vault**: `keep_owners.person_id`.
- Any change here (a new home airport, a new passport) is what every future trip reads.

**`group_members` is now the link:** a person on a movement (`person_id`, `movement_id`, out/back dates, `trip_id`). Nothing about the person is copied onto it. The store joins the person in when it reads a link.

**Vault ownership:**
- `traveller_vault._owner(m)` returns the person. Every Keep call and every vault link uses it.
- `group_book` grants AgAPI's per-booking key to the person (`owner_of`).
- AgAPI's worker key stays the link id, because a booking belongs to one trip.

**Matching:** the organiser's own name for a person on their own list, among their own company's people.
- Exactly one match: that person, with their details updated from the row.
- No match: a new person is added.
- Two matches: the row is asked about, never guessed.
- It never matches on email ("same email = same person" would be a patch).

## Surfaces

**/group gains People:**
- add someone (name, grade, home airport, city, email, phone);
- Edit;
- Documents (their own vault page, no trip needed);
- tick people, then "Put the N ticked on <trip>".

People already on the trip show "✓ on it". The master list's "From" column shows the home airport.

**Routes:**
- `GET /api/booking/group/people`;
- `POST /api/booking/group/people` (rows, or pasted text);
- `POST /api/booking/group/people/{id}`;
- `POST /api/booking/group/people/{id}/documents`;
- `POST /api/booking/group/choose`.

All of them go through the one outcome path (`group_outcome.run`: `person_add`, `person_edit`, `documents`, `choose`). Choosing plans the new travellers from each person's home airport.

**The chat:** the tools `group_person_add` ("add Ana García, Madrid, worker") and `group_choose` ("Lisbon 17–21 Nov for Ana, Luis and 10 more"). Both use the same outcome path.

## Migration: `053_group_roster.sql` (SQL FOR CHAT)

1. **Archives first:** `group_members_archive_351` and `keep_owners_archive_351`.
2. **People, as the data shows them:** one per company and name (trimmed, case-folded).
   - Each person takes the id of their row whose vault is kept (the most recent row with a vault, else the most recent row).
   - The Keep's sealed items are bound to that id, so nothing is re-keyed.
   - Contacts are the latest ones given.
3. **Links:** every row is linked to its person. The kept vault moves to the person. The copied columns on links are nulled (the archive holds them).
4. **Refuses rather than guesses:** it rolls back if any row is left without a person.
5. **Idempotent.**

**ONE vault per person (Tyler, 6 Nov 11:40).** After 053, 38 vaults were still owned by old trip rows (`member_id`). These are SECOND COPIES of a person's vault: 50 items for 20 people, all on the test organiser's company. They are resolved in three steps:

1. `054_vault_copies_archive.sql` (SQL FOR CHAT) archives first. It copies each copy's owner row, key and items, and each of their persons' too, so an archived item can still be opened by the key service.
2. **The product** folds each copy into its person: `python -m booking_signer.vault_fold`, run once in the Sasha service, calls `s2_keep.fold_into`.
   - For each kind, the newest item of the two is kept. It is re-sealed under the person's own key if it was the copy's.
   - Every other item of that kind, and the whole copy (its items and its key), is shredded.
   - It prints counts only, and running it again does nothing.
3. `055_keep_owners_no_member.sql` (SQL FOR CHAT) removes `member_id` from keep_owners. A vault is then an account's or a person's, exactly one. It refuses while any copy is left.

**Two places where the model was told the old copy model, found live** (the tool registry, the one source):
- `group_start` said "Then ask for the list", so the model asked for every person's details and dates again.
- One person named in the chat went through the list path.

Both now say: choose from the roster (`group_choose`), and a person named alone is `group_person_add`.

## Found by the live proof, and fixed at their one source

- **/s2 offered a hand copy of the group tools' names.** `group_person_add` and `group_choose` were in the registry but never offered on /s2. `S2_TOOLS` now takes the whole `group_*` family from the registry.
- **"The trip" meant the newest one made.** Starting Porto left Lisbon unreachable. The OPEN trip is now the organiser's own choice, stored once (`056_group_open_trip.sql`, `group_movements.opened_at`).
  - `store.movement(account)`, the one read every action uses, returns it.
  - /group shows Your trips with an Open button for each; the chat has `group_open`.
- **Where a person flies from had two answers.** Planning read the roster airport; booking read the city ("no flight None → Lisbon"). Now `groups.origin` is the one answer, used by planning, AgAPI's booking search and the invoice.

**Not this class (said, not patched):** `_quote` hard-codes the hotel country as Spain, and "Porto" resolved to BPT (Beaumont, Texas). The Porto card was left untapped.

## Live proof (6 Nov, project.kanoe.ai, the test organiser, fictional people, no emails or phones)

- 25 on the roster of "Lusa Obras Demo (fictional)": 24 added through People, 1 through the chat ("add Ana García, Madrid, supervisor, home airport MAD").
- Lisbon 17–21 Nov: 11 ticked plus Ana from the chat makes 12, each planned from their own airport (MAD, BCN, SVQ, VLC, BIO, AGP).
- 12 fictional passports were saved on each person's own vault page.
- Book all, then Yes (Duffel TEST via AgAPI's sandbox): 12 booked.
- Invoice KAN-844FE183-TEST: €8,104.18, one line per person with their own airport and references.
- Porto 1–3 Dec, chosen in the chat ("Ana García, Luis Pérez and Marta Ruiz"): all 3 show Passport ✓, with nothing typed again.

## Tests

- `backend/tests/test_s351_roster.py` covers:
  - the roster made once;
  - links only;
  - a second trip reusing people;
  - ambiguous names asked about;
  - one vault per person serving the next trip;
  - a new home airport being what the next search reads;
  - the 053 migration on real Postgres;
  - one vault per person: 054 archive → the fold → 055, on real Postgres (newest per kind, the copies' keys shredded, 055 refusing while a copy is left);
  - the tool descriptions.
- 333, 334, 336 and 346 are updated to the person-owned vault.
