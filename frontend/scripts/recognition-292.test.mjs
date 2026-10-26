// Sasha 292 · a discover card shows AgAPI's recognition sentence exactly as given (credited and dated) — none → nothing. No guide is
// named here: the words are AgAPI's.
//   node --test scripts/recognition-292.test.mjs
import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

test("the card renders AgAPI's recognition words, and names no guide of its own", () => {
  assert.match(readFileSync(new URL('../app/s2/S2App.tsx', import.meta.url), 'utf8'), /recognition: o\.recognition\?\.words/)
  const card = readFileSync(new URL('../app/components/cards/PlaceCard.tsx', import.meta.url), 'utf8')
  assert.match(card, /extra\?\.recognition \? <span data-recognition[^>]*>\{untag\(extra\.recognition\)\}<\/span> : null/)
  assert.doesNotMatch(card, /michelin|bib gourmand|50 best|repsol/i)
})
