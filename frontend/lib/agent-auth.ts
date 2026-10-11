/**
 * Sasha 213 · WHO is talking to Sasha's agent (/next): the founder (his session cookie → `x-sasha-session: founder` with the
 * booking key, as before) OR a signed-in GUEST (their own Supabase session → `Authorization: Bearer <their token>`, which the
 * backend verifies itself — booking_signer.identity). Anyone else: null → 401. A guest is never the founder, and the
 * booking key never reaches a guest's browser. SERVER ONLY.
 */
import { CLIENT_KEY } from '@/lib/api'
import { actingAs } from '@/lib/acting-as'

export async function agentHeaders(): Promise<Record<string, string> | null> {
  const extra: Record<string, string> = CLIENT_KEY ? { 'X-Client-Key': CLIENT_KEY } : {}
  // Sasha 241 · WHO IS ACTING (lib/acting-rule.mjs): a real sign-in wins over the founder cookie; the founder over the auto guest
  const who = await actingAs()
  if (!who) return null
  if (who.kind === 'founder') {
    const key = (process.env.SASHA_BOOKING_KEY ?? '').trim()
    return key ? { 'x-sasha-session': 'founder', 'x-sasha-booking-key': key, ...extra } : null
  }
  return { authorization: `Bearer ${who.accessToken}`, ...extra }
}
