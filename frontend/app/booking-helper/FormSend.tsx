'use client'

/**
 * Sasha 89 · THE FORM RUNG, SUBMITTING — the venue's own booking form, filled by Sasha and sent after the guest's yes
 * (backend/booking_signer/form_rung.py). The read-back lists EVERY field and value the server will send; the yes binds
 * to its hash; it is sent once; their answer page is shown word for word. A CAPTCHA or a box agreeing to terms stops it
 * before anything is filled, and the server's reason is shown as it said it.
 */
import { useState } from 'react'
import { bookingReq, refusal } from '@/lib/booking-client'
import { GatedButton } from './GatedButton'

type Result = { status: string; say: string; their_page?: string; booking_reference?: string | null }

export function FormSend({ readId, venueLabel, defaults, at, party }: { readId: string; venueLabel: string
  defaults: { name: string; email: string; phone: string }; at?: string | null; party?: number | null }) {
  // Sasha 121 · from the chat: the day, time and party already asked for; the email may be left to the server (your account's)
  const [d, setD] = useState({ date: at ? at.slice(0, 10) : '', time: at ? at.slice(11, 16) : '21:00', party: party ?? 2,
    name: defaults.name, email: defaults.email, phone: defaults.phone })
  const [phase, setPhase] = useState<'details' | 'preparing' | 'read_back' | 'sending' | 'done' | 'stopped'>('details')
  const [rb, setRb] = useState<{ form_id: string; lines: string[]; sha256: string } | null>(null)
  const [note, setNote] = useState<string | null>(null)
  const [result, setResult] = useState<Result | null>(null)

  async function prepare() {
    setPhase('preparing'); setNote(null)
    const reservation = { schema: 'reservation/1', flow: 'book', where: {},
      who: { name: d.name.trim(), contact: { ...(d.email.trim() ? { email: d.email.trim() } : {}), mobile_e164: d.phone.replace(/[\s().-]/g, '') } },
      what: { activity: 'a table', activity_venue_lang: 'una mesa', category: 'restaurant' },
      when: { mode: 'at', at: `${d.date}T${d.time}` }, how_many: { count: d.party, unit: 'people' } }
    const r = await bookingReq('/api/booking/forms', { read_id: readId, reservation })
    if (!r.ok) { setPhase('stopped'); setNote(`Not filled — ${refusal(r.json, r.status)}. Nothing was sent.`); return }
    const b = r.json.read_back as { lines: string[]; sha256: string }
    setRb({ form_id: String(r.json.form_id), lines: b.lines, sha256: b.sha256 }); setPhase('read_back')
  }

  async function send() {
    if (!rb) return
    setPhase('sending'); setNote(null)
    const r = await bookingReq(`/api/booking/forms/${rb.form_id}/send`, { read_back_sha256: rb.sha256, approval: { how: 'button', said: null } })
    if (!r.ok) { setPhase('stopped'); setNote(`Not sent — ${refusal(r.json, r.status)}.`); return }
    setResult(r.json as unknown as Result); setPhase('done')
  }

  const run = (f: () => Promise<void>) => () => { f().catch((e) => { setPhase('stopped'); setNote(`Stopped: ${(e as Error).message}. Nothing more was done.`) }) }
  return (
    <div className="mt-4 rounded border p-3 text-sm">
      <p className="font-medium">Sasha fills {venueLabel}&rsquo;s own booking form and sends it — only after you&rsquo;ve seen every field and said yes.</p>
      <div className="mt-2 grid grid-cols-2 gap-2">
        <label>Date <input className="w-full rounded border px-2 py-1" type="date" value={d.date} onChange={(e) => setD({ ...d, date: e.target.value })} /></label>
        <label>Time <input className="w-full rounded border px-2 py-1" type="time" value={d.time} onChange={(e) => setD({ ...d, time: e.target.value })} /></label>
        <label>People <input className="w-full rounded border px-2 py-1" type="number" min={1} max={20} value={d.party} onChange={(e) => setD({ ...d, party: Number(e.target.value) })} /></label>
        <label>Name <input className="w-full rounded border px-2 py-1" value={d.name} onChange={(e) => setD({ ...d, name: e.target.value })} /></label>
        <label>Email (blank: your account&rsquo;s) <input className="w-full rounded border px-2 py-1" value={d.email} onChange={(e) => setD({ ...d, email: e.target.value })} /></label>
        <label>Phone <input className="w-full rounded border px-2 py-1" value={d.phone} onChange={(e) => setD({ ...d, phone: e.target.value })} /></label>
      </div>
      <div className="mt-2">
        <GatedButton label="Fill the form (nothing is sent yet)" onClick={run(prepare)}
          needs={[!d.date && 'a date', !d.time && 'a time', d.name.trim().length < 2 && 'a name', !!d.email.trim() && !d.email.includes('@') && 'a valid email',
            phase === 'preparing' && 'the form to be read', (phase === 'sending' || phase === 'done') && 'nothing — it has been sent']} />
      </div>
      {rb && (
        <div className="mt-3 rounded bg-black/5 p-3">
          <p className="font-medium">Exactly what will be sent — your yes covers every line:</p>
          {rb.lines.map((l, i) => <p key={i}>{l}</p>)}
          <div className="mt-2">
            <GatedButton label="Yes — send it" onClick={run(send)} needs={[phase !== 'read_back' && phase !== 'sending' && phase !== 'done' && 'a fresh read-back']}
              done={(phase === 'sending' || phase === 'done') && 'Approved — sent at most once per yes.'} />
          </div>
        </div>
      )}
      {note && <p className="mt-2">{note}</p>}
      {result && (
        <div className="mt-3 rounded border-2 border-emerald-700 p-3">
          <p className="font-semibold">{result.say}</p>
          {result.booking_reference ? <p>Their reference: {result.booking_reference}</p> : <p>They gave no reference on their page.</p>}
          {result.their_page ? <p className="mt-1 whitespace-pre-wrap">Their page, word for word: &ldquo;{result.their_page}&rdquo;</p> : null}
        </div>
      )}
    </div>
  )
}
