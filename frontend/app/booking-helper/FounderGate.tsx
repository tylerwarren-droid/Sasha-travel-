'use client'

/**
 * S-41 · The booking page is the founder's only. Signed out, it shows a passphrase field and nothing else; every booking
 * route behind it also refuses without the session (the pass-through checks it again, server-side).
 */
import { useEffect, useState, type ReactNode } from 'react'
import { GatedButton } from './GatedButton'

type State = { phase: 'checking' } | { phase: 'in' } | { phase: 'out'; configured: boolean; note: string | null }

export function FounderGate({ children }: { children: ReactNode }) {
  const [state, setState] = useState<State>({ phase: 'checking' })
  const [pass, setPass] = useState('')

  useEffect(() => {
    fetch('/api/founder-session').then(async (r) => {
      const j = (await r.json()) as { signed_in?: boolean; configured?: boolean }
      setState(j.signed_in ? { phase: 'in' } : { phase: 'out', configured: j.configured !== false, note: null })
    }).catch((e) => setState({ phase: 'out', configured: true, note: `Could not check the session (${(e as Error).message}).` }))
  }, [])

  async function signIn() {
    const r = await fetch('/api/founder-session', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ passphrase: pass }) })
    const j = (await r.json().catch(() => ({}))) as { message?: string }
    setPass('')
    if (r.ok) setState({ phase: 'in' })
    else setState({ phase: 'out', configured: r.status !== 503, note: j.message ?? `Refused (HTTP ${r.status}).` })
  }

  if (state.phase === 'in') return <>{children}</>
  return (
    <main className="mx-auto my-6 max-w-md space-y-3 rounded-lg bg-white p-6 text-sm text-neutral-900 [color-scheme:light]">
      <h1 className="text-lg font-semibold">Sasha bookings — founder only</h1>
      {state.phase === 'checking' ? <p>Checking…</p> : (
        <>
          {!state.configured && <p className="text-red-800">This deployment has no founder passphrase set, so nobody can sign in.</p>}
          <input className="w-full rounded border px-2 py-1" type="password" autoComplete="current-password" placeholder="Passphrase"
            value={pass} onChange={(e) => setPass(e.target.value)} />
          <GatedButton label="Sign in" onClick={() => { signIn().catch((e) => setState({ phase: 'out', configured: true, note: `Stopped: ${(e as Error).message}` })) }}
            needs={[pass.length < 12 && 'the passphrase (12 characters or more)', !state.configured && 'a passphrase set on the server']} />
          {state.note && <p>{state.note}</p>}
        </>
      )}
    </main>
  )
}
