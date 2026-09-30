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

type Reservation = {
  id: string; channel: string; venue: string; date: string; time: string; timezone: string | null; party: number
  status: string; status_words: string; booking_reference: string | null; venue_words: string | null
}
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

export default function SashaReservations() {
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
    for (const r of [...state.items].sort((a, b) => (a.date + a.time).localeCompare(b.date + b.time))) {
      byDay.set(r.date, [...(byDay.get(r.date) ?? []), r])
    }
  }
  return (
    <>
      <div className="lw-when">Reservations Sasha made</div>
      <div className="lw-card">
        <div className="lw-cardBody" style={{ paddingTop: 14 }}>
          {state.phase === 'loading' && <div className="lw-note-s">Loading your reservations…</div>}
          {state.phase === 'failed' && <div className="lw-note-s">Your reservations couldn&rsquo;t be loaded just now.</div>}
          {state.phase === 'loaded' && state.items.length === 0 && <div className="lw-note-s">No reservations made through Sasha yet.</div>}
          {state.phase === 'loaded' && [...byDay].map(([day, rows]) => (
            <div key={day} style={{ marginBottom: 12 }}>
              <div style={{ fontWeight: 600, marginBottom: 4 }}>{dayHeader(day)}</div>
              {rows.map((r) => (
                <div key={r.id} style={{ marginBottom: 8 }}>
                  <div>{r.time} ({zoneName(r.timezone)}) · {r.venue} · {r.party} {r.party === 1 ? 'person' : 'people'} · {CHANNEL[r.channel] ?? r.channel}</div>
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
