# Sasha 338 · Open sign-in, with every new person NOT live (Tyler, 4 Nov 11:45)

## 1 · melissa@virtique.it (done first)

**The invite list** is sasha-prod's Supabase Auth users. Supabase's public sign-up is off, so a sign-in link only went to an address that already had a user. "This address hasn't been invited" was SignInForm's wording for Supabase's own "signups not allowed".

Her user was created with Sasha's own admin key (in memory, under `railway run`). Her "Email me a sign-in link" works.

## Root test (written first)

**ONE place decides WHO may sign in:** `booking_signer/sign_up.py`, through `may_sign_in(email)`.

- The rule today is Tyler's: anyone with an email address.
- Supabase's own public sign-up stays OFF. So this rule is the only way to an account: the sign-in page asks it first (`POST /api/booking/sign-up`), it opens the account, and Supabase then emails the link.
- `ops.invite` only EMAILS an invitation; it decides nothing.

**ONE place decides WHAT a person may do for real:** AgAPI's `person_access` record, read through `agapi/person_access.py`.

- A brand-new person has no row, so their record is CLOSED:
  - test mode (the sandbox, payments TEST);
  - `real_venue_sends` off; `platform_submit` off; calls off; no mailboxes.
- That holds until Tyler marks them live on /admin/access.
- `agapi_route.person_mode` now reads ONLY that record. Live means only a row that says live; no row, or an unreadable record, means test.
- The second list it used to consult (the guest's `app_metadata.kanoe_test` marker) is no longer read for this. It was a PATCH: two places deciding test vs live.
- This reverses Sasha 253's choice that a real guest with no row should go live.

**Daily AI budget** (`app/agent/sasha.py`, `over_budget`), read from the same record:

| Person | Turns a day | Turns a minute |
|---|---|---|
| Not live | **60** (`SASHA_DAILY_TURNS_NEW`) | 10 |
| Live | 300, as before | 10 |
| Founder | exempt, as before | 10 |

Any allow-list of addresses, or any second test/live list, is a PATCH.

**The whole class** (`tests/test_s338_open_sign_in.py`):

- A brand-new email opens an account. The answer is the same whether or not it existed (no enumeration).
- That person chats: one turn answers.
- Nothing real is sent or charged:
  - every AgAPI family routes to the sandbox, even with every route set live;
  - their record has no real power;
  - their day is capped at 60 turns.
- Only `sign_up.py`, `ops.py` (the invitation) and `guest_accounts.py` (anonymous guest sessions) create auth users.
- `person_mode` reads no marker.
