// Sasha 271 · B/C/D — her on-screen presence is ONE rule (lib/presence-rule.mjs), and /s2 draws her from it.
//   node --test scripts/presence-rule.test.mjs
import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { presence, ring, GREEN, reappear, voiceOf, inView, dayOf, HOLD_MS, IDLE_MS, VOICE_ON, TAP_TO_TALK, PAUSED } from '../lib/presence-rule.mjs'
import { OPENING } from '../lib/greeting-rule.mjs'

const P = (o) => presence({ phase: 'bubble', signedIn: true, ...o })

test('the arrival is full size; after it she is ALWAYS the corner — never nothing', () => {
  for (const phase of OPENING) assert.equal(P({ phase }).where, 'full', phase)
  assert.equal(P({ phase: 'off' }).where, 'full')                                     // signed in, before its first step: no flip
  assert.equal(P({ phase: 'off', signedIn: null, soon: true }).where, 'full')          // the cookie says signed in: her frame at once
  for (const o of [{}, { asleep: true }, { dormant: true }, { started: true }, { asleep: true, dormant: true }])
    assert.equal(P(o).where, 'corner', JSON.stringify(o))                              // a tab, Pause, her rest: still the corner
  assert.equal(P({ phase: 'off', started: true }).where, 'corner')                     // another tab at load: the corner at once
  assert.equal(P({ phase: 'off', reduced: true }).where, 'corner')                     // reduced motion: the corner at once
  assert.equal(P({ phase: 'off', signedIn: false }).where, 'none')                     // signed out: her opening is for the signed-in
  assert.equal(P({ phase: 'bubble', signedIn: false }).where, 'none')
})

test('the ring: green awake and listening, a calm paused look with Wake, faded at rest', () => {
  assert.equal(P({ micLive: true }).look, 'listening')   // Sasha 273 · moved: "listening" is the mic actually hearing (was: awake)
  assert.equal(P({}).look, 'idle')                        // awake, the mic not hearing: no green
  assert.match(ring('listening').border, new RegExp(GREEN))
  assert.equal(P({ asleep: true }).look, 'paused')
  assert.doesNotMatch(ring('paused').border, new RegExp(GREEN))
  assert.equal(ring('paused').glow, 'none')
  assert.equal(P({ asleep: true }).label, 'Wake')
  assert.equal(P({}).label, 'Pause Sasha')
  assert.equal(P({ dormant: true }).look, 'resting')
  assert.notEqual(ring('listening', true).glow, ring('listening').glow)                // brighter while she speaks
})

test('a tap: the corner brings her back full size; paused, it wakes her; her face brought back taps back to the corner', () => {
  assert.equal(P({}).tap, 'face_back')
  assert.equal(P({ asleep: true }).tap, 'wake')
  assert.equal(P({ phase: 'faceAgain' }).where, 'full')
  assert.equal(P({ phase: 'faceAgain' }).tap, 'collapse')
  for (const phase of OPENING) assert.equal(P({ phase }).tap, null, phase)           // the arrival takes no tap (it never swallows one)
})

test('the mic follows the same state: never while paused or at rest', () => {
  assert.equal(P({}).listening, true)
  assert.equal(P({ asleep: true }).listening, false)
  assert.equal(P({ dormant: true }).listening, false)
})

test('/s2 draws her from it: one element, measured to the corner, no portal, no second timer, the still after a release', () => {
  const hello = readFileSync(new URL('../app/s2/S2Hello.tsx', import.meta.url), 'utf8')
  assert.match(hello, /const p = presence\(\{ phase, tapFor, started, signedIn, soon, asleep, dormant, reduced: reducedMotion\(\), micLive, arrive \}\)/)   // Sasha 273 · + the mic's truth, rule 4
  assert.match(hello, /const big = p\.where === 'full'/)
  assert.doesNotMatch(hello, /createPortal/)                                          // never drawn into a slot that may not be there
  assert.doesNotMatch(hello, /if \(!slot\) return null/)
  assert.doesNotMatch(hello, /idleLive/)                                              // no "stay full size" timer of the arrival
  assert.match(hello, /c\.dataset\.drawn = '0'/)                                      // letting her live face go shows her still
  assert.match(hello, /SESSION_DISCONNECTED/)                                         // its session ending by itself, too
  assert.match(hello, /\(corner \|\| \(big && !live\)\) && <div aria-hidden data-sasha-still/)
  assert.match(hello, /await arrivalLine\(nameRef\.current \?\? null, back\.current\)/)   // her lines: voice.py's, never the page's own
  assert.doesNotMatch(hello, /WELCOME_BACK|Hey, welcome back!|I'm going to head behind the scenes/)
  const app = readFileSync(new URL('../app/s2/S2App.tsx', import.meta.url), 'utf8')
  assert.match(app, /<span id="s2-face-slot"/)
})

// ── Sasha 273 (rows 1031–1035, Tyler's demo with Jon, 16 Oct) ─────────────────────────────────────────────────────────────────
test('273 · 3: the voice label and the green ring are the mic actually hearing — never a flag', () => {
  assert.deepEqual(voiceOf({ micLive: true }), { live: true, words: VOICE_ON })
  assert.deepEqual(voiceOf({}), { live: false, words: TAP_TO_TALK })                  // back from the background, the mic not live
  assert.deepEqual(voiceOf({ asleep: true, micLive: true }), { live: false, words: PAUSED })
  assert.equal(voiceOf({ dormant: true, micLive: true }).live, false)
  assert.equal(P({ micLive: true }).voice, VOICE_ON)
  assert.equal(P({}).voice, TAP_TO_TALK)
  assert.doesNotMatch(ring('idle').border, new RegExp(GREEN))
  assert.equal(P({ phase: 'faceAgain' }).look, 'idle')
  assert.equal(P({ phase: 'faceAgain', micLive: true }).look, 'listening')
})

test('273 · 4: rule 4 — she reappears and greets only after 30 min quiet, on a new day, or with news; paused stays paused', () => {
  const now = Date.parse('2026-10-16T09:03:17Z'), tz = 'Europe/Madrid'
  assert.equal(reappear({ lastAt: now - 60e3, now, tz }).greet, false)                  // the 11:03 return, mid-booking: nothing
  assert.equal(reappear({ lastAt: now - IDLE_MS + 1000, now, tz }).greet, false)
  assert.deepEqual(reappear({ lastAt: now - 31 * 60e3, now, tz }), { greet: true, lead: 'hello', why: 'idle' })
  assert.deepEqual(reappear({ lastAt: null, now, tz }), { greet: true, lead: 'hello', why: 'idle' })   // a first visit
  const lateNight = Date.parse('2026-10-16T21:55:00Z'), afterMidnight = lateNight + 10 * 60e3   // 23:55 → 00:05 in Madrid
  assert.deepEqual(reappear({ lastAt: lateNight, now: afterMidnight, tz }), { greet: true, lead: 'hello', why: 'new_day' })
  assert.equal(reappear({ lastAt: lateNight, now: afterMidnight, tz: 'America/New_York' }).greet, false)   // the PERSON's zone
  assert.deepEqual(reappear({ lastAt: now - 60e3, now, tz, news: 'You’re booked.' }), { greet: true, lead: 'news', why: 'news' })
  assert.equal(reappear({ lastAt: now - 3 * 3600e3, now, tz, asleep: true }).greet, false)   // paused stays paused
  assert.equal(reappear({ lastAt: now - 60e3, now, tz, news: 'x', asleep: true }).greet, false)
  assert.equal(dayOf(lateNight, tz), '2026-10-16'); assert.equal(dayOf(afterMidnight, tz), '2026-10-17')
  assert.equal(IDLE_MS, 30 * 60 * 1000)
})

test('273 · 1 + 5: the corner only inside the visible viewport; her arrival ends on its speech-ended event, then ~0.5 s', () => {
  const vv = { top: 0, height: 700 }
  assert.equal(inView({ top: 600, width: 40 }, vv), true)
  assert.equal(inView({ top: 680, width: 40 }, vv), false)                              // under a browser's bottom bar
  assert.equal(inView({ top: 600, width: 0 }, vv), false)
  assert.equal(HOLD_MS, 500)
  assert.equal(P({ phase: 'off', arrive: false }).where, 'corner')                       // a quick return: never full size
  assert.equal(P({ phase: 'off', arrive: true }).where, 'full')
  const hello = readFileSync(new URL('../app/s2/S2Hello.tsx', import.meta.url), 'utf8')
  assert.doesNotMatch(hello, /secs \* 1000/)                                            // no duration guessed from the audio's size
  assert.doesNotMatch(hello, /a\.length \* 3\) \/ 4 \/ 48000/)
  assert.match(hello, /AgentEventsEnum\.AVATAR_SPEAK_ENDED/)
  assert.match(hello, /const held = \(\) => new Promise\(r => setTimeout\(r, HOLD_MS\)\)/)
  assert.match(hello, /inView\(/)
  assert.match(hello, /window\.visualViewport/)
})

test('273 · 4 + 5: /s2 greets only from rule 4, has one return handler, and its shell is the dynamic viewport', () => {
  const app = readFileSync(new URL('../app/s2/S2App.tsx', import.meta.url), 'utf8')
  assert.doesNotMatch(app, /\[\.\.\.shown, \{ role: 'sasha', text: line, cards: \[\], restored: true \}\]/)   // the 11:03 append, every load
  assert.match(app, /\.\.\.\(greet \? \[\{ role: 'sasha' as const, text: line/)
  assert.equal((app.match(/addEventListener\('visibilitychange'/g) || []).length, 1)   // ONE return handler (mic + rule 4)
  assert.match(app, /voiceCtl\.current\?\.resume\(\)/)
  assert.match(app, /if \(document\.visibilityState === 'hidden'\) speaker\.interrupt\(\)/)   // never resumes mid-sentence
  assert.match(app, /data-s2-shell style=\{\{ height: '100dvh'/)
  assert.match(app, /paddingBottom: 'calc\(10px \+ env\(safe-area-inset-bottom\)\)'/)
  assert.doesNotMatch(app, /'🔊 Voice on'/)                                              // "Voice" is the mic's word, never the speaker's
  assert.match(app, /voiceOf\(\{ asleep, dormant, micLive \}\)/)
  assert.match(app, /strict ctlRef=\{voiceCtl\} onConnectedChange=\{setMicLive\}/)
})
