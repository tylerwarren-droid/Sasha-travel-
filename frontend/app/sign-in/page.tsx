/**
 * S-62 step 3 · /sign-in — one email field; sign-up and sign-in are the same step (a Supabase magic link).
 * At /sign-in, not /login: app/login is the CTO's and his drop could overwrite it. ⛔ Closed until the founder opens
 * guest sign-in (GUEST_SIGN_IN_ENABLED=1), after the key rotation — and it says so rather than showing a dead form.
 */
import { guestSignInOpen, safeNext, supabaseConfigured } from '@/lib/guest-session'
import SignInForm from './SignInForm'

export const dynamic = 'force-dynamic'

export default async function SignInPage({ searchParams }: { searchParams: Promise<Record<string, string | undefined>> }) {
  const q = await searchParams
  const box = { maxWidth: 420, margin: '10vh auto', padding: 24, fontFamily: 'system-ui, sans-serif', lineHeight: 1.5 } as const
  if (!guestSignInOpen()) {
    return <main style={box}><h1>Sign in</h1><p>Sign-in isn&rsquo;t open yet — it opens soon.</p></main>
  }
  if (!supabaseConfigured()) {
    return <main style={box}><h1>Sign in</h1><p>Sign-in isn&rsquo;t configured on this deployment, so no link can be sent.</p></main>
  }
  return (
    <main style={box}>
      <h1>Sign in to book with Sasha</h1>
      {q.error && <p role="alert" style={{ color: '#9a1c1c' }}>That sign-in link didn&rsquo;t work: {q.error}. Ask for a new one below.</p>}
      <SignInForm next={safeNext(q.next)} />
      <p style={{ fontSize: 13, opacity: 0.75 }}>
        Sasha is operated by Kanoe Technologies SL. We use your email only to sign you in and to send you what you book.{' '}
        <a href="/sasha-privacy">How we handle your details</a>.
      </p>
    </main>
  )
}
