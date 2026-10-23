// Sasha 271 · B/C/D — her on-screen presence is ONE rule (lib/presence-rule.mjs), and /s2 draws her from it.
//   node --test scripts/presence-rule.test.mjs
import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { presence, ring, GREEN, reappear, voiceOf, inView, dayOf, HOLD_MS, IDLE_MS, VOICE_ON, TAP_TO_TALK, PAUSED, WORK_PULSE, WORK_PULSE_CSS, speakVia, withCamera, wordOf } from '../lib/presence-rule.mjs'
import { OPENING, openingShown } from '../lib/greeting-rule.mjs'

const P = (o) => presence({ phase: 'bubble', signedIn: true, ...o })

test('the arrival is full size; after it she is ALWAYS the corner — never nothing', () => {
  for (const phase of OPENING) assert.equal(P({ phase }).where, phase === 'voice' ? 'corner' : 'full', phase)   // Sasha 281 · MOVED: her voice alone, from the corner
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
  assert.equal(P({ micLive: true }).look, 'listening')   // Sasha 273 · moved: "listening" is the mic actually hearing (was: awake)
  assert.equal(P({}).look, 'idle')                        // awake, the mic not hearing: no green
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
  assert.match(hello, /const p = presence\(\{ phase, tapFor, started, signedIn, soon, asleep, dormant, reduced: reducedMotion\(\), micLive, arrive \}\)/)   // Sasha 273 · + the mic's truth, rule 4
  assert.match(hello, /const big = p\.where === 'full'/)
  assert.doesNotMatch(hello, /createPortal/)                                          // never drawn into a slot that may not be there
  assert.doesNotMatch(hello, /if \(!slot\) return null/)
  assert.doesNotMatch(hello, /idleLive/)                                              // no "stay full size" timer of the arrival
  assert.match(hello, /c\.dataset\.drawn = '0'/)                                      // letting her live face go shows her still
  assert.match(hello, /SESSION_DISCONNECTED/)                                         // its session ending by itself, too
  assert.match(hello, /\(corner \|\| \(big && !live\)\) && <div aria-hidden data-sasha-still/)
  assert.match(hello, /arrivalLine\(nameRef\.current \?\? null, !!back\.current, live\)/)   // her lines: voice.py's, never the page's own · Sasha 281 MOVED: + live
  assert.doesNotMatch(hello, /WELCOME_BACK|Hey, welcome back!|I'm going to head behind the scenes/)
  const app = readFileSync(new URL('../app/s2/S2App.tsx', import.meta.url), 'utf8')
  assert.match(app, /<span id="s2-face-slot"/)
})

// ── Sasha 273 (rows 1031–1035, Tyler's demo with Jon, 16 Oct) ─────────────────────────────────────────────────────────────────
test('273 · 3: the voice label and the green ring are the mic actually hearing — never a flag', () => {
  assert.deepEqual(voiceOf({ micLive: true }), { live: true, words: VOICE_ON })
  assert.deepEqual(voiceOf({}), { live: false, words: TAP_TO_TALK })                  // back from the background, the mic not live
  assert.deepEqual(voiceOf({ asleep: true, micLive: true }), { live: false, words: PAUSED })
  assert.equal(voiceOf({ dormant: true, micLive: true }).live, false)
  assert.equal(P({ micLive: true }).voice, VOICE_ON)
  assert.equal(P({}).voice, TAP_TO_TALK)
  assert.doesNotMatch(ring('idle').border, new RegExp(GREEN))
  assert.equal(P({ phase: 'faceAgain' }).look, 'idle')
  assert.equal(P({ phase: 'faceAgain', micLive: true }).look, 'listening')
})

test('273 · 4: rule 4 — she reappears and greets only after 30 min quiet, on a new day, or with news; paused stays paused', () => {
  const now = Date.parse('2026-10-16T09:03:17Z'), tz = 'Europe/Madrid'
  assert.equal(reappear({ lastAt: now - 60e3, now, tz }).greet, false)                  // the 11:03 return, mid-booking: nothing
  assert.equal(reappear({ lastAt: now - IDLE_MS + 1000, now, tz }).greet, false)
  assert.deepEqual(reappear({ lastAt: now - 31 * 60e3, now, tz }), { greet: true, lead: 'hello', why: 'idle' })
  assert.deepEqual(reappear({ lastAt: null, now, tz }), { greet: true, lead: 'hello', why: 'idle' })   // a first visit
  const lateNight = Date.parse('2026-10-16T21:55:00Z'), afterMidnight = lateNight + 10 * 60e3   // 23:55 → 00:05 in Madrid
  assert.deepEqual(reappear({ lastAt: lateNight, now: afterMidnight, tz }), { greet: true, lead: 'hello', why: 'new_day' })
  assert.equal(reappear({ lastAt: lateNight, now: afterMidnight, tz: 'America/New_York' }).greet, false)   // the PERSON's zone
  assert.deepEqual(reappear({ lastAt: now - 60e3, now, tz, news: 'You’re booked.' }), { greet: true, lead: 'news', why: 'news' })
  assert.equal(reappear({ lastAt: now - 3 * 3600e3, now, tz, asleep: true }).greet, false)   // paused stays paused
  assert.equal(reappear({ lastAt: now - 60e3, now, tz, news: 'x', asleep: true }).greet, false)
  assert.equal(dayOf(lateNight, tz), '2026-10-16'); assert.equal(dayOf(afterMidnight, tz), '2026-10-17')
  assert.equal(IDLE_MS, 30 * 60 * 1000)
})

test('273 · 1 + 5: the corner only inside the visible viewport; her arrival ends on its speech-ended event, then ~0.5 s', () => {
  const vv = { top: 0, height: 700 }
  assert.equal(inView({ top: 600, width: 40 }, vv), true)
  assert.equal(inView({ top: 680, width: 40 }, vv), false)                              // under a browser's bottom bar
  assert.equal(inView({ top: 600, width: 0 }, vv), false)
  assert.equal(HOLD_MS, 500)
  assert.equal(P({ phase: 'off', arrive: false }).where, 'corner')                       // a quick return: never full size
  assert.equal(P({ phase: 'off', arrive: true }).where, 'full')
  const hello = readFileSync(new URL('../app/s2/S2Hello.tsx', import.meta.url), 'utf8')
  assert.doesNotMatch(hello, /secs \* 1000/)                                            // no duration guessed from the audio's size
  assert.doesNotMatch(hello, /a\.length \* 3\) \/ 4 \/ 48000/)
  assert.match(hello, /AgentEventsEnum\.AVATAR_SPEAK_ENDED/)
  assert.match(hello, /const held = \(\) => new Promise\(r => setTimeout\(r, HOLD_MS\)\)/)
  assert.match(hello, /inView\(/)
  assert.match(hello, /window\.visualViewport/)
})

test('273 · 4 + 5: /s2 greets only from rule 4, has one return handler, and its shell is the dynamic viewport', () => {
  const app = readFileSync(new URL('../app/s2/S2App.tsx', import.meta.url), 'utf8')
  assert.doesNotMatch(app, /\[\.\.\.shown, \{ role: 'sasha', text: line, cards: \[\], restored: true \}\]/)   // the 11:03 append, every load
  assert.match(app, /\.\.\.\(greet \? \[\{ role: 'sasha' as const, text: line/)
  assert.equal((app.match(/addEventListener\('visibilitychange'/g) || []).length, 1)   // ONE return handler (mic + rule 4)
  assert.match(app, /voiceCtl\.current\?\.resume\(\)/)
  assert.match(app, /if \(document\.visibilityState === 'hidden'\) speaker\.interrupt\(\)/)   // never resumes mid-sentence
  assert.match(app, /data-s2-shell style=\{\{ height: '100dvh'/)
  assert.match(app, /paddingBottom: 'calc\(10px \+ env\(safe-area-inset-bottom\)\)'/)
  assert.doesNotMatch(app, /'🔊 Voice on'/)                                              // "Voice" is the mic's word, never the speaker's
  assert.match(app, /voiceOf\(\{ asleep, dormant, micLive \}\)/)
  assert.match(app, /strict ctlRef=\{voiceCtl\} onConnectedChange=\{setMicLive\}/)
})

// ── Sasha 274 (rows 1061/1062, Tyler's iPhone 14:48–14:53) ───────────────────────────────────────────────────────────────────
test('274 · 1: rule 4 never greets under her own unanswered booking question — even after 30 minutes', async () => {
  const { midFlow } = await import('../lib/greeting-rule.mjs')
  const now = Date.parse('2026-10-16T12:47:58Z')
  const q = [{ role: 'user', text: 'Book Trebbiano for 4 at 21:00' }, { role: 'sasha', text: '4 people at Trebbiano, today at 21:00. Shall I call them now?…', cards: [] }]
  assert.equal(midFlow(q), true)
  assert.deepEqual(reappear({ lastAt: now - 45 * 60e3, now, tz: 'Europe/Madrid', midFlow: true }), { greet: false, lead: null, why: 'mid_booking' })
  assert.equal(reappear({ lastAt: now - 45 * 60e3, now, tz: 'Europe/Madrid', midFlow: false }).greet, true)       // not mid-booking: as 273
  assert.equal(reappear({ lastAt: now - 45 * 60e3, now, midFlow: true, news: 'You’re booked.' }).lead, 'news')     // news still leads
  assert.equal(midFlow([{ role: 'sasha', text: '', cards: [{ k: 'read_back', choices: [{ title: 'Call them' }] }] }]), true)
  assert.equal(midFlow([{ role: 'sasha', text: 'Booked: Trebbiano, 21:00.', cards: [] }]), false)
  assert.equal(midFlow([{ role: 'user', text: 'what about 22:00?' }]), false)
  assert.equal(midFlow([]), false)
})

test('279 · A: while she works the ring she has pulses (slowly), and stops when she answers — never paused or at rest', () => {
  assert.equal(ring('listening', false, true).pulse, WORK_PULSE)
  assert.equal(ring('idle', false, true).pulse, WORK_PULSE)
  assert.equal(ring('listening', false, false).pulse, null)   // her answer has begun: no pulse
  assert.equal(ring('paused', false, true).pulse, null)
  assert.equal(ring('resting', false, true).pulse, null)
  assert.equal(ring('listening', false, true).border, ring('listening').border)   // the green stays the mic's truth (273)
  assert.match(WORK_PULSE_CSS, new RegExp(`@keyframes ${WORK_PULSE}`))
  const app = readFileSync(new URL('../app/s2/S2App.tsx', import.meta.url), 'utf8')
  assert.match(app, /if \(ev\.type === 'working' && typeof ev\.on === 'boolean'\) setWorking\(ev\.on\)/)   // the stream's one state
})

// ── Sasha 281 (Tyler, 21 Oct 17:58: on his return "I'm turning off my camera" — her mouth didn't move) ─────────────────────────
const code = (t) => t.replace(/\/\*[\s\S]*?\*\/|\/\/[^\n]*/g, '')
test('281 · the rule: a line is on her live lips, or said with her in the corner — never over a big still or a frozen face', () => {
  assert.equal(speakVia({ live: true }), 'face')
  assert.equal(speakVia({ live: false }), 'corner')
  assert.equal(openingShown('voice', 'voice', false), null)                       // her voice alone is not drawn full size
  assert.equal(P({ phase: 'voice' }).where, 'corner')
  assert.equal(P({ phase: 'voice' }).tap, null)                                    // no face brought back under a line it isn't saying
  for (const phase of OPENING.filter(x => x !== 'voice')) assert.equal(P({ phase }).where, 'full', phase)
})

test('281 · the camera words only when there is a camera: her live face says them; her voice alone never does', () => {
  const CAM = "I'm turning my camera off — just talk, or tap to see me."
  assert.equal(withCamera('Hey Tyler', CAM, true), `Hey Tyler. ${CAM}`)
  assert.equal(withCamera('Hey Tyler', CAM, false), 'Hey Tyler.')
  assert.equal(withCamera('Your payment went through.', CAM, true), `Your payment went through. ${CAM}`)
  assert.equal(withCamera('Your payment went through.', CAM, false), 'Your payment went through.')
  assert.equal(withCamera('', CAM, false), '')
})

test('281 · ONE way S2Hello speaks: Face.say (her lips) and the voice are reached only from speak(); the page\'s speaker routes there', () => {
  const hello = code(readFileSync(new URL('../app/s2/S2Hello.tsx', import.meta.url), 'utf8'))
  const body = hello.slice(hello.indexOf('const speak = async'), hello.indexOf('const speakRef'))
  assert.ok(body.length > 100, 'speak() is there')
  assert.equal((hello.match(/talker\.sayNow\(/g) || []).length, 1, 'one talker.sayNow')              // her voice: only inside speak()
  assert.ok(body.includes('talker.sayNow(plain)'))
  assert.equal((hello.match(/\bf\.say\(|face\.current\.say\(|\.say\(t\)/g) || []).length, 1, 'one face say')   // her lips: only inside speak()
  assert.ok(body.includes('await f.say(t)'))
  assert.match(body, /if \(bigNow\(\)\) await collapse\(\)/)                                       // the corner before her voice
  assert.match(hello, /talker\.setRoute\(async t => \{ await speakRef\.current\(t\) \}\)/)          // every page line, her whole visit
  assert.equal((hello.match(/talker\.setRoute\(/g) || []).length, 3)                                  // set once; cleared on leaving (2)
  assert.doesNotMatch(hello, /setPhase\('faceLate'\)|to\('faceLate'\)/)                              // a late face never shown mid-line
  assert.match(hello, /return new Promise<boolean>\(res => \{ speaking = \(\) => res\(true\)/)        // Face.say says whether it reached her lips
  assert.match(hello, /if \(!a \|\| gone\) return false/)
  assert.match(hello, /idle\.current = setTimeout\(\(\) => \{ if \(phaseRef\.current === 'faceAgain'\) void collapse\(\) \}/)   // her face let go → the corner
  assert.match(hello, /const ended = \(\) => \{ if \(mine && face\.current === mine\) void collapse\(\) \}/)
  assert.match(hello, /if \(loud && lineToSay && !asleepRef\.current\) await speak\(lineToSay, ''\)/)   // bye: no camera words without a camera
})

test('281 · the page asks for the camera line only while her live face is up', () => {
  const app = code(readFileSync(new URL('../app/s2/S2App.tsx', import.meta.url), 'utf8'))
  assert.match(app, /const onCamera = leaving && !!helloCtl\.current\?\.live\(\)/)
  assert.match(app, /const said1 = onCamera \? \(cameraOffLine\(\) \|\| null\)/)
  assert.match(app, /const l = helloCtl\.current\.live\(\) \? cameraOffLine\(\) : ''/)
  const fl = code(readFileSync(new URL('../lib/first-line.ts', import.meta.url), 'utf8'))
  assert.equal((fl.match(/withCamera\(/g) || []).length, 2)                                             // arrival and news
})

test('283 · item 1 · the trip card reads the Trip view\'s own record — never the event\'s kind (moved from backend T63, 283b)', () => {
  const app = readFileSync(new URL('../app/s2/S2App.tsx', import.meta.url), 'utf8')
  assert.ok(!app.includes("'Flights to choose from'"))
  assert.ok(app.includes("bookingReq('/api/booking/plan')"))
  assert.ok(app.includes('r.json.card'))
})

test('283 · item 4c · his plain answer to "Did it go through?" — and only a plain one', () => {
  assert.equal(wordOf('Yes'), true)
  assert.equal(wordOf('yep, all booked'), true)
  assert.equal(wordOf('It went through!'), true)
  assert.equal(wordOf('no'), false)
  assert.equal(wordOf('Not yet'), false)
  assert.equal(wordOf("it didn't"), false)
  assert.equal(wordOf('yes can you also book a spa on Saturday at ten'), null)   // a new request is a turn
  assert.equal(wordOf('did it?'), null)
  assert.equal(wordOf('book me a table'), null)
})

test('283 · item 3 · the mic, her sound and her corner are the shell\'s — no tab can unmount them', () => {
  const app = code(readFileSync(new URL('../app/s2/S2App.tsx', import.meta.url), 'utf8'))
  const tabs = app.indexOf("{tab === 'trip' ? (")
  const body = app.indexOf("<div ref={end} />", tabs)
  const close = app.indexOf(')}', body)
  assert.ok(tabs > 0 && body > tabs && close > body)
  for (const owner of ['<VoiceButton', 'id="s2-face-slot"', '<SleepButton', 'aria-label="Message Sasha"']) {
    const at = app.indexOf(owner)
    assert.ok(at > close, `${owner} sits after the tab switch closes (drawn under every tab)`)
  }
  assert.equal((app.match(/<VoiceButton /g) || []).length, 1)   // one mic
})
