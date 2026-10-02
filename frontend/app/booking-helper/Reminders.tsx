'use client'

/**
 * S-83 · REMINDERS on WhatsApp: on/off, and the starting point "time to leave" is measured from.
 *
 * The starting point is only what the guest types (never inferred, never geocoded and stored); with none, there is no
 * "time to leave" — never a straight-line guess. Reminders need consent v3: a guest linked under v2 is asked once on
 * WhatsApp ("Reply YES REMINDERS").
 */
import { useEffect, useState } from 'react'
import { bookingReq, guestRefusal as refusal } from '@/lib/booking-client'
import { bookingHeaders, bookingUrl } from '@/lib/booking-api'
import { GatedButton } from './GatedButton'

type View = { prefs: { all_off: boolean; off_kinds: string[] }; place: { label: string; address: string } | null }

export function Reminders() {
  const [view, setView] = useState<View | null>(null)
  const [words, setWords] = useState<string | null>(null)
  const [place, setPlace] = useState({ label: '', address: '' })
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    let off = false
    bookingReq('/api/booking/proactive').then((r) => {
      if (off) return
      if (r.ok) setView(r.json as unknown as View)
      else setWords(refusal(r.json, r.status))
    }).catch((e) => { if (!off) setWords((e as Error).message) })
    return () => { off = true }
  }, [])

  async function put(path: string, method: 'PUT' | 'POST' | 'DELETE', body?: unknown) {
    setBusy(true)
    try {
      const r = await fetch(bookingUrl(path), { method, headers: bookingHeaders(), ...(body === undefined ? {} : { body: JSON.stringify(body) }) })
      let j: Record<string, unknown> = {}
      try { j = await r.json() } catch { /* reported by its status */ }
      if (!r.ok) { setWords(`Not saved — ${refusal(j, r.status)}.`); return }
      const g = await bookingReq('/api/booking/proactive')
      if (g.ok) setView(g.json as unknown as View)
      setWords('Saved.')
    } finally { setBusy(false) }
  }

  if (!view) return words ? <p className="text-xs opacity-75">Reminders: {words}</p> : null
  return (
    <div className="space-y-2 border-t pt-2">
      <p><strong>Reminders</strong> — the day before, when it&rsquo;s time to leave, a morning summary; never 22:00–08:00, at most 4 a day.</p>
      {words && <p className="text-xs">{words}</p>}
      <GatedButton label={view.prefs.all_off ? 'Turn reminders on' : 'Turn reminders off'}
        onClick={() => { put('/api/booking/proactive/prefs', 'PUT', { all_off: !view.prefs.all_off, off_kinds: view.prefs.off_kinds }).catch((e) => setWords((e as Error).message)) }}
        needs={[busy && 'the last step to finish']} />
      <p className="text-xs opacity-75">On WhatsApp: STOP REMINDERS turns them off, YES REMINDERS turns them on.</p>
      {view.place ? (
        <p>Time to leave is measured from <strong>{view.place.label}</strong> ({view.place.address}).{' '}
          <button type="button" className="underline" onClick={() => { put('/api/booking/proactive/place', 'DELETE').catch((e) => setWords((e as Error).message)) }}>Remove</button></p>
      ) : (
        <div className="space-y-1">
          <p className="text-xs opacity-75">No starting point saved, so no &ldquo;time to leave&rdquo; message — Sasha never guesses a travel time.</p>
          <input className="w-full rounded border px-2 py-1" placeholder="A name, e.g. my hotel" value={place.label} onChange={(e) => setPlace({ ...place, label: e.target.value })} />
          <input className="w-full rounded border px-2 py-1" placeholder="Its address" value={place.address} onChange={(e) => setPlace({ ...place, address: e.target.value })} />
          <GatedButton label="Save starting point" onClick={() => { put('/api/booking/proactive/place', 'POST', place).catch((e) => setWords((e as Error).message)) }}
            needs={[!place.label.trim() && 'a name', place.address.trim().length < 3 && 'an address', busy && 'the last step to finish']} />
        </div>
      )}
    </div>
  )
}
