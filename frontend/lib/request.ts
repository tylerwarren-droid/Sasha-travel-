/**
 * Sasha 348 · THE ONE REQUEST CLIENT — every request a page (or a route, or a library) makes goes through here, and nowhere else touches
 * the network. The prebuild (scripts/check-outcome-surfaces.mjs) REFUSES a direct fetch( / new EventSource( / new WebSocket( /
 * navigator.sendBeacon( / axios anywhere else in the frontend — zero exceptions. Built on lib/outcome: a request's failure is always told
 * (named, before the caller sees it), so even a caller that handles it quietly leaves a trace with its name.
 *
 *   reach(input, init)       fetch's own signature → a Response (throws on a network failure, after telling it). The streams, the blobs,
 *                            the audio — anything that needs the Response itself.
 *   request(url, init)       JSON in and out → { ok, status, json } — NEVER throws: a network failure is { ok: false, status: 0 } with
 *                            words in json.message (lib/outcome's heard() reads them)
 *   events(url, init)        new EventSource's signature → the EventSource, its drops told
 *   socket(url, protocols)   new WebSocket's signature → the WebSocket, its errors told
 *   beacon(url, data)        navigator.sendBeacon's signature → whether it was queued; when it can't be, the same request through reach
 *   axios                    the few axios calls CTO files make (axios.post), on reach: { data, status }, a non-2xx throws — as axios does
 *
 * Moving a file onto it is mechanical (`node scripts/one-client.mjs --write`, also Stage B after a CTO drop): each of the above has the
 * signature of what it replaces.
 */
import { failed, toConsole } from './outcome'

export type Res = { ok: boolean; status: number; json: Record<string, unknown> }

const where = (input: RequestInfo | URL | string): string => {
  try {
    const u = typeof input === 'string' ? input : input instanceof URL ? input.href : (input as Request).url
    return new URL(u, 'http://x').pathname
  } catch { return 'a request' }
}

/** THE one place a request leaves the frontend. */
export async function reach(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  try {
    return await globalThis.fetch(input, init)
  } catch (e) {
    if (!(e instanceof Error && e.name === 'AbortError')) toConsole(failed(`The request to ${where(input)}`, e))   // an abort is the caller's own
    throw e
  }
}

/** JSON in, JSON out, never throws — the failure comes back as words, for heard() to say. */
export async function request(url: string, init?: RequestInit & { timeoutMs?: number }): Promise<Res> {
  const ctl = new AbortController()
  const timer = init?.timeoutMs ? setTimeout(() => ctl.abort(), init.timeoutMs) : null
  try {
    const r = await reach(url, { ...init, signal: init?.signal ?? ctl.signal })
    let json: Record<string, unknown> = {}
    try { json = await r.json() } catch { json = {} }   // a body that isn't JSON: its status says what happened
    return { ok: r.ok, status: r.status, json }
  } catch (e) {
    const timedOut = e instanceof Error && e.name === 'AbortError' && init?.timeoutMs
    return { ok: false, status: 0, json: { message: timedOut ? `Sasha's server did not answer within ${Math.round(init!.timeoutMs! / 1000)}s`
      : `Sasha's server couldn't be reached (${e instanceof Error ? e.message : 'no connection'})` } }
  } finally { if (timer) clearTimeout(timer) }
}

/** new EventSource, its drops told (it reconnects on its own; each drop is named once). */
export function events(url: string | URL, init?: EventSourceInit): EventSource {
  const es = new EventSource(url, init)
  es.addEventListener('error', () => toConsole(`The live updates from ${where(url)} dropped — reconnecting.`))
  return es
}

/** new WebSocket, its errors told. */
export function socket(url: string | URL, protocols?: string | string[]): WebSocket {
  const ws = new WebSocket(url, protocols)
  ws.addEventListener('error', () => toConsole(`The connection to ${where(url)} failed.`))
  return ws
}

/** navigator.sendBeacon — when the browser won't queue it, the same request through reach (keepalive), its failure told. */
export function beacon(url: string | URL, data?: BodyInit | null): boolean {
  if (typeof navigator !== 'undefined' && navigator.sendBeacon?.(url, data)) return true
  reach(url, { method: 'POST', body: data ?? null, keepalive: true }).catch((e: unknown) => toConsole(failed(`The note to ${where(url)}`, e)))
  return false
}

/** axios.post as the CTO's files use it, on reach: resolves { data, status } for a 2xx, rejects with { response: { data, status } } else. */
// eslint-disable-next-line @typescript-eslint/no-explicit-any -- axios own default: the CTO code reads response.data freely
export const axios = {
  async post<T = any>(url: string, data?: unknown, config?: { headers?: Record<string, string>; timeout?: number }): Promise<{ data: T; status: number }> {
    const r = await request(url, { method: 'POST', headers: { 'content-type': 'application/json', ...(config?.headers || {}) },
      body: JSON.stringify(data ?? {}), timeoutMs: config?.timeout })
    if (r.ok) return { data: r.json as T, status: r.status }
    throw Object.assign(new Error(String(r.json.message || `Request failed with status code ${r.status}`)), { response: { data: r.json, status: r.status }, isAxiosError: true })
  },
}
