'use client'
import { useState, useRef, useEffect, useCallback } from 'react'
import { preconnect } from 'react-dom'   // Sasha 322 · DNS + TLS to the speech service warmed before the tap
import { Mic, MicOff, Loader2 } from 'lucide-react'
import { apiUrl, apiHeaders } from '@/lib/api'
import { watchdogAction } from '@/lib/voice-watchdog.mjs'

interface VoiceButtonProps {
  onTranscript: (text: string) => void
  /** Sasha 259 · the S2 shell (Tyler, row 884): no text under the mic — its icon's own state; the words go on its label/tooltip */
  quiet?: boolean
  disabled?: boolean
  autoStart?: boolean
  readyToListen?: boolean
  // Deliberately muted (currently: while the itinerary builds). This is a HARD mute — unlike
  // the ordinary speak-gate it cannot be barged through, because there is nothing to barge
  // into: the build runs server-side and can't be cancelled. Without this, speaking during a
  // build tripped BARGE_IN, which force-opened the gate, so Sasha started listening again and
  // the mic went green while the UI still claimed she wasn't listening.
  muted?: boolean
  onSpeakingChange?: (isSpeaking: boolean) => void
  avatarSpeaking?: boolean
  onInterrupt?: () => void
  onSetGate?: (gate: (value: boolean) => void) => void
  avatarSpeechGetter?: () => string
  language?: string
  // Fired whenever the live STT socket connects (true) or drops (false), so the parent
  // can show an accurate "mic live" status instead of guessing.
  onConnectedChange?: (connected: boolean) => void
  // Surfaces mic/voice failures to the page. Without this the error only ever rendered as a
  // small red line under the mic icon in the composer, while the call panel — the thing
  // everyone is actually looking at — sat on "Starting microphone…" forever.
  onMicError?: (message: string | null) => void
  // Hands the mic-device list + switcher up to the page, which renders the picker as a pill
  // next to the camera toggle in the call panel where every other call control lives. This is
  // the ONLY place the picker is drawn — VoiceButton no longer renders one itself.
  onMicDevices?: (info: MicDevicesInfo | null) => void
  // Sasha 246 item 2 · the pause / sleep button: asleep = the mic is OFF (stream stopped, socket closed, no auto-listen, no
  // reconnect, no barge-in). Pressing the mic while asleep wakes her (onWake) and starts listening; a wake from elsewhere
  // brings the mic back only if it was on (or wanted) when she fell asleep.
  asleep?: boolean
  onWake?: () => void
  // Sasha 273 · item 3 (/s2 only — /next is unchanged): `hearing` is STRICT — frames arriving NOW (within LIVE_FRAME_MS), a live
  // unmuted track, the audio running. A page that went to the background (an iPhone suspends both) is never "on". `ctlRef` gives
  // the page the mic's two moves for its one return handler and its "Tap to talk": resume (on return, what the browser allows
  // without a tap) and tap (inside a tap: start or resume, never stop).
  strict?: boolean
  ctlRef?: { current: VoiceCtl | null }
  // Sasha 322 · her phase, for the ONE state machine (lib/mic-machine.mjs): she is speaking (the mic paused) / a turn is in flight
  speaking?: boolean
  thinking?: boolean
  /** Sasha 322 · the mic's state as the machine reads it from the pipeline: off · connecting · listening · thinking · speaking */
  onState?: (state: MicState) => void
}

/** Sasha 273 · what /s2 may ask of its mic: on return, resume what was live; on a tap, listen (start or resume — never stop). */
export type VoiceCtl = { resume: () => void; tap: () => void; granted: () => boolean; speechEndAt: () => number | null }
export type MicState = 'off' | 'connecting' | 'listening' | 'thinking' | 'speaking'

// What the page needs to render its own mic picker: the choosable devices, what's selected
// now, and the switcher (which tears down and reopens the pipeline on the new device).
export interface MicDevicesInfo {
  devices: { deviceId: string; label: string; isPhone: boolean }[]
  selectedId: string
  switchMic: (id: string) => void
}

// UI language → a valid Deepgram nova-3 language code (en-US is the safe default).
const DG_LANG: Record<string, string> = {
  en: 'en-US', vi: 'vi', ko: 'ko', zh: 'zh', ja: 'ja', fr: 'fr', es: 'es', de: 'de', hi: 'hi',
}

// Public env key is a DEV fallback only. In production the backend mints a short-lived,
// scoped key (see getDeepgramKey) so a long-lived key never sits in the browser.
import { keyOrFail, RECONNECTS_BEFORE_SAYING } from '@/lib/mic-fail.mjs'   // Sasha 215 · the mic never fails silently
import { micLog } from '@/lib/mic-log'   // Sasha 213 · the mic's state machine, logged
import { BLOCKED, micPermission } from '@/lib/mic-state'   // Sasha 266 · "on" only when it hears; blocked said, with its steps
import { holdPlayAndRecord, audioSessionType } from '@/lib/audio-session'   // Sasha 267 · the page's one audio session
import { makeDownsampler, sendRate } from '@/lib/downsample.mjs'   // Sasha 215 (d) · the mic at 16 kHz
import { micState as readMic, MIC_WORDS, REPLY_MS } from '@/lib/mic-machine.mjs'   // Sasha 322 · the ONE state machine, read from the pipeline

const PUBLIC_DEEPGRAM_KEY = process.env.NEXT_PUBLIC_DEEPGRAM_API_KEY || ''

// Ask the backend for an ephemeral STT key. Sasha 215 · the public env key ONLY when the backend says the proxy isn't
// configured (501, local dev) — any other failure is said, never a silent fallback to an empty key (CR 56 #9).
async function getDeepgramKey(): Promise<string> {
  let status = 0, key = ''
  try {
    const res = await fetch(apiUrl('/api/voice/deepgram-key'), { method: 'POST', headers: apiHeaders() })
    status = res.status
    micLog('key', { status: res.status })
    if (res.ok) key = ((await res.json())?.key as string) || ''
  } catch { /* unreachable: status 0 */ }
  return keyOrFail(status, key, PUBLIC_DEEPGRAM_KEY).key
}

// Sasha 322 · THE KEY IS MINTED BEFORE THE TAP (Tyler's iPhone, 1 Nov: 0.73–1.09 s of every start was this mint, and the socket waited
// for it). One key per page, kept KEY_REUSE_MS (it lives DEEPGRAM_KEY_TTL, an hour, on the server) and reused by every socket — a tap and
// every reconnect find it ready. Asks for nothing (no mic, no permission prompt); never minted for a site the browser blocks.
const KEY_REUSE_MS = 10 * 60 * 1000
let KEY: { key: string; at: number } | null = null
let KEY_INFLIGHT: Promise<string> | null = null
function prefetchKey(): Promise<string> {
  if (KEY && Date.now() - KEY.at < KEY_REUSE_MS) return Promise.resolve(KEY.key)
  if (KEY_INFLIGHT) return KEY_INFLIGHT
  KEY_INFLIGHT = getDeepgramKey().then(k => { if (k) KEY = { key: k, at: Date.now() }; return k }).finally(() => { KEY_INFLIGHT = null })
  return KEY_INFLIGHT
}
function dropKey() { KEY = null }
const BUFFER_MS = 5000   // Sasha 322 · words said while it gets ready: kept (up to this much) and sent first when the socket opens

// Barge-in tuning. The mic is fully muted while the avatar speaks — that is what
// stops the avatar hearing itself. A user may still interrupt, but ONLY with a
// sustained, clearly-loud voice; speaker bleed is moderate and must never trip this
// or the echo loop returns. Set BARGE_IN_ENABLED = false to disable interruption
// entirely (guarantees zero echo; the user simply waits for the avatar to finish).
const BARGE_IN_ENABLED = true
// Barge-in over SPEAKERS: the browser's echo cancellation (enabled in getUserMedia)
// removes most of the avatar's audio from the mic; this threshold sits above the typical
// AEC *residual* but below normal user speech (~0.1–0.3 RMS close-talking). Tuned live.
// If it ever self-triggers on loud speakers, raise it; if you can't interrupt, lower it.
// 0.12/40 (the loud-hall setting) proved DEAF in live runs: a guest saying "Sasha. Sasha.
// Sasha." and "stop stop stop" at close range could not interrupt her once — the single
// most-repeated failure across two recorded sessions. 0.08/30 keeps a margin over AEC
// residual and room bleed while letting a raised voice actually barge in. Raise toward
// 0.12 ONLY for a genuinely loud hall, and re-test interruption before the demo.
const BARGE_IN_RMS = 0.08
const BARGE_IN_FRAMES = 30           // ~75ms sustained — rejects transient residual spikes
// Echo (avatar audio bleeding into the mic) only arrives in the brief tail right after
// the avatar goes quiet. Beyond this window, identical words are the USER genuinely
// answering (e.g. repeating the avatar's options like "mix of everything") — never
// discard those, or the avatar appears to "stop hearing" the user.
const ECHO_WINDOW_MS = 1000
// Turn-hold after Deepgram declares end-of-speech, before the transcript is submitted.
// Deepgram's endpointing fires speech_final after just 300ms of silence — a natural
// mid-sentence pause — which made Sasha answer half-finished thoughts. The hold gives the
// guest time to resume (which cancels it and merges the fragments into one turn):
//  - transcript already ends in . ! ? → almost certainly finished → short hold, snappy reply
//  - trailing off unpunctuated ("I want to go to…") → likely thinking → wait longer
const TURN_HOLD_DONE_MS = 350       // asked a question / gave a directive / short answer
const TURN_HOLD_DECLARATIVE_MS = 1300  // complete sentence but only setting context — guests
                                       // routinely breathe ~1s and continue ("I'm traveling
                                       // from India with my wife. [pause] For seven days.")
const TURN_HOLD_PAUSE_MS = 1000
// A false start ("But…", "That…", "so we want to…") is grammatically incomplete — a lone
// connector word, or a turn ending in a conjunction/preposition/article. Guests follow these
// with LONG thinking pauses (2-4s), far beyond the normal hold, and submitting them made
// Sasha reply to one word ("Sorry, go ahead — what were you thinking?") three times in a
// session. Give these a much longer runway; if nothing more ever comes, they still submit
// and Sasha handles the fragment gracefully.
const TURN_HOLD_FRAGMENT_MS = 2500
// A single connector/filler word alone is a false start ("But…", "That…", "Well…").
// Trailing words are judged separately: "that"/"it" at the END of a phrase usually
// COMPLETE it ("let's do that", "book it") and must stay snappy, while a trailing
// conjunction/preposition/article ("we want to go to…") means the guest is mid-thought.
const ALONE_FRAGMENT_WORDS = new Set([
  'but', 'and', 'so', 'that', 'or', 'because', 'then', 'also', 'if', 'the', 'a', 'an',
  'to', 'with', 'my', 'our', 'i', 'we', 'it', 'is', 'um', 'uh', 'well', 'hmm', 'like',
  'actually', 'maybe', 'plus', 'what',
])
const TRAILING_FRAGMENT_WORDS = new Set([
  'but', 'and', 'so', 'or', 'because', 'then', 'if', 'to', 'with', 'for', 'of', 'in',
  'on', 'at', 'the', 'a', 'an', 'my', 'our', 'i', 'we', 'is', 'are', 'was', 'um', 'uh',
  'well', 'hmm', 'plus', 'than', 'about', 'around', 'near', 'from', 'into',
])
// A turn ending in a place name is complete however it parses ("what can we do in Hoi An"
// must not be read as trailing off at the article 'an').
const ENDS_WITH_PLACE = new RegExp(
  '\\b(hoi an|ha ?long( bay)?|da ?nang|phu ?quoc|da ?lat|mui ne|con dao|nha trang|' +
  'ninh binh|sa ?pa|hanoi|saigon|ho chi minh( city)?|hue|vietnam|mekong( delta)?)$')
// A pure greeting ("Hey, Sasha.") is an opener, never a whole turn — the ask is coming.
const GREETING_WORDS = new Set(['hey', 'hi', 'hello', 'sasha', 'shasha', 'sacha', 'there',
                                'good', 'morning', 'afternoon', 'evening', 'again'])
const isFragmentTurn = (t: string): boolean => {
  const clean = t.toLowerCase().replace(/[^a-z' ]/g, ' ').replace(/\s+/g, ' ').trim()
  const words = clean.split(' ').filter(Boolean)
  if (!words.length) return true
  if (words.every(w => GREETING_WORDS.has(w))) return true
  if (ENDS_WITH_PLACE.test(clean)) return false
  if (words.length === 1) return ALONE_FRAGMENT_WORDS.has(words[0])
  return TRAILING_FRAGMENT_WORDS.has(words[words.length - 1])
}

// Words that make a sentence an ASK — something Sasha should act on now. A punctuated
// sentence WITHOUT any of these is narrative context, and guests often keep narrating.
const DIRECTIVE_WORDS = new Set([
  'show', 'find', 'book', 'reserve', 'build', 'plan', 'create', 'make', 'tell', 'give',
  'recommend', 'suggest', 'help', 'need', 'want', 'search', 'look', 'get', 'add', 'remove',
  'swap', 'change', 'cheaper', 'upgrade', 'please', 'can', 'could', 'would', 'what',
  'where', 'when', 'which', 'how', 'why', 'who', 'yes', 'no', 'okay', 'ok', 'sure',
])

// The turn-end hold, graded by how finished the utterance actually is.
const holdFor = (text: string): number => {
  if (isFragmentTurn(text)) return TURN_HOLD_FRAGMENT_MS
  const t = text.trim()
  if (/\?$/.test(t)) return TURN_HOLD_DONE_MS          // asked Sasha something — done
  const words = t.toLowerCase().replace(/[^a-z' ]/g, ' ').split(/\s+/).filter(Boolean)
  if (/[.!]$/.test(t)) {
    if (words.length <= 4) return TURN_HOLD_DONE_MS     // short answer ("Seven days.")
    if (words.some(w => DIRECTIVE_WORDS.has(w))) return TURN_HOLD_DONE_MS
    return TURN_HOLD_DECLARATIVE_MS                     // context-setting — may continue
  }
  return TURN_HOLD_PAUSE_MS                             // unpunctuated trailing pause
}
// Real acoustic echo is a multi-word fragment of the avatar's sentence. A SHORT reply
// ("Hanoi", "yes please", "the beach") that happens to echo a word the avatar just said is
// almost always the user genuinely answering — and the mic is muted while the avatar
// speaks, so true echo is rare on the normal path. Never echo-filter short replies; this
// is the main cause of "she sometimes doesn't hear me".
const ECHO_MIN_WORDS = 4

const normalizeText = (t: string) => t.toLowerCase().replace(/[^\w\s]/g, '').split(/\s+/).filter(Boolean)

// Continuity / handoff devices we should NOT auto-select: a Mac hands the iPhone's or iPad's mic
// to the browser as "default", so a guest whose phone is in another room gets a dead mic.
// NOTE the word boundaries. This previously included a bare `phone` alternative, which matches
// the substring in "MacBook Pro Microphone", "Headset Microphone", "External Microphone" — i.e.
// virtually every real mic. Any machine that also had a device WITHOUT "phone" in its label
// (Yeti, Scarlett, Teams Audio, a virtual/loopback device) would therefore treat its genuine
// built-in mic as a Continuity device and deliberately switch away from it to that other input,
// which is usually silent. That is the "mic isn't picked up on some systems" report.
const PHONE_MIC_RE = /\b(iphone|ipad)\b|continuity/i
const MIC_PREF_KEY = 'sasha_mic_id'

// Which audioinput to open. An explicit stored choice wins (if still present); otherwise pick the
// first REAL local mic, skipping any phone/Continuity device; '' means "let the browser decide"
// (only reached before labels are known or when a phone is genuinely the only input).
function preferredAudioDeviceId(list: MediaDeviceInfo[], stored: string): string {
  const inputs = list.filter(d => d.kind === 'audioinput' && d.deviceId && d.deviceId !== 'default')
  if (stored && inputs.some(d => d.deviceId === stored)) return stored
  const local = inputs.find(d => d.label && !PHONE_MIC_RE.test(d.label))
  return local?.deviceId || ''
}

// Sasha 101 · place names guests SAY that the recogniser mangles ("Chamberí" came back "Chambhuri"): nova-3 keyterms
const KEYTERMS = ['Chamberí', 'Malasaña', 'Chueca', 'Lavapiés', 'La Latina', 'Salamanca', 'Retiro', 'Chamartín', 'Argüelles', 'Moncloa', 'Huertas']
  .map((k) => `&keyterm=${encodeURIComponent(k)}`).join('')

// Sasha 264 · item 7: what the mic says when it isn't reaching her (never "Listening" while deaf)
const DEAF_TAP = 'Sasha can’t hear you — tap the mic to talk'
const DEAF_AFTER_MS = 4000
// Sasha 267 · iOS refused the mic because the page's audio was play-only (should no longer happen: lib/audio-session) — said plainly
const AUDIO_MODE = 'I can’t hear you — your phone kept this page’s sound play-only. Reload this page, then tap the mic.'
const PREROLL_MS = 600        // Sasha 265 · item 1: kept while she speaks, sent only if the person talks over her (barge-in)
const RESUME_WAIT_MS = 1000   // Sasha 265 · item 1: how long the audio may take to start before the socket opens anyway (and the screen says tap)

export default function VoiceButton({ onTranscript, quiet = false, muted = false, disabled, autoStart = false, readyToListen = false, onSpeakingChange, onInterrupt, onSetGate, avatarSpeechGetter, language = 'en', onConnectedChange, onMicError, onMicDevices, asleep = false, onWake, strict = false, ctlRef, speaking, thinking, onState }: VoiceButtonProps) {
  const strictRef = useRef(strict)   // Sasha 273 · /s2: "on" only while frames arrive
  useEffect(() => { strictRef.current = strict }, [strict])
  const wasLiveRef = useRef(false)   // Sasha 273 · it was live when the page went to the background: resume it on return
  const listenRef = useRef<(() => void) | null>(null)
  const speechEndRef = useRef<number | null>(null)   // Sasha 275 · S1 measure: when the person's speech ended (the page's clock)
  // Sasha 274 · item 4: the browser's own answer for the microphone, known BEFORE a tap — so a tap that starts a conversation (New
  // chat, a chip) can start listening inside it, synchronously, when it is already granted (never a permission prompt from it)
  const permRef = useRef<string | null>(null)
  useEffect(() => {
    if (!strict) return
    let st: PermissionStatus | null = null
    navigator.permissions?.query({ name: 'microphone' as PermissionName }).then(p => { st = p; permRef.current = p.state; p.onchange = () => { permRef.current = p.state } }).catch(() => { permRef.current = null })
    return () => { if (st) st.onchange = null }
  }, [strict])   // Sasha 273 · "Tap to talk" on a connected mic that isn't hearing: resume it
  const droppedMutedRef = useRef(false)   // Sasha 213 · log the muted spell once, not per frame
  // Sasha 322 · THE ONE STATE MACHINE's inputs that aren't the pipeline's own objects, and its output
  const wantedRef = useRef(false)                       // a connect was asked for (a tap, autoStart) and not stopped
  const permStateRef = useRef<string | null>(null)      // the browser's permission answer, as last read
  const speakingRef = useRef(false)                     // her voice is playing (the mic paused)
  const thinkingRef = useRef(false)                     // a turn is in flight (the mic paused)
  const [state, setState] = useState<MicState>('off')
  const stateRef = useRef<MicState>('off')
  const onStateRef = useRef(onState)
  useEffect(() => { onStateRef.current = onState }, [onState])
  const recomputeRef = useRef<() => void>(() => {})
  const connectRef = useRef<() => void>(() => {})
  const flushRef = useRef<(() => void) | null>(null)   // sends what was buffered while the socket opened
  const levelRef = useRef<HTMLSpanElement | null>(null) // the live input-level bar (written from the frames, never re-rendered)
  const tapAtRef = useRef(0)                            // his tap: tap → Listening is measured from here
  const replyAtRef = useRef(0)                          // the speech service's last answer (any message) — it answers what it hears
  const sendFromRef = useRef(0)                         // when audio started (again) to leave for it — its answer is due from here
  const lastSentRef = useRef(0)
  useEffect(() => { speakingRef.current = !!speaking; recomputeRef.current() }, [speaking])
  useEffect(() => { thinkingRef.current = !!thinking; recomputeRef.current() }, [thinking])
  useEffect(() => {   // Sasha 322 · the key minted before any tap — never for a site the browser blocks (Sasha 266)
    let live = true
    try { preconnect('https://api.deepgram.com') } catch { /* a hint only */ }
    void fetch('/pcm-capture.js', { cache: 'force-cache' }).catch(() => {})   // the worklet's file in cache before the tap
    micPermission().then(perm => { if (!live) return; permStateRef.current = perm; if (perm !== 'denied') void prefetchKey() })
    return () => { live = false }
  }, [])
  const [isConnecting, setIsConnecting] = useState(false)
  const [isConnected, setIsConnected] = useState(false)   // the socket is open — NOT "on" (Sasha 266: that is `hearing`)
  // Sasha 266 · row 943 (a): the mic is "on" ONLY when it hears — a live, unmuted audio track delivering frames. The button's "on"
  // look, its "Listening" words and onConnectedChange(true) all come from here, never from an open socket.
  const [hearing, setHearing] = useState(false)
  const hearingRef = useRef(false)
  const connectT0 = useRef(0)
  const firstHeardRef = useRef(false)
  const [isSpeaking, setIsSpeaking] = useState(false)
  const [micError, setMicError] = useState<string | null>(null)
  // Mic device selection. On a Mac, Continuity silently hands the *iPhone's* mic to the browser
  // as the default input — so a guest whose phone isn't even nearby gets no audio. We enumerate
  // inputs, prefer a real local mic over any phone/Continuity device, and let the guest pick.
  const [audioDevices, setAudioDevices] = useState<MediaDeviceInfo[]>([])
  const [selectedMicId, setSelectedMicId] = useState<string>('')   // '' = auto (avoid-phone)
  const selectedMicIdRef = useRef<string>('')
  useEffect(() => { selectedMicIdRef.current = selectedMicId }, [selectedMicId])

  const wsRef = useRef<WebSocket | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const audioCtxRef = useRef<AudioContext | null>(null)
  const workletNodeRef = useRef<AudioWorkletNode | null>(null)
  const connectedRef = useRef(false)
  const transcriptRef = useRef('')
  // Start gated — worklet runs immediately but audio is suppressed until first AVATAR_SPEAK_ENDED
  // Sasha 264 · item 7 (Tyler's phone, /s2, 14 Oct): closed at the start ONLY when someone owns the gate (onSetGate: the call, /s2's
  // speaker) and will open it when she stops — /s2 had no owner, so an auto-started mic dropped every frame while it showed connected
  const micGatedRef = useRef(!!onSetGate)
  const gateOwnedRef = useRef(!!onSetGate)   // Sasha 322 · someone closes the gate while she talks (the call, /s2's speaker)
  const gateOpenedAtRef = useRef(0)  // when the mic last opened — bounds the echo window
  // Sasha 192 · THE WATCHDOG: listening never dies silently (live 7 Oct: 3 minutes deaf after Sasha's question)
  const heardAtRef = useRef(0)        // when speech started with no transcript yet
  const lastAliveRef = useRef(0)      // last transcript, or (re)connection
  const lastFrameRef = useRef(0)      // Sasha 264 · item 7: the last audio frame the mic delivered (0: none yet)
  const deafRef = useRef(false)       // Sasha 264 · item 7: the mic isn't reaching her, and the screen says so
  const gatedSinceRef = useRef(0)     // when the mic was last closed for Sasha speaking
  const connectingRef = useRef(false)  // Sasha 197 · a connect is in flight (permission, key, socket) — never start a second
  const hadConnectedRef = useRef(false) // Sasha 197 · the watchdog only REconnects a connection that was up
  const [notCaught, setNotCaught] = useState(false)
  const loudFramesRef = useRef(0)
  const keepAliveIntervalRef = useRef<any>(null)
  // Deepgram auto-reconnect state. The mic stream stays alive across reconnects; only
  // the WS + audio graph are rebuilt so a transient network drop doesn't kill voice.
  const manualStopRef = useRef(false)          // true = user/unmount stop → do NOT reconnect
  const dgReconnectTimerRef = useRef<any>(null)
  const dgReconnectAttemptsRef = useRef(0)
  const readyToListenRef = useRef(readyToListen)
  useEffect(() => { readyToListenRef.current = readyToListen }, [readyToListen])
  // Mirrored for the audio worklet's long-lived onmessage closure — see note above.
  const mutedRef = useRef(muted)
  useEffect(() => { mutedRef.current = muted; recomputeRef.current() }, [muted])
  // Refs so the long-lived Deepgram/worklet closures (created once in connect()) always
  // call the LATEST props. Without this, ws.onmessage captures the first onTranscript →
  // first sendMessage → a stale `messages` snapshot, so every voice turn sends the same
  // outdated conversation_history to the conductor and the avatar loses memory.
  const onInterruptRef = useRef(onInterrupt)
  useEffect(() => { onInterruptRef.current = onInterrupt }, [onInterrupt])
  const onTranscriptRef = useRef(onTranscript)
  useEffect(() => { onTranscriptRef.current = onTranscript }, [onTranscript])
  const onSpeakingChangeRef = useRef(onSpeakingChange)
  useEffect(() => { onSpeakingChangeRef.current = onSpeakingChange }, [onSpeakingChange])
  // Muting must also clear any in-flight "speaking" state. Otherwise the last value before the
  // mute landed sticks, and the page keeps rendering "Listening…" over a mic that is shut.
  useEffect(() => {
    if (!muted) return
    loudFramesRef.current = 0
    setIsSpeaking(false)
    onSpeakingChangeRef.current?.(false)
  }, [muted])
  const avatarSpeechGetterRef = useRef(avatarSpeechGetter)
  useEffect(() => { avatarSpeechGetterRef.current = avatarSpeechGetter }, [avatarSpeechGetter])
  const onConnectedChangeRef = useRef(onConnectedChange)
  useEffect(() => { onConnectedChangeRef.current = onConnectedChange }, [onConnectedChange])
  const onMicErrorRef = useRef(onMicError)
  useEffect(() => { onMicErrorRef.current = onMicError }, [onMicError])
  // Single place that records a mic failure: keeps the local composer line and the page-level
  // call panel in sync, so the error can never be visible in one and invisible in the other.
  // Sasha 320 · THE ONE TRUTH is the browser's answer AFTER HIS TAP on the mic: a mic started without a tap (autoStart, on load) may be
  // refused or suspended, and that is never said — nothing shows until he taps. Clearing a line always goes through.
  const tappedRef = useRef(false)
  const reportMicError = useCallback((m: string | null) => {
    if (m && !tappedRef.current) { micLog('held', { why: 'no tap yet — nothing said on the page', message: m }); return }
    setMicError(m)
    onMicErrorRef.current?.(m)
  }, [])
  const languageRef = useRef(language)
  useEffect(() => { languageRef.current = language }, [language])
  const connectTimeoutRef = useRef<any>(null)  // fails a hung connect so it never sticks
  // Sasha 246 item 2 · asleep: the mic off and kept off; resumeRef = it was on (or wanted) when she fell asleep
  const asleepRef = useRef(asleep)
  const resumeRef = useRef(false)
  const onWakeRef = useRef(onWake)
  useEffect(() => { onWakeRef.current = onWake }, [onWake])

  // Expose gate to parent on mount — gate is a pure ref flag, no audio pipeline changes
  useEffect(() => {
    onSetGate?.((value) => {
      console.log('[GATE] set to', value)
      micGatedRef.current = value
      gatedSinceRef.current = value ? Date.now() : 0
      heardAtRef.current = 0
      if (!value) {
        gateOpenedAtRef.current = Date.now()  // start the echo window
        transcriptRef.current = ''
        setIsSpeaking(false)
        // Flush Deepgram's buffer so avatar speech captured during gate-on is discarded
        if (wsRef.current?.readyState === WebSocket.OPEN) {
          wsRef.current.send(JSON.stringify({ type: 'Finalize' }))
        }
      } else {
        loudFramesRef.current = 0  // avatar just started — reset barge-in counter
      }
      recomputeRef.current()
    })
    console.log('[GATE] registered, present:', !!onSetGate)
  }, [])

  // Sasha 322 · THE ONE STATE MACHINE: a snapshot of the pipeline itself (permission, track, audio, socket, frames) and her phase → the
  // state drawn (lib/mic-machine.mjs). Recomputed on every pipeline event and on a 250 ms tick (a frame's age); never set on a timer.
  const snapshot = () => {
    const tr = streamRef.current?.getAudioTracks()[0]
    const ws = wsRef.current
    return {
      wanted: wantedRef.current, connecting: connectingRef.current, perm: permStateRef.current,
      track: tr ? tr.readyState : null, trackMuted: !!tr?.muted, audio: audioCtxRef.current?.state ?? null,
      socket: ws ? (ws.readyState === WebSocket.OPEN ? 'open' : ws.readyState === WebSocket.CONNECTING ? 'connecting' : 'closed') : null,
      lastFrameAt: lastFrameRef.current, now: Date.now(), gated: micGatedRef.current, muted: mutedRef.current, asleep: asleepRef.current,
      // her voice: the page says so (speaking), or the gate its owner closes while she talks is shut (a gated mic is her speaking)
      speaking: speakingRef.current || (gateOwnedRef.current && micGatedRef.current), thinking: thinkingRef.current, deaf: deafRef.current,
      lastReplyAt: ws && ws.readyState === WebSocket.OPEN && sendFromRef.current ? Math.max(replyAtRef.current, sendFromRef.current) : null,
      backlog: ws && ws.readyState === WebSocket.OPEN ? ws.bufferedAmount : 0,
    }
  }
  const recompute = useCallback(() => {
    const st = readMic(snapshot()) as MicState
    if (st === stateRef.current) return
    const from = stateRef.current
    stateRef.current = st; setState(st); onStateRef.current?.(st)
    const live = st === 'listening'
    if (live !== hearingRef.current) { hearingRef.current = live; setHearing(live); onConnectedChangeRef.current?.(live) }   // Sasha 266: "on" = hearing
    if (live) { connectingRef.current = false; setIsConnecting(false) }   // the connect is done when audio reaches her
    micLog('state', { state: st, why: from, ...(tapAtRef.current ? { ms: Date.now() - tapAtRef.current } : {}) })
    if (live && tapAtRef.current) { micLog('listening', { ms: Date.now() - tapAtRef.current }); tapAtRef.current = 0 }   // tap → Listening, reported
  // eslint-disable-next-line react-hooks/exhaustive-deps -- reads refs only
  }, [])
  useEffect(() => { recomputeRef.current = recompute })

  // the audio pipeline (stream, audio, worklet) — torn down only on a stop, a dead track or a new device; never for a dropped socket
  const teardownAudio = () => {
    try { workletNodeRef.current?.disconnect() } catch {}
    workletNodeRef.current = null; flushRef.current = null
    try { audioCtxRef.current?.close() } catch {}
    audioCtxRef.current = null
    if (streamRef.current) { streamRef.current.getTracks().forEach(t => t.stop()); streamRef.current = null }
  }
  const pipelineLive = () => {
    const tr = streamRef.current?.getAudioTracks()[0]
    return !!(tr && tr.readyState === 'live' && audioCtxRef.current && audioCtxRef.current.state !== 'closed' && workletNodeRef.current)
  }

  const stopAll = useCallback(() => {
    manualStopRef.current = true   // intentional stop — suppress auto-reconnect
    wantedRef.current = false
    clearTimeout(dgReconnectTimerRef.current)
    clearTimeout(connectTimeoutRef.current)
    clearInterval(keepAliveIntervalRef.current)
    if (wsRef.current) { wsRef.current.close(); wsRef.current = null }
    teardownAudio()
    setIsConnected(false)
    setIsSpeaking(false)
    setIsConnecting(false)
    connectedRef.current = false
    connectingRef.current = false
    transcriptRef.current = ''
    recompute()
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Sasha 273 · strict (/s2): the mic stops being "on" the moment it stops hearing — Sasha 322: the machine reads it (track, audio, frames)
  const notHearing = useCallback((why: string) => {
    micLog('not_hearing', { why })
    recomputeRef.current()
  }, [])

  // Sasha 322 · the frame handler, ONCE per pipeline: a frame goes to the socket when it is open — and while it is still opening, it is
  // KEPT (up to BUFFER_MS) and sent first on open, so words said during "Getting ready…" reach her (micLog 'flushed' {ms}).
  const wirePipeline = (ctx: AudioContext, stream: MediaStream) => {
    const source = ctx.createMediaStreamSource(stream)
    const node = new AudioWorkletNode(ctx, 'pcm-capture')
    const downsample = makeDownsampler(ctx.sampleRate)
    workletNodeRef.current = node
    const rate = sendRate(ctx.sampleRate)
    const pending: ArrayBuffer[] = []
    let pendingSamples = 0
    const pendingMax = Math.round(rate * BUFFER_MS / 1000)
    const toPcm = (float32: Float32Array): ArrayBuffer | null => {
      // Convert float32 to int16 PCM before sending — Sasha 215 (d): at 16 kHz (a third of the upload at 48 kHz)
      const pcm = downsample(float32)
      if (!pcm.length) return null
      const int16 = new Int16Array(pcm.length)
      for (let i = 0; i < pcm.length; i++) {
        const v = Math.max(-1, Math.min(1, pcm[i]))
        int16[i] = v < 0 ? v * 0x8000 : v * 0x7fff
      }
      return int16.buffer
    }
    const send = (float32: Float32Array) => {
      const buf = toPcm(float32)
      if (!buf) return
      const ws = wsRef.current
      if (ws && ws.readyState === WebSocket.OPEN) {
        const t = Date.now()
        if (t - lastSentRef.current > 500) sendFromRef.current = t   // sending (re)starts: the service's answer is due from now
        lastSentRef.current = t
        ws.send(buf); return
      }
      if (!wantedRef.current) return
      pending.push(buf); pendingSamples += buf.byteLength / 2
      while (pending.length > 1 && pendingSamples > pendingMax) pendingSamples -= pending.shift()!.byteLength / 2
    }
    flushRef.current = () => {
      const ws = wsRef.current
      if (!ws || ws.readyState !== WebSocket.OPEN || !pending.length) return
      const ms = Math.round(pendingSamples / rate * 1000)
      for (const b of pending.splice(0)) ws.send(b)
      pendingSamples = 0
      micLog('flushed', { ms })   // Sasha 322 · item 3: what he said while it got ready, used
    }
    // Sasha 265 · item 1 (the browser proof: "Book a table for two tonight" came back "A table for two tonight"): talking over
    // her, the frames that tripped barge-in were dropped with the rest — the first word lost every time. The last PREROLL_MS
    // while closed are kept and sent on a barge-in ONLY (never when she simply stops: that audio is her own voice).
    const preroll: Float32Array[] = []
    let prerollLen = 0
    const prerollMax = Math.round(ctx.sampleRate * PREROLL_MS / 1000)
    let level = 0, drawn = false
    node.port.onmessage = (e) => {
      const float32 = e.data as Float32Array
      lastFrameRef.current = Date.now()   // Sasha 264 · item 7: the mic is delivering
      const rms = Math.sqrt(float32.reduce((sum, x) => sum + x * x, 0) / float32.length)
      level = Math.max(rms, level * 0.85)   // Sasha 322 · the live input level: moves with his voice, drawn once a frame at most
      if (!drawn) { drawn = true; requestAnimationFrame(() => { drawn = false; const el = levelRef.current; if (el) el.style.transform = `scaleX(${Math.min(1, level * 8).toFixed(3)})` }) }
      if (stateRef.current !== 'listening') recomputeRef.current()   // Sasha 322 · frames (again): the machine says if audio reaches her
      if (deafRef.current) { deafRef.current = false; reportMicError(null); micLog('hearing', { after: 'deaf' }) }
      // HARD mute (itinerary build / any in-flight turn): drop every frame at the source,
      // before Deepgram and before barge-in. `muted` is documented as a hard mute, but the
      // frame loop only honoured the speak-gate — so a build whose classify was slow/failed
      // left the mic genuinely streaming under a "Not listening" label. Enforce it here so
      // the mic is truly deaf whenever muted, independent of the speak-gate's timing.
      if (mutedRef.current) { preroll.length = 0; prerollLen = 0; if (!droppedMutedRef.current) { droppedMutedRef.current = true; micLog('dropping', { why: 'muted while a turn runs' }) } return }
      if (droppedMutedRef.current) { droppedMutedRef.current = false; micLog('listening', { after: 'muted' }) }
      if (micGatedRef.current) {
        preroll.push(float32); prerollLen += float32.length
        while (prerollLen - preroll[0].length >= prerollMax) prerollLen -= preroll.shift()!.length
        // Gate ON = avatar is speaking. DROP every frame so the avatar's audio
        // bleeding into the mic is never streamed to Deepgram. This is the core
        // echo fix — Deepgram simply never hears the avatar.
        // A deliberate mute is not interruptible — barge-in only exists to cut off the
        // avatar mid-sentence, and during a build she isn't speaking.
        if (BARGE_IN_ENABLED && !mutedRef.current) {
          if (rms > BARGE_IN_RMS) {
            loudFramesRef.current += 1
            if (loudFramesRef.current >= BARGE_IN_FRAMES) {
              loudFramesRef.current = 0
              console.log('[BARGE-IN]', rms.toFixed(3), '> thr', BARGE_IN_RMS, '— interrupting avatar')
              micLog('barge_in', { rms: Number(rms.toFixed(3)) })
              onInterruptRef.current?.()
              micGatedRef.current = false  // open mic; gate setter fires async
              micLog('preroll', { ms: Math.round(prerollLen / ctx.sampleRate * 1000) })
              for (const f of preroll.splice(0)) send(f)   // Sasha 265 · item 1: the words that interrupted her, from their start
              prerollLen = 0
              recomputeRef.current()
            }
          } else {
            loudFramesRef.current = 0  // must be SUSTAINED — reset on any quiet frame
          }
        }
        return  // gated: never send avatar bleed to Deepgram
      }
      loudFramesRef.current = 0
      if (preroll.length) { preroll.length = 0; prerollLen = 0 }   // opened by her stopping: what was kept is her voice — dropped
      send(float32)
    }
    source.connect(node)
    // Keep the audio graph alive WITHOUT monitoring the mic to the speakers.
    // Routing the worklet straight to ctx.destination plays the user's mic out
    // loud, which adds a feedback path and muddies echo cancellation. Sink through
    // a zero-gain node instead.
    const sink = ctx.createGain()
    sink.gain.value = 0
    node.connect(sink)
    sink.connect(ctx.destination)
  }

  // Sasha 322 · THE SOCKET ALONE — opened at the tap beside the mic (never after it), and the only thing a reconnect rebuilds: the stream,
  // the running audio and the worklet stay, so a dropped socket never needs a new tap on a phone (1 Nov: every reconnect came back
  // "deaf, audio suspended until a tap") and the state is Connecting the moment it drops — never a stale Listening.
  const openSocket = (dgKey: string) => {
    const ctx = audioCtxRef.current
    if (!ctx || !dgKey || manualStopRef.current) return
    const cur = wsRef.current
    if (cur && (cur.readyState === WebSocket.OPEN || cur.readyState === WebSocket.CONNECTING)) return
    const dgLang = DG_LANG[languageRef.current || 'en'] || 'en-US'
    const ws = new WebSocket(
      `wss://api.deepgram.com/v1/listen?encoding=linear16&sample_rate=${sendRate(ctx.sampleRate)}&channels=1&model=nova-3&language=${dgLang}&smart_format=true&interim_results=true&endpointing=150&utterance_end_ms=1000&vad_events=true${KEYTERMS}`,
      ['token', dgKey]
    )
    wsRef.current = ws
    sendFromRef.current = 0; replyAtRef.current = 0
    recomputeRef.current()

    // Watchdog: if the socket doesn't open within 8s, close it so onclose can retry —
    // otherwise a rejected connection leaves the mic stuck on the "connecting" spinner.
    clearTimeout(connectTimeoutRef.current)
    connectTimeoutRef.current = setTimeout(() => {
      if (ws.readyState !== WebSocket.OPEN) {
        console.warn('[DG] connect watchdog — socket never opened, closing to retry')
        try { ws.close() } catch {}
      }
    }, 8000)

    // Dedup state for BUG 4 — scoped to this connection's lifetime
    let lastFinal = ''
    let lastFinalAt = 0
    // Turn-hold: Deepgram's endpointing (300ms) fires speech_final on any natural
    // mid-sentence pause, and firing immediately made Sasha answer half a sentence
    // ("I want to go to…" → she replies before "…Hanoi with my wife" arrives). Instead
    // of firing on speech_final, HOLD briefly; if the guest resumes (SpeechStarted or a
    // fresh interim), cancel the hold and keep accumulating — the fragments merge into
    // one turn. A transcript that already ends in terminal punctuation is very likely a
    // finished sentence, so it gets a short hold; a trailing/unpunctuated one waits longer.
    let pendingFire: any = null

    ws.onopen = () => {
      // Guard against StrictMode race: cleanup may have nulled wsRef while WS was connecting
      if (wsRef.current !== ws) {
        console.log('[DG] onopen: WS superseded by cleanup, discarding')
        ws.close()
        return
      }
      console.log('[DG] connected')
      micLog('socket_open', { ms: Date.now() - connectT0.current })
      clearTimeout(connectTimeoutRef.current)
      setIsConnected(true)   // Sasha 266: open — "on" only once it hears (the machine, from the frames)
      connectedRef.current = true; lastAliveRef.current = Date.now()   // Sasha 192
      hadConnectedRef.current = true    // Sasha 197
      dgReconnectAttemptsRef.current = 0   // healthy connection — reset backoff
      if (!deafRef.current) reportMicError(null)   // Sasha 215 · open again: the error goes — Sasha 266: never "can't hear you" while still deaf

      // KeepAlive runs for the lifetime of the session — not gated, always on
      keepAliveIntervalRef.current = setInterval(() => {
        if (wsRef.current?.readyState === WebSocket.OPEN) {
          wsRef.current.send(JSON.stringify({ type: 'KeepAlive' }))
        }
      }, 8000)
      flushRef.current?.()   // Sasha 322 · what he said while it got ready, sent first
      recomputeRef.current()
    }

    ws.onmessage = (event) => {
      replyAtRef.current = Date.now()   // Sasha 322 · the service answered: audio is reaching it
      if (micGatedRef.current) return
      try {
        const data = JSON.parse(event.data)
        if (data.type === 'SpeechStarted') {
          micLog('speech_start')
          if (!heardAtRef.current) heardAtRef.current = Date.now()   // Sasha 192 · the watchdog's clock
          clearTimeout(pendingFire)   // guest resumed — this turn isn't over
          setIsSpeaking(true)
          onSpeakingChangeRef.current?.(true)
        }

        const isEcho = (text: string): boolean => {
          // Only acoustic bleed (which arrives right after the avatar goes quiet) is
          // echo. After the window, identical words are the user genuinely answering.
          if (Date.now() - gateOpenedAtRef.current > ECHO_WINDOW_MS) return false
          const tWords = normalizeText(text)
          if (tWords.length < ECHO_MIN_WORDS) return false  // never drop short genuine replies
          const bWords = new Set(normalizeText(avatarSpeechGetterRef.current?.() ?? ''))
          if (tWords.length > 0 && bWords.size > 0) {
            const overlap = tWords.filter(w => bWords.has(w)).length / tWords.length
            if (overlap >= 0.6) {
              console.log('[ECHO] discarded (within echo window):', text)
              micLog('dropped', { why: 'echo of her own words', text })
              return true
            }
          }
          return false
        }

        const fireTranscript = (final: string) => {
          setIsSpeaking(false)
          onSpeakingChangeRef.current?.(false)
          if (final === lastFinal && Date.now() - lastFinalAt < 5000) { micLog('dropped', { why: 'repeat within 5 s', text: final }); return }
          lastFinal = final
          lastFinalAt = Date.now()
          if (isEcho(final)) return
          heardAtRef.current = 0; lastAliveRef.current = Date.now(); setNotCaught(false)   // Sasha 192 · heard: the watchdog rests
          micLog('submitted', { text: final })
          if (!firstHeardRef.current) { firstHeardRef.current = true; micLog('first_transcript', { ms: Date.now() - connectT0.current }) }   // Sasha 267 · reported (no words)
          onTranscriptRef.current?.(final)
        }

        const scheduleFire = () => {
          clearTimeout(pendingFire)
          // Hold graded by how finished the utterance is: question/directive/short
          // answer → fast; declarative narration → breathing room; fragment → longest.
          const hold = holdFor(transcriptRef.current)
          pendingFire = setTimeout(() => {
            if (transcriptRef.current.length >= 3) {
              const final = transcriptRef.current
              transcriptRef.current = ''
              fireTranscript(final)
            }
          }, hold)
        }

        if (data.type === 'Results') {
          const fragment = data.channel?.alternatives?.[0]?.transcript || ''
          if (fragment) micLog(data.is_final ? 'final' : 'partial', { text: fragment, speech_final: !!data.speech_final })
          // Sasha 214 · words are arriving, so Deepgram is alive: the watchdog's "speech with no transcript" clock rests.
          // It ran from the first SpeechStarted until a SUBMIT, so a guest who kept talking through the declarative hold
          // (two statements 2.5 s apart) tripped the 8 s restart on a healthy socket and lost the held words (B3 harness).
          if (fragment) heardAtRef.current = 0
          if (data.is_final === true) {
            // Accumulate is_final fragments; the hold below decides when the turn is over.
            if (fragment) {
              transcriptRef.current = transcriptRef.current
                ? `${transcriptRef.current} ${fragment}`
                : fragment
            }
            if (data.speech_final === true && transcriptRef.current.length >= 3) {
              speechEndRef.current = Date.now()   // Sasha 275
              scheduleFire()
            }
          } else if (fragment) {
            // A non-empty interim means the guest is mid-word again — not done.
            clearTimeout(pendingFire)
          }
        }
        // UtteranceEnd fallback — fires if speech_final never came
        if (data.type === 'UtteranceEnd') micLog('utterance_end', { pending: transcriptRef.current.length })
        if (data.type === 'UtteranceEnd' && transcriptRef.current.length >= 3) {
          speechEndRef.current = speechEndRef.current && Date.now() - speechEndRef.current < 3000 ? speechEndRef.current : Date.now()   // Sasha 275
          scheduleFire()
        }
      } catch(e) {}
    }

    ws.onerror = () => {
      // A WebSocket error Event carries NO detail — it always serialises to {}. The real
      // diagnostic is the close code, logged in onclose (which also handles reconnect).
      console.warn('[DG] socket error (readyState', ws.readyState, ') — reconnect handled on close')
    }
    ws.onclose = (e) => {
      clearTimeout(pendingFire)
      console.log('[DG] closed:', e.code, e.reason)
      micLog('socket_close', { code: e.code, reason: e.reason })
      if (wsRef.current !== ws) return  // superseded socket — ignore
      wsRef.current = null
      clearTimeout(connectTimeoutRef.current)
      clearInterval(keepAliveIntervalRef.current)
      connectedRef.current = false
      setIsConnected(false)
      setIsSpeaking(false)
      if (e.code === 1008 || e.code === 4001 || e.code === 4003) dropKey()   // a refused key: the next socket gets a fresh one
      // Auto-reconnect on an UNEXPECTED drop (network blip, server reap) — but not
      // after a user/unmount stop, and only while we still want to be listening.
      if (manualStopRef.current || !readyToListenRef.current) { connectingRef.current = false; setIsConnecting(false); recomputeRef.current(); return }
      connectingRef.current = true; setIsConnecting(true)
      recomputeRef.current()   // Sasha 322 · item 4: Connecting at once — never a stale Listening
      const attempt = (dgReconnectAttemptsRef.current = Math.min(dgReconnectAttemptsRef.current + 1, 6))
      // Sasha 215 · reconnecting again and again without ever opening is a dead mic: shown and said, not retried in silence
      if (attempt >= RECONNECTS_BEFORE_SAYING) reportMicError('Voice service unavailable')
      const backoff = Math.min(250 * 2 ** (attempt - 1), 8000)  // 0.25s → 8s cap
      console.log(`[DG] unexpected close — reconnecting in ${backoff}ms (attempt ${attempt})`)
      clearTimeout(dgReconnectTimerRef.current)
      dgReconnectTimerRef.current = setTimeout(() => {
        if (manualStopRef.current || !readyToListenRef.current) return
        if (pipelineLive()) {   // Sasha 322 · the socket alone: the audio is still running (no new tap needed)
          void prefetchKey().then(k => { if (k) openSocket(k); else { connectingRef.current = false; reportMicError('Voice service unavailable'); recomputeRef.current() } })
        } else { connectingRef.current = false; connectRef.current() }   // the pipeline died too (a dead track): rebuilt whole
      }, backoff)
    }
  }

  const connect = useCallback(async () => {
    if (asleepRef.current) { resumeRef.current = true; micLog('asleep', { connect: 'deferred until she wakes' }); return }   // Sasha 246 · asleep: never listening
    if (connectedRef.current || connectingRef.current) return
    connectingRef.current = true
    wantedRef.current = true
    manualStopRef.current = false  // a fresh connect attempt re-enables reconnect
    console.log('[DG] connecting...')
    micLog('connect')
    if (!dgReconnectAttemptsRef.current) reportMicError(null)   // Sasha 215 · a reconnect keeps the error on screen until it opens
    setIsConnecting(true)
    connectT0.current = Date.now()
    // Sasha 265 · item 1 (Tyler's iPhone 14:21Z, his Mac Chrome 14:46Z: a key minted, NO socket ever reached Deepgram): the audio was
    // made AFTER the mic permission and the key, and its resume() was waited on for good — a phone (or Chrome with no tap yet)
    // never resumes audio outside a tap, so the socket was never opened and 264's "can't hear you" line, after that await, never ran.
    // Made and resumed HERE, before the first await — inside the tap when a tap started it — and never waited on (RESUME_WAIT_MS).
    holdPlayAndRecord('the mic')   // Sasha 267 · before any mic request: "playback" makes iOS refuse capture (InvalidStateError)
    if (pipelineLive()) {   // Sasha 322 · the pipeline is up (a socket dropped): the socket alone
      if (audioCtxRef.current && audioCtxRef.current.state !== 'running') audioCtxRef.current.resume().catch(() => {})
      recompute()
      void prefetchKey().then(k => { if (k) openSocket(k); else { connectingRef.current = false; setIsConnecting(false); reportMicError('Voice service unavailable'); recompute() } })
      return
    }
    teardownAudio()   // the pieces of a pipeline that died
    const ctx = new AudioContext()
    audioCtxRef.current = ctx
    const resumed = ctx.resume().catch(() => {})
    const workletReady = ctx.audioWorklet.addModule('/pcm-capture.js')   // Sasha 322 · loaded beside the mic, not after the socket
    workletReady.catch(() => {})
    const dropCtx = () => { if (audioCtxRef.current === ctx) audioCtxRef.current = null; ctx.close().catch(() => {}) }
    recompute()
    try {
      // Sasha 266 · row 943 (a): his iPhone minted 16 keys and never asked for the mic. The browser's own answer first — a site the
      // browser blocks is said at once, with the steps to allow it (never a key, never a silent retry, never "on")
      const perm = await micPermission()
      permStateRef.current = perm
      micLog('permission_state', { perm, state: audioSessionType() || 'none (not iOS Safari)' })
      if (perm === 'denied') {
        connectingRef.current = false; setIsConnecting(false); dropCtx()
        micLog('blocked', { perm, why: 'the browser blocks the microphone for this site' })
        reportMicError(BLOCKED)
        recompute()
        return
      }
      // Sasha 322 · the key was minted on mount (prefetchKey): ready now — and the socket opens BESIDE the mic, not after it
      const keyPromise = prefetchKey()
      void keyPromise.then(k => { if (k && audioCtxRef.current === ctx && !manualStopRef.current) openSocket(k) })
      const baseAudio: MediaTrackConstraints = { echoCancellation: true, noiseSuppression: true, autoGainControl: true }
      // Resolve the device BEFORE opening anything. Once mic permission was granted in a
      // prior session, enumerateDevices() exposes labels without an active stream — so we
      // can open the preferred LOCAL mic directly instead of opening the OS default first.
      // On a Mac with Continuity that default is the guest's iPhone: the phone visibly
      // "connects" on every session start even though we swap away afterwards, and if it
      // sleeps or leaves the room the session goes deaf. `exact` (not `ideal`) so the
      // browser can't silently fall back to the phone; a stale/unplugged id throws and the
      // catch below retries with defaults.
      let wantId = selectedMicIdRef.current
      if (!wantId) {
        try { wantId = preferredAudioDeviceId(await navigator.mediaDevices.enumerateDevices(), '') } catch {}
      }
      let stream: MediaStream
      try {
        stream = await navigator.mediaDevices.getUserMedia({
          audio: wantId ? { ...baseAudio, deviceId: { exact: wantId } } : baseAudio,
        })
      } catch (e: any) {
        // A pinned mic that is unplugged, already claimed by another app (Windows commonly
        // reports NotReadableError / "Device Occupied"), or whose constraints can't be met would
        // otherwise leave the guest with no voice at all. Retry once with no device constraint
        // and no processing flags — any working mic beats a silent session.
        if (e?.name === 'NotAllowedError') throw e   // permission is not something to retry around
        console.warn('[MIC] preferred device failed (' + e?.name + '), retrying with defaults')
        stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      }
      // Device labels are only readable AFTER permission is granted, so enumerate now. If the
      // guest hasn't pinned a mic and the browser handed us a phone/Continuity input, swap to a
      // real local mic before wiring the pipeline — this is the "it's still using my iPhone" fix,
      // so audio doesn't die when the phone isn't nearby. Best-effort: never block voice over it.
      try {
        const list = await navigator.mediaDevices.enumerateDevices()
        setAudioDevices(list.filter(d => d.kind === 'audioinput'))
        if (!selectedMicIdRef.current) {
          const activeLabel = stream.getAudioTracks()[0]?.label || ''
          if (PHONE_MIC_RE.test(activeLabel)) {
            const better = preferredAudioDeviceId(list, '')
            if (better) {
              stream.getTracks().forEach(t => t.stop())
              stream = await navigator.mediaDevices.getUserMedia({ audio: { ...baseAudio, deviceId: { ideal: better } } })
              console.log('[MIC] avoided phone/Continuity input, switched to a local mic')
            }
          }
        }
      } catch { /* enumerate/re-acquire is best-effort */ }
      streamRef.current = stream
      permStateRef.current = 'granted'
      micLog('permission', { granted: true, device: stream.getAudioTracks()[0]?.label || '' })
      // Mid-session mic death (the "froze at minute N" failure): a Continuity iPhone that
      // sleeps, locks, or walks out of range kills its audio track SILENTLY — no WS close,
      // no error, the guest just stops being heard and the demo looks frozen. A dead track ends the PIPELINE (Sasha 322: the
      // socket alone can't fix it): torn down, and the socket's close rebuilds it whole on a healthy local mic. Our own teardown calls
      // track.stop(), which does NOT fire onended, so this cannot loop. A mute must be SUSTAINED to count — brief mutes happen on
      // audio-route changes and self-recover.
      {
        const track = stream.getAudioTracks()[0]
        if (track) {
          let muteTimer: any = null
          const dead = (why: string) => {
            if (streamRef.current !== stream || manualStopRef.current) return
            console.warn(`[MIC] input track ${why} (${track.label || 'unknown device'}) — recycling connection`)
            reportMicError('Microphone disconnected — reconnecting')
            teardownAudio()
            if (wsRef.current) { try { wsRef.current.close() } catch {} } else { connectingRef.current = false; connectRef.current() }
            recompute()
          }
          track.onended = () => { notHearing('the track ended'); dead('ended') }
          track.onmute = () => { notHearing('the track was muted'); clearTimeout(muteTimer); muteTimer = setTimeout(() => dead('stayed muted'), 4000) }
          track.onunmute = () => { clearTimeout(muteTimer); recompute() }
        }
      }
      const dgKey = await keyPromise
      if (asleepRef.current) {   // Sasha 246 · fell asleep while the mic was opening: close it, listen again only when she wakes
        connectingRef.current = false; setIsConnecting(false); resumeRef.current = true
        if (wsRef.current) { try { wsRef.current.close() } catch {} wsRef.current = null }
        teardownAudio(); recompute()
        return
      }
      if (!dgKey) { connectingRef.current = false; setIsConnecting(false); reportMicError('Voice service unavailable'); teardownAudio(); recompute(); return }

      await Promise.race([resumed, new Promise(r => setTimeout(r, RESUME_WAIT_MS))])   // Sasha 265 · item 1: looked at, never waited for
      micLog('audiocontext', { state: ctx.state, sampleRate: ctx.sampleRate })
      // Sasha 264 · item 7: a phone only lets the mic's audio run from a tap — started without one (autoStart), it stays suspended and
      // no frame ever comes. Never "Listening" then: the screen says to tap, and the tap (toggleListening) turns it on.
      if (ctx.state !== 'running') { deafRef.current = true; reportMicError(DEAF_TAP); micLog('deaf', { why: 'audio suspended until a tap' }) }
      ctx.onstatechange = () => { micLog('audiocontext', { state: ctx.state }); if (ctx.state !== 'running') notHearing('audio ' + ctx.state); else recompute() }   // iOS suspends it when the page loses audio focus · 273: then never "on"
      console.log('[DG] AudioContext sampleRate:', ctx.sampleRate)
      await workletReady
      wirePipeline(ctx, stream)
      micLog('worklet', { ms: Date.now() - connectT0.current })
      openSocket(dgKey)   // opened already beside the mic (this is a no-op then)
      flushRef.current?.()
      recompute()

    } catch (err: any) {
      connectingRef.current = false
      setIsConnecting(false)
      teardownAudio()
      if (wsRef.current) { try { wsRef.current.close() } catch {} wsRef.current = null }
      recompute()
      // Name the actual failure. "Could not access microphone" sent people hunting for a
      // permission problem when the real cause was another app holding the device.
      micLog('error', { name: err?.name, message: String(err?.message || '').slice(0, 120) })
      if (err.name === 'InvalidStateError') reportMicError(AUDIO_MODE)   // Sasha 267 · iOS kept the page play-only: said, never "on"
      else if (err.name === 'NotAllowedError') { micLog('blocked', { name: err.name, why: 'the request was refused' }); reportMicError(BLOCKED) }   // Sasha 266 · + its steps on the page
      else if (err.name === 'NotFoundError') reportMicError('No microphone found')
      else if (err.name === 'NotReadableError') reportMicError('Mic is in use by another app')
      else if (err.name === 'OverconstrainedError') reportMicError('Selected mic is unavailable')
      else reportMicError(err.message || 'Could not access microphone')
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])  // stable — all dynamic props are read via refs above
  useEffect(() => { connectRef.current = connect })

  // Sasha 246 item 2 · fall asleep: everything stops (the stream's tracks, the socket, the reconnect timers; stopAll marks it a
  // manual stop, so neither the watchdog nor onclose reconnects). Wake: the mic comes back only if it was on or wanted.
  useEffect(() => {
    if (asleep) {
      if (connectedRef.current || connectingRef.current) resumeRef.current = true
      asleepRef.current = true   // from here no connect starts; the teardown runs in the same tick, after this effect
      queueMicrotask(() => { if (!asleepRef.current) return; stopAll(); connectingRef.current = false; micLog('asleep', { resume: resumeRef.current }) })
    } else if (asleepRef.current) {
      asleepRef.current = false
      micLog('awake', { resume: resumeRef.current })
      if (resumeRef.current) { resumeRef.current = false; connect() }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- stopAll and connect are stable
  }, [asleep])

  useEffect(() => {
    const t = setInterval(() => {
      const now = Date.now()
      recomputeRef.current()   // Sasha 322 · a frame's age is a pipeline fact: the machine re-reads it
      // Sasha 322 · item 4: a socket the browser still calls open that takes audio and answers nothing for 2× REPLY_MS is dead — closed, so
      // onclose brings it back (the screen already left Listening at REPLY_MS: the machine reads the same fact)
      const ws0 = wsRef.current
      if (ws0 && ws0.readyState === WebSocket.OPEN && sendFromRef.current && now - lastSentRef.current < 1000 &&
          now - Math.max(replyAtRef.current, sendFromRef.current) > 2 * REPLY_MS) {
        micLog('socket_silent', { ms: now - Math.max(replyAtRef.current, sendFromRef.current) })
        sendFromRef.current = 0; try { ws0.close() } catch { /* onclose reconnects */ }
      }
      // a gate closed from the start (before her greeting) gets a clock too, so rule 1 covers the first turn
      if (micGatedRef.current && !gatedSinceRef.current && connectedRef.current) gatedSinceRef.current = now
      // Sasha 197 · the decision is lib/voice-watchdog.mjs (held by scripts/check-voice-watchdog.mjs at build).
      // 192 connected whenever "not connected and no socket" — true for the whole of a first connect (mic permission,
      // key, socket), so after the greeting it kept starting new connects over the one about to open: the mic never came on.
      // Sasha 264 · item 7: connected, open and not paused, yet no frame from the mic for DEAF_AFTER_MS → it isn't reaching her: said
      if (connectedRef.current && !mutedRef.current && !asleepRef.current && !deafRef.current && streamRef.current &&
          now - Math.max(lastFrameRef.current, lastAliveRef.current) > DEAF_AFTER_MS) {
        deafRef.current = true; connectingRef.current = false; setIsConnecting(false); reportMicError(DEAF_TAP); micLog('deaf', { why: 'no audio from the mic', ms: now - lastFrameRef.current })
        recomputeRef.current()   // Sasha 266 / 322 · no audio reaching her: never "Listening"
      }
      const act = watchdogAction({
        now, manualStop: manualStopRef.current, ready: readyToListenRef.current, muted: mutedRef.current,
        connected: connectedRef.current, connecting: connectingRef.current, hadConnected: hadConnectedRef.current,
        wsOpen: !!wsRef.current, lastAlive: lastAliveRef.current, gated: micGatedRef.current,
        gatedSince: gatedSinceRef.current, heardAt: heardAtRef.current,
      })
      if (act === 'rearm') {
        console.warn('[WATCHDOG] mic closed 45 s — re-arming')
        micGatedRef.current = false; gatedSinceRef.current = 0; gateOpenedAtRef.current = now
      } else if (act === 'restart') {
        console.warn('[WATCHDOG] speech with no transcript for 8 s — restarting the stream')
        heardAtRef.current = 0
        setNotCaught(true); setTimeout(() => setNotCaught(false), 6000)
        try { wsRef.current?.close() } catch { /* onclose reconnects */ }
      } else if (act === 'reconnect') {
        console.warn('[WATCHDOG] connection lost and not retrying — reconnecting')
        lastAliveRef.current = now
        connect()
      }
    }, 250)   // Sasha 322 · the machine re-reads a frame's age 4× a second (the watchdog's own clocks are its own)
    return () => clearInterval(t)
  }, [connect, notHearing])

  const toggleListening = () => {
    tappedRef.current = true   // Sasha 320 · from now on the browser's answer is his to hear
    if (!connectedRef.current && !tapAtRef.current) { tapAtRef.current = Date.now(); micLog('tap') }   // Sasha 322 · tap → Listening, measured (once)
    if (asleepRef.current) {   // Sasha 246 · pressing the mic wakes her — and she listens
      asleepRef.current = false; resumeRef.current = false
      onWakeRef.current?.()
    }
    if (connectedRef.current && deafRef.current) {   // Sasha 264 · item 7: the tap a phone needs — the same mic turned on, not off
      audioCtxRef.current?.resume().then(() => micLog('audiocontext', { state: audioCtxRef.current?.state, by: 'tap' })).catch(() => {})
      micGatedRef.current = false; gateOpenedAtRef.current = Date.now()
      deafRef.current = false; reportMicError(null); recomputeRef.current()
      return
    }
    if (connectedRef.current && strictRef.current && !hearingRef.current) { listenRef.current?.(); return }   // Sasha 273 · "Tap to talk": resume, never off
    if (connectedRef.current) { stopAll(); return }
    // Sasha 171 · a CLICK on the mic is the guest asking to talk: the gate opens now. It started closed "until the avatar
    // finishes speaking" — in the text box, with no call, the avatar never speaks, so nothing said ever reached Deepgram
    // (live: "the 🎙 in the text box does not accept"). The call's own gate (onSetGate) still closes it while she talks.
    micGatedRef.current = false
    gateOpenedAtRef.current = Date.now()
    console.log('[GATE] opened by a click on the mic')
    connect()
  }

  // Sasha 273 · item 3 · the page's one return handler and its "Tap to talk" (/s2, strict). resume: on return from the background,
  // what the browser allows WITHOUT a tap — the audio resumed, or a mic whose track the background ended opened again — and only for a
  // mic that was live when the page left. Whatever the browser refuses stays honestly "Tap to talk". tap: inside a tap — listen now.
  const resumeMic = () => {
    if (asleepRef.current || !wasLiveRef.current) return
    const tr = streamRef.current?.getAudioTracks()[0]
    const ctx = audioCtxRef.current
    micLog('return', { state: ctx?.state || 'none', why: tr ? tr.readyState : 'no track' })
    if (connectedRef.current && (!tr || tr.readyState === 'ended')) { stopAll(); manualStopRef.current = false; connect(); return }
    if (connectedRef.current && ctx && ctx.state !== 'running') { ctx.resume().then(() => micLog('audiocontext', { state: ctx.state, by: 'return' })).catch(() => {}); return }
    if (!connectedRef.current && !connectingRef.current) connect()
  }
  const listenNow = () => {
    if (stateRef.current !== 'listening') { tapAtRef.current = Date.now(); micLog('tap') }   // Sasha 322 · tap / New chat → Listening, measured
    if (asleepRef.current || !connectedRef.current) { toggleListening(); return }   // asleep: wakes her and listens · off: starts it
    const tr = streamRef.current?.getAudioTracks()[0]
    if (!tr || tr.readyState === 'ended') { stopAll(); manualStopRef.current = false; micGatedRef.current = false; gateOpenedAtRef.current = Date.now(); connect(); return }
    audioCtxRef.current?.resume().then(() => micLog('audiocontext', { state: audioCtxRef.current?.state, by: 'tap' })).catch(() => {})   // inside the tap
    micGatedRef.current = false; gateOpenedAtRef.current = Date.now()
    if (deafRef.current) { deafRef.current = false; reportMicError(null) }
    recomputeRef.current()
  }
  useEffect(() => {
    if (!ctlRef) return
    ctlRef.current = { resume: resumeMic, tap: listenNow, granted: () => permRef.current === 'granted', speechEndAt: () => speechEndRef.current }
    return () => { ctlRef.current = null }
  })
  useEffect(() => { listenRef.current = listenNow })
  useEffect(() => {   // Sasha 273 · was it live as the page went to the background? (only that is resumed on return)
    if (!strict) return
    const seen = () => { if (document.visibilityState === 'hidden') wasLiveRef.current = hearingRef.current || connectedRef.current }
    document.addEventListener('visibilitychange', seen)
    return () => document.removeEventListener('visibilitychange', seen)
  }, [strict])

  useEffect(() => {
    console.log('[DG] readyToListen:', readyToListen, 'autoStart:', autoStart, 'disabled:', disabled)
    if (autoStart && readyToListen && !disabled) connect()
  }, [readyToListen])

  useEffect(() => {
    return () => stopAll()
  }, [])

  // Load the guest's saved mic and keep the device list fresh — plugging in a headset mid-call
  // should show up in the picker. Before permission, labels are blank; connect() re-enumerates
  // with real labels once the mic is granted, which is what drives the avoid-phone logic.
  useEffect(() => {
    try { const s = localStorage.getItem(MIC_PREF_KEY) || ''; if (s) { setSelectedMicId(s); selectedMicIdRef.current = s } } catch {}
    const refresh = () => navigator.mediaDevices?.enumerateDevices?.()
      .then(list => setAudioDevices(list.filter(d => d.kind === 'audioinput')))
      .catch(() => {})
    refresh()
    navigator.mediaDevices?.addEventListener?.('devicechange', refresh)
    return () => navigator.mediaDevices?.removeEventListener?.('devicechange', refresh)
  }, [])

  // Guest picked a mic (or cleared to Auto): remember it and re-open the pipeline on the new
  // device. stopAll → connect is the same teardown/rebuild a reconnect already uses, so it's safe.
  const switchMic = useCallback((id: string) => {
    setSelectedMicId(id)
    selectedMicIdRef.current = id
    try { id ? localStorage.setItem(MIC_PREF_KEY, id) : localStorage.removeItem(MIC_PREF_KEY) } catch {}
    const wasConnected = connectedRef.current
    stopAll()
    if (wasConnected) setTimeout(() => { connect() }, 150)
  }, [connect, stopAll])

  // Only worth showing once there's a real choice AND labels have loaded (pre-permission the
  // labels are blank and a picker of "Microphone 1/2" helps no one).
  const namedDevices = audioDevices.filter(d => d.deviceId && d.label)
  const showMicPicker = namedDevices.length > 1

  // Publish the picker upward so the page can render it as a call-panel pill. Routed through a
  // ref (same idiom as onMicErrorRef) so a parent that re-creates the callback each render can
  // never turn this into a render loop. Reports null when there's nothing worth choosing, which
  // is what makes the pill appear only once a real second mic exists.
  const onMicDevicesRef = useRef(onMicDevices)
  useEffect(() => { onMicDevicesRef.current = onMicDevices }, [onMicDevices])
  useEffect(() => {
    onMicDevicesRef.current?.(
      showMicPicker
        ? {
            devices: namedDevices.map(d => ({ deviceId: d.deviceId, label: d.label, isPhone: PHONE_MIC_RE.test(d.label) })),
            selectedId: selectedMicId,
            switchMic,
          }
        : null,
    )
    // Unmount (e.g. session end) must clear the pill, or it lingers pointing at a dead switcher.
    return () => onMicDevicesRef.current?.(null)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [showMicPicker, selectedMicId, switchMic, audioDevices])

  // Sasha 322 · what the mic SAYS and SHOWS is the machine's state (lib/mic-machine.mjs), on every page: off · connecting · listening ·
  // thinking · speaking — an error the browser gave after his tap first (Sasha 320), asleep, then the state's own words
  const stateWords = micError || (asleep ? 'Asleep — not listening' : notCaught ? 'I didn’t catch that — say it again' : MIC_WORDS[state])
  const look = asleep ? 'bg-white/10 opacity-60'
    : state === 'listening' ? `bg-emerald-600${isSpeaking ? ' scale-110' : ''}`
    : state === 'connecting' ? 'bg-yellow-500'
    : state === 'speaking' ? 'bg-amber-500/80'
    : state === 'thinking' ? 'bg-white/10 opacity-70'
    : 'bg-indigo-600 hover:bg-indigo-700'
  return (
    <div className="flex flex-col items-center gap-1" data-mic-state={state}>
      <button
        onClick={toggleListening}
        disabled={disabled}
        aria-label={stateWords} title={stateWords} data-mic-state={state}
        className={`w-10 h-10 rounded-full flex items-center justify-center flex-shrink-0 transition-all ${look} disabled:opacity-40`}
      >
        {asleep ? <MicOff className="w-4 h-4 text-white/50" />
          : state === 'connecting' ? <Loader2 className="w-4 h-4 text-white animate-spin" />
          : state === 'thinking' || state === 'speaking' ? <MicOff className="w-4 h-4 text-white/70" />   /* the mic paused while she answers */
          : <Mic className="w-4 h-4 text-white" />}
      </button>
      {/* Sasha 322 · the live input level: moves with his voice — drawn only while Listening (audio reaching her) */}
      <span aria-hidden="true" data-mic-meter style={{ display: 'block', width: 36, height: 3, borderRadius: 2, overflow: 'hidden', background: 'rgba(52,211,153,.25)', visibility: state === 'listening' ? 'visible' : 'hidden' }}>
        <span ref={levelRef} style={{ display: 'block', height: '100%', background: '#34d399', transformOrigin: 'left center', transform: 'scaleX(0)', transition: 'transform 60ms linear' }} />
      </span>
      {!quiet && <p className={`text-xs text-center max-w-[200px] ${micError ? 'text-red-400' : state === 'listening' ? 'text-emerald-400' : 'text-white/60'}`}>{stateWords}</p>}
      {/* The mic picker is deliberately NOT rendered here. It is published upward via
          onMicDevices and drawn by the page as a pill beside the camera toggle, where the rest
          of the call controls live. */}
    </div>
  )
}
