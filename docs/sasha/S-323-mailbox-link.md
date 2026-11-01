# Sasha 323 · the mailbox link never dies silently; "My bookings" is demo-clean

Tyler: "of course I want email connection" (built in Oct). It was found broken from 20 Oct to 1 Nov, and nobody was told.

## Root test (written before the code)

1. **The one truth** for "is the mailbox link alive" is the last token-refresh result, kept on the link (`mailbox_links`):
   - `needs_reconnect_at`: Google refused the refresh token (its code, e.g. `invalid_grant`, goes to the log with it);
   - `last_sync_at`: the last refresh that worked.

   No new column, so no SQL for Tyler to run.

   Every sync starts with a refresh, so every sync re-reads the truth.
2. **PATCH test.** A reconnect reminder on a timer is a patch. Tyler is told by the refresh result itself, in the sync that finds it,
   once (`told_reconnect_at`). A reconnect clears both stamps, so the next death is told again.
3. **Whole class: can the link be dead for more than one sync without Tyler being told?** No:
   - **A permanent refusal** (any code except temporary HTTP 5xx/429 or a network failure) marks it dead and tells him in the same
     sync.
   - **A link already dead before this fix** (his, since 20 Oct) has `needs_reconnect_at` and no `told_reconnect_at`. The first sync
     after the deploy tells him. The loop syncs at boot, then every 6 h.
   - **A temporary error** is not a death. It is logged and retried on the next sync.

## Why it died on 20 Oct

- **Consent:** 13 Oct. **Death:** 20 Oct, exactly 7 days later. Google issues refresh tokens that expire after 7 days to an OAuth app
  whose publishing status is "Testing" and whose user type is "External"; once expired, the refresh answers `invalid_grant`.
- **What the code shows:** `mailbox.sync` marks a link `needs_reconnect_at` ONLY on `connection_invalid_grant`, then skipped it on
  every later sync without a word. That was the silent part.
- **What is missing:** Railway keeps the last 50 deployments, back to 27 Oct, so the 20 Oct log lines are gone. Sasha's database rows
  can't be read from this session. From this fix on, every refusal is logged with Google's code (`[mailbox] the Gmail link's
  token refresh was refused: invalid_grant`).
- **The same expiry hits the Google Calendar link** (same OAuth app); `calendar_sync._expired` already tells once.

## Tyler's steps: move the OAuth app to "In production" (his to click)

Google Cloud console → the project that owns the OAuth client in Railway's `SASHA_GOOGLE_OAUTH_CLIENT_ID`.

1. Open https://console.cloud.google.com/auth/audience. On older consoles it's *APIs & Services → OAuth consent screen*. Pick the
   project at the top.
2. Under **Publishing status: Testing**, press **Publish app**, then confirm.
3. What changes:
   - **Refresh tokens no longer expire after 7 days.** They last until revoked, password-reset or unused for 6 months.
   - **The 100-test-user cap and the test-user list stop applying.** Anyone with a Google account can reach the consent screen. Sasha
     still lets only invited accounts connect (the invitation check is Sasha's, not Google's).
   - **Gmail read-only is a *restricted* scope, and Calendar a *sensitive* one.** Until Google verifies the app, everyone who connects
     sees **"Google hasn't verified this app"**. They press **Advanced → Go to Sasha (unsafe)** once. An unverified app is capped at
     **100 users ever**, which is plenty for the beta.
   - **Full verification** (the restricted-scope security assessment) is only needed to lift the warning and the cap. It's not needed
     for Tyler and invited testers.
4. Then reconnect Gmail (and Calendar) once on **/you**. Tokens issued while the app was in Testing keep their 7-day life; the new
   ones don't.

## Outlook

- tyler@kanoe.ai is on Microsoft 365 (kanoe.ai's MX is `kanoe-ai.mail.protection.outlook.com`). Production reports Outlook
  `configured: true`.
- It connects the same way, read-only: **/you → Outlook** (CR 86: delegated Mail.Read, sealed in the vault, never sends, moves or
  deletes).
- Today it feeds the subscription finder (receipts) only. Booking confirmations come from the Gmail sync.

## My bookings (/you and S2's trip)

- **One rule:** `journeys.booking_view`.
  - Upcoming first, soonest first.
  - Past, cancelled, declined and failed bookings sit behind **Show history**, newest first.
  - Kanoe's test venues and scratch/test bookings are never shown to a person whose access record is live.
- /you's My bookings now reads the same list as the trip board (`/api/booking/journeys`), so a booking made through AgAPI shows
  there too.
