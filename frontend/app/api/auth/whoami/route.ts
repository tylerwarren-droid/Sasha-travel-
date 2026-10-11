/** S-62 step 6 · who is signed in, for the chat to say so: the founder, a guest (verified with Supabase), or nobody. */
import { NextResponse } from 'next/server'
import { actingAs } from '@/lib/acting-as'
import { guestSignInOpen } from '@/lib/guest-session'

export const dynamic = 'force-dynamic'

/** Sasha 241 · the account actually ACTING: 'user' (a real sign-in — wins over the founder cookie), 'founder', or 'guest'
 *  (the automatic browser guest). `who: 'guest'` + email is kept for a real sign-in too, as before; `acting` says which. */
export async function GET() {
  const who = await actingAs()
  if (who?.kind === 'founder') return NextResponse.json({ who: 'founder', acting: 'founder', guest_sign_in_open: guestSignInOpen() })
  return NextResponse.json(who ? { who: 'guest', acting: who.kind, email: who.email, guest_sign_in_open: true }
    : { who: null, acting: null, guest_sign_in_open: guestSignInOpen() })
}
