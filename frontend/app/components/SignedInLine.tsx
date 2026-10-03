'use client'

/**
 * S-62 step 6 · the chat says WHO is booking, and asks a stranger to sign in — repo-only, inside our ChatBooking, so the
 * CTO's SashaChat.tsx needs no change. Every line comes from /api/auth/whoami; nothing is assumed.
 */
import { useEffect, useState } from 'react'

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
  const who = useWho()
  if (who === null) return <span>Checking who&rsquo;s signed in…</span>
  // Sasha 120 · signed out, ALWAYS "Sign in to book" with the link — never whose account booking is open to
  const next = typeof window !== 'undefined' ? window.location.pathname : '/demo'
  return <span><a href={`/sign-in?next=${encodeURIComponent(next)}`}>Sign in to book</a> — Sasha emails you a link.</span>
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
      {who.who === 'founder' ? 'Booking as the founder.' : <>Booking as {who.email ?? 'your account'}. <button type="button" onClick={signOut} style={{ textDecoration: 'underline' }}>Sign out</button></>}
      {' · '}<a href="/you" style={{ textDecoration: 'underline' }}>You</a>
      {out && <> {out}</>}
    </div>
  )
}
