'use client'

/**
 * Sasha 131 · what each route cost and what it got — the cost per CONFIRMED booking (backend/booking_signer/route_costs.py).
 * A call's cost is Bland's own price; email / one-tap / form costs are the rate settings, and an unset rate shows as
 * unknown, never as zero.
 */
import { useState } from 'react'
import { bookingHeaders, bookingUrl } from '@/lib/booking-api'
import { guestRefusal as refusal } from '@/lib/booking-client'
import { GatedButton } from './GatedButton'

type Route = { route: string; count: number; eur: number | null; usd?: number; source: string }
type Row = { id: string; venue: string | null; status: string; confirmed: boolean; routes: Route[]; eur: number | null }
type Out = { bookings: number; confirmed: number; eur_total: number; eur_per_confirmed: number | null; note: string | null;
  by_route: Record<string, { count: number; eur: number; confirmed_bookings: number }>; rows: Row[] }

const eur = (v: number | null | undefined) => (v === null || v === undefined ? 'unknown' : `€${v.toFixed(3)}`)

export function RouteCosts() {
  const [out, setOut] = useState<Out | null>(null)
  const [words, setWords] = useState<string | null>(null)
  async function load() {
    const r = await fetch(bookingUrl('/api/booking/ops/route-costs'), { headers: bookingHeaders() })
    const j = await r.json().catch(() => ({}))
    if (r.ok) { setOut(j as Out); setWords(null) } else setWords(`Route costs — ${refusal(j, r.status)}.`)
  }
  return (
    <section className="space-y-2 rounded border p-3">
      <h2 className="font-semibold">Cost per confirmed booking</h2>
      <GatedButton label="Show route costs" onClick={() => { load() }} needs={[]} />
      {words && <p>{words}</p>}
      {out && (
        <div className="space-y-2 text-sm">
          <p><strong>{eur(out.eur_per_confirmed)}</strong> per confirmed booking · {out.confirmed} confirmed of {out.bookings} · total {eur(out.eur_total)}</p>
          {out.note && <p className="text-xs">{out.note}</p>}
          <ul className="text-xs">
            {Object.entries(out.by_route).map(([k, v]) => <li key={k}>{k}: {v.count} used · {eur(v.eur)} · in {v.confirmed_bookings} confirmed booking(s)</li>)}
          </ul>
          <table className="text-xs">
            <thead><tr><th className="text-left">Venue</th><th className="text-left">Outcome</th><th className="text-left">Routes</th><th className="text-left">Cost</th></tr></thead>
            <tbody>
              {out.rows.map(r => (
                <tr key={r.id}>
                  <td>{r.venue}</td><td>{r.status}</td>
                  <td>{r.routes.map(x => `${x.route}×${x.count} (${x.source})`).join(' · ')}</td>
                  <td>{eur(r.eur)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
