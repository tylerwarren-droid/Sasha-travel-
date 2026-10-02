'use client'

/**
 * S-79 · GOOGLE CALENDAR — "Sasha bookings" in the guest's calendar, and a free/busy check before booking.
 *
 * Connect: the guest ticks the connection consent (its version and hash prove the words shown), Google's own page asks
 * for exactly two permissions (create a "Sasha bookings" calendar; see free/busy — never event titles), and Google sends
 * them back here. While the app is in Google's testing mode the connection expires every 7 days: shown as "Expired,
 * reconnect", never "Connected".
 */
import { useEffect, useState } from 'react'
import { bookingReq, guestRefusal as refusal } from '@/lib/booking-client'
import { bookingHeaders, bookingUrl } from '@/lib/booking-api'
import { GatedButton } from './GatedButton'

type View = { configured: boolean; connected: boolean; expired: boolean; last_ok_at: string | null
  consent: { version: string; text: string; sha256: string } }

export function CalendarConnect() {
  const [view, setView] = useState<View | null>(null)
  const [words, setWords] = useState<string | null>(null)
  const [ticked, setTicked] = useState(false)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    let off = false
    const params = new URLSearchParams(window.location.search)
    const q = params.get('google')
    if (q) {                                     // read once, then gone: a reload or a later connect never shows a stale word
      params.delete('google')
      const rest = params.toString()
      window.history.replaceState(null, '', window.location.pathname + (rest ? `?${rest}` : '') + window.location.hash)
    }
    bookingReq('/api/booking/google').then((r) => {
      if (off) return
      if (r.ok) setView(r.json as unknown as View)
      else setWords(refusal(r.json, r.status))
      const connected = r.ok && (r.json as unknown as View).connected
      if (q && !(connected && q !== 'connected')) setWords({ connected: 'Connected.', declined: 'Not connected — you declined on Google’s page.',
        failed: 'Not connected — Google’s answer could not be used. Try again.', scopes_missing: 'Not connected — both permissions are needed.',
        vault_closed: 'Not connected — the vault that keeps the access is not open on this server yet.' }[q] ?? null)
    }).catch((e) => { if (!off) setWords((e as Error).message) })
    return () => { off = true }
  }, [])

  async function connect() {
    if (!view) return
    setBusy(true)
    try {
      const r = await bookingReq('/api/booking/google/connect', { consent_version: view.consent.version, consent_sha256: view.consent.sha256 })
      if (!r.ok) { setWords(`Not connected — ${refusal(r.json, r.status)}.`); return }
      window.location.href = String(r.json.url)
    } finally { setBusy(false) }
  }

  async function disconnect() {
    setBusy(true)
    try {
      const r = await fetch(bookingUrl('/api/booking/google'), { method: 'DELETE', headers: bookingHeaders() })
      let j: Record<string, unknown> = {}
      try { j = await r.json() } catch { /* reported by its status */ }
      setWords(r.ok ? String(j.say ?? 'Disconnected.') : `Not disconnected — ${refusal(j, r.status)}.`)
      const g = await bookingReq('/api/booking/google')
      if (g.ok) setView(g.json as unknown as View)
    } finally { setBusy(false) }
  }

  return (
    <section id="calendar" className="space-y-2 rounded border p-3">
      <h2 className="font-semibold">Google Calendar</h2>
      {words && <p>{words}</p>}
      {view && !view.configured && <p className="opacity-75">Google sign-in isn&rsquo;t set up on this server yet.</p>}
      {view && view.configured && view.connected && (
        <div className="space-y-1">
          <p>Connected — your bookings appear in the &ldquo;Sasha bookings&rdquo; calendar.{view.last_ok_at ? ` Last updated ${new Date(view.last_ok_at).toLocaleString('en-GB', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })}.` : ''}</p>
          <GatedButton label="Disconnect" onClick={() => { disconnect().catch((e) => setWords((e as Error).message)) }} needs={[busy && 'the last step to finish']} />
        </div>
      )}
      {view && view.configured && !view.connected && (
        <div className="space-y-2">
          {view.expired && <p><strong>Expired, reconnect.</strong> While Sasha is in Google&rsquo;s testing mode, a connection lasts 7 days. Nothing is lost: your bookings sync again once you reconnect.</p>}
          <label className="flex items-start gap-2">
            <input type="checkbox" checked={ticked} onChange={(e) => setTicked(e.target.checked)} />
            <span>{view.consent.text}</span>
          </label>
          <GatedButton label={view.expired ? 'Reconnect Google Calendar' : 'Connect Google Calendar'}
            onClick={() => { connect().catch((e) => setWords((e as Error).message)) }} needs={[!ticked && 'the box above ticked', busy && 'the last step to finish']} />
        </div>
      )}
    </section>
  )
}
