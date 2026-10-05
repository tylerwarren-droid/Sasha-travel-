'use client'

/**
 * S-62 step 6 · the chat says WHO is booking, and asks a stranger to sign in — repo-only, inside our ChatBooking, so the
 * CTO's SashaChat.tsx needs no change. Every line comes from /api/auth/whoami; nothing is assumed.
 */
import { useEffect, useState } from 'react'
import { ensureGuest } from '@/lib/guest-start'

type Who = { who: 'founder' | 'guest' | null; email?: string | null; guest_sign_in_open: boolean }

function useWho(): Who | null | 'unknown' {
  const [who, setWho] = useState<Who | null | 'unknown'>(null)
  useEffect(() => {
    let off = false
    ;(async () => {
      try {
        const r = await fetch('/api/auth/whoami', { cache: 'no-store' })
        const j = r.ok ? (await r.json() as Who) : null
        if (!off) setWho(j ?? 'unknown')
      } catch {
        if (!off) setWho('unknown')
      }
    })()
    return () => { off = true }
  }, [])
  return who
}

export function SignInToBook() {
  // Sasha 153 · no sign-in wall: this only shows when the automatic guest session couldn't open — it tries again
  const [state, setState] = useState<'starting' | 'ready' | 'failed'>('starting')
  useEffect(() => { ensureGuest().then((ok) => setState(ok ? 'ready' : 'failed')) }, [])
  if (state === 'starting') return <span>Opening your private session…</span>
  if (state === 'ready') return <span>Your private session is open — ask again and I&rsquo;ll carry on.</span>
  return <span>I couldn&rsquo;t open your private session just now — try again in a moment.</span>
}

export function WhoIsBooking() {
  const who = useWho()
  const [out, setOut] = useState<string | null>(null)
  if (who === null || who === 'unknown' || !who.who) return null
  async function signOut() {
    try {
      const r = await fetch('/api/auth/sign-out', { method: 'POST' })
      const j = await r.json().catch(() => ({})) as { message?: string }
      setOut(r.ok ? 'Signed out.' : `Not signed out — ${j.message ?? `HTTP ${r.status}`}`)
    } catch (e) {
      setOut(`Not signed out — ${(e as Error).message}`)
    }
  }
  return (
    <div style={{ fontSize: 12, opacity: 0.75, marginBottom: 6 }}>
      {who.who === 'founder' ? 'Booking as the founder.' : (who.email ?? '').endsWith('@guests.kanoe.ai')
        ? 'Booking as a private guest — only you see these bookings.'
        : <>Booking as {who.email ?? 'your account'}. <button type="button" onClick={signOut} style={{ textDecoration: 'underline' }}>Sign out</button></>}
      {' · '}<a href="/you" style={{ textDecoration: 'underline' }}>You</a>
      {out && <> {out}</>}
    </div>
  )
}

/** Sasha 158 · on EVERY page: who this browser is — "Signed in as Tyler" (the founder's session), "Signed in as <email>",
 *  or "Guest" with the 10-second sign-in. From /api/auth/whoami; nothing assumed, nothing shown while it is unknown. */
export function WhoBadge() {
  const who = useWho()
  if (who === null || who === 'unknown') return null
  const email = who.email ?? ''
  const guest = !who.who || email.endsWith('@guests.kanoe.ai')
  const label = who.who === 'founder' ? 'Signed in as Tyler' : guest ? 'Guest' : `Signed in as ${email || 'you'}`
  return (
    <div style={{ position: 'fixed', left: '50%', top: 6, transform: 'translateX(-50%)', zIndex: 50, fontSize: 11, padding: '3px 9px', borderRadius: 999,
      background: 'rgba(17,17,17,.78)', color: '#fff', border: '1px solid rgba(255,255,255,.15)', pointerEvents: 'auto' }}>
      {label}{guest && <> · <a href="/sign-in" style={{ textDecoration: 'underline' }}>Sign in</a></>}
    </div>
  )
}
