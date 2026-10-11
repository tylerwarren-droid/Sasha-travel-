# Sasha 240 — report (11 Oct 2026) · one-click sign-in for EU, the "Signed in as Tyler" guest, Vercel's failed build

No code changed in 240; this report is the only commit. Backend unchanged (Railway a0d36d66). The sign-in link itself is in the
mailbox only (row 727), never in this public repo.

## 0 · One-click sign-in for eu234: DONE
- **Format:** `https://project.kanoe.ai/auth/confirm?token_hash=<Supabase admin magiclink hashed_token>&type=magiclink&next=/s2`.
  `/auth/confirm` verifies it with Supabase (verifyOtp), sets the session cookie and redirects to `/s2`.
- **Proved on a throwaway scratch account** (43d5b187, deleted after):
  - opening the link → **307 → /s2**, session cookie set (1);
  - `GET /s2` → **200**;
  - the signed-in-only `/api/s2-memory` → **200** `{"ok":true,…}`;
  - the same link again → `/sign-in?error=Email link is invalid or has expired` (one use only).
- **eu234's own link:** generated fresh and **not opened**, so it's unspent. Posted as "EU234 LINK …" (row 727).
  - It works once and expires per Supabase's email-link setting.
  - A link preview (WhatsApp/Slack/iMessage) doesn't spend it: `/auth/confirm` answers previews with a static page.

## 1 · The "Signed in as Tyler" guest: FOUND (no code change)
- **Whose:** `036ee17b…` / `guest-79ca220e4786…@guests.kanoe.ai` is an **automatic browser guest**. It was created 5 Oct 2026 16:03:41 UTC by
  the "no sign-in wall" rule (`ensureGuest`) in that Chrome, and signed in once at 16:03:42.
  - It belongs to no person: 1 trip, 0 Keep, 0 Activity, 0 WhatsApp, 0 contact. Read-only check; nothing changed.
- **Why the label says Tyler:** it isn't a name typed in chat.
  - `WhoBadge` shows "Signed in as Tyler" only when `/api/auth/whoami` says `who: "founder"`.
  - whoami says founder whenever the browser holds the **founder cookie `sasha_founder`** (set by the founder passphrase gate, valid 365 days), whatever Supabase guest session it also holds.
  - That Chrome holds both, and the founder cookie wins.
- **The risk for EU's walk:** `agentHeaders()` follows the same rule, so in that Chrome **/s2 talks to the agent AS TYLER'S ACCOUNT**, even after the eu234 link (the founder cookie still wins).
- **Safe ways to walk:**
  - (a) open the eu234 link in a **separate Chrome profile or an Incognito window** (no founder cookie); or
  - (b) sign the founder out in that Chrome first (`DELETE /api/founder-session`); Tyler then signs in again with the passphrase after.
- **Not changed (needs Tyler's say):** the badge and the agent proxy could say "Signed in as Tyler — a guest session is also open", or a link sign-in could end the founder cookie. Both change how Tyler's own browser behaves.

## 2 · Vercel's failed production build: CAUSE NOT REACHABLE, mitigated
- **What GitHub's commit statuses show for 62d11f0:**
  - production `dpl_FZXtnP3u6TjS8AfqUh2P3fjVAsy3` started 12:08:16 and **failed at 12:08:35 (19 s)**;
  - the same sha's preview `dpl_AC9GU1a5y7zcbaLjs51dN2iKEd7S` started at the same second and was READY at 12:08:51;
  - that push started 6 Vercel builds (3 projects × branch + main) and 2 Railway builds at once;
  - `npx next build` passed here; the next push (dc3c869) built READY in production.
- **Not in our code.**
- **The log:** Vercel's API (via the MCP) returns 404 "Deployment not found" for *every* deployment's details and events here, READY ones included, and there's no authenticated Vercel CLI on this machine.
  - The log is in the Vercel dashboard (inspector link above), or via `npx vercel inspect dpl_FZXtnP3u6TjS8AfqUh2P3fjVAsy3 --logs` on a logged-in machine.
- **The pattern:** both failed builds (237's preview of 63c835e; 239's production of 62d11f0) came from pushes that sent the same sha to `sasha/NNN` and `main` within seconds, so twin builds of one sha ran in parallel.
- **Mitigation from now on:**
  - Push **only `main`**, so there's one build per sha.
  - After **every** push, confirm production for that sha is READY before saying it's shipped. If it's ERROR, push again or use Vercel's Redeploy; 239's case rebuilt READY.
  - This report's own push is the first one pushed that way.
