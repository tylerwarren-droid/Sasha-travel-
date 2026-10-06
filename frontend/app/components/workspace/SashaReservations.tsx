'use client'

/**
 * S-45 · The reservations Sasha made — by phone, email, a venue's booking page or its form — in the guest's trip view.
 *
 * Repo-only: a CTO drop does not ship this file, and Stage B re-inserts it into YouPanel (CLAUDE.md, the fourth heredoc;
 * scripts/check-outcome-surfaces.mjs fails the build if the insertion is missing).
 *
 * It reads /api/booking/reservations through the founder-session pass-through. FOUR states, each true:
 *   · 200 with items  → the list, grouped by day
 *   · 200, empty      → "No reservations made through Sasha yet." — only because the query really answered empty
 *   · 401             → nothing: not signed in as the founder, so this view makes no claim at all
 *   · anything else   → "Your reservations couldn't be loaded just now." — never the empty sentence
 * Every non-pending status is shown with its own words; none of them says "booked" unless the venue confirmed.
 */
import { useEffect, useState } from 'react'
import { bookingUrl, bookingHeaders } from '@/lib/booking-api'
import ReceiptCard from '../ReceiptCard'

type Reservation = {
  id: string; channel: string; venue: string; date: string | null; time: string | null; timezone: string | null; party: number | null
  status: string; status_words: string; booking_reference: string | null; venue_words: string | null
  // Sasha 88 · a phone booking's receipt: the place by its name, both references, the transcript, the proof
  receipt: string | null
  // S-64 step 14 · what was asked for: the activity, its length, its count in its own unit
  what: string; unit: string; count: number | null; duration_min: number | null
}

const UNIT_ONE: Record<string, string> = { people: 'person', sessions: 'session', pieces: 'piece', places: 'place' }
/** "a 60-minute relaxing massage · 1 person" · "a table · 4 people" · "a tattoo session, 120 min · 1 session" */
const whatLine = (r: Reservation) =>
  `${r.what}${r.duration_min && !r.what.includes(String(r.duration_min)) ? `, ${r.duration_min} min` : ''}`
  + (r.count ? ` · ${r.count} ${r.count === 1 ? (UNIT_ONE[r.unit] ?? r.unit) : r.unit}` : '')
type State = { phase: 'loading' } | { phase: 'hidden' } | { phase: 'failed' } | { phase: 'loaded'; items: Reservation[] }

const CHANNEL: Record<string, string> = { phone: 'by phone', email: 'by email', link: 'by their booking page', form: 'by their booking form' }

/** "Thu 2 Oct 2026" — from the calendar date itself, no timezone arithmetic on a date */
const dayHeader = (iso: string) => {
  const d = new Date(`${iso}T12:00:00Z`)
  const wd = d.toLocaleDateString('en-GB', { weekday: 'short', timeZone: 'UTC' })
  const mo = d.toLocaleDateString('en-GB', { month: 'short', timeZone: 'UTC' })
  return `${wd} ${d.getUTCDate()} ${mo} ${d.getUTCFullYear()}`
}
const zoneName = (tz: string | null) => (tz ? `${tz.split('/').pop()!.replace(/_/g, ' ')} time` : 'their local time')

/** Sasha 175 · the Trip panel's "All bookings" and "In progress" tabs reuse this list: a title, a filter, an empty sentence */
export default function SashaReservations({ title = 'Reservations Sasha made', only, empty = 'No reservations made through Sasha yet.' }:
  { title?: string; only?: (status: string) => boolean; empty?: string } = {}) {
  const [state, setState] = useState<State>({ phase: 'loading' })

  useEffect(() => {
    let cancelled = false
    fetch(bookingUrl('/api/booking/reservations'), { headers: bookingHeaders() })
      .then(async (r) => {
        if (cancelled) return
        if (r.status === 401) { setState({ phase: 'hidden' }); return }
        if (!r.ok) { setState({ phase: 'failed' }); return }
        const j = (await r.json()) as { reservations?: Reservation[] }
        if (!Array.isArray(j.reservations)) { setState({ phase: 'failed' }); return }
        setState({ phase: 'loaded', items: j.reservations })
      }).catch(() => { if (!cancelled) setState({ phase: 'failed' }) })
    return () => { cancelled = true }
  }, [])

  if (state.phase === 'hidden') return null
  const byDay = new Map<string, Reservation[]>()
  if (state.phase === 'loaded') {
    for (const r of [...state.items].filter((x) => !only || only(x.status)).sort((a, b) => `${a.date ?? '9'}${a.time ?? ''}`.localeCompare(`${b.date ?? '9'}${b.time ?? ''}`))) {
      const key = r.date ?? ''   // an ASKING call's reservation has no day yet: grouped last, said plainly
      byDay.set(key, [...(byDay.get(key) ?? []), r])
    }
  }
  return (
    <>
      <div className="lw-when">{title}</div>
      <div className="lw-card">
        <div className="lw-cardBody" style={{ paddingTop: 14 }}>
          {state.phase === 'loading' && <div className="lw-note-s">Loading your reservations…</div>}
          {state.phase === 'failed' && <div className="lw-note-s">Your reservations couldn&rsquo;t be loaded just now.</div>}
          {state.phase === 'loaded' && byDay.size === 0 && <div className="lw-note-s">{empty}</div>}
          {state.phase === 'loaded' && [...byDay].map(([day, rows]) => (
            <div key={day} style={{ marginBottom: 12 }}>
              <div style={{ fontWeight: 600, marginBottom: 4 }}>{day ? dayHeader(day) : 'No day set yet — they were asked when they have space'}</div>
              {rows.map((r) => r.receipt ? <ReceiptCard key={r.id} path={r.receipt} /> : (
                <div key={r.id} style={{ marginBottom: 8 }}>
                  <div>{r.time ? `${r.time} (${zoneName(r.timezone)}) · ` : ''}{r.venue} · {whatLine(r)} · {CHANNEL[r.channel] ?? r.channel}</div>
                  <div className="lw-note-s">{r.status_words}</div>
                  <div className="lw-note-s">{r.booking_reference ? `Their reference: ${r.booking_reference}` : 'They gave no reference'}</div>
                  {r.venue_words ? <div className="lw-note-s">What they said: &ldquo;{r.venue_words}&rdquo;</div> : null}
                </div>
              ))}
            </div>
          ))}
        </div>
      </div>
    </>
  )
}
