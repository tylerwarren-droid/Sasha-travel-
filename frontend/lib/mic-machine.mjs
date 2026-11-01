/**
 * Sasha 322 · THE MIC'S ONE STATE MACHINE — read from the audio pipeline, never a timer or a button flag (docs/sasha/S-322-mic-truth.md).
 *
 *   hears(p)     audio IS reaching her now: the track live and unmuted, the audio running, the socket open, a frame within LIVE_FRAME_MS,
 *                not gated (she isn't talking) and not muted (no turn in flight) — exactly when VoiceButton's frame handler sends — and
 *                the audio LEAVING: nothing stuck in the socket, and the speech service answering within REPLY_MS.
 *   micState(p)  off · connecting · listening · thinking · speaking — from that snapshot and her phase. Listening ⇔ hears(p).
 *
 * The snapshot p: { wanted, connecting, perm, track: 'live'|'ended'|null, trackMuted, audio: 'running'|'suspended'|'closed'|null,
 *                   socket: 'open'|'connecting'|'closed'|null, lastFrameAt, now, gated, muted, asleep, speaking, thinking, deaf,
 *                   lastReplyAt (the speech service's last answer, or when sending (re)started), backlog (bytes queued in the socket) }
 */

/** The words, one place (everywhere the mic is drawn). */
export const MIC_WORDS = Object.freeze({
  off: 'Tap to talk',
  connecting: 'Getting ready…',
  listening: 'Listening',
  thinking: 'Thinking',
  speaking: 'Speaking',
})

/** A frame older than this and the mic is not hearing (a fact about the pipeline, not a label timer). */
export const LIVE_FRAME_MS = 1000
/** The speech service answers audio it receives: measured 1 Nov, a reply every ~1.0 s even in silence (max gap 1,013 ms). No reply for
 *  this long while audio is being sent = the audio is not reaching her (a half-open socket the browser still calls open). */
export const REPLY_MS = 3000
/** Audio queued in the socket and not leaving (bytes; 16 kHz int16 = 32 kB/s): ~1.5 s stuck = not reaching her. */
export const BACKLOG_MAX = 48000

/** @param {Record<string, any>} p */
export function hears(p) {
  return p.perm !== 'denied' && p.track === 'live' && !p.trackMuted && p.audio === 'running' && p.socket === 'open'
    && !!p.lastFrameAt && (p.now - p.lastFrameAt) <= LIVE_FRAME_MS && !p.gated && !p.muted && !p.asleep
    && (p.lastReplyAt == null || (p.now - p.lastReplyAt) <= REPLY_MS) && !((p.backlog || 0) > BACKLOG_MAX)
}

/** @param {Record<string, any>} p @returns {'off'|'connecting'|'listening'|'thinking'|'speaking'} */
export function micState(p) {
  if (p.asleep) return 'off'
  if (hears(p)) return 'listening'          // audio reaching her outranks everything (a barge-in over her voice is Listening)
  if (p.speaking) return 'speaking'         // her voice: the mic paused
  if (p.thinking || p.muted) return 'thinking'   // a turn in flight: the mic paused
  if (p.deaf) return 'off'                  // a live stream that delivered no audio (VoiceButton's deaf check): "Tap to talk", never "ready"
  if (!p.wanted || p.perm === 'denied') return 'off'
  if (p.audio === 'suspended' && !p.connecting) return 'off'   // the phone holds the audio until a tap: "Tap to talk" is the truth
  // wanted and not hearing: something is being brought up (a connect in flight, the socket opening, frames not yet arriving)
  if (p.connecting || p.socket === 'connecting' || p.socket === 'open' || p.track === 'live') return 'connecting'
  return 'off'
}

/** @param {Record<string, any>} p */
export function micWords(p) {
  return MIC_WORDS[micState(p)]
}
