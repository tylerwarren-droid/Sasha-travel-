// Sasha 215 (d) · the mic at 16 kHz (lib/downsample.mjs, used by VoiceButton)
import test from 'node:test'
import assert from 'node:assert/strict'
import { makeDownsampler, sendRate } from '../lib/downsample.mjs'

function run(rate, seconds, freq) {
  const ds = makeDownsampler(rate)
  const n = Math.round(rate * seconds)
  const out = []
  for (let i = 0; i < n; i += 128) {
    const f = new Float32Array(Math.min(128, n - i))
    for (let k = 0; k < f.length; k++) f[k] = Math.sin(2 * Math.PI * freq * (i + k) / rate) * 0.5
    out.push(...ds(f))
  }
  return out
}

test('one second at 48 kHz or 44.1 kHz becomes one second at 16 kHz, in 128-sample frames, nothing lost at the joins', () => {
  assert.ok(Math.abs(run(48000, 1, 440).length - 16000) <= 1)
  assert.ok(Math.abs(run(44100, 1, 440).length - 16000) <= 1)
})

test('speech-band audio keeps its level; a tone above 8 kHz is attenuated', () => {
  const rms = (a) => Math.sqrt(a.reduce((s, x) => s + x * x, 0) / a.length)
  const speech = rms(run(48000, 0.5, 300))
  assert.ok(speech > 0.33 && speech < 0.36, `300 Hz rms ${speech}`)   // 0.5 / √2 ≈ 0.354
  assert.ok(rms(run(48000, 0.5, 15000)) < 0.15)
})

test('16 kHz is what Deepgram is told; a capture at or under 16 kHz is sent as it is', () => {
  assert.equal(sendRate(48000), 16000)
  assert.equal(sendRate(16000), 16000)
  assert.equal(sendRate(8000), 8000)
  const same = new Float32Array([0.1, 0.2])
  assert.equal(makeDownsampler(16000)(same), same)
})
