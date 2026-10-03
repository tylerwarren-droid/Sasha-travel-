'use client'

/**
 * CR 10 · one account, one itinerary — the DATED REMINDERS the products keep (relocation: apply-from, certificates, TIE;
 * health: the padrón follow-ups). They are not bookings, so they are not trip items: "You" lists them in their own block
 * (the Sasha tab's rule). Appointments the person booked themselves are trip items and show in their bookings.
 *
 * Repo-only. It reads /api/booking/products/reminders through the founder-session pass-through. FOUR states, each true:
 *   · 200 with items  → the list, by date
 *   · 200, empty      → nothing drawn: no block at all (an empty list is not news here)
 *   · 401             → nothing: not signed in, so this view makes no claim
 *   · anything else   → "Your reminders couldn't be loaded just now." — never silence
 */
import { useEffect, useState } from 'react'
import { bookingUrl, bookingHeaders } from '@/lib/booking-api'

type Reminder = { on: string; text: string; product: string; label: string; sent: boolean }
type State = { phase: 'loading' } | { phase: 'hidden' } | { phase: 'failed' } | { phase: 'loaded'; items: Reminder[] }

/** "Thu 2 Oct 2026" — from the calendar date itself, no timezone arithmetic on a date */
const day = (iso: string) => {
  const d = new Date(`${iso}T12:00:00Z`)
  return `${d.toLocaleDateString('en-GB', { weekday: 'short', timeZone: 'UTC' })} ${d.getUTCDate()} ${d.toLocaleDateString('en-GB', { month: 'short', timeZone: 'UTC' })} ${d.getUTCFullYear()}`
}

export default function ProductReminders() {
  const [state, setState] = useState<State>({ phase: 'loading' })

  useEffect(() => {
    let cancelled = false
    fetch(bookingUrl('/api/booking/products/reminders'), { headers: bookingHeaders() })
      .then(async (r) => {
        if (cancelled) return
        if (r.status === 401) { setState({ phase: 'hidden' }); return }
        if (!r.ok) { setState({ phase: 'failed' }); return }
        const j = (await r.json()) as { reminders?: Reminder[] }
        if (!Array.isArray(j.reminders)) { setState({ phase: 'failed' }); return }
        setState({ phase: 'loaded', items: j.reminders })
      }).catch(() => { if (!cancelled) setState({ phase: 'failed' }) })
    return () => { cancelled = true }
  }, [])

  if (state.phase === 'hidden' || state.phase === 'loading') return null
  if (state.phase === 'loaded' && state.items.length === 0) return null
  return (
    <>
      <div className="lw-when">Reminders</div>
      <div className="lw-card">
        <div className="lw-cardBody" style={{ paddingTop: 14 }}>
          {state.phase === 'failed' && <div className="lw-note-s">Your reminders couldn&rsquo;t be loaded just now.</div>}
          {state.phase === 'loaded' && state.items.map((r, i) => (
            <div key={`${r.on}-${i}`} style={{ marginBottom: 10 }}>
              <div className="lw-note-s"><b>{day(r.on)}</b> · {r.label}{r.sent ? ' · sent on WhatsApp' : ''}</div>
              <div>{r.text}</div>
            </div>
          ))}
          <div className="lw-note-s" style={{ marginTop: 6 }}>Sasha sends each one on WhatsApp on its day (WhatsApp lets her write first only within 24 hours of your last message).</div>
        </div>
      </div>
    </>
  )
}
