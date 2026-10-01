/**
 * S-62 step 0 · WHO is signed in, for a server route that writes. SERVER ONLY.
 *
 * Today the one session is the founder's (lib/founder-session.ts). S-62 step 4 adds a Supabase guest session here,
 * verified with Supabase — never a header that merely says who someone is. ⛔ Fails closed: no valid session, null.
 */
import { cookies } from 'next/headers'
import { COOKIE, valid } from '@/lib/founder-session'

export type SignedIn = { who: 'founder' }

export async function signedIn(): Promise<SignedIn | null> {
  const store = await cookies()
  return valid(store.get(COOKIE)?.value) ? { who: 'founder' } : null
}
