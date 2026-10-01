/** S-62 step 3 · sign out: the guest's Supabase session ends and its cookies are cleared. Says what happened. */
import { NextResponse } from 'next/server'
import { guestClient, supabaseConfigured } from '@/lib/guest-session'

export async function POST() {
  if (!supabaseConfigured()) return NextResponse.json({ ok: false, rule: 'sign_in_not_configured', message: 'sign-in is not configured here' }, { status: 503 })
  const supabase = await guestClient()
  const { error } = await supabase.auth.signOut()
  return error
    ? NextResponse.json({ ok: false, rule: 'sign_out_failed', message: error.message }, { status: 502 })
    : NextResponse.json({ ok: true })
}
