/**
 * Sasha 249 · ONE IDENTITY (one-truth-spec §1.1): the headers that tell Sasha's backend WHO IS ACTING — built here, once, for
 * every proxy (lib/agent-auth.ts agentHeaders: the agent routes, /api/booking-proxy, /api/sasha). Until 249 the founder's
 * headers were built three times, each a little differently. Pure (tested in scripts/agent-headers.test.mjs).
 *   · nobody → null (the route answers 401; nothing is forwarded);
 *   · the founder → `x-sasha-session: founder` WITH the booking key (the backend accepts the word only with the key; no key
 *     configured → null), and his address so guests beside him are never capped (Sasha 159);
 *   · a signed-in account or the automatic guest → their own Supabase token, which the backend verifies itself.
 * The booking key never goes with a guest's token from here (the booking proxy adds it as the gate key, not as identity).
 */

/**
 * @param {{ kind: 'founder' } | { kind: 'user' | 'guest', accessToken: string } | null | undefined} acting
 * @param {{ key?: string, clientKey?: string, ip?: string }} [env]
 * @returns {Record<string, string> | null}
 */
export function headersFor(acting, { key = '', clientKey = '', ip = '' } = {}) {
  if (!acting) return null
  const extra = clientKey ? { 'X-Client-Key': clientKey } : {}
  if (acting.kind === 'founder') {
    if (!key) return null
    return { 'x-sasha-session': 'founder', 'x-sasha-booking-key': key, ...(ip ? { 'x-sasha-client-ip': ip } : {}), ...extra }
  }
  if ((acting.kind === 'user' || acting.kind === 'guest') && acting.accessToken) {
    return { authorization: `Bearer ${acting.accessToken}`, ...extra }
  }
  return null
}

/** The caller's address, as the proxies read it (first x-forwarded-for, else x-real-ip). */
/** @param {{ get(name: string): string | null }} headers */
export function clientIp(headers) {
  return (headers.get('x-forwarded-for') ?? '').split(',')[0].trim() || headers.get('x-real-ip') || ''
}
