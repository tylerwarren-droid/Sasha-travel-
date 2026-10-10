'use client'

/**
 * Sasha 225 · /s2's opening: her face says hello (~5–8 s), then she goes behind the scenes — a small bubble (tap = her face back).
 *
 *  · The avatar is a LiveAvatar LITE session: her face only, lip-synced to the audio /s2 sends — her OWN voice, the same one her
 *    spoken replies use after the hand-off (Deepgram, /api/s2-voice/pcm). One voice from the first word.
 *  · It starts in parallel with the page. Not on screen within 5 s (from its start) → the hello is said in her voice alone (no face, never a spinner).
 *  · A phone that won't play sound before a tap gets "Tap to hear Sasha" — the hello starts on that tap, never silently.
 *  · After the hello the session is ENDED (no live session left running); the bubble shows her face as it last was.
 *  · Tap the bubble: her face back (a new session) — while it's up, her replies are spoken by it; tap again (or 90 s quiet) → bubble.
 */
import { useEffect, useRef, useState } from 'react'

export type Talker = {
  unlock: () => void
  sayNow: (t: string) => Promise<'played' | 'blocked' | 'failed'>
  setRoute: (fn: ((t: string) => Promise<void>) | null) => void
  onSpeaking: (fn: (speaking: boolean) => void) => () => void
}

type Face = { video: HTMLVideoElement; say: (text: string) => Promise<number>; stop: () => Promise<void> }

const GOLD = '#e8b931'
export const helloLine = (name?: string | null) =>
  `Hi${name ? ` ${name}` : ''}, I'm Sasha. I'm going to head behind the scenes and get to work — just talk to me normally. ` +
  'I can book restaurants and trips, sort your subscriptions, send emails for you, and more.'

async function pcm(text: string): Promise<string | null> {
  const r = await fetch('/api/s2-voice/pcm', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ text }) }).catch(() => null)
  const j = r && r.ok ? await r.json().catch(() => null) : null
  return j?.audio || null
}

/** A LITE session on `video`; resolves once her face is on screen. */
async function startFace(video: HTMLVideoElement): Promise<Face> {
  const [tr, sdk] = await Promise.all([fetch('/api/s2-avatar/token', { cache: 'no-store' }), import('@heygen/liveavatar-web-sdk')])
  const { token } = await tr.json()
  if (!token) throw new Error('no token')
  // eslint-disable-next-line @typescript-eslint/no-explicit-any -- the SDK's classes are loosely typed
  const { LiveAvatarSession, SessionEvent } = sdk as any
  const s = new LiveAvatarSession(token, { voiceChat: false, video_settings: { quality: 'medium', encoding: 'H264' } })
  const ready = new Promise<void>((res, rej) => {
    s.on(SessionEvent.SESSION_STREAM_READY, () => { s.attach(video); res() })
    s.on(SessionEvent.SESSION_START_FAILED, () => rej(new Error('start failed')))
  })
  const stop = async () => { try { await s.stop() } catch { /* already stopped */ } }
  try { await s.start(); await ready } catch (e) { await stop(); throw e }
  return {
    video,
    stop,
    say: async (text: string) => {   // → seconds of speech (her voice, lip-synced)
      const a = await pcm(text)
      if (!a) return 0
      s.repeatAudio(a)
      return (a.length * 3) / 4 / 48000
    },
  }
}

function still(keyed: HTMLCanvasElement | null): string | null {   // her face as it last was, on the page's own dark (keyed)
  try {
    if (!keyed || !keyed.width) return null
    const c = document.createElement('canvas'); c.width = 160; c.height = Math.round((160 * keyed.height) / keyed.width)
    const x = c.getContext('2d')
    if (!x) return null
    x.fillStyle = '#1b1b26'; x.fillRect(0, 0, c.width, c.height)
    x.drawImage(keyed, 0, 0, c.width, c.height)
    return c.toDataURL('image/jpeg', 0.85)
  } catch { return null }
}

/** The avatar streams on a green screen: each decoded frame drawn to the canvas with the green knocked out (as /next does). */
function chroma(video: HTMLVideoElement, canvas: HTMLCanvasElement): () => void {
  const ctx = canvas.getContext('2d', { willReadFrequently: true })
  let running = true
  const one = () => {
    try {
      const w = video.videoWidth, h = video.videoHeight
      if (ctx && w && h && video.readyState >= 2) {
        if (canvas.width !== w || canvas.height !== h) { canvas.width = w; canvas.height = h }
        ctx.drawImage(video, 0, 0, w, h)
        const f = ctx.getImageData(0, 0, w, h), d = f.data
        for (let i = 0; i < d.length; i += 4) {
          const r = d[i], g = d[i + 1], b = d[i + 2]
          if (g > 90 && g > r * 1.35 && g > b * 1.35) d[i + 3] = 0
          else if (g > 80 && g > r * 1.1 && g > b * 1.1) d[i + 3] = Math.floor(d[i + 3] * 0.5)
        }
        ctx.putImageData(f, 0, 0)
      }
    } catch { /* a bad frame: keep going */ }
  }
  // eslint-disable-next-line @typescript-eslint/no-explicit-any -- requestVideoFrameCallback isn't in every TS lib yet
  const v = video as any
  if (typeof v.requestVideoFrameCallback === 'function') { const step = () => { if (running) { one(); v.requestVideoFrameCallback(step) } }; v.requestVideoFrameCallback(step) }
  else { const step = () => { if (running) { one(); requestAnimationFrame(step) } }; requestAnimationFrame(step) }
  return () => { running = false }
}

export default function S2Hello({ talker, name, signedIn }: { talker: Talker; name: string | null | undefined; signedIn: boolean | null }) {
  type Phase = 'off' | 'starting' | 'face' | 'voice' | 'tap' | 'bubble' | 'faceAgain'
  const [phase, setPhase] = useState<Phase>('off')
  const [tapFor, setTapFor] = useState<'face' | 'voice'>('voice')
  const [img, setImg] = useState<string | null>(null)
  const [talking, setTalking] = useState(false)
  const video = useRef<HTMLVideoElement | null>(null)
  const canvas = useRef<HTMLCanvasElement | null>(null)
  const unkey = useRef<(() => void) | null>(null)
  const nameRef = useRef<string | null | undefined>(name)
  useEffect(() => { nameRef.current = name }, [name])
  const keyOn = () => { unkey.current?.(); if (video.current && canvas.current) unkey.current = chroma(video.current, canvas.current) }
  const keyOff = () => { unkey.current?.(); unkey.current = null }
  const face = useRef<Face | null>(null)
  const text = useRef('')
  const [line, setLine] = useState('')
  const idle = useRef<ReturnType<typeof setTimeout> | null>(null)
  const early = useRef<{ p: Promise<Face>; t0: number } | null>(null)   // her face starts at mount, before the sign-in check returns

  useEffect(() => {
    if (signedIn === false) { early.current?.p.then(f => f.stop()).catch(() => {}); early.current = null; return }
    if (early.current || !video.current) return
    try { if (sessionStorage.getItem('s2_hello') === '1') return } catch { /* private mode */ }
    early.current = { p: startFace(video.current), t0: performance.now() }
    early.current.p.catch(() => {})
  }, [signedIn])

  useEffect(() => talker.onSpeaking(setTalking), [talker])

  const handoff = async () => {
    const f = face.current
    face.current = null
    if (f) { setImg(still(canvas.current) || img); keyOff(); await f.stop() }   // the session ENDS after the hello
    try { sessionStorage.setItem('s2_hello', '1') } catch { /* private mode */ }
    setPhase('bubble')
  }
  const words = () => { text.current = helloLine(nameRef.current ?? null); setLine(text.current); return text.current }
  const speakFace = async () => {
    words()
    const f = face.current
    if (!f) return handoff()
    const secs = await f.say(text.current)
    setTimeout(handoff, Math.max(2500, secs * 1000 + 900))
  }
  const speakVoice = async () => {
    const r = await talker.sayNow(words())
    if (r === 'blocked') { setTapFor('voice'); setPhase('tap'); return }
    handoff()
  }

  // the opening: once per visit (the session), as soon as the page is signed in and the name is known (or ~0.9 s has passed)
  useEffect(() => {
    if (signedIn !== true || phase !== 'off') return
    let settled = false, timer: ReturnType<typeof setTimeout> | undefined
    const go = setTimeout(() => {   // out of the effect's own pass (no state set while it runs)
    let greeted = false
    try { greeted = sessionStorage.getItem('s2_hello') === '1' } catch { /* private mode */ }
    if (greeted) { setPhase('bubble'); return }
    setPhase('starting')
    const v = video.current as HTMLVideoElement
    const t0 = early.current?.t0 ?? performance.now()
    const starting = early.current?.p ?? startFace(v)
    starting.then(() => console.log(`[s2-hello] face on screen in ${Math.round(performance.now() - t0)} ms`)).catch(() => console.log('[s2-hello] face failed to start'))
    timer = setTimeout(() => {   // not on screen in 5 s (from its start): her voice alone, never a spinner
      if (settled) return
      settled = true
      console.log('[s2-hello] not on screen in 5 s — her voice alone')
      starting.then(f => f.stop()).catch(() => {})
      setPhase('voice')
      speakVoice()
    }, Math.max(0, 5000 - (performance.now() - t0)))
    starting.then(async f => {
      if (settled) return
      settled = true
      clearTimeout(timer)
      face.current = f
      keyOn()
      setPhase('face')
      v.muted = false
      try { await v.play(); speakFace() } catch { v.muted = true; v.play().catch(() => {}); setTapFor('face'); setPhase('tap') }
    }).catch(() => {
      if (settled) return
      settled = true
      clearTimeout(timer)
      setPhase('voice')
      speakVoice()
    })
    }, 0)
    return () => { clearTimeout(go); if (timer) clearTimeout(timer) }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- once, when signed in
  }, [signedIn])

  useEffect(() => () => { keyOff(); face.current?.stop(); talker.setRoute(null) }, [talker])   // leaving the page ends any session

  const tapToHear = () => {
    talker.unlock()
    if (tapFor === 'face' && face.current) { const v = face.current.video; v.muted = false; v.play().catch(() => {}); setPhase('face'); speakFace() }
    else { setPhase('voice'); speakVoice() }
  }

  const collapse = async () => {
    if (idle.current) clearTimeout(idle.current)
    talker.setRoute(null)
    const f = face.current
    face.current = null
    if (f) { setImg(still(canvas.current) || img); keyOff(); await f.stop() }
    setPhase('bubble')
  }
  const faceBack = async () => {
    talker.unlock()
    setPhase('faceAgain')
    try {
      const f = await startFace(video.current as HTMLVideoElement)
      face.current = f
      keyOn()
      f.video.muted = false
      f.video.play().catch(() => {})
      const arm = () => { if (idle.current) clearTimeout(idle.current); idle.current = setTimeout(collapse, 90000) }
      talker.setRoute(async t => { arm(); const secs = await f.say(t); await new Promise(r => setTimeout(r, secs * 1000 + 300)) })
      arm()
    } catch { setPhase('bubble') }
  }

  const big = phase === 'starting' || phase === 'face' || phase === 'faceAgain' || (phase === 'tap' && tapFor === 'face')
  return (
    <>
      <div onClick={phase === 'faceAgain' ? collapse : undefined} style={{
        position: 'fixed', zIndex: 40, transition: 'all .45s ease', overflow: 'hidden', background: 'radial-gradient(120% 90% at 50% 20%, #2a2440 0%, #14141c 70%)',
        ...(big ? { left: '50%', top: 'calc(env(safe-area-inset-top) + 96px)', width: 'min(86vw, 420px)', aspectRatio: '3 / 4', transform: 'translateX(-50%)', borderRadius: 24, boxShadow: '0 20px 60px rgba(0,0,0,.6)', opacity: phase === 'starting' ? 0 : 1 }
          : { right: 16, bottom: 'calc(env(safe-area-inset-bottom) + 92px)', width: 0, height: 0, borderRadius: '50%', opacity: 0 }) }}>
        <video ref={video} playsInline autoPlay muted style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'cover', opacity: 0, pointerEvents: 'none' }} />
        <canvas ref={canvas} style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'cover', objectPosition: 'center 18%', display: 'block' }} />
        {phase === 'tap' && tapFor === 'face' && <button onClick={tapToHear} style={{ position: 'absolute', left: '50%', bottom: 18, transform: 'translateX(-50%)', padding: '12px 20px', borderRadius: 999, border: 0, background: GOLD, color: '#111', fontWeight: 700, fontSize: 16 }}>Tap to hear Sasha</button>}
      </div>
      {phase === 'voice' || (phase === 'tap' && tapFor === 'voice') ? (
        <div style={{ position: 'fixed', zIndex: 40, left: 16, right: 16, top: 'calc(env(safe-area-inset-top) + 110px)', maxWidth: 520, margin: '0 auto', padding: 18, borderRadius: 20, background: '#16161f', border: '1px solid rgba(255,255,255,.12)', color: '#fff', fontSize: 17, lineHeight: 1.45 }}>
          {line}
          {phase === 'tap' && <div><button onClick={tapToHear} style={{ marginTop: 12, padding: '10px 18px', borderRadius: 999, border: 0, background: GOLD, color: '#111', fontWeight: 700 }}>Tap to hear Sasha</button></div>}
        </div>) : null}
      {phase === 'bubble' && (
        <button onClick={faceBack} aria-label="Sasha — tap to see her" style={{
          position: 'fixed', zIndex: 40, right: 16, bottom: 'calc(env(safe-area-inset-bottom) + 92px)', width: 58, height: 58, borderRadius: '50%', padding: 0,
          border: `2px solid ${talking ? GOLD : 'rgba(255,255,255,.35)'}`, boxShadow: talking ? `0 0 0 6px rgba(232,185,49,.25)` : '0 6px 18px rgba(0,0,0,.5)',
          background: img ? `center / cover no-repeat url(${img})` : 'linear-gradient(135deg,#6d4aff,#9b4dff)', color: '#fff', fontWeight: 700, fontSize: 20, transition: 'box-shadow .3s, border-color .3s' }}>
          {img ? '' : 'S'}</button>)}
    </>
  )
}
