'use client'

/**
 * S-62 step 6 · the chat says WHO is booking, and asks a stranger to sign in — repo-only, inside our ChatBooking, so the
 * CTO's SashaChat.tsx needs no change. Every line comes from /api/auth/whoami; nothing is assumed.
 */
import { useEffect, useState, type CSSProperties } from 'react'
import { usePathname } from 'next/navigation'
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
  // Sasha 274 · rows 1063/1064: the ONE thing that crosses a change of person — the guest's own conversation, handed to the account
  // they chose to sign in as (SIGN_IN_CARRY, set only by that tap, read once by /s2). Everything else of this tab goes.
  let carry: string | null = null
  try { carry = sessionStorage.getItem(SIGN_IN_CARRY) } catch { /* private window */ }
  try { sessionStorage.clear(); if (carry) sessionStorage.setItem(SIGN_IN_CARRY, carry) } catch { /* private window */ }
}
/** Sasha 274 · the guest's conversation, carried through their own sign-in (S2App puts it; it reads it once). */
export const SIGN_IN_CARRY = 's2_carry_sign_in'
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

const S2_SHELL = /^\/(s2|next)(\/|$)/

/** Sasha 257 · the S2 shell's identity: one quiet line in its header — the same whoami fact as WhoBadge, never floating. */
export function WhoLine({ style }: { style?: CSSProperties }) {
  const who = useWho()
  if (who === null || who === 'unknown') return null
  const acting = actingOf(who)
  const guest = acting !== 'user' && acting !== 'founder'
  return (
    <div style={{ fontSize: 11.5, color: 'rgba(255,255,255,.5)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', ...style }}>
      {badgeFor(who)}{guest && <> · <a href="/sign-in" style={{ textDecoration: 'underline', color: 'inherit' }}>Sign in</a></>}
    </div>
  )
}

/** Sasha 274 · rows 1063/1064 · /s2's ONE ACCOUNT CONTROL, where "Signed in as …" was only text (no sign-out, no switch, no sign-in):
 *   a signed-in account → tap it: Sign out (back to a private guest) · Switch account (sign-in, nothing carried — another person)
 *   the founder        → tap it: Switch account (a real sign-in outranks the founder's cookie: lib/acting-rule.mjs)
 *   a guest            → "Guest — Sign in to book for real": sign-in, THIS conversation carried (onSignIn)
 *  From whoami's acting alone (lib/acting-rule.mjs), never re-derived. */
export function AccountControl({ style, onSignIn }: { style?: CSSProperties; onSignIn?: () => void }) {
  const who = useWho()
  const [open, setOpen] = useState(false)
  const [note, setNote] = useState<string | null>(null)
  if (who === null || who === 'unknown') return null
  const acting = actingOf(who)
  const next = '/sign-in?next=%2Fs2'
  const signIn = (carry: boolean) => { if (carry) onSignIn?.(); window.location.href = next }
  async function signOut(then: 'guest' | 'sign_in') {
    setNote(null)
    try {
      const r = await fetch('/api/auth/sign-out', { method: 'POST' })
      const j = await r.json().catch(() => ({})) as { message?: string }
      if (!r.ok) { setNote(`Not signed out — ${j.message ?? `HTTP ${r.status}`}`); return }
      forgetPerson(); try { localStorage.removeItem(WHO_KEY) } catch { /* fine */ }
      if (then === 'sign_in') { window.location.href = next; return }
      await ensureGuest()   // back to a private guest (Sasha 153: no sign-in wall)
      window.location.href = '/s2'
    } catch (e) { setNote(`Not signed out — ${(e as Error).message}`) }
  }
  const link = { background: 'none', border: 0, padding: 0, color: 'inherit', textDecoration: 'underline', font: 'inherit', cursor: 'pointer' } as const
  const item = { display: 'block', width: '100%', textAlign: 'left', padding: '11px 14px', background: 'transparent', border: 0, color: '#fff', fontSize: 14.5 } as const
  return (
    <div data-account={acting || 'none'} style={{ position: 'relative', fontSize: 11.5, color: 'rgba(255,255,255,.55)', ...style }}>
      {acting === 'guest' || acting === null
        ? <button type="button" onClick={() => signIn(true)} style={{ ...link, color: '#e8b931', textDecoration: 'none', fontWeight: 600 }}>Guest — Sign in to book for real</button>
        : <button type="button" aria-expanded={open} aria-haspopup="menu" onClick={() => setOpen(o => !o)} style={{ ...link, textDecoration: 'none', maxWidth: '100%', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {badgeFor(who)} ▾</button>}
      {open && acting !== 'guest' ? (
        <div role="menu" style={{ position: 'absolute', right: 0, top: 22, minWidth: 190, zIndex: 30, background: '#16161f', border: '1px solid rgba(255,255,255,.12)', borderRadius: 12, overflow: 'hidden', boxShadow: '0 10px 30px rgba(0,0,0,.5)' }}>
          {acting === 'user' ? <button type="button" role="menuitem" style={item} onClick={() => { setOpen(false); void signOut('guest') }}>Sign out</button> : null}
          <button type="button" role="menuitem" style={{ ...item, borderTop: acting === 'user' ? '1px solid rgba(255,255,255,.1)' : 0 }}
            onClick={() => { setOpen(false); if (acting === 'user') void signOut('sign_in'); else signIn(false) }}>Switch account</button>
        </div>) : null}
      {note ? <div role="status" style={{ color: '#f19999', marginTop: 4 }}>{note}</div> : null}
    </div>
  )
}

/** Sasha 158 · on EVERY page: who this browser is — "Signed in as Tyler" (the founder's session), "Signed in as <email>",
 *  or "Guest" with the 10-second sign-in. From /api/auth/whoami; nothing assumed, nothing shown while it is unknown. */
export function WhoBadge() {
  const who = useWho()
  const path = usePathname() || ''
  // Sasha 257 · Tyler (row 860): on the S2 shell (/s2, and /next with it) the floating pill sat over the chat and the cards —
  // there the SAME fact (whoami) is said quietly in the header (WhoLine), never over content
  if (S2_SHELL.test(path)) return null
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
