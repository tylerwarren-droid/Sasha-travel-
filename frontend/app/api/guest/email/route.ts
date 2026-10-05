import { NextResponse } from 'next/server'
import { guest, guestClient } from '@/lib/guest-session'

/**
 * Sasha 153 · "Keep this across devices: add your email" — offered AFTER a booking, never before. The guest's own account
 * gets the address (Supabase sends its confirmation link); nothing else changes. Only an automatic guest account
 * (an address on guests.kanoe.ai) is offered this; a real address is never replaced here.
 */
export const dynamic = 'force-dynamic'

export async function POST(request: Request) {
  const g = await guest()
  if (!g) return NextResponse.json({ ok: false, rule: 'no_guest', message: 'No guest session in this browser.' }, { status: 401 })
  if (!(g.email ?? '').endsWith('@guests.kanoe.ai')) {
    return NextResponse.json({ ok: false, rule: 'already_has_email', message: 'This account already has its email.' }, { status: 409 })
  }
  const body = await request.json().catch(() => ({})) as { email?: unknown }
  const email = typeof body.email === 'string' ? body.email.trim() : ''
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(email) || email.length > 200) {
    return NextResponse.json({ ok: false, rule: 'email_invalid', message: 'That doesn’t look like an email address.' }, { status: 422 })
  }
  const sb = await guestClient()
  const { error } = await sb.auth.updateUser({ email })
  if (error) return NextResponse.json({ ok: false, rule: 'email_not_set', message: error.message }, { status: 422 })
  return NextResponse.json({ ok: true, say: `Check ${email} for a confirmation link. Once confirmed, sign in with it on any device and your bookings are there.` })
}
