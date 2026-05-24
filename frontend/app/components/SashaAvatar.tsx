'use client'
import { useEffect, useRef, useState } from 'react'

interface SashaAvatarProps {
  onAvatarReady: (speak: (text: string) => void) => void
  isListening?: boolean
}

export default function SashaAvatar({ onAvatarReady, isListening }: SashaAvatarProps) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const audioRef = useRef<HTMLAudioElement>(null)
  const avatarRef = useRef<any>(null)
  const [status, setStatus] = useState<'idle' | 'loading' | 'ready' | 'error'>('idle')
  const [error, setError] = useState('')

  useEffect(() => {
    return () => {
      avatarRef.current?.stop?.()
    }
  }, [])

  const initAvatar = async () => {
    setStatus('loading')
    try {
      const tokenRes = await fetch('/api/heygen/token')
      const { token } = await tokenRes.json()
      if (!token) throw new Error('No token received')

      const sdk = await import('@heygen/liveavatar-web-sdk')
      const { LiveAvatarSession, SessionEvent } = sdk as any

      const avatar = new LiveAvatarSession(token, { voiceChat: true })

      avatar.on(SessionEvent.SESSION_STREAM_READY, () => {
        setStatus('ready')
        
        // Attach video track
        if (videoRef.current && avatar._remoteVideoTrack) {
          avatar._remoteVideoTrack.attach(videoRef.current)
        }
        
        // Attach audio track
        if (audioRef.current && avatar._remoteAudioTrack) {
          avatar._remoteAudioTrack.attach(audioRef.current)
        }

        const speakFn = (text: string) => {
          try { avatar.repeat(text) } catch(e) { console.error('Avatar speak error:', e) }
        }
        onAvatarReady(speakFn)
        speakFn('Hello')
      })

      avatar.on(SessionEvent.SESSION_DISCONNECTED, () => {
        setStatus('idle')
      })

      try { await avatar.start() } catch(e: any) { if (!String(e?.message).toLowerCase().includes("micro")) throw e }
      avatarRef.current = avatar
    } catch (err: any) {
      setError(err.message || 'Failed to connect')
      setStatus('error')
    }
  }

  return (
    <div className="relative w-full h-full flex items-center justify-center bg-[#0a0a0f] rounded-3xl overflow-hidden border border-white/5">
      <video
        ref={videoRef}
        autoPlay
        playsInline
        className={`w-full h-full object-cover transition-opacity duration-500 ${status === 'ready' ? 'opacity-100' : 'opacity-0'}`}
      />
      <audio ref={audioRef} autoPlay />

      {status === 'loading' && (
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-4">
          <div className="w-16 h-16 rounded-full bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center animate-pulse">
            <span className="text-white text-2xl font-light">S</span>
          </div>
          <div className="text-xs text-white/30 tracking-widest uppercase">Connecting to Sasha...</div>
        </div>
      )}

      {status === 'idle' && (
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-4">
          <div className="w-16 h-16 rounded-full bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center">
            <span className="text-white text-2xl font-light">S</span>
          </div>
          <button onClick={initAvatar} className="text-xs text-white/30 hover:text-white/60 border border-white/10 px-4 py-2 rounded-full transition-all">
            Connect Avatar
          </button>
        </div>
      )}

      {status === 'error' && (
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-4">
          <div className="w-16 h-16 rounded-full bg-red-500/10 border border-red-500/20 flex items-center justify-center">
            <span className="text-red-400 text-2xl">!</span>
          </div>
          <div className="text-xs text-red-400/60 text-center px-4">{error}</div>
          <button onClick={initAvatar} className="text-xs text-white/30 hover:text-white/60 underline">Try again</button>
        </div>
      )}

      {status === 'ready' && (
        <div className="absolute top-4 right-4">
          <div className="flex items-center gap-1.5 bg-black/40 backdrop-blur-sm px-3 py-1.5 rounded-full border border-white/10">
            <div className={`w-1.5 h-1.5 rounded-full ${isListening ? 'bg-red-400 animate-pulse' : 'bg-emerald-400'}`} />
            <span className="text-xs text-white/40">{isListening ? 'Listening' : 'Live'}</span>
          </div>
        </div>
      )}
    </div>
  )
}
