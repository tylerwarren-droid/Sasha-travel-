// Sasha 249 · T5/T6 on the Trip tab: ONE PARTY (the trip's figures first, never a silent 1 or 2) and ONE TOTAL (the basket's
// euro figure; the planner's $ figure only as a labelled guess when the basket has none).
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { partySize } from '../lib/trip-party.mjs'

const src = (p) => readFileSync(new URL(p, import.meta.url), 'utf8')

test('T6 · the trip figures\' party wins over the plan, the estimate and the page', () => {
  assert.equal(partySize({ party: 3 }, { travellers: 4 }, 1, { party: 2 }), 2)
  assert.equal(partySize({ party: 3 }, null, 1, { party: null }), 3)   // figures without a party: the plan's
  assert.equal(partySize({}, null, 0, null), null)                       // nothing known: null, never 1
  assert.equal(partySize({}, null, 0, { party: 0 }), null)
})

test('T6 · no surface passes a silent 1 or 2 as the travellers', () => {
  assert.match(src('../app/s2/S2App.tsx'), /travellerCount=\{0 /)
  assert.doesNotMatch(src('../app/components/SashaChat.tsx'), /user\.travellers\?\.length \|\| 2\)/)
  const panel = src('../app/components/workspace/TripPanel.tsx')
  assert.match(panel, /partySize\(richItinerary, cb, cb\?\.travellers \|\| travellerCount, tt\)/)
  assert.match(panel, /\{pax \?\? '—'\}/)
})

test('T5 · the $ estimate is only the planner\'s guess, labelled, when the basket has no total', () => {
  const panel = src('../app/components/workspace/TripPanel.tsx')
  assert.match(panel, /tt \? 'All in' : "Planner's guess"/)
  assert.doesNotMatch(panel, /'Estimated total'/)
})
