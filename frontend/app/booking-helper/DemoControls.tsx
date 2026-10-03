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
  const [login, setLogin] = useState<{ username: string; password: string; site: string; name: string } | null>(null)
  async function run(path: string, label: string) {
    setBusy(true); setWords(`${label}…`)
    try {
      const r = await bookingReq(path, {}, 120000)
      const j = r.json as Record<string, unknown>
      setWords(r.ok ? `${label}: ${String(j.say ?? j.text ?? j.offered ?? 'done')}` : `${label} — ${refusal(j, r.status)}.`)
    } catch (e) { setWords((e as Error).message) } finally { setBusy(false) }
  }
  async function showLogin(path: string, site: string) {
    const r = await fetch(bookingUrl(path), { headers: bookingHeaders() })
    const j = await r.json().catch(() => ({}))
    // Sasha 131 · the vault takes a site ADDRESS (demo-spa.kanoe.ai), which the server names; the display name stays
    if (r.ok) setLogin({ ...(j as { username: string; password: string; site: string }), name: site }); else setWords(`${site} login — ${refusal(j, r.status)}.`)
  }
  const needs = [busy && 'the last step to finish']
  return (
    <section className="space-y-2 rounded border p-3">
      <h2 className="font-semibold">Investor demo</h2>
      <div className="flex flex-wrap gap-2">
        <GatedButton label="Reset the demo" onClick={() => { run('/api/booking/ops/demo/reset', 'Reset') }} needs={needs} />
        <GatedButton label="E · Send “time to leave” now" onClick={() => { run('/api/booking/ops/demo/leave-now', 'Time to leave') }} needs={needs} />
        <GatedButton label="G · Gmail find (≈1 min)" onClick={() => { run('/api/booking/ops/demo/gmail-seed', 'Gmail find') }} needs={needs} />
        <GatedButton label="F · Demo shop login" onClick={() => { showLogin('/api/booking/ops/demo-shop-login', 'Kanoe Demo Market') }} needs={needs} />
        <GatedButton label="Spa · Demo spa membership" onClick={() => { showLogin('/api/booking/ops/demo-spa-login', 'Kanoe Demo Spa') }} needs={needs} />
      </div>
      {words && <p>{words}</p>}
      {login && <p className="text-xs">{login.name} (ours — a demo, nothing real): <strong>{login.username}</strong> / <code>{login.password}</code> — save it in
        {' '}<a className="underline" href="/vault">My accounts</a> as site &ldquo;{login.site}&rdquo;, kind &ldquo;Password&rdquo;.</p>}
    </section>
  )
}
