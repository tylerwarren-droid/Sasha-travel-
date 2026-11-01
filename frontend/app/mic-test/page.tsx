'use client'
/**
 * Sasha 214 · B3 — THE MIC, TESTED ALONE. The same VoiceButton /next uses, with nothing else on the page: every final
 * transcript it submits lands in window.__mic (and on screen), every state change in window.__micLog. A headless harness
 * plays 50 recorded sentences into it; on an iPhone, tap Start and read the sentences aloud — the page scores itself.
 */
import { useRef, useState } from 'react'
import VoiceButton, { type VoiceCtl } from '@/app/components/VoiceButton'

const SENTENCES = [
  'A week in Portugal for two in November', 'Find me a seafood restaurant in Madrid tonight', 'What is the weather like in Lisbon',
  'Book the second one please', 'Show me something cheaper', 'Can we fly from Barcelona instead', 'Ten days in Japan in spring',
  'I would like a quiet hotel by the sea', 'How much is the whole trip', 'Add a day in Porto', 'We love wine and the coast',
  'A table for four at eight thirty', 'Somewhere warm in February', 'Is breakfast included', 'Change the dates to the twelfth',
  'What time does the flight land', 'A spa on Saturday morning', 'Remove the second hotel', 'Find a direct flight', 'That sounds perfect',
  'Can you send it to my phone', 'Two adults and one child', 'Something with a pool', 'How far is it from the airport',
  'Let us go with the first option', 'Is there a later flight', 'A long weekend in Rome', 'I need a window seat', 'What is the total',
  'Book it', 'Morocco for eight days', 'Markets and the desert', 'Make it business class', 'Any vegetarian restaurants nearby',
  'Leave on Friday come back on Monday', 'Show me the cards again', 'Cancel that', 'What do you recommend', 'A boat trip in the afternoon',
  'We are celebrating an anniversary', 'Keep it under two thousand euros', 'Somewhere in Mexico for food and ruins', 'Yes please',
  'No thank you', 'Can we stay one more night', 'A tattoo studio next Tuesday at five', 'Which one has the best reviews',
  'Pick the cheapest flight', 'Let me think about it', 'Thank you Sasha',
]

const WORDS = (s: string) => s.toLowerCase().replace(/[^a-z0-9 ]/g, ' ').split(/\s+/).filter(Boolean)
// a sentence is heard when one submitted transcript carries at least 80% of its words (smart_format writes "8:30", "2,000")
const heardIn = (s: string, heard: string[]) => heard.some(h => {
  const hw = new Set(WORDS(h)), sw = WORDS(s)
  return sw.filter(w => hw.has(w)).length >= Math.ceil(sw.length * 0.8)
})

export default function MicTest() {
  const [on, setOn] = useState(false)
  const [heard, setHeard] = useState<string[]>([])
  const ctl = useRef<VoiceCtl | null>(null)
  // Sasha 322 · her two phases, switchable here so every mic state can be seen (and screenshotted) without a conversation: speaking
  // closes the gate as /s2's speaker does; thinking mutes it as a turn in flight does
  const [speaking, setSpeaking] = useState(false)
  const [thinking, setThinking] = useState(false)
  const gate = useRef<((v: boolean) => void) | null>(null)   // Sasha 322 · the mic is on the page from load (as on /s2); Start is his tap on it
  const onTranscript = (t: string) => {
    const w = window as unknown as { __mic?: { t: number; text: string }[] }
    ;(w.__mic ??= []).push({ t: Math.round(performance.now()), text: t })
    setHeard(h => [...h, t])
  }
  const score = SENTENCES.filter(s => heardIn(s, heard)).length
  return (
    <main style={{ padding: 16, fontFamily: 'system-ui', maxWidth: 640, margin: '0 auto' }}>
      <h1 style={{ fontSize: 20 }}>Mic test</h1>
      <p>Tap Start, allow the mic, then read each sentence with a short pause between them. Score: <b id="mt-score">{score}</b>/50 · heard {heard.length}</p>
      {!on ? <button id="mt-start" onClick={() => { setOn(true); ctl.current?.tap() }} style={{ fontSize: 18, padding: '12px 24px' }}>Start</button> : null}
      <VoiceButton onTranscript={onTranscript} readyToListen strict ctlRef={ctl} speaking={speaking} thinking={thinking} muted={thinking}
        onSetGate={g => { gate.current = g; g(false) }} />
      <p style={{ display: 'flex', gap: 8 }}>
        <button id="mt-speaking" onClick={() => { const v = !speaking; setSpeaking(v); gate.current?.(v) }}>{speaking ? 'Sasha stops speaking' : 'Sasha speaks'}</button>
        <button id="mt-thinking" onClick={() => setThinking(t => !t)}>{thinking ? 'Sasha stops thinking' : 'Sasha thinks'}</button>
      </p>
      <ol style={{ lineHeight: 1.6 }}>{SENTENCES.map(s => <li key={s} data-s={s} style={{ color: heardIn(s, heard) ? '#0a0' : undefined }}>{s}</li>)}</ol>
      <h2 style={{ fontSize: 16 }}>Heard</h2>
      <ol id="mt-heard">{heard.map((h, i) => <li key={i}>{h}</li>)}</ol>
    </main>
  )
}
