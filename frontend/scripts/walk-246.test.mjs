// Sasha 246 item 4 (EU 241's walk) · the Trip tab's travellers, My Keep's header line, the Subscriptions card with none found.
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { partySize } from '../lib/trip-party.mjs'
import { keepLead, leadItem } from '../lib/keep-lead.mjs'
import { subsHeading, subsFooter } from '../lib/subscriptions-heading.mjs'

test('travellers: the plan\'s party wins over the page\'s default (a trip for two never shows 1)', () => {
  assert.equal(partySize({ party: 2 }, null, 1), 2)
  assert.equal(partySize({ travellers: 3 }, null, 1), 3)
  assert.equal(partySize({}, { travellers: 4 }, 1), 4)
  assert.equal(partySize(null, null, 2), 2)
  assert.equal(partySize({ party: '2' }, null, 1), 2)
  assert.equal(partySize({ party: 0 }, null, 1), 1)
  // Sasha 249 · updated: this pinned the silent 1 that 249 removes (ONE PARTY: unknown is null — the tab shows "—", Sasha asks)
  assert.equal(partySize(undefined, undefined, undefined), null)
})

test('travellers: TripPanel reads the party, and /s2 is no longer left with its fixed 1', () => {
  const src = readFileSync(new URL('../app/components/workspace/TripPanel.tsx', import.meta.url), 'utf8')
  assert.match(src, /const pax = partySize\(richItinerary,/)
})

test('My Keep: the header names THEIR item, a passport first — never the fixed example', () => {
  const items = [{ type: 'loyalty', masked: 'Iberia Plus ••••432' }, { type: 'passport', masked: 'Passport PT ••••789' }]
  assert.equal(leadItem(items).masked, 'Passport PT ••••789')
  assert.match(keepLead(items), /only “Passport PT ••••789”\./)
  assert.match(keepLead([{ type: 'loyalty', masked: 'Iberia Plus ••••432' }]), /only “Iberia Plus ••••432”/)
  assert.doesNotMatch(keepLead(items), /ES ••••456/)
})

test('My Keep: nothing kept → a neutral line with no example', () => {
  for (const none of [[], null, undefined, [{ type: 'passport', masked: '' }]]) {
    const l = keepLead(none)
    assert.doesNotMatch(l, /••••/)
    assert.match(l, /^Sasha never sees what you keep here — only a masked version of it\./)
  }
})

test('My Keep: no page carries the fixed "Passport ES ••••456" line any more', () => {
  for (const f of ['../app/keep/page.tsx', '../app/s2/S2App.tsx', '../app/keep/KeepScreen.tsx']) {
    const src = readFileSync(new URL(f, import.meta.url), 'utf8')
    assert.doesNotMatch(src, /<p[^>]*>Sasha never sees these — only “Passport ES ••••456”/, f)
  }
})

test('Subscriptions: none found has its own heading and no "tap one" line', () => {
  assert.equal(subsHeading([], ''), 'No subscriptions found')
  assert.equal(subsHeading([], 'EUR 0.00'), 'No subscriptions found')
  assert.equal(subsFooter([], 'your Gmail'), 'From your Gmail · nothing to cancel')
  assert.doesNotMatch(subsFooter([], ''), /tap one/)
})

test('Subscriptions: a list is as before', () => {
  const items = [{ service: 'Netflix' }]
  assert.equal(subsHeading(items, 'EUR 12.99'), 'About EUR 12.99 a month')
  assert.equal(subsHeading(items, ''), undefined)
  assert.equal(subsFooter(items, ''), 'From your receipts · tap one to cancel it — nothing happens until you say yes')
})
