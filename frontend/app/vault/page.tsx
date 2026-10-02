'use client'

/**
 * S-78 step 5 · YOUR VAULT — the accesses Sasha may use for you, each sealed on its own; what she has used, and when.
 *
 * Never shows a secret back (the server returns names and history only; V-3: no plaintext export, no "reveal").
 * Kinds are offered strongest first (R7), each with what it honestly is; a sign-in with the site (OAuth) is listed but
 * not offered — no site is connected that way yet. One tap revokes; "Revoke everything" is one button. Delete-all and
 * the data download (S-78 §9) are at the foot.
 */
import { useCallback, useEffect, useState } from 'react'
import { bookingReq, guestRefusal as refusal } from '@/lib/booking-client'
import { bookingHeaders, bookingUrl } from '@/lib/booking-api'
import { FounderGate } from '../booking-helper/FounderGate'
import { GatedButton } from '../booking-helper/GatedButton'

type Use = { action_kind: string; action_ref: string; status: string; started_at: string; ended_at: string | null }
type Item = { id: string; provider: string; label: string; kind: string; special_category: boolean; created_at: string
  last_used_at: string | null; revoked_at: string | null; uses: Use[] }
type Kind = { kind: string; offered: boolean; words: string }
type View = { items: Item[]; kinds: Kind[]; open: { open: boolean; why?: string; backend?: string }
  health: { allowed: boolean; consent: { version: string; text: string; sha256: string } } }

const KIND_NAME: Record<string, string> = { oauth: 'Sign in with the site', app_password: 'App password', passkey: 'Passkey',
  password: 'Password', identifier: 'Membership or loyalty number' }
const FIELDS: Record<string, string[]> = { app_password: ['username', 'password'], password: ['username', 'password'], identifier: ['value'], passkey: [] }
const when = (iso: string | null) => (iso ? new Date(iso).toLocaleString('en-GB', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' }) : '—')

async function send(method: 'DELETE', path: string, body?: unknown) {
  const r = await fetch(bookingUrl(path), { method, headers: bookingHeaders(), ...(body === undefined ? {} : { body: JSON.stringify(body) }) })
  let json: Record<string, unknown> = {}
  try { json = await r.json() } catch { /* reported by its status */ }
  return { ok: r.ok, status: r.status, json }
}

function Vault() {
  const [view, setView] = useState<View | null>(null)
  const [words, setWords] = useState<string | null>(null)
  const [form, setForm] = useState({ provider: '', label: '', kind: 'app_password', username: '', password: '', value: '' })
  const [busy, setBusy] = useState(false)
  const [confirm, setConfirm] = useState('')

  const load = useCallback(async () => {
    const r = await bookingReq('/api/booking/vault')
    if (r.ok) setView(r.json as unknown as View)
    else setWords(refusal(r.json, r.status))
  }, [])
  useEffect(() => {
    let off = false
    bookingReq('/api/booking/vault').then((r) => {
      if (off) return
      if (r.ok) setView(r.json as unknown as View)
      else setWords(refusal(r.json, r.status))
    }).catch((e) => { if (!off) setWords((e as Error).message) })
    return () => { off = true }
  }, [])

  async function save() {
    setBusy(true)
    try {
      const fields = Object.fromEntries(FIELDS[form.kind].map((k) => [k, form[k as 'username' | 'password' | 'value']]))
      const r = await bookingReq('/api/booking/vault', { provider: form.provider, label: form.label, kind: form.kind, fields })
      setWords(r.ok ? `Saved. ${String(r.json.say ?? '')}` : `Not saved — ${refusal(r.json, r.status)}.`)
      if (r.ok) setForm({ provider: '', label: '', kind: form.kind, username: '', password: '', value: '' })
      await load()
    } finally { setBusy(false) }
  }

  async function revoke(id: string | null) {
    setBusy(true)
    try {
      const r = id ? await send('DELETE', `/api/booking/vault/${id}`) : await bookingReq('/api/booking/vault/revoke-all', {})
      setWords(r.ok ? (Array.isArray(r.json.say) ? (r.json.say as string[]).join(' ') || 'Nothing to revoke.' : String(r.json.say ?? 'Revoked.'))
        : `Not revoked — ${refusal(r.json, r.status)}.`)
      await load()
    } finally { setBusy(false) }
  }

  async function download() {
    const r = await bookingReq('/api/booking/account/export')
    if (!r.ok) { setWords(`No download — ${refusal(r.json, r.status)}.`); return }
    const a = document.createElement('a')
    a.href = URL.createObjectURL(new Blob([JSON.stringify(r.json, null, 2)], { type: 'application/json' }))
    a.download = 'sasha-my-data.json'
    a.click()
  }

  async function eraseAll() {
    setBusy(true)
    try {
      const r = await send('DELETE', '/api/booking/account/data', { confirm })
      setWords(r.ok ? String(r.json.say ?? 'Deleted.') : `Nothing was deleted — ${refusal(r.json, r.status)}.`)
      await load()
    } finally { setBusy(false) }
  }

  const live = view?.items.filter((i) => !i.revoked_at) ?? []
  const input = 'w-full rounded border px-2 py-1'
  return (
    <main className="mx-auto my-6 max-w-2xl space-y-5 rounded-lg bg-white p-6 text-sm text-neutral-900 [color-scheme:light]">
      <header className="space-y-1">
        <h1 className="text-xl font-semibold">Your vault</h1>
        <p className="opacity-75">Logins and numbers Sasha may use to book for you. Each is encrypted on its own; the AI never sees them. One is
          opened only inside a booking you said yes to, and only if what she read back to you named it. No booking uses a saved access yet.</p>
      </header>
      {words && <p className="rounded bg-neutral-100 p-2">{words}</p>}
      {view && !view.open.open && <p className="rounded border border-amber-400 p-2">The vault is closed on this server: {view.open.why}. Nothing can be saved yet.</p>}

      {view && (
        <section className="space-y-2">
          <h2 className="font-semibold">Saved</h2>
          {live.length === 0 && <p className="opacity-75">Nothing saved.</p>}
          {live.map((i) => (
            <div key={i.id} className="rounded border p-2">
              <div className="flex justify-between gap-2">
                <span><strong>{i.label}</strong> · {i.provider} · {KIND_NAME[i.kind] ?? i.kind}</span>
                <GatedButton label="Revoke" onClick={() => { revoke(i.id).catch((e) => setWords((e as Error).message)) }} needs={[busy && 'the last step to finish']} />
              </div>
              <div className="text-xs opacity-75">Saved {when(i.created_at)} · {i.last_used_at ? `last used ${when(i.last_used_at)}` : 'never used'}</div>
              {i.uses.length > 0 && (
                <ul className="ml-4 list-disc text-xs">
                  {i.uses.map((u, n) => <li key={n}>{when(u.started_at)} — {u.action_kind} {u.action_ref.slice(0, 8)} — {u.status}</li>)}
                </ul>
              )}
            </div>
          ))}
          {live.length > 1 && <GatedButton label="Revoke everything" onClick={() => { revoke(null).catch((e) => setWords((e as Error).message)) }} needs={[busy && 'the last step to finish']} />}
        </section>
      )}

      {view && (
        <section className="space-y-2">
          <h2 className="font-semibold">Add one</h2>
          <ul className="space-y-1">
            {view.kinds.map((k) => (
              <li key={k.kind}>
                {k.offered ? (
                  <label className="flex items-start gap-2">
                    <input type="radio" name="kind" checked={form.kind === k.kind} onChange={() => setForm({ ...form, kind: k.kind })} />
                    <span><strong>{KIND_NAME[k.kind]}</strong> — {k.words}</span>
                  </label>
                ) : <span className="opacity-60"><strong>{KIND_NAME[k.kind]}</strong> — {k.words}</span>}
              </li>
            ))}
          </ul>
          <input className={input} placeholder="The site, e.g. mercadona.es" value={form.provider} onChange={(e) => setForm({ ...form, provider: e.target.value })} />
          <input className={input} placeholder="A name you'll recognise, e.g. Mercadona login" value={form.label} onChange={(e) => setForm({ ...form, label: e.target.value })} />
          {FIELDS[form.kind].includes('username') && <input className={input} placeholder="Username or email" autoComplete="off" value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} />}
          {FIELDS[form.kind].includes('password') && <input className={input} type="password" placeholder={form.kind === 'app_password' ? 'The app password' : 'Password'} autoComplete="new-password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />}
          {FIELDS[form.kind].includes('value') && <input className={input} placeholder="The number" autoComplete="off" value={form.value} onChange={(e) => setForm({ ...form, value: e.target.value })} />}
          <p className="text-xs opacity-70">Never a card number: payments go through Stripe. Health-related accesses aren&rsquo;t accepted yet{view.health.allowed ? '' : ' (that needs a data-protection assessment first)'}.</p>
          <GatedButton label="Save" onClick={() => { save().catch((e) => setWords((e as Error).message)) }}
            needs={[!view.open.open && 'the vault to be opened on the server', form.provider.trim().length < 3 && 'the site', !form.label.trim() && 'a name',
              FIELDS[form.kind].some((k) => !form[k as 'username' | 'password' | 'value'].trim()) && 'every field', busy && 'the last step to finish']} />
        </section>
      )}

      <section className="space-y-2 border-t pt-4">
        <h2 className="font-semibold">Your data</h2>
        <GatedButton label="Download what Sasha holds about me" onClick={() => { download().catch((e) => setWords((e as Error).message)) }} needs={[]} />
        <p className="text-xs opacity-70">Saved accesses come as names and history only, never their contents.</p>
        <p>Delete everything: your saved accesses, WhatsApp link and saved details. Bookings already made stay with the venue&rsquo;s own record.
          This needs a sign-in with your email link in the last ten minutes. Type <strong>delete everything</strong> to confirm.</p>
        <input className={input} value={confirm} onChange={(e) => setConfirm(e.target.value)} placeholder="delete everything" />
        <GatedButton label="Delete everything" onClick={() => { eraseAll().catch((e) => setWords((e as Error).message)) }}
          needs={[confirm.trim().toLowerCase() !== 'delete everything' && 'the words typed above', busy && 'the last step to finish']} />
      </section>
    </main>
  )
}

export default function VaultPage() {
  return <FounderGate><Vault /></FounderGate>
}
