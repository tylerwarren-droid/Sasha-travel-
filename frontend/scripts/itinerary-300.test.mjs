// Sasha 300 · THE ONE ITINERARY — the page's half: each booking says its status in words, the way it was made (its route), the
// venue's own words as data, and its map; the Trip tab's days and lists say the route and their words too.
//   node --test scripts/itinerary-300.test.mjs
import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const cards = readFileSync(new URL('../app/components/cards/S2Cards.tsx', import.meta.url), 'utf8')
const trip = readFileSync(new URL('../app/components/workspace/TripPanel.tsx', import.meta.url), 'utf8')

test('300 · the plans card: status in words, the route, their words (quoted, data), the map', () => {
  const fn = cards.slice(cards.indexOf('export function Plans('), cards.indexOf('/** CR 75'))
  assert.match(fn, /untag\(p\.status_words \|\| p\.status\)/)
  assert.match(fn, /p\.route_words \? ` · \$\{p\.route_words\}` : ''/)
  assert.match(fn, /They said: &ldquo;\{p\.venue_said\.untrusted_text\}&rdquo;/)
  assert.match(fn, /href=\{p\.map_url\}/)
})

test('300 · the Trip tab: a day\'s booking and the lists say the route; the lists quote the venue', () => {
  assert.match(trip, /\{shortStatus\(b\)\}\{b\.route_words \? ` · \$\{b\.route_words\}` : ''\}/)
  assert.match(trip, /\{r\.route_words \? ` · \$\{r\.route_words\}` : ''\}/)
  assert.match(trip, /They said: &ldquo;\{r\.venue_words\}&rdquo;/)
})
