'use client'

/**
 * Sasha 225 · /s2's opening: her face says hello (~5–8 s), then she goes behind the scenes — a small bubble (tap = her face back).
 *
 *  · The avatar is a LiveAvatar LITE session: her face only, lip-synced to the audio /s2 sends — her OWN voice, the same one her
 *    spoken replies use after the hand-off (Deepgram, /api/s2-voice/pcm). One voice from the first word.
 *  · It starts in parallel with the page. Not on screen within 3 s → the hello is said in her voice alone (no face, never a spinner).
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
  "I can book restaurants and trips, send emails for you, keep your passport safe, and more."

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

function still(v: HTMLVideoElement | null): string | null {
  try {
    if (!v || !v.videoWidth) return null
    const c = document.createElement('canvas'); c.width = 160; c.height = Math.round((160 * v.videoHeight) / v.videoWidth)
    c.getContext('2d')?.drawImage(v, 0, 0, c.width, c.height)
    return c.toDataURL('image/jpeg', 0.8)
  } catch { return null }
}

export default function S2Hello({ talker, name, ready }: { talker: Talker; name: string | null | undefined; ready: boolean }) {
  type Phase = 'off' | 'starting' | 'face' | 'voice' | 'tap' | 'bubble' | 'faceAgain'
  const [phase, setPhase] = useState<Phase>('off')
  const [tapFor, setTapFor] = useState<'face' | 'voice'>('voice')
  const [img, setImg] = useState<string | null>(null)
  const [talking, setTalking] = useState(false)
  const video = useRef<HTMLVideoElement | null>(null)
  const face = useRef<Face | null>(null)
  const text = useRef('')
  const [line, setLine] = useState('')
  const idle = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => talker.onSpeaking(setTalking), [talker])

  const handoff = async () => {
    const f = face.current
    face.current = null
    if (f) { setImg(still(f.video) || img); await f.stop() }   // the session ENDS after the hello
    try { sessionStorage.setItem('s2_hello', '1') } catch { /* private mode */ }
    setPhase('bubble')
  }
  const speakFace = async () => {
    const f = face.current
    if (!f) return handoff()
    const secs = await f.say(text.current)
    setTimeout(handoff, Math.max(2500, secs * 1000 + 900))
  }
  const speakVoice = async () => {
    const r = await talker.sayNow(text.current)
    if (r === 'blocked') { setTapFor('voice'); setPhase('tap'); return }
    handoff()
  }

  // the opening: once per visit (the session), as soon as the page is signed in and the name is known (or ~0.9 s has passed)
  useEffect(() => {
    if (!ready || phase !== 'off' || name === undefined) return
    let settled = false, timer: ReturnType<typeof setTimeout> | undefined
    const go = setTimeout(() => {   // out of the effect's own pass (no state set while it runs)
    let greeted = false
    try { greeted = sessionStorage.getItem('s2_hello') === '1' } catch { /* private mode */ }
    if (greeted) { setPhase('bubble'); return }
    text.current = helloLine(name)
    setLine(text.current)
    setPhase('starting')
    const v = video.current as HTMLVideoElement
    const starting = startFace(v)
    timer = setTimeout(() => {   // not on screen in 3 s: her voice alone, never a spinner
      if (settled) return
      settled = true
      starting.then(f => f.stop()).catch(() => {})
      setPhase('voice')
      speakVoice()
    }, 3000)
    starting.then(async f => {
      if (settled) return
      settled = true
      clearTimeout(timer)
      face.current = f
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
    // eslint-disable-next-line react-hooks/exhaustive-deps -- once, when ready
  }, [ready, name])

  useEffect(() => () => { face.current?.stop(); talker.setRoute(null) }, [talker])   // leaving the page ends any session

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
    if (f) { setImg(still(f.video) || img); await f.stop() }
    setPhase('bubble')
  }
  const faceBack = async () => {
    talker.unlock()
    setPhase('faceAgain')
    try {
      const f = await startFace(video.current as HTMLVideoElement)
      face.current = f
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
        position: 'fixed', zIndex: 40, transition: 'all .45s ease', overflow: 'hidden', background: '#000',
        ...(big ? { left: '50%', top: 'calc(env(safe-area-inset-top) + 96px)', width: 'min(86vw, 420px)', aspectRatio: '3 / 4', transform: 'translateX(-50%)', borderRadius: 24, boxShadow: '0 20px 60px rgba(0,0,0,.6)', opacity: phase === 'starting' ? 0 : 1 }
          : { right: 16, bottom: 'calc(env(safe-area-inset-bottom) + 92px)', width: 0, height: 0, borderRadius: '50%', opacity: 0 }) }}>
        <video ref={video} playsInline autoPlay muted style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
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
