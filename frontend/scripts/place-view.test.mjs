// Sasha 248 · one place card: facts carry their source; a Google category is only ever labelled.
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { cantRead, placeFacts, photoOf, sourceWord } from '../lib/place-view.mjs'

test("the site's own words are the fact, with their source", () => {
  const card = { name: 'Casa Lucio', type: 'traditional Spanish restaurant', place: { type: { value: 'traditional Spanish restaurant', quote: 'Cocina española…', source: 'site' } } }
  const f = placeFacts(card)
  assert.equal(f.type.value, 'traditional Spanish restaurant')
  assert.equal(sourceWord(f.type), 'From their own site')
})

test("Google's category is never shown as what it is (Sasha 250: arroz places the map calls Korean)", () => {
  assert.equal(placeFacts({ name: 'X', type: 'listed on the map as Korean restaurant', type_source: 'map' }).type, null)
  assert.equal(placeFacts({ place: { type: { value: 'listed on the map as Korean restaurant', source: 'map' } } }).type, null)
})

test("why a site couldn't be read is one sentence, whatever shape it came in (it crashed the sheet live)", () => {
  assert.equal(cantRead({ cant_read: { rule: 'refused', say: 'x.net turned us away.', evidence: '403', at: 1 } }), 'x.net turned us away.')
  assert.equal(cantRead({ cant_read: 'no text' }), 'no text')
  assert.equal(cantRead({}), null)
})

test('a photo carries its credit', () => {
  assert.deepEqual(photoOf({ gphoto: { uri: 'https://lh3.googleusercontent.com/x' } }), { url: 'https://lh3.googleusercontent.com/x', mark: 'Google' })
  assert.equal(photoOf({ photo: 'https://casalucio.es/og.jpg' }).mark, 'their site')
  assert.equal(photoOf({}), null)
})
