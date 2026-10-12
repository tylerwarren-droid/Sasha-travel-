/**
 * Sasha 213 · WHO is talking to Sasha's agent (/next): the founder (his session cookie → `x-sasha-session: founder` with the
 * booking key, as before) OR a signed-in GUEST (their own Supabase session → `Authorization: Bearer <their token>`, which the
 * backend verifies itself — booking_signer.identity). Anyone else: null → 401. A guest is never the founder, and the
 * booking key never reaches a guest's browser. SERVER ONLY.
 * Sasha 249 · ONE agentHeaders(acting) for every proxy — the agent routes, /api/booking-proxy and /api/sasha — built by
 * lib/agent-headers.mjs headersFor(). With no `acting` given it asks actingAs() (lib/acting-as.ts), the one frontend rule.
 */
import { CLIENT_KEY } from '@/lib/api'
import { actingAs, type Acting } from '@/lib/acting-as'
import { headersFor } from '@/lib/agent-headers.mjs'

export { clientIp } from '@/lib/agent-headers.mjs'

export async function agentHeaders(acting?: Acting | null, opts: { ip?: string } = {}): Promise<Record<string, string> | null> {
  // Sasha 241 · WHO IS ACTING (lib/acting-rule.mjs): a real sign-in wins over the founder cookie; the founder over the auto guest
  const who = acting === undefined ? await actingAs() : acting
  return headersFor(who, { key: (process.env.SASHA_BOOKING_KEY ?? '').trim(), clientKey: CLIENT_KEY || '', ip: opts.ip || '' })
}
