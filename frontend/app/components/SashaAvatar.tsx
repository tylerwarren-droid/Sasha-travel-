'use client'
import { useEffect, useRef, useState, useCallback } from 'react'

/**
 * Session-start warmup.
 *
 * This component only mounts on "Tap to start" — by which point the guest is already staring
 * at a loading screen, and only then do we fetch a token and download the SDK chunk. Both are
 * independent of the tap, so we do them WHILE the splash screen is up and the guest is reading
 * it. Minting a token does not start a session (only start() does, and that's what bills), so
 * this costs nothing but saves a round-trip plus a chunk download off the critical path.
 *
 * Module-level because the component doesn't exist yet when we want to start.
 */
/** Never START a session with a token older than this — re-mint instead. */
const PREFETCH_TTL_MS = 60_000
/** Re-mint once the warm token reaches this age. Must be BELOW the TTL: the caller re-warms
 *  on a timer, and if this equalled the TTL every tick would no-op and the token would always
 *  be expired by the time it was used. */
const PREFETCH_REFRESH_MS = 40_000
let _tokenPrefetch: { href: string; at: number; promise: Promise<Response> } | null = null

export function prefetchAvatarSession(href: string): void {
  try {
    // Warm the SDK chunk (idempotent — the bundler caches the module).
    void import('@heygen/liveavatar-web-sdk')
    if (_tokenPrefetch?.href === href && Date.now() - _tokenPrefetch.at < PREFETCH_REFRESH_MS) return
    _tokenPrefetch = { href, at: Date.now(), promise: fetch(href).catch(() => null as any) }
  } catch { /* warmup is best-effort — never let it break the page */ }
}

/** Take a still-fresh prefetched token, once. Stale or already-used ones are ignored so a
 *  retry always mints a new token rather than replaying an expired one. */
function takePrefetchedToken(href: string): Promise<Response> | null {
  const p = _tokenPrefetch
  if (!p || p.href !== href) return null
  _tokenPrefetch = null                                   // single use
  if (Date.now() - p.at > PREFETCH_TTL_MS) return null    // too old to trust
  return p.promise
}

interface SashaAvatarProps {
  onAvatarReady: (speakFn: (text: string) => void, interruptFn: () => void) => void
  isListening?: boolean
  tokenUrl?: string
  onAvatarSpeakingChange?: (speaking: boolean) => void
  onGate?: (value: boolean) => void
  onAvatarSpeechBuffer?: (getText: () => string) => void
  onReadyToListen?: () => void
  onSashaFinished?: () => void
  removeGreen?: boolean
  // When true, the component's built-in top-right status badge (Live/Listening + weak
  // connection) is not rendered — for pages that supply their own call chrome.
  hideStatusBadge?: boolean
}

export default function SashaAvatar({ onAvatarReady, isListening, tokenUrl = '/api/heygen/token', onAvatarSpeakingChange, onGate, onAvatarSpeechBuffer, onReadyToListen, onSashaFinished, removeGreen = true, hideStatusBadge = false }: SashaAvatarProps) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const chromaRafRef = useRef<number>(0)
  const avatarRef = useRef<any>(null)
  const reconnectTimerRef = useRef<any>(null)
  const keepAliveTimerRef = useRef<any>(null)
  const isReconnecting = useRef(false)
  const reconnectAttemptsRef = useRef(0)
  // The real end reason (NO_CREDITS / AVATAR_DELETED / MAX_DURATION_REACHED / …) arrives on
  // the session.stopped event as `stop_reason`; the later disconnect event only carries a
  // generic transport reason. We stash it so the disconnect handler can tell a permanent
  // failure (don't retry — surface it) from a transient drop (reconnect).
  const lastStopReasonRef = useRef<string>('')
  const isMountedRef = useRef(true)
  const safetyTimerRef = useRef<any>(null)
  const trailingTimerRef = useRef<any>(null)
  const avatarSpeechBufferRef = useRef<{ text: string; ts: number }[]>([])
  const hasOpenedMicRef = useRef(false)
  // Single source of truth for "the avatar is mid-response". Drives idempotent gate
  // opening — we deliberately do NOT count speak segments (see speak-handler block).
  const speakingRef = useRef(false)
  // Remote-audio silence release (the definitive fix for dropped speak_ended events): an
  // AnalyserNode on the avatar's own audio track. When she has actually been silent for
  // ~1.1s while speakingRef still says "speaking", the utterance is over regardless of
  // whether LiveAvatar ever delivered the final speak_ended — previously a single dropped
  // event left the mic gated until the 30s greeting watchdog (a ~17s deaf mic after a 13s
  // greeting, which read as "she is not hearing me").
  const audioWatchRef = useRef<any>(null)
  const audioCtxRef = useRef<AudioContext | null>(null)
  const [status, setStatus] = useState<'idle' | 'loading' | 'ready' | 'error'>('idle')
  const [error, setError] = useState('')
  const [connectionQuality, setConnectionQuality] = useState<'good' | 'bad' | null>(null)

  // Cold-start mask. The LiveAvatar session takes ~4s to allocate on HeyGen's side and
  // there is no pre-warm API, so the correct fix is to make that wait feel intentional
  // and on-brand rather than show dead air. We step through reassuring copy instead of a
  // bare spinner so an investor never sees an "is it broken?" moment.
  const WAKE_MESSAGES = ['Waking Sasha up', 'Warming up the connection', 'Almost ready']
  const [wakeIdx, setWakeIdx] = useState(0)
  useEffect(() => {
    if (status !== 'loading') { setWakeIdx(0); return }
    const id = setInterval(() => setWakeIdx(i => Math.min(i + 1, WAKE_MESSAGES.length - 1)), 1800)
    return () => clearInterval(id)
  }, [status])

  const initAvatar = useCallback(async () => {
    if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current)
    if (keepAliveTimerRef.current) clearInterval(keepAliveTimerRef.current)
    setStatus('loading')
    setError('')

    const clearAllTimers = () => {
      clearTimeout(safetyTimerRef.current)
      clearTimeout(trailingTimerRef.current)
    }

    const openGate = () => {
      // Runs its release path exactly ONCE per utterance. Whichever end-detector fires
      // first (quiet debounce, absolute watchdog, or session stop) wins; the rest no-op.
      if (!speakingRef.current) return
      speakingRef.current = false
      clearAllTimers()
      onGate?.(false)
      onAvatarSpeakingChange?.(false)
      onSashaFinished?.()
      if (!hasOpenedMicRef.current) {
        hasOpenedMicRef.current = true
        console.log('[MIC] opening mic')
        onReadyToListen?.()
      }
    }

    // Absolute backstop. Force-opens the mic even if the avatar's final speak_ended is
    // never delivered — the exact failure that used to wedge the conversation.
    const armWatchdog = (ms: number) => {
      clearTimeout(safetyTimerRef.current)
      safetyTimerRef.current = setTimeout(() => {
        console.log('[GATE] watchdog fired — force-opening mic after', ms, 'ms')
        openGate()
      }, ms)
    }

    try {
      // Cross-session memory: pass the prior session id so a returning guest is remembered.
      // OFF by default — enabling it asks LiveAvatar to bootstrap memory at token time, which
      // can add latency / a retry on accounts that can't resolve it. Turn on with
      // NEXT_PUBLIC_ENABLE_MEMORY=true once the account supports Session Memory.
      const memoryOn = process.env.NEXT_PUBLIC_ENABLE_MEMORY === 'true'
      const prev = (memoryOn && typeof window !== 'undefined') ? (localStorage.getItem('sasha_last_session') || '') : ''
      const sep = tokenUrl.includes('?') ? '&' : '?'
      const tokenHref = prev ? `${tokenUrl}${sep}prev_session=${encodeURIComponent(prev)}` : tokenUrl

      // Minting the token and downloading the SDK are INDEPENDENT — they used to run one
      // after the other, so the guest waited for the sum. Run them together and use whatever
      // the splash screen already prefetched.
      const t0 = performance.now()
      const warm = takePrefetchedToken(tokenHref)
      const [tokenRes, sdk] = await Promise.all([
        warm || fetch(tokenHref),
        import('@heygen/liveavatar-web-sdk'),
      ])
      // A prefetch that failed resolves to null — fall back to a live fetch rather than dying.
      const res = (tokenRes as Response | null) || (await fetch(tokenHref))
      const { token } = await res.json()
      const t1 = performance.now()
      console.log(`[HG] token+sdk ${Math.round(t1 - t0)}ms${warm ? ' (prefetched)' : ''}`)
      if (!token) throw new Error('No token received')
      const { LiveAvatarSession, SessionEvent, AgentEventsEnum } = sdk as any

      const avatar = new LiveAvatarSession(token, {
        voiceChat: false,
        video_settings: { quality: 'medium', encoding: 'H264' }
      })
      // Publish the instance BEFORE start() — teardown must always be able to reach it.
      // This used to be assigned only after `await avatar.start()` resolved, so unmounting
      // during HeyGen's ~4s cold start (End Session, or a language switch remounting via
      // key={language}) left the cleanup calling stop() on a null ref. The session then
      // finished starting with nothing alive to stop it: a live, billed avatar running until
      // HeyGen's own max-duration cap, invisible to the user.
      avatarRef.current = avatar

      // BUG 3 — guard so speak handlers are registered exactly once per avatar instance
      let speakHandlersRegistered = false

      avatar.on(SessionEvent.SESSION_STREAM_READY, () => {
        isReconnecting.current = false
        reconnectAttemptsRef.current = 0   // healthy stream — reset the outage streak
        lastStopReasonRef.current = ''
        setStatus('ready')
        setConnectionQuality('good')
        if (videoRef.current) {
          avatar.attach(videoRef.current)
          videoRef.current.play().catch((e: any) => console.warn('Autoplay blocked:', e))
          // Watch the avatar's OWN audio output. Event-independent end-of-speech: if we've
          // heard her audio during this utterance and it's now been quiet for ~1.1s, the
          // utterance is over — release the mic even when the final speak_ended never
          // arrives. `heard` guards the startup latency between speak_started and the
          // first audio frame, so we never release before she has begun talking.
          try {
            const srcObj = videoRef.current.srcObject
            if (srcObj instanceof MediaStream && srcObj.getAudioTracks().length) {
              clearInterval(audioWatchRef.current)
              audioCtxRef.current?.close().catch(() => {})
              const actx = new (window.AudioContext || (window as any).webkitAudioContext)()
              audioCtxRef.current = actx
              const srcNode = actx.createMediaStreamSource(new MediaStream([srcObj.getAudioTracks()[0]]))
              const an = actx.createAnalyser()
              an.fftSize = 512
              srcNode.connect(an)   // analysis only — never routed to the speakers
              const buf = new Float32Array(an.fftSize)
              let heard = false
              let lastLoud = Date.now()
              audioWatchRef.current = setInterval(() => {
                if (!speakingRef.current) { heard = false; lastLoud = Date.now(); return }
                an.getFloatTimeDomainData(buf)
                let s = 0
                for (let i = 0; i < buf.length; i++) s += buf[i] * buf[i]
                const rms = Math.sqrt(s / buf.length)
                if (rms > 0.01) { heard = true; lastLoud = Date.now() }
                else if (heard && Date.now() - lastLoud > 1100) {
                  console.log('[GATE] remote-audio silence — releasing mic (event-independent)')
                  openGate()
                }
              }, 150)
            }
          } catch (e) { console.warn('[GATE] audio watch unavailable:', e) }
        }
        // Clear before reassigning: if the SDK re-fires SESSION_STREAM_READY on the same
        // instance (an internal stream/ICE recovery, no remount), the previous interval would
        // be orphaned and keep pinging keepAlive forever alongside its replacement.
        if (keepAliveTimerRef.current) clearInterval(keepAliveTimerRef.current)
        keepAliveTimerRef.current = setInterval(() => {
          void Promise.resolve(avatar.keepAlive?.()).catch(() => {})
        }, 150000)

        if (!speakHandlersRegistered) {
          speakHandlersRegistered = true
          console.log('[HG] registering speak handlers')

          // One response arrives as one or more sentence SEGMENTS, each with its own
          // speak_started / speak_ended. LiveAvatar does NOT guarantee these fire 1:1 —
          // a speak_ended can be dropped or an extra speak_started can arrive — so we
          // never count segments (a single mismatch would wedge the turn forever).
          // Instead:
          //   speak_started -> definitely speaking; cancel any pending mic-open
          //   speak_ended   -> maybe done; (re)arm a quiet-debounce
          //   debounce elapses with no new speak_started -> open the mic
          // The absolute watchdog (armed in speakFn, or on the opening greeting) is the
          // final backstop if the very last speak_ended is dropped. openGate() is
          // idempotent, so whichever detector fires first opens the mic exactly once.
          const GATE_OPEN_DEBOUNCE = 1000
          // True backstop only — the opening greeting can run ~15-20s, so this must be
          // well beyond it. The normal path opens the mic ~1s after speak_ended; this
          // only fires if speak_ended is never delivered.
          const GREETING_WATCHDOG_MS = 30000

          const scheduleGateOpen = () => {
            clearTimeout(trailingTimerRef.current)
            trailingTimerRef.current = setTimeout(() => {
              console.log('[GATE] avatar quiet — opening mic')
              openGate()
            }, GATE_OPEN_DEBOUNCE)
          }

          avatar.on(AgentEventsEnum.AVATAR_SPEAK_STARTED, () => {
            console.log('[HG] speak started')
            // Whenever Sasha speaks, the mic closes — no matter who started it. This used to
            // only happen inside speakFn(), so an utterance the SDK began on its own (the
            // opening greeting) left the mic open. That was survivable on first mount because
            // VoiceButton's gate defaults closed, but a mid-call language switch remounts ONLY
            // this component: VoiceButton keeps its already-open gate, and Deepgram transcribes
            // Sasha's new greeting and sends it back as if the guest had said it.
            // openGate() is idempotent, so closing here is safe on every segment.
            if (!speakingRef.current) {
              armWatchdog(GREETING_WATCHDOG_MS)   // backstop for an utterance we didn't start
              onGate?.(true)
              onAvatarSpeakingChange?.(true)
            }
            speakingRef.current = true
            clearTimeout(trailingTimerRef.current)  // still speaking — cancel pending open
          })

          avatar.on(AgentEventsEnum.AVATAR_SPEAK_ENDED, () => {
            console.log('[GATE] speak ended — arming quiet debounce')
            // Deliberately do NOT clear the watchdog here — it must survive a dropped
            // final speak_ended. openGate() clears it on the normal path.
            scheduleGateOpen()
          })

          avatar.on(AgentEventsEnum.SESSION_STOPPED, (e: any) => {
            console.log('[LA] session stopped:', e?.stop_reason)
            lastStopReasonRef.current = e?.stop_reason || e?.end_reason || ''
            speakingRef.current = false
            clearAllTimers()
            onGate?.(false)
            onAvatarSpeakingChange?.(false)
            onSashaFinished?.()
          })

          const addToSpeechBuffer = (e: any) => {
            const text = typeof e === 'string' ? e : (e?.text || e?.transcript || '')
            if (text) avatarSpeechBufferRef.current.push({ text, ts: Date.now() })
          }
          avatar.on(AgentEventsEnum.AVATAR_TRANSCRIPTION_CHUNK, addToSpeechBuffer)
          avatar.on(AgentEventsEnum.AVATAR_TRANSCRIPTION, addToSpeechBuffer)

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
        clearAllTimers()
        speakingRef.current = false
        onGate?.(false)
        onAvatarSpeakingChange?.(false)
        onSashaFinished?.()
        const endReason = lastStopReasonRef.current || (typeof reason === 'string' ? reason : reason?.reason || '')
        console.log('[HG] session disconnected, reason:', reason, 'endReason:', endReason)

        // Permanent failures will hit the SAME wall on reconnect — retrying just produces a
        // reconnect storm and a flickering avatar. Surface a clear message instead.
        const PERMANENT = new Set(['MAX_DURATION_REACHED', 'NO_CREDITS', 'AVATAR_DELETED'])
        if (PERMANENT.has(endReason)) {
          const msg = endReason === 'NO_CREDITS' ? 'Session ended — LiveAvatar credits exhausted'
            : endReason === 'AVATAR_DELETED' ? 'This avatar is no longer available'
            : 'Session ended — tap to start a new conversation'
          setError(msg)
          setStatus('error')
          return
        }

        // Transient drop — reconnect, but cap attempts so a hard-down backend can't loop
        // forever (each failed start would re-enter here).
        const MAX_RECONNECTS = 5
        if (reconnectAttemptsRef.current >= MAX_RECONNECTS) {
          setError('Connection lost — tap to try again')
          setStatus('error')
          return
        }
        setStatus('idle')
        if (!isReconnecting.current && isMountedRef.current) {
          isReconnecting.current = true
          reconnectAttemptsRef.current += 1
          const backoff = Math.min(2000 * reconnectAttemptsRef.current, 8000)
          console.log(`[HG] reconnecting (attempt ${reconnectAttemptsRef.current}/${MAX_RECONNECTS}) in ${backoff}ms`)
          reconnectTimerRef.current = setTimeout(() => { Promise.resolve(avatarRef.current?.stop?.()).catch(() => {}); initAvatar() }, backoff)
        }
      })

      avatar.on(SessionEvent.SESSION_START_FAILED, () => {
        clearInterval(keepAliveTimerRef.current)
        setStatus('idle')
        const MAX_RECONNECTS = 5
        if (reconnectAttemptsRef.current >= MAX_RECONNECTS) {
          setError('Could not connect to Sasha — tap to try again')
          setStatus('error')
          return
        }
        if (!isReconnecting.current) {
          isReconnecting.current = true
          reconnectAttemptsRef.current += 1
          reconnectTimerRef.current = setTimeout(() => { Promise.resolve(avatarRef.current?.stop?.()).catch(() => {}); initAvatar() }, 3000)
        }
      })

      await avatar.start()
      console.log(`[HG] session.start ${Math.round(performance.now() - t1)}ms`)
      // Second guard: if we were unmounted WHILE start() was in flight, the cleanup already
      // ran. Its stop() may have been a no-op (the session had no id yet), so stop the now
      // fully-started session here and go no further — no handlers, no onAvatarReady.
      if (!isMountedRef.current) {
        console.log('[HG] unmounted during start — stopping orphaned session')
        void Promise.resolve(avatar.stop?.()).catch(() => {})
        return
      }
      console.log('[HG] sessionId:', avatar.sessionId, 'maxDuration:', avatar.maxSessionDuration)
      // Remember this session so the NEXT one can carry memory forward.
      try { if (avatar.sessionId && typeof window !== 'undefined') localStorage.setItem('sasha_last_session', avatar.sessionId) } catch {}

      onAvatarSpeechBuffer?.(() => {
        const cutoff = Date.now() - 15000
        avatarSpeechBufferRef.current = avatarSpeechBufferRef.current.filter(e => e.ts > cutoff)
        return avatarSpeechBufferRef.current.map(e => e.text).join(' ')
      })

      const speakFn = (text: string) => {
        try {
          clearAllTimers()
          speakingRef.current = true
          onGate?.(true)
          onAvatarSpeakingChange?.(true)
          avatar.repeat(text)
          // Absolute backstop, scaled to response length and hard-capped. Cleared by
          // openGate() on the normal (event-driven) path; only fires if the avatar's
          // speak_ended never arrives.
          const delay = Math.min(30000, Math.max(6000, text.length * 80)) + 2000
          console.log('[GATE] watchdog armed for', delay, 'ms')
          armWatchdog(delay)
        } catch(e) {
          console.error('Avatar speak error:', e)
          openGate()
        }
      }
      const interruptFn = () => {
        try {
          void Promise.resolve(avatar.interrupt?.()).catch(() => {})
          speakingRef.current = false
          clearAllTimers()
          onGate?.(false)
          onAvatarSpeakingChange?.(false)
          onSashaFinished?.()
        } catch(e) {}
      }
      onAvatarReady(speakFn, interruptFn)

    } catch (err: any) {
      setError(err.message || 'Failed to connect')
      setStatus('error')
    }
  }, [tokenUrl, onAvatarReady, onAvatarSpeakingChange, onGate, onAvatarSpeechBuffer, onReadyToListen, onSashaFinished])

  useEffect(() => {
    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible' && status === 'idle') { initAvatar() }
      if (document.visibilityState === 'visible' && videoRef.current) { videoRef.current.play().catch(() => {}) }
    }
    document.addEventListener('visibilitychange', handleVisibilityChange)
    return () => document.removeEventListener('visibilitychange', handleVisibilityChange)
  }, [status, initAvatar])

  // Green-screen removal: the avatar streams on a chroma-green background. We draw each
  // video frame to a canvas and knock out green-dominant pixels so Sasha sits cleanly on
  // the app's dark background instead of a distracting green box.
  useEffect(() => {
    if (!removeGreen || status !== 'ready') return
    const video = videoRef.current
    const canvas = canvasRef.current
    if (!video || !canvas) return
    const ctx = canvas.getContext('2d', { willReadFrequently: true })
    if (!ctx) return
    let running = true
    // Chroma-key ONE frame. EVERYTHING that can throw is inside try/catch so a single bad frame
    // never freezes the avatar; the caller always schedules the next one.
    const processFrame = () => {
      try {
        const w = video.videoWidth, h = video.videoHeight
        if (w && h && video.readyState >= 2) {
          if (canvas.width !== w || canvas.height !== h) { canvas.width = w; canvas.height = h }
          ctx.drawImage(video, 0, 0, w, h)
          const frame = ctx.getImageData(0, 0, w, h)
          const d = frame.data
          for (let i = 0; i < d.length; i += 4) {
            const r = d[i], g = d[i + 1], b = d[i + 2]
            if (g > 90 && g > r * 1.35 && g > b * 1.35) {
              d[i + 3] = 0                                  // green → transparent
            } else if (g > 80 && g > r * 1.1 && g > b * 1.1) {
              d[i + 3] = Math.floor(d[i + 3] * 0.5)         // soft edge / spill
            }
          }
          ctx.putImageData(frame, 0, 0)
        }
      } catch { /* frame not ready / transient — keep looping */ }
    }
    // LIP-SYNC: drive the canvas off requestVideoFrameCallback, not requestAnimationFrame.
    // rVFC fires once per DECODED video frame, on the video's own playback clock — the exact
    // clock its audio plays on — so the chroma-keyed visual can never drift from the voice. rAF
    // is display-refresh driven: under CPU load (this loop does a full-frame getImageData + a
    // per-pixel scan) it processes stale frames and the lips fall behind the real-time audio,
    // which is the "voice doesn't match the visual" lag. Fall back to rAF only where rVFC is
    // missing (older Safari); there the drift can return under load, but sync is preserved on
    // every current browser.
    const vAny = video as any
    if (typeof vAny.requestVideoFrameCallback === 'function') {
      const step = () => { if (!running) return; processFrame(); vAny.requestVideoFrameCallback(step) }
      vAny.requestVideoFrameCallback(step)
    } else {
      const step = () => { if (!running) return; processFrame(); chromaRafRef.current = requestAnimationFrame(step) }
      chromaRafRef.current = requestAnimationFrame(step)
    }
    return () => { running = false; cancelAnimationFrame(chromaRafRef.current) }
  }, [removeGreen, status])

  useEffect(() => {
    isMountedRef.current = true
    initAvatar()
    return () => {
      isMountedRef.current = false
      clearTimeout(reconnectTimerRef.current)
      clearTimeout(safetyTimerRef.current)
      clearTimeout(trailingTimerRef.current)
      clearInterval(keepAliveTimerRef.current)
      clearInterval(audioWatchRef.current)
      audioCtxRef.current?.close().catch(() => {})
      void Promise.resolve(avatarRef.current?.stop?.()).catch(() => {})
    }
  }, [])

  return (
    <div className="relative w-full h-full flex items-center justify-center bg-[#0a0a0f] rounded-3xl overflow-hidden border border-white/5">
      <video
        ref={videoRef}
        autoPlay
        playsInline
        className={`w-full h-full object-cover transition-opacity duration-500 ${status === 'ready' && !removeGreen ? 'opacity-100' : 'opacity-0'}`}
        style={{ objectPosition: 'center 18%' }}
      />
      {removeGreen && (
        <canvas
          ref={canvasRef}
          className={`absolute inset-0 w-full h-full object-cover transition-opacity duration-500 ${status === 'ready' ? 'opacity-100' : 'opacity-0'}`}
          style={{ objectPosition: 'center 18%' }}
        />
      )}
      {status === 'loading' && (
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-5" style={{ background: 'radial-gradient(circle at 50% 40%, #15151f, #0a0a0f)' }}>
          <div className="relative flex items-center justify-center">
            {/* soft expanding halo — reads as "alive / warming up", not "stuck" */}
            <div className="absolute w-24 h-24 rounded-full animate-ping" style={{ background: 'radial-gradient(circle, rgba(218,165,32,0.30), transparent 70%)' }} />
            <div
              className="w-20 h-20 rounded-full flex items-center justify-center"
              style={{ background: 'linear-gradient(135deg, #DAA520, #B8860B)', boxShadow: '0 0 44px rgba(218,165,32,0.45)' }}
            >
              <span className="text-white text-3xl font-light">S</span>
            </div>
          </div>
          <div className="flex flex-col items-center gap-1.5">
            <div className="text-sm text-white/75 tracking-wide transition-opacity duration-300">{WAKE_MESSAGES[wakeIdx]}…</div>
            <div className="text-[11px] text-white/25 tracking-[0.2em] uppercase">Sasha · AI Concierge</div>
          </div>
        </div>
      )}
      {status === 'error' && (
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-4">
          <div className="w-16 h-16 rounded-full bg-red-500/10 border border-red-500/20 flex items-center justify-center">
            <span className="text-red-400 text-2xl">!</span>
          </div>
          <div className="text-xs text-red-400/60 text-center px-4">{error}</div>
          <button
            onClick={() => {
              reconnectAttemptsRef.current = 0
              isReconnecting.current = false
              lastStopReasonRef.current = ''
              // Stop the previous session before starting another. Both AUTOMATIC retry paths
              // already do this; the manual button didn't, so a guest tapping "Try again"
              // could leave the old session running server-side while a new one spun up.
              void Promise.resolve(avatarRef.current?.stop?.()).catch(() => {})
              avatarRef.current = null
              initAvatar()
            }}
            className="text-xs text-white/30 hover:text-white/60 underline"
          >Try again</button>
        </div>
      )}
      {status === 'ready' && !hideStatusBadge && (
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
