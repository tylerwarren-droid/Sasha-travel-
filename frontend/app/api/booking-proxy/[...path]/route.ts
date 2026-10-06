import { cookies } from 'next/headers'
import { NextResponse } from 'next/server'
import { API_URL } from '@/lib/api'
import { COOKIE, valid } from '@/lib/founder-session'
import { guest } from '@/lib/guest-session'

/**
 * S-41 · The booking pass-through. The booking page calls THIS (same origin); it checks the founder's session and
 * only then calls the backend's /api/booking/… with SASHA_BOOKING_KEY, which the browser never sees.
 *
 * ⛔ No session → 401, and nothing reaches the backend. No key configured here → 503. A path outside the booking
 * routes is never forwarded.
 */
async function pass(request: Request, ctx: { params: Promise<{ path: string[] }> }): Promise<Response> {
  // S-62 step 4 · WHO: the founder's session, or a guest verified with Supabase (only while guest sign-in is open).
  // The backend is told which — the founder by name, a guest by their signed access token, which it verifies again.
  const store = await cookies()
  let who: Record<string, string>
  if (valid(store.get(COOKIE)?.value)) {
    // Sasha 159 · with his address, so guests on his devices and wifi are never capped
    const ip = (request.headers.get('x-forwarded-for') ?? '').split(',')[0].trim() || request.headers.get('x-real-ip') || ''
    who = { 'x-sasha-session': 'founder', ...(ip ? { 'x-sasha-client-ip': ip } : {}) }
  } else {
    const g = await guest()
    if (!g) {
      return NextResponse.json({ ok: false, rule: 'sign_in_required', message: 'Sign in to book with Sasha.' }, { status: 401 })
    }
    who = { authorization: `Bearer ${g.accessToken}` }
  }
  const key = (process.env.SASHA_BOOKING_KEY ?? '').trim()
  if (!key) {
    return NextResponse.json({ ok: false, rule: 'booking_key_not_configured', message: 'SASHA_BOOKING_KEY is not set on this deployment' }, { status: 503 })
  }
  const { path } = await ctx.params
  if (!path.length || path.some((p) => p === '..' || p.includes('/') || p === '')) {
    return NextResponse.json({ ok: false, rule: 'path_refused', message: 'not a booking route' }, { status: 400 })
  }
  const url = `${API_URL}/api/booking/${path.map(encodeURIComponent).join('/')}${new URL(request.url).search}`
  const init: RequestInit = { method: request.method, headers: { 'content-type': 'application/json', 'x-sasha-booking-key': key, ...who }, cache: 'no-store' }
  if (request.method !== 'GET') init.body = await request.text()
  let r: Response
  try {
    r = await fetch(url, init)
  } catch (e) {
    return NextResponse.json({ ok: false, rule: 'backend_unreachable', message: `Sasha's server could not be reached (${(e as Error).message})` }, { status: 502 })
  }
  // FastAPI puts a dependency's refusal under `detail`: lift it, so the page reads { rule, message } the same way
  let json: unknown = null
  try { json = await r.json() } catch { /* a non-JSON answer is reported by its status */ }
  const flat = json && typeof json === 'object' && 'detail' in (json as object) && typeof (json as { detail: unknown }).detail === 'object'
    ? (json as { detail: object }).detail : json
  return NextResponse.json(flat ?? { ok: false, rule: `HTTP ${r.status}` }, { status: r.status })
}

export const GET = pass
export const POST = pass
export const PUT = pass      // S-62 step 5 · the guest's saved details
export const DELETE = pass
