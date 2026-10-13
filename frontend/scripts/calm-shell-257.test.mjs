// Sasha 257 · the S2 shell (rows 859–861): her face never an empty circle, Jon's "she can't hear me", a calm screen.
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const read = p => readFileSync(new URL(`../${p}`, import.meta.url), 'utf8')
const hello = read('app/s2/S2Hello.tsx'), app = read('app/s2/S2App.tsx'), who = read('app/components/SignedInLine.tsx'), mic = read('app/components/VoiceButton.tsx')

test('her face: a still only from a frame actually drawn; the last real one kept; a late face waits for its first frame', () => {
  assert.match(hello, /!keyed \|\| !keyed\.width \|\| !drawn\(keyed\)/)           // never a blank canvas (the empty dark circle)
  assert.match(hello, /canvas\.dataset\.drawn = '1'/)                               // set only where a frame is drawn
  assert.match(hello, /localStorage\.setItem\(FACE_KEY, url\)/)                     // kept for the next arrival
  assert.match(hello, /const k = keptFace\(\); if \(k\) setImg/)                    // her face on arrival
  assert.match(hello, /firstFrame\(canvas\.current\)\.then/)                        // a late face (10.6 s on a phone) waits for its frame
  assert.doesNotMatch(hello, /setTimeout\(\(\) => \{ face\.current = null; setImg\(still/)   // the old 0.9 s still is gone
})

test('Jon: a message while she answers is queued, never dropped; a stalled reply stops; done ends the read', () => {
  assert.match(app, /if \(busy\) \{ queued\.current = \[\.\.\.queued\.current, t\]/)
  assert.doesNotMatch(app, /if \(!t \|\| busy\) return/)
  assert.match(app, /signal: abort\.signal/)
  assert.match(app, /finished = true; rd\.cancel\(\)/)
  assert.match(app, /const \[nxt, \.\.\.rest\] = queued\.current/)
  assert.match(app, /disabled=\{!input\.trim\(\)\}/)                                 // Send works while she answers
})

test('a calm screen: identity quietly in the header (whoami), no floating pill on the S2 shell, no "Type instead"', () => {
  assert.match(who, /const S2_SHELL = \/\^\\\/\(s2\|next\)/)
  assert.match(who, /if \(S2_SHELL\.test\(path\)\) return null/)
  assert.match(app, /<WhoLine /)
  assert.doesNotMatch(app, /Type instead/)
})

test('the mic says plainly what it is: paused while she answers (not a red "Not…"); a blocked mic says what to do', () => {
  assert.doesNotMatch(mic, />Not listening</)
  assert.match(mic, /Mic paused while Sasha answers/)
  assert.match(mic, /Mic blocked — allow it for this site in your browser settings, or type/)
})

test('the sign-in code: any spacing or prefix is the same six digits; a code after the link was used says "already signed in"', () => {
  const code = read('app/auth/code/route.ts'), form = read('app/sign-in/SignInForm.tsx')
  assert.match(code, /replace\(\/\\D\+\/g, ''\)/)
  assert.match(code, /data\?\.user\?\.email \|\| ''\)\.toLowerCase\(\) === email\) return NextResponse\.json\(\{ ok: true, already: true/)
  assert.match(code, /You’re already signed in/)
  assert.doesNotMatch(code, /^export function (?!POST)/m)                         // a route exports its handlers only
  assert.match(form, /You&rsquo;re already signed in — taking you to Sasha\./)
})

test('the holding line keeps the "…" beneath it: she is still working until her words come', () => {
  const app = read('app/s2/S2App.tsx')
  assert.match(app, /m\.hold \? <>\{m\.hold\}<div>…<\/div><\/> : '…'/)
})
