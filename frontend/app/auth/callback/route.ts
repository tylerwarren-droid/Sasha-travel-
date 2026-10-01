/**
 * S-62 step 3 · /auth/callback — the magic link lands here: the code is exchanged for a session (cookies set by
 * @supabase/ssr), then back to where the guest was. ⛔ Closed while guest sign-in is (GUEST_SIGN_IN_ENABLED).
 * A failed exchange goes back to /sign-in WITH Supabase's reason — never on to the chat as if signed in.
 */
import { NextResponse } from 'next/server'
import { guestClient, guestSignInOpen, safeNext, supabaseConfigured } from '@/lib/guest-session'

export async function GET(request: Request) {
  const url = new URL(request.url)
  const next = safeNext(url.searchParams.get('next'))
  const back = (why: string) => NextResponse.redirect(new URL(`/sign-in?error=${encodeURIComponent(why)}&next=${encodeURIComponent(next)}`, url.origin))
  if (!guestSignInOpen() || !supabaseConfigured()) return back('guest sign-in is not open')
  const code = url.searchParams.get('code')
  if (!code) return back(url.searchParams.get('error_description') ?? 'the link had no code')
  const supabase = await guestClient()
  const { error } = await supabase.auth.exchangeCodeForSession(code)
  if (error) return back(error.message)
  return NextResponse.redirect(new URL(next, url.origin))
}
