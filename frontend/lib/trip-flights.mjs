/**
 * Sasha 252 · THE TRIP TAB'S FLIGHTS, FROM THE ONE TRIP RECORD (EU 251: "Ask Sasha for flights to Lisbon — book right here" while the
 * flights were chosen — the tab decided from the plan's arrival city alone). The flights on the trip and their state come from the
 * server's trip_figures lines (basket.trip_figures — the same record as the total, get_status and the chat); never guessed here.
 */
const WORDS = { suggested: 'suggested — not booked yet', chosen: 'chosen — not booked yet', held: 'held — not booked yet',
  awaiting_payment: 'waiting for payment', paid: 'paid — being booked', booked: 'booked ✅', cancelled: 'cancelled' }

/** [{what, day, words}] for the trip's flights, outbound first; [] when the trip has none (then the tab may offer to find them). */
export function tripFlights(tt) {
  const lines = (tt && Array.isArray(tt.lines)) ? tt.lines : []
  return lines.filter(l => l && l.kind === 'flight' && l.state !== 'cancelled')
    .sort((a, b) => String(a.day || '').localeCompare(String(b.day || '')))
    .map(l => ({ what: String(l.what || 'Flight'), day: l.day ? dayWords(l.day) : null, words: WORDS[l.state] || String(l.state || '') }))
}

/** "2026-10-24" → "Sat 24 Oct" (the trip's own calendar day — no time zone shift) */
export function dayWords(iso) {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(iso || ''))
  if (!m) return String(iso || '')
  const d = new Date(Date.UTC(+m[1], +m[2] - 1, +m[3]))
  return d.toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short', timeZone: 'UTC' })
}
