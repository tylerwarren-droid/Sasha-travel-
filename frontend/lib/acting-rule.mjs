/**
 * Sasha 241 · WHO IS ACTING — the one rule, pure (tested in scripts/acting-rule.test.mjs; used by lib/acting-as.ts):
 *   1. a REAL signed-in account (a Supabase session with an invited, non-guest email) — always wins;
 *   2. else the founder's own cookie (sasha_founder);
 *   3. else the automatic browser guest (guest-…@guests.kanoe.ai, the "no sign-in wall" session);
 *   4. else nobody.
 * Found 11 Oct (Sasha 240): the founder cookie overrode every session, so a browser that held it acted as Tyler even after
 * another account signed in. An automatic guest never outranks the founder: every browser has one (Tyler's too).
 */
export const GUEST_DOMAIN = '@guests.kanoe.ai'

/** @param {string | null | undefined} email */
export function isAutoGuest(email) {
  return typeof email === 'string' && email.toLowerCase().endsWith(GUEST_DOMAIN)
}

/**
 * @param {{ guestEmail?: string | null, hasSession?: boolean, founderCookie?: boolean }} [who]
 * @returns {'user'|'founder'|'guest'|null}
 */
export function decide({ guestEmail = null, hasSession = false, founderCookie = false } = {}) {
  if (hasSession && !isAutoGuest(guestEmail)) return 'user'
  if (founderCookie) return 'founder'
  if (hasSession) return 'guest'
  return null
}

/** The badge: always the account actually acting. */
/**
 * @param {'user'|'founder'|'guest'|null} kind
 * @param {string | null | undefined} [email]
 */
export function badge(kind, email) {
  if (kind === 'founder') return 'Founder: Tyler'
  if (kind === 'user') return `Signed in as ${email || 'you'}`
  return 'Guest'
}
