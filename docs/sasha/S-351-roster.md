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

**Older duplicate vaults** (the same person's second passport from another trip) stay as they were, owned by that old row. Nothing is lost. They can be cleared once the organiser confirms.

## Tests

- `backend/tests/test_s351_roster.py` covers:
  - the roster made once;
  - links only;
  - a second trip reusing people;
  - ambiguous names asked about;
  - one vault per person serving the next trip;
  - a new home airport being what the next search reads;
  - the 053 migration on real Postgres.
- 333, 334, 336 and 346 are updated to the person-owned vault.
