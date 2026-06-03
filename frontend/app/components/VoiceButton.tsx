'use client'
import { useState, useRef, useEffect, useCallback } from 'react'
import { Mic, MicOff, Loader2 } from 'lucide-react'

interface VoiceButtonProps {
  onTranscript: (text: string) => void
  disabled?: boolean
  autoStart?: boolean
  onSpeakingChange?: (isSpeaking: boolean) => void
}

const DEEPGRAM_API_KEY = process.env.NEXT_PUBLIC_DEEPGRAM_API_KEY

export default function VoiceButton({ 
  onTranscript, 
  disabled,
  autoStart = false,
  onSpeakingChange
}: VoiceButtonProps) {
  const [isListening, setIsListening] = useState(false)
  const [isConnecting, setIsConnecting] = useState(false)
  const [isSpeaking, setIsSpeaking] = useState(false)
  const [micError, setMicError] = useState<string | null>(null)
  
  const wsRef = useRef<WebSocket | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const processorRef = useRef<ScriptProcessorNode | null>(null)
  const audioContextRef = useRef<AudioContext | null>(null)
  const isListeningRef = useRef(false)
  const currentTranscriptRef = useRef<string>('')

  const stopAll = useCallback(() => {
    if (processorRef.current) { processorRef.current.disconnect(); processorRef.current = null }
    if (audioContextRef.current) { audioContextRef.current.close().catch(() => {}); audioContextRef.current = null }
    if (wsRef.current) { wsRef.current.close(); wsRef.current = null }
    if (streamRef.current) { streamRef.current.getTracks().forEach(t => t.stop()); streamRef.current = null }
    setIsListening(false)
    setIsSpeaking(false)
    setIsConnecting(false)
    isListeningRef.current = false
    currentTranscriptRef.current = ''
  }, [])

  const startListening = useCallback(async () => {
    if (isListeningRef.current) return
    setMicError(null)
    setIsConnecting(true)
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, sampleRate: 16000 } })
      streamRef.current = stream
      const ws = new WebSocket(
        `wss://api.deepgram.com/v1/listen?model=nova-3&language=en-US&smart_format=true&interim_results=true&endpointing=300&utterance_end_ms=1000&vad_events=true`,
        ['token', DEEPGRAM_API_KEY || '']
      )
      wsRef.current = ws
      ws.onopen = () => {
        setIsConnecting(false)
        setIsListening(true)
        isListeningRef.current = true
        const audioContext = new AudioContext({ sampleRate: 16000 })
        audioContextRef.current = audioContext
        const source = audioContext.createMediaStreamSource(stream)
        const processor = audioContext.createScriptProcessor(4096, 1, 1)
        processorRef.current = processor
        processor.onaudioprocess = (e) => {
          if (ws.readyState !== WebSocket.OPEN) return
          const input = e.inputBuffer.getChannelData(0)
          const int16 = new Int16Array(input.length)
          for (let i = 0; i < input.length; i++) {
            int16[i] = Math.max(-32768, Math.min(32767, input[i] * 32768))
          }
          ws.send(int16.buffer)
        }
        source.connect(processor)
        processor.connect(audioContext.destination)
      }
      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data)
          if (data.type === 'SpeechStarted') {
            setIsSpeaking(true)
            onSpeakingChange?.(true)
            return
          }
          if (data.type === 'Results') {
            const transcript = data.channel?.alternatives?.[0]?.transcript || ''
            const isFinal = data.is_final
            const speechFinal = data.speech_final
            if (transcript) currentTranscriptRef.current = transcript
            if ((speechFinal || isFinal) && currentTranscriptRef.current) {
              const final = currentTranscriptRef.current
              currentTranscriptRef.current = ''
              setIsSpeaking(false)
              onSpeakingChange?.(false)
              onTranscript(final)
            }
          }
          // UtteranceEnd fallback — fires when Deepgram detects end of utterance
          if (data.type === 'UtteranceEnd') {
            if (currentTranscriptRef.current) {
              const final = currentTranscriptRef.current
              currentTranscriptRef.current = ''
              setIsSpeaking(false)
              onSpeakingChange?.(false)
              onTranscript(final)
            }
          }
        } catch(e) {}
      }
      ws.onerror = () => { setMicError('Connection error'); stopAll() }
      ws.onclose = () => {
        if (isListeningRef.current) {
          setTimeout(() => { if (isListeningRef.current) startListening() }, 2000)
        }
      }
    } catch (err: any) {
      setIsConnecting(false)
      if (err.name === 'NotAllowedError') setMicError('Mic permission denied')
      else if (err.name === 'NotFoundError') setMicError('No microphone found')
      else setMicError(err.message || 'Could not access microphone')
    }
  }, [onTranscript, onSpeakingChange, stopAll])

  const toggleListening = () => {
    if (isListeningRef.current) { isListeningRef.current = false; stopAll() }
    else startListening()
  }

  useEffect(() => {
    if (autoStart && !disabled) startListening()
    return () => stopAll()
  }, [autoStart])

  useEffect(() => { return () => stopAll() }, [stopAll])

  return (
    <div className="flex flex-col items-center gap-1">
      <button
        onClick={toggleListening}
        disabled={disabled || isConnecting}
        className={`w-10 h-10 rounded-full flex items-center justify-center flex-shrink-0 transition-all ${
          isSpeaking ? 'bg-green-500 animate-pulse scale-110' 
          : isListening ? 'bg-red-500 animate-pulse' 
          : isConnecting ? 'bg-yellow-500' 
          : 'bg-indigo-600 hover:bg-indigo-700'
        } disabled:opacity-40`}
      >
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
