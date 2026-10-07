'use client'

/**
 * Sasha 132 · "Book it (TEST)" on a Duffel flight card (backend/booking_signer/travel.py): the read-back (exactly what
 * happens, TEST said twice) → Yes → one touch on Stripe's TEST page → the Duffel TEST order → the itinerary. The yes is
 * bound to the read-back's hash on the server; nothing is booked before Stripe records the test payment.
 */
import { useEffect, useState } from 'react'
import { bookingReq, guestRefusal as refusal, SIGN_IN_TO_BOOK } from '@/lib/booking-client'
import { setPendingYes } from '@/lib/chat-booking-bus'

type Phase = { k: 'idle' } | { k: 'reading' } | { k: 'readback'; lines: string[]; sha: string } | { k: 'paying'; url: string; sid: string; phone?: boolean }
  | { k: 'booked'; say: string } | { k: 'error'; say: string }

export function FlightBookTest({ offerId, autoStart = false }: { offerId: string; autoStart?: boolean }) {
  const [p, setP] = useState<Phase>({ k: 'idle' })
  async function prepare() {
    setP({ k: 'reading' })
    const r = await bookingReq('/api/booking/travel/flight/prepare', { offer_id: offerId })
      .catch((e: Error) => ({ ok: false, status: 0, json: { message: e.message } as Record<string, unknown> }))
    if (r.status === 401) return setP({ k: 'error', say: SIGN_IN_TO_BOOK })
    if (!r.ok) return setP({ k: 'error', say: `Not booked — ${refusal(r.json, r.status)}.` })
    const rb = r.json.read_back as { lines: string[]; sha256: string }
    setP({ k: 'readback', lines: rb.lines, sha: rb.sha256 })
  }
  async function yes(sha: string, said: string | null = null) {
    const r = await bookingReq('/api/booking/travel/flight/pay', { offer_id: offerId, read_back_sha256: sha, approval: said ? { how: 'chat', said } : { how: 'button' } })
    if (!r.ok) return setP({ k: 'error', say: `Not booked — ${refusal(r.json, r.status)}.` })
    // Sasha 161 · desktop books, phone confirms: the tap to pay went to the phone; the laptop keeps "or pay here"
    const phone = String(r.json.phone ?? '').startsWith('sent')
    setP({ k: 'paying', url: String(r.json.url), sid: String(r.json.session_id), phone })
    if (!phone) window.open(String(r.json.url), '_blank', 'noopener')
  }
  // Sasha 182 · picked by words in the chat: the read-back at once; a typed or spoken "yes" answers it, as the button does
  useEffect(() => { if (autoStart) prepare() }, [])  // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (p.k !== 'readback') return
    const sha = p.sha
    setPendingYes((said) => { yes(sha, said) })
    return () => setPendingYes(null)
  }, [p])  // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (p.k !== 'paying') return
    const t = setInterval(async () => {
      const r = await bookingReq(`/api/booking/travel/flight/status?session_id=${encodeURIComponent(p.sid)}&offer_id=${encodeURIComponent(offerId)}`).catch(() => null)
      const s = r?.json?.status
      if (s === 'booked') setP({ k: 'booked', say: String(r!.json.say) })
      else if (s === 'failed') setP({ k: 'error', say: String(r!.json.say) })
    }, 3000)
    return () => clearInterval(t)
  }, [p, offerId])
  if (p.k === 'idle') return <button className="price" onClick={() => { prepare() }}>Book it (TEST)</button>
  if (p.k === 'reading') return <span className="o2">Reading the offer…</span>
  if (p.k === 'readback') return (
    <div className="o2" style={{ maxWidth: 420 }}>
      <ul>{p.lines.map((l, i) => <li key={i}>{l}</li>)}</ul>
      <button className="price" onClick={() => { yes(p.sha) }}>Yes, book it (TEST)</button>{' '}
      <button className="viewlink" onClick={() => setP({ k: 'idle' })}>No</button>
    </div>
  )
  if (p.k === 'paying') return p.phone
    ? <span className="o2">Waiting for you to confirm on your phone… (TEST — nothing is charged) · or <a href={p.url} target="_blank" rel="noopener noreferrer">pay here</a></span>
    : <span className="o2">Pay the TEST fare on <a href={p.url} target="_blank" rel="noopener noreferrer">Stripe&rsquo;s test page</a> (Apple Pay or a saved card; nothing is charged). I&rsquo;ll book it the moment it&rsquo;s paid…</span>
  return <span className="o2">{p.say}</span>
}
