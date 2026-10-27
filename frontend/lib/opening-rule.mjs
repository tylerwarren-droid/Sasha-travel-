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
//
// Sasha 296 · COMING BACK, AND "STILL HERE" (Tyler, 26 Oct: "when you come back after say thirty seconds… you have to tap the mic to
// activate and it's just not entirely clear what needs to happen… the user just has to always be informed and know what to do"). The
// same rule, for every state after the first seconds — never a second "resume" screen:
//   returned     the page back (a hidden tab, a locked phone) after AWAY_MS away, short of rule 4's re-arrival (presence-rule
//                reappear): her still full size with ONE action — CONTINUE, OR_TYPE — the same panel, in her frame (phase BACK). His tap:
//                her sound, the mic, then she speaks first, ONE line that picks up where they were (voice.pickup_line).
//   paused       her one action is Wake (sleep-rule): the corner, dimmed, its word, and the page's line.
//   the corner   settle(): the first time in a session her line carries the camera words (voice.CAMERA_OFF); every time after, a pause →
//                "Still here." (ES "Aquí sigo.") → a pause → the circle. Never the full line twice in a session; no live face, no words.
//   her face     always drawn while signed in (presence never 'none'): full size or the corner — paused, listening, thinking, speaking.
// Measured before (390×844 and desktop): back after 30 s or a lock — only the 40 px circle and the mic's small word; on desktop the one
// tap there turned a live mic OFF. Her face sent to the corner: at once and silent (≤0.5 s); her requests: the full camera line every time.
import { STARTERS } from './capabilities.generated.mjs'
import { voiceOf } from './presence-rule.mjs'
import { buttonLabel } from './sleep-rule.mjs'

export { STARTERS }
/** The opening's phase in S2Hello: her still, waiting for his tap. */
export const READY = 'ready'
export const TALK = 'Tap to talk to Sasha'
export const OR_TYPE = 'or type'
/** Her one line when her voice can't be played here, after his tap (the mic's refusal has its own words: lib/mic-state). */
export const NO_SOUND = 'My voice won’t play on this device — I’ll answer in writing. Type below.'

/** Sasha 296 · S2Hello's phase while a return waits for his tap (her still, full size, CONTINUE). */
export const BACK = 'back'
export const CONTINUE = 'Tap to continue'
/** Sasha 296 · away this long (hidden → visible, the page's own two moments) and a return is `returned`; a glance away is nothing. */
export const AWAY_MS = 10000
/** Sasha 296 · the slight pause on both ends of "Still here." — not instantaneous. */
export const PAUSE_MS = 700

/** What the opening draws, and the ONE action of every state: the panel (TALK, or CONTINUE on a return · OR_TYPE · STARTERS on load)
 *  while she waits for his tap — and only then. `full`: she is drawn full size now (presence) — before her arrival is decided ('off',
 *  rule 4 still asking, up to ~2.5 s) the panel is already there with her, so the first paint never shows her without the action (a
 *  tap then is held until the arrival is decided). Sasha 296 · `soon`: this browser holds a sign-in (its cookie) while the page's own
 *  check is still answering — a brand-new guest sees the action with her first paint. `action`: what to do now, in every state —
 *  'talk' · 'continue' (the panel) · 'wake' (paused) · 'cue' (the mic's own word: listening · thinking · speaking · tap).
 *  @param {{ phase: string, signedIn: boolean | null, soon?: boolean, started?: boolean, asleep?: boolean, full?: boolean }} s */
export function opening(s) {
  const back = s.phase === BACK
  const waits = s.phase === READY || back || (s.phase === 'off' && !!s.full)
  const sure = s.signedIn === true || (s.signedIn === null && !!s.soon)
  const panel = sure && waits && !s.started && !s.asleep
  const action = s.asleep ? 'wake' : panel ? (back ? 'continue' : 'talk') : 'cue'
  return { panel, action, words: s.asleep ? buttonLabel(true) : back ? CONTINUE : TALK, starters: panel && !back,
           speaks: !waits && s.phase !== 'off' }
}

/** Sasha 296 · RETURNED: the page is back after `away` ms hidden — not paused (Wake is its action), not at rest, nothing in flight (her
 *  answer is what's there), on her own tab. Rule 4's re-arrival (30 min, a new day, news) is asked first, by the same return handler.
 *  @param {{ away: number, asleep?: boolean, dormant?: boolean, busy?: boolean, here?: boolean }} s */
export function returned(s) {
  return Number(s.away) >= AWAY_MS && !s.asleep && !s.dormant && !s.busy && s.here !== false
}

/** Sasha 296 · INTO THE CORNER, the ONE rule (arrival, a return, his request, a tap on her face): `said` — the camera words have
 *  already been on her lips this session; `live` — her live face is up. The steps S2Hello runs, in order:
 *    'say'    her line (with the camera words when `camera`; alone, CAMERA_OFF itself) · 'hold' HOLD_MS (presence-rule)
 *    'pause'  PAUSE_MS · 'still' "Still here." (voice.STILL_HERE / STILL_HERE_ES)
 *  No live face: no camera words, no "Still here" — the corner at once, her line in her voice (Sasha 281).
 *  @param {{ said: boolean, live: boolean }} s  @returns {{ camera: boolean, steps: ('say' | 'hold' | 'pause' | 'still')[] }} */
export function settle(s) {
  if (!s.live) return { camera: false, steps: [] }
  if (!s.said) return { camera: true, steps: ['say', 'hold'] }
  return { camera: false, steps: ['say', 'pause', 'still', 'pause'] }
}
/** Sasha 296 · this tab's session: the camera words have been on her lips (sessionStorage — a reload of the tab keeps it). */
export const CAMERA_SAID = 's2_camera_said'

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
