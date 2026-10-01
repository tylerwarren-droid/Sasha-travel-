/**
 * S-66 (EU spec) step 2 · ONE booking client for every surface that books: the booking console (Ladder, PhoneCall)
 * and Sasha's chat (ChatBooking). Every request goes through /api/booking-proxy — the founder's session, and the
 * booking key added on the server (lib/booking-api.ts) — so the browser never holds the key.
 *
 * Nothing here decides anything: the server compares hashes, re-checks opt-outs, holds the caps. A refusal is
 * returned with the server's own rule and words, for the surface to show unchanged.
 */
import { bookingUrl, bookingHeaders } from '@/lib/booking-api'

export type Res = { ok: boolean; status: number; json: Record<string, unknown> }

/** The sentence a surface shows when there is no founder session (401): no booking buttons, only this. */
export const FOUNDER_ONLY = "Booking is only open to the founder's account for now."

export async function bookingReq(path: string, body?: unknown, timeoutMs = 30000): Promise<Res> {
  const ctl = new AbortController()
  const timer = setTimeout(() => ctl.abort(), timeoutMs)
  let r: Response
  try {
    r = await fetch(bookingUrl(path), body === undefined
      ? { headers: bookingHeaders(), signal: ctl.signal }
      : { method: 'POST', headers: bookingHeaders(), body: JSON.stringify(body), signal: ctl.signal })
  } catch (e) {
    throw new Error((e as Error).name === 'AbortError' ? `Sasha's server did not answer within ${timeoutMs / 1000}s` : `could not reach Sasha's server (${(e as Error).message})`)
  } finally { clearTimeout(timer) }
  let json: Record<string, unknown> = {}
  try { json = await r.json() } catch { /* reported by its status */ }
  return { ok: r.ok, status: r.status, json }
}

/** "rule — message", as the server said it */
export const refusal = (j: Record<string, unknown>, status: number) =>
  `${typeof j.rule === 'string' ? j.rule : `HTTP ${status}`}${typeof j.message === 'string' ? ` — ${j.message}` : ''}`

export type Candidate = { place_id: string; name: string | null; address: string | null; country: string | null; phone: string | null
  website: string | null; type: string | null; status: string | null; listing_url: string
  // S-68 step 2 · as the listing gives them; null when it doesn't say (never 0)
  rating?: number | null; rating_count?: number | null; price_level?: number | null
  location?: { lat: number; lng: number } | null; hours_periods?: unknown[] | null
  // S-68 step 3 · from the place the guest named; the server's own words ("1.2 km away (straight line)")
  distance_m?: number | null; distance?: string | null
  // S-68 step 4 · at the time asked for, by its listing's hours; the server's own words ("Closed Tue 15:00 (opens 17:00)")
  open_at?: { known: boolean; open: boolean | null; words: string }
  // S-68 step 5 · before a pick, from the listing alone; the real ladder comes from the read
  books?: { how: 'call' | 'site' | 'you'; words: string }
  rating_words?: string; price_words?: string }
// S-68 step 6 · every chip's order, computed once on the server: a re-sort is no new search
export type Ranking = { default: string; chips: Record<string, string>; orders: Record<string, string[]>
  groups: Record<string, 'main' | 'hours_unknown' | 'closed_then' | 'closed_temporarily'>; count: string; explainers: Record<string, string> }
export type Rung = { rung: string; available: boolean; fact_index: number | null; value: string; source_label: string; why_not: string | null }

export const findVenues = (what: string, where: string, country?: string, near?: string, openAt?: string) =>
  bookingReq('/api/booking/venues/find', { what, where, country: country || undefined, near: near || undefined, open_at: openAt || undefined })
// S-68 step 9 · style for the cards shown (≤ 5), from each venue's own website; AI-summarised, quoted, not stored
export type Style = { label?: string; tags?: { tag: string; quote: string }[]; source?: string; why?: string }
export const styleVenues = (what: string, venues: { place_id: string; website: string | null }[]) =>
  bookingReq('/api/booking/venues/style', { what, venues }, 60000)
export const readVenue = (q: { name: string; city: string; country?: string; website?: string; place_id?: string; asked_for?: string }) =>
  bookingReq('/api/booking/venues/read', { name: q.name, city: q.city, country: q.country || undefined, website: q.website || undefined,
    ...(q.place_id ? { place_id: q.place_id, asked_for: q.asked_for } : {}) })
export const prepareCall = (body: Record<string, unknown>) => bookingReq('/api/booking/calls', body)
export const approveCall = (callId: string, sha256: string, approval: { how: 'button' | 'voice' | 'chat'; said: string | null }) =>
  bookingReq(`/api/booking/calls/${callId}/place`, { read_back_sha256: sha256, approval })
export const getCall = (callId: string) => bookingReq(`/api/booking/calls/${callId}`)
export const reservations = () => bookingReq('/api/booking/reservations')
