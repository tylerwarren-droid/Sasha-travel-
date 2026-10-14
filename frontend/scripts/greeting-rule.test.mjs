// Sasha 251 · THE GREETING: shown on arrival, gone once the conversation starts — never over the conversation.
import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { conversationStarted, arrivalStarted, openingShown, openingEnds, OPENING } from '../lib/greeting-rule.mjs'

test('arrival: an empty conversation has not started', () => {
  assert.equal(conversationStarted([]), false)
  assert.equal(conversationStarted(undefined), false)
})

test('her own lines alone do not start it (the hello, "I\'m here", a proactive note)', () => {
  assert.equal(conversationStarted([{ role: 'sasha', text: 'Hey Tyler, what can I help you with?' }]), false)
})

test('their first turn starts it: a sent message, a chip, a spoken transcript, a card tap — all land as a user turn', () => {
  assert.equal(conversationStarted([{ role: 'user', text: 'A table tonight' }, { role: 'sasha', text: '' }]), true)
})

test('a restored conversation with their turns has already started (as a conversation) — but NOT this arrival (Sasha 265, row 936)', () => {
  const back = [{ role: 'user', text: 'dinner', restored: true }, { role: 'sasha', text: 'Here are three', restored: true }, { role: 'sasha', text: 'Hey Tyler, what can I help you with?', restored: true }]
  assert.equal(conversationStarted(back), true)
  assert.equal(arrivalStarted(back), false)   // the return plays the opening: full size, the hello, then the circle
  assert.equal(arrivalStarted([...back, { role: 'user', text: 'and a spa' }]), true)   // a turn taken NOW ends it
})

test('on arrival the card ("Hey <name>…" + "Tap to hear Sasha") and her face are shown', () => {
  assert.equal(openingShown('tap', 'voice', false), 'card')
  assert.equal(openingShown('voice', 'voice', false), 'card')
  assert.equal(openingShown('tap', 'face', false), 'face')
  assert.equal(openingShown('face', 'voice', false), 'face')
  assert.equal(openingShown('faceLate', 'voice', false), 'face')
})

test('THE BUG: blocked sound left the tap card up for the whole visit — once started, nothing of the opening is drawn', () => {
  for (const phase of OPENING) for (const tapFor of ['face', 'voice']) assert.equal(openingShown(phase, tapFor, true), null, `${phase}/${tapFor}`)
})

test('once started, every opening phase ends (to the bubble); the bubble and "off" stay as they are', () => {
  for (const phase of OPENING) assert.equal(openingEnds(phase, true), true, phase)
  assert.equal(openingEnds('bubble', true), false)
  assert.equal(openingEnds('off', true), false)
  for (const phase of OPENING) assert.equal(openingEnds(phase, false), false, phase)
})

test('her face back from the bubble is their own choice — not the opening', () => {
  assert.equal(openingShown('faceAgain', 'voice', true), 'face')
  assert.equal(openingEnds('faceAgain', true), false)
  assert.equal(openingShown('bubble', 'voice', false), null)
})

test('/s2 wires it: S2Hello draws from openingShown and S2App passes started from the messages', () => {
  const hello = readFileSync(new URL('../app/s2/S2Hello.tsx', import.meta.url), 'utf8')
  const app = readFileSync(new URL('../app/s2/S2App.tsx', import.meta.url), 'utf8')
  assert.match(hello, /openingShown\(phase, tapFor, started\)/)
  assert.match(hello, /shown === 'card'/)
  assert.doesNotMatch(hello, /phase === 'voice' \|\| \(phase === 'tap' && tapFor === 'voice'\) \?/)
  assert.match(app, /started=\{arrivalStarted\(msgs\)\}/)   // Sasha 265 · item 2 (was conversationStarted: a return skipped her)
  assert.match(app, /restored: true/)
})

test('Sasha 265 · item 2 (row 936): ONE arrival sequence — no per-tab skip, her face full size from the first instant, the circle found when its slot appears', () => {
  const hello = readFileSync(new URL('../app/s2/S2Hello.tsx', import.meta.url), 'utf8')
  assert.doesNotMatch(hello, /getItem\('s2_hello'\)/)                 // a return no longer skips the opening
  assert.doesNotMatch(hello, /opacity: phase === 'starting' \? 0/)      // never invisible while her live face starts
  assert.match(hello, /const big = shown === 'face' \|\| shown === 'card'/)   // her voice alone still shows her face
  assert.match(hello, /prefers-reduced-motion: reduce/)                  // the one thing that skips the motion
  assert.match(hello, /new MutationObserver\(look\)/)                   // the circle's slot is watched, not looked up once in render
  assert.doesNotMatch(hello, /const slot = typeof document/)
})
