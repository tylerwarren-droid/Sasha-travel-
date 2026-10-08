/**
 * Sasha 213 · WHO is talking to Sasha's agent (/next): the founder (his session cookie → `x-sasha-session: founder` with the
 * booking key, as before) OR a signed-in GUEST (their own Supabase session → `Authorization: Bearer <their token>`, which the
 * backend verifies itself — booking_signer.identity). Anyone else: null → 401. A guest is never the founder, and the
 * booking key never reaches a guest's browser. SERVER ONLY.
 */
import { cookies } from 'next/headers'
import { CLIENT_KEY } from '@/lib/api'
import { COOKIE, valid } from '@/lib/founder-session'
import { guest } from '@/lib/guest-session'

export async function agentHeaders(): Promise<Record<string, string> | null> {
  const store = await cookies()
  const extra: Record<string, string> = CLIENT_KEY ? { 'X-Client-Key': CLIENT_KEY } : {}
  if (valid(store.get(COOKIE)?.value)) {
    const key = (process.env.SASHA_BOOKING_KEY ?? '').trim()
    return key ? { 'x-sasha-session': 'founder', 'x-sasha-booking-key': key, ...extra } : null
  }
  const g = await guest()
  return g ? { authorization: `Bearer ${g.accessToken}`, ...extra } : null
}
