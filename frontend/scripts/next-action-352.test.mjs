// Sasha 352 · THE NEXT ACTION: every card's buttons come from the server's ONE table (backend/booking_signer/next_actions.py), from its
// item's state — no surface hard-wires a Book / See-the-trip / Book-all / Invite button of its own. A tap says the button's words.
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const read = (p) => readFileSync(new URL(p, import.meta.url), 'utf8')
const cards = read('../app/components/cards/S2Cards.tsx')
const s2 = read('../app/s2/S2App.tsx')
// Sasha 358 · /group renders THE GROUP VIEW (app/components/group/GroupView.tsx), which holds the master list
const groupPage = read('../app/group/page.tsx')
const group = read('../app/components/group/GroupView.tsx')
const cardsOf = read('../lib/cards-of.ts')   // Sasha 402 · THE ONE MAPPING, moved out of S2App

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
  assert.ok(groupPage.includes('return <GroupView />'))                  // Sasha 358 MOVED: the page is the ONE group view
  assert.ok(group.includes('(st.list.actions || []).map('))             // the list's own actions (was v?.actions)
  assert.ok(group.includes('(r?.actions || []).map('))                  // each row's actions
  // Sasha 364 MOVED: the card draws its live copy (cur = the list re-read, its actions from the server) — still only the server's actions
  assert.ok(cards.includes('<NextButtons actions={cur.actions as NextAction[]} send={send} />'))
  assert.ok(cards.includes('actions: Array.isArray(j.actions) ? j.actions : c.actions'))
})

test('352 · the Booked card carries Change / Cancel from the server', () => {
  assert.ok(s2.includes("{ k: 'booked'; line: string; actions?: NextAction[] }"))
  assert.ok(s2.includes('<NextButtons actions={c.actions} send={send} />'))
})

test('352 · the trip card reads its state again when the turn ends (found live: a read-back in the pick turn left [Book it] showing)', () => {
  const chat = read('../app/components/SashaChat.tsx')
  for (const src of [s2, chat]) assert.match(src, /ev\.type === 'done'\) \{[\s\S]{0,40}window\.dispatchEvent\(new Event\('sasha-plan-refresh'\)\)/)
})

test('354 · a pending item draws the trip\'s ONE card on /s2 (a trip render with no proposal cards)', () => {
  // Sasha 402 MOVED: the mapping is lib/cards-of.ts
  assert.ok(cardsOf.includes("if (k === 'trip' && !(Array.isArray(ev.cards) && ev.cards.length) && !ev.total) return [{ k: 'trip' }]"))
})
