'use client'
import { useState, useRef, useEffect, useCallback } from 'react'
import { Mic, MicOff, Loader2 } from 'lucide-react'

interface VoiceButtonProps {
  onTranscript: (text: string) => void
  disabled?: boolean
  autoStart?: boolean
  readyToListen?: boolean
  onSpeakingChange?: (isSpeaking: boolean) => void
  avatarSpeaking?: boolean
  onInterrupt?: () => void
  onSetGate?: (gate: (value: boolean) => void) => void
  avatarSpeechGetter?: () => string
}

const DEEPGRAM_API_KEY = process.env.NEXT_PUBLIC_DEEPGRAM_API_KEY

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
const BARGE_IN_RMS = 0.07
const BARGE_IN_FRAMES = 30           // ~75ms sustained — rejects transient residual spikes
// Echo (avatar audio bleeding into the mic) only arrives in the brief tail right after
// the avatar goes quiet. Beyond this window, identical words are the USER genuinely
// answering (e.g. repeating the avatar's options like "mix of everything") — never
// discard those, or the avatar appears to "stop hearing" the user.
const ECHO_WINDOW_MS = 1500

const normalizeText = (t: string) => t.toLowerCase().replace(/[^\w\s]/g, '').split(/\s+/).filter(Boolean)

export default function VoiceButton({ onTranscript, disabled, autoStart = false, readyToListen = false, onSpeakingChange, onInterrupt, onSetGate, avatarSpeechGetter }: VoiceButtonProps) {
  const [isConnecting, setIsConnecting] = useState(false)
  const [isConnected, setIsConnected] = useState(false)
  const [isSpeaking, setIsSpeaking] = useState(false)
  const [micError, setMicError] = useState<string | null>(null)

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
  const avatarSpeechGetterRef = useRef(avatarSpeechGetter)
  useEffect(() => { avatarSpeechGetterRef.current = avatarSpeechGetter }, [avatarSpeechGetter])

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
    clearInterval(keepAliveIntervalRef.current)
    workletNodeRef.current?.disconnect()
    workletNodeRef.current = null
    audioCtxRef.current?.close()
    audioCtxRef.current = null
    if (wsRef.current) { wsRef.current.close(); wsRef.current = null }
    if (streamRef.current) { streamRef.current.getTracks().forEach(t => t.stop()); streamRef.current = null }
    setIsConnected(false)
    setIsSpeaking(false)
    setIsConnecting(false)
    connectedRef.current = false
    transcriptRef.current = ''
  }, [])

  const connect = useCallback(async () => {
    if (connectedRef.current) return
    manualStopRef.current = false  // a fresh connect attempt re-enables reconnect
    console.log('[DG] connecting...')
    console.log('[DG] API key present:', !!DEEPGRAM_API_KEY)
    setMicError(null)
    setIsConnecting(true)
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true }
      })
      streamRef.current = stream

      // AudioContext — resume() immediately for Safari (requires in-gesture call stack)
      const ctx = new AudioContext()
      audioCtxRef.current = ctx
      await ctx.resume()
      console.log('[DG] AudioContext sampleRate:', ctx.sampleRate)

      const ws = new WebSocket(
        `wss://api.deepgram.com/v1/listen?encoding=linear16&sample_rate=${ctx.sampleRate}&channels=1&model=nova-3&language=en-US&smart_format=true&interim_results=true&endpointing=300&utterance_end_ms=1000&vad_events=true`,
        ['token', DEEPGRAM_API_KEY || '']
      )
      wsRef.current = ws

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
        setIsConnecting(false)
        setIsConnected(true)
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
          if (micGatedRef.current) {
            // Gate ON = avatar is speaking. DROP every frame so the avatar's audio
            // bleeding into the mic is never streamed to Deepgram. This is the core
            // echo fix — Deepgram simply never hears the avatar.
            if (BARGE_IN_ENABLED) {
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

      ws.onerror = (e) => { console.error('[DG] error:', e) }
      ws.onclose = (e) => {
        console.log('[DG] closed:', e.code, e.reason)
        const wasActiveSocket = wsRef.current === ws
        if (!wasActiveSocket) return  // superseded socket — ignore
        wsRef.current = null

        // Tear down this connection's audio graph so a reconnect rebuilds cleanly.
        clearInterval(keepAliveIntervalRef.current)
        try { workletNodeRef.current?.disconnect() } catch {}
        workletNodeRef.current = null
        try { audioCtxRef.current?.close() } catch {}
        audioCtxRef.current = null
        if (streamRef.current) { streamRef.current.getTracks().forEach(t => t.stop()); streamRef.current = null }
        connectedRef.current = false
        setIsConnected(false)
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
      if (err.name === 'NotAllowedError') setMicError('Mic permission denied')
      else if (err.name === 'NotFoundError') setMicError('No microphone found')
      else setMicError(err.message || 'Could not access microphone')
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

  return (
    <div className="flex flex-col items-center gap-1">
      <button
        onClick={toggleListening}
        disabled={disabled || isConnecting}
        className={`w-10 h-10 rounded-full flex items-center justify-center flex-shrink-0 transition-all ${
          isSpeaking    ? 'bg-green-500 animate-pulse scale-110'
          : isConnected ? 'bg-red-500 animate-pulse'
          : isConnecting ? 'bg-yellow-500'
          : 'bg-indigo-600 hover:bg-indigo-700'
        } disabled:opacity-40`}
      >
        {isConnecting ? <Loader2 className="w-4 h-4 text-white animate-spin" />
          : isConnected ? <MicOff className="w-4 h-4 text-white" />
          : <Mic className="w-4 h-4 text-white" />}
      </button>
      {micError && <p className="text-xs text-red-400 text-center max-w-[200px]">{micError}</p>}
      {isConnected && !isSpeaking && <p className="text-xs text-white/30 text-center">Ready</p>}
      {isSpeaking && <p className="text-xs text-green-400 text-center">Speaking...</p>}
    </div>
  )
}
