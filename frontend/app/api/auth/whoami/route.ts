/** S-62 step 6 · who is signed in, for the chat to say so: the founder, a guest (verified with Supabase), or nobody. */
import { NextResponse } from 'next/server'
import { founderSignedIn } from '@/lib/signed-in'
import { guest, guestSignInOpen } from '@/lib/guest-session'

export const dynamic = 'force-dynamic'

export async function GET() {
  if (await founderSignedIn()) return NextResponse.json({ who: 'founder', guest_sign_in_open: guestSignInOpen() })
  const g = await guest()
  return NextResponse.json(g ? { who: 'guest', email: g.email, guest_sign_in_open: true } : { who: null, guest_sign_in_open: guestSignInOpen() })
}
