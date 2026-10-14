// Sasha 246 item 2 · the pause / sleep button: one tap stops her and the mic; a tap, her face, the mic or typing wakes her.
import test from 'node:test'
import assert from 'node:assert/strict'
import { sleepStep, mayListen, maySpeak, buttonLabel, HERE, AWAKE, ASLEEP } from '../lib/sleep-rule.mjs'

test('one tap: asleep — her speech stops, the mic goes off, her face dims; no "I\'m here"', () => {
  const r = sleepStep(AWAKE, 'tap_pause')
  assert.equal(r.state, ASLEEP)
  assert.deepEqual(r.effects, { stopAudio: true, micOff: true, dim: true, sayHere: false, speakHere: false, releaseFace: true })   // 268: her live face let go
})

test('tap again: awake, says "I\'m here" (spoken when her voice is on)', () => {
  const r = sleepStep(ASLEEP, 'tap_pause')
  assert.equal(r.state, AWAKE)
  assert.equal(r.effects.sayHere, true)
  assert.equal(r.effects.speakHere, true)
  assert.equal(r.effects.dim, false)
  assert.equal(r.effects.micOff, false)
  assert.equal(HERE, "I'm here")
})

test('she also wakes on a tap on her face, a press of the mic, or typing', () => {
  for (const ev of ['tap_face', 'press_mic', 'typed']) {
    const r = sleepStep(ASLEEP, ev)
    assert.equal(r.state, AWAKE, ev)
    assert.equal(r.effects.sayHere, true, ev)
  }
})

test('typing or the mic wakes her with the line shown, not spoken (her reply is coming / they are about to talk)', () => {
  assert.equal(sleepStep(ASLEEP, 'typed').effects.speakHere, false)
  assert.equal(sleepStep(ASLEEP, 'press_mic').effects.speakHere, false)
  assert.equal(sleepStep(ASLEEP, 'tap_face').effects.speakHere, true)
  assert.equal(sleepStep(ASLEEP, 'tap_pause').effects.speakHere, true)
})

test('awake: a face tap, the mic or typing changes nothing here (add, never remove: they do what they always did)', () => {
  for (const ev of ['tap_face', 'press_mic', 'typed']) {
    const r = sleepStep(AWAKE, ev)
    assert.equal(r.state, AWAKE, ev)
    assert.deepEqual(r.effects, { stopAudio: false, micOff: false, dim: false, sayHere: false, speakHere: false, releaseFace: false }, ev)
  }
})

test('an unknown event leaves her as she is; asleep stays dim and deaf', () => {
  const r = sleepStep(ASLEEP, 'something_else')
  assert.equal(r.state, ASLEEP)
  assert.equal(r.effects.dim, true)
  assert.equal(r.effects.micOff, true)
  assert.equal(r.effects.sayHere, false)
  assert.equal(sleepStep(AWAKE, 'something_else').state, AWAKE)
})

test('asleep: never listening, never speaking; the button says what a tap will do', () => {
  assert.equal(mayListen(ASLEEP), false)
  assert.equal(maySpeak(ASLEEP), false)
  assert.equal(mayListen(true), false)
  assert.equal(mayListen(AWAKE), true)
  assert.equal(maySpeak(false), true)
  assert.equal(buttonLabel(false), 'Pause Sasha')
  assert.equal(buttonLabel(true), 'Wake')   // Sasha 268 · item 8: Tyler's words, always shown
})
