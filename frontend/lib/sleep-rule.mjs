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
/** @typedef {{ stopAudio: boolean, micOff: boolean, dim: boolean, sayHere: boolean, speakHere: boolean }} SleepEffects */

const WAKERS = new Set(['tap_pause', 'tap_face', 'press_mic', 'typed'])

/**
 * The next state and what to do about it.
 * @param {SleepState} state
 * @param {SleepEvent | string} event
 * @returns {{ state: SleepState, effects: SleepEffects }}
 */
export function sleepStep(state, event) {
  const none = { stopAudio: false, micOff: false, dim: false, sayHere: false, speakHere: false }
  if (state === ASLEEP && WAKERS.has(event)) {
    return { state: AWAKE, effects: { ...none, sayHere: true, speakHere: event === 'tap_pause' || event === 'tap_face' } }
  }
  if (state !== ASLEEP && event === 'tap_pause') {
    return { state: ASLEEP, effects: { ...none, stopAudio: true, micOff: true, dim: true } }
  }
  // awake + a face tap / mic press / typing: nothing here — that action does what it always did
  return { state: state === ASLEEP ? ASLEEP : AWAKE, effects: { ...none, micOff: state === ASLEEP, dim: state === ASLEEP } }
}

/** Asleep: never listening (no capture, no auto-listen, no voice activity). @param {SleepState | boolean} s */
export const mayListen = (s) => s !== ASLEEP && s !== true
/** Asleep: nothing is said aloud. @param {SleepState | boolean} s */
export const maySpeak = (s) => s !== ASLEEP && s !== true

/** The button's words. @param {boolean} asleep */
export const buttonLabel = (asleep) => (asleep ? 'Wake Sasha' : 'Pause Sasha')
/** Under her face while asleep. */
export const ASLEEP_LINE = 'Asleep — not listening. Tap to wake her.'
