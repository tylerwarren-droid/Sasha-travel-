'use client'

/**
 * CR 62 · ACTIVITY — everything Sasha did for you, newest first, on your phone: each booking, payment, email, WhatsApp,
 * calendar add and cancellation, one line each with a big check (green done · red failed or not sent · amber waiting), and a
 * Proof tap: the provider's reference, the time, what you approved, and whether it verifies. Read-only, from Pacioli's
 * records (backend agapi/activity.py). A record that couldn't be read is SAID — never a silently shorter list.
 */
import { useEffect, useState } from 'react'
import { SignedInGate } from '../components/SignedInGate'

type Proof = { reference: string | null; at: string; approved: string | null; fingerprint: string | null; verified: boolean; source: string }
type Item = { kind: string; state: string; check: 'green' | 'red' | 'amber'; line: string; at: string; ref: string; about?: string | null; proof?: Proof }
type Load = { phase: 'loading' } | { phase: 'failed'; why: string } | { phase: 'ready'; items: Item[]; unavailable: string[] }

const ICON = { green: '✓', red: '✕', amber: '…' } as const
const TONE = {
  green: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300',
  red: 'bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-300',
  amber: 'bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300',
} as const
const SOURCE: Record<string, string> = { venues: 'your restaurant and venue bookings', flights_and_stays: 'your flights and stays', s2: 'your messages and calendar' }

function when(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  const today = new Date().toDateString() === d.toDateString()
  return today ? d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    : d.toLocaleDateString([], { day: 'numeric', month: 'short' }) + ' · ' + d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

function ProofBox({ p }: { p: Proof }) {
  return (
    <details className="mt-2">
      <summary className="inline-block cursor-pointer select-none rounded-full border border-neutral-300 px-3 py-1 text-sm font-semibold dark:border-neutral-700">Proof</summary>
      <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">
        <dt className="opacity-60">Reference</dt><dd className="break-all">{p.reference ?? '—'}</dd>
        <dt className="opacity-60">When</dt><dd>{when(p.at) || p.at}</dd>
        <dt className="opacity-60">You approved</dt><dd>{p.approved ? `“${p.approved}”` : '—'}</dd>
        {p.fingerprint && (<><dt className="opacity-60">Fingerprint</dt><dd className="break-all font-mono text-xs">{p.fingerprint.slice(0, 23)}…</dd></>)}
      </dl>
      <p className={`mt-1 text-sm font-bold ${p.verified ? 'text-emerald-700 dark:text-emerald-400' : 'text-neutral-500'}`}>
        {p.verified ? '✓ Verified — the record matches its proof' : 'No provider proof on record for this one'}
      </p>
    </details>
  )
}

function ActivityList() {
  const [load, setLoad] = useState<Load>({ phase: 'loading' })
  useEffect(() => {
    let live = true
    const get = async () => {
      try {
        const r = await fetch('/api/sasha-agent/activity', { cache: 'no-store' })
        const j = await r.json()
        if (!live) return
        if (!r.ok || !j.ok) setLoad({ phase: 'failed', why: j.message ?? `the server answered ${r.status}` })
        else setLoad({ phase: 'ready', items: j.items ?? [], unavailable: j.unavailable ?? [] })
      } catch (e) {
        if (live) setLoad({ phase: 'failed', why: (e as Error).message })
      }
    }
    get().catch((e: Error) => setLoad({ phase: 'failed', why: e.message }))
    return () => { live = false }
  }, [])

  if (load.phase === 'loading') return <p className="px-4 py-8 text-center opacity-60">Reading your records…</p>
  if (load.phase === 'failed') return <p className="mx-4 rounded-lg bg-red-50 p-4 text-red-700 dark:bg-red-950 dark:text-red-300">Your activity couldn’t be read just now ({load.why}). Nothing is lost — try again in a minute.</p>
  return (
    <>
      {load.unavailable.length > 0 && (
        <p className="mx-4 mb-2 rounded-lg bg-amber-50 p-3 text-sm text-amber-900 dark:bg-amber-950 dark:text-amber-200">
          Part of your record couldn’t be read just now: {load.unavailable.map(u => SOURCE[u] ?? u).join(', ')}. This list may be missing those.
        </p>
      )}
      {load.items.length === 0 && load.unavailable.length === 0 ? (
        <p className="px-4 py-8 text-center opacity-60">Sasha hasn’t done anything for you yet. When she books, pays, emails or messages for you, it’s listed here with its proof.</p>
      ) : (
        <ul className="px-3">
          {load.items.map(i => (
            <li key={i.ref + i.line} className="flex items-start gap-3 border-b border-neutral-200 py-3 dark:border-neutral-800">
              <span aria-hidden className={`grid h-11 w-11 flex-none place-items-center rounded-full text-2xl font-bold ${TONE[i.check]}`}>{ICON[i.check]}</span>
              <div className="min-w-0 flex-1">
                <p className="text-lg font-semibold leading-tight">{i.line}</p>
                {i.about && <p className="truncate opacity-70">{i.about}</p>}
                <p className="text-xs opacity-50">{when(i.at)}</p>
                {i.proof && <ProofBox p={i.proof} />}
              </div>
            </li>
          ))}
        </ul>
      )}
    </>
  )
}

export default function ActivityPage() {
  return (
    <SignedInGate>
      <main className="mx-auto min-h-screen max-w-md bg-white pb-10 text-neutral-900 dark:bg-neutral-950 dark:text-neutral-100">
        <h1 className="px-4 pb-2 pt-6 text-2xl font-bold">Activity</h1>
        <p className="px-4 pb-3 text-sm opacity-60">Everything Sasha did for you — tap Proof on any line.</p>
        <ActivityList />
      </main>
    </SignedInGate>
  )
}
