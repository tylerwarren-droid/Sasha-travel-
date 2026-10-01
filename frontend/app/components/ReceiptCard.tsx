'use client'

/**
 * Sasha 88 · THE BOOKING RECEIPT — one reservation as it can be shown and proved (backend/booking_signer/receipt.py):
 * the place by its name (never the words searched with), what, when, for whom, BOTH references, their words, what they
 * wrote, the two-sided transcript, and the yes it rests on. Every line is the server's; nothing here decides anything.
 * Used in the itinerary (SashaReservations) and under a call's result in the chat (ChatBookingCall).
 */
import { useEffect, useState } from 'react'
import { bookingUrl, bookingHeaders } from '@/lib/booking-api'

export type Receipt = {
  venue: { name: string; source: string }; what: string; count: number | null; unit: string; date: string | null; time: string | null
  timezone: string | null; for_whom: string | null; status_words: string
  references: { venue: string | null; sasha: string | null }; their_words: string | null
  reading: { outcome?: string; why?: string; quote?: string; read_by?: string }
  transcript: { who: 'Sasha' | 'Venue'; text: string; at: string | null }[]
  written_promise: { asked: string | null; their_answer: string | null; note?: string } | null
  recording: { kept: boolean; why: string }
  written: { channel: string; from: string | null; subject: string | null; text: string | null; recording_url: string | null; received_at: string | null }[]
  proof: { read_back: string[]; read_back_sha256: string | null; approved: { how: string | null; said: string | null; at: string | null }
    brief_sha256: string | null; request_sha256: string | null; placed_at: string | null }
}

const UNIT_ONE: Record<string, string> = { people: 'person', sessions: 'session', pieces: 'piece', places: 'place' }
const WRITTEN: Record<string, string> = { sms: 'SMS', whatsapp: 'WhatsApp', voicemail: 'Voicemail', email: 'Email' }
/** "Sat 3 Oct 2026" — the calendar date itself, no timezone arithmetic */
const day = (iso: string) => {
  const d = new Date(`${iso}T12:00:00Z`)
  return `${d.toLocaleDateString('en-GB', { weekday: 'short', timeZone: 'UTC' })} ${d.getUTCDate()} ${d.toLocaleDateString('en-GB', { month: 'short', timeZone: 'UTC' })} ${d.getUTCFullYear()}`
}
const stamp = (iso: string | null) => (iso ? `${day(iso.slice(0, 10))}, ${iso.slice(11, 16)} UTC` : 'time not recorded')
const short = (h: string | null) => (h ? `${h.slice(0, 8)}…${h.slice(-4)}` : '—')

export function ReceiptView({ r }: { r: Receipt }) {
  const small = { fontSize: 12, opacity: 0.75 } as const
  return (
    <div style={{ border: '1px solid rgba(0,0,0,.15)', borderRadius: 10, padding: 12, margin: '6px 0' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
        <strong>{r.venue.name}</strong><span style={small}>Receipt</span>
      </div>
      <div style={small}>Name: {r.venue.source}</div>
      <div>{r.what}{r.count ? ` · ${r.count} ${r.count === 1 ? (UNIT_ONE[r.unit] ?? r.unit) : r.unit}` : ''}
        {r.date ? ` · ${day(r.date)}` : ''}{r.time ? ` at ${r.time}` : ''}{r.for_whom ? ` · under ${r.for_whom}` : ''}</div>
      <div style={{ marginTop: 4 }}>{r.status_words}</div>
      <div style={{ marginTop: 4 }}>
        Their reference: {r.references.venue ?? 'they gave none'} · Sasha&rsquo;s reference: {r.references.sasha ?? 'none (booked before references were issued)'}
      </div>
      {r.their_words ? <div style={{ marginTop: 4 }}>What they said: &ldquo;{r.their_words}&rdquo;</div> : null}
      {r.reading.why ? <div style={small}>{r.reading.why}{r.reading.read_by ? ` — ${r.reading.read_by}` : ''}</div> : null}
      {r.written_promise && (
        // Sasha 90 (a) · asked to confirm in writing: what they said to it, verbatim
        <div style={{ marginTop: 4, fontSize: 13 }}>
          {r.written_promise.asked
            ? <>Asked to confirm in writing — they said: {r.written_promise.their_answer ? <>&ldquo;{r.written_promise.their_answer}&rdquo;</> : 'nothing'}</>
            : r.written_promise.note}
        </div>
      )}
      {r.written.length > 0 && (
        <div style={{ marginTop: 6 }}>
          <div style={{ fontWeight: 600 }}>What they wrote</div>
          {r.written.map((w, i) => (
            <div key={i} style={{ fontSize: 13 }}>{WRITTEN[w.channel] ?? w.channel}, {stamp(w.received_at)}: {w.text ? <>&ldquo;{w.text}&rdquo;</> : w.recording_url ? 'a voicemail (recording at Twilio)' : 'no text'}</div>
          ))}
        </div>
      )}
      <details style={{ marginTop: 6 }}>
        <summary>The call, word for word ({r.transcript.length} lines)</summary>
        {r.transcript.length === 0 ? <div style={small}>No transcript was returned for this call.</div>
          : r.transcript.map((t, i) => <div key={i} style={{ fontSize: 13 }}><strong>{t.who}:</strong> {t.text}</div>)}
        <div style={small}>Recording: {r.recording.why}</div>
      </details>
      <details style={{ marginTop: 4 }}>
        <summary>The yes it rests on</summary>
        <ol style={{ paddingLeft: 18, fontSize: 13 }}>{r.proof.read_back.map((l, i) => <li key={i}>{l}</li>)}</ol>
        <div style={small}>Approved {r.proof.approved.how === 'chat' ? `in the chat (“${r.proof.approved.said ?? ''}”)` : r.proof.approved.how === 'button' ? 'with the button' : (r.proof.approved.how ?? '—')}, {stamp(r.proof.approved.at)}.
          {' '}Read-back {short(r.proof.read_back_sha256)} · call {short(r.proof.brief_sha256)} · request {short(r.proof.request_sha256)}</div>
      </details>
    </div>
  )
}

/** Fetches one receipt and shows it; says plainly when it cannot. */
export default function ReceiptCard({ path }: { path: string }) {
  const [state, setState] = useState<{ r: Receipt } | { why: string } | null>(null)
  useEffect(() => {
    let off = false
    fetch(bookingUrl(path), { headers: bookingHeaders() })
      .then(async (res) => {
        if (off) return
        if (!res.ok) { setState({ why: res.status === 401 ? 'sign in to see it' : `it couldn't be loaded (${res.status})` }); return }
        setState({ r: (await res.json()) as Receipt })
      }).catch((e) => { if (!off) setState({ why: (e as Error).message }) })
    return () => { off = true }
  }, [path])
  if (!state) return <div style={{ fontSize: 13, opacity: 0.7 }}>Loading the receipt…</div>
  if ('why' in state) return <div style={{ fontSize: 13, opacity: 0.7 }}>The receipt isn&rsquo;t shown: {state.why}.</div>
  return <ReceiptView r={state.r} />
}
