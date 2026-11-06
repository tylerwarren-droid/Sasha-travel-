// Sasha 352 · THE NEXT ACTION: every card's buttons come from the server's ONE table (backend/booking_signer/next_actions.py), from its
// item's state — no surface hard-wires a Book / See-the-trip / Book-all / Invite button of its own. A tap says the button's words.
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const read = (p) => readFileSync(new URL(p, import.meta.url), 'utf8')
const cards = read('../app/components/cards/S2Cards.tsx')
const s2 = read('../app/s2/S2App.tsx')
const group = read('../app/group/page.tsx')

test('352 · the ONE trip card (S2 and S1) renders its next actions, and a tap says them', () => {
  assert.ok(cards.includes('<NextButtons actions={t?.actions} send={send} />'))
  assert.ok(cards.includes("send(String(a.say))"))                       // tapping = saying it
  assert.ok(!s2.includes('function TripCard('))                          // one trip card, shared
  assert.ok(!(s2 + cards).includes('>See the whole trip</button>'))      // the view comes from the table too
  assert.ok(cards.includes("'flight_chosen', 'trip']"))                  // S1 draws it (SHARED_KINDS)
  assert.ok(s2.includes('<TripCard send={send} />'))
})

test('352 · the master list (page and card) renders its rows\' and its own actions — no button of its own', () => {
  assert.doesNotMatch(group, />Book all planned<|>Invite everyone to the vault<|>Book<\/button>|>Invite<\/button>/)
  assert.ok(group.includes('(v?.actions || []).map('))
  assert.ok(group.includes('(r.actions || []).map('))
  assert.ok(cards.includes('<NextButtons actions={c.actions as NextAction[]} send={send} />'))
})

test('352 · the Booked card carries Change / Cancel from the server', () => {
  assert.ok(s2.includes("{ k: 'booked'; line: string; actions?: NextAction[] }"))
  assert.ok(s2.includes('<NextButtons actions={c.actions} send={send} />'))
})

test('352 · the trip card reads its state again when the turn ends (found live: a read-back in the pick turn left [Book it] showing)', () => {
  const chat = read('../app/components/SashaChat.tsx')
  for (const src of [s2, chat]) assert.match(src, /ev\.type === 'done'\) \{[\s\S]{0,40}window\.dispatchEvent\(new Event\('sasha-plan-refresh'\)\)/)
})
