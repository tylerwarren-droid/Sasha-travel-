// Sasha 301 · THE FINE PRINT — the page's half: each booking shows the venue's terms in THEIR quoted sentence (with the deadline
// they stated) and his Keep's perks (masked lines from the server); the Trip tab's lists and day lines say the deadline too.
//   node --test scripts/fine-print-301.test.mjs
import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const cards = readFileSync(new URL('../app/components/cards/S2Cards.tsx', import.meta.url), 'utf8')
const trip = readFileSync(new URL('../app/components/workspace/TripPanel.tsx', import.meta.url), 'utf8')

test('301 · the plans card: each term is their quoted sentence under its label and deadline; the perks as the server wrote them', () => {
  const fn = cards.slice(cards.indexOf('export function Plans('), cards.indexOf('/** CR 75'))
  assert.match(fn, /<b>\{termHead\(t\)\}<\/b>: <span[^>]*>&ldquo;\{t\.quote\}&rdquo;<\/span>/)
  assert.match(fn, /\{x\.line\}/)
  assert.match(cards, /t\.by_words \? ` — by \$\{t\.by_words\}` : ''/)
})

test('301 · the Trip tab: one way to say a term (termHead); a day line says the deadline only when they stated one', () => {
  assert.match(trip, /import \{ termHead, type Term \} from '\.\.\/cards\/S2Cards'/)
  assert.match(trip, /x\.kinds\.includes\('cancellation'\) && x\.by_words/)
  assert.match(trip, /\{shortStatus\(b\)\}\{b\.route_words \? ` · \$\{b\.route_words\}` : ''\}\{cancelBy\(b\.terms\)\}/)
  assert.doesNotMatch(trip + cards, /free to cancel/i)   // never "free" in our words: only theirs, quoted
})
