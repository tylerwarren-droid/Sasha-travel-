/**
 * S-62 step 0 · WHO is signed in, for a server route that writes. SERVER ONLY.
 *
 * Today the one session is the founder's (lib/founder-session.ts). S-62 step 4 adds a Supabase guest session here,
 * verified with Supabase — never a header that merely says who someone is. ⛔ Fails closed: no valid session, null.
 */
import { actingAs, founderActing } from '@/lib/acting-as'

export type SignedIn = { who: 'founder' } | { who: 'guest'; id: string }

/** Sasha 241 · who is ACTING (lib/acting-rule.mjs): a real sign-in wins over the founder cookie. A signed-in account (real or the
 *  automatic guest) is { who: 'guest', id } here, as before. */
export async function signedIn(): Promise<SignedIn | null> {
  const who = await actingAs()
  if (!who) return null
  return who.kind === 'founder' ? { who: 'founder' } : { who: 'guest', id: who.id }
}

/** Writes that only the founder may make — only when the founder is the one ACTING (Sasha 241: not when another account
 *  is signed in on a browser that also holds the founder cookie). */
export async function founderSignedIn(): Promise<boolean> {
  return founderActing()
}
