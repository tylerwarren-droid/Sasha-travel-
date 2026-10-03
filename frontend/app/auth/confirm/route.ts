/**
 * Sasha 121 · /auth/confirm — an INVITATION (or a fresh sign-in link the founder sent from ops) lands here: the token is
 * verified with Supabase (verifyOtp), the session cookies are set by @supabase/ssr, then on to "You". ⛔ Closed while
 * guest sign-in is (GUEST_SIGN_IN_ENABLED). Sign-up stays invite-only: Supabase's public sign-up is disabled, so only
 * an address the founder invited can ever hold a session. A failed link goes back to /sign-in with Supabase's reason.
 */
import { NextResponse } from 'next/server'
import { guestClient, guestSignInOpen, safeNext, supabaseConfigured } from '@/lib/guest-session'

export async function GET(request: Request) {
  const url = new URL(request.url)
  const next = safeNext(url.searchParams.get('next') ?? '/you')
  const back = (why: string) => NextResponse.redirect(new URL(`/sign-in?error=${encodeURIComponent(why)}&next=${encodeURIComponent(next)}`, url.origin))
  if (!guestSignInOpen() || !supabaseConfigured()) return back('guest sign-in is not open')
  const tokenHash = url.searchParams.get('token_hash')
  const type = url.searchParams.get('type')
  if (!tokenHash || (type !== 'invite' && type !== 'magiclink')) return back('the link is incomplete')
  const supabase = await guestClient()
  const { error } = await supabase.auth.verifyOtp({ token_hash: tokenHash, type })
  if (error) return back(error.message)
  return NextResponse.redirect(new URL(next, url.origin))
}
