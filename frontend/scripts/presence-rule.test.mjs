// Sasha 271 · B/C/D — her on-screen presence is ONE rule (lib/presence-rule.mjs), and /s2 draws her from it.
//   node --test scripts/presence-rule.test.mjs
import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { presence, ring, GREEN } from '../lib/presence-rule.mjs'
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
  assert.equal(P({}).look, 'listening')
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
  assert.match(hello, /const p = presence\(\{ phase, tapFor, started, signedIn, soon, asleep, dormant, reduced: reducedMotion\(\) \}\)/)
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
