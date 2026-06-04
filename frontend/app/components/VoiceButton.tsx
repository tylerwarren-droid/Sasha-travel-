'use client'
import { useState, useRef, useEffect, useCallback } from 'react'
import { Mic, MicOff, Loader2 } from 'lucide-react'

interface VoiceButtonProps {
  onTranscript: (text: string) => void
  disabled?: boolean
  autoStart?: boolean
  onSpeakingChange?: (isSpeaking: boolean) => void
  avatarSpeaking?: boolean
  onInterrupt?: () => void
  onSetGate?: (gate: (value: boolean) => void) => void
}

const DEEPGRAM_API_KEY = process.env.NEXT_PUBLIC_DEEPGRAM_API_KEY

export default function VoiceButton({ onTranscript, disabled, autoStart = false, onSpeakingChange, onInterrupt, onSetGate }: VoiceButtonProps) {
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
  const keepAliveIntervalRef = useRef<any>(null)
  // Ref so the worklet closure always sees the latest onInterrupt prop
  const onInterruptRef = useRef(onInterrupt)
  useEffect(() => { onInterruptRef.current = onInterrupt }, [onInterrupt])

  // Expose gate to parent on mount — gate is a pure ref flag, no audio pipeline changes
  useEffect(() => {
    onSetGate?.((value) => {
      console.log('[GATE] set to', value)
      micGatedRef.current = value
      if (!value) {
        transcriptRef.current = ''
        setIsSpeaking(false)
      }
    })
    console.log('[GATE] registered, present:', !!onSetGate)
  }, [])

  const stopAll = useCallback(() => {
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
            // While avatar is speaking, measure RMS — loud user voice means interrupt
            const rms = Math.sqrt(float32.reduce((s, x) => s + x * x, 0) / float32.length)
            console.log('[RMS]', rms.toFixed(4), 'gated:', micGatedRef.current)
            if (rms > 0.0005) {
              onInterruptRef.current?.()
              micGatedRef.current = false  // open mic immediately; gate setter fires async
            } else {
              return  // speaker bleed, drop frame
            }
          }
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
        // Connect to destination to keep the audio graph alive in some browsers
        node.connect(ctx.destination)
      }

      ws.onmessage = (event) => {
        if (micGatedRef.current) return
        try {
          const data = JSON.parse(event.data)
          if (data.type === 'SpeechStarted') {
            setIsSpeaking(true)
            onSpeakingChange?.(true)
          }
          // Only process is_final results — ignore interim results entirely (BUG 4)
          if (data.type === 'Results' && data.is_final === true) {
            const transcript = data.channel?.alternatives?.[0]?.transcript || ''
            if (transcript) transcriptRef.current = transcript
            if (transcriptRef.current && transcriptRef.current.length >= 3) {
              const final = transcriptRef.current
              transcriptRef.current = ''
              setIsSpeaking(false)
              onSpeakingChange?.(false)
              if (final === lastFinal && Date.now() - lastFinalAt < 5000) return
              lastFinal = final
              lastFinalAt = Date.now()
              onTranscript(final)
            }
          }
          if (data.type === 'UtteranceEnd' && transcriptRef.current && transcriptRef.current.length >= 3) {
            const final = transcriptRef.current
            transcriptRef.current = ''
            setIsSpeaking(false)
            onSpeakingChange?.(false)
            if (final === lastFinal && Date.now() - lastFinalAt < 5000) return
            lastFinal = final
            lastFinalAt = Date.now()
            onTranscript(final)
          }
        } catch(e) {}
      }

      ws.onerror = (e) => { console.error('[DG] error:', e); setMicError('Connection error') }
      ws.onclose = (e) => {
        console.log('[DG] closed:', e.code, e.reason)
        if (wsRef.current === ws) wsRef.current = null
      }

    } catch (err: any) {
      setIsConnecting(false)
      if (err.name === 'NotAllowedError') setMicError('Mic permission denied')
      else if (err.name === 'NotFoundError') setMicError('No microphone found')
      else setMicError(err.message || 'Could not access microphone')
    }
  }, [onTranscript, onSpeakingChange])

  const toggleListening = () => {
    if (connectedRef.current) stopAll()
    else connect()
  }

  useEffect(() => {
    console.log('[DG] connect called, autoStart:', autoStart, 'disabled:', disabled)
    if (autoStart && !disabled) connect()
    return () => stopAll()
  }, [autoStart])

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
