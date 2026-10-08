/**
 * Sasha 215 (b) · /auth/code — the 6-digit code from the sign-in email, typed in WHERE THEY ARE (an iPhone Home Screen app has
 * its own cookies, so a link opens Safari and signs Safari in, not the app). Verified with Supabase (verifyOtp, type email);
 * the session cookies are set by @supabase/ssr exactly as the link's. ⛔ Closed while guest sign-in is (GUEST_SIGN_IN_ENABLED).
 */
import { NextResponse } from 'next/server'
import { guestClient, guestSignInOpen, safeNext, supabaseConfigured } from '@/lib/guest-session'

export async function POST(request: Request) {
  if (!guestSignInOpen() || !supabaseConfigured()) return NextResponse.json({ ok: false, why: 'guest sign-in is not open' }, { status: 403 })
  const b = await request.json().catch(() => ({}))
  const email = String(b?.email ?? '').trim().toLowerCase()
  const code = String(b?.code ?? '').replace(/\s+/g, '')
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email) || !/^\d{6}$/.test(code)) return NextResponse.json({ ok: false, why: 'that is not a 6-digit code' }, { status: 400 })
  const supabase = await guestClient()
  const { error } = await supabase.auth.verifyOtp({ email, token: code, type: 'email' })
  if (error) return NextResponse.json({ ok: false, why: error.message }, { status: 401 })
  return NextResponse.json({ ok: true, next: safeNext(b?.next) })
}
