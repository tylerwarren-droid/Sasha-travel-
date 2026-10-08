// Sasha 215 · the mic never fails silently (lib/mic-fail.mjs, used by VoiceButton and /next)
import test from 'node:test'
import assert from 'node:assert/strict'
import { keyOrFail, micFailLine, shouldSay, RECONNECTS_BEFORE_SAYING } from '../lib/mic-fail.mjs'

test('the backend key is used; the public key only when the proxy is not configured (501)', () => {
  assert.deepEqual(keyOrFail(200, 'k1', 'pub'), { key: 'k1' })
  assert.deepEqual(keyOrFail(501, '', 'pub'), { key: 'pub' })
  assert.equal(keyOrFail(500, '', 'pub').key, '')
  assert.equal(keyOrFail(500, '', 'pub').error, 'Voice service unavailable')
  assert.equal(keyOrFail(0, '', '').error, 'Voice service unavailable')   // unreachable: a failure, never silent
})

test('every real mic failure is said, with what to do', () => {
  for (const e of ['Mic permission denied', 'No microphone found', 'Mic is in use by another app', 'Voice service unavailable', 'Selected mic is unavailable'])
    assert.match(micFailLine(e), /type to me/, e)
  assert.equal(micFailLine(null), null)
  assert.equal(micFailLine('Microphone disconnected — reconnecting'), null)   // a passing state, shown but not said
})

test('said once per kind of failure', () => {
  const said = new Set()
  const line = shouldSay('Voice service unavailable', said)
  assert.ok(line)
  said.add(line)
  assert.equal(shouldSay('Voice service unavailable', said), null)
  assert.ok(shouldSay('Mic permission denied', said))
  assert.ok(RECONNECTS_BEFORE_SAYING >= 2 && RECONNECTS_BEFORE_SAYING <= 5)
})
