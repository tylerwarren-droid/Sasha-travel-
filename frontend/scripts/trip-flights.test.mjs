import { test } from 'node:test'
import assert from 'node:assert/strict'
import { tripFlights } from '../lib/trip-flights.mjs'

test('chosen flights are shown with their state — never "ask Sasha for flights" (EU 251)', () => {
  const tt = { lines: [{ kind: 'flight', state: 'chosen', what: 'easyJet U2 7651 LIS→MAD', day: '2026-10-26' },
    { kind: 'stay', state: 'chosen', what: 'Patio São Vicente', day: '2026-10-24' },
    { kind: 'flight', state: 'chosen', what: 'Air Europa UX 1153 MAD→LIS', day: '2026-10-24' }] }
  assert.deepEqual(tripFlights(tt), [
    { what: 'Air Europa UX 1153 MAD→LIS', day: 'Sat 24 Oct', words: 'chosen — not booked yet' },
    { what: 'easyJet U2 7651 LIS→MAD', day: 'Mon 26 Oct', words: 'chosen — not booked yet' }])
})

test('booked says booked; no flights on the trip → nothing (the hint may show)', () => {
  assert.equal(tripFlights({ lines: [{ kind: 'flight', state: 'booked', what: 'X', day: '2026-10-24' }] })[0].words, 'booked ✅')
  assert.deepEqual(tripFlights({ lines: [] }), [])
  assert.deepEqual(tripFlights(null), [])
})
