'use client'

/**
 * Sasha 120 · the gate for a guest's own pages ("You", the Vault): the founder OR a signed-in guest — each sees only their
 * own (the backend acts for the verified account alone). Signed out: "Sign in to book", with the link — never a word
 * about whose account booking is open to.
 */
import { useEffect, useState, type ReactNode } from 'react'

type Who = { who: 'founder' | 'guest' | null; email?: string | null; guest_sign_in_open: boolean }

export function SignedInGate({ children }: { children: ReactNode }) {
  const [who, setWho] = useState<Who | null | 'unknown'>(null)
  useEffect(() => {
    let off = false
    fetch('/api/auth/whoami', { cache: 'no-store' })
      .then(async (r) => { if (!off) setWho(r.ok ? (await r.json() as Who) : 'unknown') })
      .catch(() => { if (!off) setWho('unknown') })
    return () => { off = true }
  }, [])
  if (who === null) return <main className="mx-auto my-6 max-w-2xl p-6 text-sm">Checking who&rsquo;s signed in…</main>
  if (who !== 'unknown' && who.who) return <>{children}</>
  const next = typeof window !== 'undefined' ? window.location.pathname : '/you'
  return (
    <main className="mx-auto my-6 max-w-2xl space-y-2 rounded-lg bg-white p-6 text-sm text-neutral-900 [color-scheme:light]">
      <h1 className="text-xl font-semibold">Sign in to book</h1>
      <p><a className="underline" href={`/sign-in?next=${encodeURIComponent(next)}`}>Sign in</a> — Sasha emails you a link; there is no password.</p>
    </main>
  )
}
