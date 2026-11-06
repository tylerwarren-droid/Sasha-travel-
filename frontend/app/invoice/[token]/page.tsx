'use client'
/**
 * Sasha 334 · THE MOVEMENT'S ONE INVOICE — addressed to the company: one line per worker (who, route, dates, hotel nights, price), the
 * swaps and cancellations with their refunds, the total and the REAV note; TEST in test mode. Read from AgAPI's records by the server
 * (GET /api/booking/group-invoice/<token> — the link's own signature, 30 days). "Print / Save as PDF" makes the PDF.
 */
import { use, useEffect, useState } from 'react'
import { apiUrl } from '@/lib/api'
import { reach } from '@/lib/request'   // Sasha 348 · the ONE request client

type Line = { who: string; route: string; dates: string; hotel_nights?: number | null; price: string; references: string[]; what?: string; refund?: string }
type Inv = { to: string; number: string; date: string; test: boolean; movement: { destination?: string; starts_on?: string; ends_on?: string; hotel_area?: string }
  lines: Line[]; adjustments: Line[]; total: string; reav: string }

export default function InvoicePage({ params }: { params: Promise<{ token: string }> }) {
  const { token } = use(params)
  const [inv, setInv] = useState<Inv | null>(null)
  const [err, setErr] = useState<string | null>(null)
  useEffect(() => {
    reach(apiUrl(`/api/booking/group-invoice/${encodeURIComponent(token)}`), { cache: 'no-store' })
      .then(async r => { const j = await r.json().catch(() => null); if (r.ok && j && !j.why) setInv(j); else setErr((j && (j.message || j.why)) || 'This invoice couldn’t be opened.') })
      .catch(() => setErr('This invoice couldn’t be opened.'))
  }, [token])
  const cell = { padding: '6px 8px', borderBottom: '1px solid #eaecf0', textAlign: 'left' as const, fontSize: 13 }
  if (err) return <main style={{ maxWidth: 820, margin: '40px auto', padding: '0 16px', fontFamily: 'system-ui' }}><p>{err}</p></main>
  if (!inv) return <main style={{ maxWidth: 820, margin: '40px auto', padding: '0 16px', fontFamily: 'system-ui' }}><p>Loading…</p></main>
  return (
    <main style={{ maxWidth: 820, margin: '24px auto', padding: '0 16px', fontFamily: 'system-ui, sans-serif', color: '#101828', background: '#fff' }}>
      {inv.test && <p data-test style={{ background: '#fff3cd', border: '1px solid #e0c36b', borderRadius: 6, padding: '4px 8px', display: 'inline-block' }}>TEST — nothing is charged</p>}
      <h1 style={{ fontSize: 22, marginBottom: 0 }}>Invoice {inv.number}</h1>
      <p style={{ margin: '4px 0 16px', color: '#475467' }}>{inv.date} · To: <strong>{inv.to}</strong> · {inv.movement.destination}
        {inv.movement.starts_on ? ` · ${inv.movement.starts_on} – ${inv.movement.ends_on}` : ''}{inv.movement.hotel_area ? ` · hotel ${inv.movement.hotel_area}` : ''}</p>
      <table style={{ width: '100%', borderCollapse: 'collapse' }}>
        <thead><tr>{['Traveller', 'Route', 'Dates', 'Hotel nights', 'References', 'Price'].map(h => <th key={h} style={cell}>{h}</th>)}</tr></thead>
        <tbody>{inv.lines.map((l, i) => <tr key={i} data-line><td style={cell}>{l.who}</td><td style={cell}>{l.route}</td><td style={cell}>{l.dates}</td>
          <td style={cell}>{l.hotel_nights ?? '—'}</td><td style={cell}>{l.references.join(' · ')}</td><td style={cell}>{l.price}</td></tr>)}</tbody>
      </table>
      {inv.adjustments.length > 0 && <><h2 style={{ fontSize: 16 }}>Swaps and cancellations</h2>
        <table style={{ width: '100%', borderCollapse: 'collapse' }}><tbody>{inv.adjustments.map((a, i) => <tr key={i} data-adjustment>
          <td style={cell}>{a.who}</td><td style={cell}>{a.what}</td><td style={cell}>{a.references.join(' · ')}</td><td style={cell}>refund {a.refund}</td></tr>)}</tbody></table></>}
      <p style={{ fontSize: 18, fontWeight: 700, textAlign: 'right' }} data-total>Total {inv.total}</p>
      <p style={{ fontSize: 12, color: '#475467' }}>{inv.reav}</p>
      <button type="button" onClick={() => window.print()} style={{ marginTop: 12 }}>Print / Save as PDF</button>
    </main>)
}
