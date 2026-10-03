'use client'

/**
 * Sasha 121 · the INVESTOR DEMO's controls (docs/business/investor-demo-v2.md) — the same founder-only server routes as
 * backend/scripts/demo.py. Each says what it is: "leave now" arrives labelled "sent early for the demo"; the Gmail find
 * comes from OUR test venue's email; reset touches only test-venue bookings.
 */
import { useState } from 'react'
import { bookingReq, guestRefusal as refusal } from '@/lib/booking-client'
import { bookingHeaders, bookingUrl } from '@/lib/booking-api'
import { GatedButton } from './GatedButton'

export function DemoControls() {
  const [words, setWords] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [login, setLogin] = useState<{ username: string; password: string; shop: string } | null>(null)
  async function run(path: string, label: string) {
    setBusy(true); setWords(`${label}…`)
    try {
      const r = await bookingReq(path, {}, 120000)
      const j = r.json as Record<string, unknown>
      setWords(r.ok ? `${label}: ${String(j.say ?? j.text ?? j.offered ?? 'done')}` : `${label} — ${refusal(j, r.status)}.`)
    } catch (e) { setWords((e as Error).message) } finally { setBusy(false) }
  }
  async function showLogin() {
    const r = await fetch(bookingUrl('/api/booking/ops/demo-shop-login'), { headers: bookingHeaders() })
    const j = await r.json().catch(() => ({}))
    if (r.ok) setLogin(j as { username: string; password: string; shop: string }); else setWords(`Demo shop login — ${refusal(j, r.status)}.`)
  }
  const needs = [busy && 'the last step to finish']
  return (
    <section className="space-y-2 rounded border p-3">
      <h2 className="font-semibold">Investor demo</h2>
      <div className="flex flex-wrap gap-2">
        <GatedButton label="Reset the demo" onClick={() => { run('/api/booking/ops/demo/reset', 'Reset') }} needs={needs} />
        <GatedButton label="E · Send “time to leave” now" onClick={() => { run('/api/booking/ops/demo/leave-now', 'Time to leave') }} needs={needs} />
        <GatedButton label="G · Gmail find (≈1 min)" onClick={() => { run('/api/booking/ops/demo/gmail-seed', 'Gmail find') }} needs={needs} />
        <GatedButton label="F · Demo shop login" onClick={() => { showLogin() }} needs={needs} />
      </div>
      {words && <p>{words}</p>}
      {login && <p className="text-xs">Kanoe Demo Market (ours — sells nothing): <strong>{login.username}</strong> / <code>{login.password}</code> — save it in
        {' '}<a className="underline" href="/vault">My accounts</a> as site &ldquo;Kanoe Demo Market&rdquo;, kind &ldquo;Password&rdquo;.</p>}
    </section>
  )
}
