'use client'

/**
 * S-62 step 6 · the chat says WHO is booking, and asks a stranger to sign in — repo-only, inside our ChatBooking, so the
 * CTO's SashaChat.tsx needs no change. Every line comes from /api/auth/whoami; nothing is assumed.
 */
import { useEffect, useState } from 'react'
import { ensureGuest } from '@/lib/guest-start'
import { actingOf, badgeFor, whoKey, changed, PER_PERSON_LOCAL, WHO_KEY } from '@/lib/acting-rule.mjs'

type Who = { who: 'founder' | 'guest' | null; acting?: 'founder' | 'user' | 'guest' | null; email?: string | null; guest_sign_in_open: boolean }

function useWho(): Who | null | 'unknown' {
  const [who, setWho] = useState<Who | null | 'unknown'>(null)
  useEffect(() => {
    let off = false
    ;(async () => {
      try {
        const r = await fetch('/api/auth/whoami', { cache: 'no-store' })
        const j = r.ok ? (await r.json() as Who) : null
        if (j) forgetIfSomeoneElse(j)   // Sasha 242 · before anything reads them
        if (!off) setWho(j ?? 'unknown')
      } catch {
        if (!off) setWho('unknown')
      }
    })()
    return () => { off = true }
  }, [])
  return who
}

/** Sasha 242 · per-person browser storage belongs to ONE person: when the person acting changes (sign-out, another sign-in),
 *  it goes (lib/acting-rule.mjs). Found by EU's walk (row 730): a new account saw trips it never made. */
export function forgetPerson(): void {
  try { for (const k of PER_PERSON_LOCAL) localStorage.removeItem(k) } catch { /* private window */ }
  try { sessionStorage.clear() } catch { /* private window */ }
}
function forgetIfSomeoneElse(j: Who): void {
  try {
    const now = whoKey(actingOf(j), j.email)   // Sasha 249 · whoami's acting, never re-derived here
    if (changed(localStorage.getItem(WHO_KEY), now)) forgetPerson()
    localStorage.setItem(WHO_KEY, now)
  } catch { /* storage off: nothing kept to leak */ }
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
  const acting = who === null || who === 'unknown' ? null : actingOf(who)   // Sasha 249 · whoami's acting, never the email suffix
  if (who === null || who === 'unknown' || !acting) return null
  async function signOut() {
    try {
      const r = await fetch('/api/auth/sign-out', { method: 'POST' })
      if (r.ok) { forgetPerson(); try { localStorage.removeItem(WHO_KEY) } catch { /* fine */ } }   // Sasha 242
      const j = await r.json().catch(() => ({})) as { message?: string }
      setOut(r.ok ? 'Signed out.' : `Not signed out — ${j.message ?? `HTTP ${r.status}`}`)
    } catch (e) {
      setOut(`Not signed out — ${(e as Error).message}`)
    }
  }
  return (
    <div style={{ fontSize: 12, opacity: 0.75, marginBottom: 6 }}>
      {acting === 'founder' ? 'Booking as the founder.' : acting === 'guest'
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
  // Sasha 241 · always the account ACTING (/api/auth/whoami, lib/acting-rule.mjs) — a real sign-in is never shown as Tyler.
  // Sasha 249 · from whoami's `acting` alone: no second decision here from `who` or the email's suffix
  const acting = actingOf(who)
  const guest = acting !== 'user' && acting !== 'founder'
  const label = badgeFor(who)
  return (
    <div style={{ position: 'fixed', left: '50%', top: 6, transform: 'translateX(-50%)', zIndex: 50, fontSize: 11, padding: '3px 9px', borderRadius: 999,
      background: 'rgba(17,17,17,.78)', color: '#fff', border: '1px solid rgba(255,255,255,.15)', pointerEvents: 'auto' }}>
      {label}{guest && <> · <a href="/sign-in" style={{ textDecoration: 'underline' }}>Sign in</a></>}
    </div>
  )
}
