// Sasha 271 · B/C/D · HER ON-SCREEN PRESENCE, as ONE rule (held by scripts/presence-rule.test.mjs).
// Everything /s2 draws of her — the arrival, the corner circle, its ring, its paused look, what a tap on her does, and whether her
// mic may listen — comes from presence(). Its inputs are the one state there is: her arrival's phase (S2Hello), the Pause/Wake state
// (lib/sleep-rule.mjs) and her rest (Sasha 231). No second timer or flag decides where she is or how she looks.
//
//   the arrival   half-body, full size: "Hey there" (a return: "Hey <name>"), then at once "I'm turning off my camera, but just speak to
//                 me naturally. You can always tap to get me back." (backend voice.py) — then the corner. Tap the corner: full size.
//   the corner    ALWAYS drawn once she has arrived (signed in): her still, in the voice row's corner on her own tab, else the
//                 screen's bottom-right corner. Never nothing: no tab, no rest, no released live face takes her off the screen.
//   the ring      green while she is awake and listening · a calm, different look while paused (dimmed, no ring, "Wake") · faded at rest.
import { OPENING, openingShown } from './greeting-rule.mjs'
import { buttonLabel, mayListen } from './sleep-rule.mjs'

export const GREEN = '#34d399'
/** @typedef {'full' | 'corner' | 'none'} Where */
/** @typedef {'arriving' | 'listening' | 'paused' | 'resting'} Look */

/**
 * @param {{ phase: string, tapFor?: 'face' | 'voice', started?: boolean, signedIn: boolean | null, soon?: boolean, asleep?: boolean,
 *           dormant?: boolean, reduced?: boolean }} s
 * @returns {{ where: Where, look: Look, card: boolean, tap: 'face_back' | 'wake' | 'collapse' | null, listening: boolean, label: string }}
 */
export function presence(s) {
  const asleep = !!s.asleep, dormant = !!s.dormant
  const listening = mayListen(asleep) && !dormant   // the mic: never while paused (sleep-rule) or at rest
  const label = buttonLabel(asleep)                  // the Pause button's word: "Wake" while paused
  if (s.signedIn === false) return { where: 'none', look: 'resting', card: false, tap: null, listening: false, label }   // her opening is for the signed-in
  const shown = openingShown(s.phase, s.tapFor || 'voice', !!s.started)
  // before the opening's first step: full size at once when this browser holds a sign-in (Sasha 268 — no blank page, no one-tick flip)
  const before = s.phase === 'off' && !s.started && !asleep && !s.reduced && (s.signedIn === true || (s.signedIn === null && !!s.soon))
  if (shown || before) {
    return { where: 'full', look: s.phase === 'faceAgain' ? (listening ? 'listening' : 'paused') : 'arriving', card: shown === 'card',
             tap: s.phase === 'faceAgain' ? 'collapse' : null, listening, label }
  }
  if (s.signedIn !== true && s.phase === 'off') return { where: 'none', look: 'resting', card: false, tap: null, listening: false, label }
  return { where: 'corner', look: asleep ? 'paused' : dormant ? 'resting' : 'listening', card: false, tap: asleep ? 'wake' : 'face_back', listening, label }
}

/** The corner's ring, from presence's look: green awake and listening (brighter while she speaks); paused and resting have none. */
export function ring(look, talking = false) {
  if (look === 'listening') return { border: `2.5px solid ${GREEN}`, glow: `0 0 0 ${talking ? 6 : 4}px rgba(52,211,153,${talking ? 0.4 : 0.25})` }
  if (look === 'paused') return { border: '2px solid rgba(255,255,255,.22)', glow: 'none' }
  return { border: '2px solid rgba(255,255,255,.18)', glow: 'none' }
}

/** Is this phase her arrival (the opening)? Re-exported so S2Hello asks one module. */
export const arriving = (phase) => OPENING.includes(phase)
