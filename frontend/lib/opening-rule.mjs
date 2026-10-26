// Sasha 295 · THE OPENING — the ONE place S2's first seconds are defined (held by scripts/opening-rule.test.mjs).
// Tyler, 26 Oct: "sometimes when I go to S2 it's not clear what to do… she sits and looks at you and it's a bit of a stand-off."
// Measured before (390×844 and desktop, signed in): 0–1 s an empty page; 1–6 s her face full size over everything, silent, the only
// action a small mic in the corner; ~6 s "Hey there." — which a phone refuses before a tap, so it became "Tap to hear Sasha".
//
// From page load to the first exchange, every device the same:
//   on load      her still, full size, and ONE action — TALK, with OR_TYPE under it, and STARTERS (each a real tool today, chosen in
//                backend/agapi/s2_home.py). Nothing is said: a browser won't play her before a tap, so nothing waits for one.
//   the tap      inside it, in order: her sound unlocked, the mic started (its permission asked here, by his tap), then her hello
//                (voice.HELLO / HELLO_BACK — "Hi <name> — what shall I book for you?"), its audio fetched before the tap.
//   or type      the box, focused; a starter is sent as his first message. Either ends the opening, with no hello.
//   after        one cue each, on the mic itself (cueOf): listening · thinking · speaking. A refused mic or sound that won't play is
//                said in one line, the box ready (NO_SOUND, the mic's own words) — never a silent face.
// No second welcome over the page, no per-device branch, no timer that shows "ready" before it is.
import { STARTERS } from './capabilities.generated.mjs'
import { voiceOf } from './presence-rule.mjs'

export { STARTERS }
/** The opening's phase in S2Hello: her still, waiting for his tap. */
export const READY = 'ready'
export const TALK = 'Tap to talk to Sasha'
export const OR_TYPE = 'or type'
/** Her one line when her voice can't be played here, after his tap (the mic's refusal has its own words: lib/mic-state). */
export const NO_SOUND = 'My voice won’t play on this device — I’ll answer in writing. Type below.'

/** What the opening draws: the panel (TALK · OR_TYPE · STARTERS) while her arrival waits for his tap — and only then. `full`: she is
 *  drawn full size now (presence) — before her arrival is decided ('off', rule 4 still asking, up to ~2.5 s) the panel is already
 *  there with her, so the first paint never shows her without the action (a tap then is held until the arrival is decided).
 *  @param {{ phase: string, signedIn: boolean | null, started?: boolean, asleep?: boolean, full?: boolean }} s */
export function opening(s) {
  const waits = s.phase === READY || (s.phase === 'off' && !!s.full)
  const panel = s.signedIn === true && waits && !s.started && !s.asleep
  return { panel, speaks: s.phase !== READY && s.phase !== 'off' }
}

/** What a tap on TALK starts, in this order, inside the tap (a phone allows sound and the mic's prompt only there). */
export const ON_TAP = ['unlock', 'mic', 'hello']

export const LISTENING = 'Listening'
export const THINKING = 'Thinking'
export const SPEAKING = 'Speaking'
/** THE ONE CUE (the mic's state and its word): speaking over thinking over listening — each its own look; paused, resting and a
 *  refused mic as presence-rule / mic-state say. From the real state only: her audio playing, a turn in flight, the mic hearing.
 *  @param {{ asleep?: boolean, dormant?: boolean, micLive?: boolean, speaking?: boolean, thinking?: boolean, micNote?: string | null }} s
 *  @returns {{ state: 'paused' | 'speaking' | 'thinking' | 'listening' | 'refused' | 'tap', words: string }} */
export function cueOf(s) {
  const vo = voiceOf(s)
  if (s.asleep) return { state: 'paused', words: vo.words }
  if (s.speaking) return { state: 'speaking', words: SPEAKING }
  if (s.thinking) return { state: 'thinking', words: THINKING }
  if (vo.live) return { state: 'listening', words: LISTENING }
  if (s.micNote) return { state: 'refused', words: vo.words }
  return { state: 'tap', words: vo.words }
}
