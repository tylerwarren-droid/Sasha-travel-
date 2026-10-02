'use client'

/**
 * Sasha 96 · CANCELLING IN THE CHAT — "cancel Botavara" → the booking it means (found by the venue's real name, from
 * its receipt) → ONE sentence → one yes (a tap or a typed/spoken yes) → she cancels it herself → "Reservation
 * cancelled", with their words as proof; the guest's copy is emailed by the server (guest_receipt).
 *
 * The cancel call is PREPARED before the question, so the yes binds to its read-back hash exactly as a booking's does
 * (one tap away under "See exactly what I'll say"). Today she cancels by phone — the call she made is the one she
 * undoes. A cancel link in their confirmation email, a reply to it, or a text are the next routes (not built yet).
 */
import { useEffect, useState } from 'react'
import { approveCall, getCall, prepareCall, refusal, reservations } from '@/lib/booking-client'
import { bookingUrl, bookingHeaders } from '@/lib/booking-api'
import { setPendingYes } from '@/lib/chat-booking-bus'
import { GatedButton } from '../booking-helper/GatedButton'
import type { Receipt } from './ReceiptCard'

type Row = { id: string; channel: string; status: string; date: string | null; receipt: string | null }
type Found = { rc: Receipt & { call_id: string; trip_item_id: string } }
type Phase = { p: 'finding' } | { p: 'none'; words: string } | { p: 'choose'; options: Found[] } | { p: 'preparing'; f: Found }
  | { p: 'ask'; f: Found; callId: string; lines: string[]; sha: string } | { p: 'cancelling'; f: Found } | { p: 'done'; f: Found; say: string; words: string | null; cancelled: boolean }
  | { p: 'refused'; words: string } | { p: 'not_now' }

const SLEEP = (ms: number) => new Promise((r) => setTimeout(r, ms))
const fold = (s: string) => s.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().replace(/[^a-z0-9 ]/g, ' ').split(/\s+/).filter((w) => w.length > 2)
const matches = (name: string, asked: string) => { const n = fold(name); const a = fold(asked); return a.length > 0 && a.every((w) => n.some((x) => x.startsWith(w) || w.startsWith(x))) }
const dayWords = (d: string | null) => (d ? new Date(`${d}T12:00:00Z`).toLocaleDateString('en-GB', { weekday: 'long', day: 'numeric', month: 'long', timeZone: 'UTC' }) : 'no day set')

export default function ChatCancel({ venue }: { venue: string }) {
  const [phase, setPhase] = useState<Phase>({ p: 'finding' })

  async function prepare(f: Found) {
    setPhase({ p: 'preparing', f })
    const r = await prepareCall({ cancels_call_id: f.rc.call_id })
    if (!r.ok) { setPhase({ p: 'refused', words: `I can't cancel it by phone right now — ${refusal(r.json, r.status)}. Nothing was dialled.` }); return }
    const rb = r.json.read_back as { lines: string[]; sha256: string }
    setPhase({ p: 'ask', f, callId: String(r.json.call_id), lines: rb.lines, sha: rb.sha256 })
  }

  useEffect(() => {
    let off = false
    ;(async () => {
      const res = await reservations()
      if (off) return
      if (!res.ok) { setPhase({ p: 'none', words: `I couldn't look up your bookings — ${refusal(res.json, res.status)}.` }); return }
      const today = new Date().toISOString().slice(0, 10)
      const rows = ((res.json.reservations ?? []) as Row[]).filter((x) => x.channel === 'phone' && x.receipt
        && !['cancelled', 'declined', 'failed'].includes(x.status) && (!x.date || x.date >= today))
      const rcs = await Promise.all(rows.map(async (x) => {
        const g = await fetch(bookingUrl(x.receipt!), { headers: bookingHeaders() })
        return g.ok ? ((await g.json()) as Found['rc']) : null
      }))
      if (off) return
      const hits = rcs.filter((rc): rc is Found['rc'] => !!rc && matches(rc.venue.name, venue)).map((rc) => ({ rc }))
      if (hits.length === 0) { setPhase({ p: 'none', words: `I can't find an upcoming booking of yours at ${venue}.` }); return }
      if (hits.length > 1) { setPhase({ p: 'choose', options: hits }); return }
      await prepare(hits[0])
    })().catch((e) => { if (!off) setPhase({ p: 'refused', words: (e as Error).message }) })
    return () => { off = true }
  // eslint-disable-next-line react-hooks/exhaustive-deps -- once per cancel request
  }, [venue])

  async function approve(callId: string, sha: string, f: Found, how: 'button' | 'chat', said: string | null) {
    setPendingYes(null)
    setPhase({ p: 'cancelling', f })
    const r = await approveCall(callId, sha, { how, said })
    if (!r.ok) { setPhase({ p: 'refused', words: `Not cancelled — ${refusal(r.json, r.status)}. Nothing was dialled.` }); return }
    if (r.json.status !== 'placed' && r.json.status !== 'uncertain') { setPhase({ p: 'refused', words: String(r.json.say ?? 'The call was not placed.') }); return }
    for (let i = 0; i < 48; i++) {
      await SLEEP(10000)
      const g = await getCall(callId)
      if (!g.ok) continue
      const v = g.json as { status: string; outcome?: string | null; say?: string | null; venue_words?: string | null }
      if (v.status === 'placed' || v.status === 'placing') continue
      setPhase({ p: 'done', f, cancelled: v.outcome === 'yes', say: v.outcome === 'yes' ? 'Reservation cancelled.' : String(v.say ?? 'It is not cancelled yet.'),
        words: v.venue_words ?? null })
      return
    }
    setPhase({ p: 'refused', words: 'The call has not finished after 8 minutes; its result is kept on the server.' })
  }

  // a typed or spoken "yes" binds to THIS cancel while its question is showing
  useEffect(() => {
    if (phase.p !== 'ask') return
    const { callId, sha, f } = phase
    setPendingYes((said) => { approve(callId, sha, f, 'chat', said).catch((e) => setPhase({ p: 'refused', words: (e as Error).message })) })
    return () => setPendingYes(null)
  // eslint-disable-next-line react-hooks/exhaustive-deps -- re-armed for each question
  }, [phase.p === 'ask' ? phase.callId : null])

  const box = { border: '1px solid rgba(0,0,0,.12)', borderRadius: 10, padding: 12, margin: '8px 0', fontSize: 14 } as const
  const sentence = (f: Found) => `Cancel ${f.rc.venue.name}, ${dayWords(f.rc.date)}${f.rc.time ? ` at ${f.rc.time}` : ''}, for ${f.rc.count ?? '—'}, under ${f.rc.for_whom ?? '—'}?`
  return (
    <div style={box}>
      {phase.p === 'finding' && <div>Finding your booking at {venue}…</div>}
      {phase.p === 'none' && <div>{phase.words}</div>}
      {phase.p === 'choose' && (
        <div>
          <div>You have more than one booking there — which one?</div>
          {phase.options.map((f) => <div key={f.rc.call_id} style={{ marginTop: 4 }}><GatedButton label={sentence(f).replace(/^Cancel /, '').replace(/\?$/, '')} onClick={() => { prepare(f).catch((e) => setPhase({ p: 'refused', words: (e as Error).message })) }} needs={[]} /></div>)}
        </div>
      )}
      {phase.p === 'preparing' && <div>Getting the cancellation ready…</div>}
      {phase.p === 'ask' && (
        <div>
          <div style={{ fontWeight: 600 }}>{sentence(phase.f)}</div>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginTop: 4 }}>
            <GatedButton label="Yes, cancel it" onClick={() => { approve(phase.callId, phase.sha, phase.f, 'button', null).catch((e) => setPhase({ p: 'refused', words: (e as Error).message })) }} needs={[]} />
            <GatedButton label="No" onClick={() => { setPendingYes(null); setPhase({ p: 'not_now' }) }} needs={[]} />
            <span style={{ fontSize: 12, opacity: 0.7 }}>or say “yes”</span>
          </div>
          <details style={{ marginTop: 6, fontSize: 13 }}>
            <summary>See exactly what I&rsquo;ll say</summary>
            <ol style={{ paddingLeft: 18 }}>{phase.lines.map((l, i) => <li key={i}>{l}</li>)}</ol>
          </details>
        </div>
      )}
      {phase.p === 'cancelling' && <div>I&rsquo;m calling {phase.f.rc.venue.name} to cancel it now…</div>}
      {phase.p === 'done' && (
        <div>
          <div style={{ fontWeight: 600 }}>{phase.say}</div>
          {phase.words ? <div style={{ marginTop: 4 }}>What they said, word for word: &ldquo;{phase.words}&rdquo;</div> : null}
          {phase.cancelled ? <div style={{ fontSize: 12, opacity: 0.75, marginTop: 4 }}>A copy is on its way to your email; the call is on the booking&rsquo;s receipt.</div> : null}
        </div>
      )}
      {phase.p === 'refused' && <div>{phase.words}</div>}
      {phase.p === 'not_now' && <div>Nothing was cancelled.</div>}
    </div>
  )
}
