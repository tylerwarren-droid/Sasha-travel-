'use client'
import { useEffect, useRef, useState, useCallback, RefObject } from 'react'

interface SashaAvatarProps {
  onAvatarReady: (speakFn: (text: string) => void, interruptFn: () => void) => void
  isListening?: boolean
  tokenUrl?: string
  onAvatarSpeakingChange?: (speaking: boolean) => void
  onGate?: (value: boolean) => void
  sentenceQueueRef?: RefObject<string[]>
  getSentenceQueueLength?: () => number
}

export default function SashaAvatar({ onAvatarReady, isListening, tokenUrl = '/api/heygen/token', onAvatarSpeakingChange, onGate, sentenceQueueRef, getSentenceQueueLength }: SashaAvatarProps) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const avatarRef = useRef<any>(null)
  const reconnectTimerRef = useRef<any>(null)
  const keepAliveTimerRef = useRef<any>(null)
  const isReconnecting = useRef(false)
  const isMountedRef = useRef(true)
  const gateTimeoutRef = useRef<any>(null)
  const [status, setStatus] = useState<'idle' | 'loading' | 'ready' | 'error'>('idle')
  const [error, setError] = useState('')
  const [connectionQuality, setConnectionQuality] = useState<'good' | 'bad' | null>(null)

  const initAvatar = useCallback(async () => {
    if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current)
    if (keepAliveTimerRef.current) clearInterval(keepAliveTimerRef.current)
    setStatus('loading')
    setError('')

    // State machine for concurrent speak events (BUG 1+2)
    let active = 0
    let ungateTimer: ReturnType<typeof setTimeout> | undefined

    // Safety timeout wrapper — if gate stays on >15s, force-ungate
    const gate = (value: boolean) => {
      if (value) {
        clearTimeout(gateTimeoutRef.current)
        gateTimeoutRef.current = setTimeout(() => {
          console.log('[GATE] safety timeout — force ungating after 15s')
          onGate?.(false)
          onAvatarSpeakingChange?.(false)
        }, 15000)
      } else {
        clearTimeout(gateTimeoutRef.current)
      }
      onGate?.(value)
    }

    const gateOn = () => {
      clearTimeout(ungateTimer)
      gate(true)
    }

    const gateOffSoon = () => {
      clearTimeout(ungateTimer)
      ungateTimer = setTimeout(() => {
        if (active === 0 && (getSentenceQueueLength?.() ?? 0) === 0) {
          console.log('[GATE] ungating — queue empty, active 0')
          onAvatarSpeakingChange?.(false)
          gate(false)
        }
      }, 500)
    }

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

      // BUG 3 — guard so speak handlers are registered exactly once per avatar instance
      let speakHandlersRegistered = false

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

        if (!speakHandlersRegistered) {
          speakHandlersRegistered = true
          console.log('[HG] registering speak handlers')

          avatar.on(AgentEventsEnum.AVATAR_SPEAK_STARTED, () => {
            active++
            console.log('[GATE] speak started, active:', active)
            onAvatarSpeakingChange?.(true)
            gateOn()
          })

          avatar.on(AgentEventsEnum.AVATAR_SPEAK_ENDED, () => {
            active = Math.max(0, active - 1)
            console.log('[SENTENCE] queue length:', sentenceQueueRef?.current?.length ?? 0, 'active:', active)
            const next = sentenceQueueRef?.current?.shift()
            if (next) {
              // More sentences queued — speak immediately; gateOn() inside speakFn keeps gate on
              speakFn(next)
            } else if (active === 0) {
              gateOffSoon()
            }
          })

          avatar.on(AgentEventsEnum.SESSION_STOPPED, (e: any) => {
            console.log('[LA] session stopped:', e?.stop_reason)
            active = 0
            clearTimeout(ungateTimer)
            gate(false)
            onAvatarSpeakingChange?.(false)
          })

          Object.values(AgentEventsEnum).forEach((evt) => {
            avatar.on(evt as any, (e: any) => console.log('[LA event]', evt, e))
          })
        }
      })

      avatar.on(SessionEvent.SESSION_CONNECTION_QUALITY_CHANGED, (quality: any) => {
        const q = quality?.quality || quality
        setConnectionQuality(q === 'BAD' ? 'bad' : 'good')
        if (q === 'BAD') { try { avatar.updateVideoSettings?.({ quality: 'low' }) } catch(e) {} }
      })

      avatar.on(SessionEvent.SESSION_DISCONNECTED, (reason: any) => {
        clearInterval(keepAliveTimerRef.current)
        active = 0
        clearTimeout(ungateTimer)
        gate(false)
        onAvatarSpeakingChange?.(false)
        console.log('[HG] session disconnected, reason:', reason)
        if (reason === 'MAX_DURATION_REACHED') {
          setError('Session ended — tap to start a new conversation')
          setStatus('error')
          return
        }
        setStatus('idle')
        console.log('[HG] restarting...')
        if (!isReconnecting.current && isMountedRef.current) {
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
      console.log('[HG] sessionId:', avatar.sessionId, 'maxDuration:', avatar.maxSessionDuration)

      const speakFn = (text: string) => {
        try {
          if (active > 0) avatar.interrupt?.()
          gateOn()
          avatar.repeat(text)
        } catch(e) {
          console.error('Avatar speak error:', e)
          gate(false)
        }
      }
      const interruptFn = () => {
        try {
          avatar.interrupt?.()
          active = 0
          clearTimeout(ungateTimer)
          gate(false)
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
    isMountedRef.current = true
    initAvatar()
    return () => {
      isMountedRef.current = false
      clearTimeout(reconnectTimerRef.current)
      clearTimeout(gateTimeoutRef.current)
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
