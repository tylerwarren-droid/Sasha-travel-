'use client'

/** S-62 step 3 · the email → a magic link. It says only what happened: sent, or Supabase's own reason it wasn't. */
import { useState } from 'react'
import { createBrowserClient } from '@supabase/ssr'

export default function SignInForm({ next }: { next: string }) {
  const [email, setEmail] = useState('')
  const [state, setState] = useState<{ phase: 'idle' | 'sending' } | { phase: 'sent'; to: string } | { phase: 'failed'; why: string }>({ phase: 'idle' })

  async function send(e: React.FormEvent) {
    e.preventDefault()
    const to = email.trim()
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(to)) { setState({ phase: 'failed', why: 'that is not an email address' }); return }
    setState({ phase: 'sending' })
    try {
      const supabase = createBrowserClient(process.env.NEXT_PUBLIC_SUPABASE_URL!, process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!)
      const { error } = await supabase.auth.signInWithOtp({
        email: to, options: { emailRedirectTo: `${window.location.origin}/auth/callback?next=${encodeURIComponent(next)}`, shouldCreateUser: true },
      })
      setState(error ? { phase: 'failed', why: error.message } : { phase: 'sent', to })
    } catch (err) {
      setState({ phase: 'failed', why: (err as Error).message })
    }
  }

  if (state.phase === 'sent') return <p>We&rsquo;ve emailed a sign-in link to <strong>{state.to}</strong>. Open it on this device to continue.</p>
  return (
    <form onSubmit={send}>
      <label htmlFor="email">Your email</label>
      <input id="email" type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)}
        style={{ display: 'block', width: '100%', padding: 8, margin: '6px 0 10px' }} />
      <button type="submit" style={{ padding: '8px 14px' }}>{state.phase === 'sending' ? 'Sending…' : 'Email me a sign-in link'}</button>
      {state.phase === 'failed' && <p role="alert" style={{ color: '#9a1c1c' }}>No link was sent: {state.why}.</p>}
    </form>
  )
}
