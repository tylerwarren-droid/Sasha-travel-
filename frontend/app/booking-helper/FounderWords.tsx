'use client'

/**
 * Sasha 253 · G15 — the founder's WhatsApp words, here on the ops console (docs/sasha/S252-whatsapp-capabilities.md rows 35, 62,
 * 73-75): the CAPTCHA test, the TEST deposit page, the hotel engine-link check and the space he is in. Each button calls the
 * founder-only server route that runs the SAME code as the word did (backend/booking_signer/demo_ops.py). "Reset the demo" is in
 * the Investor demo block above. The words keep working on the old WhatsApp flow until it is retired.
 */
import { useState } from 'react'
import { bookingReq, guestRefusal as refusal } from '@/lib/booking-client'
import { GatedButton } from './GatedButton'

type Hotel = { n: number; name: string; engine: string; url?: string; answer?: string | null }
const ANSWERS = ['filled', 'not filled', 'wrong page'] as const

export function FounderWords() {
  const [words, setWords] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [hotels, setHotels] = useState<Hotel[] | null>(null)
  async function run(path: string, label: string, body?: unknown) {
    setBusy(true); setWords(`${label}…`)
    try {
      const r = await bookingReq(path, body, 120000)
      const j = r.json as Record<string, unknown>
      setWords(r.ok ? `${label}: ${String(j.say ?? 'done')}` : `${label} — ${refusal(j, r.status)}.`)
      return r.ok ? j : null
    } catch (e) { setWords((e as Error).message); return null } finally { setBusy(false) }
  }
  async function loadCheck() {
    const j = await run('/api/booking/ops/demo/engine-check', 'Engine check')
    if (j) setHotels((j.hotels as Hotel[]) ?? [])
  }
  async function answer(n: number, a: string) {
    const j = await run('/api/booking/ops/demo/engine-check', `Link ${n}`, { n, answer: a })
    if (j) await loadCheck()
  }
  const needs = [busy && 'the last step to finish']
  return (
    <section className="space-y-2 rounded border p-3">
      <h2 className="font-semibold">Founder tools (were WhatsApp words)</h2>
      <div className="flex flex-wrap gap-2">
        <GatedButton label="Send me the CAPTCHA test" onClick={() => { run('/api/booking/ops/demo/captcha-test', 'CAPTCHA test', {}) }} needs={needs} />
        <GatedButton label="TEST deposit page to my WhatsApp" onClick={() => { run('/api/booking/ops/demo/test-deposit', 'TEST deposit', {}) }} needs={needs} />
        <GatedButton label="Which space am I in?" onClick={() => { run('/api/booking/ops/demo/space', 'Space') }} needs={needs} />
        <GatedButton label="Hotel engine check" onClick={() => { loadCheck() }} needs={needs} />
      </div>
      {words && <p>{words}</p>}
      {hotels && hotels.length > 0 && (
        <ul className="space-y-1">
          {hotels.map(h => (
            <li key={h.n} className="flex flex-wrap items-center gap-2">
              <span>{h.n}. {h.name} ({h.engine}){h.url && <> — <a className="underline" href={h.url} target="_blank" rel="noopener noreferrer">open the link</a></>}:</span>
              {h.answer
                ? <strong>{h.answer}</strong>
                : ANSWERS.map(a => <GatedButton key={a} label={a} onClick={() => { answer(h.n, a) }} needs={needs} />)}
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
