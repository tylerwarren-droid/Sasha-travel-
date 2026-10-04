'use client'

/**
 * Sasha 135 · "Reserve (TEST)" on a hotel card (backend/booking_signer/hotel_test.py): check-in, nights, party → the
 * read-back ("Test booking: no hotel contacted", a TEST price said to be a placeholder) → Yes → one touch on Stripe's TEST
 * page → a TEST- reference in the itinerary and calendar. Never "confirmed": no hotel is contacted, nothing is reserved.
 */
import { useEffect, useState } from 'react'
import { bookingReq, guestRefusal as refusal, SIGN_IN_TO_BOOK } from '@/lib/booking-client'

type Phase = { k: 'idle' } | { k: 'form' } | { k: 'readback'; lines: string[]; sha: string } | { k: 'paying'; url: string; sid: string }
  | { k: 'done'; say: string } | { k: 'error'; say: string }

const inAWeek = () => new Date(Date.now() + 7 * 864e5).toISOString().slice(0, 10)

export function HotelBookTest({ hotel, city, nights: n0, checkin: c0, party: p0 }: { hotel: string; city?: string; nights?: number; checkin?: string; party?: number }) {
  const [p, setP] = useState<Phase>({ k: 'idle' })
  const [checkin, setCheckin] = useState(c0 && /^\d{4}-\d{2}-\d{2}$/.test(c0) ? c0 : inAWeek())   // Sasha 143 · the stay asked for
  const [nights, setNights] = useState(n0 && n0 > 0 ? n0 : 2)
  const [party, setParty] = useState(p0 && p0 > 0 ? p0 : 2)
  const details = () => ({ hotel, city: city || '', checkin, nights, party })
  async function prepare() {
    const r = await bookingReq('/api/booking/travel/hotel/prepare', details())
      .catch((e: Error) => ({ ok: false, status: 0, json: { message: e.message } as Record<string, unknown> }))
    if (r.status === 401) return setP({ k: 'error', say: SIGN_IN_TO_BOOK })
    if (!r.ok) return setP({ k: 'error', say: `No test booking — ${refusal(r.json, r.status)}.` })
    const rb = r.json.read_back as { lines: string[]; sha256: string }
    setP({ k: 'readback', lines: rb.lines, sha: rb.sha256 })
  }
  async function yes(sha: string) {
    const r = await bookingReq('/api/booking/travel/hotel/pay', { ...details(), read_back_sha256: sha, approval: { how: 'button' } })
    if (!r.ok) return setP({ k: 'error', say: `No test booking — ${refusal(r.json, r.status)}.` })
    setP({ k: 'paying', url: String(r.json.url), sid: String(r.json.session_id) })
    window.open(String(r.json.url), '_blank', 'noopener')
  }
  useEffect(() => {
    if (p.k !== 'paying') return
    const t = setInterval(async () => {
      const r = await bookingReq('/api/booking/travel/hotel/status', { ...details(), session_id: p.sid }).catch(() => null)
      if (r?.json?.status === 'booked') setP({ k: 'done', say: String(r.json.say) })
    }, 3000)
    return () => clearInterval(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [p])
  if (p.k === 'idle') return <button className="price" onClick={() => setP({ k: 'form' })}>Reserve (TEST)</button>
  if (p.k === 'form') return (
    <div className="o2" style={{ maxWidth: 420 }}>
      <div>Test booking: no hotel contacted.</div>
      <label>Check-in <input type="date" value={checkin} onChange={e => setCheckin(e.target.value)} /></label>{' '}
      <label>Nights <input type="number" min={1} max={30} value={nights} onChange={e => setNights(Number(e.target.value))} style={{ width: 48 }} /></label>{' '}
      <label>People <input type="number" min={1} max={10} value={party} onChange={e => setParty(Number(e.target.value))} style={{ width: 48 }} /></label>{' '}
      <button className="price" onClick={() => { prepare() }}>Continue</button>
    </div>
  )
  if (p.k === 'readback') return (
    <div className="o2" style={{ maxWidth: 420 }}>
      <ul>{p.lines.map((l, i) => <li key={i}>{l}</li>)}</ul>
      <button className="price" onClick={() => { yes(p.sha) }}>Yes, test-book it</button>{' '}
      <button className="viewlink" onClick={() => setP({ k: 'idle' })}>No</button>
    </div>
  )
  if (p.k === 'paying') return <span className="o2">Pay the TEST price on <a href={p.url} target="_blank" rel="noopener noreferrer">Stripe&rsquo;s test page</a> (Apple Pay or a saved card; nothing is charged, no hotel is contacted)…</span>
  return <span className="o2">{p.say}</span>
}
