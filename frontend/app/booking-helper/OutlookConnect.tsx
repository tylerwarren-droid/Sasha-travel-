'use client'

/**
 * CR 86 · OUTLOOK / MICROSOFT 365, READ-ONLY — beta, by invitation, next to Gmail.
 *
 * Microsoft's own sign-in, asking only to READ mail (never send, move or delete). Sasha searches ONLY for receipt and renewal
 * emails from the last 13 months, to list what you're subscribed to, and never stores an email. Ask Sasha "what subscriptions am I
 * paying for?" in the chat once connected.
 */
import { useEffect, useState } from 'react'
import { bookingReq, guestRefusal as refusal } from '@/lib/booking-client'
import { bookingHeaders, bookingUrl } from '@/lib/booking-api'
import { GatedButton } from './GatedButton'

type View = { configured: boolean; invited?: boolean; connected: boolean; consent: { version: string; text: string; sha256: string } }

export function OutlookConnect() {
  const [view, setView] = useState<View | null>(null)
  const [words, setWords] = useState<string | null>(null)
  const [ticked, setTicked] = useState(false)
  const [busy, setBusy] = useState(false)

  async function load() {
    const r = await bookingReq('/api/booking/outlook')
    if (r.ok) setView(r.json as unknown as View)
    else setWords(refusal(r.json, r.status))
  }
  useEffect(() => {
    let off = false
    const params = new URLSearchParams(window.location.search)
    const q = params.get('outlook')
    if (q) {                                     // read once, then gone
      params.delete('outlook')
      const rest = params.toString()
      window.history.replaceState(null, '', window.location.pathname + (rest ? `?${rest}` : '') + window.location.hash)
    }
    bookingReq('/api/booking/outlook').then((r) => {
      if (off) return
      if (r.ok) setView(r.json as unknown as View)
      else setWords(refusal(r.json, r.status))
      const connected = r.ok && (r.json as unknown as View).connected
      if (q && !(connected && q !== 'connected')) setWords({ connected: 'Connected — ask Sasha “what subscriptions am I paying for?”', declined: 'Not connected — the Microsoft sign-in was cancelled.',
        failed: 'Not connected — Microsoft’s answer could not be used. Try again.', scopes_missing: 'Not connected — the read-only mail permission is needed.',
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
    const r = await bookingReq('/api/booking/outlook/connect', { consent_version: view.consent.version, consent_sha256: view.consent.sha256 })
    if (!r.ok) { setWords(`Not connected — ${refusal(r.json, r.status)}.`); return }
    window.location.href = String(r.json.url)
  })
  const disconnect = () => act(async () => {
    const r = await fetch(bookingUrl('/api/booking/outlook'), { method: 'DELETE', headers: bookingHeaders() })
    const j = r.ok ? await r.json() : null
    setWords(r.ok ? `Disconnected — the access is deleted here. ${j?.at_microsoft ?? ''}`.trim() : 'Not disconnected.')
    await load()
  })

  return (
    <section id="outlook" className="space-y-2 rounded border p-3">
      <h2 className="font-semibold">Outlook / Microsoft 365 (read-only, beta, by invitation)</h2>
      {words && <p>{words}</p>}
      {view && view.invited === false && <p className="opacity-75">Outlook is a beta by invitation, and it isn&rsquo;t open for your account yet.</p>}
      {view && !view.configured && <p className="opacity-75">Microsoft sign-in isn&rsquo;t set up on this server yet.</p>}
      {view && view.configured && view.connected && (
        <div className="space-y-2">
          <p>Connected. Ask Sasha &ldquo;what subscriptions am I paying for?&rdquo; — she reads only receipt and renewal emails.</p>
          <GatedButton label="Disconnect" onClick={() => { disconnect() }} needs={[busy && 'the last step to finish']} />
        </div>
      )}
      {view && view.configured && view.invited !== false && !view.connected && (
        <div className="space-y-2">
          <label className="flex items-start gap-2"><input type="checkbox" checked={ticked} onChange={(e) => setTicked(e.target.checked)} /><span>{view.consent.text}</span></label>
          <GatedButton label="Connect Outlook (read-only)" onClick={() => { connect() }}
            needs={[!ticked && 'the box above ticked', busy && 'the last step to finish']} />
        </div>
      )}
    </section>
  )
}
