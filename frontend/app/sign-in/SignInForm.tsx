'use client'

/** S-62 step 3 · the email → a magic link. It says only what happened: sent, or Supabase's own reason it wasn't. */
import { useState } from 'react'
import { createBrowserClient } from '@supabase/ssr'

// Sasha 215 (b) / 216 · the sign-in email carries a 6-digit code as well as the link once its Supabase template has
// {{ .Token }} (the founder's yes, 9 Oct). The box says "if your email shows a code", so it's true whether or not the
// template has been changed yet; NEXT_PUBLIC_SIGNIN_CODE=0 hides it.
const CODE_IN_EMAIL = process.env.NEXT_PUBLIC_SIGNIN_CODE === '1'

// Sasha 223 · the boxes are white, the page's text is white: say the box's own colours, or what's typed is invisible
const FIELD: React.CSSProperties = { display: 'block', width: '100%', padding: 10, margin: '6px 0 10px', color: '#111', background: '#fff',
  caretColor: '#111', border: '1px solid #8a8a8a', borderRadius: 8, fontSize: 16, colorScheme: 'light' }
const BUTTON: React.CSSProperties = { padding: '11px 18px', borderRadius: 999, border: 'none', background: '#e8b931', color: '#111', fontWeight: 700, fontSize: 16, cursor: 'pointer' }
const FIELD_CSS = '.si-field::placeholder{color:#6b6b6b;opacity:1}.si-field::-webkit-input-placeholder{color:#6b6b6b}'

function CodeEntry({ to, next }: { to: string; next: string }) {
  const [code, setCode] = useState('')
  const [why, setWhy] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  async function verify(e: React.FormEvent) {
    e.preventDefault()
    setBusy(true); setWhy(null)
    try {
      const r = await fetch('/auth/code', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ email: to, code, next }) })
      const j = await r.json().catch(() => ({}))
      if (j?.ok) { window.location.href = j.next || next; return }
      setWhy(j?.why || `it didn\u2019t work (HTTP ${r.status})`)
    } catch (err) { setWhy((err as Error).message) }
    setBusy(false)
  }
  return (
    <form onSubmit={verify}>
      <p>We&rsquo;ve emailed <strong>{to}</strong> a sign-in link. Open it on this device — or, if the email shows a 6-digit code, type it here (that works in the Home Screen app too).</p>
      <label htmlFor="code">The 6-digit code</label>
      <input id="code" inputMode="numeric" autoComplete="one-time-code" pattern="[0-9 ]{6,7}" maxLength={7} required value={code}
        onChange={(e) => setCode(e.target.value)} className="si-field" placeholder="123456" style={{ ...FIELD, fontSize: 20, letterSpacing: 4 }} />
      <style>{FIELD_CSS}</style>
      <button type="submit" disabled={busy} style={BUTTON}>{busy ? 'Signing in…' : 'Sign in'}</button>
      {why && <p role="alert" style={{ color: '#9a1c1c' }}>Not signed in: {why}.</p>}
    </form>
  )
}

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
      // Sasha 121 · invite-only: an address nobody invited gets that, plainly — never Supabase's internal words
      setState(error ? { phase: 'failed', why: /signups? not allowed/i.test(error.message) ? 'Sasha is invite-only for now — this address hasn\u2019t been invited' : error.message } : { phase: 'sent', to })
    } catch (err) {
      setState({ phase: 'failed', why: (err as Error).message })
    }
  }

  if (state.phase === 'sent') return CODE_IN_EMAIL ? <CodeEntry to={state.to} next={next} /> : <p>We&rsquo;ve emailed a sign-in link to <strong>{state.to}</strong>. Open it on this device to continue.</p>
  return (
    <form onSubmit={send}>
      <label htmlFor="email">Your email</label>
      <input id="email" type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)}
        className="si-field" placeholder="you@example.com" style={FIELD} />
      <style>{FIELD_CSS}</style>
      <button type="submit" style={BUTTON}>{state.phase === 'sending' ? 'Sending…' : 'Email me a sign-in link'}</button>
      {state.phase === 'failed' && <p role="alert" style={{ color: '#9a1c1c' }}>No link was sent: {state.why}.</p>}
    </form>
  )
}
