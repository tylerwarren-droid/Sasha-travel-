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

/**
 * Sasha 249 · ONE IDENTITY (one-truth-spec §1.1): what a page shows is whoami's `acting` — the server's decide() above —
 * and NEVER re-derived on the page from the email's suffix (SignedInLine and KeepAcrossDevices did). Unknown → nobody.
 * @param {{ acting?: unknown } | null | undefined} w  the /api/auth/whoami answer
 * @returns {'user'|'founder'|'guest'|null}
 */
export function actingOf(w) {
  const a = w && typeof w === 'object' ? w.acting : null
  return a === 'user' || a === 'founder' || a === 'guest' ? a : null
}

/**
 * Sasha 249 · the badge for a whoami answer: badge(actingOf(w), w.email).
 * @param {{ acting?: unknown, email?: string | null } | null | undefined} w
 */
export function badgeFor(w) {
  return badge(actingOf(w), w?.email ?? null)
}

/**
 * Sasha 242 · PER-PERSON browser storage goes when the person acting changes (sign-out, another sign-in) — found by EU's walk
 * (row 730): after a new sign-in, Trip showed trips the account never made. Device preferences (the mic, mute, a closed panel) stay.
 */
export const PER_PERSON_LOCAL = ['sasha_last_session', 's2_met', 's2_hello', 'kanoe_onboarding_draft']
export const WHO_KEY = 'sasha.who'

/** The identity this browser acts as, as a short key ("founder", "user:a@b.c", "guest:guest-…", "none"). */
export function whoKey(acting, email) {
  if (acting === 'founder') return 'founder'
  if (acting === 'user' || acting === 'guest') return `${acting}:${String(email || '').toLowerCase()}`
  return 'none'
}

/** True when what was stored belongs to someone else (a first visit — nothing stored — is not a change). */
export function changed(prev, now) {
  return typeof prev === 'string' && prev !== '' && prev !== now
}
