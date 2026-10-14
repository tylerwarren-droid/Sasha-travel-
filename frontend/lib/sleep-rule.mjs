// Sasha 246 item 2 · THE PAUSE / SLEEP BUTTON, as a rule (held by scripts/sleep-rule.test.mjs).
// One tap and she is ASLEEP: what she is saying stops mid-word, the mic is off (no capture, no auto-listen, no voice activity),
// her face dims. Tap again — or tap her face, press the mic, type to her — and she wakes with "I'm here".
// The same rule on /s2 (S2App) and /next (the page + SashaChat); each surface carries out the effects with its own parts.

export const AWAKE = 'awake'
export const ASLEEP = 'asleep'
/** Her one line on waking: always shown in the chat; SPOKEN (when her voice is on) for a tap on the button or on her face — not
 *  for typing (her reply is coming) nor for the mic (they are about to talk: she would talk over them, into the open mic). */
export const HERE = "I'm here"

/** @typedef {'awake' | 'asleep'} SleepState */
/** @typedef {'tap_pause' | 'tap_face' | 'press_mic' | 'typed'} SleepEvent */
/** @typedef {{ stopAudio: boolean, micOff: boolean, dim: boolean, sayHere: boolean, speakHere: boolean, releaseFace: boolean }} SleepEffects */

const WAKERS = new Set(['tap_pause', 'tap_face', 'press_mic', 'typed'])

/**
 * The next state and what to do about it.
 * @param {SleepState} state
 * @param {SleepEvent | string} event
 * @returns {{ state: SleepState, effects: SleepEffects }}
 */
export function sleepStep(state, event) {
  const none = { stopAudio: false, micOff: false, dim: false, sayHere: false, speakHere: false, releaseFace: false }
  if (state === ASLEEP && WAKERS.has(event)) {
    return { state: AWAKE, effects: { ...none, sayHere: true, speakHere: event === 'tap_pause' || event === 'tap_face' } }
  }
  if (state !== ASLEEP && event === 'tap_pause') {
    return { state: ASLEEP, effects: { ...none, stopAudio: true, micOff: true, dim: true, releaseFace: true } }   // Sasha 268 · item 8: her live face let go (cost)
  }
  // awake + a face tap / mic press / typing: nothing here — that action does what it always did
  return { state: state === ASLEEP ? ASLEEP : AWAKE, effects: { ...none, micOff: state === ASLEEP, dim: state === ASLEEP } }
}

/** Asleep: never listening (no capture, no auto-listen, no voice activity). @param {SleepState | boolean} s */
export const mayListen = (s) => s !== ASLEEP && s !== true
/** Asleep: nothing is said aloud. @param {SleepState | boolean} s */
export const maySpeak = (s) => s !== ASLEEP && s !== true

/** The button's words — always shown beside its icon (Sasha 268 · item 8, row 954: "The moon icon isn't understood"). @param {boolean} asleep */
export const buttonLabel = (asleep) => (asleep ? 'Wake' : 'Pause Sasha')
/** While paused, said plainly on the page (/s2 under the controls, /next on her stage). */
export const ASLEEP_LINE = 'Sasha is paused — not listening, not talking. Tap Wake to bring her back.'
