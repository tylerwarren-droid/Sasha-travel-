// Sasha 378 · CR 188's Sasha half — the web chat's booking card FOLLOWS AgAPI's ONE decision (the plan /venues/read returns:
// venue.profile's route, channel, words and button). It chooses no channel of its own: no ladder, no "call instead", no one-tap page.
//   node --test scripts/follows-agapi-378.test.mjs
import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync, existsSync } from 'node:fs'

const card = readFileSync(new URL('../app/components/ChatBooking.tsx', import.meta.url), 'utf8')

test("378 · the card switches on AgAPI's routes only", () => {
  for (const r of ["'send_form'", "'ask_then_send'", "'message'", "'call'", "'call_at_opening'", "'call_no_voice'"]) assert.ok(card.includes(r), r)
  assert.match(card, /plan\.link/)
  assert.match(card, /plan\.line/)
})

test('378 · no channel of its own: no ladder, no "call instead", no one-tap page', () => {
  for (const gone of ['plan.ladder', "'one_tap'", 'callInstead', 'setChosen', 'ChatBookingLink', "pr === 'form'", "pr === 'email'"]) {
    assert.ok(!card.includes(gone), gone)
  }
  assert.ok(!existsSync(new URL('../app/components/ChatBookingLink.tsx', import.meta.url)))
})
