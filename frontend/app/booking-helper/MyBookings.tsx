'use client'

/** Sasha 120 · "You": the guest's own bookings — the server's list for the signed-in account, worded as the server words it.
 *  Sasha 323 · DEMO-CLEAN, ONE RULE (backend journeys.booking_view, the same list as S2's trip): upcoming first, soonest first; past,
 *  cancelled and declined behind "Show history"; a test or scratch booking never shown to a real person. Read from /api/booking/journeys
 *  so a booking made through AgAPI is here too (the old /reservations list had only Sasha's own). */
import { useEffect, useState } from 'react'
import { bookingReq, guestRefusal as refusal } from '@/lib/booking-client'

type R = { id: string; venue: string; date: string | null; time: string | null; party?: number | null; status: string; status_words?: string
  booking_reference?: string | null }

const day = (d: string | null) => (d ? new Date(`${d}T12:00:00`).toLocaleDateString('en-GB', { weekday: 'long', day: 'numeric', month: 'long' }) : 'no day set')

function Row({ x }: { x: R }) {
  return (
    <li>
      <strong>{x.venue}</strong> — {day(x.date)}{x.time ? ` at ${x.time}` : ''}{x.party ? `, ${x.party} ${x.party === 1 ? 'person' : 'people'}` : ''}
      {' · '}{x.status_words ?? x.status}{x.booking_reference ? ` · their reference ${x.booking_reference}` : ''}
    </li>
  )
}

export function MyBookings() {
  const [rows, setRows] = useState<R[] | null>(null)
  const [past, setPast] = useState<R[]>([])
  const [showPast, setShowPast] = useState(false)
  const [words, setWords] = useState<string | null>(null)
  useEffect(() => {
    let off = false
    const load = () => bookingReq('/api/booking/journeys').then((r) => {
      if (off) return
      if (r.ok) {
        setRows(((r.json.everything as R[]) ?? []).filter((x) => x.status !== 'pending' && x.status !== 'saved'))
        setPast((r.json.history as R[]) ?? [])
        setWords(null)
      } else setWords(refusal(r.json, r.status))
    }).catch((e) => { if (!off) setWords((e as Error).message) })
    load()
    const t = setInterval(load, 8000)   // Sasha 121 · live: a booking made on the phone appears here within seconds
    return () => { off = true; clearInterval(t) }
  }, [])
  return (
    <section id="bookings" className="space-y-2 rounded border p-3">
      <h2 className="font-semibold">My bookings</h2>
      {words && <p>{words}</p>}
      {rows && rows.length === 0 && <p className="opacity-75">Nothing coming up. Ask Sasha in the chat or on WhatsApp.</p>}
      {rows && rows.length > 0 && <ul className="space-y-1">{rows.map((x) => <Row key={x.id} x={x} />)}</ul>}
      {past.length > 0 && (
        <>
          <button type="button" className="underline opacity-75" data-show-history onClick={() => setShowPast((v) => !v)}>
            {showPast ? 'Hide history' : `Show history (${past.length})`}</button>
          {showPast && <ul className="space-y-1 opacity-75">{past.map((x) => <Row key={x.id} x={x} />)}</ul>}
        </>
      )}
    </section>
  )
}
