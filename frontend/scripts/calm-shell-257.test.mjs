// Sasha 257 · the S2 shell (rows 859–861): her face never an empty circle, Jon's "she can't hear me", a calm screen.
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const read = p => readFileSync(new URL(`../${p}`, import.meta.url), 'utf8')
const hello = read('app/s2/S2Hello.tsx'), app = read('app/s2/S2App.tsx'), who = read('app/components/SignedInLine.tsx'), mic = read('app/components/VoiceButton.tsx')

test('her face: live only from a frame actually drawn; ONE half-body still (268, never a kept snapshot); a late face waits for its first frame', () => {
  assert.match(hello, /canvas\.dataset\.drawn = '1'/)                               // set only where a frame is drawn
  assert.match(hello, /const img = FACE_STILL/)                                      // 268: the one still, never a snapshot
  assert.doesNotMatch(hello.replace(/\/\*[\s\S]*?\*\/|\/\/[^\n]*/g, ''), /FACE_KEY|keptFace|sasha-face\.jpg/)                   // the kept close-up is retired
  // Sasha 271 · Sasha 281 MOVED · Sasha 303 MOVED: a late face is let go (its session closed) — no face is started before his tap any
  // more, so the only late one is his tap's own (tapFace): not on screen in FACE_WAIT_MS, or the page moved on meanwhile
  assert.match(hello, /if \(!f\) \{ p\.then\(late => \{ void late\.stop\('late'\) \}\)\.catch\(\(\) => \{\}\); return false \}/)
  assert.match(hello, /if \(phaseRef\.current !== 'face'\) \{ void f\.stop\('late'\); return false \}/)
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
  assert.match(app, /<AccountControl /)   // Sasha 274 · moved: the same quiet line, now the one account control (rows 1063/1064)
  assert.doesNotMatch(app, /Type instead/)
})

test('the mic says plainly what it is: paused while she answers (not a red "Not…"); a blocked mic says what to do', () => {
  assert.doesNotMatch(mic, />Not listening</)
  assert.match(mic, /Mic paused while Sasha answers/)
  // Sasha 266 · row 943 (a): a blocked mic says what to do — the plain line (lib/mic-state BLOCKED) and the steps for that browser
  assert.match(mic, /reportMicError\(BLOCKED\)/)
  assert.match(mic, /micError === BLOCKED && <p[^>]*>\{stepsFor\(\)\}/)
})

test('the sign-in code: any spacing or prefix is the same six digits; a code after the link was used says "already signed in"', () => {
  const code = read('app/auth/code/route.ts'), form = read('app/sign-in/SignInForm.tsx')
  assert.match(code, /replace\(\/\\D\+\/g, ''\)/)
  assert.match(code, /data\?\.user\?\.email \|\| ''\)\.toLowerCase\(\) === email\) return NextResponse\.json\(\{ ok: true, already: true/)
  assert.match(code, /You’re already signed in/)
  assert.doesNotMatch(code, /^export function (?!POST)/m)                         // a route exports its handlers only
  assert.match(form, /You&rsquo;re already signed in — taking you to Sasha\./)
})

test('Sasha 259 · ONE working mark: the holding line, else "…" — and aria-busy says she is working', () => {
  const app = read('app/s2/S2App.tsx')
  assert.match(app, /<div aria-busy="true" data-sasha-working[^>]*>\{m\.hold \|\| '…'\}<\/div>/)
})

test('Sasha 259 · a calm phone screen: her face is a real still (268: half-body), in the voice row with the moon; no text under the mic', () => {
  const app = read('app/s2/S2App.tsx'), hello = read('app/s2/S2Hello.tsx'), mic = read('app/components/VoiceButton.tsx')
  assert.match(hello, /export const FACE_STILL = '\/sasha-half\.webp'/)               // never the "S"; 268: her half-body still
  assert.doesNotMatch(hello, /\{img \? '' : 'S'\}/)
  assert.match(hello, /document\.getElementById\('s2-face-slot'\)/)
  assert.match(app, /<span id="s2-face-slot"/)
  assert.match(app, /<SleepButton asleep=\{asleep\} onToggle=\{\(\) => sleepEvent\('tap_pause'\)\} size=\{36\} style=\{\{ flexShrink: 0, padding: '0 10px' \}\} \/>/)   // Sasha 273 · moved: never squeezed at 390 px
  assert.doesNotMatch(app, /position: 'fixed', zIndex: 46, left: 16/)                   // the moon no longer floats over "Voice off"
  assert.match(app, /<VoiceButton quiet /)
  assert.match(mic, /\{!quiet && !asleep && muted && <p/)
})

test('Sasha 259 · the overlap rule: any two boxes that cross fail; touching does not', async () => {
  const { overlaps } = await import('../lib/overlap.mjs')
  assert.deepEqual(overlaps([{ name: 'face', x: 330, y: 700, w: 58, h: 58 }, { name: 'send', x: 340, y: 760, w: 44, h: 44 }]), [])
  assert.deepEqual(overlaps([{ name: 'face', x: 330, y: 740, w: 58, h: 58 }, { name: 'send', x: 340, y: 760, w: 44, h: 44 }]), [['face', 'send']])
  assert.deepEqual(overlaps([{ name: 'a', x: 0, y: 0, w: 10, h: 10 }, { name: 'b', x: 10, y: 0, w: 10, h: 10 }]), [])
})

test('Sasha 258 · the Trip tab is "booked" by THIS trip\'s own state, never a table booked elsewhere', () => {
  assert.match(read('app/components/workspace/TripPanel.tsx'), /ON_IT\.includes\(ts\.trip_state \?\? ts\.state\)/)
})
