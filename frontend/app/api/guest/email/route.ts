import { NextResponse } from 'next/server'
import { guestClient } from '@/lib/guest-session'
import { actingAs } from '@/lib/acting-as'

/**
 * Sasha 153 · "Keep this across devices: add your email" — offered AFTER a booking, never before. The guest's own account
 * gets the address (Supabase sends its confirmation link); nothing else changes. Only an automatic guest account
 * (an address on guests.kanoe.ai) is offered this; a real address is never replaced here.
 */
export const dynamic = 'force-dynamic'

export async function POST(request: Request) {
  // Sasha 249 · WHO IS ACTING (lib/acting-as.ts → acting-rule.mjs decide()), not a second check of the email's suffix here:
  // only the automatic guest, when it is the one acting (never under the founder's session or a real sign-in)
  const a = await actingAs()
  if (!a) return NextResponse.json({ ok: false, rule: 'no_guest', message: 'No guest session in this browser.' }, { status: 401 })
  if (a.kind !== 'guest') {
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
