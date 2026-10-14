/**
 * Sasha 267 · THE ONE AUDIO SESSION (iOS Safari's navigator.audioSession). Tyler's iPhone (14 Oct 20:01, /s2, her voice on) reported
 * — through the mic's own log — getUserMedia refused 4 ms after "permission: prompt" with InvalidStateError "AudioSession category is
 * not compatible with audio capture": her voice's unlock() set the page's session to "playback" on every tap, the mic's own tap
 * included, and iOS then refuses the microphone without ever asking. Two parts of the page each assumed their own audio mode.
 *
 * ONE owner: the page's session is "play-and-record" — set before her face or voice starts, before any mic request, re-asserted after
 * the avatar connects — and nothing sets it to anything else. Her voice and his mic coexist. Where the API doesn't exist (every
 * browser but Safari 16.4+), a no-op.
 */
import { report } from '@/lib/mic-state'

export const PLAY_AND_RECORD = 'play-and-record'

type Session = { type: string }

function session(): Session | null {
  try {
    return (navigator as unknown as { audioSession?: Session }).audioSession ?? null
  } catch {
    return null
  }
}

/** The page's audio session as "play-and-record" (`why`: who asked — her voice, her face, the mic). → the type now, or null (no API). */
export function holdPlayAndRecord(why: string): string | null {
  const s = session()
  if (!s) return null
  try {
    if (s.type !== PLAY_AND_RECORD) {
      const was = s.type
      s.type = PLAY_AND_RECORD
      report('audio_session', { state: `${was} → ${s.type}`, why })
    }
  } catch (e) {
    report('audio_session', { name: (e as Error).name, message: (e as Error).message, why })
  }
  return s.type
}

/** The page's audio session type now ("auto" | "playback" | "play-and-record" | …), or null where the browser has none. */
export function audioSessionType(): string | null {
  return session()?.type ?? null
}
