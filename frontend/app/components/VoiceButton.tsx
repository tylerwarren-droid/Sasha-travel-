'use client'
import { useState, useRef } from 'react'
import { Mic, MicOff, Loader2 } from 'lucide-react'
import axios from 'axios'

interface VoiceButtonProps {
  onTranscript: (text: string) => void
  disabled?: boolean
}

export default function VoiceButton({ onTranscript, disabled }: VoiceButtonProps) {
  const [isListening, setIsListening] = useState(false)
  const [isRequestingMic, setIsRequestingMic] = useState(false)
  const [isProcessing, setIsProcessing] = useState(false)
  const [micError, setMicError] = useState<string | null>(null)
  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const chunksRef = useRef<Blob[]>([])

  const startListening = async () => {
    setMicError(null)
    setIsRequestingMic(true)
    setIsListening(true)

    try {
      if (!navigator.mediaDevices?.getUserMedia) {
        throw Object.assign(new Error('Microphone access is not supported in this browser.'), { name: 'NotSupportedError' })
      }
      if (!window.isSecureContext) {
        throw Object.assign(new Error('Microphone access requires HTTPS.'), { name: 'InsecureError' })
      }

      const stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: false, noiseSuppression: false, sampleRate: 44100 } })
      setIsRequestingMic(false)

      const mimeType = MediaRecorder.isTypeSupported('audio/webm') ? 'audio/webm' : MediaRecorder.isTypeSupported('audio/mp4') ? 'audio/mp4' : ''
      const mediaRecorder = new MediaRecorder(stream, mimeType ? { mimeType } : {})
      mediaRecorderRef.current = mediaRecorder
      chunksRef.current = []

      mediaRecorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data)
      }

      mediaRecorder.onstop = async () => {
        setIsListening(false)
        setIsProcessing(true)
        try {
          const audioBlob = new Blob(chunksRef.current, { type: 'audio/webm' })
          const formData = new FormData()
          formData.append('audio', audioBlob, 'recording.webm')
          const response = await axios.post(
            process.env.NEXT_PUBLIC_API_URL + '/voice/transcribe',
            formData,
            { headers: { 'Content-Type': 'multipart/form-data' } }
          )
          const { transcript, confidence } = response.data
          if (transcript && confidence > 0.5) {
            onTranscript(transcript)
          }
        } catch (error) {
          console.error('Transcription error:', error)
        } finally {
          setIsProcessing(false)
          stream.getTracks().forEach(track => track.stop())
        }
      }

      mediaRecorder.start()
      setTimeout(() => {
        if (mediaRecorder.state === 'recording') mediaRecorder.stop()
      }, 15000)

    } catch (err: any) {
      console.error('Microphone error:', err)
      setIsRequestingMic(false)
      setIsListening(false)
      if (err.name === 'NotAllowedError') {
        setMicError('Mic permission denied. Please allow microphone access in your browser settings.')
      } else if (err.name === 'NotFoundError') {
        setMicError('No microphone found on this device.')
      } else if (err.name === 'NotReadableError') {
        setMicError('Microphone is in use by another app.')
      } else {
        setMicError(err.message || 'Could not access the microphone.')
      }
    }
  }

  const stopListening = () => {
    if (mediaRecorderRef.current?.state === 'recording') {
      mediaRecorderRef.current.stop()
    }
  }

  return (
    <div className="flex flex-col items-center gap-1">
      <button
        onClick={isListening ? stopListening : startListening}
        disabled={disabled || isProcessing}
        className={`w-10 h-10 rounded-full flex items-center justify-center flex-shrink-0 transition-all ${
          isListening ? 'bg-red-500 animate-pulse' : isRequestingMic ? 'bg-yellow-500' : isProcessing ? 'bg-amber-500' : 'bg-indigo-600 hover:bg-indigo-700'
        } disabled:opacity-40`}
      >
        {isProcessing ? <Loader2 className="w-4 h-4 text-white animate-spin" /> : isListening ? <MicOff className="w-4 h-4 text-white" /> : <Mic className="w-4 h-4 text-white" />}
      </button>
      {micError && (
        <p className="text-xs text-red-400 text-center max-w-[200px]">{micError}</p>
      )}
    </div>
  )
}
