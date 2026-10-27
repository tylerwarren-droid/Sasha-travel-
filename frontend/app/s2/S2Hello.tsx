'use client'

/**
 * Sasha 225 · /s2's opening: her face says hello (~5–8 s), then she goes behind the scenes — a small bubble (tap = her face back).
 * Sasha 271 · B/C/D (rows 1008/1009): her arrival is half-body, "Hey there" (a return: "Hey <name>") and at once voice.CAMERA_OFF — then
 * the corner circle, within seconds (no longer "full size until his first request", Sasha 268). Where she is, her ring, her paused look
 * and what a tap does are ONE rule's (lib/presence-rule.mjs). She is ONE element that moves between full size and the corner — drawn
 * always once she's arrived: never into a slot that may not exist (another tab), never under the page's rest fade, and after her live
 * face is let go (or its session ends by itself) her still is shown, never an empty frame.
 *
 *  · The avatar is a LiveAvatar LITE session: her face only, lip-synced to the audio /s2 sends — her OWN voice, the same one her
 *    spoken replies use after the hand-off (Deepgram, /api/s2-voice/pcm). One voice from the first word.
 *  · It starts in parallel with the page. Not on screen within 5 s (from its start) → the hello is said in her voice alone (no face, never a spinner).
 *  · A phone that won't play sound before a tap gets "Tap to hear Sasha" — the hello starts on that tap, never silently.
 *  · After the hello the session is ENDED (no live session left running); the bubble shows her face as it last was.
 *  · Tap the bubble: her face back (a new session) — while it's up, her replies are spoken by it; tap again (or 90 s quiet) → bubble.
 * Sasha 295 · THE OPENING (lib/opening-rule.mjs, its one place): on arrival her still waits with ONE action — "Tap to talk to Sasha",
 * "or type", the starters — and says nothing until that tap; the tap starts the mic and her hello (its audio already fetched). The
 * 5 s "not on screen → her voice alone" race of Sasha 232 is gone with it: before the tap nothing is said, so nothing waits on her face.
 * Sasha 296 · COMING BACK, AND "STILL HERE" (the same rule): a return (returned) is her still full size with "Tap to continue" — the
 * same panel — and his tap hears her pick up where they were; every move into the corner is settle(): the camera words once a session,
 * then a pause, "Still here.", a pause.
 */
import { useEffect, useRef, useState, useSyncExternalStore } from 'react'
import { openingEnds, OPENING } from '@/lib/greeting-rule.mjs'
import { presence, ring, HOLD_MS, inView, WORK_PULSE_CSS, WORK_PULSE_S, speakVia, withCamera } from '@/lib/presence-rule.mjs'
import { openingShown } from '@/lib/greeting-rule.mjs'
import { arrivalLine, newsLine, cameraOffLine, stillHereLine } from '@/lib/first-line'
import { holdPlayAndRecord } from '@/lib/audio-session'   // Sasha 267 · her face shares the page's one audio session
import { READY, BACK, OR_TYPE, STARTERS, PAUSE_MS, CAMERA_SAID, opening, settle as settleOf } from '@/lib/opening-rule.mjs'   // Sasha 295 · THE OPENING, its one place · 296: + the return, the corner

export type Talker = {
  unlock: () => void
  sayNow: (t: string) => Promise<'played' | 'blocked' | 'failed'>
  setRoute: (fn: ((t: string) => Promise<void>) | null) => void
  onSpeaking: (fn: (speaking: boolean) => void) => () => void
  heard?: () => void   // Sasha 281 · her face started a line (the page's audible measure)
  prefetch?: (t: string) => void   // Sasha 295 · her hello's audio, fetched before his tap (said within ~1 s of it)
  speaking?: (b: boolean) => void   // Sasha 295 · her face is saying a line: the page's one "speaking" (the mic's gate, its cue)
}

/** Sasha 273 · item 1: `say` resolves when her face has FINISHED saying it — LiveAvatar's own AVATAR_SPEAK_ENDED (or the session ending),
 *  never a duration guessed from the audio's size (that guess ended her arrival before the avatar, which starts late, had finished).
 *  Sasha 281 · THE ONE PLACE A LINE REACHES HER LIPS (repeatAudio). It says whether the line went to them (false: no audio, the
 *  session gone, or repeatAudio refused) — never a silent "said" — and lines are said one after another, never cut by the next. */
type Face = { video: HTMLVideoElement; say: (text: string) => Promise<boolean>; stop: () => Promise<void> }

const GOLD = '#e8b931'
/** Sasha 230 · a LATER visit (she's said hello in this browser before) · Sasha 271: then she says "Hey <name>" (voice.HELLO_BACK). */
const metBefore = (): boolean => { try { return localStorage.getItem('s2_met') === '1' } catch { return false } }

/** Sasha 295 · her hello's lip-sync audio, fetched while the opening waits for his tap — taken once by Face.say. */
const pcmEarly = new Map<string, Promise<string | null>>()
const prefetchPcm = (text: string) => { if (text && !pcmEarly.has(text)) pcmEarly.set(text, pcm(text)) }
async function pcm(text: string): Promise<string | null> {
  const r = await fetch('/api/s2-voice/pcm', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ text }) }).catch(() => null)
  const j = r && r.ok ? await r.json().catch(() => null) : null
  return j?.audio || null
}

/** A LITE session on `video`; resolves once her face is on screen. Sasha 271 · C: `onEnd` — the session ended by itself (the avatar
 *  service disconnected it): she is let go exactly as when her idle time runs out, her still shown. */
async function startFace(video: HTMLVideoElement, onEnd?: () => void): Promise<Face> {
  holdPlayAndRecord('her face')
  const [tr, sdk] = await Promise.all([fetch('/api/s2-avatar/token', { cache: 'no-store' }), import('@heygen/liveavatar-web-sdk')])
  const { token } = await tr.json()
  if (!token) throw new Error('no token')
  // eslint-disable-next-line @typescript-eslint/no-explicit-any -- the SDK's classes are loosely typed
  const { LiveAvatarSession, SessionEvent, AgentEventsEnum } = sdk as any
  const s = new LiveAvatarSession(token, { voiceChat: false, video_settings: { quality: 'medium', encoding: 'H264' } })
  const ready = new Promise<void>((res, rej) => {
    s.on(SessionEvent.SESSION_STREAM_READY, () => { s.attach(video); res() })
    s.on(SessionEvent.SESSION_START_FAILED, () => rej(new Error('start failed')))
  })
  let speaking: (() => void) | null = null   // Sasha 273 · the line being said: settled by her own speech-ended event
  let gone = false   // Sasha 281 · the session ended (stopped, or by itself): no line reaches her lips any more
  let chain: Promise<unknown> = Promise.resolve()   // Sasha 281 · one line at a time
  const finished = (why: string) => { const f = speaking; speaking = null; if (f) { console.log(`[s2-hello] her face finished speaking (${why})`); f() } }
  if (AgentEventsEnum?.AVATAR_SPEAK_ENDED) s.on(AgentEventsEnum.AVATAR_SPEAK_ENDED, () => finished('speech ended'))
  if (SessionEvent.SESSION_DISCONNECTED) s.on(SessionEvent.SESSION_DISCONNECTED, () => { console.log('[s2-hello] her live face ended'); gone = true; finished('session ended'); onEnd?.() })
  const stop = async () => { gone = true; finished('stopped'); try { await s.stop() } catch { /* already stopped */ } }
  try { await s.start(); await ready } catch (e) { await stop(); throw e }
  holdPlayAndRecord('her face connected')   // Sasha 267 · re-asserted after the avatar connects (its media may have set its own)
  return {
    video,
    stop,
    say: (text: string) => {   // her voice, lip-synced — resolves when she has said it (her speech-ended event): true, on her lips
      const run = chain.then(async () => {
        if (gone) return false
        const early = pcmEarly.get(text); pcmEarly.delete(text)
        const a = await (early ?? pcm(text))
        if (!a || gone) return false
        return new Promise<boolean>(res => { speaking = () => res(true); try { s.repeatAudio(a) } catch { speaking = null; res(false) } })
      })
      chain = run.catch(() => {})
      return run.catch(() => false)
    },
  }
}

/** Sasha 268 · rows 952/953 (Tyler): ONE FRAMING — her half-body view (head, shoulders, upper body), exactly as her live video draws it.
 *  The still is a frame of that live video (1280×720, keyed, transparent — public/sasha-half.webp), drawn in the SAME box with the same
 *  crop and position as the live canvas (cover · center 18%), so when the live video takes over nothing moves. It replaces the tight
 *  face close-up (/sasha-face.jpg, 320×320) and the small kept snapshots (s2_face, 160 px) — neither is shown anywhere any more. */
export const FACE_STILL = '/sasha-half.webp'
export const FRAMING = 'center 18% / cover no-repeat'
/** Sasha 265 · item 2: the one thing that skips the arrival's motion (row 936) — then the circle at once, her face still shown. */
/** Sasha 268 · her frame from the first paint (the proof saw ~1.3 s of page without her while the sign-in check ran): a browser that
 *  holds a sign-in shows her still at once; a signed-out answer takes it away (her opening is for the signed-in). */
const signedInHere = (): boolean => { try { return /(?:^|; )sb-[^=]+-auth-token(?:\.0)?=/.test(document.cookie) } catch { return false } }
const never = () => () => {}
const reducedMotion = (): boolean => { try { return window.matchMedia('(prefers-reduced-motion: reduce)').matches } catch { return false } }
const drawn = (c: HTMLCanvasElement | null) => !!c && c.dataset.drawn === '1'

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

/** Sasha 266 · row 943 (b): her LIVE face (a tap brought her back) is let go after this long quiet (it bills by the minute) — her
 *  still stays, full size, until a tap or his next request sends her to the corner. Sasha 271: never an empty frame (letGo). */
const FACE_IDLE_S = 120
/** Sasha 271 · the corner, when her own tab's voice row (#s2-face-slot) isn't on screen: the screen's bottom-right corner. */
const CORNER = 40
const CORNER_FALLBACK = { left: `calc(100vw - ${CORNER + 16}px)`, top: `calc(100dvh - ${CORNER + 16}px - env(safe-area-inset-bottom))` }
/** Sasha 273 · the visible viewport (a phone browser's bars are outside it): where the corner may sit. */
const viewNow = () => { const v = window.visualViewport; return v ? { top: v.offsetTop, height: v.height, left: v.offsetLeft, width: v.width } : { top: 0, height: window.innerHeight, left: 0, width: window.innerWidth } }
const held = () => new Promise(r => setTimeout(r, HOLD_MS))   // Sasha 273 · item 1: after her speech-ended event, ~0.5 s, then the corner
const pause = () => new Promise(r => setTimeout(r, PAUSE_MS))   // Sasha 296 · the slight pause on both ends of "Still here."
/** Sasha 296 · this tab's session has heard the camera words on her lips (opening-rule CAMERA_SAID). */
const cameraSaid = (): boolean => { try { return sessionStorage.getItem(CAMERA_SAID) === '1' } catch { return false } }
const markCamera = () => { try { sessionStorage.setItem(CAMERA_SAID, '1') } catch { /* private mode */ } }
const lang = (): string => { try { return navigator.language || 'en' } catch { return 'en' } }

/** Sasha 268 · what the page asks of her: is she full size, and — on his next request after a tap brought her back — say this, then
 *  the corner. Sasha 271: during her arrival she is already saying it; she goes to the corner as it ends. Sasha 273 · again: rule 4
 *  (lib/presence-rule.mjs reappear) said she reappears — the arrival once more ("Hey <name>", or her news first), then the corner. */
export type HelloCtl = { big: () => boolean; bye: (line: string, speak: boolean) => Promise<void>; again: (news?: string | null) => boolean; live: () => boolean
  waiting: () => boolean   // Sasha 295 · the opening waits for his tap (anything he does first ends it: bye)
  returned: (pickup: Promise<string>) => boolean   // Sasha 296 · the page is back (opening-rule returned): her still, "Tap to continue"
  settleLine: () => string }   // Sasha 296 · what she says going into the corner now (settle): the camera words once, then 'Still here.'

export default function S2Hello({ talker, name, signedIn, backLine, dormant, asleep = false, onWake, started = false, ctlRef, arrive, micLive = false, lead = null, working = false,
  onBegin, onType, onStarter, onNoSound, onOpening, muted = false }: { talker: Talker; name: string | null | undefined; signedIn: boolean | null; backLine?: string | null; dormant?: boolean
  asleep?: boolean; onWake?: () => void
  /** Sasha 295 · THE OPENING's moves (lib/opening-rule.mjs), each inside his tap: the mic · the box · a starter · her voice failed · panel up */
  onBegin?: () => void; onType?: () => void; onStarter?: (t: string) => void; onNoSound?: () => void; onOpening?: (up: boolean) => void
  started?: boolean; ctlRef?: { current: HelloCtl | null }
  arrive?: boolean; micLive?: boolean; lead?: string | null; working?: boolean; muted?: boolean }) {   // Sasha 246 item 2 · asleep: her face stops and dims; a tap on it wakes her · Sasha 251 · started: the conversation has begun — the opening ends · Sasha 273 · arrive: rule 4's answer at load (undefined: not known yet) · micLive: the mic is hearing
  type Phase = 'off' | 'ready' | 'back' | 'starting' | 'face' | 'faceLate' | 'voice' | 'tap' | 'bubble' | 'faceAgain'
  const [phase, setPhase] = useState<Phase>('off')
  const [tapFor, setTapFor] = useState<'face' | 'voice'>('voice')
  const phaseRef = useRef<Phase>('off')
  useEffect(() => { phaseRef.current = phase }, [phase])
  // Sasha 281 · the phase, set now (the ref at once — the next line asks it before React renders)
  const to = (ph: Phase) => { phaseRef.current = ph; setPhase(ph) }
  const tapForRef = useRef<'face' | 'voice'>('voice')
  useEffect(() => { tapForRef.current = tapFor }, [tapFor])
  const img = FACE_STILL   // Sasha 268 · the ONE still (her half-body frame) — never a kept snapshot or a close-up
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
  const [live, setLive] = useState(false)   // the live face has drawn a frame: her still steps back (the keyed frame is see-through)
  const face = useRef<Face | null>(null)
  // Sasha 271 · C — THE VANISH, at its cause: her live face was let go (120 s quiet, Pause, or its session ended by itself) and the
  // canvas it had drawn on stayed "drawn" — so her still stayed hidden behind a frame with nothing reliable in it. Now letting her go
  // empties the canvas and shows her still, every way it happens: the frame is never left showing nothing.
  const letGo = (f: Face | null) => {
    if (f && face.current === f) face.current = null
    keyOff()
    const c = canvas.current
    if (c) { try { c.getContext('2d')?.clearRect(0, 0, c.width, c.height) } catch { /* no context */ } c.dataset.drawn = '0' }
    setLive(false)
    if (f) void f.stop()
  }
  const collapse = async () => {
    if (idle.current) clearTimeout(idle.current)
    const f = face.current
    if (f) letGo(f)
    to('bubble')
  }
  // Sasha 266 · row 943 (b) · Sasha 281: a tap's live face is let go after FACE_IDLE_S quiet (it bills by the minute) — and she goes to the
  // corner with it (271 left her still full size: the next line was said over it, a frozen face)
  const arm = () => {
    if (phaseRef.current !== 'faceAgain') return
    if (idle.current) clearTimeout(idle.current)
    idle.current = setTimeout(() => { if (phaseRef.current === 'faceAgain') void collapse() }, FACE_IDLE_S * 1000)
  }
  // Sasha 281 · her live face is up AND heard (a face still muted — its tap card waiting — is not her lips yet)
  const faceUp = () => !!face.current && !face.current.video.muted
  // Sasha 281 · THE ONE WAY SHE SAYS ANYTHING on /s2 while she is drawn — her arrival, a return, bye, and (the route, below) every line
  // the page speaks. Her live face up → its lips (Face.say); it missed them, or there is no live face → the corner first, then her
  // voice (`plain`: the line without the camera words). NEVER a line over a big still or a frozen face (presence-rule speakVia).
  const bigNow = () => phaseRef.current === 'faceAgain' || openingShown(phaseRef.current, tapForRef.current, false) !== null   // an opening phase still drawn (started or not: it is going)
  const speak = async (t: string, plain: string = t): Promise<'face' | 'played' | 'blocked' | 'failed' | 'none'> => {
    const f = face.current
    if (t && f && speakVia({ live: faceUp() }) === 'face') {
      arm()
      talker.heard?.()   // Sasha 275's measure: her voice starts (as the page's own audio element reports it)
      talker.speaking?.(true)   // Sasha 295 · the mic's gate and the cue: she is speaking (her face's audio isn't the page's element)
      const said = await f.say(t)
      talker.speaking?.(false)
      if (said) return 'face'
      console.log('[s2-hello] a line missed her lips — the corner, then her voice')
    }
    if (bigNow()) await collapse()   // no live face, or it missed her lips: the corner before a word
    if (!plain) return 'none'
    return talker.sayNow(plain)
  }
  const speakRef = useRef(speak)
  useEffect(() => { speakRef.current = speak })
  // every line the page says (its speaker's queue) comes here — set for her whole time on the page, not only while a tap holds her face
  useEffect(() => { talker.setRoute(async t => { await speakRef.current(t) }); return () => talker.setRoute(null) }, [talker])
  const text = useRef('')
  const [line, setLine] = useState('')
  const idle = useRef<ReturnType<typeof setTimeout> | null>(null)
  const early = useRef<{ p: Promise<Face>; t0: number } | null>(null)   // her face starts at mount, before the sign-in check returns
  const asleepRef = useRef(asleep)   // Sasha 246 item 2
  const startedRef = useRef(started)   // Sasha 251 · read by the opening's own async steps (a late face, a blocked voice)

  useEffect(() => {
    if (signedIn === false || arrive === false) { early.current?.p.then(f => f.stop()).catch(() => {}); early.current = null; return }   // Sasha 273 · no arrival: no face started
    if (early.current || !video.current || reducedMotion()) return   // Sasha 265 · item 2: every arrival (row 936) — no per-tab skip
    early.current = { p: startFace(video.current), t0: performance.now() }
    early.current.p.catch(() => {})
  }, [signedIn, arrive])

  useEffect(() => talker.onSpeaking(setTalking), [talker])

  const handoff = async () => {
    const f = face.current
    if (f) letGo(f)   // the session ENDS after the hello — her still, in the corner
    try { sessionStorage.setItem('s2_hello', '1'); localStorage.setItem('s2_met', '1') } catch { /* private mode */ }
    to('bubble')
  }
  const back = useRef<boolean | null>(null)   // Sasha 230 · decided once per visit, before the hello is said
  const news = useRef<string | null>(null)    // Sasha 273 · item 4 (c): her reappearance leads with this (again's, or the load's `lead`)
  const leadRef = useRef<string | null>(lead)   // the load's news (rule 4 at load), said once
  const leadSaid = useRef<string | null>(null)
  useEffect(() => { leadRef.current = lead }, [lead])
  // Sasha 271 · B: voice.arrival_line — "Hey there." / "Hey <name>.", from the backend. Sasha 281 · 296: `plain` is the line alone; the
  // camera words are settle()'s to add (her live face, once a session) — lipLine() is what her lips will say, fetched ahead.
  const words = async () => {
    if (back.current === null) back.current = metBefore() || !!backRef.current
    const fresh = leadRef.current && leadRef.current !== leadSaid.current ? leadRef.current : null
    if (fresh) leadSaid.current = fresh
    const n = news.current || fresh
    const plain = await (n ? newsLine(n, false) : arrivalLine(nameRef.current ?? null, !!back.current, false))
    text.current = plain
    setLine(plain)
    return { plain }
  }
  const lipLine = (plain: string) => (cameraSaid() ? plain : withCamera(plain, cameraOffLine(), true))
  // Sasha 296 · INTO THE CORNER — the ONE way (opening-rule settle), from her arrival, a return, his request and a tap on her face:
  // `lead` said on her lips (with the camera words the first time a session; else a pause, "Still here.", a pause). No live face: the
  // corner first, `plain` in her voice, no camera words. → how her lead went. The caller then sends her to the corner.
  const settleNow = async (lead: string, plain: string): Promise<'face' | 'played' | 'blocked' | 'failed' | 'none'> => {
    const s = settleOf({ said: cameraSaid(), live: faceUp() })
    if (!s.steps.length) return speak('', plain)
    let how: 'face' | 'played' | 'blocked' | 'failed' | 'none' = 'face'
    for (const st of s.steps) {
      if (asleepRef.current) return how   // paused mid-way: she stops (the pause's own collapse)
      if (st === 'say') {
        const t = s.camera ? withCamera(lead, cameraOffLine(), true) : lead
        if (!t) continue
        how = await speak(t, plain)
        if (how !== 'face') return how   // it missed her lips: speak() took her to the corner and said `plain`
        if (s.camera && cameraOffLine()) markCamera()
      } else if (st === 'hold') await held()
      else if (st === 'pause') await pause()
      else if (st === 'still') { const t = stillHereLine(lang()); if (t && await speak(t, '') !== 'face') return how }
    }
    return how
  }
  const settleLine = () => (faceUp() ? (cameraSaid() ? stillHereLine(lang()) : cameraOffLine()) : '')
  // Sasha 271 · B (row 1008): her lines, then the corner — no wait for his first request (Sasha 266/268's stay is gone).
  // Sasha 273 · item 1: "then" is her line's OWN speech-ended event, then HOLD_MS — never a guessed duration, so she never leaves mid-line.
  const toCorner = async () => { if (OPENING.includes(phaseRef.current)) { await held(); if (OPENING.includes(phaseRef.current)) await handoff() } }
  // Sasha 295 · her lines are worked out ONCE, while the opening waits (their audio fetched then) — the tap says these
  const lines = useRef<Promise<{ plain: string }> | null>(null)
  const take = () => { const l = lines.current || words(); lines.current = null; return l }
  const speakFace = async () => {
    if (asleepRef.current || startedRef.current) return handoff()   // Sasha 246 · asleep: no hello — straight to the (dimmed) bubble · Sasha 251: or already talking
    const { plain } = await take()
    if (!face.current || !plain) return handoff()
    const how = await settleNow(plain, plain)   // Sasha 296 · her live face says it, then settle's beats — each over when SHE says it is
    if (how === 'face') { if (OPENING.includes(phaseRef.current)) await handoff() }   // Sasha 281 · else it missed her lips: speak() took her to the corner
    else { if (how === 'failed') onNoSound?.(); await handoff() }   // Sasha 295 · never a silent face: her one line, the box ready
  }
  const speakVoice = async () => {
    if (asleepRef.current || startedRef.current) return handoff()   // Sasha 246 · Sasha 251: they already started — no hello over them
    const { plain } = await take()
    if (!plain) return handoff()
    const r = await speak(plain)   // Sasha 281 · no live face: from the corner (phase 'voice' is drawn there), the line alone
    if (r === 'failed') onNoSound?.()   // Sasha 295 · her voice didn't play: said in one line, the box ready
    if (r === 'blocked' && startedRef.current) return handoff()   // Sasha 251 · they started talking meanwhile: no tap card over the chat
    if (r === 'blocked') { setTapFor(face.current ? 'face' : 'voice'); to('tap'); return }   // Sasha 232 · her face, if it came, with the tap
    await toCorner()   // said — then the corner
  }

  const lateFace = (f: Face, v: HTMLVideoElement) => {
    const now = phaseRef.current
    console.log(`[s2-hello] face on screen late (${now})`)
    // Sasha 281 · a face that comes while her voice is mid-line ('voice', Tyler's 17:58 return) is NEVER shown: that line isn't on its
    // lips, so it would be a frozen face (it was: phase faceLate, her live face full size, muted, lips still). Only a tap card waiting
    // to be tapped takes it — the tap then says the line through it.
    if (now === 'tap' && tapForRef.current === 'voice') { face.current = f; keyOn(); v.muted = true; v.play().catch(() => {}); setTapFor('face') }
    else letGo(f)   // Sasha 257 · 268: no snapshot · 271: she's in the corner — her still
  }

  // the opening: as soon as the page is signed in and the name is known (or ~0.9 s has passed) — Sasha 273 · and rule 4 has answered:
  // a quick return mid-conversation (arrive === false) is NO arrival (the corner at once, no face started, no line); and again() runs
  // the same arrival when rule 4 says she reappears on a return to the page.
  const timers = useRef<{ go?: ReturnType<typeof setTimeout>; timer?: ReturnType<typeof setTimeout> }>({})
  const arriveNow = (skip: boolean) => {
    const go = setTimeout(() => {   // out of the effect's own pass (no state set while it runs)
    // Sasha 265 · item 2 (row 936, Tyler: "when he logs back in he never sees her"): a return skipped this — sessionStorage
    // 's2_hello' sent every later arrival straight to the bubble. ONE arrival sequence now, every arrival: her face full size, the
    // hello (a return: "welcome back"), then the circle. Only reduced motion skips the motion — the circle at once, her face in it.
    if (skip || reducedMotion() || startedRef.current || asleepRef.current) { early1.current = false; to('bubble'); return }   // Sasha 251 · already talking (this visit): no opening over it · 273: rule 4 said no
    // Sasha 295 · THE OPENING (lib/opening-rule.mjs): her still, full size, with ONE action — and NOTHING said until his tap (a phone
    // won't play her before one: the stand-off Tyler saw was her waiting ~6 s to try). Her face keeps starting meanwhile (muted when it
    // comes); her lines are worked out now and their audio fetched, so the tap hears her within ~1 s. No timer decides anything here.
    const v = video.current as HTMLVideoElement
    const t0 = early.current?.t0 ?? performance.now()
    const starting = early.current?.p ?? startFace(v)
    early.current = null   // Sasha 273 · used: a later arrival (again) starts its own
    to(READY)
    lines.current = words()
    if (early1.current) { early1.current = false; begin(); return }   // he tapped while she was still being decided: her hello now (her voice)
    lines.current.then(({ plain }) => { if (plain) talker.prefetch?.(plain) }).catch(() => {})
    starting.then(async f => {
      console.log(`[s2-hello] face on screen in ${Math.round(performance.now() - t0)} ms`)
      if (phaseRef.current !== READY) { lateFace(f, v); return }   // the tap came first: her voice is saying it — never a frozen face
      face.current = f
      keyOn()
      v.muted = true; v.play().catch(() => {})   // her live face, quiet, until his tap
      const l = await lines.current?.catch(() => null)
      if (l?.plain) prefetchPcm(lipLine(l.plain))   // what her lips will say (settle: the camera words once a session)
      // her live face bills by the minute: a tap that never comes lets it go (her still stays, the action with it)
      timers.current.timer = setTimeout(() => { if (phaseRef.current === READY && face.current === f) letGo(f) }, FACE_IDLE_S * 1000)
    }).catch(() => console.log('[s2-hello] face failed to start — her voice will say it'))
    }, 0)
    timers.current.go = go
  }
  /** Sasha 295 · THE TAP (TALK): inside it, in order — her sound, the mic (its prompt asked by this tap), then her hello: her live
   *  face says it when it is up (unmuted here, in the tap), else her voice from the corner. Never before it. */
  const early1 = useRef(false)   // a tap before her arrival was decided ('off'): held, then the hello once it is
  const begin = () => {
    if (phaseRef.current === 'off') { talker.unlock(); onBegin?.(); early1.current = true; return }
    if (phaseRef.current !== READY && phaseRef.current !== BACK) return   // Sasha 296 · "Tap to continue": the same tap
    if (timers.current.timer) clearTimeout(timers.current.timer)
    talker.unlock()
    onBegin?.()
    const f = face.current
    if (f) { f.video.muted = false; f.video.play().catch(() => {}); to('face'); void speakFace() }
    else { to('voice'); void speakVoice() }
  }
  /** OR_TYPE, or a starter: the box (or that first message) — the opening ends at once, with no hello over it. */
  const skipTo = (then: () => void) => { if (phaseRef.current !== READY && phaseRef.current !== BACK && phaseRef.current !== 'off') return; talker.unlock(); lines.current = null; then(); void handoff() }
  useEffect(() => {
    if (signedIn !== true || arrive === undefined || phaseRef.current !== 'off') return
    arriveNow(arrive === false)
    const tm = timers.current
    return () => { clearTimeout(tm.go); clearTimeout(tm.timer) }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- once, when signed in and rule 4 has answered
  }, [signedIn, arrive])
  /** Sasha 273 · item 4: rule 4 said she reappears (30 min quiet, a new day, or news) — from the corner only, never while paused, never
   *  over another tab, never mid-sentence (the page stopped her speech when it was hidden). → whether she did. */
  const again = (lead?: string | null) => {
    if (phaseRef.current !== 'bubble' || asleepRef.current || startedRef.current || byeing.current) return false
    back.current = true
    news.current = lead || null
    to('off')
    arriveNow(false)
    return true
  }
  /** Sasha 296 · RETURNED (opening-rule returned, asked by the page's ONE return handler): from the corner only, never while paused or
   *  over another tab — her still full size and "Tap to continue"; his tap hears `pickup` (voice.pickup_line, its audio fetched now)
   *  in her voice, from the corner. No live face is started for it (it takes ~10 s to come; the tap is sooner). */
  const returnedNow = (pickup: Promise<string>) => {
    if (phaseRef.current !== 'bubble' || asleepRef.current || startedRef.current || byeing.current) return false
    lines.current = pickup.then(plain => { text.current = plain; setLine(plain); return { plain } })
    lines.current.then(({ plain }) => { if (plain) talker.prefetch?.(plain) }).catch(() => {})
    to(BACK)
    return true
  }

  useEffect(() => () => { keyOff(); face.current?.stop(); talker.setRoute(null) }, [talker])   // leaving the page ends any session


  const tapToHear = () => {
    talker.unlock()
    if (tapFor === 'face' && face.current) { const v = face.current.video; v.muted = false; v.play().catch(() => {}); to('face'); speakFace() }
    else { to('voice'); speakVoice() }
  }

  const faceBack = async () => {
    talker.unlock()
    to('faceAgain')
    try {
      let mine: Face | null = null
      const ended = () => { if (mine && face.current === mine) void collapse() }   // Sasha 271 · its session ended by itself · 281: to the corner
      const f = await startFace(video.current as HTMLVideoElement, ended)
      if (phaseRef.current !== 'faceAgain') { letGo(f); return }   // Sasha 281 · a line sent her to the corner while her face connected
      mine = f
      face.current = f
      keyOn()
      f.video.muted = false
      f.video.play().catch(() => {})
      // Sasha 268 · item 6: no timer sends her back to the circle but her quiet (arm, FACE_IDLE_S) — his next request (bye) or a tap.
      // Her replies reach her lips through the page's route (speak), each over on her speech-ended event (Sasha 273).
      arm()
    } catch { to('bubble') }
  }

  // Sasha 268 · item 4: when a tap brought her back (faceAgain), his next REAL request (the page decides: voice.py's rule, a card's tap,
  // or the first tool the turn starts) sends her to the corner: she says voice.CAMERA_OFF (her live face, lip-synced, when it is up;
  // else her voice), then the corner. Sasha 271 · B: during her ARRIVAL she is already saying it — the corner follows as it ends.
  const byeing = useRef(false)
  const isBig = () => OPENING.includes(phaseRef.current) || phaseRef.current === 'faceAgain'
  const bye = async (lineToSay: string, loud: boolean) => {
    if (phaseRef.current === READY || phaseRef.current === BACK) { lines.current = null; await handoff(); return }   // Sasha 295 · he spoke or typed before the tap: the opening ends, no hello
    if (phaseRef.current !== 'faceAgain' || byeing.current) return
    byeing.current = true
    try {
      // Sasha 281 · the camera line only on her live lips; no live face → no camera words, the corner at once
      // Sasha 296 · settle: the camera words the first time a session, else a pause, "Still here.", a pause (lineToSay is settleLine's)
      if (loud && lineToSay && !asleepRef.current) await settleNow('', '')   // Sasha 273 · each over when her speech-ended event says so
    } catch { /* said or not, she goes to work */ } finally { byeing.current = false }
    await collapse()
  }
  useEffect(() => { if (ctlRef) ctlRef.current = { big: isBig, bye, again, live: faceUp, waiting: () => phaseRef.current === READY || phaseRef.current === BACK,
    returned: returnedNow, settleLine } })

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

  // Sasha 265 · item 2 · Sasha 271 · C: WHERE THE CORNER IS — her own tab's voice row (#s2-face-slot, Sasha 259: never over send), else
  // the screen's bottom-right corner. Measured, never portalled into the slot: a slot that isn't there (another tab, the sign-in
  // check) or a page faded at rest (Sasha 231) made her vanish. The slot is watched; she follows it.
  // Sasha 273 · items 1 + 5: "on screen" is the VISIBLE viewport (lib/presence-rule.mjs inView) — on iOS Safari the slot sat under the
  // bottom address bar, inside window.innerHeight, so she went "to the corner" and was covered: the vanish Tyler saw. Not visible → the
  // visible viewport's own bottom-right corner, measured the same way.
  const [spot, setSpot] = useState<{ x: number; y: number } | null>(null)
  useEffect(() => {
    const look = () => {
      const r = document.getElementById('s2-face-slot')?.getBoundingClientRect()
      const vv = viewNow()
      const sx = r ? Math.round(r.right - CORNER) : 0, sy = r ? Math.round(r.top + (r.height - CORNER) / 2) : 0
      const ok = !!r && inView({ top: sy, bottom: sy + CORNER, width: r.width }, vv, CORNER) && sx >= vv.left && sx + CORNER <= vv.left + vv.width
      const x = ok ? sx : Math.round(vv.left + vv.width - CORNER - 16), y = ok ? sy : Math.round(vv.top + vv.height - CORNER - 16)
      setSpot(s => (s && s.x === x && s.y === y ? s : { x, y }))
    }
    look()
    const mo = new MutationObserver(look)
    mo.observe(document.body, { childList: true, subtree: true })
    const t = setInterval(look, 500)
    const vv = window.visualViewport
    window.addEventListener('resize', look); window.addEventListener('scroll', look, true)
    vv?.addEventListener('resize', look); vv?.addEventListener('scroll', look)
    return () => { mo.disconnect(); clearInterval(t); window.removeEventListener('resize', look); window.removeEventListener('scroll', look, true)
                   vv?.removeEventListener('resize', look); vv?.removeEventListener('scroll', look) }
  }, [])
  // Sasha 271 · THE ONE PRESENCE (lib/presence-rule.mjs): full size or the corner, her look (green ring listening · paused · resting),
  // what a tap does — from her phase, Pause/Wake and her rest. Nothing else decides where she is or how she looks.
  const soon = useSyncExternalStore(never, signedInHere, () => false)   // 268 · hydration-safe: false on the server, the cookie on the client
  const p = presence({ phase, tapFor, started, signedIn, soon, asleep, dormant, reduced: reducedMotion(), micLive, arrive })
  const big = p.where === 'full'
  // Sasha 295 · the page draws no second welcome under the opening (its empty state waits while the panel is up)
  const op = opening({ phase, signedIn, soon, started, asleep, full: big })   // Sasha 296 · + soon: a brand-new guest's first paint carries it
  const panel = op.panel
  useEffect(() => { onOpening?.(panel) }, [panel, onOpening])
  useEffect(() => { if (!big) return; const t = setInterval(() => setLive(drawn(canvas.current)), 50); return () => clearInterval(t) }, [big])   // 268: within 50 ms
  const r = ring(p.look, talking, working)   // Sasha 279 · A · she works: the ring pulses (lib/presence-rule.mjs)
  // Sasha 296 · a tap on her face sends her to the corner through settle — never at once and silent
  const tap = p.tap === 'collapse' ? () => { void bye(settleLine(), !muted) } : p.tap === 'wake' ? () => onWake?.() : p.tap === 'face_back' ? faceBack : undefined
  const corner = p.where === 'corner'
  return (
    <>
      {r.pulse ? <style>{WORK_PULSE_CSS}</style> : null}
      <div data-sasha-face={big ? 'full' : corner ? 'circle' : undefined} data-sasha-look={p.look} data-sasha-working={r.pulse ? 'pulse' : undefined} onClick={tap}
        role={corner ? 'button' : undefined} tabIndex={corner ? 0 : undefined} onKeyDown={corner ? e => { if (e.key === 'Enter' || e.key === ' ') tap?.() } : undefined}
        aria-label={corner ? (p.look === 'paused' ? 'Sasha is paused — tap Wake, or her face, to wake her' : 'Sasha — tap to see her') : undefined}
        aria-hidden={p.where === 'none' ? true : undefined} style={{
        // Sasha 267 · never swallows a tap meant for the page: only the corner (and her face brought back) takes a tap
        position: 'fixed', zIndex: 40, pointerEvents: corner || p.tap === 'collapse' ? 'auto' : 'none', cursor: corner ? 'pointer' : undefined,
        // Sasha 268 · she appears at full size at once (no grow-in); only the move to the corner animates
        transition: big ? 'none' : 'left .45s ease, top .45s ease, width .45s ease, height .45s ease, border-radius .45s ease, transform .45s ease, box-shadow .3s, border-color .3s, opacity .8s, filter .8s',
        overflow: 'hidden', boxSizing: 'border-box', background: 'radial-gradient(120% 90% at 50% 20%, #2a2440 0%, #14141c 70%)',
        ...(big ? { left: '50%', top: 'calc(env(safe-area-inset-top) + 96px)', width: 'min(86vw, 420px)', aspectRatio: '3 / 4', transform: 'translateX(-50%)', borderRadius: 24, boxShadow: '0 20px 60px rgba(0,0,0,.6)', opacity: 1 }
          : corner ? { ...(spot ? { left: spot.x, top: spot.y } : CORNER_FALLBACK), width: CORNER, height: CORNER, aspectRatio: 'auto', transform: 'none', borderRadius: '50%',
                       border: r.border, boxShadow: r.glow, ...(r.pulse && !reducedMotion() ? { animation: `${r.pulse} ${WORK_PULSE_S}s ease-in-out infinite` } : {}), opacity: p.look === 'resting' ? 0.45 : p.look === 'paused' ? 0.6 : 1,
                       filter: p.look === 'paused' ? 'grayscale(.85) brightness(.75)' : 'none' }
          : { ...CORNER_FALLBACK, width: 0, height: 0, borderRadius: '50%', opacity: 0 }) }}>
        {(corner || (big && !live)) && <div aria-hidden data-sasha-still style={{ position: 'absolute', inset: 0, background: `${FRAMING} url(${img})` }} />}
        <video ref={video} playsInline autoPlay muted style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'cover', opacity: 0, pointerEvents: 'none' }} />
        <canvas ref={canvas} style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'cover', objectPosition: 'center 18%', display: 'block', opacity: big ? 1 : 0 }} />
        {corner && p.look === 'paused' ? (   /* Sasha 271 · D: paused, a calm look and its word — a tap wakes her */
          <span aria-hidden style={{ position: 'absolute', left: 0, right: 0, bottom: 3, textAlign: 'center', fontSize: 9.5, fontWeight: 700, letterSpacing: '.02em', color: '#fff', textShadow: '0 1px 2px #000' }}>Wake</span>) : null}
        {panel ? (   /* Sasha 295 · THE OPENING: ONE action, "or type", the starters — in her own frame, nothing said until the tap */
          <div data-opening style={{ position: 'absolute', left: 0, right: 0, bottom: 0, padding: '28px 14px 14px', background: 'linear-gradient(transparent, rgba(10,10,16,.94) 22%)',
            display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 8, pointerEvents: 'auto' }}>
            <button type="button" data-opening-talk onClick={begin} style={{ width: '100%', maxWidth: 340, minHeight: 58, padding: '14px 18px', borderRadius: 999, border: 0, background: GOLD, color: '#111',
              fontWeight: 800, fontSize: 18, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 10, boxShadow: '0 8px 24px rgba(232,185,49,.35)', cursor: 'pointer' }}>
              <svg aria-hidden width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"><rect x="9" y="2" width="6" height="12" rx="3" /><path d="M5 10a7 7 0 0 0 14 0M12 17v4" /></svg>
              {op.words}</button>
            <button type="button" data-opening-type onClick={() => skipTo(() => onType?.())} style={{ background: 'none', border: 0, color: 'rgba(255,255,255,.85)', fontSize: 15, textDecoration: 'underline', textUnderlineOffset: 3, padding: '4px 10px', cursor: 'pointer' }}>{OR_TYPE}</button>
            {op.starters ? <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, justifyContent: 'center' }}>
              {STARTERS.map(t => (
                <button key={t} type="button" data-starter onClick={() => skipTo(() => onStarter?.(t))} style={{ padding: '7px 12px', borderRadius: 999, border: '1px solid rgba(255,255,255,.28)', background: 'rgba(20,20,28,.75)', color: '#fff', fontSize: 13.5, cursor: 'pointer' }}>{t}</button>))}
            </div> : null}
          </div>) : null}
        {p.card ? (   /* her voice alone: her line under her face, in the same frame (Sasha 265 · item 2) */
          <div style={{ position: 'absolute', left: 0, right: 0, bottom: 0, padding: '14px 16px 16px', background: 'linear-gradient(transparent, rgba(10,10,16,.92) 30%)', color: '#fff', fontSize: 16, lineHeight: 1.45 }}>
            {line}
            {phase === 'tap' && <div><button onClick={tapToHear} style={{ pointerEvents: 'auto', marginTop: 10, padding: '10px 18px', borderRadius: 999, border: 0, background: GOLD, color: '#111', fontWeight: 700 }}>Tap to hear Sasha</button></div>}
          </div>) : big && phase === 'tap' && <button onClick={tapToHear} style={{ pointerEvents: 'auto', position: 'absolute', left: '50%', bottom: 18, transform: 'translateX(-50%)', padding: '12px 20px', borderRadius: 999, border: 0, background: GOLD, color: '#111', fontWeight: 700, fontSize: 16 }}>Tap to hear Sasha</button>}
      </div>
    </>
  )
}
