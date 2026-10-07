'use client'
import { useCallback, useEffect, useRef, useState } from 'react'
import TripPanel from '../components/workspace/TripPanel'
import SashaAvatar from '../components/SashaAvatar'
import VoiceButton from '../components/VoiceButton'
import { OPENING_TEXT } from '@/lib/avatar-context.mjs'

/**
 * Sasha 203/204 · /next — SASHA AS AN AI AGENT WITH TOOLS, with her avatar. One model runs the conversation in her persona
 * and acts only through AgAPI v0 (TEST mode). Voice: the Deepgram mic (with its watchdog) → the agent, exactly like typed
 * text; her reply is spoken SENTENCE BY SENTENCE as it streams (repeat()); a quiver line ("That sounds fun!", "Let me look into
 * that.") fills any silence; talking over her stops her (barge-in). The itinerary panel refreshes as tools return. Every voice
 * turn's time to first sound and to the full answer is posted to the server log. The current Sasha page is untouched.
 */
type Msg = { role: 'user' | 'assistant'; content: string }
const TOOL_WORDS: Record<string, string> = {
  propose_trip: 'Putting your trip together', search_flights: 'Looking at flights', search_stays: 'Looking at places to stay',
  swap_stay: 'Changing a stay', choose_offer: 'Swapping the flight', hold_booking: 'Checking everything before booking',
  book: 'Sending the payment to your phone', get_total: 'Adding it up', get_trip: 'Reading your trip', get_status: 'Checking what’s booked',
  save_travellers: 'Saving the travellers', check_offer: 'Checking the fare', search_venues: 'Looking for places', read_booking_route: 'Reading how they take bookings',
}
const strip = (t: string) => t.replace(/[*_`#>]/g, '').replace(/\s+/g, ' ').trim()

export default function NextPage() {
  const [msgs, setMsgs] = useState<Msg[]>([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [doing, setDoing] = useState<string | null>(null)
  const [panelKey, setPanelKey] = useState(0)
  const [openDays, setOpenDays] = useState<Set<number>>(new Set([1]))
  const [started, setStarted] = useState(false)
  const [voiceReady, setVoiceReady] = useState(false)
  const [speaking, setSpeaking] = useState(false)
  const [listening, setListening] = useState(false)
  const session = useRef(`next-${Math.random().toString(36).slice(2, 10)}`)
  const end = useRef<HTMLDivElement>(null)
  const msgsRef = useRef<Msg[]>([])
  useEffect(() => { msgsRef.current = msgs; end.current?.scrollIntoView({ behavior: 'smooth' }) }, [msgs, doing])

  // ── the avatar's voice: a queue, so sentences follow one another without cutting in ──
  const speakFn = useRef<((t: string) => void) | null>(null)
  const interruptFn = useRef<(() => void) | null>(null)
  const gateRef = useRef<((v: boolean) => void) | null>(null)
  const queue = useRef<string[]>([])
  const talking = useRef(false)
  const turnId = useRef(0)
  const lastQuiver = useRef<string | null>(null)
  const timing = useRef<{ id: number; t0: number; first?: number; firstKind?: string; done?: boolean; engine?: number; tools?: string[] } | null>(null)

  const sendTiming = useCallback(() => {
    const t = timing.current
    if (!t || !t.done || queue.current.length || talking.current) return
    const body = { session: session.current, first_sound_ms: t.first != null ? Math.round(t.first - t.t0) : null,
      full_answer_ms: Math.round(performance.now() - t.t0), first_sound_kind: t.firstKind ?? null, engine_first_text_ms: t.engine ?? null, tools: t.tools ?? [] }
    timing.current = null
    console.log('[NEXT timing]', body)
    fetch('/api/sasha-agent/timing', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) }).catch(() => {})
  }, [])

  const speak = useCallback((text: string, kind: 'quiver' | 'say', id: number) => {
    if (!speakFn.current || id !== turnId.current) return   // no avatar, or a turn she was talked over in
    const t = strip(text)
    if (!t) return
    if (kind === 'say' && lastQuiver.current && t === lastQuiver.current) return   // she already said it as the quiver
    if (kind === 'quiver') {
      if (talking.current) return   // never pile a quiver on top of speech
      lastQuiver.current = t
    }
    const tm = timing.current
    if (tm && tm.id === id && tm.first == null) { tm.first = performance.now(); tm.firstKind = kind }
    if (talking.current) { queue.current.push(t); return }
    talking.current = true
    speakFn.current(t)
  }, [])

  const onFinished = useCallback(() => {   // the avatar finished an utterance: the next sentence, or done
    const next = queue.current.shift()
    if (next && speakFn.current) { speakFn.current(next); return }
    talking.current = false
    sendTiming()
  }, [sendTiming])

  const bargeIn = useCallback(() => {   // the guest talked over her: stop, and drop what was queued for that turn
    queue.current = []
    talking.current = false
    turnId.current += 1
    interruptFn.current?.()
  }, [])

  async function send(text: string, voice = false) {
    const t = text.trim()
    if (!t || busy) return
    if (talking.current) bargeIn()   // a new turn always takes the floor
    const id = ++turnId.current
    lastQuiver.current = null
    if (voice || started) timing.current = { id, t0: performance.now() }
    const history = msgsRef.current
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
          else if (ev.type === 'say') speak(ev.text, 'say', id)
          else if (ev.type === 'quiver') speak(ev.text, 'quiver', id)
          else if (ev.type === 'tool_start') setDoing(TOOL_WORDS[ev.name] ?? 'Working on it')
          else if (ev.type === 'tool') { setDoing(null); if (timing.current?.id === id) (timing.current.tools ??= []).push(ev.name) }
          else if (ev.type === 'trip_changed') setPanelKey((k) => k + 1)
          else if (ev.type === 'replace') {
            reply = ev.text; show(reply)
            if (ev.speak && id === turnId.current) { queue.current = []; interruptFn.current?.(); talking.current = false; speak(ev.text, 'say', id) }
          }
          else if (ev.type === 'done') {
            reply = ev.text || reply; show(reply); setPanelKey((k) => k + 1)
            if (timing.current?.id === id) { timing.current.done = true; timing.current.engine = ev.ms?.first_text ?? undefined; sendTiming() }
          }
          else if (ev.type === 'error') { reply = ev.message; show(reply); speak(ev.message, 'say', id) }
        }
      }
    } catch {
      show(reply || 'I lost the connection for a moment — could you say that again?')
    } finally {
      setBusy(false); setDoing(null)
    }
  }
  const sendRef = useRef(send)
  sendRef.current = send

  return (
    <main style={{ display: 'grid', gridTemplateColumns: 'minmax(340px, 1fr) minmax(360px, 1.1fr)', gap: 16, height: '100vh', padding: 16,
      background: '#0d0f12', color: '#eee', boxSizing: 'border-box' }}>
      <section style={{ display: 'flex', flexDirection: 'column', minHeight: 0, gap: 10 }}>
        <div style={{ fontSize: 13, opacity: 0.6 }}>Sasha · next (an agent with tools · TEST mode — nothing real is booked or charged)</div>
        <div style={{ position: 'relative', height: '38vh', minHeight: 220, borderRadius: 14, overflow: 'hidden', background: '#111' }}>
          {started ? (
            <SashaAvatar tokenUrl="/api/heygen/token?lang=en" hideStatusBadge
              onAvatarReady={(s, i) => { speakFn.current = s; interruptFn.current = i }}
              isListening={listening}
              onGate={(v) => gateRef.current?.(v)}
              onAvatarSpeakingChange={setSpeaking}
              onReadyToListen={() => setVoiceReady(true)}
              onSashaFinished={onFinished} />
          ) : (
            <button onClick={() => { setStarted(true); if (!msgsRef.current.length) setMsgs([{ role: 'assistant', content: OPENING_TEXT }]) }} style={{ position: 'absolute', inset: 0, background: 'transparent', color: '#eee', border: 0,
              fontSize: 18, cursor: 'pointer' }}>▶ Talk to Sasha</button>
          )}
          {started && (
            <div style={{ position: 'absolute', left: 12, bottom: 10, fontSize: 12, padding: '4px 10px', borderRadius: 999, background: 'rgba(0,0,0,.55)' }}>
              {!voiceReady ? 'Connecting…' : speaking ? 'Sasha is speaking…' : 'Listening…'}
            </div>
          )}
        </div>
        <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 10, paddingRight: 6 }}>
          {msgs.length === 0 && <div style={{ opacity: 0.7 }}>Tap “Talk to Sasha”, or type — tell her where you’d like to go.</div>}
          {msgs.map((m, i) => (
            <div key={i} style={{ alignSelf: m.role === 'user' ? 'flex-end' : 'flex-start', maxWidth: '85%', background: m.role === 'user' ? '#2a3442' : '#1b1f25',
              borderRadius: 12, padding: '8px 12px', whiteSpace: 'pre-wrap', lineHeight: 1.45 }}>{m.content || (busy && i === msgs.length - 1 ? '…' : '')}</div>
          ))}
          {doing && <div style={{ fontSize: 12, opacity: 0.6 }}>{doing}…</div>}
          <div ref={end} />
        </div>
        <form onSubmit={(e) => { e.preventDefault(); send(input) }} style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          {started && (
            <VoiceButton autoStart readyToListen={voiceReady} avatarSpeaking={speaking}
              onTranscript={(t) => sendRef.current(t, true)}
              onInterrupt={bargeIn}
              onSetGate={(g) => { gateRef.current = g }}
              onSpeakingChange={setListening} language="en" />
          )}
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
