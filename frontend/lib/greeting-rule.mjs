// Sasha 251 · THE GREETING, as a rule (held by scripts/greeting-rule.test.mjs).
// /s2's opening — her face saying hello, or the card with her line ("Hey <first name>, what can I help you with?") and
// "Tap to hear Sasha" — shows on arrival and is gone the moment the conversation starts: they send a message, tap a chip or a
// card, or speak; or the conversation they come back to already has their turns in it. It never sits over the conversation.
// (Found live: a phone that blocked sound kept the card, with its tap button, over the messages and place cards for the whole
// visit — it only went away on that tap.) Every way of starting already unlocks her voice itself (speaker.unlock on the tap),
// so nothing is lost when the card goes.

/** @typedef {'off' | 'starting' | 'face' | 'faceLate' | 'voice' | 'tap' | 'bubble' | 'faceAgain'} HelloPhase */

/** The opening's own phases: the ones that end when the conversation starts. ('faceAgain' is their own tap on the bubble.) */
export const OPENING = ['starting', 'face', 'faceLate', 'voice', 'tap']

/** The conversation has started once there is a turn of THEIRS in it (sent, tapped, spoken, or restored from last time).
 *  Her own lines alone (the hello, "I'm here", a proactive note) do not start it.
 *  @param {{ role: string }[]} msgs */
export function conversationStarted(msgs) {
  return Array.isArray(msgs) && msgs.some(m => m && m.role === 'user')
}

/** Sasha 265 · item 2 (row 936): EVERY arrival plays the opening — a return included. Turns restored from last time (marked
 *  `restored`) are the conversation they come back to, not a turn of this visit: only a turn taken NOW ends the opening.
 *  @param {{ role: string, restored?: boolean }[]} msgs */
export function arrivalStarted(msgs) {
  return conversationStarted((Array.isArray(msgs) ? msgs : []).filter(m => m && !m.restored))
}

/** What the opening draws now: her big face, the line card, or nothing.
 *  @param {HelloPhase} phase  @param {'face' | 'voice'} tapFor  @param {boolean} started
 *  @returns {'face' | 'card' | null} */
export function openingShown(phase, tapFor, started) {
  if (phase === 'faceAgain') return 'face'   // their own tap on the bubble: her face back, by their choice
  if (started || !OPENING.includes(phase)) return null
  // Sasha 281 · her voice alone ('voice') is said from the CORNER (presence-rule speakVia): never her big still while she speaks
  if (phase === 'voice') return null
  if (phase === 'tap' && tapFor === 'voice') return 'card'
  return 'face'   // starting (still invisible), face, faceLate, tap on her face
}

/** True when the opening is up (or on its way) and the conversation has started: it ends now — to the bubble.
 *  @param {HelloPhase} phase  @param {boolean} started */
export function openingEnds(phase, started) {
  return !!started && OPENING.includes(phase)
}

/** Sasha 274 · item 1: MID-BOOKING, from what is on the screen — her last line is a question still waiting for their answer, or a
 *  card that asks (a read-back with its choices, a no-answer's one question). Then rule 4 never greets (presence-rule.mjs reappear),
 *  and a new release waits (S2App's safe moment). Their own last turn, or her plain statement, is not mid-booking.
 *  @param {{ role: string, text?: string, cards?: { k: string, choices?: unknown[] }[] }[]} msgs */
export function midFlow(msgs) {
  const last = (Array.isArray(msgs) ? msgs : []).filter(m => m && (m.text || (m.cards && m.cards.length))).at(-1)
  if (!last || last.role === 'user') return false
  if ((last.cards || []).some(c => c && (c.k === 'no_answer' || (c.k === 'read_back' && Array.isArray(c.choices) && c.choices.length)))) return true
  return /\?\s*[)"”’']*\s*$/.test(String(last.text || '').replace(/[…\s]+$/, ''))
}
