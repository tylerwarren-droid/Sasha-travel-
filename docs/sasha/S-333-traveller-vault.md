# Sasha 333 · The traveller vault: passport, frequent-flyer and hotel loyalty

Tyler, 3 Nov 20:37. This moves group members from "needs vault" to "planned".

## Root test (written before the code)

### 1. One vault record per person

It is the Keep (CR 63: `agapi/keep.py` + `agapi/s2_keep.py`, tables `keep_keys` / `keep_items`) under the member's OWN id: a Keep of
their own, never the organiser's.
- **Per person:** a data key wrapped by the vault's KMS, every value AES-256-GCM, bound to the person by its AAD.
- **Deleting the person's key** shreds every value at once.
- **Nothing new stores a number:** no new table, no column on the group's tables, no field on a trip row.

### 2. Everything else holds a masked view or a reference

| Who | What they hold |
|---|---|
| The master list / the organiser | ✓ / missing, and a programme's name ("Iberia Plus ✓") — not even a mask with digits |
| The planner | `has_passport` (true / false) |
| The member's own page | masks ("Passport ES ••••0421") |
| The booking call (CR 163) | a reference (`keep:<item id>`) |

The full values are opened ONLY by the Keep's own code at booking time.

### 3. PATCH check

- **No second copy.** The ways a copy could happen, each closed:
  - a trip row (the planner writes none);
  - a log (counts only, never a value or a mask);
  - a chat message (the invite carries a link, never a number, and the tool says NEVER ask for one);
  - the model's context (its tools return ✓ / missing).
- **Said:** `keep.py` gains two OPTIONAL passport fields, `name` (as on the passport) and `born_on`, which the airline needs.
  - The frozen sandbox vectors stand, because the fields are optional.
  - AgAPI's copy of `keep.py` should get the same two fields: a CR ask, so the two copies don't drift.

### 4. Whole class (tests/test_s333.py)

- The 24 numbers saved through the page are searched for in the logs, the trips, the emails, the WhatsApp reply, everything the model
  can see, the member pages, the Keep's stored rows (sealed) and the group's tables. They are found nowhere: 0 everywhere.
- The member's page shows masks; the model's inputs carry no "••••" at all.

## What it does

1. **Invite** (`group_invite_vault`, or "Invite everyone to the vault" / "Invite" on `/group`):
   - A signed, single-person, 7-day link per member.
   - It is emailed where the list has their email (new optional `email` column). The rest come back as links for the organiser to
     forward.
   - Nothing is ever collected in chat.
2. **The page** (`/vault/<token>`, no sign-in: the token is the key):
   - Passport: number, country, expiry, name as on the passport, date of birth. All five are required here.
   - Frequent-flyer and hotel loyalty: programme + number.
   - Saved into THEIR Keep. Never logged, never sent to the model.
3. **Display:** the member sees masks; the organiser sees "Passport ✓ / missing" and "Iberia Plus ✓".
4. **Use:** the master list moves to "planned" once the member's Keep holds a passport. CR 163 opens the values at booking time, by
   reference.
5. **Delete:**
   - From the same page: one item, or everything, which also destroys their key.
   - "Delete my passport" from their own WhatsApp number: the list's new optional `phone` column, matched to the webhook's signed
     sender.

## Not done, said plainly

- **WhatsApp invites:** a first message to a number that never wrote to Kanoe needs an approved template. Invites go by email, or the
  organiser forwards the link.
- **Changing a number:** the page has no "change". Delete the item and add it again.
