'use client'

/**
 * Sasha 144 · THE CALL AND BOOKING LOG (backend/booking_signer/ops_log.py) — one place to answer a venue's dispute:
 * every call (venue, time, outcome, the venue's own words, Bland's record) and every booking (status, the venue's
 * reference, Sasha's K-reference, the guest's receipt, the calendar event). Test-line calls are in it, marked TEST.
 * What a record doesn't hold is said ("not recorded"), never filled in.
 */
import { useState } from 'react'
import { bookingHeaders, bookingUrl } from '@/lib/booking-api'
import { guestRefusal as refusal } from '@/lib/booking-client'

type Call = { call_id: string; test: boolean; venue: string | null; purpose: string | null; language: string | null; created_at: string | null
  placed_at: string | null; status: string | null; outcome: string | null; venue_words: string | null; not_placed_why: string | null
  k_ref: string | null; booking_status: string | null; bland_call_id: string | null; minutes: number | null; price_usd: number | null
  transcript: string | null; recording: string | null; trip_item_id: string | null }
type Booking = { id: string; type: string | null; status: string; venue: string | null; when_local: string | null; party: number | null
  venue_reference: string | null; k_ref: string | null; routes: Record<string, number>; created_at: string | null
  receipt: string | { outcome: string; route: string; kind: string; at: string }[]; calendar: string | { event_id: string | null; status: string | null } }
type Out = { since: string; calls: Call[]; bookings: Booking[]; receipts_recorded: boolean }
type Turn = { who: string; text: string }

// the audit trail's date construction (en-GB, 2-digit day, short month, numeric year, upper case) + the clock time
const fmt = (iso: string | null) => {
  if (!iso) return '—'
  const d = new Date(iso)
  if (isNaN(d.getTime())) return iso
  return `${d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' }).toUpperCase()} ${d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })}`
}

async function call(path: string, init?: RequestInit) {
  const r = await fetch(bookingUrl(path), { ...init, headers: { ...bookingHeaders(), ...(init?.headers || {}) } })
  const j = await r.json().catch(() => ({}))
  return { ok: r.ok, status: r.status, j }
}

export function CallLog() {
  const [q, setQ] = useState('')
  const [kind, setKind] = useState('all')
  const [tests, setTests] = useState('include')
  const [days, setDays] = useState(60)
  const [out, setOut] = useState<Out | null>(null)
  const [words, setWords] = useState<string | null>(null)
  const [bland, setBland] = useState<Record<string, { turns: Turn[]; recording: string; status: string | null; minutes: number | null } | string>>({})
  const [busy, setBusy] = useState(false)

  async function load() {
    setBusy(true)
    const p = new URLSearchParams({ q, kind, tests, days: String(days) })
    const r = await call(`/api/booking/ops/log?${p}`)
    setBusy(false)
    if (r.ok) { setOut(r.j as Out); setWords(null) } else setWords(`The log — ${refusal(r.j, r.status)}.`)
  }
  async function blandRecord(id: string) {
    setBland(b => ({ ...b, [id]: 'reading Bland’s record…' }))
    const r = await call(`/api/booking/ops/log/bland/${encodeURIComponent(id)}`)
    setBland(b => ({ ...b, [id]: r.ok ? { turns: r.j.transcript as Turn[], recording: r.j.recording, status: r.j.status, minutes: r.j.minutes }
      : `Bland’s record — ${refusal(r.j, r.status)}.` }))
  }
  async function testCall() {
    const r = await call('/api/booking/ops/calls/test', { method: 'POST', body: JSON.stringify({ language: 'en', minutes: 1 }) })
    setWords(r.ok ? (r.j.placed ? `Test call placed and logged (Bland ${r.j.bland_call_id}). Its outcome is read in about a minute.`
      : `Test call logged but NOT placed — ${r.j.why}.`) : `Test call — ${refusal(r.j, r.status)}.`)
    if (r.ok) load()
  }
  async function importBland() {
    const r = await call('/api/booking/ops/calls/import-bland', { method: 'POST' })
    if (!r.ok) return setWords(`Import — ${refusal(r.j, r.status)}.`)
    const other = (r.j.not_in_our_log_other_numbers || []) as { bland_call_id: string; at: string }[]
    setWords(`Imported ${r.j.imported_test_calls.length} test-line call(s) from Bland’s log (of ${r.j.bland_calls_seen} seen).` +
      (other.length ? ` ⚠ ${other.length} call(s) to OTHER numbers are in Bland’s log but not ours: ${other.map(o => o.bland_call_id).join(', ')}.` : ' No other call is missing.'))
    load()
  }

  return (
    <section className="space-y-3">
      <div>
        <input className="w-full rounded border px-2 py-1" placeholder="Search: venue, reference, K-reference, words, Bland id…"
               value={q} onChange={e => setQ(e.target.value)} onKeyDown={e => { if (e.key === 'Enter') load() }} />
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <select className="rounded border px-1" value={kind} onChange={e => setKind(e.target.value)}>
            <option value="all">Calls and bookings</option><option value="calls">Calls only</option><option value="bookings">Bookings only</option>
          </select>
          <select className="rounded border px-1" value={tests} onChange={e => setTests(e.target.value)}>
            <option value="include">Tests included</option><option value="exclude">No tests</option><option value="only">Tests only</option>
          </select>
          <select className="rounded border px-1" value={days} onChange={e => setDays(Number(e.target.value))}>
            {[7, 30, 60, 180, 365].map(d => <option key={d} value={d}>Last {d} days</option>)}
          </select>
          <button className="rounded border px-2 py-1" onClick={load} disabled={busy}>{busy ? 'Loading…' : 'Show'}</button>
          <button className="rounded border px-2 py-1" onClick={testCall}>Place a logged test call</button>
          <button className="rounded border px-2 py-1" onClick={importBland}>Import test calls Bland has</button>
        </div>
      </div>
      {words && <p>{words}</p>}
      {out && (
        <>
          <h2 className="font-semibold">Calls ({out.calls.length})</h2>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead><tr className="text-left"><th>When</th><th>Venue</th><th>Outcome</th><th>The venue’s words</th><th>Refs</th><th>Bland</th></tr></thead>
              <tbody>
                {out.calls.map(c => (
                  <tr key={c.call_id} className="border-t align-top">
                    <td className="whitespace-nowrap pr-2">{fmt(c.placed_at || c.created_at)}</td>
                    <td className="pr-2">{c.test && <span className="mr-1 rounded bg-amber-100 px-1 font-semibold">TEST</span>}{c.venue}
                      <div className="opacity-60">{c.purpose}{c.language ? ` · ${c.language}` : ''}</div></td>
                    <td className="pr-2">{c.outcome || c.status}{c.not_placed_why ? <div className="opacity-70">{c.not_placed_why}</div> : null}
                      {c.minutes != null && <div className="opacity-60">{c.minutes} min{c.price_usd != null ? ` · $${c.price_usd}` : ''}</div>}</td>
                    <td className="pr-2">{c.venue_words ? `“${c.venue_words}”` : <span className="opacity-60">none recorded</span>}</td>
                    <td className="pr-2">{c.k_ref || '—'}{c.booking_status ? <div className="opacity-60">booking: {c.booking_status}</div> : null}</td>
                    <td>
                      {c.bland_call_id ? (
                        <>
                          <code className="break-all">{c.bland_call_id}</code>
                          <div><button className="underline" onClick={() => blandRecord(c.bland_call_id!)}>Bland’s record</button></div>
                          {(() => {
                            const b = bland[c.bland_call_id!]
                            if (!b) return null
                            if (typeof b === 'string') return <div>{b}</div>
                            return (
                              <div className="mt-1 space-y-0.5">
                                <div className="opacity-70">{b.status}{b.minutes != null ? ` · ${b.minutes} min` : ''}</div>
                                <div className="opacity-70">{/^https?:/.test(b.recording) ? <a className="underline" href={b.recording} target="_blank" rel="noopener noreferrer">Recording</a> : b.recording}</div>
                                {b.turns.length ? b.turns.map((t, i) => <div key={i}><strong>{t.who}:</strong> {t.text}</div>) : <div className="opacity-70">No transcript in Bland’s record.</div>}
                              </div>
                            )
                          })()}
                        </>
                      ) : <span className="opacity-60">not placed</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <h2 className="font-semibold">Bookings ({out.bookings.length})</h2>
          {!out.receipts_recorded && <p className="text-xs opacity-75">Receipts are recorded from sql/032 on; before it, a receipt shows as “not recorded”.</p>}
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead><tr className="text-left"><th>For</th><th>Venue</th><th>Status</th><th>Their ref</th><th>K-ref</th><th>How</th><th>Receipt</th><th>Calendar</th></tr></thead>
              <tbody>
                {out.bookings.map(b => (
                  <tr key={b.id} className="border-t align-top">
                    <td className="whitespace-nowrap pr-2">{b.when_local || '—'}{b.party ? ` · ${b.party}` : ''}</td>
                    <td className="pr-2">{b.venue}<div className="opacity-60">{b.type}</div></td>
                    <td className="pr-2">{b.status}</td>
                    <td className="pr-2">{b.venue_reference || '—'}</td>
                    <td className="pr-2">{b.k_ref || '—'}</td>
                    <td className="pr-2">{Object.entries(b.routes).map(([k, v]) => `${k}×${v}`).join(' · ') || '—'}</td>
                    <td className="pr-2">{typeof b.receipt === 'string' ? b.receipt : b.receipt.map((x, i) => <div key={i}>{x.outcome} · {fmt(x.at)}</div>)}</td>
                    <td>{typeof b.calendar === 'string' ? b.calendar : `${b.calendar.status || 'event'} (${b.calendar.event_id})`}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </section>
  )
}
