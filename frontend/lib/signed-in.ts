/**
 * S-62 step 0 · WHO is signed in, for a server route that writes. SERVER ONLY.
 *
 * Today the one session is the founder's (lib/founder-session.ts). S-62 step 4 adds a Supabase guest session here,
 * verified with Supabase — never a header that merely says who someone is. ⛔ Fails closed: no valid session, null.
 */
import { cookies } from 'next/headers'
import { COOKIE, valid } from '@/lib/founder-session'
import { guest } from '@/lib/guest-session'

export type SignedIn = { who: 'founder' } | { who: 'guest'; id: string }

export async function signedIn(): Promise<SignedIn | null> {
  const store = await cookies()
  if (valid(store.get(COOKIE)?.value)) return { who: 'founder' }
  const g = await guest()   // S-62 step 4 · null while guest sign-in is closed
  return g ? { who: 'guest', id: g.id } : null
}

/** Writes that only the founder may make (onboarding a business writes `clients` with the service-role key). */
export async function founderSignedIn(): Promise<boolean> {
  const store = await cookies()
  return valid(store.get(COOKIE)?.value)
}
