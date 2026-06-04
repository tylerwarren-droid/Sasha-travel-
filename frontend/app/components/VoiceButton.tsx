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
  const recorderRef = useRef<MediaRecorder | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const connectedRef = useRef(false)
  const transcriptRef = useRef('')
  // Start gated — mic is live but audio is suppressed until first AVATAR_SPEAK_ENDED
  const micGatedRef = useRef(true)
  const keepAliveIntervalRef = useRef<any>(null)

  // Expose gate to parent on mount — gate is purely a ref flag, no recorder state changes
  useEffect(() => {
    onSetGate?.((value) => {
      console.log('[GATE] set to', value)
      micGatedRef.current = value
      if (!value) {
        // Discard any partial transcript that accumulated while gated
        transcriptRef.current = ''
        setIsSpeaking(false)
      }
    })
    console.log('[GATE] registered, present:', !!onSetGate)
  }, [])

  const stopAll = useCallback(() => {
    clearInterval(keepAliveIntervalRef.current)
    if (recorderRef.current && recorderRef.current.state !== 'inactive') recorderRef.current.stop()
    recorderRef.current = null
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
    setMicError(null)
    setIsConnecting(true)
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true }
      })
      streamRef.current = stream

      const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus') ? 'audio/webm;codecs=opus'
        : MediaRecorder.isTypeSupported('audio/mp4') ? 'audio/mp4'
        : 'audio/webm'
      console.log('[DG] connecting | mimeType:', mimeType, '| key present:', !!DEEPGRAM_API_KEY)

      const ws = new WebSocket(
        `wss://api.deepgram.com/v1/listen?model=nova-3&language=en-US&smart_format=true&interim_results=true&endpointing=300&utterance_end_ms=1000&vad_events=true`,
        ['token', DEEPGRAM_API_KEY || '']
      )
      wsRef.current = ws

      ws.onopen = () => {
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

        // Recorder runs continuously — gating is done purely in ondataavailable
        const recorder = new MediaRecorder(stream, { mimeType })
        recorderRef.current = recorder
        recorder.ondataavailable = (e) => {
          if (micGatedRef.current) return
          if (e.data.size > 0 && ws.readyState === WebSocket.OPEN) ws.send(e.data)
        }
        recorder.start(250)
      }

      ws.onmessage = (event) => {
        // Gate blocks all message processing — no partial transcripts bleed through
        if (micGatedRef.current) return
        try {
          const data = JSON.parse(event.data)
          if (data.type === 'SpeechStarted') {
            setIsSpeaking(true)
            onSpeakingChange?.(true)
          }
          if (data.type === 'Results') {
            const transcript = data.channel?.alternatives?.[0]?.transcript || ''
            if (transcript) transcriptRef.current = transcript
            if (data.speech_final && transcriptRef.current && transcriptRef.current.length >= 3) {
              const final = transcriptRef.current
              transcriptRef.current = ''
              setIsSpeaking(false)
              onSpeakingChange?.(false)
              onTranscript(final)
            }
          }
          if (data.type === 'UtteranceEnd' && transcriptRef.current && transcriptRef.current.length >= 3) {
            const final = transcriptRef.current
            transcriptRef.current = ''
            setIsSpeaking(false)
            onSpeakingChange?.(false)
            onTranscript(final)
          }
        } catch(e) {}
      }

      ws.onerror = (e) => { console.error('[DG] error:', e); setMicError('Connection error') }
      ws.onclose = (e) => { console.log('[DG] closed:', e.code, e.reason) }

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
