'use client'

/**
 * S-25 · The booking page — DRY RUN ONLY. docs/sasha-contract/README.md §4–§7.
 *
 * This page RELAYS. It never builds, edits or signs a task, and it never decides an outcome:
 *   · the server records the intent and returns the words to read back   (POST /api/booking/intents)
 *   · the user says yes; the server signs the task                        (POST /api/booking/intents/{id}/issue)
 *   · the helper, in this Chrome, fills the venue's form and stops before sending
 *   · the helper's device-signed report goes to the server, which verifies it and says what to tell the user
 *                                                                          (POST /api/booking/reports)
 * and only then is the helper told it may drop the report (ACK).
 *
 * ⛔ There is no live mode here: `mode` is the constant "dry_run", and the server refuses "live" anyway.
 * ⚠ The helper accepts only a TOP-LEVEL tab on https://project.kanoe.ai — never the Demo tab, which frames Sasha.
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { bookingUrl as apiUrl, bookingHeaders as apiHeaders } from '@/lib/booking-api'
import { GatedButton } from './GatedButton'
import { PhoneCall } from './PhoneCall'
import { Ladder } from './Ladder'
import { FounderGate } from './FounderGate'

const MODE = 'dry_run' as const
const VENUE = 'restaurante-psi'
const HELPER_ID_KEY = 'sasha.bookingHelperId'
/**
 * P807mv · The DEMO guest. Read-back line 4 says the email and telephone ALOUD, so a room must hear a demo
 * profile, never the founder's own. Used when Sasha's hand-off link says `profile=demo`; always editable.
 * The number is in Ofcom's range reserved for drama (020 7946 0xxx), so it rings no one.
 */
const DEMO_PROFILE = { name: 'Jon Peters', email: 'jon@kanoe.ai', phone: '+44 20 7946 0123' }
const VENUE_DISPLAY: Record<string, string> = { 'Restaurante Psi': 'Restaurante Psi, Lisbon' }
// Psi's served hours (contract §3.6): 12:30–15:00 and 19:30–22:00, in 30-minute steps; no Sunday.
const SLOTS = ['12:30', '13:00', '13:30', '14:00', '14:30', '15:00', '19:30', '20:00', '20:30', '21:00', '21:30', '22:00']
const PHASES = ['verifying', 'awaiting_permission', 'filling', 'submitting', 'reading'] as const

type Msg = { type: string; [k: string]: unknown }
type Port = {
  postMessage(m: Msg): void
  onMessage: { addListener(fn: (m: Msg) => void): void }
  onDisconnect: { addListener(fn: () => void): void }
  disconnect(): void
}
type Runtime = { connect?: (id: string) => Port; lastError?: { message?: string } }
type Health = {
  /** true when the page could not ask at all — never read as "the server said not ready" */
  unreachable?: boolean
  mounted?: boolean
  signer?: { configured?: boolean; matches_pinned?: boolean; fingerprint?: string | null }
  storage?: { configured?: boolean; provisioned?: boolean; missing?: string[] }
}
type Line = { at: string; text: string; tone: 'info' | 'ok' | 'stop' }
type Reservation = {
  id: string; venue: string; date: string; time: string; timezone: string; party: number
  status: string; status_words: string; booking_reference: string | null; sasha_reference: string
}

const runtime = (): Runtime | undefined =>
  (typeof window === 'undefined' ? undefined : (window as unknown as { chrome?: { runtime?: Runtime } }).chrome?.runtime)

const CALL_TIMEOUT_MS = 20000

async function call(path: string, body?: unknown): Promise<{ ok: boolean; status: number; json: Record<string, unknown> }> {
  // ⚠ a request that never answers must SAY so — without a limit it would leave the page silent and greyed out
  const ctl = new AbortController()
  const timer = setTimeout(() => ctl.abort(), CALL_TIMEOUT_MS)
  let r: Response
  try {
    r = await fetch(apiUrl(path), body === undefined ? { headers: apiHeaders(), signal: ctl.signal } : { method: 'POST', headers: apiHeaders(), body: JSON.stringify(body), signal: ctl.signal })
  } catch (e) {
    throw new Error((e as Error).name === 'AbortError' ? `Sasha's server did not answer within ${CALL_TIMEOUT_MS / 1000}s` : `could not reach Sasha's server (${(e as Error).message})`)
  } finally { clearTimeout(timer) }
  let json: Record<string, unknown> = {}
  try { json = await r.json() } catch { /* a non-JSON answer is reported by status below */ }
  return { ok: r.ok, status: r.status, json }
}

/** "Mon 5 Oct" — weekday, day, month, from the stored calendar date (no timezone arithmetic on a date). */
const shortDate = (iso: string) => {
  const d = new Date(`${iso}T12:00:00Z`)
  return `${d.toLocaleDateString('en-GB', { weekday: 'short', timeZone: 'UTC' })} ${d.getUTCDate()} ${d.toLocaleDateString('en-GB', { month: 'short', timeZone: 'UTC' })}`
}

const refusal = (j: Record<string, unknown>, status: number) =>
  `${typeof j.rule === 'string' ? j.rule : `HTTP ${status}`}${typeof j.message === 'string' ? ` — ${j.message}` : ''}`

export default function BookingHelperPage() {
  const [framed, setFramed] = useState(false)
  const [helperId, setHelperId] = useState('')
  const [health, setHealth] = useState<Health | null>(null)
  const [deviceId, setDeviceId] = useState<string | null>(null)
  const [paired, setPaired] = useState(false)
  const [busy, setBusy] = useState(false)
  // ⚠ state, not the port ref: a ref does not re-render, so a button gated on it is only as fresh as the last render
  const [connected, setConnected] = useState(false)
  // ⚠ "not attempted" is a STATE (P807mt-S4), not an empty log — an empty log is also what a silent failure looks like
  const [started, setStarted] = useState(false)
  const [log, setLog] = useState<Line[]>([])
  const [form, setForm] = useState({ date: '', time: '20:00', party: 2, name: '', email: '', phone: '' })
  const [intent, setIntent] = useState<{ id: string; lines: string[] } | null>(null)
  // S-26: the helper ID is plumbing. Known (from storage or the link) → never shown, connected automatically.
  const [knownHelper, setKnownHelper] = useState(false)
  const [autoTried, setAutoTried] = useState(false)
  const [tripItemId, setTripItemId] = useState<string | null>(null)
  // S-26: the last beat — the reservation as the server holds it, read back after the report is stored
  const [reservation, setReservation] = useState<Reservation | null>(null)
  const [phases, setPhases] = useState<string[]>([])

  const port = useRef<Port | null>(null)
  const waiters = useRef<Array<{ type: string; resolve: (m: Msg) => void }>>([])

  const note = useCallback((text: string, tone: Line['tone'] = 'info') =>
    setLog((l) => [...l, { at: new Date().toLocaleTimeString('en-GB'), text, tone }]), [])
  /** Every action opens with this: it marks the page as having attempted something, and says what. */
  const begin = useCallback((text: string) => { setStarted(true); note(text) }, [note])

  useEffect(() => {
    setFramed(window.top !== window.self)
    const fromQuery = new URLSearchParams(window.location.search).get('helper')
    let stored = ''
    try { stored = localStorage.getItem(HELPER_ID_KEY) ?? '' } catch { /* storage may be blocked */ }
    setHelperId(fromQuery || stored)
    setKnownHelper(!!(fromQuery || stored))
    // S-26: Sasha's hand-off link pre-fills what the guest said plainly; nothing else is guessed
    const q = new URLSearchParams(window.location.search)
    if (!q.get('venue') || q.get('venue') === VENUE) {
      const d = q.get('date'), t = q.get('time'), n = Number(q.get('party'))
      setForm((f) => ({
        ...f,
        ...(d && /^\d{4}-\d{2}-\d{2}$/.test(d) ? { date: d } : {}),
        ...(t && SLOTS.includes(t) ? { time: t } : {}),
        ...(Number.isInteger(n) && n >= 1 && n <= 20 ? { party: n } : {}),
        ...(q.get('profile') === 'demo' ? DEMO_PROFILE : {}),
      }))
    }
    call('/api/booking/health').then((r) => setHealth(r.json as Health)).catch(() => setHealth({ unreachable: true }))
  }, [])

  const ready = !!(health?.mounted && health.signer?.matches_pinned && health.storage?.provisioned)

  // ── the report: relay to the server, and ACK only once it has verified and stored it ──────────────
  const relayReport = useCallback(async (m: Msg) => {
    const { report, task_digest, device_id, device_signature } = m as unknown as {
      report: Record<string, unknown>; task_digest: string | null; device_id: string; device_signature: string
    }
    const r = await call('/api/booking/reports', { report, task_digest, device_id, device_signature })
    if (!r.ok) {
      // ⚠ contract §5.4: not recorded, and NOT acknowledged — the helper keeps it for PENDING
      note(`The server did not accept this report: ${refusal(r.json, r.status)}. Nothing is assumed either way.`, 'stop')
      return
    }
    if (typeof r.json.say === 'string') note(r.json.say, r.json.outcome ? 'ok' : 'info')
    if (typeof r.json.status_line === 'string') note(r.json.status_line, 'ok')
    if (r.json.already_recorded) note('This report had already been recorded; it was not recorded twice.')
    const intentId = typeof report?.intent_id === 'string' ? report.intent_id : null
    if (intentId) port.current?.postMessage({ type: 'ACK', intent_id: intentId })
    // S-26: read the reservation back from the server — the page shows what is STORED, never what it assumes
    if (typeof r.json.reservation_id === 'string') {
      const id = r.json.reservation_id
      try {
        const list = await call('/api/booking/reservations')
        const found = ((list.json.reservations as Reservation[] | undefined) ?? []).find((x) => x.id === id)
        if (found) setReservation(found)
        else note('The report was stored, but the reservation could not be read back yet.', 'stop')
      } catch (e) {
        note(`The report was stored, but the reservation could not be read back: ${(e as Error).message}.`, 'stop')
      }
    }
  }, [note])

  const onMessage = useCallback((m: Msg) => {
    if (m.type === 'PROGRESS' && typeof m.phase === 'string') { setPhases((p) => [...p, m.phase as string]); return }
    if (m.type === 'REPORT') {
      // ⛔ P807mt-S2: never launched unobserved. A report that cannot be delivered is SAID — contract §5.5:
      // a missing report is never "nothing happened". The helper keeps it until the server has stored it.
      relayReport(m).catch((e) => note(
        `The report could not be delivered to Sasha’s server: ${(e as Error).message}. The helper is keeping it — press “Resend pending reports” to offer it again. Nothing is assumed either way.`,
        'stop',
      ))
    }
    if (m.type === 'REFUSED' || m.type === 'ERROR') note(`The helper ${m.type === 'REFUSED' ? 'refused this page' : 'reported its own error'}: ${String(m.why)}`, 'stop')
    const i = waiters.current.findIndex((w) => w.type === m.type)
    if (i >= 0) { const [w] = waiters.current.splice(i, 1); w.resolve(m) }
  }, [note, relayReport])

  const next = (type: string, ms = 15000) => new Promise<Msg>((resolve, reject) => {
    const w = { type, resolve }
    waiters.current.push(w)
    setTimeout(() => {
      const i = waiters.current.indexOf(w)
      if (i >= 0) { waiters.current.splice(i, 1); reject(new Error(`no ${type} from the helper within ${ms / 1000}s`)) }
    }, ms)
  })

  // ── connect, identify, pair ────────────────────────────────────────────────────────────────────
  const connect = async () => {
    setBusy(true)
    begin('Connecting to the helper…')
    try {
      const rt = runtime()
      if (!rt?.connect) throw new Error('Chrome does not offer the helper to this page — it is not installed, or this is not Chrome')
      if (!/^[a-p]{32}$/.test(helperId)) throw new Error('the helper ID is the 32 letters Chrome shows on chrome://extensions')
      try { localStorage.setItem(HELPER_ID_KEY, helperId) } catch { /* not essential */ }
      const p = rt.connect(helperId)
      port.current = p
      p.onMessage.addListener(onMessage)
      p.onDisconnect.addListener(() => { port.current = null; setConnected(false); setDeviceId(null); note(`The helper disconnected${rt.lastError?.message ? `: ${rt.lastError.message}` : ''}.`, 'stop') })
      const hello = next('HELLO')
      p.postMessage({ type: 'HELLO', protocol: 1 })
      const h = await hello
      const id = String(h.device_id)
      setDeviceId(id)
      setConnected(true)
      note(`Connected to ${String(h.agent)} on this browser.`, 'ok')
      const devs = await call('/api/booking/devices')
      if (!devs.ok) throw new Error(refusal(devs.json, devs.status))
      if ((devs.json.devices as string[] | undefined)?.includes(id)) { setPaired(true); note('This browser is already paired.', 'ok') }
      // reports owed from an earlier visit (contract §5.5: a missing report is never "nothing happened")
      p.postMessage({ type: 'PENDING' })
    } catch (e) {
      note(`Could not connect: ${(e as Error).message}.`, 'stop')
    } finally { setBusy(false) }
  }

  const pair = async () => {
    setBusy(true)
    begin('Pairing this browser — asking Sasha’s server for a challenge…')
    try {
      const ch = await call('/api/booking/pairing/challenge', {})
      if (!ch.ok) throw new Error(refusal(ch.json, ch.status))
      const answer = next('PAIR')
      port.current?.postMessage({ type: 'PAIR', challenge: ch.json.challenge })
      const a = await answer
      if (a.ok !== true) throw new Error(`the helper would not pair: ${String(a.why)}`)
      const r = await call('/api/booking/pairing', {
        challenge: ch.json.challenge, device_id: a.device_id, device_public_spki: a.device_public_spki, origin: a.origin, signature: a.signature,
      })
      if (!r.ok) throw new Error(refusal(r.json, r.status))
      setPaired(true)
      note('This browser is paired to the account.', 'ok')
    } catch (e) {
      note(`Pairing failed: ${(e as Error).message}.`, 'stop')
    } finally { setBusy(false) }
  }

  // ── the booking: record the intent, read back, yes, sign, run ─────────────────────────────────────
  const prepare = async () => {
    setBusy(true); setIntent(null); setPhases([])
    begin('Recording the booking and asking for the words to read back…')
    try {
      const r = await call('/api/booking/intents', { venue: VENUE, mode: MODE, ...form })
      if (!r.ok) throw new Error(refusal(r.json, r.status))
      const rb = r.json.read_back as { lines: string[] }
      setIntent({ id: String(r.json.intent_id), lines: rb.lines })
      setTripItemId(typeof r.json.trip_item_id === 'string' ? r.json.trip_item_id : null)
      setReservation(null)
    } catch (e) {
      note(`Nothing was recorded: ${(e as Error).message}.`, 'stop')
    } finally { setBusy(false) }
  }

  const approve = async () => {
    if (!intent || !deviceId) return
    setBusy(true); setPhases([])
    begin('Asking Sasha’s server to sign the task…')
    try {
      const r = await call(`/api/booking/intents/${intent.id}/issue`, { device_id: deviceId, approval: { how: 'button', said: null } })
      if (!r.ok) throw new Error(refusal(r.json, r.status))
      // ⚠ relayed EXACTLY as the server returned it — the page never edits a task
      port.current?.postMessage({ type: 'RUN', payload: r.json.payload, signature: r.json.signature })
      note('The signed task went to the helper. Watch for Chrome asking to allow the restaurant’s site — that step is yours.')
      setIntent(null)
    } catch (e) {
      note(`The task was not signed: ${(e as Error).message}. Nothing was sent to the restaurant.`, 'stop')
    } finally { setBusy(false) }
  }

  const resendPending = () => {
    begin('Asking the helper for any reports it is still holding…')
    port.current?.postMessage({ type: 'PENDING' })
  }

  // S-26: a browser that is already set up connects on its own — the guest never sees or types the helper ID
  useEffect(() => {
    if (knownHelper && ready && !connected && !busy && !autoTried) {
      setAutoTried(true)
      connect().catch((e) => note(`Could not connect: ${(e as Error).message}.`, 'stop'))
    }
  })

  // ── the page ──────────────────────────────────────────────────────────────────────────────────
  const tomorrow = new Date(Date.now() + 86400000).toISOString().slice(0, 10)
  const sunday = form.date !== '' && new Date(`${form.date}T12:00:00Z`).getUTCDay() === 0
  // ⚠ every button is a GatedButton: it cannot be greyed out without rendering what it is waiting for
  const prepareNeeds = [
    !paired && 'a paired browser (step 2)',
    !form.date && 'a date',
    sunday && 'a day other than Sunday',
    !form.name && 'a name',
    !form.email && 'an email',
    !form.phone && 'a telephone',
    busy && 'the step in progress to finish',
  ]
  const stepInProgress = busy && 'the step in progress to finish'

  if (framed) {
    return (
      <main className="mx-auto my-6 max-w-xl rounded-lg bg-white p-6 text-neutral-900">
        <p>The booking helper only talks to Sasha in her own tab.</p>
        <a className="underline" href={typeof window === 'undefined' ? '#' : window.location.href} target="_blank" rel="noopener">Open this page in its own tab</a>
      </main>
    )
  }

  return (
    // S-41 · founder only: signed out, the page is a passphrase field and nothing else
    <FounderGate>
    {/* ⚠ The site's global style is DARK (globals.css: #0a0a0f, near-white text) and inputs inherit that text
        colour onto the browser's white field — typed values were invisible. This page carries its own light
        surface so every field, option and log line is legible whatever the site's theme. */}
    <main className="mx-auto my-6 max-w-2xl space-y-6 rounded-lg bg-white p-6 text-sm text-neutral-900 [color-scheme:light]">
      <header className="space-y-1">
        <h1 className="text-xl font-semibold">Book a table</h1>
        {/* S-41 G1 · the dry-run promise belongs to the form helper ONLY — the phone and email sections below are real */}
        <p className="rounded bg-amber-50 p-2 text-amber-900">
          Form helper (steps 1–3): a dry run — the helper opens the restaurant’s page on this computer, fills it in, and stops before sending. Nothing is sent to the restaurant from these steps.
        </p>
      </header>

      <section className="space-y-1">
        <h2 className="font-semibold">1 · Sasha’s side</h2>
        {health === null ? <p>Checking…</p> : (
          <ul>
            {health.unreachable && <li className="text-red-800">Could not reach Sasha’s server to ask — this is not the server saying no.</li>}
            <li>Booking routes: {health.mounted ? 'mounted' : 'not reachable'}</li>
            <li>Signing key: {health.signer?.matches_pinned ? `set, fingerprint ${health.signer.fingerprint}` : 'not ready — nothing can be signed'}</li>
            <li>Storage: {health.storage?.provisioned ? 'ready' : `not ready${health.storage?.missing?.length ? ` (missing: ${health.storage.missing.join(', ')})` : ''}`}</li>
          </ul>
        )}
      </section>

      <section className="space-y-2">
        <h2 className="font-semibold">2 · The helper in this browser</h2>
        {knownHelper ? null : (
          // ⚠ asked ONCE per browser, only when nothing is known — then remembered and never shown again
          <label className="block">Set up this browser — the helper’s ID (once, from chrome://extensions)
            <input className="mt-1 w-full rounded border p-1 font-mono" value={helperId} onChange={(e) => setHelperId(e.target.value.trim())} />
          </label>
        )}
        <div className="flex flex-wrap gap-3">
          <GatedButton label="Connect" onClick={connect}
            done={connected && 'Connected.'}
            needs={[health === null && 'the check of Sasha’s side (step 1)', health !== null && !ready && 'Sasha’s side (step 1) to be ready', stepInProgress]} />
          <GatedButton label="Pair this browser" onClick={pair}
            done={paired && 'This browser is paired.'}
            needs={[!connected && 'Connect, first', stepInProgress]} />
          <GatedButton label="Resend pending reports" onClick={resendPending}
            needs={[!connected && 'Connect, first', stepInProgress]} />
        </div>
        {deviceId && <p className="font-mono text-xs">Device {deviceId.slice(0, 16)}… · {paired ? 'paired' : 'not paired yet'}</p>}
      </section>

      <section className="space-y-2">
        <h2 className="font-semibold">3 · The booking — Restaurante Psi, Lisbon</h2>
        <div className="grid grid-cols-2 gap-2">
          <label>Date<input type="date" min={tomorrow} className="block w-full rounded border p-1" value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })} /></label>
          <label>Time<select className="block w-full rounded border p-1" value={form.time} onChange={(e) => setForm({ ...form, time: e.target.value })}>{SLOTS.map((s) => <option key={s}>{s}</option>)}</select></label>
          <label>People<select className="block w-full rounded border p-1" value={form.party} onChange={(e) => setForm({ ...form, party: Number(e.target.value) })}>{Array.from({ length: 20 }, (_, i) => i + 1).map((n) => <option key={n} value={n}>{n}</option>)}</select></label>
          <label>Name<input className="block w-full rounded border p-1" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></label>
          <label>Email<input type="email" className="block w-full rounded border p-1" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></label>
          <label>Telephone<input className="block w-full rounded border p-1" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} /></label>
        </div>
        {sunday && <p className="text-amber-800">Psi takes no bookings on Sunday.</p>}
        <GatedButton label="Prepare" onClick={prepare} needs={prepareNeeds} />
      </section>

      {intent && (
        <section className="space-y-2 rounded border p-3">
          <h2 className="font-semibold">4 · Read this back</h2>
          {/* ⚠ exactly the server's five lines — the yes is bound to their hash */}
          {intent.lines.map((l, i) => <p key={i}>{l}</p>)}
          <div className="flex gap-2">
            <GatedButton label="Yes — prepare it (dry run)" className="bg-black text-white" onClick={approve}
              needs={[!connected && 'the helper to be connected (step 2)', stepInProgress]} />
            <GatedButton label="No" onClick={() => { setIntent(null); begin('Not approved. Nothing was signed.') }} needs={[stepInProgress]} />
          </div>
        </section>
      )}

      {reservation && reservation.id === tripItemId && (
        // P807mv §3 · the reservation as STORED, in two lines: what it is, and what it is not. The only number is
        // Sasha's own, labelled as hers — a dry run creates no restaurant reservation, and Psi gives no number.
        <section className="space-y-1 rounded border-2 border-emerald-700 p-3">
          <h2 className="font-semibold">Your reservation</h2>
          <p className="text-base font-semibold">
            {VENUE_DISPLAY[reservation.venue] ?? reservation.venue} · {shortDate(reservation.date)} · {reservation.time} · {reservation.party} {reservation.party === 1 ? 'person' : 'people'}
          </p>
          <p className="font-semibold">{reservation.status_words} · Sasha ref {reservation.sasha_reference}</p>
          <p className="text-xs opacity-70">No restaurant number: {reservation.booking_reference ? `the restaurant’s is ${reservation.booking_reference}` : 'Restaurante Psi gives none on its page, and a dry run creates no reservation.'}</p>
        </section>
      )}

      {phases.length > 0 && (
        <section>
          <h2 className="font-semibold">The helper</h2>
          <ol className="list-decimal pl-5">{PHASES.map((p) => <li key={p} className={phases.includes(p) ? '' : 'opacity-30'}>{p}</li>)}</ol>
        </section>
      )}

      <section>
        <h2 className="font-semibold">What happened</h2>
        {!started ? <p className="opacity-60">Nothing attempted yet.</p> : (
          <ul className="space-y-1">{log.map((l, i) => (
            <li key={i} className={l.tone === 'stop' ? 'text-red-800' : l.tone === 'ok' ? 'text-green-800' : ''}>{l.at} — {l.text}</li>
          ))}</ul>
        )}
      </section>
      <Ladder defaults={DEMO_PROFILE} />
      <PhoneCall defaults={DEMO_PROFILE} />
    </main>
    </FounderGate>
  )
}
