// Sasha 297 · "WHAT KIND OF PLACE?" — her ONE question's three taps on /s2: from the server's render (kind_ask), each tap sent as his
// own message (the same as saying it), gone once tapped. The question's words and the choices are the backend's (voice.KIND_ASK/CHOICES).
//   node --test scripts/kind-ask-297.test.mjs
import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const app = readFileSync(new URL('../app/s2/S2App.tsx', import.meta.url), 'utf8')

test('297 · the card comes only from the server\'s kind_ask render, with its own choices', () => {
  assert.match(app, /else if \(ev\.kind === 'kind_ask' && Array\.isArray\(ev\.choices\) && ev\.choices\.length\) add\(\{ k: 'kind_ask', ask: String\(ev\.ask \|\| ''\), choices: ev\.choices\.map\(String\) \}\)/)
  assert.match(app, /if \(c\.k === 'kind_ask'\) return <KindAsk choices=\{c\.choices\} send=\{send\} \/>/)
  assert.doesNotMatch(app, /Something special|Good value|Takeaway \/ delivery/)   // never the page's own words or list
})

test('297 · a tap is his answer: sent as his message, then the taps go', () => {
  const k = app.slice(app.indexOf('function KindAsk('), app.indexOf('/** The first n sentences'))
  assert.match(k, /onClick=\{\(\) => \{ setDone\(true\); send\(t\) \}\}/)
  assert.match(k, /if \(done\) return null/)
  assert.doesNotMatch(k, /fetch\(|sort\(|place_id/)   // no search, no ranking, no venue of its own
})
