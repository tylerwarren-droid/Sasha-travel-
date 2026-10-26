// Sasha 295 · THE FIRST FIVE SECONDS: one action on load, nothing said before his tap, her hello after it, one cue each.
//   node --test scripts/opening-rule.test.mjs
import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { opening, cueOf, READY, TALK, OR_TYPE, STARTERS, ON_TAP, NO_SOUND, LISTENING, THINKING, SPEAKING } from '../lib/opening-rule.mjs'
import { OPENING, openingShown } from '../lib/greeting-rule.mjs'
import { presence, TAP_TO_TALK, PAUSED } from '../lib/presence-rule.mjs'
import { CHIPS } from '../lib/capabilities.generated.mjs'

const hello = readFileSync(new URL('../app/s2/S2Hello.tsx', import.meta.url), 'utf8')
const app = readFileSync(new URL('../app/s2/S2App.tsx', import.meta.url), 'utf8')

test('on load: the panel (one action, "or type", the starters) — for the signed in, while she waits for his tap', () => {
  assert.equal(opening({ phase: READY, signedIn: true }).panel, true)
  assert.equal(opening({ phase: READY, signedIn: true }).speaks, false)   // nothing is said before the tap
  assert.equal(opening({ phase: READY, signedIn: false }).panel, false)
  assert.equal(opening({ phase: READY, signedIn: true, started: true }).panel, false)   // another tab: gone
  assert.equal(opening({ phase: READY, signedIn: true, asleep: true }).panel, false)
  for (const ph of ['off', 'face', 'voice', 'tap', 'bubble', 'faceAgain']) assert.equal(opening({ phase: ph, signedIn: true }).panel, false, ph)
  assert.equal(opening({ phase: 'off', signedIn: true, full: true }).panel, true)    // her first full-size paint carries the action
  assert.equal(opening({ phase: 'off', signedIn: null, full: true }).panel, false)   // not before the sign-in answer (no mic yet)
  assert.equal(opening({ phase: 'bubble', signedIn: true, full: true }).panel, false)
  assert.equal(TALK, 'Tap to talk to Sasha')
  assert.equal(OR_TYPE, 'or type')
})

test('ready is an opening phase: drawn full size (her still), ended by the conversation starting like the rest', () => {
  assert.ok(OPENING.includes(READY))
  assert.equal(openingShown(READY, 'voice', false), 'face')
  assert.equal(openingShown(READY, 'voice', true), null)
  assert.equal(presence({ phase: READY, signedIn: true }).where, 'full')
})

test('the starters are 2–3 of her own chips (backend s2_home.STARTERS) — only things she does today', () => {
  assert.ok(STARTERS.length >= 2 && STARTERS.length <= 3)
  for (const s of STARTERS) assert.ok(CHIPS.includes(s), s)
})

test('the tap, in order: her sound, the mic, her hello — and in the page, nothing before it', () => {
  assert.deepEqual(ON_TAP, ['unlock', 'mic', 'hello'])
  const begin = hello.slice(hello.indexOf('const begin = () => {'), hello.indexOf('const skipTo'))
  assert.ok(begin.indexOf('talker.unlock()') < begin.indexOf('onBegin?.()') && begin.indexOf('onBegin?.()') < begin.indexOf('speakFace()'))
  const arrive = hello.slice(hello.indexOf('const arriveNow = (skip: boolean) => {'), hello.indexOf('const begin = () => {'))
  assert.match(arrive, /to\(READY\)/)
  assert.doesNotMatch(arrive, /speakVoice\(|speakFace\(|sayNow\(/)   // she never speaks on load
  assert.doesNotMatch(arrive, /5000/)                                 // no "not on screen in 5 s" race: nothing waits on her face
  assert.match(arrive, /talker\.prefetch\?\.\(plain\)/)                // her hello's audio fetched before the tap (~1 s after it)
  assert.match(app, /const begin = \(\) => \{ micUsed\.current = true; if \(!asleepRef\.current && !muted && !micLive && !dormant\) voiceCtl\.current\?\.tap\(\) \}/)
})

test('one panel, in her frame — never a second welcome under it', () => {
  assert.equal((hello.match(/data-opening-talk/g) || []).length, 1)
  assert.match(hello, /\{panel \? \(/)
  assert.match(app, /msgs\.length === 0 \? \(openingUp \? null : \(/)
  assert.doesNotMatch(app, /GREETING|chipAt/)   // no fixed welcome line, no rotating eight
  assert.match(app, /if \(helloCtl\.current\?\.waiting\(\)\) void helloCtl\.current\.bye\('', false\)/)   // typed or spoken first: it ends
})

test('one cue each: speaking over thinking over listening; paused and the tap word as before', () => {
  assert.deepEqual(cueOf({ micLive: true }), { state: 'listening', words: LISTENING })
  assert.deepEqual(cueOf({ micLive: true, thinking: true }), { state: 'thinking', words: THINKING })
  assert.deepEqual(cueOf({ micLive: true, thinking: true, speaking: true }), { state: 'speaking', words: SPEAKING })
  assert.deepEqual(cueOf({ asleep: true, speaking: true }), { state: 'paused', words: PAUSED })
  assert.deepEqual(cueOf({}), { state: 'tap', words: TAP_TO_TALK })
  assert.equal(cueOf({ micNote: 'blocked' }).state, 'refused')
  assert.match(app, /data-cue-state=\{cue\.state\}/)
  for (const st of ['speaking', 'thinking']) assert.ok(app.includes(`.s2-mic[data-cue-state="${st}"] button`), st)
  assert.match(hello, /talker\.speaking\?\.\(true\)/)   // her face's line counts as speaking (the cue, the mic's gate)
})

test('mic refused or sound failed: one line, the box ready — never a silent face', () => {
  assert.ok(NO_SOUND.length < 90)
  assert.match(app, /const noSound = \(\) => \{ setSoundNote\(NO_SOUND\); typeBox\.current\?\.focus\(\) \}/)
  assert.match(app, /useEffect\(\(\) => \{ if \(micNote\) typeBox\.current\?\.focus\(\) \}, \[micNote\]\)/)
  assert.match(hello, /if \(r === 'failed'\) onNoSound\?\.\(\)/)
  assert.match(hello, /if \(how === 'failed'\) onNoSound\?\.\(\)/)
})
