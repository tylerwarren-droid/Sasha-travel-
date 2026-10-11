/**
 * Sasha 241 · WHO IS ACTING, server side — the one place every route asks (lib/acting-rule.mjs holds the rule, tested):
 * a real signed-in account wins over the founder cookie; the founder cookie wins over the automatic browser guest.
 * SERVER ONLY. Fails closed: nobody → null.
 */
import { cookies } from 'next/headers'
import { COOKIE, valid } from '@/lib/founder-session'
import { guest } from '@/lib/guest-session'
import { decide } from '@/lib/acting-rule.mjs'

export type Acting =
  | { kind: 'founder' }
  | { kind: 'user' | 'guest'; id: string; email: string | null; accessToken: string }

export async function actingAs(): Promise<Acting | null> {
  const store = await cookies()
  const founderCookie = valid(store.get(COOKIE)?.value)
  const g = await guest()
  const kind = decide({ hasSession: !!g, guestEmail: g?.email ?? null, founderCookie })
  if (kind === 'founder') return { kind: 'founder' }
  if ((kind === 'user' || kind === 'guest') && g) return { kind, id: g.id, email: g.email, accessToken: g.accessToken }
  return null
}

/** True only when the founder is the one acting (not merely holding the cookie under someone else's sign-in). */
export async function founderActing(): Promise<boolean> {
  return (await actingAs())?.kind === 'founder'
}
