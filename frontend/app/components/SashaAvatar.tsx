'use client'
import { useEffect, useRef, useState, useCallback } from 'react'

interface SashaAvatarProps {
  onAvatarReady: (speakFn: (text: string) => void, interruptFn: () => void) => void
  isListening?: boolean
  tokenUrl?: string
  onAvatarSpeakingChange?: (speaking: boolean) => void
  onGate?: (value: boolean) => void
}

export default function SashaAvatar({ onAvatarReady, isListening, tokenUrl = '/api/heygen/token', onAvatarSpeakingChange, onGate }: SashaAvatarProps) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const avatarRef = useRef<any>(null)
  const reconnectTimerRef = useRef<any>(null)
  const keepAliveTimerRef = useRef<any>(null)
  const isReconnecting = useRef(false)
  const [status, setStatus] = useState<'idle' | 'loading' | 'ready' | 'error'>('idle')
  const [error, setError] = useState('')
  const [connectionQuality, setConnectionQuality] = useState<'good' | 'bad' | null>(null)

  const initAvatar = useCallback(async () => {
    if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current)
    if (keepAliveTimerRef.current) clearInterval(keepAliveTimerRef.current)
    setStatus('loading')
    setError('')
    try {
      const tokenRes = await fetch(tokenUrl)
      const { token } = await tokenRes.json()
      if (!token) throw new Error('No token received')
      const sdk = await import('@heygen/liveavatar-web-sdk')
      const { LiveAvatarSession, SessionEvent, AgentEventsEnum } = sdk as any

      const avatar = new LiveAvatarSession(token, {
        voiceChat: false,
        video_settings: { quality: 'medium', encoding: 'H264' }
      })

      avatar.on(SessionEvent.SESSION_STREAM_READY, () => {
        isReconnecting.current = false
        setStatus('ready')
        setConnectionQuality('good')
        if (videoRef.current) {
          avatar.attach(videoRef.current)
          videoRef.current.play().catch((e: any) => console.warn('Autoplay blocked:', e))
        }
        keepAliveTimerRef.current = setInterval(() => {
          try { avatar.keepAlive?.() } catch(e) {}
        }, 150000)

        avatar.on(AgentEventsEnum.AVATAR_SPEAK_STARTED, () => {
          onAvatarSpeakingChange?.(true)
        })
        avatar.on(AgentEventsEnum.AVATAR_SPEAK_ENDED, () => {
          setTimeout(() => {
            onAvatarSpeakingChange?.(false)
            onGate?.(false)
          }, 400)
        })

        Object.values(AgentEventsEnum).forEach((evt) => {
          avatar.on(evt as any, (e: any) => console.log('[LA event]', evt, e))
        })
      })

      avatar.on(SessionEvent.SESSION_CONNECTION_QUALITY_CHANGED, (quality: any) => {
        const q = quality?.quality || quality
        setConnectionQuality(q === 'BAD' ? 'bad' : 'good')
        if (q === 'BAD') { try { avatar.updateVideoSettings?.({ quality: 'low' }) } catch(e) {} }
      })

      avatar.on(SessionEvent.SESSION_DISCONNECTED, (reason: any) => {
        clearInterval(keepAliveTimerRef.current)
        onAvatarSpeakingChange?.(false)
        onGate?.(false)
        setStatus('idle')
        const shouldReconnect = !isReconnecting.current && (reason === 'UNKNOWN_REASON' || reason === undefined || reason === null)
        if (shouldReconnect) {
          isReconnecting.current = true
          reconnectTimerRef.current = setTimeout(() => { avatarRef.current?.stop?.(); initAvatar() }, 2000)
        }
      })

      avatar.on(SessionEvent.SESSION_START_FAILED, () => {
        clearInterval(keepAliveTimerRef.current)
        setStatus('idle')
        if (!isReconnecting.current) {
          isReconnecting.current = true
          reconnectTimerRef.current = setTimeout(() => { avatarRef.current?.stop?.(); initAvatar() }, 3000)
        }
      })

      await avatar.start()
      avatarRef.current = avatar

      const speakFn = (text: string) => {
        try {
          onGate?.(true)
          avatar.repeat(text)
        } catch(e) { console.error('Avatar speak error:', e) }
      }
      const interruptFn = () => {
        try {
          avatar.interrupt?.()
          onGate?.(false)
          onAvatarSpeakingChange?.(false)
        } catch(e) {}
      }
      onAvatarReady(speakFn, interruptFn)

    } catch (err: any) {
      setError(err.message || 'Failed to connect')
      setStatus('error')
    }
  }, [tokenUrl, onAvatarReady, onAvatarSpeakingChange, onGate])

  useEffect(() => {
    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible' && status === 'idle') { initAvatar() }
      if (document.visibilityState === 'visible' && videoRef.current) { videoRef.current.play().catch(() => {}) }
    }
    document.addEventListener('visibilitychange', handleVisibilityChange)
    return () => document.removeEventListener('visibilitychange', handleVisibilityChange)
  }, [status, initAvatar])

  useEffect(() => {
    initAvatar()
    return () => {
      clearTimeout(reconnectTimerRef.current)
      clearInterval(keepAliveTimerRef.current)
      avatarRef.current?.stop?.()
    }
  }, [])

  return (
    <div className="relative w-full h-full flex items-center justify-center bg-[#0a0a0f] rounded-3xl overflow-hidden border border-white/5">
      <video
        ref={videoRef}
        autoPlay
        playsInline
        className={`w-full h-full object-cover transition-opacity duration-500 ${status === 'ready' ? 'opacity-100' : 'opacity-0'}`}
      />
      {status === 'loading' && (
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-4">
          <div className="w-16 h-16 rounded-full bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center animate-pulse">
            <span className="text-white text-2xl font-light">S</span>
          </div>
          <div className="text-xs text-white/30 tracking-widest uppercase">Connecting to Sasha...</div>
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
        <div className="absolute top-4 right-4 flex flex-col items-end gap-2">
          <div className="flex items-center gap-1.5 bg-black/40 backdrop-blur-sm px-3 py-1.5 rounded-full border border-white/10">
            <div className={`w-1.5 h-1.5 rounded-full ${isListening ? 'bg-red-400 animate-pulse' : 'bg-emerald-400'}`} />
            <span className="text-xs text-white/40">{isListening ? 'Listening' : 'Live'}</span>
          </div>
          {connectionQuality === 'bad' && (
            <div className="flex items-center gap-1.5 bg-black/40 backdrop-blur-sm px-3 py-1.5 rounded-full border border-yellow-500/20">
              <div className="w-1.5 h-1.5 rounded-full bg-yellow-400" />
              <span className="text-xs text-yellow-400/60">Weak connection</span>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
