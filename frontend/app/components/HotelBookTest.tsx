'use client'

/**
 * Sasha 135 · "Reserve (TEST)" on a hotel card (backend/booking_signer/hotel_test.py): check-in, nights, party → the
 * read-back ("Test booking: no hotel contacted", a TEST price said to be a placeholder) → Yes → one touch on Stripe's TEST
 * page → a TEST- reference in the itinerary and calendar. Never "confirmed": no hotel is contacted, nothing is reserved.
 */
import { useEffect, useState } from 'react'
import { bookingReq, guestRefusal as refusal, SIGN_IN_TO_BOOK } from '@/lib/booking-client'

type Phase = { k: 'idle' } | { k: 'form' } | { k: 'readback'; lines: string[]; sha: string } | { k: 'paying'; url: string; sid: string; phone?: boolean }
  | { k: 'done'; say: string; sid?: string } | { k: 'error'; say: string }
  // Sasha 155 · the hotel's own page, live (our test hotel, a fictional guest): the guest ticks the box and presses
  | { k: 'live'; done: string; view: string; hid: string; t: string; say: string } | { k: 'booked'; done: string; say: string }

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
    // Sasha 161 · desktop books, phone confirms: the tap to pay went to the phone; the laptop keeps "or pay here"
    const phone = String(r.json.phone ?? '').startsWith('sent')
    setP({ k: 'paying', url: String(r.json.url), sid: String(r.json.session_id), phone })
    if (!phone) window.open(String(r.json.url), '_blank', 'noopener')
  }
  useEffect(() => {
    if (p.k !== 'paying') return
    const t = setInterval(async () => {
      const r = await bookingReq('/api/booking/travel/hotel/status', { ...details(), session_id: p.sid }).catch(() => null)
      if (r?.json?.status === 'booked') setP({ k: 'done', say: String(r.json.say), sid: p.sid })
    }, 3000)
    return () => clearInterval(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [p])
  useEffect(() => {
    if (p.k !== 'live') return
    const t = setInterval(async () => {
      const r = await bookingReq(`/api/booking/handover/${p.hid}/status?t=${encodeURIComponent(p.t)}`).catch(() => null)
      const st = String(r?.json?.state ?? '')
      if (st === 'booked') setP({ k: 'booked', done: p.done, say: `✅ Booked on the hotel's page${r?.json?.reference ? ` — their reference ${String(r.json.reference)}` : ''}. (Kanoe Test Hotel: our own test page, a fictional guest.)` })
      else if (st === 'answered') setP({ k: 'booked', done: p.done, say: `The hotel's page answered${r?.json?.say ? `: ${String(r.json.say)}` : ''} — not read as a confirmation.` })
    }, 2500)
    return () => clearInterval(t)
  }, [p])
  async function finishLive(done: string, sid: string) {
    const r = await bookingReq('/api/booking/travel/hotel/handover', { ...details(), session_id: sid }, 60000)
    if (!r.ok) return setP({ k: 'booked', done, say: `The hotel's page couldn't be opened live — ${refusal(r.json, r.status)}.` })
    const view = String(r.json.view_url)
    setP({ k: 'live', done, view, hid: String(r.json.handover_id), t: new URL(view).searchParams.get('t') ?? '', say: String(r.json.say) })
  }
  if (p.k === 'idle') return <button className="price" onClick={() => setP({ k: 'form' })}>Reserve</button>
  if (p.k === 'form') return (
    <div className="o2" style={{ maxWidth: 420, flexBasis: '100%' }}>
      <div>Test booking: no hotel contacted.</div>
      <label>Check-in <input type="date" value={checkin} onChange={e => setCheckin(e.target.value)} /></label>{' '}
      <label>Nights <input type="number" min={1} max={30} value={nights} onChange={e => setNights(Number(e.target.value))} style={{ width: 48 }} /></label>{' '}
      <label>People <input type="number" min={1} max={10} value={party} onChange={e => setParty(Number(e.target.value))} style={{ width: 48 }} /></label>{' '}
      <button className="price" onClick={() => { prepare() }}>Continue</button>
    </div>
  )
  if (p.k === 'readback') return (
    <div className="o2" style={{ maxWidth: 420, flexBasis: '100%' }}>
      <ul>{p.lines.map((l, i) => <li key={i}>{l}</li>)}</ul>
      <button className="price" onClick={() => { yes(p.sha) }}>Yes, test-book it</button>{' '}
      <button className="viewlink" onClick={() => setP({ k: 'idle' })}>No</button>
    </div>
  )
  // Sasha 161 · past the button, the step takes its own full line in the card (it never squeezes the hotel's details)
  if (p.k === 'paying') return p.phone
    ? <span className="o2" style={{ flexBasis: '100%' }}>Waiting for you to confirm on your phone… (nothing is charged) · or <a href={p.url} target="_blank" rel="noopener noreferrer">pay here</a></span>
    : <span className="o2">Pay the price on <a href={p.url} target="_blank" rel="noopener noreferrer">Stripe&rsquo;s test page</a> (Apple Pay or a saved card; nothing is charged, no hotel is contacted)…</span>
  if (p.k === 'done') return (
    <span className="o2" style={{ flexBasis: '100%' }}>✅ {p.say}{p.sid ? <>{' '}<button className="price" onClick={() => { finishLive(p.say, p.sid!) }}>Finish on the hotel&rsquo;s page (live) →</button></> : null}</span>
  )
  if (p.k === 'live') return (
    <div className="o2" style={{ maxWidth: 420 }}>
      <div>{p.done}</div>
      <div style={{ margin: '6px 0' }}>{p.say}</div>
      <iframe src={p.view} title="The hotel's page, live" allow="clipboard-write" style={{ width: '100%', height: 620, border: '1px solid #ccc', borderRadius: 8 }} />
      <a className="viewlink" href={p.view} target="_blank" rel="noopener noreferrer">Open full screen ↗</a>
    </div>
  )
  if (p.k === 'booked') return <span className="o2">{p.done} {p.say}</span>
  return <span className="o2">{p.say}</span>
}
