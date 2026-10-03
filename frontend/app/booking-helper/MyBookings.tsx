'use client'

/** Sasha 120 · "You": the guest's own bookings — the server's list for the signed-in account, worded as the server words it. */
import { useEffect, useState } from 'react'
import { bookingReq, guestRefusal as refusal } from '@/lib/booking-client'

type R = { id: string; venue: string; date: string | null; time: string | null; party: number | null; status: string; status_words: string
  booking_reference: string | null }

const day = (d: string | null) => (d ? new Date(`${d}T12:00:00`).toLocaleDateString('en-GB', { weekday: 'long', day: 'numeric', month: 'long' }) : 'no day set')

export function MyBookings() {
  const [rows, setRows] = useState<R[] | null>(null)
  const [words, setWords] = useState<string | null>(null)
  useEffect(() => {
    let off = false
    bookingReq('/api/booking/reservations').then((r) => {
      if (off) return
      if (r.ok) setRows(((r.json.reservations as R[]) ?? []).filter((x) => x.status !== 'pending'))
      else setWords(refusal(r.json, r.status))
    }).catch((e) => { if (!off) setWords((e as Error).message) })
    return () => { off = true }
  }, [])
  return (
    <section id="bookings" className="space-y-2 rounded border p-3">
      <h2 className="font-semibold">My bookings</h2>
      {words && <p>{words}</p>}
      {rows && rows.length === 0 && <p className="opacity-75">No bookings yet. Ask Sasha in the chat or on WhatsApp.</p>}
      {rows && rows.length > 0 && (
        <ul className="space-y-1">
          {rows.map((x) => (
            <li key={x.id}>
              <strong>{x.venue}</strong> — {day(x.date)}{x.time ? ` at ${x.time}` : ''}{x.party ? `, ${x.party} ${x.party === 1 ? 'person' : 'people'}` : ''}
              {' · '}{x.status_words}{x.booking_reference ? ` · their reference ${x.booking_reference}` : ''}
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
