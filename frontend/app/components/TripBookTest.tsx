'use client'

/**
 * Sasha 169 (2) · BOOK THE WHOLE TRIP (backend/booking_signer/trip_book.py): the plan's hotels and its flights, TEST, in ONE
 * read-back → one yes (the button, or a typed/spoken "yes") → ONE tap to pay on the phone (or pay here) → ✅ here, and each
 * booking on its day in the Trip panel. The yes is bound to the read-back's hash on the server; nothing is booked before
 * Stripe records the TEST payment.
 */
import { useEffect, useState } from 'react'
import { bookingReq, guestRefusal as refusal, SIGN_IN_TO_BOOK } from '@/lib/booking-client'
import { setPendingYes } from '@/lib/chat-booking-bus'

/** Sasha 186 · the card's answers look and act like buttons on every panel (they read as plain text in the chat) */
const YES_BTN = { background: '#E8B923', color: '#111', border: 0, borderRadius: 8, padding: '6px 14px', fontWeight: 600, cursor: 'pointer' } as const
const NO_BTN = { background: 'transparent', color: 'inherit', border: '1px solid rgba(255,255,255,.35)', borderRadius: 8, padding: '6px 14px', cursor: 'pointer' } as const

type Phase = { k: 'reading' } | { k: 'readback'; lines: string[]; sha: string } | { k: 'paying'; url: string; sid: string; phone: boolean }
  | { k: 'booked'; say: string } | { k: 'error'; say: string } | { k: 'no' }

export function TripBookTest({ from }: { from: string }) {
  const [p, setP] = useState<Phase>({ k: 'reading' })
  useEffect(() => {
    let off = false
    bookingReq('/api/booking/travel/trip/prepare', { from }, 60000)
      .catch((e: Error) => ({ ok: false, status: 0, json: { message: e.message } as Record<string, unknown> }))
      .then((r) => {
        if (off) return
        if (r.status === 401) return setP({ k: 'error', say: SIGN_IN_TO_BOOK })
        if (!r.ok) return setP({ k: 'error', say: `Not booked — ${refusal(r.json, r.status)}.` })
        const rb = r.json.read_back as { lines: string[]; sha256: string }
        setP({ k: 'readback', lines: rb.lines, sha: rb.sha256 })
      })
    return () => { off = true }
  }, [from])
  async function yes(sha: string, said: string | null = null) {
    const r = await bookingReq('/api/booking/travel/trip/pay', { read_back_sha256: sha, approval: said ? { how: 'chat', said } : { how: 'button' } })
    if (!r.ok) return setP({ k: 'error', say: `Not booked — ${refusal(r.json, r.status)}.` })
    const phone = String(r.json.phone ?? '').startsWith('sent')
    setP({ k: 'paying', url: String(r.json.url), sid: String(r.json.session_id), phone })
    if (!phone) window.open(String(r.json.url), '_blank', 'noopener')
  }
  // a typed or spoken "yes" answers the read-back, as the button does
  useEffect(() => {
    if (p.k !== 'readback') return
    const sha = p.sha
    setPendingYes((said) => { yes(sha, said) })
    return () => setPendingYes(null)
  }, [p])  // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (p.k !== 'paying') return
    const t = setInterval(async () => {
      const r = await bookingReq(`/api/booking/travel/trip/status?session_id=${encodeURIComponent(p.sid)}`).catch(() => null)
      const s = r?.json?.status
      if (s === 'booked') setP({ k: 'booked', say: String(r!.json.say) })
      else if (s === 'failed') setP({ k: 'error', say: String(r!.json.say) })
    }, 3000)
    return () => clearInterval(t)
  }, [p])
  const box = { background: 'rgba(255,255,255,.04)', border: '1px solid rgba(255,255,255,.1)', borderRadius: 10, padding: 10, marginTop: 6, maxWidth: 560 } as const
  if (p.k === 'reading') return <div className="o2" style={box}>Pricing the hotels and flights (TEST)…</div>
  if (p.k === 'readback') return (
    <div className="o2" style={box}>
      <ul style={{ margin: 0, paddingLeft: 18 }}>{p.lines.map((l, i) => <li key={i} style={{ marginBottom: 3 }}>{l}</li>)}</ul>
      <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
        <button className="price" style={YES_BTN} onClick={() => { yes(p.sha) }}>Yes, book it all (TEST)</button>
        <button className="viewlink" style={NO_BTN} onClick={() => setP({ k: 'no' })}>No</button>
      </div>
    </div>
  )
  if (p.k === 'paying') return p.phone
    ? <div className="o2" style={box}>📱 Sent to your phone — tap to pay there (Apple Pay; TEST, nothing is charged). I&rsquo;ll book everything the moment it&rsquo;s paid… · or <a href={p.url} target="_blank" rel="noopener noreferrer">pay here</a></div>
    : <div className="o2" style={box}>Pay the TEST total on <a href={p.url} target="_blank" rel="noopener noreferrer">Stripe&rsquo;s test page</a> (Apple Pay or a saved card; nothing is charged). I&rsquo;ll book everything the moment it&rsquo;s paid…</div>
  if (p.k === 'no') return <div className="o2" style={box}>OK — nothing was booked.</div>
  return <div className="o2" style={{ ...box, whiteSpace: 'pre-line' }}>{p.say}</div>
}
