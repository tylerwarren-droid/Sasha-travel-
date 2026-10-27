// Sasha 295 · THE FIRST FIVE SECONDS: one action on load, nothing said before his tap, her hello after it, one cue each.
//   node --test scripts/opening-rule.test.mjs
import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { opening, cueOf, READY, TALK, OR_TYPE, STARTERS, ON_TAP, NO_SOUND, LISTENING, THINKING, SPEAKING, BACK, CONTINUE, AWAY_MS, PAUSE_MS, returned, settle, CAMERA_SAID } from '../lib/opening-rule.mjs'
import { OPENING, openingShown, openingEnds } from '../lib/greeting-rule.mjs'
import { presence, TAP_TO_TALK, PAUSED, HOLD_MS } from '../lib/presence-rule.mjs'
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

// ── Sasha 296 · COMING BACK, AND "STILL HERE" — the same rule, every state after the first seconds ──────────────────────────────
const fl = readFileSync(new URL('../lib/first-line.ts', import.meta.url), 'utf8')

test('296 · returned: away AWAY_MS or more, not paused, not at rest, nothing in flight, her own tab — a glance away is nothing', () => {
  assert.equal(returned({ away: 30000 }), true)          // 30 s away (a hidden tab, a locked phone)
  assert.equal(returned({ away: AWAY_MS }), true)
  assert.equal(returned({ away: AWAY_MS - 1 }), false)
  assert.equal(returned({ away: 0 }), false)
  assert.equal(returned({ away: 30000, asleep: true }), false)   // paused: Wake is its action
  assert.equal(returned({ away: 30000, dormant: true }), false)
  assert.equal(returned({ away: 30000, busy: true }), false)     // her answer is what's there
  assert.equal(returned({ away: 30000, here: false }), false)    // another tab
})

test('296 · back: her still full size with ONE action in words — "Tap to continue", "or type" — the same panel, never a second screen', () => {
  const o = opening({ phase: BACK, signedIn: true })
  assert.deepEqual([o.panel, o.action, o.words, o.starters, o.speaks], [true, 'continue', CONTINUE, false, false])
  assert.equal(CONTINUE, 'Tap to continue')
  assert.ok(OPENING.includes(BACK))
  assert.equal(openingShown(BACK, 'voice', false), 'face')
  assert.equal(openingEnds(BACK, true), true)               // another tab ends it like the rest
  assert.equal(presence({ phase: BACK, signedIn: true }).where, 'full')
  assert.equal(opening({ phase: BACK, signedIn: true, asleep: true }).panel, false)
  assert.equal(opening({ phase: READY, signedIn: true }).action, 'talk')
  assert.equal(opening({ phase: 'bubble', signedIn: true, asleep: true }).action, 'wake')
  assert.equal(opening({ phase: 'bubble', signedIn: true }).action, 'cue')
  assert.equal((hello.match(/data-opening-talk/g) || []).length, 1)   // ONE button: its words are the state's
  assert.match(hello, /\{op\.words\}<\/button>/)
  assert.doesNotMatch(hello + app, /data-resume|ResumeCard|Welcome back card/)
})

test('296 · the return is the ONE return handler: the page\'s own two moments (hidden, shown), rule 4 first — never a timer', () => {
  const back = app.slice(app.indexOf('const comeBack = useCallback'), app.indexOf('useEffect(() => { comeBackRef.current = comeBack }'))
  assert.match(back, /const away = hiddenAt\.current \? Date\.now\(\) - hiddenAt\.current : 0/)
  assert.ok(back.indexOf('helloCtl.current?.again(') < back.indexOf('returned({ away'))
  assert.match(back, /helloCtl\.current\?\.returned\(fetch\('\/api\/s2-memory\?pickup=1'/)
  assert.doesNotMatch(back, /setTimeout|setInterval/)
  assert.equal((app.match(/addEventListener\('visibilitychange'/g) || []).length, 1)
  const rt = hello.slice(hello.indexOf('const returnedNow = '), hello.indexOf('useEffect(() => () => { keyOff()'))
  assert.match(rt, /to\(BACK\)/)
  assert.match(rt, /talker\.prefetch\?\.\(plain\)/)   // her pickup line's audio fetched before his tap
  assert.doesNotMatch(rt, /speak\(|sayNow\(|setTimeout/)    // nothing said before the tap, nothing timed
  const begin = hello.slice(hello.indexOf('const begin = () => {'), hello.indexOf('const skipTo'))
  assert.match(begin, /phaseRef\.current !== READY && phaseRef\.current !== BACK/)   // "Tap to continue" is the same tap: sound, mic, her line
  assert.match(hello, /waiting: \(\) => phaseRef\.current === READY \|\| phaseRef\.current === BACK/)   // he speaks or types first: it ends
})

test('296 · settle: the camera words once a session; after that a pause, "Still here.", a pause; no live face, no words', () => {
  assert.deepEqual(settle({ said: false, live: true }), { camera: true, steps: ['say', 'hold'] })
  assert.deepEqual(settle({ said: true, live: true }), { camera: false, steps: ['say', 'pause', 'still', 'pause'] })
  assert.deepEqual(settle({ said: false, live: false }), { camera: false, steps: [] })
  assert.deepEqual(settle({ said: true, live: false }), { camera: false, steps: [] })
  assert.ok(PAUSE_MS >= 400 && PAUSE_MS <= 1200)   // a slight pause: noticeable, never a wait
  assert.ok(HOLD_MS > 0)
  // three moves into the corner in one session: the full line once, then "Still here" twice
  let said = false
  const heard = []
  for (let i = 0; i < 3; i++) { const s = settle({ said, live: true }); heard.push(s.camera ? 'camera' : s.steps.includes('still') ? 'still' : '-'); if (s.camera) said = true }
  assert.deepEqual(heard, ['camera', 'still', 'still'])
  assert.equal(CAMERA_SAID, 's2_camera_said')
})

test('296 · every move into the corner goes through settle — arrival, his request (bye), a tap on her face — never at once and silent', () => {
  const sn = hello.slice(hello.indexOf('const settleNow = async'), hello.indexOf('const settleLine = '))
  assert.match(sn, /settleOf\(\{ said: cameraSaid\(\), live: faceUp\(\) \}\)/)
  assert.match(sn, /if \(s\.camera && cameraOffLine\(\)\) markCamera\(\)/)   // marked only once it was on her lips
  assert.match(sn, /stillHereLine\(lang\(\)\)/)
  assert.match(hello, /const how = await settleNow\(plain, plain\)/)                     // her arrival
  assert.match(hello, /await settleNow\('', ''\)/)                                          // bye (his request)
  assert.match(hello, /const tap = p\.tap === 'collapse' \? \(\) => \{ void bye\(settleLine\(\), !muted\) \}/)   // a tap on her face
  assert.doesNotMatch(app, /cameraOffLine\(/)   // the page never picks the camera line itself any more
  assert.match(fl, /export function stillHereLine\(lang: string\): string/)
  assert.match(fl, /\/\^es\\b\/i\.test\(lang/)   // ES: "Aquí sigo."
})

test('296 · her face is never blank: signed in, she is drawn in every state — paused, back, corner, listening, thinking, speaking', () => {
  for (const phase of ['off', READY, BACK, 'starting', 'face', 'faceLate', 'voice', 'tap', 'bubble', 'faceAgain'])
    for (const asleep of [false, true]) for (const dormant of [false, true]) for (const micLive of [false, true])
      assert.notEqual(presence({ phase, signedIn: true, asleep, dormant, micLive }).where, 'none', `${phase} asleep=${asleep} dormant=${dormant} mic=${micLive}`)
  assert.match(hello, /\(corner \|\| \(big && !live\)\) && <div aria-hidden data-sasha-still/)   // her still unless her live face is drawing
})

test('296 · a brand-new guest: the action with her first paint (the sign-in cookie), a tap that early held — the mic once signed in', () => {
  assert.equal(opening({ phase: 'off', signedIn: null, soon: true, full: true }).panel, true)
  assert.equal(opening({ phase: 'off', signedIn: null, soon: false, full: true }).panel, false)
  assert.equal(opening({ phase: 'off', signedIn: false, soon: true, full: true }).panel, false)
  assert.match(hello, /opening\(\{ phase, signedIn, soon, started, asleep, full: big \}\)/)
  assert.match(app, /const beginNow = \(\) => \{ if \(!voiceCtl\.current\) micAsked\.current = true; begin\(\) \}/)
  assert.match(app, /onBegin=\{beginNow\}/)
})
