# S-62 — guest accounts: what is built, what holds it, and how it ships

*Sasha tab, 1 Oct 2026 (Sasha 67). Spec: `docs/sasha/S-62-guest-accounts.md`. Steps 1–6 are built and tested on the
**local branch `s62-guest-accounts`, which is NOT pushed** (main deploys).*

## ⛔ The hold

**Nothing that opens guest sign-up is deployed until the founder confirms the service-role key rotation (step 0).**

- The branch is not pushed: pushing main deploys both Vercel and Railway.
- **Second lock, after merge:** guest sign-in is closed unless `GUEST_SIGN_IN_ENABLED=1` on Vercel.
  - `/sign-in` then says "isn't open yet".
  - `/auth/callback` refuses.
  - No guest session is accepted anywhere.

## What is built (branch commits)

| Step | What | Tests |
|---|---|---|
| 1 | The backend verifies WHO. A Supabase access token is checked: ES256 signature against the project's public JWKS, issuer, audience, role and expiry. The founder's session (`x-sasha-session: founder`) maps to `FOUNDER_ACCOUNT_ID` once set, and to the demo account until then. The demo is used only when asked for. No account → 401 `account_required`. | `tests/test_identity.py`: forged, unknown-key, expired, other-project, wrong-audience, anon-role and garbage tokens; keys unreachable fails closed (503) |
| 2 | Isolation: guest B gets nothing of A's on any route. Every read, call, email and link GET and approve route, the cancel, the intent approval, devices and reservations answer B **exactly as for an id that never existed**. Calls and emails are capped per account (`SASHA_CALLS_PER_ACCOUNT_PER_DAY` 10, `SASHA_EMAILS_PER_ACCOUNT_PER_DAY` 5) as well as per server. | memory **and** Postgres |
| 3 | `/sign-in` sends a magic link. `/auth/callback` exchanges the code, and a failure goes back with Supabase's reason. Sign-out. The sign-in page names Kanoe Technologies SL and links the privacy notice. Next 16 has no middleware of ours; the CTO's `middleware.ts` is untouched. | typecheck and build |
| 4 | The booking proxy accepts a guest verified with Supabase and forwards the token, which the backend verifies again. The founder session names itself. **Onboarding stays founder-only**: a guest must never upsert a business's `clients` row. | build guard |
| 5 | `guest_contacts` (**015, not applied**), with GET/PUT/DELETE `/contact` on the caller's own account. A save must carry the current consent sentence's version and sha256. Change and delete. The chat card uses saved details, saves them only under the sentence shown, and deletes them on request. | memory and Postgres |
| 6 | The chat says who is booking (founder, or the guest's email, with Sign out) and asks a stranger to sign in. It lives in our booking card, so the CTO's `SashaChat.tsx` is untouched. | typecheck and build |

## Step 7: the CTO's half (the founder handles the CTO)

**Blocking for strangers, not for the founder and trusted testers.** In `backend/app/` (his):

1. The chat sends the Supabase access token with each conductor call.
2. `chat_store` and `api/chats.py` take the account from the **verified** token, not `DEMO_USER_ID`.
3. **`GET /api/chats/{session_id}` checks ownership.** Today it returns anyone's conversation, including a name and
   mobile a guest typed.
4. The demo id stays for the public demo pages only.

booking_signer's `identity.verify_token` can be imported for (2): it is outside `backend/app/` and survives his drops.

## Merge and deploy order (after the founder confirms the rotation)

1. **Founder:** rotate the service-role key. Set `SUPABASE_SERVICE_ROLE_KEY` on Vercel and Railway himself (rule 17).
   Tell this tab.
2. **This tab, live:**
   - the old key is refused (a REST read answers 401);
   - a signed-in onboarding save works (it writes one `clients` row, which is then removed with its `.error` checked);
   - a booking works end to end.
3. **Founder, Supabase dashboard:**
   - Auth → URL configuration: add `https://project.kanoe.ai/auth/callback` to the redirect URLs;
   - Auth → SMTP: Resend credentials, sender on `kanoe.ai` (he enters them; rule 17).
   - Optionally, his own auth user. Then `FOUNDER_ACCOUNT_ID` on Railway. Until it is set, his bookings stay under the
     demo account, as today. Calma is there.
4. **Founder approves 015.** This tab runs it via `railway run` (preview, transaction, verify).
5. **Vercel env (founder):** `NEXT_PUBLIC_SUPABASE_URL` and `NEXT_PUBLIC_SUPABASE_ANON_KEY` (the publishable key).
   `GUEST_SIGN_IN_ENABLED` is **left unset**.
6. **Merge `s62-guest-accounts` → main and push through the full gate.**
   - **Vercel deploys before Railway matters:** the old backend ignores the proxy's new `x-sasha-session` header, but the
     new backend refuses a request without it.
   - So, check Vercel is READY first, then let Railway deploy.
   - Then check the founder's booking page still works (founder session → his account).
7. **Proof (step 8)**, with `GUEST_SIGN_IN_ENABLED=1` set by the founder for the test:
   - two test guests (the founder's second address plus one other) sign in by magic link;
   - each books by phone in chat;
   - SQL shows each reservation under its own `account_id`;
   - B gets 404 for A's call;
   - after step 7, B can't read A's chat.
   Then the founder decides whether `GUEST_SIGN_IN_ENABLED` stays on.

## Decisions taken here (the founder can change them)

- **Per-account daily caps:** 10 calls and 5 emails per account per 24 h, set by env. They sit beside the global 20 calls
  and 5 emails.
- **Onboarding is founder-only, not "any signed-in user"**, until business accounts exist.
- **The founder maps to the demo account until `FOUNDER_ACCOUNT_ID` is set**, so his existing reservations don't vanish.

## Shipped — 1 Oct 2026 (Sasha 73), guest sign-in HELD CLOSED

- **Step 0: done by moving the database (S-69).**
  - The leaked key's project is paused: it answers 540 to everything.
  - The new keys are in place, and an onboarding save works.
  - A booking read works against the new database.
- **015** applied on sasha-prod: guest_contacts, RLS on, no policies, 0 rows.
- **Auth on sasha-prod** (Management API, read back):
  - site URL `https://project.kanoe.ai`, with `/auth/callback` as the only redirect;
  - SMTP via Resend (`smtp.resend.com:465`) from `sasha@booking.kanoe.ai`, verified in Resend. It uses a **dedicated
    Resend key restricted to sending from booking.kanoe.ai** ("supabase-auth-smtp (sasha-prod)"), not Sasha's own key;
  - magic-link and confirmation emails name Sasha and Kanoe Technologies SL, and link the privacy notice;
  - JWT signing ES256.
- **Merged and deployed (c842326).** Vercel and Railway both went live.
- **Live checks:**
  - the founder's booking route works through the new identity check (reservations 200, Calma confirmed);
  - whoami says founder;
  - an unsigned booking call answers 401 `sign_in_required`;
  - an unsigned onboarding save answers 401;
  - `/sign-in` says "isn't open yet";
  - a Supabase sign-up answers 422 `signup_disabled`.
- **To OPEN guest sign-in, the founder flips TWO switches:**
  1. Supabase sasha-prod: Auth → "Allow new users to sign up" (`disable_signup` false);
  2. Vercel sasha-heygen: `GUEST_SIGN_IN_ENABLED=1`, then redeploy.
  - Then run the step-8 proof.
  - Step 7 (chat history per account, and the ownership check on `/api/chats/{id}`) is still open. It is the line for
    strangers.

## Step 7 shipped — 1 Oct 2026 (Sasha 74, 71ffe2f)

- **The chat sends a signed-in guest's Supabase token** (`frontend/lib/guest-auth.ts`, five "S-62 step 7" lines in
  SashaChat, and YouPanel's trips fetch). The backend verifies it exactly as bookings are
  (`app/services/chat_account.py` → `booking_signer.identity`).
- **Theirs alone:**
  - chats (list, and read by id);
  - the conductor: a session someone else owns is never appended to or read, and a new one starts;
  - classify: another account's itinerary is never looked into;
  - payments: only your own itinerary or offer can be paid for;
  - trips.
  - Someone else's session answers exactly as one that does not exist.
- **No token** means the public demo, as before. **A bad token is refused** (401), never the demo.
- **Live:**
  - an anonymous `/api/chats` answers 200;
  - a session that is not yours answers 404;
  - a bad token answers 401 `account_token_invalid`;
  - classify answers anonymously;
  - the founder's booking route is unaffected.
  - Tests: `tests/test_chat_accounts.py` (6).
- **Guest sign-in stays closed.** To open it, the founder flips two switches: Supabase "allow new users to sign up", and
  Vercel `GUEST_SIGN_IN_ENABLED=1`. Then the step-8 proof runs, with two guests.
