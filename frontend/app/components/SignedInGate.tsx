'use client'

/**
 * Sasha 120 · the gate for a guest's own pages ("You", the Vault): the founder OR a signed-in guest — each sees only their
 * own (the backend acts for the verified account alone). Signed out: "Sign in to book", with the link — never a word
 * about whose account booking is open to.
 */
import { useEffect, useState, type ReactNode } from 'react'
import { ensureGuest } from '@/lib/guest-start'

type Who = { who: 'founder' | 'guest' | null; email?: string | null; guest_sign_in_open: boolean }

export function SignedInGate({ children }: { children: ReactNode }) {
  const [who, setWho] = useState<Who | null | 'unknown'>(null)
  useEffect(() => {
    let off = false
    // Sasha 153 · no sign-in wall: a visitor with no account gets their own private guest account first
    const ask = () => fetch('/api/auth/whoami', { cache: 'no-store' }).then(async (r) => (r.ok ? (await r.json() as Who) : null))
    ask().then(async (w) => {
      if (w && !w.who && (await ensureGuest())) w = await ask()
      if (!off) setWho(w ?? 'unknown')
    }).catch(() => { if (!off) setWho('unknown') })
    return () => { off = true }
  }, [])
  if (who === null) return <main className="mx-auto my-6 max-w-2xl p-6 text-sm">Checking who&rsquo;s signed in…</main>
  if (who !== 'unknown' && who.who) return <>{children}</>
  const next = typeof window !== 'undefined' ? window.location.pathname : '/you'
  return (
    <main className="mx-auto my-6 max-w-2xl space-y-2 rounded-lg bg-white p-6 text-sm text-neutral-900 [color-scheme:light]">
      <h1 className="text-xl font-semibold">Couldn&rsquo;t open your private session</h1>
      <p>Sasha makes one for you automatically; it didn&rsquo;t open just now. <a className="underline" href={next}>Try again</a>,
        or <a className="underline" href={`/sign-in?next=${encodeURIComponent(next)}`}>use your email</a> if you&rsquo;ve added one.</p>
    </main>
  )
}
