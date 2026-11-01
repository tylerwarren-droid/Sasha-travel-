// Sasha 322 · the mic's one state machine (lib/mic-machine.mjs): Listening ⇔ audio reaching her, read from the pipeline.
// Root test (3): can the screen say "Listening" while no audio reaches her, or the reverse? Every snapshot below answers no.
import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { hears, micState, MIC_WORDS, LIVE_FRAME_MS, REPLY_MS } from '../lib/mic-machine.mjs'

const NOW = 100000
const LIVE = { wanted: true, connecting: false, perm: 'granted', track: 'live', trackMuted: false, audio: 'running', socket: 'open',
  lastFrameAt: NOW - 50, now: NOW, gated: false, muted: false, asleep: false, speaking: false, thinking: false }

test('listening only when every part of the pipeline is up and frames arrive now', () => {
  assert.equal(micState(LIVE), 'listening')
  for (const [k, v] of [['track', 'ended'], ['trackMuted', true], ['audio', 'suspended'], ['audio', 'closed'], ['socket', 'closed'],
                        ['socket', 'connecting'], ['lastFrameAt', NOW - LIVE_FRAME_MS - 1], ['lastFrameAt', 0], ['perm', 'denied'],
                        ['gated', true], ['muted', true], ['asleep', true]]) {
    assert.notEqual(micState({ ...LIVE, [k]: v }), 'listening', `${k}=${v} must not be Listening`)
    assert.equal(hears({ ...LIVE, [k]: v }), false)
  }
})

test('the reverse: frames being sent (hears) is always shown as Listening, even over her voice (a barge-in)', () => {
  assert.equal(micState({ ...LIVE, speaking: true }), 'listening')
  assert.equal(micState({ ...LIVE, thinking: true }), 'listening')
})

test('a dropped stream falls back at once — never a stale Listening', () => {
  assert.equal(micState({ ...LIVE, socket: 'closed', connecting: true }), 'connecting')     // the socket reconnecting
  assert.equal(micState({ ...LIVE, socket: 'closed', track: 'live' }), 'connecting')        // pipeline up, socket coming back
  assert.equal(micState({ ...LIVE, wanted: false, socket: null, track: null, audio: null }), 'off')
  assert.equal(micState({ ...LIVE, lastFrameAt: NOW - 1500 }), 'connecting')                // frames stopped: not Listening
  assert.equal(micState({ ...LIVE, audio: 'suspended' }), 'off')                            // the phone wants a tap: Tap to talk
  assert.equal(micState({ ...LIVE, lastFrameAt: 0, deaf: true }), 'off')                    // no audio from a live stream: Tap to talk
})

test('a socket the browser calls open but that takes no audio away, or gets no answer, is not Listening', () => {
  assert.equal(micState({ ...LIVE, lastReplyAt: NOW - 500 }), 'listening')
  assert.equal(micState({ ...LIVE, lastReplyAt: NOW - 3500 }), 'connecting')     // no answer for > REPLY_MS: half-open
  assert.equal(micState({ ...LIVE, backlog: 100000 }), 'connecting')             // the audio queued, not leaving (the network gone)
})

test('her phases: speaking and thinking pause the mic and say so; asleep is off', () => {
  assert.equal(micState({ ...LIVE, gated: true, speaking: true }), 'speaking')
  assert.equal(micState({ ...LIVE, muted: true, thinking: true }), 'thinking')
  assert.equal(micState({ ...LIVE, muted: true }), 'thinking')
  assert.equal(micState({ ...LIVE, asleep: true, speaking: true }), 'off')
})

test('connecting while a connect is in flight; off when nobody asked', () => {
  const fresh = { ...LIVE, connecting: true, track: null, audio: 'running', socket: null, lastFrameAt: 0 }
  assert.equal(micState(fresh), 'connecting')
  assert.equal(micState({ ...fresh, connecting: false, wanted: false }), 'off')
})

test('the words, one place', () => {
  assert.deepEqual(MIC_WORDS, { off: 'Tap to talk', connecting: 'Getting ready…', listening: 'Listening', thinking: 'Thinking', speaking: 'Speaking' })
})

const VB = readFileSync(new URL('../app/components/VoiceButton.tsx', import.meta.url), 'utf8')
test('VoiceButton draws only the machine: its label, its data-mic-state, and no label set on a timer', () => {
  assert.match(VB, /readMic\(snapshot\(\)\)/)
  assert.match(VB, /data-mic-state=\{state\}/)
  assert.match(VB, /MIC_WORDS\[state\]/)
  assert.doesNotMatch(VB, /setTimeout\([^)]*set(MicState|State)\(/)
})

test('speed: the key is minted before the tap, the socket opens beside the mic, the pipeline outlives a socket, early words are buffered', () => {
  assert.match(VB, /prefetchKey\(\)/)                      // on mount — asks for no mic
  assert.match(VB, /openSocket\(/)                         // the socket alone, on a tap and on a reconnect
  assert.match(VB, /micLog\('flushed'/)                    // words said while connecting, sent first
  assert.match(VB, /micLog\('socket_silent'/)              // a silent socket closed: it comes back
  assert.equal(REPLY_MS, 3000)
  assert.doesNotMatch(VB.slice(VB.indexOf('ws.onclose')), /audioCtxRef\.current\?\.close\(\)[^]*?connectedRef\.current = false[^]*?\/\/ end onclose/)
})
