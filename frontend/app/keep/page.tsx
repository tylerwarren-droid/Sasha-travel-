'use client'

/**
 * CR 63 · THE KEEP — where your numbers and codes live, on your phone. Sasha (the AI) only ever sees a mask ("Passport ES
 * ••••456"); code fills the real value into a booking at the moment of use, after your yes for a document. Door codes, Wi-Fi
 * and booking references are only ever shown to YOU, here. Card numbers, one-time codes and passwords are never kept.
 * Values go from this form straight to the server, which seals them under your own key; nothing here logs or keeps them.
 */
import { Fragment, useEffect, useState } from 'react'
import { SignedInGate } from '../components/SignedInGate'
import { GatedButton } from '../booking-helper/GatedButton'

type Item = { item_id: string; type: string; tier: 'free' | 'yes' | 'read_back'; masked: string; last_used_at?: string }
type Types = Record<string, { tier: Item['tier']; name: string; fields: string[] }>
type Load = { phase: 'loading' } | { phase: 'failed'; why: string } | { phase: 'ready'; items: Item[]; types: Types }

const TIER: Record<Item['tier'], string> = {
  free: 'Used for you freely',
  yes: 'Used only after your yes',
  read_back: 'Shown only to you, here',
}
const DATE_FIELDS = new Set(['expires_on'])
const SECRET_FIELDS = new Set(['number', 'code', 'password', 'reference', 'activation_code', 'iccid'])
const label = (f: string) => f.replace(/_/g, ' ').replace(/^./, c => c.toUpperCase())

async function call(path: string, init?: RequestInit): Promise<{ ok: boolean; status: number; j: Record<string, unknown> }> {
  const r = await fetch(path, { cache: 'no-store', ...init })
  let j: Record<string, unknown> = {}
  try { j = await r.json() } catch { j = { message: `the server answered ${r.status}` } }
  return { ok: r.ok && j.ok !== false, status: r.status, j }
}

function AddItem({ types, onSaved }: { types: Types; onSaved: (msg: string) => void }) {
  const [kind, setKind] = useState('passport')
  const [vals, setVals] = useState<Record<string, string>>({})
  const [state, setState] = useState<{ phase: 'idle' } | { phase: 'saving' } | { phase: 'refused'; why: string }>({ phase: 'idle' })
  const fields = types[kind]?.fields ?? []
  const save = async () => {
    setState({ phase: 'saving' })
    const value = Object.fromEntries(Object.entries(vals).filter(([k, v]) => fields.includes(k) && v.trim() !== ''))
    const r = await call('/api/sasha-agent/keep', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ type: kind, value }) })
    setVals({})                                   // the value leaves this page's memory as soon as it's sent
    if (r.ok) { setState({ phase: 'idle' }); onSaved(r.j.created ? `Saved: ${r.j.masked}` : `Already in your Keep: ${r.j.masked}`) }
    else setState({ phase: 'refused', why: String(r.j.message ?? 'Not saved.') })
  }
  return (
    <section className="mx-3 mt-4 rounded-2xl border border-neutral-200 p-4 dark:border-neutral-800">
      <h2 className="text-lg font-semibold">Add to your Keep</h2>
      <select className="mt-2 w-full rounded-lg border border-neutral-300 bg-transparent p-3 dark:border-neutral-700" value={kind}
        onChange={e => { setKind(e.target.value); setVals({}); setState({ phase: 'idle' }) }}>
        {Object.entries(types).map(([k, t]) => <option key={k} value={k}>{t.name} — {TIER[t.tier].toLowerCase()}</option>)}
      </select>
      {fields.map(f => (
        <label key={f} className="mt-2 block text-sm">
          <span className="opacity-70">{label(f)}</span>
          <input className="mt-1 w-full rounded-lg border border-neutral-300 bg-transparent p-3 text-base dark:border-neutral-700"
            type={DATE_FIELDS.has(f) ? 'date' : SECRET_FIELDS.has(f) ? 'password' : 'text'} autoComplete="off" spellCheck={false}
            value={vals[f] ?? ''} onChange={e => setVals(v => ({ ...v, [f]: e.target.value }))} />
        </label>
      ))}
      <GatedButton label={state.phase === 'saving' ? 'Saving…' : 'Save to my Keep'} className="mt-3 w-full rounded-lg bg-emerald-700 p-3 font-semibold text-white"
        onClick={() => { save().catch((e: Error) => setState({ phase: 'refused', why: e.message })) }}
        needs={[state.phase === 'saving' && 'saving…']} />
      {state.phase === 'refused' && <p className="mt-2 rounded-lg bg-red-50 p-3 text-sm text-red-700 dark:bg-red-950 dark:text-red-300">{state.why}</p>}
      <p className="mt-2 text-xs opacity-60">Never kept: card numbers (Sasha pays with Apple Pay), one-time or 2FA codes, passwords.</p>
    </section>
  )
}

function Row({ it, onChange }: { it: Item; onChange: (msg: string) => void }) {
  const [shown, setShown] = useState<Record<string, string> | null>(null)
  const [why, setWhy] = useState<string | null>(null)
  const show = async () => {
    const r = await call(`/api/sasha-agent/keep/${encodeURIComponent(it.item_id)}/show`, { method: 'POST' })
    if (r.ok) { setShown(r.j.values as Record<string, string>); setTimeout(() => setShown(null), 30000) }
    else setWhy(String(r.j.message ?? 'It could not be shown.'))
  }
  const remove = async () => {
    const r = await call(`/api/sasha-agent/keep/${encodeURIComponent(it.item_id)}`, { method: 'DELETE' })
    if (r.ok) onChange(`Deleted: ${it.masked}`)
    else setWhy(String(r.j.message ?? 'It could not be deleted.'))
  }
  return (
    <li className="border-b border-neutral-200 py-3 dark:border-neutral-800">
      <p className="text-lg font-semibold leading-tight">{it.masked}</p>
      <p className="text-xs opacity-60">{TIER[it.tier]}{it.last_used_at ? ` · last used ${new Date(it.last_used_at).toLocaleDateString()}` : ''}</p>
      {shown && (
        <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-3 rounded-lg bg-amber-50 p-3 text-sm dark:bg-amber-950">
          {Object.entries(shown).map(([k, v]) => (<Fragment key={k}><dt className="opacity-60">{label(k)}</dt><dd className="break-all font-mono text-base">{v}</dd></Fragment>))}
        </dl>
      )}
      {why && <p className="mt-1 text-sm text-red-700 dark:text-red-300">{why}</p>}
      <div className="mt-2 flex gap-2">
        {it.tier === 'read_back' && <GatedButton label={shown ? 'Shown (hides in 30 s)' : 'Show'} className="rounded-full border px-4 py-1 text-sm font-semibold"
          onClick={() => { show().catch((e: Error) => setWhy(e.message)) }} needs={[]} done={shown ? 'on screen now' : null} />}
        <GatedButton label="Delete" className="rounded-full border border-red-300 px-4 py-1 text-sm text-red-700 dark:text-red-300"
          onClick={() => { remove().catch((e: Error) => setWhy(e.message)) }} needs={[]} />
      </div>
    </li>
  )
}

function KeepScreen() {
  const [load, setLoad] = useState<Load>({ phase: 'loading' })
  const [note, setNote] = useState<string | null>(null)
  const [confirm, setConfirm] = useState('')
  const [version, setVersion] = useState(0)          // bumped after every change: the list is read again from the server
  useEffect(() => {
    let live = true
    const get = async () => {
      try {
        const r = await call('/api/sasha-agent/keep')
        if (!live) return
        if (r.ok) setLoad({ phase: 'ready', items: (r.j.items as Item[]) ?? [], types: (r.j.types as Types) ?? {} })
        else setLoad({ phase: 'failed', why: String(r.j.message ?? `the server answered ${r.status}`) })
      } catch (e) {
        if (live) setLoad({ phase: 'failed', why: (e as Error).message })
      }
    }
    get().catch((e: Error) => setLoad({ phase: 'failed', why: e.message }))
    return () => { live = false }
  }, [version])
  const changed = (msg: string) => { setNote(msg); setVersion(v => v + 1) }
  const wipe = async () => {
    const r = await call('/api/sasha-agent/keep?confirm=DELETE', { method: 'DELETE' })
    setConfirm('')
    changed(r.ok ? `Deleted everything (${r.j.deleted}) — and the key that opened it.` : String(r.j.message ?? 'Not deleted.'))
  }

  if (load.phase === 'loading') return <p className="px-4 py-8 text-center opacity-60">Opening your Keep…</p>
  if (load.phase === 'failed') return <p className="mx-4 rounded-lg bg-red-50 p-4 text-red-700 dark:bg-red-950 dark:text-red-300">Your Keep couldn’t be opened just now ({load.why}). Nothing was changed.</p>
  return (
    <>
      {note && <p className="mx-3 mb-2 rounded-lg bg-emerald-50 p-3 text-sm text-emerald-900 dark:bg-emerald-950 dark:text-emerald-200">{note}</p>}
      {load.items.length > 0 ? (
        <ul className="px-4">{load.items.map(it => <Row key={it.item_id} it={it} onChange={changed} />)}</ul>
      ) : (
        <p className="px-4 py-4 opacity-70">Your Keep is empty. Add your passport, ID or loyalty numbers below — Sasha will use them only where they’re needed.</p>
      )}
      <AddItem types={load.types} onSaved={changed} />
      {load.items.length > 0 && (
        <section className="mx-3 mt-6 rounded-2xl border border-red-200 p-4 dark:border-red-900">
          <h2 className="font-semibold text-red-700 dark:text-red-300">Delete everything</h2>
          <p className="text-sm opacity-70">Every item, and the key that opens them. It can’t be undone.</p>
          <input className="mt-2 w-full rounded-lg border border-neutral-300 bg-transparent p-3 dark:border-neutral-700" placeholder="Type DELETE"
            value={confirm} onChange={e => setConfirm(e.target.value)} autoComplete="off" />
          <GatedButton label="Delete everything" className="mt-2 w-full rounded-lg bg-red-700 p-3 font-semibold text-white"
            onClick={() => { wipe().catch((e: Error) => setNote(e.message)) }} needs={[confirm !== 'DELETE' && 'type DELETE above']} />
        </section>
      )}
    </>
  )
}

export default function KeepPage() {
  return (
    <SignedInGate>
      <main className="mx-auto min-h-screen max-w-md bg-white pb-10 text-neutral-900 dark:bg-neutral-950 dark:text-neutral-100">
        <h1 className="px-4 pb-1 pt-6 text-2xl font-bold">Your Keep</h1>
        <p className="px-4 pb-3 text-sm opacity-60">Sasha never sees these — only “Passport ES ••••456”. They’re filled in where needed, at that moment, after your yes.</p>
        <KeepScreen />
      </main>
    </SignedInGate>
  )
}
