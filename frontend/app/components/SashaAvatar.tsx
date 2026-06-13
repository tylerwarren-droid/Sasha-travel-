'use client'
import { useEffect, useRef, useState, useCallback } from 'react'

interface SashaAvatarProps {
  onAvatarReady: (speak: (text: string) => void) => void
  isListening?: boolean
  tokenUrl?: string
}

export default function SashaAvatar({ onAvatarReady, isListening, tokenUrl = '/api/heygen/token' }: SashaAvatarProps) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const avatarRef = useRef<any>(null)
  const reconnectTimerRef = useRef<any>(null)
  const keepAliveTimerRef = useRef<any>(null)
  const isReconnecting = useRef(false)
  const [status, setStatus] = useState<'idle' | 'loading' | 'ready' | 'error'>('idle')
  const [error, setError] = useState('')
  const [connectionQuality, setConnectionQuality] = useState<'good' | 'bad' | null>(null)

  // ─────────────────────────────────────────────
  // INIT AVATAR
  // ─────────────────────────────────────────────
  const initAvatar = useCallback(async () => {
    // Clear any existing timers
    if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current)
    if (keepAliveTimerRef.current) clearInterval(keepAliveTimerRef.current)

    setStatus('loading')
    setError('')

    try {
      const tokenRes = await fetch(tokenUrl)
      const { token } = await tokenRes.json()
      if (!token) throw new Error('No token received')

      const sdk = await import('@heygen/liveavatar-web-sdk')
      const { LiveAvatarSession, SessionEvent } = sdk as any

      // Pin to current SDK behavior — lower video quality for TCP fallback resilience
      const avatar = new LiveAvatarSession(token, {
        voiceChat: true,
        video_settings: {
          quality: 'medium',   // HeyGen recommendation: medium survives TCP fallback far better than high
          encoding: 'H264',    // HeyGen recommendation: H264 is most reliable on Safari
        }
      })

      // ── Stream ready ──
      avatar.on(SessionEvent.SESSION_STREAM_READY, () => {
        try { avatar.interrupt?.() } catch(e) {}
        isReconnecting.current = false
        setStatus('ready')
        setConnectionQuality('good')

        if (videoRef.current) {
          // iOS Safari fix: attach stream, keep muted initially, then unmute on user gesture
          avatar.attach(videoRef.current)
          videoRef.current.muted = true
          videoRef.current.play()
            .then(() => {
              // Unmute after successful play — works around Safari autoplay gating
              if (videoRef.current) videoRef.current.muted = false
            })
            .catch((e: any) => {
              // Safari blocked autoplay — stay muted, user gesture will unmute
              console.warn('Autoplay blocked, staying muted until user interaction:', e)
            })
        }

        // Keep-alive ping every 2.5 minutes to avoid idle timeout
        keepAliveTimerRef.current = setInterval(() => {
          try { avatar.ping?.() } catch(e) {}
        }, 150000)
      })

      // ── Connection quality ──
      avatar.on(SessionEvent.SESSION_CONNECTION_QUALITY_CHANGED, (quality: any) => {
        const q = quality?.quality || quality
        console.log('[Avatar] Connection quality:', q)
        setConnectionQuality(q === 'BAD' ? 'bad' : 'good')

        // On bad connection, lower video quality further
        if (q === 'BAD') {
          try { avatar.updateVideoSettings?.({ quality: 'low' }) } catch(e) {}
        }
      })

      // ── Disconnected ──
      avatar.on(SessionEvent.SESSION_DISCONNECTED, (reason: any) => {
        console.log('[Avatar] Disconnected, reason:', reason)
        clearInterval(keepAliveTimerRef.current)
        setStatus('idle')

        // Auto-reconnect on network drops (not on intentional stops)
        const shouldReconnect =
          !isReconnecting.current &&
          (reason === 'UNKNOWN_REASON' || reason === undefined || reason === null)

        if (shouldReconnect) {
          console.log('[Avatar] Network drop detected — reconnecting in 2s...')
          isReconnecting.current = true
          reconnectTimerRef.current = setTimeout(() => {
            avatarRef.current?.stop?.()
            initAvatar()
          }, 2000)
        }
      })

      // ── Session start failed (timeout) ──
      avatar.on(SessionEvent.SESSION_START_FAILED, () => {
        console.log('[Avatar] Session start failed — retrying in 3s...')
        clearInterval(keepAliveTimerRef.current)
        setStatus('idle')
        if (!isReconnecting.current) {
          isReconnecting.current = true
          reconnectTimerRef.current = setTimeout(() => {
            avatarRef.current?.stop?.()
            initAvatar()
          }, 3000)
        }
      })

      await avatar.start()
      avatarRef.current = avatar

      const speakFn = (text: string) => {
        try { avatar.repeat(text, { rate: 0.85 }) } catch(e) { console.error('Avatar speak error:', e) }
      }
      onAvatarReady(speakFn)

    } catch (err: any) {
      setError(err.message || 'Failed to connect')
      setStatus('error')
    }
  }, [tokenUrl, onAvatarReady])

  // ─────────────────────────────────────────────
  // iOS SAFARI: handle backgrounding + screen lock
  // Reconnect when tab becomes visible again
  // ─────────────────────────────────────────────
  useEffect(() => {
    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible' && status === 'idle') {
        console.log('[Avatar] Tab resumed — reconnecting...')
        initAvatar()
      }

      // iOS Safari: unmute video on visibility restore (Safari re-gates audio on resume)
      if (document.visibilityState === 'visible' && videoRef.current) {
        videoRef.current.play().catch(() => {})
      }
    }

    document.addEventListener('visibilitychange', handleVisibilityChange)
    return () => document.removeEventListener('visibilitychange', handleVisibilityChange)
  }, [status, initAvatar])

  // ─────────────────────────────────────────────
  // iOS SAFARI: unmute on user tap anywhere on video
  // Handles the "video plays, no audio" case
  // ─────────────────────────────────────────────
  const handleVideoTap = () => {
    if (videoRef.current && videoRef.current.muted) {
      videoRef.current.muted = false
      videoRef.current.play().catch(() => {})
    }
  }

  // ─────────────────────────────────────────────
  // INIT + CLEANUP
  // ─────────────────────────────────────────────
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
        muted          // Start muted — Safari requires this for autoplay, unmuted after play()
        onClick={handleVideoTap}
        onTouchEnd={handleVideoTap}
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
