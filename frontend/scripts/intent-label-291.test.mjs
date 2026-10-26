// Sasha 291 · a discover card shows AgAPI's own label for what they want to do ("walk-in, no bookings") — passed through, never S2's.
//   node --test scripts/intent-label-291.test.mjs
import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

test("the card carries AgAPI's label as given", () => {
  assert.match(readFileSync(new URL('../app/s2/S2App.tsx', import.meta.url), 'utf8'), /label: o\.label/)
  const card = readFileSync(new URL('../app/components/cards/PlaceCard.tsx', import.meta.url), 'utf8')
  assert.match(card, /extra\?\.label \? <span data-intent-label/)
  assert.doesNotMatch(card, /walk-in, no bookings/)   // the words are AgAPI's, never written here
})
