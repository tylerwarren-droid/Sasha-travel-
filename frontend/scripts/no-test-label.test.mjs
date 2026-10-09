// Sasha 218 · no visible TEST label on /next (lib/no-test-label.mjs) — display only
import test from 'node:test'
import assert from 'node:assert/strict'
import { untag, untagDeep } from '../lib/no-test-label.mjs'

test('the labels go, the words around them stay', () => {
  const cases = [
    ['€2,770.00 total for 2 · TEST', '€2,770.00 total for 2'],
    ['✈️ Iberia IB 3179 MAD→HAN · 2026-11-11 · booked · ref 0KC1VI (TEST)', '✈️ Iberia IB 3179 MAD→HAN · 2026-11-11 · booked · ref 0KC1VI'],
    ['Total €2,479.28 (TEST) — ONE tap to pay on your phone', 'Total €2,479.28 — ONE tap to pay on your phone'],
    ['TEST · booked (demo)', 'booked (demo)'],
    ['Your trip · TEST', 'Your trip'],
    ['Pay the TEST fare on Stripe', 'Pay the fare on Stripe'],
    ['Casa Marea (test)', 'Casa Marea'],
    ['Book it (TEST)', 'Book it'],
    ['Kept here · not sent (test)', 'Kept here · not sent'],
    ['Casa Lucio (our test venue stood in)', 'Casa Lucio'],   // Sasha 219
    ['21:00 · Casa Lucio (test venue stood in)', '21:00 · Casa Lucio'],
    ['Casa Lucio (TEST stand-in)', 'Casa Lucio'],
  ]
  for (const [a, b] of cases) assert.equal(untag(a), b, a)
})

test('ordinary words are never touched', () => {
  for (const s of ['Sasha Test Venue', 'a taste test', 'The Test Kitchen', 'Contest winners', 'Test booking: no hotel contacted'])
    assert.equal(untag(s), s, s)
})

test('ids, links and kinds are left exactly as they are', () => {
  const ev = { type: 'render', kind: 'flights', turn: 'TEST1', cards: [{ id: 'off_TEST', price: '€120 · TEST', url: 'https://x/TEST', name: 'Iberia (TEST)' }] }
  const out = untagDeep(ev)
  assert.equal(out.turn, 'TEST1')
  assert.equal(out.cards[0].id, 'off_TEST')
  assert.equal(out.cards[0].url, 'https://x/TEST')
  assert.equal(out.cards[0].price, '€120')
  assert.equal(out.cards[0].name, 'Iberia')
})
