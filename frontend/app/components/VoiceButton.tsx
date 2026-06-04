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
}

const DEEPGRAM_API_KEY = process.env.NEXT_PUBLIC_DEEPGRAM_API_KEY

export default function VoiceButton({ onTranscript, disabled, autoStart = false, onSpeakingChange, avatarSpeaking, onInterrupt }: VoiceButtonProps) {
  const [isListening, setIsListening] = useState(false)
  const [isConnecting, setIsConnecting] = useState(false)
  const [isSpeaking, setIsSpeaking] = useState(false)
  const [micError, setMicError] = useState<string | null>(null)

  const wsRef = useRef<WebSocket | null>(null)
  const recorderRef = useRef<MediaRecorder | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const isListeningRef = useRef(false)
  const transcriptRef = useRef('')
  const avatarSpeakingRef = useRef(false)

  // Keep avatarSpeakingRef in sync with prop
  useEffect(() => {
    avatarSpeakingRef.current = !!avatarSpeaking
  }, [avatarSpeaking])

  const stopAll = useCallback(() => {
    if (recorderRef.current?.state === 'recording') recorderRef.current.stop()
    if (wsRef.current) { wsRef.current.close(); wsRef.current = null }
    if (streamRef.current) { streamRef.current.getTracks().forEach(t => t.stop()); streamRef.current = null }
    setIsListening(false)
    setIsSpeaking(false)
    setIsConnecting(false)
    isListeningRef.current = false
    transcriptRef.current = ''
  }, [])

  const startListening = useCallback(async () => {
    if (isListeningRef.current) return
    setMicError(null)
    setIsConnecting(true)
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true }
      })
      streamRef.current = stream
      const mimeType = MediaRecorder.isTypeSupported('audio/mp4') ? 'audio/mp4'
        : MediaRecorder.isTypeSupported('audio/webm;codecs=opus') ? 'audio/webm;codecs=opus'
        : 'audio/webm'
      console.log('[DG] Using mimeType:', mimeType)
      console.log('[DG] API key present:', !!DEEPGRAM_API_KEY)
      const ws = new WebSocket(
        `wss://api.deepgram.com/v1/listen?model=nova-3&language=en-US&smart_format=true&interim_results=true&endpointing=400&utterance_end_ms=1200&vad_events=true`,
        ['token', DEEPGRAM_API_KEY || '']
      )
      wsRef.current = ws
      ws.onopen = () => {
        console.log('[DG] WebSocket open!')
        setIsConnecting(false)
        setIsListening(true)
        isListeningRef.current = true
        const recorder = new MediaRecorder(stream, { mimeType })
        recorderRef.current = recorder
        recorder.ondataavailable = (e) => {
          if (e.data.size > 0 && ws.readyState === WebSocket.OPEN) ws.send(e.data)
        }
        recorder.start(250)
      }
      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data)
          console.log('[DG]', data.type, data.is_final, data.speech_final, data.channel?.alternatives?.[0]?.transcript?.substring(0,50))

          if (data.type === 'SpeechStarted') {
            if (avatarSpeakingRef.current) {
              onInterrupt?.()
              return
            }
            setIsSpeaking(true)
            onSpeakingChange?.(true)
          }

          if (data.type === 'Results') {
            const transcript = data.channel?.alternatives?.[0]?.transcript || ''
            if (transcript) transcriptRef.current = transcript
            if (data.speech_final && transcriptRef.current && transcriptRef.current.length >= 3) {
              if (avatarSpeakingRef.current) {
                onInterrupt?.()
                return
              }
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
      ws.onerror = (e) => { console.error('[DG] error:', e); setMicError('Connection error'); stopAll() }
      ws.onclose = (e) => {
        console.log('[DG] closed:', e.code, e.reason)
        if (isListeningRef.current) setTimeout(() => { if (isListeningRef.current) startListening() }, 2000)
      }
    } catch (err: any) {
      setIsConnecting(false)
      if (err.name === 'NotAllowedError') setMicError('Mic permission denied')
      else if (err.name === 'NotFoundError') setMicError('No microphone found')
      else setMicError(err.message || 'Could not access microphone')
    }
  }, [onTranscript, onSpeakingChange, onInterrupt, stopAll])

  const toggleListening = () => {
    if (isListeningRef.current) { isListeningRef.current = false; stopAll() }
    else startListening()
  }

  useEffect(() => {
    if (autoStart && !disabled) startListening()
    return () => { isListeningRef.current = false; stopAll() }
  }, [autoStart])

  return (
    <div className="flex flex-col items-center gap-1">
      <button onClick={toggleListening} disabled={disabled || isConnecting}
        className={`w-10 h-10 rounded-full flex items-center justify-center flex-shrink-0 transition-all ${
          isSpeaking ? 'bg-green-500 animate-pulse scale-110'
          : isListening ? 'bg-red-500 animate-pulse'
          : isConnecting ? 'bg-yellow-500'
          : 'bg-indigo-600 hover:bg-indigo-700'
        } disabled:opacity-40`}>
        {isConnecting ? <Loader2 className="w-4 h-4 text-white animate-spin" />
          : isListening ? <MicOff className="w-4 h-4 text-white" />
          : <Mic className="w-4 h-4 text-white" />}
      </button>
      {micError && <p className="text-xs text-red-400 text-center max-w-[200px]">{micError}</p>}
      {isListening && !isSpeaking && <p className="text-xs text-white/30 text-center">Listening...</p>}
      {isSpeaking && <p className="text-xs text-green-400 text-center">Speaking...</p>}
    </div>
  )
}
