'use client'

/**
 * S-82 · GMAIL, READ-ONLY — beta, by invitation (Google's testing mode: the connection lasts 7 days).
 *
 * Sasha searches ONLY for booking, cancellation and bill emails from the last 90 days, keeps only the details (venue,
 * date, reference, amount) and never the email. Each find is one sentence; nothing changes until "Yes".
 */
import { useEffect, useState } from 'react'
import { bookingReq, guestRefusal as refusal } from '@/lib/booking-client'
import { bookingHeaders, bookingUrl } from '@/lib/booking-api'
import { GatedButton } from './GatedButton'

type Find = { id: string; kind: string; action: string | null; status: string; offer_sha256: string | null; sentence: string | null }
type View = { configured: boolean; invited?: boolean; connected: boolean; expired: boolean; consent: { version: string; text: string; sha256: string }; finds: Find[] }

export function MailboxConnect() {
  const [view, setView] = useState<View | null>(null)
  const [words, setWords] = useState<string | null>(null)
  const [ticked, setTicked] = useState(false)
  const [busy, setBusy] = useState(false)

  async function load() {
    const r = await bookingReq('/api/booking/mailbox')
    if (r.ok) setView(r.json as unknown as View)
    else setWords(refusal(r.json, r.status))
  }
  useEffect(() => {
    let off = false
    const params = new URLSearchParams(window.location.search)
    const q = params.get('gmail')
    if (q) {                                     // read once, then gone: a reload or a later connect never shows a stale word
      params.delete('gmail')
      const rest = params.toString()
      window.history.replaceState(null, '', window.location.pathname + (rest ? `?${rest}` : '') + window.location.hash)
    }
    bookingReq('/api/booking/mailbox').then((r) => {
      if (off) return
      if (r.ok) setView(r.json as unknown as View)
      else setWords(refusal(r.json, r.status))
      const connected = r.ok && (r.json as unknown as View).connected
      if (q && !(connected && q !== 'connected')) setWords({ connected: 'Connected — Sasha looked for booking emails.', failed: 'Not connected — Google’s answer could not be used. Try again.', scopes_missing: 'Not connected — the read-only permission is needed.',
        vault_closed: 'Not connected — the vault that keeps the access is not open on this server yet.' }[q] ?? null)
    }).catch((e) => { if (!off) setWords((e as Error).message) })
    return () => { off = true }
  }, [])

  async function act(fn: () => Promise<void>) {
    setBusy(true)
    try { await fn() } catch (e) { setWords((e as Error).message) } finally { setBusy(false) }
  }

  const connect = () => act(async () => {
    if (!view) return
    const r = await bookingReq('/api/booking/mailbox/connect', { consent_version: view.consent.version, consent_sha256: view.consent.sha256 })
    if (!r.ok) { setWords(`Not connected — ${refusal(r.json, r.status)}.`); return }
    window.location.href = String(r.json.url)
  })
  const answer = (f: Find, yes: boolean) => act(async () => {
    const r = await bookingReq(`/api/booking/mailbox/finds/${f.id}`, { offer_sha256: f.offer_sha256, yes })
    setWords(r.ok ? String(r.json.say ?? 'Done.') : `Not changed — ${refusal(r.json, r.status)}.`)
    await load()
  })
  const sync = () => act(async () => {
    const r = await bookingReq('/api/booking/mailbox/sync', {})
    setWords(r.ok ? `Checked — ${Number(r.json.found ?? 0)} new email(s) about bookings.` : refusal(r.json, r.status))
    await load()
  })
  const disconnect = () => act(async () => {
    const r = await fetch(bookingUrl('/api/booking/mailbox'), { method: 'DELETE', headers: bookingHeaders() })
    setWords(r.ok ? 'Disconnected — the access is deleted, and so is everything found.' : 'Not disconnected.')
    await load()
  })

  const offered = view?.finds.filter((f) => f.status === 'offered' && f.sentence) ?? []
  return (
    <section id="gmail" className="space-y-2 rounded border p-3">
      <h2 className="font-semibold">Gmail (read-only, beta, by invitation)</h2>
      {words && <p>{words}</p>}
      {view && view.invited === false && <p className="opacity-75">Gmail is a beta by invitation, and it isn&rsquo;t open for your account yet.</p>}
      {view && !view.configured && <p className="opacity-75">Google sign-in isn&rsquo;t set up on this server yet.</p>}
      {view && view.configured && view.connected && (
        <div className="space-y-2">
          {offered.length === 0 ? <p className="opacity-75">Nothing waiting for you.</p> : offered.map((f) => (
            <div key={f.id} className="rounded border p-2">
              <p>{f.sentence}</p>
              <div className="flex gap-2">
                <GatedButton label="Yes" onClick={() => { answer(f, true) }} needs={[busy && 'the last step to finish']} />
                <GatedButton label="No" onClick={() => { answer(f, false) }} needs={[busy && 'the last step to finish']} />
              </div>
            </div>
          ))}
          <div className="flex gap-2">
            <GatedButton label="Check my email now" onClick={() => { sync() }} needs={[busy && 'the last step to finish']} />
            <GatedButton label="Disconnect" onClick={() => { disconnect() }} needs={[busy && 'the last step to finish']} />
          </div>
        </div>
      )}
      {view && view.configured && view.invited !== false && !view.connected && (
        <div className="space-y-2">
          {view.expired && <p><strong>Expired, reconnect.</strong> In Google&rsquo;s testing mode a connection lasts 7 days.</p>}
          <label className="flex items-start gap-2"><input type="checkbox" checked={ticked} onChange={(e) => setTicked(e.target.checked)} /><span>{view.consent.text}</span></label>
          <GatedButton label={view.expired ? 'Reconnect Gmail' : 'Connect Gmail (read-only)'} onClick={() => { connect() }}
            needs={[!ticked && 'the box above ticked', busy && 'the last step to finish']} />
        </div>
      )}
    </section>
  )
}
