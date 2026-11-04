# Sasha 336 · Group v1 demo fixes (from the SASHA 335 rehearsal)

## Root test (written first)

**What broke.** In production, 042_account_purge set `keep_keys`, `keep_items` and `keep_fills` to require `account_id` to be in `auth.users`. Sasha 333 keeps a group member's vault under the member id, so every save failed (ForeignKeyViolation). The tests missed it because they used the in-memory store.

**Who a vault belongs to.** ONE record per vault owner: `keep_owners`.

- `user_id` (auth.users) **or** `member_id` (group_members): exactly one of the two, enforced by a check.
- Each of those is unique.
- `id` = that source id (a check enforces it). So every existing `account_id` stays valid, and no row is rewritten.
- `keep_keys`, `keep_items` and `keep_fills` reference `keep_owners(id)` and cascade.
- `keep_owners` itself cascades from both sources: deleting the account, or the member, shreds that vault.

**How a row appears.** The Keep's store writes the owner row before the first key. It resolves the id against `auth.users` and `group_members` in ONE statement. An id that is neither fails the check, and the Keep says so as itself ("isn't a Sasha account or a group member"), never as "the key service didn't answer".

**What is not done.**

- The FK is not dropped and left open.
- No second table holds member vaults.
- No shadow auth user is created per member.

Any of those would be a PATCH.

**The whole class is impossible**, tested on REAL Postgres (pgserver, `tests/test_s336_keep_owners.py`), with 037 → 042's foreign keys → 048 → 050 applied as production has them:

- a member's vault saves, reads masked, and deletes (key shredded);
- an account holder's vault saved BEFORE 050 still opens after it, with row counts the same;
- the following are refused by the database itself:
  - a key for an unknown id;
  - an owner with both ids, or neither;
  - an item whose owner row doesn't exist.

## The demo fixes

2. **Readable on the dark theme.** /group and /vault draw from ONE palette (`frontend/lib/group-theme.ts`). Every text-on-background pair is at least 4.5:1 (WCAG AA); a test computes each ratio. The buttons are real buttons.
3. **"Book all" with nothing to book** answers with a short list of taps instead of a paragraph, e.g. "18 over limit — book anyway?" · "2 need their vault — invite".
   - The first tap books those workers over the limit through the same card and the same Yes.
   - The second invites those workers.
4. **Swap with a newcomer.** If the newcomer isn't on the list, the swap box takes their city and grade, adds them through the same upload, and invites them to their vault in the same flow. The swap then runs once their vault is filled.
5. **S2.** The 📎 accepts a group list (csv, xlsx or a photo), read by the same reader as /group (`POST /api/booking/group/upload`). S2 links to /group once there is a movement.
