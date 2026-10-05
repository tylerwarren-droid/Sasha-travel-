import { NextResponse } from 'next/server'
import { API_URL } from '@/lib/api'
import { founderSignedIn } from '@/lib/signed-in'
import { guest, guestClient, guestSignInOpen, supabaseConfigured } from '@/lib/guest-session'

/**
 * Sasha 153 · NO SIGN-IN WALL. A browser with no session gets its own AUTOMATIC PRIVATE GUEST ACCOUNT: the backend makes
 * it (Supabase's admin API — sign-ups stay closed to the public) and opens its first session, and this route keeps that
 * session in the browser's Supabase cookies. Already signed in (the founder, or a guest) → nothing new is made.
 * The booking key never reaches the browser; the visitor's address goes along only for the backend's per-address cap.
 */
export const dynamic = 'force-dynamic'

export async function POST(request: Request) {
  if (await founderSignedIn()) return NextResponse.json({ ok: true, kind: 'founder' })
  if (!guestSignInOpen() || !supabaseConfigured()) {
    return NextResponse.json({ ok: false, rule: 'guests_closed', message: 'Guest accounts are not open on this deployment.' }, { status: 503 })
  }
  const existing = await guest()
  if (existing) return NextResponse.json({ ok: true, kind: 'guest' })
  const key = (process.env.SASHA_BOOKING_KEY ?? '').trim()
  if (!key) return NextResponse.json({ ok: false, rule: 'booking_key_not_configured', message: 'not configured' }, { status: 503 })
  const ip = (request.headers.get('x-forwarded-for') ?? '').split(',')[0].trim() || request.headers.get('x-real-ip') || ''
  let r: Response
  try {
    r = await fetch(`${API_URL}/api/booking/guest/start`, {
      method: 'POST', cache: 'no-store',
      headers: { 'content-type': 'application/json', 'x-sasha-booking-key': key },
      body: JSON.stringify({ ip }),
    })
  } catch (e) {
    return NextResponse.json({ ok: false, rule: 'backend_unreachable', message: (e as Error).message }, { status: 502 })
  }
  const j = await r.json().catch(() => ({})) as { access_token?: string; refresh_token?: string; message?: string; rule?: string }
  if (!r.ok || !j.access_token || !j.refresh_token) {
    return NextResponse.json({ ok: false, rule: j.rule ?? `HTTP ${r.status}`, message: j.message ?? 'no guest session' }, { status: r.status === 429 ? 429 : 503 })
  }
  const sb = await guestClient()
  const { error } = await sb.auth.setSession({ access_token: j.access_token, refresh_token: j.refresh_token })
  if (error) return NextResponse.json({ ok: false, rule: 'guest_session_not_kept', message: error.message }, { status: 503 })
  return NextResponse.json({ ok: true, kind: 'guest', new: true })
}
