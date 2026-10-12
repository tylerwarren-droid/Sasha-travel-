// Sasha 248 · one place card: facts carry their source; a Google category is only ever labelled.
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { placeFacts, photoOf, sourceWord } from '../lib/place-view.mjs'

test("the site's own words are the fact, with their source", () => {
  const card = { name: 'Casa Lucio', type: 'traditional Spanish restaurant', place: { type: { value: 'traditional Spanish restaurant', quote: 'Cocina española…', source: 'site' } } }
  const f = placeFacts(card)
  assert.equal(f.type.value, 'traditional Spanish restaurant')
  assert.equal(sourceWord(f.type), 'From their own site')
})

test("Google's category is only labelled (Tyler's 12 Oct test: a Spanish place shown as Korean)", () => {
  const f = placeFacts({ name: 'X', type: 'listed on Google as Korean restaurant', type_source: 'google' })
  assert.match(f.type.value, /^listed on Google as /)
  assert.equal(sourceWord(f.type), 'From Google')
})

test('a photo carries its credit', () => {
  assert.deepEqual(photoOf({ gphoto: { uri: 'https://lh3.googleusercontent.com/x' } }), { url: 'https://lh3.googleusercontent.com/x', mark: 'Google' })
  assert.equal(photoOf({ photo: 'https://casalucio.es/og.jpg' }).mark, 'their site')
  assert.equal(photoOf({}), null)
})
