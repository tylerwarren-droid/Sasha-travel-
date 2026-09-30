'use client'

/**
 * S-33 · Phone a venue — prepare → read back → yes → Sasha calls → what they said.
 *
 * Every step ends in something visible (scripts/check-outcome-surfaces.mjs holds this file to it):
 *   · calls off on the server → said, with the button showing what it waits for; no "Yes" that cannot dial
 *   · Bland refused the call → "I couldn't place the call: <Bland's own words>" — never "calling"
 *   · the call finished → yes / no / unclear, the venue's own words, and that the outcome is an AI reading
 * The number is never typed here: the server holds it (backend/booking_signer/calls.py).
 */
import { useEffect, useState } from 'react'
import { bookingUrl as apiUrl, bookingHeaders as apiHeaders } from '@/lib/booking-api'
import { GatedButton } from './GatedButton'

type CallsHealth = { enabled?: boolean; bland_configured?: boolean; per_day?: number; venues?: Record<string, { number_set?: boolean; language?: string; why?: string }> }
type CallView = {
  call_id: string; status: string; outcome?: 'yes' | 'no' | 'unclear' | null; venue_words?: string | null; quote?: string | null
  raised?: Array<{ what: string; quote: string }>; why?: string | null; read_by?: string | null; say?: string | null
}
type Phase = 'idle' | 'preparing' | 'read_back' | 'placing' | 'on_call' | 'finished' | 'stopped'

const VENUE = 'test-line'
const POLL_MS = 5000
const POLL_LIMIT = 90   // 7½ minutes: longer than Bland's 4-minute ceiling on the call itself
const TIMEOUT_MS = 20000

async function req(path: string, body?: unknown): Promise<{ ok: boolean; status: number; json: Record<string, unknown> }> {
  const ctl = new AbortController()
  const timer = setTimeout(() => ctl.abort(), TIMEOUT_MS)
  let r: Response
  try {
    r = await fetch(apiUrl(path), body === undefined ? { headers: apiHeaders(), signal: ctl.signal } : { method: 'POST', headers: apiHeaders(), body: JSON.stringify(body), signal: ctl.signal })
  } catch (e) {
    throw new Error((e as Error).name === 'AbortError' ? `Sasha's server did not answer within ${TIMEOUT_MS / 1000}s` : `could not reach Sasha's server (${(e as Error).message})`)
  } finally { clearTimeout(timer) }
  let json: Record<string, unknown> = {}
  try { json = await r.json() } catch { /* reported by status below */ }
  return { ok: r.ok, status: r.status, json }
}

const refusal = (j: Record<string, unknown>, status: number) =>
  `${typeof j.rule === 'string' ? j.rule : `HTTP ${status}`}${typeof j.message === 'string' ? ` — ${j.message}` : ''}`

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms))

/** `readId` (S-36): call the venue Magellan read, on the number it read. Without it: the test line. */
export function PhoneCall({ defaults, readId, venueLabel, factIndex }: { defaults: { name: string; phone: string }; readId?: string; venueLabel?: string; factIndex?: number }) {
  const [health, setHealth] = useState<CallsHealth | 'unreachable' | null>(null)
  const [form, setForm] = useState({ date: '', time: '20:00', party: 2, name: defaults.name, phone: '' })
  const [phase, setPhase] = useState<Phase>('idle')
  const [lines, setLines] = useState<string[]>([])
  const [prepared, setPrepared] = useState<{ call_id: string; sha256: string } | null>(null)
  const [view, setView] = useState<CallView | null>(null)
  const [note, setNote] = useState<string | null>(null)

  useEffect(() => {
    req('/api/booking/health').then((r) => setHealth(((r.json as { calls?: CallsHealth }).calls) ?? 'unreachable')).catch(() => setHealth('unreachable'))
  }, [])

  const h = health === 'unreachable' || health === null ? null : health
  const venue = h?.venues?.[VENUE]
  const serverNeeds = [
    health === null && 'Sasha’s server to answer',
    health === 'unreachable' && 'Sasha’s server (it did not answer)',
    h && !h.enabled && 'phone calls to be switched on (SASHA_CALLS_ENABLED on the server)',
    h && !h.bland_configured && 'the calling service key (BLAND_API_KEY on the server)',
    !readId && h && venue && !venue.number_set && 'the test line’s number (SASHA_TEST_CALL_NUMBER on the server)',
  ]

  async function prepare() {
    setPhase('preparing'); setNote(null); setView(null)
    const r = await req('/api/booking/calls', { ...(readId ? { read_id: readId, ...(factIndex !== undefined ? { fact_index: factIndex } : {}) } : { venue: VENUE }), date: form.date, time: form.time, party: form.party, name: form.name, phone: form.phone || undefined })
    if (!r.ok) { setPhase('stopped'); setNote(`Not prepared: ${refusal(r.json, r.status)}. Nothing was dialled.`); return }
    const rb = r.json.read_back as { lines: string[]; sha256: string }
    setLines(rb.lines); setPrepared({ call_id: r.json.call_id as string, sha256: rb.sha256 }); setPhase('read_back')
  }

  async function place() {
    if (!prepared) return
    setPhase('placing'); setNote(null)
    const r = await req(`/api/booking/calls/${prepared.call_id}/place`, { read_back_sha256: prepared.sha256, approval: { how: 'button', said: null } })
    if (!r.ok) { setPhase('stopped'); setNote(`Not called: ${refusal(r.json, r.status)}. Nothing was dialled.`); return }
    if (r.json.status !== 'placed') { setPhase('stopped'); setNote(String(r.json.say ?? 'The call was not placed.')); return }
    setPhase('on_call'); setNote(String(r.json.say ?? 'Calling now.'))
    for (let i = 0; i < POLL_LIMIT; i++) {
      await sleep(POLL_MS)
      const g = await req(`/api/booking/calls/${prepared.call_id}`)
      if (!g.ok) { setNote(`Could not check the call just now: ${refusal(g.json, g.status)}. Still trying.`); continue }
      const v = g.json as unknown as CallView
      setView(v)
      if (v.status !== 'placed') { setPhase(v.status === 'answered' || v.status === 'not_reached' ? 'finished' : 'stopped'); return }
    }
    setPhase('stopped'); setNote('The call has not finished after 7½ minutes. Its result is kept on the server — reload to check again.')
  }

  const run = (f: () => Promise<void>) => () => {
    f().catch((e) => { setPhase('stopped'); setNote(`Stopped: ${(e as Error).message}. Nothing more was done.`) })
  }

  const formNeeds = [!form.date && 'a date', !form.time && 'a time', !(form.party >= 1) && 'a party size', form.name.trim().length < 2 && 'a name']

  return (
    <section className="mt-8 rounded border p-4">
      <h2 className="text-lg font-semibold">{venueLabel ? `Phone ${venueLabel}` : 'Phone a venue'}</h2>
      <p className="rounded bg-red-50 p-2 font-medium text-red-900">⚠ This places a REAL phone call to the number shown in the read-back, once you press “Yes — call them”.</p>
      <p className="text-sm opacity-80">Sasha calls as an AI assistant, on your behalf, and tells you exactly what they said. She never agrees to a deposit, a fee, a card or a different time.</p>
      {!readId && h?.venues?.[VENUE] && <p className="text-xs opacity-70">Venue: the Sasha test line ({venue?.language ?? '—'}). At most {h.per_day} calls a day on this server.</p>}

      <div className="mt-3 grid grid-cols-2 gap-2 text-sm">
        <label>Date <input className="w-full rounded border px-2 py-1" type="date" value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })} /></label>
        <label>Time <input className="w-full rounded border px-2 py-1" type="time" value={form.time} onChange={(e) => setForm({ ...form, time: e.target.value })} /></label>
        <label>Party <input className="w-full rounded border px-2 py-1" type="number" min={1} max={20} value={form.party} onChange={(e) => setForm({ ...form, party: Number(e.target.value) })} /></label>
        <label>Name <input className="w-full rounded border px-2 py-1" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></label>
        <label className="col-span-2">Your number, given only if they ask (optional) <input className="w-full rounded border px-2 py-1" placeholder="+351…" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} /></label>
      </div>

      <div className="mt-3">
        <GatedButton label="Prepare the call" onClick={run(prepare)}
          needs={[...serverNeeds, ...formNeeds, phase === 'preparing' && 'the read-back', (phase === 'placing' || phase === 'on_call') && 'the call in progress to finish']} />
      </div>

      {lines.length > 0 && (
        <div className="mt-4 rounded bg-black/5 p-3 text-sm">
          <p className="font-medium">Sasha will read this back — your yes covers exactly these words:</p>
          <ol className="ml-5 list-decimal">{lines.map((l, i) => <li key={i}>{l}</li>)}</ol>
          <div className="mt-2">
            <GatedButton label="Yes — call them" onClick={run(place)}
              needs={[...serverNeeds, phase !== 'read_back' && phase !== 'placing' && phase !== 'on_call' && phase !== 'finished' && 'a fresh read-back']}
              done={(phase === 'placing' || phase === 'on_call' || phase === 'finished') && 'Approved — a call is placed once per yes.'} />
          </div>
        </div>
      )}

      {note && <p className="mt-3 text-sm">{note}</p>}

      {view && view.status !== 'placed' && (
        <div className="mt-3 rounded border p-3 text-sm">
          <p className="font-medium">{view.say}</p>
          {view.outcome && <p>Outcome: <strong>{view.outcome === 'yes' ? 'they said yes' : view.outcome === 'no' ? 'they said no' : 'unclear'}</strong>{view.read_by ? <span className="opacity-70"> — {view.read_by}</span> : null}</p>}
          {view.venue_words ? <p className="mt-1">What they said, word for word: “{view.venue_words}”</p> : null}
          {(view.raised ?? []).length > 0 && <ul className="ml-5 list-disc">{(view.raised ?? []).map((r, i) => <li key={i}>{r.what}: “{r.quote}”</li>)}</ul>}
          {view.why && <p className="text-xs opacity-70">{view.why}</p>}
        </div>
      )}
    </section>
  )
}
