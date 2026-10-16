/**
 * Sasha 275 · S1 MEASURE — the founder's week (observation only; it changes nothing about how she behaves). From the backend's
 * derived store (agapi/measure.py) through GET /api/agent/measures, which is founder-only there too. Ids only — no names, no words.
 * By day, by venue type and by stop reason, with p50 / p95 / p99. Rows 1054 ("how far did we get") and the CTO plan's S1.
 */
import { founderSignedIn } from '@/lib/signed-in'
import { agentHeaders } from '@/lib/agent-auth'
import { API_URL } from '@/lib/api'

export const dynamic = 'force-dynamic'

type P = { p50: number | null; p95: number | null; p99: number | null; n: number }
// eslint-disable-next-line @typescript-eslint/no-explicit-any -- the store's derived summary, shaped by agapi/measure.summarise
type S = Record<string, any>

const box = { maxWidth: 1100, margin: '0 auto', padding: '24px 16px', fontFamily: 'system-ui, sans-serif', color: '#e8e8ef', lineHeight: 1.45 } as const
const th = { textAlign: 'left', padding: '6px 10px', borderBottom: '1px solid rgba(255,255,255,.18)', fontWeight: 600, fontSize: 13 } as const
const td = { padding: '6px 10px', borderBottom: '1px solid rgba(255,255,255,.08)', fontSize: 13, fontVariantNumeric: 'tabular-nums' } as const
const p3 = (x?: P) => (x && x.n ? `${x.p50 ?? '–'} / ${x.p95 ?? '–'} / ${x.p99 ?? '–'}  (n ${x.n})` : '—')
const pct = (x: number | null | undefined) => (typeof x === 'number' ? `${Math.round(x * 100)}%` : '—')

export default async function MeasuresPage({ searchParams }: { searchParams: Promise<{ days?: string }> }) {
  if (!(await founderSignedIn())) return <main style={{ ...box, background: '#0b0b10', minHeight: '100dvh' }}><h1>Founder only</h1></main>
  const days = Math.max(1, Math.min(31, Number((await searchParams).days) || 7))
  const headers = await agentHeaders()
  const r = headers ? await fetch(`${API_URL}/api/agent/measures?days=${days}`, { headers, cache: 'no-store' }).catch(() => null) : null
  const j = r && r.ok ? await r.json().catch(() => null) : null
  if (!j?.ok) return <main style={{ ...box, background: '#0b0b10', minHeight: '100dvh' }}><h1>Sasha · measures</h1><p>The store couldn’t be read{j?.rule ? ` (${j.rule})` : ''}.</p></main>
  const w: S = j.week
  const daysRows: [string, S][] = Object.entries(j.by_day || {})
  const stages = ['venue', 'channel', 'filled', 'submitted', 'confirmed']
  return (
    <main style={{ ...box, background: '#0b0b10', minHeight: '100dvh' }}>
      <h1 style={{ fontSize: 24, marginBottom: 2 }}>Sasha · measures, last {days} days</h1>
      <p style={{ opacity: 0.7, marginTop: 0, fontSize: 13 }}>Observation only — derived from AgAPI’s events and Sasha’s own records (measure v{j.mv}); ids only.
        {' '}{w.turns} turns · {w.bookings} bookings · {j.rows} rows · versions {(j.versions || []).map((v: string[]) => v.filter(Boolean).join('/')).join(', ') || '—'}</p>

      <h2 style={{ fontSize: 17 }}>Daily summary</h2>{/* Sasha 275 · kept in sasha-prod, read here (the chat reads it from this page) — never sent elsewhere */}
      {(j.daily || []).length ? (j.daily as { day: string; line: string }[]).map(d => <p key={d.day} data-daily={d.day} style={{ fontSize: 13.5, margin: '6px 0', opacity: 0.9 }}>{d.line}</p>)
        : <p style={{ fontSize: 13.5, opacity: 0.7 }}>No daily summary yet — the first one is made after 07:00 Madrid.</p>}

      <h2 style={{ fontSize: 17 }}>Responsiveness (ms, p50 / p95 / p99)</h2>
      <table style={{ borderCollapse: 'collapse', width: '100%' }}><thead><tr><th style={th}>Day</th><th style={th}>Voice: end of speech → first audible</th><th style={th}>Text: first visible</th><th style={th}>Routine reply done</th></tr></thead>
        <tbody>{daysRows.map(([d, s]) => (<tr key={d}><td style={td}>{d}</td><td style={td}>{p3(s.responsiveness.first_audible_voice_ms)}</td><td style={td}>{p3(s.responsiveness.first_visible_text_ms)}</td><td style={td}>{p3(s.responsiveness.routine_done_ms)}</td></tr>))}
          <tr><td style={{ ...td, fontWeight: 700 }}>Week</td><td style={td}>{p3(w.responsiveness.first_audible_voice_ms)}</td><td style={td}>{p3(w.responsiveness.first_visible_text_ms)}</td><td style={td}>{p3(w.responsiveness.routine_done_ms)}</td></tr></tbody></table>

      <h2 style={{ fontSize: 17 }}>Bookings: submission, outcome, the two rates</h2>
      <table style={{ borderCollapse: 'collapse', width: '100%' }}><thead><tr><th style={th}>Day</th><th style={th}>Bookings</th><th style={th}>Yes → action (ms)</th><th style={th}>Profile lookup (ms)</th><th style={th}>Yes → outcome (s)</th><th style={th}>Submission success</th><th style={th}>Venue confirmation</th><th style={th}>Duplicates · after cancel</th></tr></thead>
        <tbody>{[...daysRows, ['Week', w] as [string, S]].map(([d, s]) => (<tr key={d}><td style={{ ...td, fontWeight: d === 'Week' ? 700 : 400 }}>{d}</td><td style={td}>{s.bookings}</td><td style={td}>{p3(s.submission.yes_to_action_ms)}</td><td style={td}>{p3(s.submission.profile_lookup_ms)}</td><td style={td}>{p3(s.outcome.yes_to_outcome_s)}</td><td style={td}>{pct(s.rates.submission_success)}</td><td style={td}>{pct(s.rates.venue_confirmation)}</td><td style={{ ...td, color: (s.duplicates_sent || s.actions_after_cancel) ? '#f19999' : undefined }}>{s.duplicates_sent} · {s.actions_after_cancel}</td></tr>))}</tbody></table>

      <h2 style={{ fontSize: 17 }}>How far she got, by venue type</h2>
      <table style={{ borderCollapse: 'collapse', width: '100%' }}><thead><tr><th style={th}>Venue type</th><th style={th}>Bookings</th>{stages.map(x => <th key={x} style={th}>stopped after {x}</th>)}</tr></thead>
        <tbody>{(Object.entries(w.how_far_by_venue_type || {}) as [string, S][]).map(([k, v]) => (<tr key={k}><td style={td}>{k}</td><td style={td}>{v.n}</td>{stages.map(x => <td key={x} style={td}>{v.furthest[x]}</td>)}</tr>))}</tbody></table>

      <h2 style={{ fontSize: 17 }}>Why she stopped (biggest first)</h2>
      <table style={{ borderCollapse: 'collapse' }}><tbody>{Object.entries(w.stop_reasons || {}).map(([k, v]) => (<tr key={k}><td style={td}>{k}</td><td style={td}>{String(v)}</td></tr>))}
        {!Object.keys(w.stop_reasons || {}).length ? <tr><td style={td}>None this week</td></tr> : null}</tbody></table>

      <h2 style={{ fontSize: 17 }}>Cost</h2>
      <table style={{ borderCollapse: 'collapse' }}><tbody>
        {(Object.entries(w.cost.tokens_by_model || {}) as [string, S][]).map(([m, u]) => (<tr key={m}><td style={td}>{m}</td><td style={td}>{u.calls} calls · in {u.in.toLocaleString()} · out {u.out.toLocaleString()} · cache write {u.cw.toLocaleString()} · cache read {u.cr.toLocaleString()}</td></tr>))}
        <tr><td style={td}>Per booking (tokens)</td><td style={td}>{JSON.stringify(w.cost.per_booking_tokens ?? '—')}</td></tr>
        <tr><td style={td}>Per confirmed booking (tokens)</td><td style={td}>{JSON.stringify(w.cost.per_confirmed_tokens ?? '—')}</td></tr>
        <tr><td style={td}>Call minutes · Places reads · searches</td><td style={td}>{w.cost.call_minutes} · {w.cost.places_reads} · {w.cost.searches}</td></tr>
        <tr><td style={td}>Measuring overhead</td><td style={td}>{w.measuring_overhead_us_per_event ?? '—'} µs per stream event · writer {JSON.stringify(j.writer)}</td></tr>
      </tbody></table>
    </main>
  )
}
