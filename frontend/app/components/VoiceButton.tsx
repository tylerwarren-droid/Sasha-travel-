'use client'
import { useState, useRef, useEffect, useCallback } from 'react'
import { Mic, MicOff, Loader2 } from 'lucide-react'
import { apiUrl, apiHeaders } from '@/lib/api'

interface VoiceButtonProps {
  onTranscript: (text: string) => void
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
}

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
const PUBLIC_DEEPGRAM_KEY = process.env.NEXT_PUBLIC_DEEPGRAM_API_KEY || ''

// Ask the backend for an ephemeral STT key; fall back to the public env key if the proxy
// isn't configured (501) or is unreachable, so local dev keeps working.
async function getDeepgramKey(): Promise<string> {
  try {
    const res = await fetch(apiUrl('/api/voice/deepgram-key'), { method: 'POST', headers: apiHeaders() })
    if (res.ok) {
      const data = await res.json()
      if (data?.key) return data.key as string
    }
  } catch { /* fall through to public key */ }
  return PUBLIC_DEEPGRAM_KEY
}

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
// Raised for a loud investor-demo room: a busy hall (applause, nearby speakers, laughter)
// can push AEC residual past a low threshold and cut Sasha off mid-sentence. 0.12 sits above
// room bleed but below close-talking user speech (~0.15–0.3 RMS). Lower toward 0.08 for a
// quiet 1:1 setting where easy interruption matters more than false-trigger safety.
const BARGE_IN_RMS = 0.12
const BARGE_IN_FRAMES = 40           // ~100ms sustained — rejects transient residual spikes
// Echo (avatar audio bleeding into the mic) only arrives in the brief tail right after
// the avatar goes quiet. Beyond this window, identical words are the USER genuinely
// answering (e.g. repeating the avatar's options like "mix of everything") — never
// discard those, or the avatar appears to "stop hearing" the user.
const ECHO_WINDOW_MS = 1000
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

export default function VoiceButton({ onTranscript, muted = false, disabled, autoStart = false, readyToListen = false, onSpeakingChange, onInterrupt, onSetGate, avatarSpeechGetter, language = 'en', onConnectedChange, onMicError, onMicDevices }: VoiceButtonProps) {
  const [isConnecting, setIsConnecting] = useState(false)
  const [isConnected, setIsConnected] = useState(false)
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
  const micGatedRef = useRef(true)
  const gateOpenedAtRef = useRef(0)  // when the mic last opened — bounds the echo window
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
  useEffect(() => { mutedRef.current = muted }, [muted])
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
  const reportMicError = useCallback((m: string | null) => {
    setMicError(m)
    onMicErrorRef.current?.(m)
  }, [])
  const languageRef = useRef(language)
  useEffect(() => { languageRef.current = language }, [language])
  const connectTimeoutRef = useRef<any>(null)  // fails a hung connect so it never sticks

  // Expose gate to parent on mount — gate is a pure ref flag, no audio pipeline changes
  useEffect(() => {
    onSetGate?.((value) => {
      console.log('[GATE] set to', value)
      micGatedRef.current = value
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
    })
    console.log('[GATE] registered, present:', !!onSetGate)
  }, [])

  const stopAll = useCallback(() => {
    manualStopRef.current = true   // intentional stop — suppress auto-reconnect
    clearTimeout(dgReconnectTimerRef.current)
    clearTimeout(connectTimeoutRef.current)
    clearInterval(keepAliveIntervalRef.current)
    workletNodeRef.current?.disconnect()
    workletNodeRef.current = null
    audioCtxRef.current?.close()
    audioCtxRef.current = null
    if (wsRef.current) { wsRef.current.close(); wsRef.current = null }
    if (streamRef.current) { streamRef.current.getTracks().forEach(t => t.stop()); streamRef.current = null }
    setIsConnected(false)
    onConnectedChangeRef.current?.(false)
    setIsSpeaking(false)
    setIsConnecting(false)
    connectedRef.current = false
    transcriptRef.current = ''
  }, [])

  const connect = useCallback(async () => {
    if (connectedRef.current) return
    manualStopRef.current = false  // a fresh connect attempt re-enables reconnect
    console.log('[DG] connecting...')
    reportMicError(null)
    setIsConnecting(true)
    try {
      // Mint the ephemeral STT key in parallel with mic acquisition — no added latency.
      const keyPromise = getDeepgramKey()
      const baseAudio: MediaTrackConstraints = { echoCancellation: true, noiseSuppression: true, autoGainControl: true }
      const wantId = selectedMicIdRef.current
      let stream: MediaStream
      try {
        stream = await navigator.mediaDevices.getUserMedia({
          audio: wantId ? { ...baseAudio, deviceId: { ideal: wantId } } : baseAudio,
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
      const dgKey = await keyPromise
      if (!dgKey) { setIsConnecting(false); reportMicError('Voice service unavailable'); return }

      // AudioContext — resume() immediately for Safari (requires in-gesture call stack)
      const ctx = new AudioContext()
      audioCtxRef.current = ctx
      await ctx.resume()
      console.log('[DG] AudioContext sampleRate:', ctx.sampleRate)

      const dgLang = DG_LANG[languageRef.current || 'en'] || 'en-US'
      const ws = new WebSocket(
        `wss://api.deepgram.com/v1/listen?encoding=linear16&sample_rate=${ctx.sampleRate}&channels=1&model=nova-3&language=${dgLang}&smart_format=true&interim_results=true&endpointing=300&utterance_end_ms=1000&vad_events=true`,
        ['token', dgKey]
      )
      wsRef.current = ws

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

      ws.onopen = async () => {
        // Guard against StrictMode race: cleanup may have nulled wsRef while WS was connecting
        if (wsRef.current !== ws) {
          console.log('[DG] onopen: WS superseded by cleanup, discarding')
          ws.close()
          return
        }
        console.log('[DG] connected')
        clearTimeout(connectTimeoutRef.current)
        setIsConnecting(false)
        setIsConnected(true)
        onConnectedChangeRef.current?.(true)
        connectedRef.current = true
        dgReconnectAttemptsRef.current = 0   // healthy connection — reset backoff

        // KeepAlive runs for the lifetime of the session — not gated, always on
        keepAliveIntervalRef.current = setInterval(() => {
          if (wsRef.current?.readyState === WebSocket.OPEN) {
            wsRef.current.send(JSON.stringify({ type: 'KeepAlive' }))
          }
        }, 8000)

        // Load worklet and wire up the audio pipeline
        await ctx.audioWorklet.addModule('/pcm-capture.js')
        const source = ctx.createMediaStreamSource(stream)
        const node = new AudioWorkletNode(ctx, 'pcm-capture')
        workletNodeRef.current = node

        node.port.onmessage = (e) => {
          const float32 = e.data as Float32Array
          // HARD mute (itinerary build / any in-flight turn): drop every frame at the source,
          // before Deepgram and before barge-in. `muted` is documented as a hard mute, but the
          // frame loop only honoured the speak-gate — so a build whose classify was slow/failed
          // left the mic genuinely streaming under a "Not listening" label. Enforce it here so
          // the mic is truly deaf whenever muted, independent of the speak-gate's timing.
          if (mutedRef.current) return
          if (micGatedRef.current) {
            // Gate ON = avatar is speaking. DROP every frame so the avatar's audio
            // bleeding into the mic is never streamed to Deepgram. This is the core
            // echo fix — Deepgram simply never hears the avatar.
            // A deliberate mute is not interruptible — barge-in only exists to cut off the
            // avatar mid-sentence, and during a build she isn't speaking.
            if (BARGE_IN_ENABLED && !mutedRef.current) {
              const rms = Math.sqrt(float32.reduce((s, x) => s + x * x, 0) / float32.length)
              if (rms > BARGE_IN_RMS) {
                loudFramesRef.current += 1
                if (loudFramesRef.current >= BARGE_IN_FRAMES) {
                  loudFramesRef.current = 0
                  console.log('[BARGE-IN]', rms.toFixed(3), '> thr', BARGE_IN_RMS, '— interrupting avatar')
                  onInterruptRef.current?.()
                  micGatedRef.current = false  // open mic; gate setter fires async
                }
              } else {
                loudFramesRef.current = 0  // must be SUSTAINED — reset on any quiet frame
              }
            }
            return  // gated: never send avatar bleed to Deepgram
          }
          loudFramesRef.current = 0
          if (ws.readyState !== WebSocket.OPEN) return
          // Convert float32 to int16 PCM before sending
          const int16 = new Int16Array(float32.length)
          for (let i = 0; i < float32.length; i++) {
            const s = Math.max(-1, Math.min(1, float32[i]))
            int16[i] = s < 0 ? s * 0x8000 : s * 0x7fff
          }
          ws.send(int16.buffer)
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

      ws.onmessage = (event) => {
        if (micGatedRef.current) return
        try {
          const data = JSON.parse(event.data)
          if (data.type === 'SpeechStarted') {
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
                return true
              }
            }
            return false
          }

          const fireTranscript = (final: string) => {
            setIsSpeaking(false)
            onSpeakingChangeRef.current?.(false)
            if (final === lastFinal && Date.now() - lastFinalAt < 5000) return
            lastFinal = final
            lastFinalAt = Date.now()
            if (isEcho(final)) return
            onTranscriptRef.current?.(final)
          }

          // Accumulate is_final fragments; fire only when speech_final === true
          if (data.type === 'Results' && data.is_final === true) {
            const fragment = data.channel?.alternatives?.[0]?.transcript || ''
            if (fragment) {
              transcriptRef.current = transcriptRef.current
                ? `${transcriptRef.current} ${fragment}`
                : fragment
            }
            if (data.speech_final === true && transcriptRef.current.length >= 3) {
              const final = transcriptRef.current
              transcriptRef.current = ''
              fireTranscript(final)
            }
          }
          // UtteranceEnd fallback — fires if speech_final never came
          if (data.type === 'UtteranceEnd' && transcriptRef.current.length >= 3) {
            const final = transcriptRef.current
            transcriptRef.current = ''
            fireTranscript(final)
          }
        } catch(e) {}
      }

      ws.onerror = () => {
        // A WebSocket error Event carries NO detail — it always serialises to {}. The real
        // diagnostic is the close code, logged in onclose (which also handles reconnect). Keep
        // this a warn, not console.error: a transient, already-recovered socket blip must not
        // trip the Next.js dev error overlay in the middle of a live session.
        console.warn('[DG] socket error (readyState', ws.readyState, ') — reconnect handled on close')
      }
      ws.onclose = (e) => {
        console.log('[DG] closed:', e.code, e.reason)
        const wasActiveSocket = wsRef.current === ws
        if (!wasActiveSocket) return  // superseded socket — ignore
        wsRef.current = null
        clearTimeout(connectTimeoutRef.current)
        setIsConnecting(false)  // never leave the mic stuck on the connecting spinner

        // Tear down this connection's audio graph so a reconnect rebuilds cleanly.
        clearInterval(keepAliveIntervalRef.current)
        try { workletNodeRef.current?.disconnect() } catch {}
        workletNodeRef.current = null
        try { audioCtxRef.current?.close() } catch {}
        audioCtxRef.current = null
        if (streamRef.current) { streamRef.current.getTracks().forEach(t => t.stop()); streamRef.current = null }
        connectedRef.current = false
        setIsConnected(false)
        onConnectedChangeRef.current?.(false)
        setIsSpeaking(false)

        // Auto-reconnect on an UNEXPECTED drop (network blip, server reap) — but not
        // after a user/unmount stop, and only while we still want to be listening.
        if (manualStopRef.current || !readyToListenRef.current) return
        const attempt = (dgReconnectAttemptsRef.current = Math.min(dgReconnectAttemptsRef.current + 1, 6))
        const backoff = Math.min(500 * 2 ** (attempt - 1), 8000)  // 0.5s → 8s cap
        console.log(`[DG] unexpected close — reconnecting in ${backoff}ms (attempt ${attempt})`)
        clearTimeout(dgReconnectTimerRef.current)
        dgReconnectTimerRef.current = setTimeout(() => {
          if (!manualStopRef.current && readyToListenRef.current) connect()
        }, backoff)
      }

    } catch (err: any) {
      setIsConnecting(false)
      // Name the actual failure. "Could not access microphone" sent people hunting for a
      // permission problem when the real cause was another app holding the device.
      if (err.name === 'NotAllowedError') reportMicError('Mic permission denied')
      else if (err.name === 'NotFoundError') reportMicError('No microphone found')
      else if (err.name === 'NotReadableError') reportMicError('Mic is in use by another app')
      else if (err.name === 'OverconstrainedError') reportMicError('Selected mic is unavailable')
      else reportMicError(err.message || 'Could not access microphone')
    }
  }, [])  // stable — all dynamic props are read via refs above

  const toggleListening = () => {
    if (connectedRef.current) stopAll()
    else connect()
  }

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

  return (
    <div className="flex flex-col items-center gap-1">
      <button
        onClick={toggleListening}
        disabled={disabled || isConnecting}
        className={`w-10 h-10 rounded-full flex items-center justify-center flex-shrink-0 transition-all ${
          // Muted outranks everything. `isSpeaking` can be a stale true from the moment before
          // the mute landed, and a pulsing green mic on a closed mic is the exact thing that
          // made the UI look like it was still listening.
          muted         ? 'bg-white/10 opacity-60'
          : isSpeaking  ? 'bg-green-500 animate-pulse scale-110'
          : isConnected ? 'bg-red-500 animate-pulse'
          : isConnecting ? 'bg-yellow-500'
          : 'bg-indigo-600 hover:bg-indigo-700'
        } disabled:opacity-40`}
      >
        {muted ? <MicOff className="w-4 h-4 text-white/50" />
          : isConnecting ? <Loader2 className="w-4 h-4 text-white animate-spin" />
          : isConnected ? <MicOff className="w-4 h-4 text-white" />
          : <Mic className="w-4 h-4 text-white" />}
      </button>
      {micError && <p className="text-xs text-red-400 text-center max-w-[200px]">{micError}</p>}
      {muted && <p className="text-xs text-red-400/80 text-center">Not listening</p>}
      {!muted && isConnected && !isSpeaking && <p className="text-xs text-white/30 text-center">Ready</p>}
      {!muted && isSpeaking && <p className="text-xs text-green-400 text-center">Speaking...</p>}
      {/* The mic picker is deliberately NOT rendered here. It is published upward via
          onMicDevices and drawn by the page as a pill beside the camera toggle, where the rest
          of the call controls live. A local fallback used to exist for standalone use; it only
          ever caused confusion by reappearing under the composer, so it is gone. */}
    </div>
  )
}
