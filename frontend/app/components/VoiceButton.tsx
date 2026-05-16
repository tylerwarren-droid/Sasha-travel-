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
  const [isProcessing, setIsProcessing] = useState(false)
  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const chunksRef = useRef<Blob[]>([])

  const startListening = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const mediaRecorder = new MediaRecorder(stream, { mimeType: 'audio/webm' })
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
      setIsListening(true)
      setTimeout(() => {
        if (mediaRecorder.state === 'recording') mediaRecorder.stop()
      }, 15000)
    } catch (error) {
      alert('Could not access microphone. Please check permissions.')
    }
  }

  const stopListening = () => {
    if (mediaRecorderRef.current?.state === 'recording') {
      mediaRecorderRef.current.stop()
    }
  }

  return (
    <button
      onClick={isListening ? stopListening : startListening}
      disabled={disabled || isProcessing}
      className={`w-10 h-10 rounded-full flex items-center justify-center flex-shrink-0 transition-all ${
        isListening ? 'bg-red-500 animate-pulse' : isProcessing ? 'bg-amber-500' : 'bg-indigo-600 hover:bg-indigo-700'
      } disabled:opacity-40`}
    >
      {isProcessing ? <Loader2 className="w-4 h-4 text-white animate-spin" /> : isListening ? <MicOff className="w-4 h-4 text-white" /> : <Mic className="w-4 h-4 text-white" />}
    </button>
  )
}
