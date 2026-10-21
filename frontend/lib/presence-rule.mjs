// Sasha 271 · B/C/D · HER ON-SCREEN PRESENCE, as ONE rule (held by scripts/presence-rule.test.mjs).
// Everything /s2 draws of her — the arrival, the corner circle, its ring, its paused look, what a tap on her does, and whether her
// mic may listen — comes from presence(). Its inputs are the one state there is: her arrival's phase (S2Hello), the Pause/Wake state
// (lib/sleep-rule.mjs) and her rest (Sasha 231). No second timer or flag decides where she is or how she looks.
//
//   the arrival   half-body, full size: "Hey there" (a return: "Hey <name>"), then at once "I'm turning my camera off — just talk, or
//                 tap to see me." (backend voice.CAMERA_OFF, Sasha 281: only on her live lips) — then the corner. Tap the corner: full size.
//   the corner    ALWAYS drawn once she has arrived (signed in): her still, in the voice row's corner on her own tab, else the
//                 screen's bottom-right corner. Never nothing: no tab, no rest, no released live face takes her off the screen.
//   the ring      green ONLY while the mic is actually live (Sasha 273) · awake but not hearing: no green, "Tap to talk" · a calm,
//                 different look while paused (dimmed, no ring, "Wake") · faded at rest.
//
// Sasha 273 (rows 1031–1035, Tyler's demo with Jon, 16 Oct) — four more inputs, each the REAL state, never a flag or a guess:
//   micLive       VoiceButton's `hearing`: a live, unmuted track delivering frames NOW (AudioContext running). The voice row's label
//                 ("Voice on" / "Tap to talk") and the green ring are this and nothing else — "Voice on" was her speaker toggle, shown
//                 while the mic was dead after a return (row 1034).
//   speech ended  her arrival leaves full size only on her line's own speech-ended event (her face: LiveAvatar's AVATAR_SPEAK_ENDED;
//                 her voice: the audio's `ended`), then HOLD_MS, then the corner — never a duration guessed from the audio's size.
//   the viewport  the corner sits inside the VISIBLE viewport (visualViewport): never under a browser's bottom bar (row 1035 · 5).
//   last activity reappear() — rule 4 (Tyler, 16 Oct): she reappears and greets ONLY after 30 minutes with no activity, on a new day
//                 in the person's time zone, or with news (which she leads with). A quick return mid-conversation: nothing.
import { OPENING, openingShown } from './greeting-rule.mjs'
import { buttonLabel, mayListen } from './sleep-rule.mjs'

export const GREEN = '#34d399'
/** Sasha 273 · item 1: after her line's speech-ended event, she holds this long, then goes to the corner. */
export const HOLD_MS = 500
/** Sasha 273 · item 4 (a): this long with no activity, and a return is a new arrival (she reappears and greets). */
export const IDLE_MS = 30 * 60 * 1000
/** @typedef {'full' | 'corner' | 'none'} Where */
/** @typedef {'arriving' | 'listening' | 'idle' | 'paused' | 'resting'} Look */

/** Sasha 273 · item 3: the voice row's words, from the mic's REAL state — never "on" while it isn't hearing. */
export const VOICE_ON = 'Voice on'
export const TAP_TO_TALK = 'Tap to talk'
export const PAUSED = 'Paused'
/** The voice row's label and whether her mic is hearing — the ONE derivation (presence() uses it; /s2's voice row shows it).
 *  @param {{ asleep?: boolean, dormant?: boolean, micLive?: boolean }} s */
export function voiceOf(s) {
  const live = mayListen(!!s.asleep) && !s.dormant && !!s.micLive
  return { live, words: s.asleep ? PAUSED : live ? VOICE_ON : TAP_TO_TALK }
}

/**
 * @param {{ phase: string, tapFor?: 'face' | 'voice', started?: boolean, signedIn: boolean | null, soon?: boolean, asleep?: boolean,
 *           dormant?: boolean, reduced?: boolean, micLive?: boolean, arrive?: boolean }} s
 * @returns {{ where: Where, look: Look, card: boolean, tap: 'face_back' | 'wake' | 'collapse' | null, listening: boolean, label: string,
 *             voice: string }}
 */
export function presence(s) {
  const asleep = !!s.asleep, dormant = !!s.dormant
  const listening = mayListen(asleep) && !dormant   // the mic MAY listen: never while paused (sleep-rule) or at rest
  const { live, words: voice } = voiceOf(s)         // Sasha 273 · and it IS hearing, now
  const label = buttonLabel(asleep)                  // the Pause button's word: "Wake" while paused
  if (s.signedIn === false) return { where: 'none', look: 'resting', card: false, tap: null, listening: false, label, voice }   // her opening is for the signed-in
  const shown = openingShown(s.phase, s.tapFor || 'voice', !!s.started)
  // before the opening's first step: full size at once when this browser holds a sign-in (Sasha 268 — no blank page, no one-tick flip)
  // — Sasha 273 · unless rule 4 has already said this is no arrival (a quick return mid-conversation): then never full size
  const before = s.phase === 'off' && !s.started && !asleep && !s.reduced && s.arrive !== false && (s.signedIn === true || (s.signedIn === null && !!s.soon))
  if (shown || before) {
    return { where: 'full', look: s.phase === 'faceAgain' ? (live ? 'listening' : listening ? 'idle' : 'paused') : 'arriving', card: shown === 'card',
             tap: s.phase === 'faceAgain' ? 'collapse' : null, listening, label, voice }
  }
  if (s.signedIn !== true && s.phase === 'off') return { where: 'none', look: 'resting', card: false, tap: null, listening: false, label, voice }
  // Sasha 281 · her voice alone ('voice') is said from the corner; a tap mid-line would bring her face back under a line it isn't saying
  return { where: 'corner', look: asleep ? 'paused' : dormant ? 'resting' : live ? 'listening' : 'idle', card: false, tap: s.phase === 'voice' ? null : asleep ? 'wake' : 'face_back',
           listening, label, voice }
}

/** The corner's ring, from presence's look: green only while the mic hears (brighter while she speaks); idle, paused and resting have none.
 *  Sasha 279 · A · `working` (the stream's {"type": "working", "on"} — the SAME state that stops her "working on it" lines, backend
 *  voice.progress_due): while she works, the ring she has glows brighter and softer in a slow pulse (`pulse`: the keyframes'
 *  name, WORK_PULSE), and stops when she answers. Never while paused or resting. The green stays the mic's truth (Sasha 273).
 *  @returns {{ border: string, glow: string, pulse: string | null }} */
export const WORK_PULSE = 's2-work-pulse'
export const WORK_PULSE_S = 2.4
export function ring(look, talking = false, working = false) {
  const pulse = working && (look === 'listening' || look === 'idle') ? WORK_PULSE : null
  if (look === 'listening') return { border: `2.5px solid ${GREEN}`, glow: `0 0 0 ${talking ? 6 : 4}px rgba(52,211,153,${talking ? 0.4 : 0.25})`, pulse }
  if (look === 'paused') return { border: '2px solid rgba(255,255,255,.22)', glow: 'none', pulse: null }
  if (look === 'idle') return { border: '2px solid rgba(255,255,255,.35)', glow: 'none', pulse }
  return { border: '2px solid rgba(255,255,255,.18)', glow: 'none', pulse: null }
}
/** The pulse's keyframes (one place): the ring's glow brighter, then softer, slowly. */
export const WORK_PULSE_CSS = `@keyframes ${WORK_PULSE}{0%,100%{box-shadow:0 0 0 3px rgba(52,211,153,.18)}50%{box-shadow:0 0 0 9px rgba(52,211,153,.5)}}`

/** Sasha 273 · item 4 · WHEN SHE REAPPEARS — rule 4, the ONE place it is decided (an arrival at load, and a return to the page).
 *  She reappears and greets only when (a) IDLE_MS have passed with no activity, (b) it is a new day in the person's time zone, or
 *  (c) she has news since their last activity — then she leads with it. Paused stays paused. No activity known (a first visit): (a).
 *  @param {{ lastAt: number | null, now: number, tz?: string, news?: string | null, asleep?: boolean, midFlow?: boolean }} s
 *  @returns {{ greet: boolean, lead: 'news' | 'hello' | null, why: 'paused' | 'news' | 'mid_booking' | 'idle' | 'new_day' | 'active' }} */
export function reappear(s) {
  if (s.asleep) return { greet: false, lead: null, why: 'paused' }
  if (s.news) return { greet: true, lead: 'news', why: 'news' }
  // Sasha 274 · item 1 (row 1061, Tyler's iPhone 14:48): after 30 quiet minutes she greeted UNDER her own unanswered booking question
  // ("…Trebbiano, today at 21:00. Shall I call them now?" → "Hey Tyler, what can I help you with?"). Mid-booking — her question still
  // waiting for their answer (greeting-rule.mjs midFlow, or the record's pending) — she never greets: the question is what's there.
  if (s.midFlow) return { greet: false, lead: null, why: 'mid_booking' }
  if (!s.lastAt || !Number.isFinite(s.lastAt) || s.now - s.lastAt >= IDLE_MS) return { greet: true, lead: 'hello', why: 'idle' }
  if (dayOf(s.lastAt, s.tz) !== dayOf(s.now, s.tz)) return { greet: true, lead: 'hello', why: 'new_day' }
  return { greet: false, lead: null, why: 'active' }
}

/** The calendar day of `ms` in time zone `tz` (the device's own when not given) — "2026-10-16". */
export function dayOf(ms, tz) {
  try { return new Intl.DateTimeFormat('en-CA', { timeZone: tz || undefined, year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date(ms)) }
  catch { return new Intl.DateTimeFormat('en-CA', { year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date(ms)) }
}

/** Sasha 273 · items 1 + 5: may the corner sit on this spot? Only inside the VISIBLE viewport (a browser's bottom bar is outside it).
 *  @param {{ top: number, bottom: number, width: number }} r  @param {{ top: number, height: number }} vv  the visual viewport */
export function inView(r, vv, size = 40) {
  return !!r && r.width > 0 && r.top >= vv.top && r.top + size <= vv.top + vv.height
}

/** Sasha 281 (Tyler, 21 Oct 17:58: "Hey Tyler, I'm turning off my camera" — her mouth didn't move) · HOW A LINE IS SAID, the ONE
 *  rule S2Hello's speak() reads. Only audio handed to her live face (Face.say → repeatAudio) moves her lips, so:
 *    her live face is on screen → 'face' (lip-synced);
 *    otherwise → 'corner': she goes to the corner and the line is her voice alone — NEVER a line over a big still or a frozen face.
 *  @param {{ live: boolean }} s  live: her live face is up and drawing
 *  @returns {'face' | 'corner'} */
export function speakVia(s) {
  return s && s.live ? 'face' : 'corner'
}
/** Sasha 281 · THE CAMERA LINE ONLY WHEN THERE IS A CAMERA: her arrival / news / bye line carries voice.CAMERA_OFF only when her
 *  live face is the one saying it; else the line alone ("Hey Tyler."), never "turning off my camera" with no camera on.
 *  @param {string} lead  @param {string} cameraOff  @param {boolean} live */
export function withCamera(lead, cameraOff, live) {
  const l = String(lead || '').trim()
  const said = l && !/[.!?]$/.test(l) ? `${l}.` : l
  return live && cameraOff ? (said ? `${said} ${cameraOff}` : cameraOff) : said
}

/** Is this phase her arrival (the opening)? Re-exported so S2Hello asks one module. */
export const arriving = (phase) => OPENING.includes(phase)
