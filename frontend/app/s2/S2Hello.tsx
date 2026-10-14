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
import { createPortal } from 'react-dom'
import { openingShown, openingEnds } from '@/lib/greeting-rule.mjs'
import { holdPlayAndRecord } from '@/lib/audio-session'   // Sasha 267 · her face shares the page's one audio session

export type Talker = {
  unlock: () => void
  sayNow: (t: string) => Promise<'played' | 'blocked' | 'failed'>
  setRoute: (fn: ((t: string) => Promise<void>) | null) => void
  onSpeaking: (fn: (speaking: boolean) => void) => () => void
}

type Face = { video: HTMLVideoElement; say: (text: string) => Promise<number>; stop: () => Promise<void> }

const GOLD = '#e8b931'
/** Sasha 230 · a LATER visit (she's said hello in this browser before): no re-introduction — her face for a moment, then away. */
export const WELCOME_BACK = 'Hey, welcome back!'
const metBefore = (): boolean => { try { return localStorage.getItem('s2_met') === '1' } catch { return false } }
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
  holdPlayAndRecord('her face')
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
  holdPlayAndRecord('her face connected')   // Sasha 267 · re-asserted after the avatar connects (its media may have set its own)
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

/** Sasha 257 · Tyler (row 860): her face's bubble was an EMPTY dark circle on his phone. The face comes late there (10.6 s
 *  measured), its session was ended 0.9 s later and the bubble took a "still" of a canvas no frame had been drawn to yet (a blank
 *  300×150 canvas is still a canvas) — a dark rectangle. A still is taken only from a frame actually drawn, and the last real
 *  one is kept in this browser (FACE_KEY), so her face is in the bubble on arrival — never an empty circle. */
const FACE_KEY = 's2_face'
/** Sasha 259 · Tyler (row 883): on his phone the bubble was a plain purple "S" — no frame of her face had ever been kept in that
 *  browser (the face comes late there, or the opening is skipped once he's talking). Her face or nothing: a real still of her own
 *  stream ships with the page (public/sasha-face.jpg) and is the bubble's face until a fresher one is kept. */
export const FACE_STILL = '/sasha-face.jpg'
/** Sasha 265 · item 2: the one thing that skips the arrival's motion (row 936) — then the circle at once, her face still shown. */
const reducedMotion = (): boolean => { try { return window.matchMedia('(prefers-reduced-motion: reduce)').matches } catch { return false } }
const keptFace = (): string | null => { try { return localStorage.getItem(FACE_KEY) } catch { return null } }
const drawn = (c: HTMLCanvasElement | null) => !!c && c.dataset.drawn === '1'
async function firstFrame(c: HTMLCanvasElement | null, ms = 6000): Promise<boolean> {   // a late face: wait for its first frame
  const t0 = performance.now()
  while (!drawn(c) && performance.now() - t0 < ms) await new Promise(r => setTimeout(r, 120))
  return drawn(c)
}

function still(keyed: HTMLCanvasElement | null): string | null {   // her face as it last was, on the page's own dark (keyed)
  try {
    if (!keyed || !keyed.width || !drawn(keyed)) return null   // Sasha 257 · never a blank canvas
    const c = document.createElement('canvas'); c.width = 160; c.height = Math.round((160 * keyed.height) / keyed.width)
    const x = c.getContext('2d')
    if (!x) return null
    x.fillStyle = '#1b1b26'; x.fillRect(0, 0, c.width, c.height)
    x.drawImage(keyed, 0, 0, c.width, c.height)
    const url = c.toDataURL('image/jpeg', 0.85)
    try { localStorage.setItem(FACE_KEY, url) } catch { /* private mode / full */ }
    return url
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
        canvas.dataset.drawn = '1'   // Sasha 257 · a real frame is on the canvas
      }
    } catch { /* a bad frame: keep going */ }
  }
  // eslint-disable-next-line @typescript-eslint/no-explicit-any -- requestVideoFrameCallback isn't in every TS lib yet
  const v = video as any
  if (typeof v.requestVideoFrameCallback === 'function') { const step = () => { if (running) { one(); v.requestVideoFrameCallback(step) } }; v.requestVideoFrameCallback(step) }
  else { const step = () => { if (running) { one(); requestAnimationFrame(step) } }; requestAnimationFrame(step) }
  return () => { running = false }
}

/** Sasha 231 · the bubble sits ABOVE the "Voice on · Type instead" row (it covered "Type instead" at 92 px). */
/** Sasha 266 · row 943 (b): with no reply this long after her greeting, her LIVE face is let go (it bills by the minute) — her face
 *  stays full size (its last frame); she still waits for his first reply. Not when she drops: that is his reply, never a timer. */
const FACE_IDLE_S = 120

const BUBBLE_BOTTOM = 'calc(env(safe-area-inset-bottom) + 128px)'

export default function S2Hello({ talker, name, signedIn, backLine, dormant, asleep = false, onWake, started = false }: { talker: Talker; name: string | null | undefined; signedIn: boolean | null; backLine?: string | null; dormant?: boolean
  asleep?: boolean; onWake?: () => void
  started?: boolean }) {   // Sasha 246 item 2 · asleep: her face stops and dims; a tap on it wakes her · Sasha 251 · started: the conversation has begun — the opening ends
  type Phase = 'off' | 'starting' | 'face' | 'faceLate' | 'voice' | 'tap' | 'bubble' | 'faceAgain'
  const [phase, setPhase] = useState<Phase>('off')
  const [tapFor, setTapFor] = useState<'face' | 'voice'>('voice')
  const phaseRef = useRef<Phase>('off')
  useEffect(() => { phaseRef.current = phase }, [phase])
  const tapForRef = useRef<'face' | 'voice'>('voice')
  useEffect(() => { tapForRef.current = tapFor }, [tapFor])
  const [img, setImg] = useState<string | null>(FACE_STILL)   // Sasha 259 · her face, always — never the "S"
  useEffect(() => { const k = keptFace(); if (k) setImg(i => i || k) }, [])   // Sasha 257 · her face from the last visit, on arrival
  const [talking, setTalking] = useState(false)
  const video = useRef<HTMLVideoElement | null>(null)
  const canvas = useRef<HTMLCanvasElement | null>(null)
  const unkey = useRef<(() => void) | null>(null)
  const nameRef = useRef<string | null | undefined>(name)
  useEffect(() => { nameRef.current = name }, [name])
  const backRef = useRef<string | null | undefined>(backLine)   // Sasha 231 · "Welcome back — we were looking at …" (her memory)
  useEffect(() => { backRef.current = backLine }, [backLine])
  const keyOn = () => { unkey.current?.(); if (video.current && canvas.current) unkey.current = chroma(video.current, canvas.current) }
  const keyOff = () => { unkey.current?.(); unkey.current = null }
  const face = useRef<Face | null>(null)
  const text = useRef('')
  const [line, setLine] = useState('')
  const idle = useRef<ReturnType<typeof setTimeout> | null>(null)
  const early = useRef<{ p: Promise<Face>; t0: number } | null>(null)   // her face starts at mount, before the sign-in check returns
  const asleepRef = useRef(asleep)   // Sasha 246 item 2
  const startedRef = useRef(started)   // Sasha 251 · read by the opening's own async steps (a late face, a blocked voice)

  useEffect(() => {
    if (signedIn === false) { early.current?.p.then(f => f.stop()).catch(() => {}); early.current = null; return }
    if (early.current || !video.current || reducedMotion()) return   // Sasha 265 · item 2: every arrival (row 936) — no per-tab skip
    early.current = { p: startFace(video.current), t0: performance.now() }
    early.current.p.catch(() => {})
  }, [signedIn])

  useEffect(() => talker.onSpeaking(setTalking), [talker])

  const idleLive = useRef<ReturnType<typeof setTimeout> | null>(null)
  useEffect(() => () => { if (idleLive.current) clearTimeout(idleLive.current) }, [])
  const handoff = async () => {
    if (idleLive.current) clearTimeout(idleLive.current)
    const f = face.current
    face.current = null
    if (f) { setImg(still(canvas.current) || img); keyOff(); await f.stop() }   // the session ENDS after the hello
    try { sessionStorage.setItem('s2_hello', '1'); localStorage.setItem('s2_met', '1') } catch { /* private mode */ }
    setPhase('bubble')
  }
  const back = useRef<boolean | null>(null)   // Sasha 230 · decided once per visit, before the hello is said
  const words = () => {
    if (back.current === null) back.current = metBefore() || !!backRef.current
    text.current = backRef.current || (back.current ? WELCOME_BACK : helloLine(nameRef.current ?? null))
    setLine(text.current)
    return text.current
  }
  const speakFace = async () => {
    if (asleepRef.current || startedRef.current) return handoff()   // Sasha 246 · asleep: no hello — straight to the (dimmed) bubble · Sasha 251: or already talking
    words()
    const f = face.current
    if (!f) return handoff()
    const secs = await f.say(text.current)
    // Sasha 266 · row 943 (b): she STAYS full size through the opening exchange — her greeting AND his first reply (typed or spoken);
    // his first turn of this visit (`started`) is what sends her to the circle, never a timer. Her live face is let go only to stop its
    // billing after FACE_IDLE_S with no reply — her face (its last frame) stays, full size.
    void secs
    if (idleLive.current) clearTimeout(idleLive.current)
    idleLive.current = setTimeout(() => {
      const g = face.current
      if (!g || phaseRef.current !== 'face') return
      face.current = null
      setImg(still(canvas.current) || img)
      void g.stop()
    }, FACE_IDLE_S * 1000)
  }
  const speakVoice = async () => {
    if (asleepRef.current || startedRef.current) return handoff()   // Sasha 246 · Sasha 251: they already started — no hello over them
    const r = await talker.sayNow(words())
    if (r === 'blocked' && startedRef.current) return handoff()   // Sasha 251 · they started talking meanwhile: no tap card over the chat
    if (r === 'blocked') { setTapFor(face.current ? 'face' : 'voice'); setPhase('tap'); return }   // Sasha 232 · her face, if it came, with the tap
    // Sasha 266 · row 943 (b): said — and she stays, full size (her face with her line), until his first reply
  }

  const lateFace = (f: Face, v: HTMLVideoElement) => {
    const now = phaseRef.current
    console.log(`[s2-hello] face on screen late (${now})`)
    face.current = f
    keyOn()
    v.muted = true
    v.play().catch(() => {})
    if (now === 'voice') setPhase('faceLate')
    else if (now === 'tap' && tapForRef.current === 'voice') setTapFor('face')
    else if (now === 'bubble' || now === 'off') void firstFrame(canvas.current).then(() => { face.current = null; setImg(i => still(canvas.current) || i); keyOff(); f.stop() })   // Sasha 257 · its first frame, then the still
  }

  // the opening: once per visit (the session), as soon as the page is signed in and the name is known (or ~0.9 s has passed)
  useEffect(() => {
    if (signedIn !== true || phase !== 'off') return
    let settled = false, timer: ReturnType<typeof setTimeout> | undefined
    const go = setTimeout(() => {   // out of the effect's own pass (no state set while it runs)
    // Sasha 265 · item 2 (row 936, Tyler: "when he logs back in he never sees her"): a return skipped this — sessionStorage
    // 's2_hello' sent every later arrival straight to the bubble. ONE arrival sequence now, every arrival: her face full size, the
    // hello (a return: "welcome back"), then the circle. Only reduced motion skips the motion — the circle at once, her face in it.
    if (reducedMotion() || startedRef.current) { setPhase('bubble'); return }   // Sasha 251 · already talking (this visit): no opening over it
    setPhase('starting')
    const v = video.current as HTMLVideoElement
    const t0 = early.current?.t0 ?? performance.now()
    const starting = early.current?.p ?? startFace(v)
    starting.then(() => console.log(`[s2-hello] face on screen in ${Math.round(performance.now() - t0)} ms`)).catch(() => console.log('[s2-hello] face failed to start'))
    timer = setTimeout(() => {   // not on screen in 5 s (from its start): her voice alone, never a spinner
      if (settled) return
      settled = true
      console.log('[s2-hello] not on screen in 5 s — her voice alone')
      // Sasha 232 · her face, when it comes LATE, is SHOWN — never stopped (iPhone: the face starts in 4.7–11.6 s, measured on
      // WebKit; at > 5 s it was stopped, so on the phone her face never appeared). Still speaking → her face, big; waiting for a
      // tap → her face with "Tap to hear Sasha" (the tap then speaks through it); already done → her face becomes the bubble.
      starting.then(f => lateFace(f, v)).catch(() => {})
      setPhase('voice')
      speakVoice()
    }, Math.max(0, 5000 - (performance.now() - t0)))
    starting.then(async f => {
      if (settled) return
      settled = true
      clearTimeout(timer)
      if (asleepRef.current || startedRef.current) { face.current = f; handoff(); return }   // Sasha 246 · fell asleep before her face came: it never speaks · Sasha 251 · or they started talking
      face.current = f
      keyOn()
      setPhase('face')
      v.muted = false
      try { await v.play(); talker.unlock(); speakFace() } catch { v.muted = true; v.play().catch(() => {}); setTapFor('face'); setPhase('tap') }   // Sasha 230 · played → her voice stays on
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

  // Sasha 246 item 2 · fall asleep: her face, if it is up (the hello or "her face back"), stops NOW — mid-word — and becomes the
  // dimmed bubble; no hello is said later in this visit. Waking is the parent's (the bubble's tap → onWake).
  useEffect(() => {
    asleepRef.current = asleep
    if (!asleep) return
    try { sessionStorage.setItem('s2_hello', '1') } catch { /* private mode */ }
    const now = phaseRef.current
    if (now === 'off' || now === 'bubble') return
    if (now === 'starting') return   // the opening's own handlers see asleepRef and hand off without a word
    const t = setTimeout(() => { void collapse() }, 0)   // out of the effect's own pass
    return () => clearTimeout(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps -- on the change only
  }, [asleep])

  // Sasha 251 · THE GREETING (lib/greeting-rule.mjs): the opening shows on arrival and ends the moment the conversation starts —
  // her face (if up) stops, the card with "Tap to hear Sasha" goes, she becomes the bubble. Nothing of it is drawn after that.
  useEffect(() => {
    startedRef.current = started
    if (!openingEnds(phaseRef.current, started)) return
    try { sessionStorage.setItem('s2_hello', '1') } catch { /* private mode */ }
    if (phaseRef.current === 'starting') return   // the opening's own handlers see startedRef and hand off without a word
    const t = setTimeout(() => { void handoff() }, 0)   // out of the effect's own pass
    return () => clearTimeout(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps -- on the change only
  }, [started])

  // Sasha 265 · item 2 (her face "sometimes shows, sometimes not"): the circle was drawn into #s2-face-slot looked up DURING render —
  // a slot mounted after that render (the sign-in check, a tab switch back to Sasha, her rest) was never looked up again, so the
  // circle stayed undrawn until some unrelated re-render. The slot is watched; the circle is drawn the moment it exists.
  const [slot, setSlot] = useState<HTMLElement | null>(null)
  useEffect(() => {
    const look = () => setSlot(s => { const now = document.getElementById('s2-face-slot'); return now === s ? s : now })
    look()
    const mo = new MutationObserver(look)
    mo.observe(document.body, { childList: true, subtree: true })
    return () => mo.disconnect()
  }, [])
  const shown = openingShown(phase, tapFor, started)   // Sasha 251 · the one place that says what the opening draws
  // Sasha 265 · item 2: her face is FULL SIZE for the whole opening — a real still of her (FACE_STILL / the last kept frame) from
  // the first instant, the live face over it once drawn; her voice alone (no live face) shows her still with the line, not a text card
  const big = shown === 'face' || shown === 'card'
  const [live, setLive] = useState(false)   // the live face has drawn a frame: her still steps back (the keyed frame is see-through)
  useEffect(() => { if (!big) return; const t = setInterval(() => setLive(drawn(canvas.current)), 150); return () => clearInterval(t) }, [big])
  return (
    <>
      <div data-sasha-face={big ? 'full' : undefined} onClick={phase === 'faceAgain' ? collapse : undefined} style={{
        position: 'fixed', zIndex: 40, transition: 'all .45s ease', overflow: 'hidden', background: 'radial-gradient(120% 90% at 50% 20%, #2a2440 0%, #14141c 70%)',
        ...(big ? { left: '50%', top: 'calc(env(safe-area-inset-top) + 96px)', width: 'min(86vw, 420px)', aspectRatio: '3 / 4', transform: 'translateX(-50%)', borderRadius: 24, boxShadow: '0 20px 60px rgba(0,0,0,.6)', opacity: 1 }
          : { right: 16, bottom: BUBBLE_BOTTOM, width: 0, height: 0, borderRadius: '50%', opacity: 0 }) }}>
        {big && !live && <div aria-hidden data-sasha-still style={{ position: 'absolute', inset: 0, background: `center 18% / cover no-repeat url(${img || FACE_STILL})` }} />}
        <video ref={video} playsInline autoPlay muted style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'cover', opacity: 0, pointerEvents: 'none' }} />
        <canvas ref={canvas} style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'cover', objectPosition: 'center 18%', display: 'block' }} />
        {shown === 'card' ? (   /* her voice alone: her line under her face, in the same frame (Sasha 265 · item 2) */
          <div style={{ position: 'absolute', left: 0, right: 0, bottom: 0, padding: '14px 16px 16px', background: 'linear-gradient(transparent, rgba(10,10,16,.92) 30%)', color: '#fff', fontSize: 16, lineHeight: 1.45 }}>
            {line}
            {phase === 'tap' && <div><button onClick={tapToHear} style={{ marginTop: 10, padding: '10px 18px', borderRadius: 999, border: 0, background: GOLD, color: '#111', fontWeight: 700 }}>Tap to hear Sasha</button></div>}
          </div>) : big && phase === 'tap' && <button onClick={tapToHear} style={{ position: 'absolute', left: '50%', bottom: 18, transform: 'translateX(-50%)', padding: '12px 20px', borderRadius: 999, border: 0, background: GOLD, color: '#111', fontWeight: 700, fontSize: 16 }}>Tap to hear Sasha</button>}
      </div>
      {phase === 'bubble' && (() => {
        // Sasha 259 · Tyler (row 884): the bubble sat over the send button. It lives IN the shell's voice row now (#s2-face-slot),
        // an ordinary inline control — never floating on content or another control. No slot (another tab): not drawn.
        if (!slot) return null
        return createPortal(
          <button data-sasha-face="circle" onClick={asleep ? () => onWake?.() : faceBack} aria-label={asleep ? 'Sasha is asleep — tap her face to wake her' : 'Sasha — tap to see her'} style={{
            width: 40, height: 40, borderRadius: '50%', padding: 0, opacity: asleep ? 0.3 : dormant ? 0.45 : 1, flex: 'none',
            filter: asleep ? 'grayscale(.85) brightness(.7)' : 'none',
            border: `2px solid ${talking ? GOLD : 'rgba(255,255,255,.35)'}`, boxShadow: talking ? `0 0 0 4px rgba(232,185,49,.25)` : 'none',
            background: `center / cover no-repeat url(${img || FACE_STILL})`, transition: 'box-shadow .3s, border-color .3s, opacity 1.2s, filter 1.2s' }} />, slot)
      })()}
    </>
  )
}
