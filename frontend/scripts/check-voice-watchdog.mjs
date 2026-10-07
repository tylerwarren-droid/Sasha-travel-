// Sasha 197 · BUILD GATE (prebuild): the mic comes on after Sasha's greeting, and the watchdog never fights a connect.
import { watchdogAction as W } from '../lib/voice-watchdog.mjs'
const base = { now: 100000, manualStop: false, ready: true, muted: false, connected: false, connecting: false, hadConnected: false,
  wsOpen: false, lastAlive: 0, gated: false, gatedSince: 0, heardAt: 0 }
const cases = [
  ['a connect in flight after the greeting is never interrupted', { ...base, connecting: true }, null],
  ['the first connect (never connected yet) is left to the page, not raced', { ...base }, null],
  ['after the greeting the gate opens and the mic simply listens', { ...base, connected: true, wsOpen: true, gated: false }, null],
  ['while Sasha speaks (gated, under 45 s) nothing happens', { ...base, connected: true, wsOpen: true, gated: true, gatedSince: 90000 }, null],
  ['a mic left closed 45 s after she spoke is re-armed', { ...base, connected: true, wsOpen: true, gated: true, gatedSince: 50000 }, 'rearm'],
  ['speech heard, no transcript in 8 s → the stream restarts', { ...base, connected: true, wsOpen: true, heardAt: 90000 }, 'restart'],
  ['a real drop, nothing in flight, 15 s on → reconnect', { ...base, hadConnected: true, lastAlive: 80000 }, 'reconnect'],
  ['a drop being retried by the close handler is left alone (< 15 s)', { ...base, hadConnected: true, lastAlive: 95000 }, null],
  ['stopped by the guest: never reconnected', { ...base, manualStop: true, hadConnected: true }, null],
]
let bad = 0
for (const [name, s, want] of cases) {
  const got = W(s)
  if (got !== want) { bad++; console.error(`check-voice-watchdog: FAIL — ${name}: got ${got}, want ${want}`) }
}
if (bad) process.exit(1)
console.log(`check-voice-watchdog: ${cases.length} cases pass — the mic comes on after the greeting, no connect is raced`)
