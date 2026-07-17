'use client'

import { useState, useRef, useEffect } from 'react'
import { Mic, MicOff, Loader2 } from 'lucide-react'
import { API_URL } from '@/lib/api'

const DEMO_USER = {
  display_name: 'Alex',
  email: 'alex@example.com',
}

export default function VoicePage() {
  const [isListening, setIsListening] = useState(false)
  const [isProcessing, setIsProcessing] = useState(false)
  const [isSpeaking, setIsSpeaking] = useState(false)
  const [micError, setMicError] = useState('')
  const [transcript, setTranscript] = useState('')
  const [response, setResponse] = useState('')
  const [messages, setMessages] = useState<any[]>([])
  const [photos, setPhotos] = useState<any[]>([])
  const [activePhoto, setActivePhoto] = useState(0)
  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const chunksRef = useRef<Blob[]>([])
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const photoInterval = useRef<any>(null)

  useEffect(() => {
    if (photos.length <= 1) return
    clearInterval(photoInterval.current)
    photoInterval.current = setInterval(() => {
      setActivePhoto(prev => (prev + 1) % photos.length)
    }, 5000)
    return () => clearInterval(photoInterval.current)
  }, [photos])

  const playAudio = async (base64Audio: string) => {
    setIsSpeaking(true)
    try {
      const binary = atob(base64Audio)
      const bytes = new Uint8Array(binary.length)
      for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i)
      const blob = new Blob([bytes], { type: 'audio/mpeg' })
      const url = URL.createObjectURL(blob)
      const audio = new Audio(url)
      audioRef.current = audio
      audio.onended = () => { setIsSpeaking(false); URL.revokeObjectURL(url) }
      audio.onerror = () => setIsSpeaking(false)
      await audio.play()
    } catch (e) {
      setIsSpeaking(false)
    }
  }

  const startListening = async () => {
    setMicError('')
    if (!navigator.mediaDevices?.getUserMedia) {
      setMicError('Microphone not supported in this browser.')
      return
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const mimeType = MediaRecorder.isTypeSupported('audio/webm') ? 'audio/webm' : 'audio/mp4'
      const mediaRecorder = new MediaRecorder(stream, { mimeType })
      mediaRecorderRef.current = mediaRecorder
      chunksRef.current = []

      mediaRecorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data)
      }

      mediaRecorder.onstop = async () => {
        setIsListening(false)
        setIsProcessing(true)
        try {
          const audioBlob = new Blob(chunksRef.current, { type: mimeType })
          const formData = new FormData()
          formData.append('audio', audioBlob, 'recording.webm')
          formData.append('conversation_history', JSON.stringify(messages))

          const res = await fetch(API_URL + '/voice/conductor', {
            method: 'POST',
            body: formData
          })
          const data = await res.json()

          if (data.transcript) setTranscript(data.transcript)
          if (data.response) setResponse(data.response)
          if (data.conversation_history) setMessages(data.conversation_history)
          if (data.photos?.length > 0) { setPhotos(data.photos); setActivePhoto(0) }
          if (data.audio) await playAudio(data.audio)

        } catch (e) {
          setMicError('Something went wrong. Please try again.')
        } finally {
          setIsProcessing(false)
          stream.getTracks().forEach(t => t.stop())
        }
      }

      mediaRecorder.start()
      setIsListening(true)

      // Auto stop after 10 seconds
      setTimeout(() => {
        if (mediaRecorder.state === 'recording') mediaRecorder.stop()
      }, 10000)

    } catch (err: any) {
      if (err.name === 'NotAllowedError') {
        setMicError('Microphone permission denied. Please allow access in your browser settings.')
      } else {
        setMicError('Could not access microphone.')
      }
    }
  }

  const stopListening = () => {
    if (mediaRecorderRef.current?.state === 'recording') {
      mediaRecorderRef.current.stop()
    }
  }

  const stopSpeaking = () => {
    audioRef.current?.pause()
    setIsSpeaking(false)
  }

  const getButtonState = () => {
    if (isProcessing) return { bg: '#F59E0B', icon: 'processing', label: 'Thinking...' }
    if (isSpeaking) return { bg: '#8B5CF6', icon: 'speaking', label: 'Tap to stop' }
    if (isListening) return { bg: '#EF4444', icon: 'listening', label: 'Tap to send' }
    return { bg: '#4F46E5', icon: 'idle', label: 'Tap to speak' }
  }

  const handleButtonClick = () => {
    if (isSpeaking) { stopSpeaking(); return }
    if (isListening) { stopListening(); return }
    if (!isProcessing) startListening()
  }

  const state = getButtonState()

  return (
    <main className="h-screen flex flex-col overflow-hidden" style={{ background: '#080810' }}>

      {/* HEADER */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-white/5 flex-shrink-0"
        style={{ background: 'rgba(0,0,0,0.8)', backdropFilter: 'blur(10px)' }}>
        <div className="flex items-center gap-2">
          <span className="text-lg">🇻🇳</span>
          <span className="font-bold text-sm tracking-wide" style={{ color: '#DAA520' }}>Sasha</span>
          <div className="w-px h-3 bg-white/10" />
          <span className="text-xs text-white/30 tracking-widest uppercase">Voice Concierge</span>
        </div>
        <div className="text-xs px-2 py-1 rounded-full border" style={{ color: '#DAA520', borderColor: 'rgba(218,165,32,0.3)', background: 'rgba(218,165,32,0.1)' }}>
          Vietnam
        </div>
      </div>

      {/* PHOTO BACKGROUND */}
      <div className="flex-1 relative overflow-hidden flex flex-col items-center justify-center">
        {photos.length > 0 && (
          <div className="absolute inset-0">
            <img src={photos[activePhoto]?.url} alt="" className="w-full h-full object-cover opacity-20" />
            <div className="absolute inset-0" style={{ background: 'linear-gradient(to bottom, transparent 30%, #080810 100%)' }} />
          </div>
        )}

        {/* TRANSCRIPT + RESPONSE */}
        <div className="relative z-10 w-full max-w-sm px-6 mb-8 space-y-4">
          {transcript && (
            <div className="rounded-2xl px-4 py-3 ml-auto max-w-[85%] w-fit"
              style={{ background: 'linear-gradient(135deg, #4F46E5, #7C3AED)' }}>
              <p className="text-sm text-white">{transcript}</p>
            </div>
          )}
          {response && (
            <div className="rounded-2xl px-4 py-3 max-w-[85%]"
              style={{ background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.08)' }}>
              <p className="text-sm text-white/80 leading-relaxed">{response}</p>
            </div>
          )}
        </div>

        {/* BIG MIC BUTTON */}
        <div className="relative z-10 flex flex-col items-center gap-4">
          <button
            onClick={handleButtonClick}
            disabled={isProcessing}
            className="relative flex items-center justify-center rounded-full transition-all duration-300 disabled:opacity-50"
            style={{
              width: '96px', height: '96px',
              background: state.bg,
              boxShadow: isListening ? `0 0 0 20px ${state.bg}30, 0 0 0 40px ${state.bg}15` : `0 0 30px ${state.bg}60`
            }}
          >
            {isProcessing ? (
              <Loader2 className="w-10 h-10 text-white animate-spin" />
            ) : isListening ? (
              <MicOff className="w-10 h-10 text-white" />
            ) : isSpeaking ? (
              <svg className="w-10 h-10 text-white" fill="currentColor" viewBox="0 0 24 24">
                <path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z"/>
              </svg>
            ) : (
              <Mic className="w-10 h-10 text-white" />
            )}
            {isListening && (
              <div className="absolute inset-0 rounded-full animate-ping opacity-30" style={{ background: state.bg }} />
            )}
          </button>

          <p className="text-sm text-white/40">{state.label}</p>

          {micError && (
            <p className="text-xs text-red-400 text-center max-w-[240px]">{micError}</p>
          )}
        </div>

        {/* QUICK PROMPTS — only show when idle and no conversation yet */}
        {!transcript && !isListening && !isProcessing && (
          <div className="relative z-10 mt-8 flex flex-wrap gap-2 justify-center px-6 max-w-sm">
            {['Golf in Da Nang', 'Best beaches Vietnam', 'Book a spa', 'Find a doctor', 'Restaurant for dinner'].map(prompt => (
              <button key={prompt}
                onClick={async () => {
                  setTranscript(prompt)
                  setIsProcessing(true)
                  try {
                    const res = await fetch(API_URL + '/api/agents/conductor', {
                      method: 'POST',
                      headers: { 'Content-Type': 'application/json' },
                      body: JSON.stringify({ message: prompt, conversation_history: messages })
                    })
                    const data = await res.json()
                    setResponse(data.response)
                    setMessages(data.conversation_history || [])
                    if (data.photos?.length > 0) { setPhotos(data.photos); setActivePhoto(0) }
                    // TTS for quick prompts
                    const ttsRes = await fetch(API_URL + '/voice/tts', {
                      method: 'POST',
                      headers: { 'Content-Type': 'application/json' },
                      body: JSON.stringify({ text: data.response })
                    })
                    const ttsBlob = await ttsRes.blob()
                    const url = URL.createObjectURL(ttsBlob)
                    const audio = new Audio(url)
                    audioRef.current = audio
                    setIsSpeaking(true)
                    audio.onended = () => { setIsSpeaking(false); URL.revokeObjectURL(url) }
                    await audio.play()
                  } catch (e) {
                    setMicError('Something went wrong.')
                  } finally {
                    setIsProcessing(false)
                  }
                }}
                className="text-xs px-3 py-1.5 rounded-full border transition-all hover:bg-white/10"
                style={{ color: 'rgba(255,255,255,0.5)', borderColor: 'rgba(255,255,255,0.1)' }}>
                {prompt}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* PHOTO STRIP */}
      {photos.length > 0 && (
        <div className="flex-shrink-0 border-t border-white/5" style={{ height: '80px', background: 'rgba(0,0,0,0.4)' }}>
          <div className="flex h-full gap-1 p-1">
            {photos.map((photo, i) => (
              <button key={i} onClick={() => setActivePhoto(i)}
                className="relative rounded-lg overflow-hidden transition-all duration-300 flex-1"
                style={{ border: i === activePhoto ? '2px solid #DAA520' : '2px solid transparent' }}>
                <img src={photo.thumb} alt="" className="w-full h-full object-cover"
                  style={{ opacity: i === activePhoto ? 1 : 0.4 }} />
              </button>
            ))}
          </div>
        </div>
      )}
    </main>
  )
}
