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
  const code = String(b?.code ?? '').replace(/\D+/g, '')   // Sasha 257 · "123 456", "SASHA-123456": the digits are the code
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email) || !/^\d{6}$/.test(code)) return NextResponse.json({ ok: false, why: 'that is not a 6-digit code' }, { status: 400 })
  const supabase = await guestClient()
  const { error } = await supabase.auth.verifyOtp({ email, token: code, type: 'email' })
  if (error) {
    // Sasha 257 · Tyler (row 866): the email carries a link AND a code — after the link is used the code fails with Supabase's
    // "Token has expired". When this browser is already signed in as that address, that's what they're told, and they go on.
    const { data } = await supabase.auth.getUser()
    if ((data?.user?.email || '').toLowerCase() === email) return NextResponse.json({ ok: true, already: true, why: alreadyIn(), next: safeNext(b?.next) })
    return NextResponse.json({ ok: false, why: codeWords(error.message) }, { status: 401 })
  }
  return NextResponse.json({ ok: true, next: safeNext(b?.next) })
}

/** Sasha 257 · the page's words for a code (never Supabase's internal ones). */
function alreadyIn(): string { return 'You’re already signed in' }
function codeWords(m: string): string {
  return /expired|invalid|used/i.test(m || '') ? 'that code has expired or was already used — ask for a new one' : (m || 'that code didn’t work')
}
