// Sasha 301 · 424 · THE FINE PRINT — the page's half. Sasha 424 (NO TERM WITHOUT A FACT): no card and no Trip-tab line draws a
// booking term (a deposit, a cancellation rule, a deadline) — those are AgAPI's facts (facts.answer) or not shown. The plans card
// still draws his Keep's perks (masked lines from the server).
//   node --test scripts/fine-print-301.test.mjs
import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const cards = readFileSync(new URL('../app/components/cards/S2Cards.tsx', import.meta.url), 'utf8')
const trip = readFileSync(new URL('../app/components/workspace/TripPanel.tsx', import.meta.url), 'utf8')

test('424 · the plans card draws no term; the perks as the server wrote them', () => {
  const fn = cards.slice(cards.indexOf('export function Plans('), cards.indexOf('/** CR 75'))
  assert.ok(fn.length > 0, 'Plans() found')
  assert.match(fn, /\{x\.line\}/)
  assert.doesNotMatch(cards, /termHead|TERM_LABEL|\bterms\?:|p\.terms|by_words/)
})

test('424 · the Trip tab draws no term and no deadline on any line', () => {
  assert.doesNotMatch(trip, /termHead|cancelBy|by_words|\.terms\b|terms\?:/)
  assert.match(trip, /\{shortStatus\(b\)\}\{b\.route_words \? ` · \$\{b\.route_words\}` : ''\}/)
  assert.doesNotMatch(trip + cards, /free to cancel|free cancellation|refundable/i)
})
