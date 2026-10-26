// Sasha 293 · Details shows "Website" (their own site, else their Google listing) in a new tab, a visible "Back to Sasha", and AgAPI's
// "Our sources" page when its answer carries one (CR 125).
//   node --test scripts/details-293.test.mjs
import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const card = readFileSync(new URL('../app/components/cards/PlaceCard.tsx', import.meta.url), 'utf8')
const s2 = readFileSync(new URL('../app/s2/S2App.tsx', import.meta.url), 'utf8')

test('Website: their site, else their listing — a new tab, never a URL built here', () => {
  assert.match(card, /<a data-website href=\{place\.website \|\| place\.listing_url\} target="_blank" rel="noopener noreferrer"/)
  assert.match(card, /place\.website \? 'Website ↗' : 'Their Google listing ↗'/)
  assert.doesNotMatch(card, /google\.com\/maps/)
})

test('Back to Sasha is visible on Details and closes it', () => {
  assert.match(card, /<button type="button" data-back-to-sasha onClick=\{onClose\}[^>]*>Back to Sasha<\/button>/)
})

test("Our sources is AgAPI's page, passed through", () => {
  assert.match(card, /sourcesUrl \? <div[^>]*><a data-our-sources href=\{sourcesUrl\} target="_blank"/)
  assert.match(s2, /sources_url: ev\.sources_url \|\| null/)
  assert.match(s2, /sources_url: c\.sources_url/)
})
