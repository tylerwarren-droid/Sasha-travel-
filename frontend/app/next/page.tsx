'use client'
import { useEffect, useRef, useState } from 'react'
import TripPanel from '../components/workspace/TripPanel'

/**
 * Sasha 203 · /next — SASHA AS AN AI AGENT WITH TOOLS (web chat first). One model runs the conversation in her persona and
 * acts only through AgAPI v0 (search, propose, swap, choose, hold, book — TEST mode). The itinerary panel on the right is the
 * same view as everywhere (plan_store.view), refreshed whenever a tool changes the trip. The current Sasha is untouched.
 */
type Msg = { role: 'user' | 'assistant'; content: string }
type ToolEv = { name: string; agent?: string; ok: boolean; error?: string }
const TOOL_WORDS: Record<string, string> = {
  propose_trip: 'Putting your trip together', search_flights: 'Looking at flights', search_stays: 'Looking at places to stay',
  swap_stay: 'Changing a stay', choose_offer: 'Swapping the flight', hold_booking: 'Checking everything before booking',
  book: 'Sending the payment to your phone', get_total: 'Adding it up', get_trip: 'Reading your trip', get_status: 'Checking what’s booked',
  save_travellers: 'Saving the travellers', check_offer: 'Checking the fare', search_venues: 'Looking for places', read_booking_route: 'Reading how they take bookings',
}

export default function NextPage() {
  const [msgs, setMsgs] = useState<Msg[]>([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [doing, setDoing] = useState<string | null>(null)
  const [panelKey, setPanelKey] = useState(0)
  const [openDays, setOpenDays] = useState<Set<number>>(new Set([1]))
  const session = useRef(`next-${Math.random().toString(36).slice(2, 10)}`)
  const end = useRef<HTMLDivElement>(null)
  useEffect(() => { end.current?.scrollIntoView({ behavior: 'smooth' }) }, [msgs, doing])

  async function send(text: string) {
    const t = text.trim()
    if (!t || busy) return
    const history = msgs
    setMsgs([...history, { role: 'user', content: t }, { role: 'assistant', content: '' }])
    setInput(''); setBusy(true); setDoing(null)
    let reply = ''
    const show = (s: string) => setMsgs((m) => [...m.slice(0, -1), { role: 'assistant', content: s }])
    try {
      const r = await fetch('/api/sasha-agent', { method: 'POST', headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ message: t, history, session_id: session.current }) })
      if (!r.ok || !r.body) {
        const j = await r.json().catch(() => ({}))
        show(r.status === 401 ? 'Please sign in first — /next is your own session for now.' : `I couldn't reach my server (${j.rule ?? r.status}).`)
        return
      }
      const reader = r.body.getReader(); const dec = new TextDecoder(); let buf = ''
      for (;;) {
        const { value, done } = await reader.read()
        if (done) break
        buf += dec.decode(value, { stream: true })
        let i
        while ((i = buf.indexOf('\n\n')) >= 0) {
          const line = buf.slice(0, i).replace(/^data: /, ''); buf = buf.slice(i + 2)
          let ev: any
          try { ev = JSON.parse(line) } catch { continue }
          if (ev.type === 'text') { reply += ev.delta; show(reply); setDoing(null) }
          else if (ev.type === 'tool') setDoing((ev as ToolEv).ok ? TOOL_WORDS[ev.name] ?? ev.name : null)
          else if (ev.type === 'trip_changed') setPanelKey((k) => k + 1)
          else if (ev.type === 'replace') { reply = ev.text; show(reply) }
          else if (ev.type === 'done') { reply = ev.text || reply; show(reply); setPanelKey((k) => k + 1) }
          else if (ev.type === 'error') { reply = ev.message; show(reply) }
        }
      }
    } catch {
      show(reply || 'I lost the connection for a moment — could you say that again?')
    } finally {
      setBusy(false); setDoing(null)
    }
  }

  return (
    <main style={{ display: 'grid', gridTemplateColumns: 'minmax(320px, 1fr) minmax(360px, 1.1fr)', gap: 16, height: '100vh', padding: 16,
      background: '#0d0f12', color: '#eee', boxSizing: 'border-box' }}>
      <section style={{ display: 'flex', flexDirection: 'column', minHeight: 0 }}>
        <div style={{ fontSize: 13, opacity: 0.6, marginBottom: 8 }}>Sasha · next (an agent with tools · TEST mode — nothing real is booked or charged)</div>
        <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 10, paddingRight: 6 }}>
          {msgs.length === 0 && <div style={{ opacity: 0.7 }}>Say hello to Sasha — tell her where you’d like to go.</div>}
          {msgs.map((m, i) => (
            <div key={i} style={{ alignSelf: m.role === 'user' ? 'flex-end' : 'flex-start', maxWidth: '85%', background: m.role === 'user' ? '#2a3442' : '#1b1f25',
              borderRadius: 12, padding: '8px 12px', whiteSpace: 'pre-wrap', lineHeight: 1.45 }}>{m.content || (busy && i === msgs.length - 1 ? '…' : '')}</div>
          ))}
          {doing && <div style={{ fontSize: 12, opacity: 0.6 }}>{doing}…</div>}
          <div ref={end} />
        </div>
        <form onSubmit={(e) => { e.preventDefault(); send(input) }} style={{ display: 'flex', gap: 8, marginTop: 10 }}>
          <input value={input} onChange={(e) => setInput(e.target.value)} placeholder="Message Sasha" autoFocus
            style={{ flex: 1, padding: '10px 12px', borderRadius: 10, border: '1px solid #333', background: '#14171c', color: '#eee' }} />
          <button type="submit" disabled={busy || !input.trim()} style={{ padding: '10px 16px', borderRadius: 10, background: '#E8B923', color: '#111', border: 0, fontWeight: 600 }}>Send</button>
        </form>
      </section>
      <section style={{ overflowY: 'auto', minHeight: 0 }}>
        <TripPanel key={panelKey} richItinerary={null} openDays={openDays} travellerCount={2}
          toggleDay={(d) => setOpenDays((s) => { const n = new Set(s); n.has(d) ? n.delete(d) : n.add(d); return n })} />
      </section>
    </main>
  )
}
